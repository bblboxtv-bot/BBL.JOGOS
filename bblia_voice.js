'use strict';
// OpenAI voice: continuous WebRTC conversation and separate message dictation.
function voiceProviderOptions(){return {provider:'openai',paid_authorized:true}}
let realtimePC=null,realtimeConnecting=false,realtimeAudio=null;
let voiceGeneration=0,voiceCapture=null,voiceContext=null,voiceRecorder=null,voiceMeterTimer=null;
let voiceSpeaking=false,voiceRequest=null,voiceCancelPlayback=null,voiceUseRecorder=false;
const voicePendingRequests=new Set();
let voiceAnalyser=null,voiceSource=null,voiceSink=null,voiceOneShot=false;
let voiceBarge=null;

// Keep a short PCM pre-roll so an interruption includes the first syllable.
function stopVoiceBarge(){
 const state=voiceBarge;voiceBarge=null;if(!state)return;
 state.processor.onaudioprocess=null;
 for(const node of [state.source,state.processor,state.sink])try{node.disconnect()}catch(e){}
}
function voiceBargeWav(parts,rate){
 const length=parts.reduce((n,p)=>n+p.length,0),input=new Float32Array(length);let offset=0;
 for(const part of parts){input.set(part,offset);offset+=part.length}
 const target=16000,count=Math.floor(length*target/rate),buffer=new ArrayBuffer(44+count*2),v=new DataView(buffer);
 const text=(at,s)=>{for(let i=0;i<s.length;i++)v.setUint8(at+i,s.charCodeAt(i))};
 text(0,'RIFF');v.setUint32(4,36+count*2,true);text(8,'WAVEfmt ');v.setUint32(16,16,true);
 v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,target,true);v.setUint32(28,target*2,true);
 v.setUint16(32,2,true);v.setUint16(34,16,true);text(36,'data');v.setUint32(40,count*2,true);
 for(let i=0;i<count;i++){const a=Math.floor(i*rate/target),b=Math.min(length,Math.floor((i+1)*rate/target));let sum=0;for(let j=a;j<b;j++)sum+=input[j];v.setInt16(44+i*2,Math.max(-1,Math.min(1,sum/Math.max(1,b-a)))*32767,true)}
 return new Blob([buffer],{type:'audio/wav'});
}
async function finishVoiceBarge(state){
 if(voiceBarge!==state)return;
 const blob=voiceBargeWav(state.parts,state.rate);stopVoiceBarge();
 const generation=state.generation,active=()=>voiceMode&&generation===voiceGeneration;
 waitingVoice=true;status.textContent='Reconhecendo sua fala...';
 const controller=new AbortController();voiceRequest=controller;
 const timeout=setTimeout(()=>controller.abort(),20000);
 try{
  const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=reject;reader.readAsDataURL(blob)});
  if(!active())return;
  const response=await fetch('/api/transcribe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...voiceProviderOptions(),audio:encoded,mime:blob.type}),signal:controller.signal});
  const result=await response.json();if(!active())return;if(!response.ok)throw Error(result.error||'Falha no reconhecimento.');
  // The interrupted answer's finally must release the composer before the new turn.
  while(send.disabled&&active())await new Promise(resolve=>setTimeout(resolve,30));
  if(active()){waitingVoice=false;await sendRecognizedVoice(result.text)}
 }catch(error){if(active())voiceFailure(error)}finally{
  clearTimeout(timeout);if(voiceRequest===controller)voiceRequest=null;
 }
}
async function startVoiceBarge(token){
 if(!voiceMode||!navigator.mediaDevices?.getUserMedia)return;
 const generation=voiceGeneration,active=()=>voiceMode&&generation===voiceGeneration&&token===voiceToken&&voiceSpeaking;
 try{
  if(!voiceCapture?.getAudioTracks().some(t=>t.readyState==='live')){
   const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
   if(!active()){stream.getTracks().forEach(t=>t.stop());return}voiceCapture=stream;
  }
  if(!active())return;prepareVoiceContext();await voiceContext?.resume();
  if(!active()||!voiceContext?.createScriptProcessor)return;
  stopVoiceBarge();
  const source=voiceContext.createMediaStreamSource(voiceCapture),processor=voiceContext.createScriptProcessor(2048,1,1),sink=voiceContext.createGain();sink.gain.value=0;
  const state={source,processor,sink,generation,rate:voiceContext.sampleRate,parts:[],elapsed:0,levels:[],quiet:0,triggered:false};voiceBarge=state;
  processor.onaudioprocess=event=>{
   if(voiceBarge!==state||generation!==voiceGeneration||!voiceMode)return;
   const samples=new Float32Array(event.inputBuffer.getChannelData(0)),duration=samples.length/state.rate;
   const rms=Math.sqrt(samples.reduce((n,v)=>n+v*v,0)/samples.length);state.elapsed+=duration;
   state.parts.push(samples);
   if(!state.triggered){
    while(state.parts.length>Math.ceil(state.rate*.45/samples.length))state.parts.shift();
    state.levels=state.levels.filter(t=>state.elapsed-t<.45);
    if(rms>.008)state.levels.push(state.elapsed);
    if(state.levels.length*duration>=.12){
     state.triggered=true;state.elapsed=0;clearVoiceTimers();stopSpeaking(true);
     waitingVoice=true;status.textContent='Pode falar. Estou ouvindo você.';
    }
   }else{
    state.quiet=rms>.006?0:state.quiet+duration;
    if(state.quiet>=.7||state.elapsed>=20)finishVoiceBarge(state);
   }
  };
  source.connect(processor);processor.connect(sink);sink.connect(voiceContext.destination);
 }catch(error){if(active())status.textContent='Voz ativa. Toque no microfone para parar se o aparelho não permitir interrupção.'}
}

// Default to the user's requested brighter feminine voice and brisker delivery.
let voicePlaybackRate=Number(localStorage.getItem?.('bblia_voice_speed')||1.15);
if(![1,1.15,1.3].includes(voicePlaybackRate))voicePlaybackRate=1.15;
if(localStorage.getItem?.('bblia_voice_style')!=='feminina-agil-v1'){
 voiceIndex=0;localStorage.setItem('bblia_voice','0');localStorage.setItem('bblia_voice_style','feminina-agil-v1');
}

// A valid silent clip unlocks the reusable player during the user's tap.
unlockVoicePlayback=function(){
 prepareVoiceContext();
 if(unlockedAudio)return;
 const player=new Audio();player.setAttribute('playsinline','');player.preload='auto';
 player.src='data:audio/wav;base64,UklGRkQDAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YSADAACAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgA==';unlockedAudio=player;
 player.play().catch(()=>{});
};

function androidVoiceCapture(){
 return !!window.BBLAndroid||/; wv\)|\bwv\b/i.test(navigator.userAgent||'');
}
function prepareVoiceContext(){
 const AC=window.AudioContext||window.webkitAudioContext;
 if(!voiceContext&&AC)voiceContext=new AC();
 // Create and resume on the original tap, before microphone permission awaits.
 if(voiceContext?.state==='suspended')voiceContext.resume().catch(()=>{});
}
function createVoiceTurnDetector(){
 let voiced=[],lastSpeech=0,heard=false,noise=0.001;
 return {sample(rms,now){
  const threshold=Math.max(0.005,Math.min(0.025,noise*3));
  voiced=voiced.filter(t=>now-t<=650);
  if(rms>threshold){voiced.push(now);lastSpeech=now;if(voiced.length>=3)heard=true}
  else noise=noise*0.97+rms*0.03;
  return {heard,finished:heard&&now-lastSpeech>=850};
 }};
}

function endRealtime(){
 stopVoiceBarge();
 voiceGeneration++;clearVoiceTimers();clearInterval(voiceMeterTimer);voiceMeterTimer=null;
 voiceRequest?.abort();voiceRequest=null;
 for(const controller of voicePendingRequests)controller.abort();voicePendingRequests.clear();
 if(recognition){recognition.onend=recognition.onresult=recognition.onerror=null;try{recognition.abort()}catch(e){}recognition=null}
 const recorder=voiceRecorder;voiceRecorder=null;
 if(recorder){recorder.onstop=null;if(recorder.state!=='inactive')try{recorder.stop()}catch(e){}}
 voiceCapture?.getTracks().forEach(t=>t.stop());voiceCapture=null;
 try{voiceSource?.disconnect();voiceSink?.disconnect()}catch(e){}voiceSource=voiceAnalyser=voiceSink=null;
 if(voiceContext){voiceContext.close().catch(()=>{});voiceContext=null}
 realtimeConnecting=false;waitingVoice=false;voiceOneShot=false;
}
stopSpeaking=function(keepBarge=false){
 if(keepBarge!==true)stopVoiceBarge();
 voiceToken++;voiceRequest?.abort();voiceRequest=null;
 for(const controller of voicePendingRequests)controller.abort();voicePendingRequests.clear();
 voiceCancelPlayback?.();voiceCancelPlayback=null;
 if(currentAudio){currentAudio.pause();currentAudio=null}
 if('speechSynthesis' in window)speechSynthesis.cancel();
 voiceSpeaking=false;
};
function speechChunks(text,max=260){
 const clean=String(text).replace(/```[\s\S]*?```/g,' Trecho de código disponível na tela. ').replace(/https?:\/\/\S+/g,'').replace(/[*#`]/g,'').trim();
 const parts=[];let rest=clean;
 while(rest.length>max){let cut=Math.max(rest.lastIndexOf('. ',max),rest.lastIndexOf('! ',max),rest.lastIndexOf('? ',max));if(cut<max/3)cut=rest.lastIndexOf(' ',max);if(cut<1)cut=max;else cut++;parts.push(rest.slice(0,cut));rest=rest.slice(cut).trim()}
 if(rest)parts.push(rest);return parts;
}
function deviceSpeech(text,token){
 return new Promise((resolve,reject)=>{
  if(token!==voiceToken)return resolve();
  if(!('speechSynthesis' in window))return reject(Error('Voz indisponível neste aparelho.'));
  const utterance=new SpeechSynthesisUtterance(text);utterance.lang='pt-BR';utterance.rate=voicePlaybackRate;utterance.pitch=1;
  const selected=selectedVoice();if(selected)utterance.voice=selected;
  let timer;const finish=error=>{clearTimeout(timer);voiceCancelPlayback=null;error?reject(error):resolve()};
  voiceCancelPlayback=()=>finish();utterance.onend=()=>finish();utterance.onerror=e=>finish(Error(e.error||'Falha na voz do aparelho.'));
  timer=setTimeout(()=>{speechSynthesis.cancel();finish(Error('A voz do aparelho não respondeu.'))},Math.max(20000,text.length*150));
  speechSynthesis.speak(utterance);speechSynthesis.resume();
 });
}
async function playSpeechBlob(blob,token){
 const url=URL.createObjectURL(blob),audio=unlockedAudio||new Audio();audio.setAttribute('playsinline','');audio.src=url;audio.defaultPlaybackRate=voicePlaybackRate;audio.playbackRate=voicePlaybackRate;audio.preservesPitch=true;audio.webkitPreservesPitch=true;currentAudio=audio;
 try{await new Promise((resolve,reject)=>{
  let timer;const finish=error=>{clearTimeout(timer);audio.onended=audio.onerror=null;voiceCancelPlayback=null;error?reject(error):resolve()};
  voiceCancelPlayback=()=>{audio.pause();finish()};audio.onended=()=>finish();audio.onerror=()=>finish(Error('Falha ao reproduzir áudio.'));
  timer=setTimeout(()=>{audio.pause();finish(Error('A reprodução não terminou.'))},180000);
  if(token!==voiceToken)return finish();audio.play().catch(finish);
 })}finally{URL.revokeObjectURL(url);if(currentAudio===audio)currentAudio=null}
}
// Keep speech intact while shortening only long silence, including codec padding.
function speechRanges(buffer){
 const channels=Array.from({length:buffer.numberOfChannels},(_,i)=>buffer.getChannelData(i));
 const rate=buffer.sampleRate,length=buffer.length,threshold=0.001;
 const loud=i=>channels.some(channel=>Math.abs(channel[i])>threshold);
 let first=0,last=length-1;while(first<length&&!loud(first))first++;
 if(first===length)return [[0,length]];
 while(last>first&&!loud(last))last--;
 const start=Math.max(0,first-Math.round(rate*0.025)),end=Math.min(length,last+Math.round(rate*0.045)+1);
 const ranges=[];let from=start,i=first;
 while(i<end){
  if(loud(i)){i++;continue}
  const quiet=i;while(i<end&&!loud(i))i++;
  if(i-quiet>rate*0.45&&i<end){
   const keep=Math.round(rate*0.09);ranges.push([from,quiet+keep]);from=i-keep;
  }
 }
 if(end>from)ranges.push([from,end]);return ranges;
}
async function decodeSpeechSegments(segments){
 prepareVoiceContext();const context=voiceContext;
 if(!context?.decodeAudioData||context.state!=='running')return null;
 const decoded=[];
 for(const encoded of segments){
  const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
  decoded.push(await context.decodeAudioData(bytes.buffer));
 }
 const ranges=decoded.map(buffer=>speechRanges(buffer));
 const frames=ranges.reduce((total,parts)=>total+parts.reduce((n,[a,b])=>n+b-a,0),0);
 if(!frames)return null;
 const channels=Math.max(...decoded.map(buffer=>buffer.numberOfChannels));
 const joined=context.createBuffer(channels,frames,context.sampleRate);
 for(let channel=0;channel<channels;channel++){
  let offset=0;const target=joined.getChannelData(channel);
  decoded.forEach((buffer,index)=>{const samples=buffer.getChannelData(Math.min(channel,buffer.numberOfChannels-1));
   for(const [a,b] of ranges[index]){target.set(samples.subarray(a,b),offset);offset+=b-a}
  });
 }
 return joined;
}
async function loadSpeechChunk(text,token){
 const controller=new AbortController();voicePendingRequests.add(controller);voiceRequest=controller;
 const timeout=setTimeout(()=>controller.abort(),16000);
 try{
  const response=await fetch('/api/voice',{method:'POST',headers:{'Content-Type':'application/json'},
   body:JSON.stringify({...voiceProviderOptions(),text,voice:voiceOptions[voiceIndex]?.api||'nova',segments:true}),signal:controller.signal});
  if(!response.ok)throw Error('Serviço de voz indisponível.');
  if(token!==voiceToken)return {};
  if(response.headers?.get('Content-Type')?.includes('application/json')){
   const data=await response.json();if(!Array.isArray(data.segments)||!data.segments.length)throw Error('Áudio vazio.');
   const buffer=await decodeSpeechSegments(data.segments).catch(()=>null);
   if(buffer)return {buffer};
   const parts=data.segments.map(encoded=>Uint8Array.from(atob(encoded),c=>c.charCodeAt(0)));
   return {blob:new Blob(parts,{type:data.mime||'audio/mpeg'})};
  }
  const blob=await response.blob();if(!blob.size)throw Error('Áudio vazio.');return {blob};
 }catch(error){return {error}}finally{
  clearTimeout(timeout);voicePendingRequests.delete(controller);if(voiceRequest===controller)voiceRequest=null;
 }
}
function playSpeechBuffer(buffer,token){
 // HTML audio preserves the voice's pitch when accelerating. BufferSource changes it.
 const channels=buffer.numberOfChannels,length=buffer.length,bytes=new ArrayBuffer(44+length*channels*2),view=new DataView(bytes);
 const text=(at,value)=>{for(let i=0;i<value.length;i++)view.setUint8(at+i,value.charCodeAt(i))};
 text(0,'RIFF');view.setUint32(4,bytes.byteLength-8,true);text(8,'WAVEfmt ');view.setUint32(16,16,true);
 view.setUint16(20,1,true);view.setUint16(22,channels,true);view.setUint32(24,buffer.sampleRate,true);
 view.setUint32(28,buffer.sampleRate*channels*2,true);view.setUint16(32,channels*2,true);view.setUint16(34,16,true);text(36,'data');view.setUint32(40,bytes.byteLength-44,true);
 const samples=Array.from({length:channels},(_,c)=>buffer.getChannelData(c));
 for(let i=0;i<length;i++)for(let c=0;c<channels;c++)view.setInt16(44+(i*channels+c)*2,Math.max(-1,Math.min(1,samples[c][i]))*32767,true);
 return playSpeechBlob(new Blob([bytes],{type:'audio/wav'}),token);
}
speak=async function(text){
 stopSpeaking();const token=voiceToken;voiceSpeaking=true;const chunks=speechChunks(text);
 startVoiceBarge(token);
 // Prepare the next chunk during playback, never after a sentence has finished.
 let pending=chunks.length?loadSpeechChunk(chunks[0],token):null;
 try{for(let index=0;index<chunks.length;index++){
  const ready=await pending;if(token!==voiceToken)return;
  pending=index+1<chunks.length?loadSpeechChunk(chunks[index+1],token):null;
  if(ready.error){
   if(token!==voiceToken)return;
   status.textContent='Usando voz do aparelho enquanto o áudio online está indisponível.';
   await deviceSpeech(chunks[index],token);
   continue;
  }
  try{
   if(ready.buffer)await playSpeechBuffer(ready.buffer,token);
   else if(ready.blob)await playSpeechBlob(ready.blob,token);
  }catch(error){if(token!==voiceToken)return;throw error}
 }}finally{if(token===voiceToken){voiceSpeaking=false;stopVoiceBarge()}}
};

function offerVoiceReplay(answer){
 const bubble=feed.lastElementChild;if(!bubble)return;
 bubble.querySelector?.('.voice-replay')?.remove();
 const button=document.createElement('button');button.className='subbtn voice-replay';button.textContent='🔊 Ouvir resposta';
 button.onclick=()=>{unlockVoicePlayback();replyByVoice(answer)};bubble.append(button);
}
replyByVoice=async function(answer){
 waitingVoice=true;
 if(!muted){
  status.textContent='🔊 BBLIA falando...';
  try{await speak(answer);if(!voiceBarge?.triggered)status.textContent='Resposta concluída'}catch(e){status.textContent='Toque em Ouvir resposta para ativar o som.';offerVoiceReplay(answer)}
 }
 waitingVoice=false;
 if(voiceMode&&document.getElementById('auto').checked)scheduleVoiceListen(450);
};
scheduleVoiceListen=function(delay=300){
 clearTimeout(voiceRestartTimer);
 if(!voiceMode||waitingVoice||voiceSpeaking||voiceBarge)return;
 voiceRestartTimer=setTimeout(()=>{voiceRestartTimer=null;if(voiceMode&&!waitingVoice&&!voiceSpeaking&&!send.disabled)listenVoice()},delay);
};
function voiceFailure(error){
 const denied=['NotAllowedError','PermissionDeniedError','not-allowed','service-not-allowed'].includes(error?.name||error?.error);
 if(denied){voiceMode=false;endRealtime();setVoiceUI();status.textContent='Autorize o microfone nas configurações do aplicativo ou navegador.';return}
 waitingVoice=false;status.textContent=error?.message||'Não consegui ouvir. Tente falar novamente.';
 if(voiceMode)scheduleVoiceListen(1800);
}
async function sendRecognizedVoice(text){
 if(!text?.trim()){waitingVoice=false;if(voiceMode)scheduleVoiceListen(400);return}
 waitingVoice=true;prompt.value=text.trim();status.textContent='Enviando sua pergunta...';
 try{await sendMessage()}finally{waitingVoice=false;if(voiceMode&&!voiceSpeaking&&document.getElementById('auto').checked)scheduleVoiceListen(450)}
}
async function captureVoice(){
 if(realtimeConnecting||voiceRecorder||waitingVoice||voiceSpeaking)return;
 const generation=voiceGeneration;realtimeConnecting=true;
 const active=()=>generation===voiceGeneration&&(voiceMode||voiceOneShot);
 try{
  if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder)throw Error('Este aparelho não permite gravar a voz. Use o microfone do teclado.');
  if(!voiceCapture?.getAudioTracks().some(t=>t.readyState==='live')){
   const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
   if(!active()){stream.getTracks().forEach(t=>t.stop());return}voiceCapture=stream;
  }
  if(!active())return;
  prepareVoiceContext();
  if(!voiceContext)throw Error('Este aparelho não permite abrir o áudio da conversa.');
  if(!voiceSource){voiceSource=voiceContext.createMediaStreamSource(voiceCapture);voiceAnalyser=voiceContext.createAnalyser();voiceAnalyser.fftSize=1024;voiceSource.connect(voiceAnalyser);voiceSink=voiceContext.createGain();voiceSink.gain.value=0;voiceAnalyser.connect(voiceSink);voiceSink.connect(voiceContext.destination)}
  await voiceContext.resume();if(!active())return;
  const mime=['audio/webm;codecs=opus','audio/mp4','audio/webm','audio/ogg;codecs=opus'].find(t=>MediaRecorder.isTypeSupported(t));
  const recorder=new MediaRecorder(voiceCapture,mime?{mimeType:mime}:{});voiceRecorder=recorder;
  const chunks=[],detector=createVoiceTurnDetector();let bytes=0,heard=false,started=Date.now();
  recorder.ondataavailable=e=>{if(e.data.size){chunks.push(e.data);bytes+=e.data.size}};
  recorder.onerror=()=>{if(active()){endRealtime();voiceMode=false;setVoiceUI();status.textContent='Falha ao gravar a voz. Toque no microfone para tentar novamente.'}};
  recorder.onstop=async()=>{
   clearInterval(voiceMeterTimer);voiceMeterTimer=null;if(voiceRecorder===recorder)voiceRecorder=null;
   if(!active())return;
   if(!heard||bytes<100){if(voiceMode)scheduleVoiceListen(150);else{endRealtime();status.textContent='Nenhuma fala reconhecida.'}return}
   waitingVoice=true;status.textContent='Reconhecendo sua fala...';
   const controller=new AbortController();voiceRequest=controller;const timeout=setTimeout(()=>controller.abort(),40000);
   try{
    const blob=new Blob(chunks,{type:recorder.mimeType||mime});
    const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=reject;reader.readAsDataURL(blob)});
    if(!active())return;
    const response=await fetch('/api/transcribe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...voiceProviderOptions(),audio:encoded,mime:blob.type}),signal:controller.signal});const result=await response.json();
    if(!active())return;if(!response.ok)throw Error(result.error||'Falha no reconhecimento.');
    waitingVoice=false;await sendRecognizedVoice(result.text);
   }catch(e){if(active())voiceFailure(e)}finally{clearTimeout(timeout);if(voiceRequest===controller)voiceRequest=null;if(voiceOneShot)endRealtime()}
  };
  recorder.start(200);status.textContent='🎙️ Pode falar. Estou ouvindo.';
  const samples=new Float32Array(voiceAnalyser.fftSize);
  voiceMeterTimer=setInterval(()=>{
   if(!active()||recorder.state!=='recording')return;
   voiceAnalyser.getFloatTimeDomainData(samples);const rms=Math.sqrt(samples.reduce((sum,v)=>sum+v*v,0)/samples.length),now=Date.now();
   const turn=detector.sample(rms,now);heard=turn.heard;
   // Send only after speech and a pause. Silence never sends a chat message.
   if(turn.finished||now-started>35000||bytes>1800000){clearInterval(voiceMeterTimer);voiceMeterTimer=null;recorder.stop()}
  },100);
 }catch(e){if(active())voiceFailure(e)}finally{if(generation===voiceGeneration)realtimeConnecting=false}
}
listenVoice=function(){
 if(!voiceMode||waitingVoice||voiceSpeaking||voiceBarge||send.disabled||recognition||voiceRecorder||realtimeConnecting)return;
 const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
 if(!SR||voiceUseRecorder||androidVoiceCapture()){captureVoice();return}
 const generation=voiceGeneration,rec=new SR();recognition=rec;let spoken='',fallback=false,delivered=false;
 const recover=()=>{if(generation!==voiceGeneration||recognition!==rec||!voiceMode||delivered)return;recognition=null;rec.onend=null;try{rec.abort()}catch(e){}voiceUseRecorder=true;captureVoice()};
 const deliver=()=>{if(delivered||generation!==voiceGeneration||!voiceMode||!spoken)return;delivered=true;clearTimeout(voiceListenTimer);if(rec===recognition)recognition=null;try{rec.stop?.()}catch(e){}sendRecognizedVoice(spoken)};
 rec.lang='pt-BR';rec.continuous=false;rec.interimResults=false;
 rec.onspeechstart=()=>{clearTimeout(voiceListenTimer);voiceListenTimer=setTimeout(recover,35000)};
 rec.onspeechend=()=>{clearTimeout(voiceListenTimer);voiceListenTimer=setTimeout(recover,5000)};
 rec.onresult=e=>{if(generation!==voiceGeneration)return;spoken=Array.from(e.results).filter(r=>r.isFinal!==false).map(r=>r[0].transcript).join(' ').trim();if(spoken){waitingVoice=true;deliver()}};
 rec.onerror=e=>{if(generation!==voiceGeneration)return;if(e.error==='not-allowed'){voiceFailure(e);return}if(e.error!=='no-speech'&&e.error!=='aborted'){voiceUseRecorder=true;fallback=true}};
 rec.onend=()=>{clearTimeout(voiceListenTimer);if(rec===recognition)recognition=null;if(generation!==voiceGeneration||!voiceMode)return;if(delivered)return;if(spoken)deliver();else if(fallback)captureVoice();else if(document.getElementById('auto').checked)scheduleVoiceListen(500)};
 try{rec.start();voiceListenTimer=setTimeout(recover,10000);status.textContent='🎙️ Pode falar. Estou ouvindo.'}catch(e){recognition=null;voiceUseRecorder=true;captureVoice()}
};
function toggleVoice(){
 if(voiceMode){voiceMode=false;endRealtime();stopSpeaking();status.textContent='Conversa por voz encerrada';setVoiceUI();return}
 if(send.disabled){status.textContent='Aguarde a resposta atual terminar.';return}
 stopSpeaking();endRealtime();unlockVoicePlayback();
 if(dictation){dictation.onend=null;try{dictation.abort()}catch(e){}dictation=null;document.getElementById('dictate').classList.remove('listening')}
 voiceMode=true;document.getElementById('auto').checked=true;if(androidVoiceCapture()||!window.SpeechRecognition&&!window.webkitSpeechRecognition)prepareVoiceContext();muted=false;localStorage.setItem('bblia_muted','0');updateMute();setVoiceUI();listenVoice();
};
const originalDictateMessage=dictateMessage;
dictateMessage=function(){
 if(voiceMode)return;
 if(voiceOneShot){if(voiceRecorder?.state==='recording')voiceRecorder.stop();return}
 // Use the same OpenAI transcription backend for the message microphone.
 endRealtime();unlockVoicePlayback();prepareVoiceContext();voiceOneShot=true;captureVoice();
};
send.addEventListener?.('click',()=>unlockVoicePlayback(),{capture:true});
prompt.addEventListener?.('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey)unlockVoicePlayback()},{capture:true});
window.addEventListener('pagehide',()=>{voiceMode=false;endRealtime();stopSpeaking()});

if(typeof openSection==='function'){
 const voiceOpenSection=openSection;
 openSection=function(section){
  const result=voiceOpenSection(section);if(section!=='voices')return result;
  const parent=document.getElementById('modalContent');if(!parent)return result;
  const description=parent.querySelector('p');if(description)description.textContent='Conversa contínua: voz feminina Marin, diretamente na OpenAI. As opções abaixo ajustam a leitura de mensagens e o ditado.';
  const label=document.createElement('label');label.className='work-field';label.textContent='Velocidade da leitura';
  const select=document.createElement('select');select.setAttribute('aria-label','Velocidade da fala');
  for(const [value,name] of [[1,'Normal'],[1.15,'Ágil'],[1.3,'Rápida']]){const option=document.createElement('option');option.value=String(value);option.textContent=name;select.append(option)}
  select.value=String(voicePlaybackRate);select.onchange=()=>{voicePlaybackRate=Number(select.value);localStorage.setItem('bblia_voice_speed',String(voicePlaybackRate));if(currentAudio)currentAudio.playbackRate=voicePlaybackRate};
  label.append(select);parent.append(label);
  const usage=document.createElement('p');const days=typeof workspace!=='undefined'?workspace.preferences.voiceUsage||{}:{};
  const values=Object.values(days);usage.textContent='Voz em tempo real registrada neste espaço: '+values.reduce((n,r)=>n+r.responses,0)+' respostas, '+values.reduce((n,r)=>n+r.input,0)+' tokens de entrada e '+values.reduce((n,r)=>n+r.output,0)+' de saída nos últimos dias. Não inclui chat, trabalhos ou ditado; não é uma fatura. Consulte a OpenAI para o valor cobrado.';parent.append(usage);return result;
 };
}

// The main microphone streams speech directly; dictation keeps the recorder above.
let realtimeChannel=null,realtimeAbort=null,realtimeStarted=0,realtimeWatchdog=null;
let realtimeDisconnectedTimer=null;
const realtimeSeen=new Set(),realtimeTranscripts=new Map(),realtimeOrder=new Map();
function sendRealtimeEvent(channel,event){
 if(channel?.readyState!=='open')return false;
 channel.send(JSON.stringify(event));return true;
}
function syncRealtimeMicrophone(){
 if(!realtimePC)return;
 for(const track of voiceCapture?.getAudioTracks()||[])track.enabled=voiceMode&&!send.disabled;
}
function recordRealtimeUsage(response){
 if(!response?.id||realtimeSeen.has('usage:'+response.id))return;
 realtimeSeen.add('usage:'+response.id);
 const usage=response.usage;if(!usage)return;
 const day=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Sao_Paulo',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
 const days=workspace.preferences.voiceUsage||{};
 const row=days[day]||{responses:0,input:0,output:0,model:'gpt-realtime'};
 row.responses++;row.input+=Number(usage.input_tokens)||0;row.output+=Number(usage.output_tokens)||0;days[day]=row;
 workspace.preferences.voiceUsage=Object.fromEntries(Object.entries(days).sort().slice(-31));persist();
}
function realtimeTranscript(event,role,final){
 const key=role+':'+event.item_id;
 let entry=realtimeTranscripts.get(key);
 const text=final?(event.transcript||event.text||entry?.text||''):(entry?.text||'')+(event.delta||'');
 if(!text.trim())return;
 if(!realtimeOrder.has(event.item_id))realtimeOrder.set(event.item_id,realtimeOrder.size);
 if(!entry){entry={bubble:add(role,text),text:'',saved:false,order:realtimeOrder.get(event.item_id)};realtimeTranscripts.set(key,entry)}
 entry.text=text;entry.bubble.textContent=text;
 if(final&&!entry.saved){
  const next=Array.from(realtimeTranscripts.values()).filter(e=>e.saved&&e.order>entry.order).sort((a,b)=>a.order-b.order)[0];
  entry.saved=true;entry.message={role,content:text};
  if(next&&history.includes(next.message)){history.splice(history.indexOf(next.message),0,entry.message);if(next.bubble.parentNode===feed)feed.insertBefore(entry.bubble,next.bubble)}
  else history.push(entry.message);saveChat();
 }
 else if(final&&entry.message){entry.message.content=text;saveChat()}
}
async function handleRealtimeEvent(event,channel){
 if(channel!==realtimeChannel)return;
 const type=event.type;
 if(type==='conversation.item.added'&&event.item?.type==='message'&&!realtimeOrder.has(event.item.id))realtimeOrder.set(event.item.id,realtimeOrder.size);
 if(type==='session.created'||type==='session.updated')status.textContent='🎙️ Pode falar. Conversa OpenAI em tempo real.';
 else if(type==='input_audio_buffer.speech_started'){
  voiceSpeaking=false;waitingVoice=false;status.textContent='🎙️ Estou ouvindo você.';
 }else if(type==='input_audio_buffer.speech_stopped')status.textContent='Preparando a resposta...';
 else if(type==='output_audio_buffer.started'){voiceSpeaking=true;status.textContent='🔊 BBLIA falando...'}
 else if(type==='output_audio_buffer.stopped'||type==='output_audio_buffer.cleared'){
  voiceSpeaking=false;if(!send.disabled)status.textContent='🎙️ Pode continuar falando.';
 }else if(type==='conversation.item.input_audio_transcription.completed')realtimeTranscript(event,'user',true);
 else if(type==='response.output_audio_transcript.delta'||type==='response.audio_transcript.delta'||type==='response.output_text.delta')realtimeTranscript(event,'assistant',false);
 else if(type==='response.output_audio_transcript.done'||type==='response.audio_transcript.done'||type==='response.output_text.done')realtimeTranscript(event,'assistant',true);
 else if(type==='response.function_call_arguments.done'){
  if(event.name==='comando_tvbox'&&typeof handleRealtimeTV==='function')await handleRealtimeTV(event,channel);
  else if(event.name==='fazer_trabalho')await handleRealtimeWork(event,channel);
  else if(event.name==='criar_midia')await handleRealtimeMedia(event,channel);
  else{
   sendRealtimeEvent(channel,{type:'conversation.item.create',item:{type:'function_call_output',call_id:event.call_id,output:JSON.stringify({error:'Ferramenta não disponível.'})}});
   sendRealtimeEvent(channel,{type:'response.create'});
  }
 }else if(type==='response.done'){
  recordRealtimeUsage(event.response);
  const response=event.response;
  if(response?.status==='failed')status.textContent='A resposta por voz falhou. Encerre e tente novamente.';
 }else if(type==='error'){
  status.textContent='Falha na conversa por voz: '+(event.error?.message||'Tente iniciar novamente.');
 }
}
const endRecordedVoice=endRealtime;
endRealtime=function(){
 clearTimeout(realtimeWatchdog);clearTimeout(realtimeDisconnectedTimer);
 realtimeAbort?.abort();realtimeAbort=null;
 const pc=realtimePC;realtimePC=null;
 if(realtimeChannel){realtimeChannel.onmessage=realtimeChannel.onopen=realtimeChannel.onclose=null;try{realtimeChannel.close()}catch(e){}realtimeChannel=null}
 if(pc){pc.onconnectionstatechange=pc.ontrack=null;pc.close()}
 if(realtimeAudio){realtimeAudio.pause();realtimeAudio.srcObject=null;realtimeAudio=null}
 realtimeStarted=0;voiceSpeaking=false;realtimeTranscripts.clear();realtimeSeen.clear();realtimeOrder.clear();
 endRecordedVoice();
};
function stopRealtimeWithError(message){
 voiceMode=false;endRealtime();stopSpeaking();setVoiceUI();status.textContent=message;
}
async function startOpenAIVoice(){
 const generation=voiceGeneration;realtimeConnecting=true;
 const active=()=>voiceMode&&generation===voiceGeneration;
 const controller=new AbortController();realtimeAbort=controller;
 const timeout=setTimeout(()=>controller.abort(),25000);
 try{
  if(!window.RTCPeerConnection||!navigator.mediaDevices?.getUserMedia)throw Error('Conversa em tempo real indisponível neste navegador. Use o ditado de mensagens.');
  const audio=unlockedAudio||new Audio();audio.setAttribute('playsinline','');audio.autoplay=true;audio.muted=muted;realtimeAudio=audio;
  const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
  if(!active()){stream.getTracks().forEach(t=>t.stop());return}voiceCapture=stream;
  const pc=new RTCPeerConnection();realtimePC=pc;for(const track of stream.getAudioTracks())pc.addTrack(track,stream);
  pc.ontrack=e=>{if(!active())return;audio.srcObject=e.streams[0];audio.play().catch(()=>{status.textContent='Toque em Ativar som para ouvir.';const b=document.createElement('button');b.textContent='Ativar som';b.className='subbtn';b.onclick=()=>audio.play().then(()=>b.remove()).catch(()=>{});feed.append(b)})};
  pc.onconnectionstatechange=()=>{
   if(!active())return;clearTimeout(realtimeDisconnectedTimer);
   if(pc.connectionState==='failed'||pc.connectionState==='closed')stopRealtimeWithError('A conexão de voz caiu. Toque no microfone para reconectar.');
   else if(pc.connectionState==='disconnected')realtimeDisconnectedTimer=setTimeout(()=>{if(active()&&pc.connectionState==='disconnected')stopRealtimeWithError('Conexão de voz interrompida. Toque no microfone para reconectar.')},8000);
  };
  const channel=pc.createDataChannel('oai-events');realtimeChannel=channel;
  channel.onmessage=event=>{try{const data=JSON.parse(event.data);handleRealtimeEvent(data,channel).catch(()=>{if(active())status.textContent='Não foi possível concluir esta etapa da conversa.'})}catch(e){}};
  channel.onopen=()=>{if(!active())return;clearTimeout(realtimeWatchdog);realtimeStarted=Date.now();realtimeConnecting=false;status.textContent='🎙️ Pode falar. Estou ouvindo.';syncRealtimeMicrophone()};
  channel.onclose=()=>{if(active())stopRealtimeWithError('A conversa por voz foi desconectada. Toque no microfone para retomar.')};
  const context=JSON.stringify({name:workspace.preferences.name,instructions:workspace.preferences.instructions,project:typeof currentProject==='function'?currentProject()?.name:'',history:history.slice(-8).map(m=>({role:m.role,content:String(m.content).slice(0,1000)}))});
  const response=await fetch('/api/realtime-token',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({paid_authorized:true,context:context.slice(0,12000)}),signal:controller.signal});
  const secret=await response.json();if(!response.ok||!secret.token)throw Error(secret.error||'Não foi possível iniciar a voz OpenAI.');if(!active())return;
  const offer=await pc.createOffer();await pc.setLocalDescription(offer);if(!active())return;
  const answer=await fetch('https://api.openai.com/v1/realtime/calls',{method:'POST',headers:{Authorization:'Bearer '+secret.token,'Content-Type':'application/sdp'},body:offer.sdp,signal:controller.signal});
  if(!answer.ok)throw Error('A OpenAI não abriu a conversa por voz (HTTP '+answer.status+').');
  const sdp=await answer.text();if(!active())return;await pc.setRemoteDescription({type:'answer',sdp});
  if(channel.readyState!=='open')realtimeWatchdog=setTimeout(()=>{if(active()&&channel.readyState!=='open')stopRealtimeWithError('Não foi possível estabelecer o áudio. Toque no microfone para tentar novamente.')},15000);
 }catch(error){if(active())stopRealtimeWithError(error.name==='AbortError'?'A conexão de voz demorou demais. Toque no microfone para tentar novamente.':error.message)}
 finally{clearTimeout(timeout);if(realtimeAbort===controller)realtimeAbort=null;if(active()&&realtimeChannel?.readyState==='open')realtimeConnecting=false}
}
const toggleRecordedVoice=toggleVoice;
toggleVoice=function(){
 if(voiceMode){voiceMode=false;endRealtime();stopSpeaking();setVoiceUI();status.textContent='Conversa por voz encerrada';return}
 if(send.disabled){status.textContent='Aguarde a tarefa atual terminar.';return}
 // Continuous conversation uses the OpenAI Realtime path regardless of chat provider.
 stopSpeaking();endRealtime();unlockVoicePlayback();
 if(dictation){dictation.onend=null;try{dictation.abort()}catch(e){}dictation=null;document.getElementById('dictate').classList.remove('listening')}
 voiceMode=true;muted=false;localStorage.setItem('bblia_muted','0');document.getElementById('auto').checked=true;updateMute();setVoiceUI();status.textContent='Conectando a conversa OpenAI...';startOpenAIVoice();
};
const scheduleRecordedVoice=scheduleVoiceListen;
scheduleVoiceListen=function(delay){if(!realtimePC&&!realtimeConnecting)scheduleRecordedVoice(delay)};
const replyRecordedVoice=replyByVoice;
replyByVoice=async function(answer){if(realtimePC){waitingVoice=false;syncRealtimeMicrophone();return}return replyRecordedVoice(answer)};



