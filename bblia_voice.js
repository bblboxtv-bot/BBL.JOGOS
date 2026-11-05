'use strict';
// Browser recognition + Gemini audio transcription; no paid realtime session.
let realtimePC=null,realtimeConnecting=false,realtimeAudio=null;
let voiceGeneration=0,voiceCapture=null,voiceContext=null,voiceRecorder=null,voiceMeterTimer=null;
let voiceSpeaking=false,voiceRequest=null,voiceCancelPlayback=null,voiceUseRecorder=false;
let voiceAnalyser=null,voiceSource=null,voiceSink=null,voiceOneShot=false;

// Default to the user's requested brighter feminine voice and brisker delivery.
const voicePlaybackRate=1.15;
if(localStorage.getItem?.('bblia_voice_style')!=='feminina-agil-v1'){
 voiceIndex=0;localStorage.setItem('bblia_voice','0');localStorage.setItem('bblia_voice_style','feminina-agil-v1');
}

// A valid silent clip unlocks the reusable player during the user's tap.
unlockVoicePlayback=function(){
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
  return {heard,finished:heard&&now-lastSpeech>=1400};
 }};
}

function endRealtime(){
 voiceGeneration++;clearVoiceTimers();clearInterval(voiceMeterTimer);voiceMeterTimer=null;
 voiceRequest?.abort();voiceRequest=null;
 if(recognition){recognition.onend=recognition.onresult=recognition.onerror=null;try{recognition.abort()}catch(e){}recognition=null}
 const recorder=voiceRecorder;voiceRecorder=null;
 if(recorder){recorder.onstop=null;if(recorder.state!=='inactive')try{recorder.stop()}catch(e){}}
 voiceCapture?.getTracks().forEach(t=>t.stop());voiceCapture=null;
 try{voiceSource?.disconnect();voiceSink?.disconnect()}catch(e){}voiceSource=voiceAnalyser=voiceSink=null;
 if(voiceContext){voiceContext.close().catch(()=>{});voiceContext=null}
 realtimeConnecting=false;waitingVoice=false;voiceOneShot=false;
}
stopSpeaking=function(){
 voiceToken++;voiceRequest?.abort();voiceRequest=null;
 voiceCancelPlayback?.();voiceCancelPlayback=null;
 if(currentAudio){currentAudio.pause();currentAudio=null}
 if('speechSynthesis' in window)speechSynthesis.cancel();
 voiceSpeaking=false;
};
function speechChunks(text,max=550){
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
speak=async function(text){
 stopSpeaking();const token=voiceToken;voiceSpeaking=true;
 try{for(const chunk of speechChunks(text)){
  if(token!==voiceToken)return;
  const controller=new AbortController();voiceRequest=controller;
  const timeout=setTimeout(()=>controller.abort(),25000);
  let blob;
  try{const response=await fetch('/api/voice',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:chunk,voice:voiceOptions[voiceIndex]?.api||'nova'}),signal:controller.signal});if(!response.ok)throw Error('Serviço de voz indisponível.');blob=await response.blob();if(!blob.size)throw Error('Áudio vazio.')}
  catch(e){if(token!==voiceToken)return;await deviceSpeech(chunk,token);continue}
  finally{clearTimeout(timeout);if(voiceRequest===controller)voiceRequest=null}
  if(token!==voiceToken)return;
  try{await playSpeechBlob(blob,token)}catch(e){if(token!==voiceToken)return;await deviceSpeech(chunk,token)}
 }}finally{if(token===voiceToken)voiceSpeaking=false}
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
  try{await speak(answer);status.textContent='Resposta concluída'}catch(e){status.textContent='Toque em Ouvir resposta para ativar o som.';offerVoiceReplay(answer)}
 }
 waitingVoice=false;
 if(voiceMode&&document.getElementById('auto').checked)scheduleVoiceListen(450);
};
scheduleVoiceListen=function(delay=300){
 clearTimeout(voiceRestartTimer);
 if(!voiceMode||waitingVoice||voiceSpeaking)return;
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
 if(!voiceMode||waitingVoice||voiceSpeaking||send.disabled||recognition||voiceRecorder||realtimeConnecting)return;
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
 unlockVoicePlayback();stopSpeaking();endRealtime();
 if(dictation){dictation.onend=null;try{dictation.abort()}catch(e){}dictation=null;document.getElementById('dictate').classList.remove('listening')}
 voiceMode=true;document.getElementById('auto').checked=true;if(androidVoiceCapture()||!window.SpeechRecognition&&!window.webkitSpeechRecognition)prepareVoiceContext();muted=false;localStorage.setItem('bblia_muted','0');updateMute();setVoiceUI();listenVoice();
};
const originalDictateMessage=dictateMessage;
dictateMessage=function(){
 if(voiceMode)return;
 if(window.SpeechRecognition||window.webkitSpeechRecognition)return originalDictateMessage();
 unlockVoicePlayback();endRealtime();prepareVoiceContext();voiceOneShot=true;captureVoice();
};
window.addEventListener('pagehide',()=>{voiceMode=false;endRealtime();stopSpeaking()});
