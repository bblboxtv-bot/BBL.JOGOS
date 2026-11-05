'use strict';
let realtimePC=null,realtimeStream=null,realtimeAudio=null,realtimeChannel=null;
let realtimeTimer=null,realtimeConnecting=false,realtimeReconnectTimer=null,realtimeDisconnectTimer=null,realtimeConnectTimer=null;
let realtimeGeneration=0,realtimeReconnectAttempt=0,realtimeResponseActive=false,realtimeOutputActive=false,realtimeUserSpeaking=false;
const realtimeTranscripts=new Set();

function syncRealtimeMicrophone(){
 const listening=voiceMode&&!realtimeResponseActive&&!realtimeOutputActive&&!send.disabled;
 realtimeStream?.getAudioTracks().forEach(track=>{track.enabled=listening});
}
function sendRealtimeEvent(channel,event){
 if(channel?.readyState==='open')channel.send(JSON.stringify(event));
}
function endRealtime({preserveMicrophone=false}={}){
 realtimeGeneration++;
 for(const timer of [realtimeTimer,realtimeReconnectTimer,realtimeDisconnectTimer,realtimeConnectTimer])clearTimeout(timer);
 realtimeTimer=realtimeReconnectTimer=realtimeDisconnectTimer=realtimeConnectTimer=null;realtimeConnecting=false;
 realtimeResponseActive=realtimeOutputActive=realtimeUserSpeaking=false;
 const pc=realtimePC,channel=realtimeChannel,stream=realtimeStream,audio=realtimeAudio;
 const keepMicrophone=preserveMicrophone&&voiceMode&&stream?.getAudioTracks().some(track=>track.readyState==='live');
 realtimePC=realtimeChannel=realtimeAudio=null;
 realtimeStream=keepMicrophone?stream:null;
 if(channel){channel.onopen=channel.onmessage=channel.onclose=channel.onerror=null;try{channel.close()}catch(e){}}
 if(pc){pc.ontrack=pc.onconnectionstatechange=null;try{pc.close()}catch(e){}}
 if(keepMicrophone)stream.getAudioTracks().forEach(track=>{track.enabled=false});
 else stream?.getTracks().forEach(track=>track.stop());
 if(audio){audio.pause();audio.srcObject=null;audio.remove()}
}
function reconnectRealtime(message='Reconectando a conversa por voz...',delay=null){
 if(!voiceMode||realtimeReconnectTimer)return;
 const attempt=realtimeReconnectAttempt+1;
 endRealtime({preserveMicrophone:true});realtimeReconnectAttempt=attempt;setVoiceUI();status.textContent=message;
 realtimeReconnectTimer=setTimeout(()=>{realtimeReconnectTimer=null;if(voiceMode)startRealtime()},delay??Math.min(15000,1000*2**Math.min(attempt-1,4)));
}
function rememberVoice(role,text,id){
 if(!text?.trim()||realtimeTranscripts.has(id))return;
 realtimeTranscripts.add(id);
 if(realtimeTranscripts.size>2000)realtimeTranscripts.delete(realtimeTranscripts.values().next().value);
 history.push({role,content:text.trim()});add(role,text.trim());
 if(typeof saveChat==='function')saveChat();
}
function handleRealtimeEvent(event,channel){
 if(!voiceMode||channel!==realtimeChannel)return;
 if(event.type==='input_audio_buffer.speech_started'){
  realtimeUserSpeaking=true;
  if(!realtimeOutputActive&&!realtimeResponseActive)status.textContent='🎙️ Ouvindo você...';
 }
 if(event.type==='input_audio_buffer.speech_stopped')realtimeUserSpeaking=false;
 if(event.type==='response.created'){
  realtimeResponseActive=true;syncRealtimeMicrophone();status.textContent='🔊 Preparando sua resposta...';
 }
 if(event.type==='output_audio_buffer.started'){
  realtimeOutputActive=true;syncRealtimeMicrophone();status.textContent='🔊 BBLIA falando. Aguarde a resposta terminar.';
 }
 if(event.type==='output_audio_buffer.stopped'||event.type==='output_audio_buffer.cleared'){
  realtimeOutputActive=false;
  // Discard residual noise/echo captured before the microphone was gated.
  sendRealtimeEvent(channel,{type:'input_audio_buffer.clear'});
  syncRealtimeMicrophone();
  if(!realtimeResponseActive&&!send.disabled)status.textContent='🎙️ Pode falar. Continuo ouvindo.';
 }
 if(event.type==='conversation.item.input_audio_transcription.completed'){
  rememberVoice('user',event.transcript,'user:'+event.item_id);
 }
 if(event.type==='response.output_audio_transcript.done'||event.type==='response.audio_transcript.done'){
  rememberVoice('assistant',event.transcript,'assistant:'+event.item_id+':'+event.content_index);
 }
 if(event.type==='response.done'){
  realtimeResponseActive=false;
  const calls=(event.response?.output||[]).filter(item=>item.type==='function_call'&&['criar_midia','fazer_trabalho'].includes(item.name));
  for(const call of calls)Promise.resolve(call.name==='fazer_trabalho'?handleRealtimeWork(call,channel):handleRealtimeMedia(call,channel)).finally(()=>{if(channel===realtimeChannel)syncRealtimeMicrophone()});
  syncRealtimeMicrophone();
  // response.done can precede the end of actual speaker playback.
  if(!realtimeOutputActive&&!send.disabled)status.textContent='🎙️ Pode fazer a próxima pergunta';
 }
 if(event.type==='error'){
  const code=event.error?.code||'';
  if(/session_expired|session_timeout/.test(code))reconnectRealtime();
  else{realtimeResponseActive=false;syncRealtimeMicrophone();status.textContent='Falha na resposta de voz: '+(event.error?.message||'aguardando a próxima pergunta')}
 }
}
function renewRealtimeWhenIdle(){
 if(!voiceMode)return;
 if(realtimeResponseActive||realtimeOutputActive||realtimeUserSpeaking||send.disabled){
  realtimeTimer=setTimeout(renewRealtimeWhenIdle,15000);return;
 }
 reconnectRealtime('Renovando a conexão de voz. A conversa continua...',0);
}
async function startRealtime(){
 if(!voiceMode||realtimeConnecting||realtimePC)return;
 const generation=++realtimeGeneration;
 const current=()=>voiceMode&&generation===realtimeGeneration;
 realtimeConnecting=true;setVoiceUI();status.textContent='Conectando conversa por voz...';
 let stream=null;
 try{
  if(!navigator.mediaDevices?.getUserMedia||!window.RTCPeerConnection){
   voiceMode=false;setVoiceUI();status.textContent='Este navegador não permite conversa por voz. Abra no Safari ou Chrome.';realtimeConnecting=false;return;
  }
  stream=realtimeStream?.getAudioTracks().some(track=>track.readyState==='live')?realtimeStream:
   await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:false}});
  if(!current()){if(stream!==realtimeStream||!voiceMode)stream.getTracks().forEach(track=>track.stop());return}
  realtimeStream=stream;
  realtimeConnectTimer=setTimeout(()=>{if(current())reconnectRealtime()},30000);
  const tokenResponse=await fetch('/api/realtime-token',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
  if(!current())return;
  const data=await tokenResponse.json();
  if(!tokenResponse.ok)throw Error(data.error||'Falha ao conectar a voz');
  if(!current())return;
  const pc=new RTCPeerConnection();realtimePC=pc;
  const audio=document.createElement('audio');audio.autoplay=true;audio.playsInline=true;audio.muted=muted;audio.style.display='none';document.body.append(audio);realtimeAudio=audio;
  pc.ontrack=event=>{if(!current())return;audio.srcObject=event.streams[0];audio.play().catch(()=>{status.textContent='O navegador bloqueou o som. Toque para reabrir a conversa.'})};
  stream.getTracks().forEach(track=>pc.addTrack(track,stream));
  const channel=pc.createDataChannel('oai-events');realtimeChannel=channel;
  channel.onopen=()=>{
   if(!current())return;
   clearTimeout(realtimeConnectTimer);realtimeConnectTimer=null;
   realtimeReconnectAttempt=0;realtimeConnecting=false;
   // Restore recent text context when a connection is renewed.
   for(const message of history.slice(-16)){
    if(!['user','assistant'].includes(message.role)||!message.content?.trim())continue;
    sendRealtimeEvent(channel,{type:'conversation.item.create',item:{type:'message',role:message.role,content:[{type:message.role==='user'?'input_text':'text',text:message.content.slice(0,2000)}]}});
   }
   syncRealtimeMicrophone();status.textContent='🎙️ Conectado. Pode falar normalmente.';
   // Renew before the provider's session expiry, only between turns.
   realtimeTimer=setTimeout(renewRealtimeWhenIdle,50*60*1000);
  };
  channel.onmessage=event=>{if(!current())return;try{handleRealtimeEvent(JSON.parse(event.data),channel)}catch(e){status.textContent='Aguardando a próxima pergunta...'}};
  channel.onclose=()=>{if(current())reconnectRealtime()};
  channel.onerror=()=>{if(current())reconnectRealtime()};
  pc.onconnectionstatechange=()=>{
   if(!current())return;
   if(pc.connectionState==='connected'){clearTimeout(realtimeDisconnectTimer);realtimeDisconnectTimer=null}
   if(pc.connectionState==='disconnected'){
    if(!realtimeDisconnectTimer)realtimeDisconnectTimer=setTimeout(()=>{realtimeDisconnectTimer=null;if(current()&&pc.connectionState==='disconnected')reconnectRealtime()},5000);
   }
   if(['failed','closed'].includes(pc.connectionState))reconnectRealtime();
  };
  const offer=await pc.createOffer();if(!current())return;
  await pc.setLocalDescription(offer);if(!current())return;
  const response=await fetch('https://api.openai.com/v1/realtime/calls',{method:'POST',headers:{'Authorization':'Bearer '+data.token,'Content-Type':'application/sdp'},body:offer.sdp});
  if(!current())return;
  if(!response.ok)throw Error('Conexão de áudio recusada ('+response.status+')');
  const answer=await response.text();if(!current())return;
  await pc.setRemoteDescription({type:'answer',sdp:answer});
 }catch(error){
  if(!current())return;
  if(['NotAllowedError','PermissionDeniedError'].includes(error.name)){
   voiceMode=false;endRealtime();setVoiceUI();status.textContent='Permita o microfone no navegador para conversar.';
  }else reconnectRealtime('Reconectando a voz automaticamente...');
 }
}
function toggleVoice(){
 if(voiceMode){
  voiceMode=false;endRealtime();clearVoiceTimers();try{recognition?.abort()}catch(e){}recognition=null;
  waitingVoice=false;status.textContent='Conversa por voz encerrada';setVoiceUI();return;
 }
 unlockVoicePlayback();
 if(dictation){dictation.onend=null;dictation.stop();dictation=null;document.getElementById('dictate').classList.remove('listening')}
 clearVoiceTimers();try{recognition?.abort()}catch(e){}recognition=null;
 voiceMode=true;realtimeReconnectAttempt=0;startRealtime();
}


// Release capture when leaving the app; reuse is limited to the active voice conversation.
window.addEventListener('pagehide',()=>{voiceMode=false;endRealtime()});
