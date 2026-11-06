const vm=require('node:vm'),assert=require('node:assert/strict'),fs=require('node:fs');
let received;
const context={requestWork:async payload=>{received=payload;return{id:'job'}},Date,URLSearchParams,URL,TextEncoder,
 console,notify(){},db:null};
vm.createContext(context);vm.runInContext(fs.readFileSync(__dirname+'/bblia_computer.js','utf8').replace(/initComputerConnection\(\);\s*$/,''),context);
const run=source=>vm.runInContext(source,context);
assert.equal(run("wantsComputerWork('Instale o APK na minha TV Box pelo USB')"),true);
assert.equal(run("wantsComputerWork('Confira meu computador')"),true);
assert.equal(run("wantsComputerWork('Como instalar um APK?')"),false);
assert.equal(run("wantsComputerWork('Crie um painel de PDV')"),false);
for(const text of ['Liste as pastas da minha pasta Documentos','Li as pasta nas pasta do meu documento','Leia os arquivos dos meus documentos','Mostre as pastas','Abra minha pasta Downloads']){
 context.fileIntent=text;assert.equal(run('wantsComputerWork(fileIntent)'),true,text);
}
for(const text of ['Como listar pastas?','Leia o arquivo anexado','Crie um documento Word']){
 context.fileIntent=text;assert.equal(run('wantsComputerWork(fileIntent)'),false,text);
}
const devices=JSON.parse(run("JSON.stringify(computerDevices({content:[{type:'text',text:'Desktop Commander devices\\n\\n1. DESKTOP-TEST\\n   Status: Online\\n   ID: 9cbcf202-1832-4211-8678-c8bd1431063f\\n   Last seen: now'}]}))"));
assert.equal(devices[0].name,'DESKTOP-TEST');assert.equal(devices[0].online,true);
run("computerCache={access_token:'secret-private',device_id:'selected',expires_at:Date.now()+3600000}");
(async()=>{
 const payload={use_computer:true,messages:[{role:'user',content:'hostname'}]};context.payload=payload;
 await run('requestWork(payload)');
 assert.equal(received.computer_connection.access_token,'secret-private');
 assert.equal(payload.computer_connection,undefined,'saved payload must not gain credentials');
 assert.equal(JSON.stringify(payload).includes('secret-private'),false);
 for(const text of ['Conecte ao meu computador','Conecta no meu PC','BBLIA, entre no meu computador por favor','Acesse meu computador','Reconecte ao Commander']){
  context.intent=text;assert.equal(run('computerConnectIntent(intent)'),true,text);
 }
 for(const text of ['Como conectar ao meu computador?','Conecte ao meu computador e apague a pasta','Leia os arquivos do computador','Conecte a TV Box']){
  context.intent=text;assert.equal(run('computerConnectIntent(intent)'),false,text);
 }
 context.history=[];context.add=()=>{};context.saveChat=async()=>{};let paired=0;
 context.pair=()=>{paired++};
 run("connectCommander=async()=>pair();saveComputer=async value=>{computerCache=value};computerPost=async()=>({result:{devices:[{id:'selected',name:'MEU-PC',online:true}]}})");
 await run('connectRequestedComputer()');await run('connectRequestedComputer()');
 assert.equal(paired,0,'saved connection is reused on repeated commands');
 assert.ok(context.history.at(-1).content.includes('MEU-PC'));
 assert.equal(JSON.stringify(context.history).includes('secret-private'),false,'tokens never enter the conversation');
 run('computerCache=null');await run('connectRequestedComputer()');assert.equal(paired,1,'first use opens the account authorization');
 context.show=()=>{context.shown=true};
 run("showComputerConnection=async()=>show();computerCache={access_token:'saved',device_id:'selected',expires_at:Date.now()+3600000};computerPost=async()=>({result:{devices:[{id:'selected',name:'MEU-PC',online:false},{id:'other',name:'OUTRO-PC',online:true}]}})");
 assert.equal(await run('connectRequestedComputer()'),false);assert.equal(run('computerCache.device_id'),'selected','offline selected computer never silently switches to another');
 assert.equal(await run('computerReady()'),false,'a saved token is insufficient when the selected computer is offline');
 assert.ok(run('computerConnectionIssue').includes('offline'));
 run("computerDeviceCheck=null;computerPost=async()=>({result:{devices:[{id:'selected',name:'MEU-PC',online:true}]}})");
 assert.equal(await run('computerReady()'),true,'online selected device passes readiness');
 console.log('PASS: computer intent routing, device parsing, private request credentials excluded from saved payload');
})().catch(e=>{console.error(e);process.exitCode=1});
