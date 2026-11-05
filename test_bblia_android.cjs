const vm=require('vm'),fs=require('fs'),assert=require('assert/strict');
const context={workspace:{preferences:{}},currentChat:()=>({id:'a'}),paintResponse(){},sendMessage:()=>{throw Error('wrong route')},prompt:{value:''},attachments:[],currentProject:()=>null,notify(){},computerReady:async()=>true,wantsComputerWork:text=>/compile|computador/i.test(text)};
vm.createContext(context);vm.runInContext(fs.readFileSync('bblia_agent.js','utf8').replace(/initAutonomousWork\(\);\s*$/,''),context);
let captured;context.capture=(...args)=>{captured=args};vm.runInContext('runAutonomousWork=async(...args)=>capture(...args)',context);
(async()=>{
 context.prompt.value='Compile o APK no computador';await context.sendMessage();assert.equal(captured[2].useComputer,true);
 context.prompt.value='Crie um launcher Android';await context.sendMessage();assert.equal(captured[2].useComputer,true);
 context.computerReady=async()=>false;let prompted=false;context.showComputerConnection=async()=>{prompted=true};captured=null;
 context.prompt.value='Compile o APK no computador';await context.sendMessage();assert.equal(captured,null);assert.equal(prompted,true);
 context.prompt.value='Crie um launcher Android';await context.sendMessage();assert.equal(captured[2].useComputer,false,'source creation can continue without computer');
 assert.equal(vm.runInContext("wantsAndroidBuild('Como compilar um APK?')",context),false);
 console.log('PASS text Android build routing, selected-computer use, missing-connection prompt and source-only fallback');
})().catch(e=>{console.error(e);process.exitCode=1});
