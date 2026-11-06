const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
function harness(){
 const timers=new Map(),requests=[],audio=[],events={};let sequence=0;
 const c={console,voiceMode:false,muted:false,voiceToken:0,voiceIndex:0,currentAudio:null,unlockedAudio:null,voiceOptions:[{api:'nova'}],waitingVoice:false,recognition:null,dictation:null,voiceRestartTimer:null,voiceListenTimer:null,
  send:{disabled:false},prompt:{value:''},status:{textContent:''},history:[],feed:{lastElementChild:null},setVoiceUI(){},updateMute(){},selectedVoiceRate:()=>1,selectedVoice:()=>null,
  stopSpeaking(){},speak(){},replyByVoice(){},listenVoice(){},scheduleVoiceListen(){},dictateMessage(){},unlockVoicePlayback(){},clearVoiceTimers(){timers.clear()},localStorage:{setItem(){}},
  AbortController,Blob,Float32Array,URL:{createObjectURL:blob=>{c.lastAudioBlob=blob;return 'blob:test'},revokeObjectURL(){}},
  setTimeout(fn,delay){const n=++sequence;timers.set(n,{fn,delay});return n},clearTimeout(n){timers.delete(n)},setInterval(){},clearInterval(){},
  navigator:{},document:{getElementById:()=>({checked:true,classList:{remove(){}}})},
  fetch:async(url,options)=>{requests.push({url,data:JSON.parse(options.body)});return{ok:true,blob:async()=>new Blob(['audio'])}},
  Audio:class{constructor(){audio.push(this)}setAttribute(){}play(){return Promise.resolve()}pause(){this.paused=true}},
  sendMessage:async()=>{c.received=c.prompt.value},
 };
 class Recognition{start(){c.rec=this;c.starts=(c.starts||0)+1}abort(){this.onend?.()}}
 c.window={SpeechRecognition:Recognition,addEventListener:(name,fn)=>{events[name]=fn}};
 vm.createContext(c);vm.runInContext(fs.readFileSync(__dirname+'/bblia_voice.js','utf8'),c);
 const run=code=>vm.runInContext(code,c),flush=async()=>{for(let i=0;i<30;i++)await Promise.resolve()};
 return {c,run,flush,timers,requests,audio,events};
}
(async()=>{
 const stalled=harness();stalled.run('toggleVoice()');
 const firstWatch=[...stalled.timers.values()].find(t=>t.delay===10000);assert.ok(firstWatch,'recognition has a startup watchdog');
 stalled.c.rec.onspeechstart();assert.ok([...stalled.timers.values()].some(t=>t.delay===35000),'long speech is allowed');
 assert.equal([...stalled.timers.values()].some(t=>t.delay===10000),false,'startup deadline must not cut a spoken sentence');
 stalled.c.rec.onspeechend();assert.ok([...stalled.timers.values()].some(t=>t.delay===5000),'missing final result recovers');
 [...stalled.timers.values()].find(t=>t.delay===5000).fn();await stalled.flush();
 assert.equal(stalled.run('voiceUseRecorder'),true,'stalled browser recognition switches to recording');
 const paid=harness();paid.c.aiRequestOptions=()=>({provider:'openai',paid_authorized:true});
 const voice=paid.run('speak("Teste")');await paid.flush();assert.equal(paid.requests[0].data.provider,'openai');assert.equal(paid.requests[0].data.paid_authorized,true);paid.run('stopSpeaking()');await voice;
 const h=harness();h.run('muted=true;toggleVoice()');assert.equal(h.c.muted,false);assert.equal(h.c.starts,1);assert.equal(h.requests.length,0,'starting voice does not call OpenAI realtime');
 h.c.rec.onresult({results:[[{transcript:'Bom dia'}]]});await h.flush();assert.equal(h.c.received,'Bom dia','a final transcript must answer even when the browser never emits onend');h.c.rec.onend();await h.flush();
 h.run('toggleVoice()');assert.equal(h.c.voiceMode,false);
 const s=harness();const long='Uma resposta longa para ouvir por completo. '.repeat(30)+'FIM.';
 s.c.answer=long;const pending=s.run('speak(answer)');await s.flush();assert.equal(s.requests.length,2,'next chunk must load before current playback ends');
 s.run('voiceMode=true;scheduleVoiceListen()');assert.equal([...s.timers.values()].some(t=>t.delay===300),false,'no microphone restart while speaking');
 for(let i=0;i<10;i++){const player=s.audio.at(-1);if(!player?.onended)break;player.onended();await s.flush()}
 await pending;assert.ok(s.requests.at(-1).data.text.includes('FIM.'));assert.ok(s.requests.length>1);assert.equal(s.requests.some(r=>/openai|realtime/.test(r.url)),false);
 const cancel=harness();cancel.c.answer=long;const stopped=cancel.run('speak(answer)');await cancel.flush();cancel.run('stopSpeaking()');await stopped;assert.equal(cancel.requests.length,2,'cancellation prevents additional loads beyond the prefetched chunk');
 // Simulate speech separated by 800ms of silence: retain all speech, reduce only silence.
 const trim=harness();const samples=new Float32Array(2000);samples.fill(.1,200,600);samples.fill(.1,1400,1800);
 trim.c.fixture={numberOfChannels:1,sampleRate:1000,length:samples.length,getChannelData:()=>samples};
 const ranges=trim.run('speechRanges(fixture)');
 assert.equal(ranges.reduce((n,[a,b])=>n+b-a,0),1050);
 assert.equal(ranges.reduce((n,[a,b])=>n+samples.slice(a,b).filter(x=>x!==0).length,0),800,'no voiced samples are removed');
 const natural=new Float32Array(1200);natural.fill(.1,100,500);natural.fill(.1,700,1100);
 trim.c.fixture={numberOfChannels:1,sampleRate:1000,length:natural.length,getChannelData:()=>natural};
 assert.equal(trim.run('speechRanges(fixture).length'),1,'normal 200ms punctuation pauses remain intact');
 // Exercise decoded segment assembly and actual AudioBufferSource playback path.
 const joined=harness();const started=[];joined.c.atob=encoded=>Buffer.from(encoded,'base64').toString('binary');
 joined.c.window.AudioContext=class{
  constructor(){this.state='running';this.sampleRate=1000;this.destination={}}
  resume(){return Promise.resolve()}close(){return Promise.resolve()}
  async decodeAudioData(){const samples=new Float32Array(800);samples.fill(.1,200,600);return {numberOfChannels:1,sampleRate:1000,length:800,getChannelData:()=>samples}}
  createBuffer(channels,length,rate){const samples=Array.from({length:channels},()=>new Float32Array(length));return {numberOfChannels:channels,sampleRate:rate,length,getChannelData:i=>samples[i]}}
  createBufferSource(){const source={playbackRate:{},connect(){},disconnect(){},start(){started.push(source)},stop(){source.stopped=true}};return source}
 };
 joined.c.fetch=async(url,options)=>{joined.requests.push({url,data:JSON.parse(options.body),signal:options.signal});return {ok:true,headers:{get:()=> 'application/json'},json:async()=>({segments:['AQ==','Ag=='],mime:'audio/mpeg'})}};
 joined.c.answer=long;const gapless=joined.run('speak(answer)');await joined.flush();
 assert.equal(joined.audio.length,1);const wav=Buffer.from(await joined.c.lastAudioBlob.arrayBuffer());assert.equal(wav.toString('ascii',0,4),'RIFF');assert.equal(wav.readUInt32LE(40)/2,940,'both decoded segments are joined with short codec padding');assert.equal(joined.audio[0].preservesPitch,true,'faster playback keeps the natural timbre');
 assert.equal(joined.requests.length,2,'next response is prepared while current buffer plays');
 joined.audio[0].onended({type:'ended'});await joined.flush();assert.equal(joined.audio.length,2,'normal ended event advances without replaying the previous sentence');
 joined.run('stopSpeaking()');await gapless;assert.equal(joined.audio[1].paused,true);
 // Full interruption: retain onset, stop playback and prefetch, send WAV, then answer.
 const barge=harness();let processor,disconnected=0,trackStopped=0;
 const stream={getAudioTracks:()=>[{readyState:'live'}],getTracks:()=>[{stop(){trackStopped++}}]};
 barge.c.navigator.mediaDevices={getUserMedia:async()=>stream};
 barge.c.window.AudioContext=class{
  constructor(){this.state='running';this.sampleRate=48000;this.destination={}}
  resume(){return Promise.resolve()}close(){return Promise.resolve()}
  createMediaStreamSource(){return{connect(){},disconnect(){disconnected++}}}
  createGain(){return{gain:{value:1},connect(){},disconnect(){disconnected++}}}
  createScriptProcessor(){processor={connect(){},disconnect(){disconnected++}};return processor}
 };
 barge.c.FileReader=class{readAsDataURL(blob){barge.c.capturedBlob=blob;this.result='data:audio/wav;base64,UklGRg==';this.onload()}};
 barge.c.fetch=async(url,options)=>{barge.requests.push({url,data:JSON.parse(options.body),signal:options.signal});if(url==='/api/voice'&&barge.requests.filter(r=>r.url===url).length===2)return new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('aborted'))));return url.includes('transcribe')?{ok:true,json:async()=>({text:'Espere, quero perguntar outra coisa.'})}:{ok:true,blob:async()=>new Blob(['audio'])}};
 barge.c.answer=long;barge.run('voiceMode=true');const interrupted=barge.run('speak(answer)');await barge.flush();
 const frame=value=>processor.onaudioprocess?.({inputBuffer:{getChannelData:()=>new Float32Array(2048).fill(value)}});
 for(let i=0;i<5;i++)frame(0);frame(.2);frame(0);
 assert.equal(barge.run('voiceSpeaking'),true,'a single impact must not interrupt');
 for(let i=0;i<4;i++){frame(.009);frame(0)}
 assert.equal(barge.run('voiceSpeaking'),false,'sustained speech immediately stops the answer');
 assert.ok(barge.requests.filter(r=>r.url==='/api/voice').at(-1).signal.aborted,'all prefetched speech is cancelled');
 assert.equal(barge.run('voiceBarge.triggered'),true);barge.run('scheduleVoiceListen()');
 assert.equal([...barge.timers.values()].some(t=>t.delay===300),false,'normal listener cannot compete with interruption capture');
 for(let i=0;i<18;i++)frame(0);await barge.flush();await interrupted;
 assert.equal(barge.c.received,'Espere, quero perguntar outra coisa.');
 assert.equal(barge.requests.filter(r=>r.url==='/api/transcribe').length,1);
 const wave=Buffer.from(await barge.c.capturedBlob.arrayBuffer());assert.equal(wave.toString('ascii',0,4),'RIFF');assert.equal(wave.readUInt32LE(24),16000);
 assert.ok(wave.subarray(44).some(v=>v!==0),'first syllables are preserved in the WAV');assert.ok(disconnected>=3);
 barge.events.pagehide();assert.equal(trackStopped,1);
 const denied=harness();denied.run('toggleVoice()');denied.c.rec.onerror({error:'not-allowed'});assert.equal(denied.c.voiceMode,false);assert.match(denied.c.status.textContent,/Autorize/);
 // A late microphone permission response after stopping must release the stream.
 const stale=harness();let release;stale.c.navigator.mediaDevices={getUserMedia:()=>new Promise(r=>release=r)};stale.c.window.MediaRecorder=class{};
 stale.run('voiceMode=true;voiceUseRecorder=true');const capture=stale.run('captureVoice()');stale.run('voiceMode=false;endRealtime()');let stoppedTrack=false;release({getTracks:()=>[{stop(){stoppedTrack=true}}]});await capture;assert.equal(stoppedTrack,true);
 const quiet=harness();
 const detector=quiet.run('createVoiceTurnDetector()');
 let turn;for(let t=100;t<=600;t+=100)turn=detector.sample(t%200===0?0.009:0.001,t);
 assert.equal(turn.heard,true,'quiet syllables separated by short pauses count as speech');
 for(let t=700;t<=2100;t+=100)turn=detector.sample(0.001,t);
 assert.equal(turn.finished,true,'pause sends the phrase without a second tap');
 const silence=quiet.run('createVoiceTurnDetector()');for(let t=100;t<3000;t+=100)assert.equal(silence.sample(0.001,t).heard,false);
 const click=quiet.run('createVoiceTurnDetector()');click.sample(0.1,100);assert.equal(click.sample(0,1700).heard,false,'one impact is not speech');
 const android=harness();android.c.window.BBLAndroid={dictate(){}};
 let requested=false;android.c.navigator.mediaDevices={getUserMedia:()=>{requested=true;return new Promise(()=>{})}};android.c.window.MediaRecorder=class{};
 let contextCreated=false,resumed=false;android.c.window.AudioContext=class{constructor(){contextCreated=true;this.state='suspended'}resume(){resumed=true;this.state='running';return Promise.resolve()}close(){return Promise.resolve()}};
 android.run('toggleVoice()');assert.equal(android.c.starts,undefined,'WebView speech interface must not be used even if exposed');assert.equal(contextCreated,true);assert.equal(resumed,true);assert.equal(requested,true);
 h.events.pagehide();assert.equal(h.c.voiceMode,false);
 console.log('PASS full speech, no paid calls, playback gating, stop cancellation, permission denial, stale microphone cleanup, page exit');
})().catch(e=>{console.error(e);process.exitCode=1});

