const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const context={workspace:{preferences:{},chats:[{id:'a',projectId:'p',updated:1,messages:[{artifacts:[{name:'index.html',content:'old'},{name:'app.js',content:'keep'}]}]},
 {id:'b',projectId:'p',updated:2,messages:[{artifacts:[{name:'index.html',content:'new'}]}]}]},
 currentChat:()=>({id:'b',workMode:true}),paintResponse(){},sendMessage(){}};
vm.createContext(context);vm.runInContext(fs.readFileSync(__dirname+'/bblia_agent.js','utf8').replace(/initAutonomousWork\(\);\s*$/,''),context);
const run=code=>vm.runInContext(code,context);
assert.equal(run("wantsAutonomousWork('Crie um painel de PDV igual a esse',[{type:'image'}])"),true);
assert.equal(run("wantsAutonomousWork('Quero fazer um sistema igual à foto',[{type:'image'}])"),true);
assert.equal(run("wantsAutonomousWork('Crie uma logomarca para meu aplicativo',[])"),false);
assert.equal(run("wantsAutonomousWork('Qual é o total do carrinho?',[])"),false);
assert.equal(run("wantsAutonomousWork('Mude o cabeçalho para azul',[])"),true);
assert.equal(run("wantsAutonomousWork('Crie um launcher Android',[])"),true);
const files=JSON.parse(run("JSON.stringify(projectArtifacts('p',{id:'b'}))"));
assert.deepEqual(files,[{name:'index.html',content:'new'},{name:'app.js',content:'keep'}]);
console.log('PASS: image-to-PDV routing, followup edits, media/chat separation, latest project files and unchanged file preservation');
