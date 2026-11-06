const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const base=process.env.BBLIA_TEST_URL||'http://127.0.0.1:10000';
function wav(seconds,signal=false){const n=16000*seconds,b=Buffer.alloc(44+n*2);b.write('RIFF');b.writeUInt32LE(b.length-8,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(16000,24);b.writeUInt32LE(32000,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(n*2,40);if(signal)for(let i=0;i<n;i++)b.writeInt16LE(Math.sin(i*2*Math.PI*220/16000)*3000,44+i*2);return b}
(async()=>{
 const fixture=path.join(os.tmpdir(),'bblia-silent-mic.wav');fs.writeFileSync(fixture,wav(60));
 const browser=await chromium.launch({headless:true,args:['--autoplay-policy=no-user-gesture-required','--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream','--use-file-for-fake-audio-capture='+fixture]});
 try{
 const context=await browser.newContext({permissions:['microphone'],viewport:{width:390,height:844}}),page=await context.newPage(),errors=[],questions=[];let transcriptBytes;
 page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{window.SpeechRecognition=class{start(){window.testRec=this;window.starts=(window.starts||0)+1}abort(){this.onend?.()}stop(){this.onend?.()}}});
 await page.route('**/api/voice',route=>route.fulfill({contentType:'audio/wav',body:wav(8,true)}));
 await page.route('**/api/transcribe',async route=>{const p=route.request().postDataJSON();transcriptBytes=Buffer.from(p.audio,'base64');assert.equal(p.mime,'audio/wav');await route.fulfill({json:{text:'Agora me escute, tenho outra pergunta.'}})});
 await page.route('**/api/chat',route=>{questions.push(route.request().postDataJSON().messages.at(-1).content);return route.fulfill({json:{answer:questions.length===1?'Esta resposta longa sera interrompida enquanto ainda estiver falando.':'Recebi sua nova pergunta.',usage:{}}})});
 await page.goto(base,{waitUntil:'domcontentloaded'});await page.waitForFunction(()=>typeof workspaceReady!=='undefined'&&workspaceReady);
 await page.locator('#mic').click();await page.evaluate(()=>window.testRec.onresult({results:[Object.assign([{transcript:'Primeira pergunta'}],{isFinal:true})]}));
 await page.waitForFunction(()=>voiceBarge&&currentAudio&&!currentAudio.paused);
 await page.waitForTimeout(250);assert.equal(questions.length,1,'silence must not interrupt or submit');
 const start=Date.now();await page.evaluate(()=>{const callback=voiceBarge.processor.onaudioprocess;for(let i=0;i<5;i++)callback({inputBuffer:{getChannelData:()=>new Float32Array(2048).fill(.1)}})});
 assert.equal(await page.evaluate(()=>voiceSpeaking),false);assert.ok(Date.now()-start<500,'playback stops immediately on detected speech');
 await page.evaluate(()=>{const callback=voiceBarge.processor.onaudioprocess;for(let i=0;i<18;i++)callback?.({inputBuffer:{getChannelData:()=>new Float32Array(2048)}})});
 await page.waitForFunction(()=>history.filter(m=>m.role==='assistant').length===2);
 assert.equal(questions[1],'Agora me escute, tenho outra pergunta.');assert.equal(transcriptBytes.toString('ascii',0,4),'RIFF');assert.ok(transcriptBytes.length>1000);
 await page.waitForFunction(()=>voiceSpeaking&&voiceBarge);
 await page.locator('#mic').click();assert.equal(await page.evaluate(()=>voiceBarge===null&&voiceCapture===null&&!voiceMode),true);
 assert.deepEqual(errors,[]);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 console.log('PASS browser: playback interrupted, onset sent as WAV, second question answered, silence ignored, stop releases microphone, mobile viewport');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
