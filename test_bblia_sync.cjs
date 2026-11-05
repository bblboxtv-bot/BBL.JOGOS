const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const src=fs.readFileSync('bblia_work.js','utf8').replace(/initWorkbench\(\);\s*$/,'');
const ctx={openSection(){},sendMessage(){},structuredClone,crypto:{randomUUID:()=> 'new-chat'},setTimeout:()=>1,clearTimeout(){},document:{getElementById:()=>null},console};vm.createContext(ctx);vm.runInContext(src,ctx);
vm.runInContext(`cloudUser={id:'account-a',email:'a@test'};cloudReady=true;workspace={version:1,chats:[{id:'a',title:'A',messages:[]}],projects:[],preferences:{}};cloudRemember();`,ctx);
vm.runInContext(`workspace.chats[0].messages.push({role:'user',content:'hello'});cloudTrack()`,ctx);
assert.equal(vm.runInContext('cloudGeneration',ctx),1);
vm.runInContext(`workspace.chats=[];cloudTrack()`,ctx);
assert.ok(vm.runInContext("workspace.deleted['chats:a']",ctx));
vm.runInContext(`cloudUser=null;workspace.chats=[{id:'guest',title:'Private guest',messages:[]}];cloudTrack()`,ctx);
assert.equal(vm.runInContext('cloudGeneration',ctx),2);
(async()=>{
 // Persist keys cannot write an account workspace over guest history.
 vm.runInContext(`cloudTrack=()=>{};db={transaction(){const tx={objectStore:()=>({put:(v,key)=>{recordedKey=key;queueMicrotask(()=>tx.oncomplete())}})};return tx}};`,ctx);
 ctx.queueMicrotask=queueMicrotask;
 await vm.runInContext('persist()',ctx);assert.equal(ctx.recordedKey,'state');
 vm.runInContext("cloudUser={id:'account-b'}",ctx);await vm.runInContext('persist()',ctx);assert.equal(ctx.recordedKey,'account:account-b');
 // A response for a previous account can never replace current state.
 vm.runInContext(`cloudReady=true;cloudRunning=false;cloudDevice='browser123';send={disabled:false};voiceMode=false;cloudTrack=()=>{};accountRequest=async()=>({user:{id:'account-a'},workspace:{version:1,chats:[],projects:[]}});`,ctx);
 await vm.runInContext('cloudSync(false)',ctx);
 assert.equal(vm.runInContext('workspace.chats[0].id',ctx),'guest');
 assert.match(vm.runInContext('cloudError',ctx),/conta mudou/);
 console.log('PASS account storage isolation, deletion tracking, guest privacy, stale-account response rejection');
})().catch(e=>{console.error(e);process.exitCode=1});
