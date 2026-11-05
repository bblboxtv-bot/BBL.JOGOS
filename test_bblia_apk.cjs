const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const src=fs.readFileSync('bblia_work.js','utf8').replace(/initWorkbench\(\);\s*$/,'');
(async()=>{
let picker,request,notices=[];
const context={crypto:{randomUUID:()=> 'id'},openSection(){},sendMessage(){},document:{createElement(){return picker={click(){}}}},status:{},AbortController,setTimeout,clearTimeout,console,
fetch:async(url,options)=>{request={url,options};return {ok:true,json:async()=>({attachment:{name:'app.apk.analise.txt',type:'text',data:'ANÁLISE DO APK br.bbl.demo',apk:{name:'app.apk',package:'br.bbl.demo'}}})}}};
vm.createContext(context);vm.runInContext(src,context);
vm.runInContext('notify=message=>status.textContent=message',context);
let selected;context.chooseFiles(files=>selected=files);assert(picker.accept.includes('.apk'));
const file={name:'app.apk',size:7000000,text(){throw Error('APK must not be decoded as UTF-8')}};
picker.files=[file];await picker.onchange();assert.equal(request.url,'/api/apk/analyze');assert.strictEqual(request.options.body,file);assert.equal(selected[0].type,'text');assert.equal(selected[0].apk.package,'br.bbl.demo');
selected=null;picker.files=[{name:'large.apk',size:101*1024*1024}];await picker.onchange();assert.equal(selected,null);assert(context.status.textContent.includes('100 MB'));
context.fetch=async()=>({ok:false,json:async()=>({error:'APK corrompido'})});picker.files=[file];await picker.onchange();assert.equal(selected,null);assert(context.status.textContent.includes('corrompido'));
console.log('PASS APK picker, binary upload, analysis attachment, size limit, error handling');
})().catch(e=>{console.error(e);process.exit(1)});
