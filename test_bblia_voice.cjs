const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/bblia_voice.js','utf8');
function harness(){
 let now=0,sequence=0;const timers=new Map(),pcs=[],tracks=[],events=[];
 const context={console,voiceMode:true,muted:false,history:[],send:{disabled:false},status:{textContent:''},
  setVoiceUI(){},clearVoiceTimers(){},unlockVoicePlayback(){},dictation:null,recognition:null,waitingVoice:false,
  add(){},saveChat(){},handleRealtimeMedia:async()=>{},
  setTimeout(fn,delay){const id=++sequence;timers.set(id,{at:now+delay,fn});return id},clearTimeout(id){timers.delete(id)},
  navigator:{mediaDevices:{async getUserMedia(){const track={enabled:true,stopped:false,stop(){this.stopped=true}};tracks.push(track);return{getTracks:()=>[track],getAudioTracks:()=>[track]}}}},
  fetch:async()=>({ok:true,json:async()=>({token:'fake-ephemeral'}),text:async()=>'fake SDP'}),
  document:{body:{append(){}},createElement(){return{style:{},play:async()=>{},pause(){},remove(){}}},getElementById(){return{classList:{remove(){}}}}}};
 class Peer{
  constructor(){this.connectionState='new';pcs.push(this)}
  addTrack(){}createOffer(){return Promise.resolve({sdp:'offer'})}setLocalDescription(){return Promise.resolve()}setRemoteDescription(){return Promise.resolve()}
  createDataChannel(){return this.channel={readyState:'open',send(data){events.push(JSON.parse(data))},close(){this.readyState='closed'}}}
  close(){this.connectionState='closed'}
 }
 context.RTCPeerConnection=Peer;context.window={RTCPeerConnection:Peer};vm.createContext(context);vm.runInContext(source,context);
 const run=code=>vm.runInContext(code,context);
 async function advance(ms){const target=now+ms;while(true){const next=[...timers].filter(([,t])=>t.at<=target).sort((a,b)=>a[1].at-b[1].at)[0];if(!next)break;timers.delete(next[0]);now=next[1].at;next[1].fn();for(let n=0;n<15;n++)await Promise.resolve()}now=target}
 return{context,run,pcs,tracks,events,advance};
}
(async()=>{
 const h=harness();await h.run('startRealtime()');h.pcs[0].channel.onopen();
 assert.equal(h.tracks[0].enabled,true);
 h.run("handleRealtimeEvent({type:'response.created'},realtimeChannel);handleRealtimeEvent({type:'output_audio_buffer.started'},realtimeChannel)");
 assert.equal(h.tracks[0].enabled,false);
 h.run("handleRealtimeEvent({type:'input_audio_buffer.speech_started'},realtimeChannel);handleRealtimeEvent({type:'response.done',response:{output:[]}},realtimeChannel)");
 assert.equal(h.tracks[0].enabled,false,'must wait for actual speaker playback, not response.done');
 assert.equal(h.events.some(e=>e.type==='response.cancel'),false);
 h.run("handleRealtimeEvent({type:'output_audio_buffer.stopped'},realtimeChannel)");assert.equal(h.tracks[0].enabled,true);
 assert.equal(h.events.at(-1).type,'input_audio_buffer.clear');
 await h.advance(120000);assert.equal(h.context.voiceMode,true);assert.equal(h.pcs[0].connectionState,'new');
 h.pcs[0].connectionState='disconnected';h.pcs[0].onconnectionstatechange();await h.advance(2000);
 h.pcs[0].connectionState='connected';h.pcs[0].onconnectionstatechange();await h.advance(4000);assert.equal(h.pcs.length,1,'transient network loss must not end session');
 h.pcs[0].connectionState='failed';h.pcs[0].onconnectionstatechange();assert.equal(h.context.voiceMode,true);await h.advance(1000);assert.equal(h.pcs.length,2);
 h.pcs[1].channel.onopen();assert.equal(h.tracks[1].enabled,true);
 h.run('toggleVoice()');await h.advance(60*60*1000);assert.equal(h.context.voiceMode,false);assert.equal(h.pcs.length,2);assert.equal(h.tracks.every(t=>t.stopped),true);
 const stale=harness();let release;stale.context.navigator.mediaDevices.getUserMedia=()=>new Promise(r=>release=r);
 const pending=stale.run('startRealtime()');stale.run('toggleVoice()');const track={stopped:false,stop(){this.stopped=true}};release({getTracks:()=>[track]});await pending;assert.equal(track.stopped,true);assert.equal(stale.pcs.length,0);
 const renewal=harness();await renewal.run('startRealtime()');renewal.pcs[0].channel.onopen();renewal.run('realtimeOutputActive=true');await renewal.advance(50*60*1000);assert.equal(renewal.pcs.length,1);renewal.run('realtimeOutputActive=false');await renewal.advance(15000);assert.equal(renewal.pcs.length,2);
 console.log('PASS: playback noise gating, no response cancellation, continuous beyond 2 min, transient loss, automatic reconnect, explicit stop, stale permission race, idle session renewal');
})().catch(e=>{console.error(e);process.exitCode=1});
