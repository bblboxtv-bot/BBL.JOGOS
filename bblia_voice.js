'use strict';
// Browser recognition + Gemini audio transcription; no paid realtime session.
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
  const response=await fetch('/api/transcribe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({audio:encoded,mime:blob.type}),signal:controller.signal});
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
  const state={source,processor,sink,generation,rate:voiceContext.sampleRate,parts:[],elapsed:0,voiced:0,quiet:0,triggered:false};voiceBarge=state;
  processor.onaudioprocess=event=>{
   if(voiceBarge!==state||generation!==voiceGeneration||!voiceMode)return;
   const samples=new Float32Array(event.inputBuffer.getChannelData(0)),duration=samples.length/state.rate;
   const rms=Math.sqrt(samples.reduce((n,v)=>n+v*v,0)/samples.length);state.elapsed+=duration;
   state.parts.push(samples);
   if(!state.triggered){
    while(state.parts.length>Math.ceil(state.rate*.45/samples.length))state.parts.shift();
    state.voiced=rms>.018?state.voiced+duration:0;
    if(state.voiced>=.16){
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
const voicePlaybackRate=1.15;
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
  const utterance=new SpeechSynthesisUtterance(text);utterance.lang='pt-BR';utterance.rate=voicePlaybackRate;utterance.pitch=1.08;
  const selected=selectedVoice();if(selected)utterance.voice=selected;
  let timer;const finish=error=>{clearTimeout(timer);voiceCancelPlayback=null;error?reject(error):resolve()};
  voiceCancelPlayback=()=>finish();utterance.onend=()=>finish();utterance.onerror=e=>finish(Error(e.error||'Falha na voz do aparelho.'));
  timer=setTimeout(()=>{speechSynthesis.cancel();finish(Error('A voz do aparelho não respondeu.'))},Math.max(20000,text.length*150));
  speechSynthesis.speak(utterance);speechSynthesis.resume();
 });
}
async function playSpeechBlob(blob,token){
 const url=URL.createObjectURL(blob),audio=unlockedAudio||new Audio();audio.setAttribute('playsinline','');audio.src=url;audio.defaultPlaybackRate=voicePlaybackRate;audio.playbackRate=voicePlaybackRate;audio.preservesPitch=false;audio.webkitPreservesPitch=false;currentAudio=audio;
 try{await new Promise((resolve,reject)=>{
  let timer;const finish=error=>{clearTimeout(timer);audio.onended=audio.onerror=null;voiceCancelPlayback=null;error?reject(error):resolve()};
  voiceCancelPlayback=()=>finish();audio.onended=()=>finish();audio.onerror=()=>finish(Error('Falha ao reproduzir áudio.'));
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
   body:JSON.stringify({text,voice:voiceOptions[voiceIndex]?.api||'nova',segments:true}),signal:controller.signal});
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
 return new Promise((resolve,reject)=>{
  if(token!==voiceToken)return resolve();
  const source=voiceContext.createBufferSource();source.buffer=buffer;source.playbackRate.value=voicePlaybackRate;
  source.connect(voiceContext.destination);
  const finish=error=>{source.onended=null;source.disconnect();voiceCancelPlayback=null;error?reject(error):resolve()};
  voiceCancelPlayback=()=>{try{source.stop()}catch(e){}finish()};source.onended=()=>finish();
  try{source.start()}catch(error){finish(error)}
 });
}
speak=async function(text){
 stopSpeaking();const token=voiceToken;voiceSpeaking=true;const chunks=speechChunks(text);
 startVoiceBarge(token);
 // Prepare the next chunk during playback, never after a sentence has finished.
 let pending=chunks.length?loadSpeechChunk(chunks[0],token):null;
 try{for(let index=0;index<chunks.length;index++){
  const ready=await pending;if(token!==voiceToken)return;
  pending=index+1<chunks.length?loadSpeechChunk(chunks[index+1],token):null;
  if(ready.error){await deviceSpeech(chunks[index],token);continue}
  try{
   if(ready.buffer)await playSpeechBuffer(ready.buffer,token);
   else if(ready.blob)await playSpeechBlob(ready.blob,token);
  }catch(error){if(token!==voiceToken)return;await deviceSpeech(chunks[index],token)}
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
    const response=await fetch('/api/transcribe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({audio:encoded,mime:blob.type}),signal:controller.signal});const result=await response.json();
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
 const deliver=()=>{if(delivered||generation!==voiceGeneration||!voiceMode||!spoken)return;delivered=true;if(rec===recognition)recognition=null;try{rec.stop?.()}catch(e){}sendRecognizedVoice(spoken)};
 rec.lang='pt-BR';rec.continuous=false;rec.interimResults=false;
 rec.onresult=e=>{if(generation!==voiceGeneration)return;spoken=Array.from(e.results).filter(r=>r.isFinal!==false).map(r=>r[0].transcript).join(' ').trim();if(spoken){waitingVoice=true;deliver()}};
 rec.onerror=e=>{if(generation!==voiceGeneration)return;if(e.error==='not-allowed'){voiceFailure(e);return}if(e.error!=='no-speech'&&e.error!=='aborted'){voiceUseRecorder=true;fallback=true}};
 rec.onend=()=>{if(rec===recognition)recognition=null;if(generation!==voiceGeneration||!voiceMode)return;if(delivered)return;if(spoken)deliver();else if(fallback)captureVoice();else if(document.getElementById('auto').checked)scheduleVoiceListen(500)};
 try{rec.start();status.textContent='🎙️ Pode falar. Estou ouvindo.'}catch(e){recognition=null;voiceUseRecorder=true;captureVoice()}
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
 if(window.SpeechRecognition||window.webkitSpeechRecognition)return originalDictateMessage();
 endRealtime();unlockVoicePlayback();prepareVoiceContext();voiceOneShot=true;captureVoice();
};
send.addEventListener?.('click',()=>unlockVoicePlayback(),{capture:true});
prompt.addEventListener?.('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey)unlockVoicePlayback()},{capture:true});
window.addEventListener('pagehide',()=>{voiceMode=false;endRealtime();stopSpeaking()});
