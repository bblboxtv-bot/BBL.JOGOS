const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(__dirname+'/bblia_voice.js','utf8').split('// The main microphone streams speech directly; dictation keeps the recorder above.')[1];
function setup(){
 const tracks=[{enabled:true,stop(){this.stopped=true}}],events=[],bubbles=[];
 const c={console,setTimeout,clearTimeout,AbortController,Intl,Date,JSON,Map,Set,Number,Object,String,
  voiceMode:true,voiceGeneration:0,realtimePC:null,realtimeConnecting:false,realtimeAudio:null,
  voiceCapture:{getAudioTracks:()=>tracks},voiceSpeaking:false,waitingVoice:false,send:{disabled:false},
  workspace:{preferences:{}},history:[],status:{textContent:''},muted:false,unlockedAudio:null,
  endRealtime(){c.voiceGeneration++;for(const t of c.voiceCapture?.getAudioTracks()||[])t.stop();c.voiceCapture=null;c.waitingVoice=false},
  stopSpeaking(){},setVoiceUI(){},toggleVoice(){},scheduleVoiceListen(){events.push('listen')},
  replyByVoice(){events.push('tts')},add(role,text){const b={role,textContent:text};bubbles.push(b);return b},
  saveChat(){},persist(){},handleRealtimeWork:async()=>events.push('work'),handleRealtimeMedia:async()=>events.push('media')};
 vm.createContext(c);vm.runInContext(source,c);return{c,tracks,events,bubbles,run:code=>vm.runInContext(code,c)};
}
(async()=>{
 const {c,tracks,events,bubbles,run}=setup();
 run("realtimeChannel={readyState:'open',send(){},close(){}};realtimePC={close(){}};");
 await run("handleRealtimeEvent({type:'conversation.item.input_audio_transcription.completed',item_id:'u1',transcript:'Olá'},realtimeChannel)");
 await run("handleRealtimeEvent({type:'conversation.item.input_audio_transcription.completed',item_id:'u1',transcript:'Olá'},realtimeChannel)");
 await run("handleRealtimeEvent({type:'response.output_audio_transcript.delta',item_id:'a1',delta:'Oi'},realtimeChannel)");
 await run("handleRealtimeEvent({type:'response.output_audio_transcript.done',item_id:'a1',transcript:'Oi!'},realtimeChannel)");
 assert.equal(c.history.length,2);assert.equal(bubbles.length,2);assert.equal(c.history[1].content,'Oi!');
 run("recordRealtimeUsage({id:'r1',usage:{input_tokens:10,output_tokens:4}});recordRealtimeUsage({id:'r1',usage:{input_tokens:10,output_tokens:4}})");
 const usage=Object.values(c.workspace.preferences.voiceUsage)[0];assert.equal(usage.responses,1);assert.equal(usage.input,10);
 c.send.disabled=true;run('syncRealtimeMicrophone()');assert.equal(tracks[0].enabled,false);
 c.send.disabled=false;run('syncRealtimeMicrophone()');assert.equal(tracks[0].enabled,true);
 await run("handleRealtimeEvent({type:'response.function_call_arguments.done',name:'fazer_trabalho'},realtimeChannel)");assert(events.includes('work'));
 await run("replyByVoice('Resultado')");assert(!events.includes('tts'));
 await run("handleRealtimeEvent({type:'input_audio_buffer.speech_started'},realtimeChannel)");assert(c.status.textContent.includes('ouvindo'));
 run('endRealtime()');assert.equal(c.realtimePC,null);assert(tracks[0].stopped);assert.equal(c.voiceCapture,null);
 console.log('PASS transcripts deduplicated, usage deduplicated, microphone pause/resume, work dispatch, no duplicate TTS, interruption state and cleanup');
})().catch(error=>{console.error(error);process.exit(1)});
