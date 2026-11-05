const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
function harness(){
 const timers=new Map(),requests=[],audio=[],events={};let sequence=0;
 const c={console,voiceMode:false,muted:false,voiceToken:0,voiceIndex:0,currentAudio:null,unlockedAudio:null,voiceOptions:[{api:'nova'}],waitingVoice:false,recognition:null,dictation:null,voiceRestartTimer:null,voiceListenTimer:null,
  send:{disabled:false},prompt:{value:''},status:{textContent:''},history:[],feed:{lastElementChild:null},setVoiceUI(){},updateMute(){},selectedVoiceRate:()=>1,selectedVoice:()=>null,
  stopSpeaking(){},speak(){},replyByVoice(){},listenVoice(){},scheduleVoiceListen(){},dictateMessage(){},unlockVoicePlayback(){},clearVoiceTimers(){timers.clear()},localStorage:{setItem(){}},
  AbortController,Blob,Float32Array,URL:{createObjectURL:()=> 'blob:test',revokeObjectURL(){}},
  setTimeout(fn,delay){const n=++sequence;timers.set(n,{fn,delay});return n},clearTimeout(n){timers.delete(n)},setInterval(){},clearInterval(){},
  navigator:{},document:{getElementById:()=>({checked:true,classList:{remove(){}}})},
  fetch:async(url,options)=>{requests.push({url,data:JSON.parse(options.body)});return{ok:true,blob:async()=>new Blob(['audio'])}},
  Audio:class{constructor(){audio.push(this)}setAttribute(){}play(){return Promise.resolve()}pause(){}},
  sendMessage:async()=>{c.received=c.prompt.value},
 };
 class Recognition{start(){c.rec=this;c.starts=(c.starts||0)+1}abort(){this.onend?.()}}
 c.window={SpeechRecognition:Recognition,addEventListener:(name,fn)=>{events[name]=fn}};
 vm.createContext(c);vm.runInContext(fs.readFileSync(__dirname+'/bblia_voice.js','utf8'),c);
 const run=code=>vm.runInContext(code,c),flush=async()=>{for(let i=0;i<30;i++)await Promise.resolve()};
 return {c,run,flush,timers,requests,audio,events};
}
(async()=>{
 const h=harness();h.run('muted=true;toggleVoice()');assert.equal(h.c.muted,false);assert.equal(h.c.starts,1);assert.equal(h.requests.length,0,'starting voice does not call OpenAI realtime');
 h.c.rec.onresult({results:[[{transcript:'Bom dia'}]]});h.c.rec.onend();await h.flush();assert.equal(h.c.received,'Bom dia');
 h.run('toggleVoice()');assert.equal(h.c.voiceMode,false);
 const s=harness();const long='Uma resposta longa para ouvir por completo. '.repeat(30)+'FIM.';
 s.c.answer=long;const pending=s.run('speak(answer)');await s.flush();assert.equal(s.requests.length,1);
 s.run('voiceMode=true;scheduleVoiceListen()');assert.equal([...s.timers.values()].some(t=>t.delay===300),false,'no microphone restart while speaking');
 for(let i=0;i<10;i++){const player=s.audio.at(-1);if(!player?.onended)break;player.onended();await s.flush()}
 await pending;assert.ok(s.requests.at(-1).data.text.includes('FIM.'));assert.ok(s.requests.length>1);assert.equal(s.requests.some(r=>/openai|realtime/.test(r.url)),false);
 const cancel=harness();cancel.c.answer=long;const stopped=cancel.run('speak(answer)');await cancel.flush();cancel.run('stopSpeaking()');await stopped;assert.equal(cancel.requests.length,1);
 const denied=harness();denied.run('toggleVoice()');denied.c.rec.onerror({error:'not-allowed'});assert.equal(denied.c.voiceMode,false);assert.match(denied.c.status.textContent,/Autorize/);
 // A late microphone permission response after stopping must release the stream.
 const stale=harness();let release;stale.c.navigator.mediaDevices={getUserMedia:()=>new Promise(r=>release=r)};stale.c.window.MediaRecorder=class{};
 stale.run('voiceMode=true;voiceUseRecorder=true');const capture=stale.run('captureVoice()');stale.run('voiceMode=false;endRealtime()');let stoppedTrack=false;release({getTracks:()=>[{stop(){stoppedTrack=true}}]});await capture;assert.equal(stoppedTrack,true);
 h.events.pagehide();assert.equal(h.c.voiceMode,false);
 console.log('PASS full speech, no paid calls, playback gating, stop cancellation, permission denial, stale microphone cleanup, page exit');
})().catch(e=>{console.error(e);process.exitCode=1});
