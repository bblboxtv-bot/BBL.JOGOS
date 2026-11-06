const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const context={structuredClone,crypto:{randomUUID:()=> 'restored'},openSection(){},sendMessage(){},console,document:{getElementById:()=>({close(){}})},setTimeout(){},clearTimeout(){}};
vm.createContext(context);vm.runInContext(fs.readFileSync(__dirname+'/bblia_work.js','utf8').replace(/initWorkbench\(\);\s*$/,''),context);
const run=code=>vm.runInContext(code,context);
run(`workspace={version:1,active:'chat',preferences:{},projects:[{id:'p',name:'Meu painel',files:[]}],chats:[{id:'chat',projectId:'p',title:'Original',updated:1,messages:[
 {role:'assistant',content:'Primeira entrega',artifacts:[{name:'index.html',content:'ANTIGO'}]},
 {role:'assistant',content:'Revisão',artifacts:[{name:'index.html',content:'NOVO'},{name:'app.js',content:'PRESERVAR'},{name:'App.apk',content:'Temporário',download_url:'/expired'}]}
 ]}]};busy=()=>false;saveChat=async()=>{};persist=async()=>{};renderChat=()=>{};notify=()=>{};`);
(async()=>{
 assert.equal(run("projectFileVersions('p').length"),2);
 assert.equal(run("projectFileVersions('p')[0].files.length"),2,'temporary APK links are not restored');
 const original=run('JSON.stringify(workspace.chats[0])');
 const chat=await run("restoreProjectVersion('p','chat',0)");
 assert.equal(chat.messages[1].artifacts.find(f=>f.name==='index.html').content,'ANTIGO');
 assert.equal(chat.messages[1].artifacts.find(f=>f.name==='app.js').content,'PRESERVAR');
 assert.equal(run("JSON.stringify(workspace.chats.find(c=>c.id==='chat'))"),original,'the source conversation stays unchanged');
 assert.equal(run('workspace.active'),'restored');assert.equal(run('workspace.chats.length'),2);
 console.log('PASS project version recovery, unchanged file preservation, original history preserved, temporary links excluded');
})().catch(error=>{console.error(error);process.exitCode=1});
