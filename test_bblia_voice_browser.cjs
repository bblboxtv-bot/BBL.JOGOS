const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--autoplay-policy=no-user-gesture-required']});
 try{
 const page=await browser.newPage({viewport:{width:390,height:844}});let paid=0,requests=[];
 page.on('request',r=>{if(/realtime|api.openai/.test(r.url()))paid++});
 const wav=Buffer.alloc(44+16000);wav.write('RIFF',0);wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(8000,24);wav.writeUInt32LE(16000,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(16000,40);
 await page.route('**/api/voice',route=>{requests.push(route.request().postDataJSON().text);return route.fulfill({status:200,contentType:'audio/wav',body:wav})});
 await page.addInitScript(()=>{
  class Recognition{start(){window.testRecognition=this;window.recognitionStarts=(window.recognitionStarts||0)+1}abort(){this.onend?.()}stop(){this.onend?.()}}
  window.SpeechRecognition=Recognition;
 });
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8765');await page.waitForFunction(()=>typeof workspaceReady!=='undefined'&&workspaceReady);
 await page.locator('#mic').click();await page.waitForFunction(()=>window.recognitionStarts===1);
 await page.route('**/api/chat',route=>route.fulfill({json:{answer:('Esta resposta longa será falada por completo. ').repeat(25)+'FIM DA RESPOSTA.',usage:{}}}));
 await page.evaluate(()=>{const rec=window.testRecognition;rec.onresult({results:[Object.assign([{transcript:'Olá BBLIA'}],{isFinal:true})]});rec.onend()});
 await page.waitForFunction(()=>voiceSpeaking===true);
 const starts=await page.evaluate(()=>window.recognitionStarts);await page.waitForTimeout(600);
 assert.equal(await page.evaluate(()=>window.recognitionStarts),starts,'microphone stays stopped during playback');
 await page.waitForFunction(()=>window.recognitionStarts===2,{},{timeout:20000});
 assert.ok(requests.length>=2);assert.ok(requests.at(-1).includes('FIM DA RESPOSTA.'));assert.ok(requests[0].length>350);
 assert.equal(paid,0);assert.deepEqual(errors,[]);
 await page.locator('#mic').click();assert.equal(await page.evaluate(()=>voiceMode),false);
 // Cancellation must settle playback and prevent the rest of a long answer.
 requests=[];await page.evaluate(()=>{window.pendingSpeech=speak('Uma fala que será interrompida. '.repeat(40))});await page.waitForTimeout(100);await page.evaluate(()=>stopSpeaking());await page.evaluate(()=>window.pendingSpeech);assert.equal(requests.length,1);
 // Starting the conversation explicitly enables audible replies even if saved muted.
 await page.evaluate(()=>{muted=true});await page.locator('#mic').click();assert.equal(await page.evaluate(()=>muted),false);await page.locator('#mic').click();
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 console.log('PASS browser: full reply, microphone gated during playback, automatic next turn, zero paid voice calls, cancellation, muted recovery, phone viewport');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
