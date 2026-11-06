const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
(async()=>{
const events=[],saved=[];let calls=0;
const checkpoint={version:1,revision:3,steps:2,artifacts:[{name:'app.js',content:'const total=42;'}],plan:['Construir','Testar'],computer_actions:[],pending_action:null};
const c={workspace:{preferences:{}},currentChat(){return{}},paintResponse(){},sendMessage(){},renderWorkProgress(){},persist:async()=>{saved.push(true)},fetch:async()=>{calls++;return calls===1?{ok:false,status:404,json:async()=>({error:'reiniciou'})}:{ok:true,json:async()=>({status:'completed',artifacts:checkpoint.artifacts,checkpoint:{...checkpoint,revision:4}})}}};
vm.createContext(c);vm.runInContext(fs.readFileSync(__dirname+'/bblia_agent.js','utf8').replace(/initAutonomousWork\(\);\s*$/,''),c);
vm.runInContext('renderWorkProgress=()=>{};requestWork=async payload=>{return{id:"recovered"}}',c);
c.pending={id:'lost',payload:{messages:[{role:'user',content:'Crie um app'}],files:[],use_computer:false},checkpoint};
const result=await vm.runInContext('pollWork({},pending)',c);
assert.equal(result.status,'completed');assert.equal(c.pending.id,'recovered');assert.equal(c.pending.payload.files[0].content,'const total=42;');assert(saved.length>0);
// Never restart unknown computer commands automatically after a server restart.
c.pending={id:'lost-pc',payload:{messages:[],files:[],use_computer:true},checkpoint};calls=0;
const pc=await vm.runInContext('pollWork({},pending)',c);
assert.equal(pc.status,'partial');assert.equal(pc.recovery_required,true);assert.equal(c.pending.id,'lost-pc');
// Discard credentials and unknown fields from checkpoint persistence.
c.point={...checkpoint,revision:8,access_token:'SECRET',computer_actions:[{tool:'read_file',confirmed:true,token:'SECRET'}]};
await vm.runInContext('saveWorkCheckpoint(pending,{checkpoint:point})',c);
assert(!JSON.stringify(c.pending.checkpoint).includes('SECRET'));
console.log('PASS checkpoint persistence, automatic source recovery, no replay of computer commands, no checkpoint credentials');
})().catch(e=>{console.error(e);process.exitCode=1});
