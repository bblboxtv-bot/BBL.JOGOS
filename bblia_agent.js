'use strict';
let activeWork=null;
const workSleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));

function wantsSelfImprovement(text){
 const change=/(melhor|alter|corrig|corrij|consert|ajust|atualiz|adicione|adicionar|inclua|incluir|mude|mudar|tire|tirar|remov|implemen|implement|aperfeiço|aperfeico)/i.test(text);
 const self=/\bbblia\b|voc[êe]\s+(?:mesm[ao]|pr[óo]pri[ao])|(?:sua|seu)\s+(?:pr[óo]pri[ao]\s+)?(?:tela|interface|c[óo]digo|aplicativo|funcionamento|menu|voz|microfone)|em\s+voc[êe]/i.test(text);
 const question=/^(?:como\b|o que\b|qual\b|explique\b|me explique\b)/i.test(text.trim());
 return change&&self&&!question;
}
function wantsAutonomousWork(text,selected=[]){
 if(workspace.preferences.agent===false)return false;
 if(wantsSelfImprovement(text))return true;
 const verb=/(cria|crie|criar|faça|fazer|faz\b|monte|montar|constru|desenvolv|program|corrij|corrigir|altere|alterar|melhore|mudar|mude|quero|preciso)/i.test(text);
 const target=/\b(painel|pdv|dashboard|site|sistema|loja|app|apk|aplicativo|launcher|código|codigo|projeto|página|pagina|html|programa)\b/i.test(text);
 const visual=selected.some(f=>f.type==='image'||f.apk)&&/(igual|parecido|parecida|baseado|baseada|referência|referencia)/i.test(text);
 const mediaOnly=/^(?:crie|criar|faça|fazer|quero)\s+(?:(?:uma?|a|o)\s+)?(?:imagem|foto|logomarca|logo|vídeo|video|banner)\b/i.test(text);
 return verb&&!mediaOnly&&(target||visual||(currentChat()?.workMode&&/(corrij|altere|mude|adicione|remova|melhore|continue|finalize)/i.test(text)));
}
function projectArtifacts(projectId,chat){
 const files=new Map();
 workspace.chats.filter(c=>projectId?c.projectId===projectId:c.id===chat.id).sort((a,b)=>a.updated-b.updated)
  .forEach(c=>c.messages.forEach(m=>(m.artifacts||[]).forEach(f=>files.set(f.name,f.content))));
 return Array.from(files,([name,content])=>({name,content}));
}
function renderWorkProgress(bubble,data,cancel){
 bubble.replaceChildren();
 const title=document.createElement('strong');title.textContent='⚡ Fazendo por você';bubble.append(title);
 const message=document.createElement('p');message.textContent=data.progress||'Analisando o pedido e a referência';bubble.append(message);
 if(data.plan?.length){const list=document.createElement('ol');data.plan.forEach(step=>{const li=document.createElement('li');li.textContent=step;list.append(li)});bubble.append(list)}
 if(cancel)button(bubble,data.status==='cancelling'?'Interrompendo…':'Parar trabalho',cancel).disabled=data.status==='cancelling';
}
function webSyntaxErrors(files){
 const errors=[];const map=new Map(files.map(f=>[f.name,f.content]));
 const html=map.get('index.html');if(!html)return errors;
 const doc=new DOMParser().parseFromString(html,'text/html');
 for(const script of doc.querySelectorAll('script')){
  if(script.type&&script.type!=='text/javascript'&&script.type!=='application/javascript')continue;
  let text=script.textContent,name='script em index.html';
  if(script.getAttribute('src')){name=script.getAttribute('src').replace(/^\.\//,'').split('?')[0];text=map.get(name);if(text===undefined)continue}
  try{new Function(text)}catch(error){errors.push(name+': '+error.message)}
 }
 return errors;
}
function openWorkPreview(files){
 const map=new Map(files.map(f=>[f.name,f.content]));
 if(!map.has('index.html'))return notify('Este projeto deve ser baixado para abrir no ambiente adequado.');
 const errors=webSyntaxErrors(files);if(errors.length)return notify('A prévia encontrou um erro de código: '+errors[0]);
 const doc=new DOMParser().parseFromString(map.get('index.html'),'text/html');
 doc.querySelectorAll('base,meta[http-equiv],iframe,object,embed').forEach(node=>node.remove());
 for(const link of doc.querySelectorAll('link[rel=stylesheet]')){
  const name=(link.getAttribute('href')||'').replace(/^\.\//,'').split('?')[0];
  const css=map.get(name);if(css!==undefined){const style=doc.createElement('style');style.textContent=css;link.replaceWith(style)}else link.remove();
 }
 for(const script of doc.querySelectorAll('script[src]')){
  const name=(script.getAttribute('src')||'').replace(/^\.\//,'').split('?')[0];
  const js=map.get(name);if(js!==undefined){script.removeAttribute('src');script.textContent=js}else script.remove();
 }
 const policy=doc.createElement('meta');policy.httpEquiv='Content-Security-Policy';
 policy.content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'";
 doc.head.prepend(policy);
 const el=modalContent('Prévia do projeto','Prévia isolada para experimentar a interface. Baixe o projeto para usar armazenamento e conexões próprias.');
 const frame=document.createElement('iframe');frame.title='Prévia do projeto criado';frame.setAttribute('sandbox','allow-scripts');
 frame.setAttribute('referrerpolicy','no-referrer');frame.style.cssText='width:100%;height:68dvh;border:1px solid #596f9c;border-radius:12px;background:white';
 frame.srcdoc='<!doctype html>'+doc.documentElement.outerHTML;el.append(frame);
 button(el,'Baixar projeto completo (.zip)',()=>downloadZip('BBLIA-projeto.zip',files));
 document.getElementById('modal').style.width='min(1100px,calc(100vw - 20px))';
 document.getElementById('modal').addEventListener('close',()=>{frame.srcdoc='';document.getElementById('modal').style.width=''}, {once:true});
}
const workPaintResponse=paintResponse;
paintResponse=function(bubble,text,artifacts=[],sources=[]){
 workPaintResponse(bubble,text,artifacts,sources);
 if(artifacts.some(file=>file.name==='index.html'))button(bubble,'▶ Abrir prévia do painel',()=>openWorkPreview(artifacts));
};
async function requestWork(payload){
 const response=await fetch('/api/work/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
 const data=await response.json();if(!response.ok)throw Error(data.error||'Não foi possível iniciar o trabalho.');return data;
}
async function pollWork(bubble,pending){
 let failures=0;
 while(true){
  let data;
  try{
   const response=await fetch('/api/work/jobs/'+encodeURIComponent(pending.id));
   data=await response.json();
   if(!response.ok){if(response.status===404){const error=Error(data.error);error.expired=true;throw error}throw Error(data.error||'Falha ao consultar o trabalho')}
   failures=0;
  }catch(error){
   if(error.expired)throw error;
   failures++;renderWorkProgress(bubble,{progress:'Reconectando para acompanhar o trabalho. Ele pode continuar no servidor.'},null);
   if(failures>12)throw Error('A conexão continua indisponível. Reabra esta conversa para acompanhar o trabalho.');
   await workSleep(5000);continue;
  }
  if(!['processing','cancelling'].includes(data.status))return data;
  renderWorkProgress(bubble,data,async()=>{
   pending.cancelled=true;
   try{await fetch('/api/work/jobs/'+encodeURIComponent(pending.id)+'/cancel',{method:'POST'});renderWorkProgress(bubble,{progress:'Interrompendo após a etapa em andamento',status:'cancelling'},()=>{})}catch(error){notify('Não consegui enviar a interrupção. Tente novamente.')}
  });
  await workSleep(1500);
 }
}
async function finishWork(bubble,pending){
 const chat=currentChat();
 try{
  let data=await pollWork(bubble,pending);
  // Check generated JavaScript syntax without executing it in the BBLIA page.
  // Repair automatically, retaining the same request and files.
  for(let attempt=0;attempt<2&&data.status==='completed'&&!pending.cancelled;attempt++){
   const errors=webSyntaxErrors(data.artifacts||[]);if(!errors.length)break;
   renderWorkProgress(bubble,{progress:'Corrigindo automaticamente erros encontrados no JavaScript'},null);
   pending.payload={...pending.payload,files:data.artifacts,messages:[...pending.payload.messages.slice(-10),
    {role:'assistant',content:data.answer||'Arquivos criados.'},
    {role:'user',content:'Corrija estes erros de sintaxe encontrados no JavaScript, preservando a solução e suas funções. Não peça confirmação.\n'+errors.join('\n')}]};
   const next=await requestWork(pending.payload);pending.id=next.id;await persist();data=await pollWork(bubble,pending);
  }
  const artifacts=data.artifacts||[];
  const syntaxErrors=webSyntaxErrors(artifacts);
  if(syntaxErrors.length&&data.status==='completed'){data.status='partial';data.error='Ainda há erros de sintaxe a corrigir: '+syntaxErrors.join('; ')}
  let answer=data.answer||data.error||'O trabalho foi interrompido.';
  if(data.self_improvement)answer='Melhoria da BBLIA preparada para revisão; ainda não publicada.\n\n'+answer;
  if(data.status!=='completed')answer='Trabalho '+(data.status==='cancelled'?'interrompido':'parcial')+'. '+(data.error||'Os arquivos já criados foram preservados.');
  if(data.limitations?.length)answer+='\n\n'+data.limitations.join('\n');
  if(data.validation&&data.kind!=='computador')answer+='\n\nVerificação automática de estrutura: '+(data.validation.ok?'sem erros detectados.':'há ajustes pendentes.');
  if(artifacts.some(f=>f.name==='index.html'))answer+='\nSintaxe JavaScript da prévia: '+(syntaxErrors.length?syntaxErrors.join('; '):'sem erros detectados nos scripts verificáveis.');
  if(data.runtime_tests?.executed){const t=data.runtime_tests;answer+='\nTestes reais de lógica JavaScript: '+(t.ok?'aprovados ('+(t.passed||0)+' testes).':'falharam: '+(t.error||(t.tests||[]).filter(x=>!x.ok).map(x=>x.name+': '+x.error).join('; ')));answer+='\nEsses testes não verificam a interface visual, APIs externas nem compilação de APK.'}else if(data.kind!=='computador')answer+='\nExecução de código não confirmada nesta entrega. A verificação cobre estrutura e sintaxe.';
  paintResponse(bubble,answer,artifacts,data.sources||[]);
  history.push({role:'assistant',content:answer,artifacts,sources:data.sources||[]});
  delete chat.workJob;await saveChat();notify(data.status==='completed'?'Trabalho entregue':'Arquivos parciais disponíveis');
  return {status:data.status,summary:answer,files:artifacts.map(f=>f.name)};
 }catch(error){
  bubble.textContent='Não foi possível acompanhar o trabalho: '+error.message;
  if(error.expired){delete chat.workJob;await persist()}
  button(bubble,'Retomar acompanhamento',()=>{if(!send.disabled&&chat.workJob)resumeAutonomousWork()});
  notify('Trabalho não confirmado. Os arquivos anteriores continuam salvos.');
  return {status:'failed',error:error.message};
 }finally{
  activeWork=null;send.disabled=false;waitingVoice=false;
  if(typeof syncRealtimeMicrophone==='function')syncRealtimeMicrophone();
  feed.scrollTop=feed.scrollHeight;
 }
}
async function runAutonomousWork(text,selected=[],options={}){
 if(!workspaceReady||send.disabled)return{status:'failed',error:'Aguarde o trabalho atual terminar.'};
 const chat=currentChat();let project=currentProject();
 const selfImprovement=wantsSelfImprovement(text)||project?.kind==='bblia-self';
 if(selfImprovement&&project?.kind!=='bblia-self'){
  project={id:uid(),name:'Melhorias da BBLIA',kind:'bblia-self',instructions:'Melhorias no código da própria BBLIA. Ler os originais, preservar funções e entregar arquivos para revisão antes da publicação.',files:[]};
  workspace.projects.push(project);chat.projectId=project.id;
 }
 if(!project){project={id:uid(),name:text.slice(0,80),instructions:text.slice(0,6000),files:[]};workspace.projects.push(project);chat.projectId=project.id}
 chat.workMode=true;chat.files=selected.filter(f=>!(project.files||[]).includes(f));
 const files=projectArtifacts(project.id,chat);
 prompt.value='';attachments=[];renderAttachments();
 const label=selected.length?'\n[Referências: '+selected.map(f=>f.name).join(', ')+']':'';
 add('user',text+label);history.push({role:'user',content:text+label});
 const payload={messages:history.slice(-16).map(m=>({role:m.role,content:m.content.slice(0,12000)})),
  attachments:selected,files,self_improvement:selfImprovement,use_computer:!!options.useComputer,preferences:workspace.preferences,project:{name:project.name,instructions:project.instructions}};
 while(payload.messages[0]?.role==='assistant')payload.messages.shift();
 send.disabled=true;waitingVoice=true;
 if(typeof syncRealtimeMicrophone==='function')syncRealtimeMicrophone();
 const bubble=add('assistant','⚡ Analisando o pedido e os anexos...');
 await saveChat();
 try{
  const started=await requestWork(payload);
  const pending={id:started.id,payload,cancelled:false};chat.workJob=pending;activeWork=pending;await persist();
  return await finishWork(bubble,pending);
 }catch(error){
  bubble.textContent='Não foi possível iniciar o trabalho: '+error.message;
  send.disabled=false;waitingVoice=false;if(typeof syncRealtimeMicrophone==='function')syncRealtimeMicrophone();
  prompt.value=text;return{status:'failed',error:error.message};
 }
}
async function resumeAutonomousWork(){
 if(!workspaceReady||send.disabled||!currentChat()?.workJob)return;
 send.disabled=true;waitingVoice=true;activeWork=currentChat().workJob;
 const bubble=add('assistant','Retomando o trabalho em andamento...');
 await finishWork(bubble,activeWork);
}
const agentSendMessage=sendMessage;
sendMessage=async function(){
 const text=prompt.value.trim();const project=currentProject();
 const selected=[...(project?.files||[]),...(attachments.length?attachments:(currentChat()?.files||[]))];
 if(text&&wantsAutonomousWork(text,selected)){
  if(selected.length>4)return notify('Use até quatro referências por trabalho.');
  return runAutonomousWork(text,selected);
 }
 return agentSendMessage();
};
async function handleRealtimeWork(call,channel){
 if(realtimeMediaCalls.has(call.call_id))return;realtimeMediaCalls.add(call.call_id);
 let result;
 try{
  const args=JSON.parse(call.arguments||'{}');
  const project=currentProject();const selected=[...(project?.files||[]),...(attachments.length?attachments:(currentChat()?.files||[]))];
  if(typeof args.pedido!=='string'||args.pedido.length<5)throw Error('Descreva o trabalho que deseja criar.');
  if(selected.length>4)throw Error('Use até quatro referências por trabalho.');
  const useComputer=typeof wantsComputerWork==='function'&&wantsComputerWork(args.pedido);
  if(useComputer&&!await computerReady())throw Error('Conecte o Commander no menu Computador e TV Box da BBLIA.');
  result=await runAutonomousWork(args.pedido,selected,{useComputer});
 }catch(error){result={status:'failed',error:error.message}}
 if(channel.readyState==='open'){
  sendRealtimeEvent(channel,{type:'conversation.item.create',item:{type:'function_call_output',call_id:call.call_id,output:JSON.stringify(result)}});
  sendRealtimeEvent(channel,{type:'response.create'});
 }
}
async function initAutonomousWork(){
 while(!workspaceReady)await workSleep(100);
 const nav=document.querySelector('.panel');const entry=document.createElement('button');entry.className='navbtn';entry.textContent='⚡ Fazer por mim';
 entry.onclick=()=>{
  const el=modalContent('Fazer por mim','Anexe uma foto ou arquivo e diga o que quer pronto. A BBLIA decide detalhes comuns, pesquisa quando necessário, cria os arquivos e verifica a estrutura e a sintaxe da prévia.');
  const p=document.createElement('p');p.textContent='Exemplo: “Crie um painel de PDV igual à referência, com produtos, carrinho e fechamento de venda.”';el.append(p);
  button(el,'Começar na conversa',()=>{document.getElementById('modal').close();prompt.focus()});
 };
 nav.insertBefore(entry,nav.querySelector('.navbtn'));
 await resumeAutonomousWork();
}
initAutonomousWork();


