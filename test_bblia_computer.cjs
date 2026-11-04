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
const devices=JSON.parse(run("JSON.stringify(computerDevices({content:[{type:'text',text:'Desktop Commander devices\\n\\n1. DESKTOP-TEST\\n   Status: Online\\n   ID: 9cbcf202-1832-4211-8678-c8bd1431063f\\n   Last seen: now'}]}))"));
assert.equal(devices[0].name,'DESKTOP-TEST');assert.equal(devices[0].online,true);
run("computerCache={access_token:'secret-private',device_id:'selected',expires_at:Date.now()+3600000}");
(async()=>{
 const payload={use_computer:true,messages:[{role:'user',content:'hostname'}]};context.payload=payload;
 await run('requestWork(payload)');
 assert.equal(received.computer_connection.access_token,'secret-private');
 assert.equal(payload.computer_connection,undefined,'saved payload must not gain credentials');
 assert.equal(JSON.stringify(payload).includes('secret-private'),false);
 console.log('PASS: computer intent routing, device parsing, private request credentials excluded from saved payload');
})().catch(e=>{console.error(e);process.exitCode=1});
