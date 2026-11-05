const assert=require('assert/strict'),fs=require('fs'),vm=require('vm');
const src=fs.readFileSync('bblia_agent.js','utf8');const context={workspace:{preferences:{}},currentChat:()=>null};vm.createContext(context);
vm.runInContext(src.slice(src.indexOf('function wantsSelfImprovement'),src.indexOf('function projectArtifacts')),context);
for(const text of ['Melhore você mesma','Corrija sua tela','Quero melhorias na BBLIA','Adicione uma função no seu próprio aplicativo']){
 assert(context.wantsSelfImprovement(text),text);assert(context.wantsAutonomousWork(text),text);
}
for(const text of ['Crie um aplicativo para minha loja','Como melhorar a BBLIA?','Faça Bolsonaro dançando','Me conte uma piada com palavrões'])assert(!context.wantsSelfImprovement(text),text);
console.log('PASS self-improvement routing, normal projects, questions and creative requests');
