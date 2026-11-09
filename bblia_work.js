'use strict';
// Local workspaces never share projects with other visitors to this public URL.
// Owner selected OpenAI exclusively, including workspaces with saved Gemini preferences.
function aiRequestOptions(){return {provider:'openai',paid_authorized:true}}
let workspace={version:1,projects:[],chats:[],active:null,preferences:{name:'',instructions:'',detail:'Detalhada',web:true,auto:true}};
let db=null,attachments=[],workspaceReady=false;
const uid=()=>crypto.randomUUID();
const currentChat=()=>workspace.chats.find(c=>c.id===workspace.active);
const currentProject=()=>workspace.projects.find(p=>p.id===currentChat()?.projectId);
function notify(message){status.textContent=message}
function downloadText(name,text,type='text/plain;charset=utf-8'){
 const url=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);
}
function downloadArtifact(file){
 if(file.download_url){if(!file.download_url.startsWith('/api/apk/download/')||file.download_url.includes('..'))return notify('Link de APK inválido.');const a=document.createElement('a');a.href=file.download_url;a.download=file.name;a.click();return}
 if(!file.data_base64)return downloadText(file.name,file.content);
 try{const bytes=Uint8Array.from(atob(file.data_base64),c=>c.charCodeAt(0));const url=URL.createObjectURL(new Blob([bytes],{type:file.mime||'application/octet-stream'}));const a=document.createElement('a');a.href=url;a.download=file.name;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000)}catch(e){notify('Não foi possível baixar o documento. Tente gerar novamente.')}
}
function downloadZip(name,files){
 const encoder=new TextEncoder();let offset=0;const local=[],central=[];
 const crc32=bytes=>{let crc=0xffffffff;for(const b of bytes){crc^=b;for(let i=0;i<8;i++)crc=(crc>>>1)^((crc&1)?0xedb88320:0)}return (crc^0xffffffff)>>>0};
 for(const file of files){const filename=encoder.encode(file.name);const bytes=file.data_base64?Uint8Array.from(atob(file.data_base64),c=>c.charCodeAt(0)):encoder.encode(file.content);const crc=crc32(bytes);const header=new Uint8Array(30+filename.length);const h=new DataView(header.buffer);h.setUint32(0,0x04034b50,true);h.setUint16(4,20,true);h.setUint16(6,0x800,true);h.setUint32(14,crc,true);h.setUint32(18,bytes.length,true);h.setUint32(22,bytes.length,true);h.setUint16(26,filename.length,true);header.set(filename,30);local.push(header,bytes);
 const directory=new Uint8Array(46+filename.length);const d=new DataView(directory.buffer);d.setUint32(0,0x02014b50,true);d.setUint16(4,20,true);d.setUint16(6,20,true);d.setUint16(8,0x800,true);d.setUint32(16,crc,true);d.setUint32(20,bytes.length,true);d.setUint32(24,bytes.length,true);d.setUint16(28,filename.length,true);d.setUint32(42,offset,true);directory.set(filename,46);central.push(directory);offset+=header.length+bytes.length;
 }
 const end=new Uint8Array(22);const e=new DataView(end.buffer);e.setUint32(0,0x06054b50,true);e.setUint16(8,files.length,true);e.setUint16(10,files.length,true);e.setUint32(12,central.reduce((n,b)=>n+b.length,0),true);e.setUint32(16,offset,true);const url=URL.createObjectURL(new Blob([...local,...central,end],{type:'application/zip'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);
}
async function persist(){
 if(typeof cloudTrack==='function')cloudTrack();
 if(!db)return;
 await new Promise((resolve,reject)=>{const tx=db.transaction('work','readwrite');tx.objectStore('work').put(structuredClone(workspace),cloudUser?'account:'+cloudUser.id:'state');tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error)}).catch(()=>notify('Não foi possível salvar no aparelho. Exporte um backup antes de sair.'));
}
function modalContent(title,description){closeDrawer();const modal=document.getElementById('modal');const el=document.getElementById('modalContent');el.replaceChildren();const h=document.createElement('h2');h.textContent=title;el.append(h);if(description){const p=document.createElement('p');p.className='muted';p.textContent=description;el.append(p)}if(!modal.open)modal.showModal();return el}
function button(parent,label,fn){const b=document.createElement('button');b.className='choice';b.textContent=label;b.onclick=fn;parent.append(b);return b}
function field(parent,label,value,multiline=false){const l=document.createElement('label');l.textContent=label;l.className='work-field';const input=document.createElement(multiline?'textarea':'input');input.value=value||'';input.rows=multiline?5:undefined;l.append(input);parent.append(l);return input}
function busy(){if(send.disabled||voiceMode){notify('Finalize a resposta ou encerre a voz antes de trocar de conversa.');return true}return false}
function saveChat(){const c=currentChat();if(!c)return;c.messages=history.slice();c.updated=Date.now();if(c.title==='Nova conversa'&&history.length)c.title=history.find(m=>m.role==='user')?.content.slice(0,70)||c.title;return persist()}
function paintResponse(bubble,text,artifacts=[],sources=[]){
 bubble.replaceChildren();const chunks=String(text||'').split(/```([^\n]*)\n([\s\S]*?)```/g);
 chunks.forEach((chunk,i)=>{if(i%3===0){const p=document.createElement('div');p.textContent=chunk;bubble.append(p)}else if(i%3===1){const code=chunks[i+1];const box=document.createElement('section');const pre=document.createElement('pre');const node=document.createElement('code');node.textContent=code;pre.append(node);box.append(pre);button(box,'Copiar código',()=>navigator.clipboard.writeText(code).then(()=>notify('Código copiado')).catch(()=>notify('Selecione o código para copiar')));button(box,'Baixar código',()=>downloadText('codigo.'+({javascript:'js',typescript:'ts',python:'py',kotlin:'kt',java:'java',html:'html',css:'css',json:'json',xml:'xml',bash:'sh'}[chunk.trim().toLowerCase()]||'txt'),code));bubble.append(box)}});
 const sourceFiles=artifacts.filter(file=>!file.download_url);if(sourceFiles.length>1)button(bubble,'⬇ Baixar arquivos do projeto (.zip)',()=>downloadZip('BBLIA-arquivos.zip',sourceFiles));
 artifacts.forEach(file=>button(bubble,'⬇ '+file.name,()=>downloadArtifact(file)));
 if(sources.length){const list=document.createElement('div');list.className='sources';sources.forEach(source=>{try{const url=new URL(source.url);if(!['http:','https:'].includes(url.protocol))return;const a=document.createElement('a');a.href=url.href;a.textContent=source.title||url.hostname;a.target='_blank';a.rel='noopener noreferrer';list.append(a)}catch(e){}});bubble.append(list)}
 button(bubble,'Copiar resposta',()=>navigator.clipboard.writeText(text).then(()=>notify('Resposta copiada')).catch(()=>notify('Selecione a resposta para copiar')));
}
function renderChat(){
 history=currentChat()?.messages?.slice()||[];feed.replaceChildren();document.body.classList.add('work-mode');document.getElementById('workTitle').textContent=(currentProject()?.name||'BBLIA')+' · '+(currentChat()?.title||'Nova conversa');
 for(const [index,m] of history.entries()){const bubble=add(m.role,m.content);if(m.role==='user')button(bubble,'Editar em nova conversa',()=>branchConversation(index));if(m.role==='assistant'){if(m.media)renderMedia(bubble,m.media,m.content);else {paintResponse(bubble,m.content,m.artifacts||[],m.sources||[]);button(bubble,'Guardar na memória',()=>rememberNote(m.content));button(bubble,'Continuar em nova conversa',()=>branchConversation(index+1))}}}
 if(!history.length)add('assistant','Vamos trabalhar. Conte o que deseja criar ou anexe seus arquivos.');attachments=[];renderAttachments();
}
newChat=function(projectId=null){if(busy())return;saveChat();const c={id:uid(),projectId,title:'Nova conversa',messages:[],created:Date.now(),updated:Date.now()};workspace.chats.unshift(c);workspace.active=c.id;persist();renderChat();document.getElementById('modal').close()};
function switchChat(id){if(busy())return;saveChat();workspace.active=id;persist();renderChat();document.getElementById('modal').close()}
function showHistory(){const el=modalContent('Conversas salvas',cloudUser?'Conversas desta conta. A sincronização precisa estar concluída para aparecerem em outro aparelho.':'Salvas neste navegador. Entre na sua conta para sincronizar entre aparelhos.');const search=field(el,'Buscar conversa','');const list=document.createElement('div');el.append(list);const draw=()=>{list.replaceChildren();workspace.chats.filter(c=>(c.title+' '+c.messages.map(m=>m.content).join(' ')+' '+(workspace.projects.find(p=>p.id===c.projectId)?.name||'')).toLowerCase().includes(search.value.toLowerCase())).sort((a,b)=>b.updated-a.updated).forEach(c=>button(list,(c.id===workspace.active?'✓ ':'')+c.title,()=>switchChat(c.id)))};search.oninput=draw;draw();button(el,'Nova conversa',()=>newChat());button(el,'Baixar conversa atual (.md)',()=>downloadText('BBLIA-conversa.md',history.map(m=>'## '+(m.role==='user'?'Você':'BBLIA')+'\n\n'+m.content).join('\n\n')))}
function editProject(project=null){const el=modalContent(project?'Editar projeto':'Novo projeto','Reúna conversas e arquivos sobre um trabalho, por exemplo: BBL Launcher.');const name=field(el,'Nome',project?.name||'');name.maxLength=100;const instructions=field(el,'Objetivo, requisitos e decisões do projeto',project?.instructions||'',true);instructions.maxLength=6000;button(el,'Salvar projeto',()=>{if(!name.value.trim())return name.focus();const p=project||{id:uid(),files:[]};p.name=name.value.trim();p.instructions=instructions.value;if(!project)workspace.projects.push(p);persist();showProject(p.id)})}
function showProjects(){const el=modalContent('Projetos','Organize aplicativos, launchers e outros trabalhos com contexto próprio.');button(el,'＋ Criar projeto',()=>editProject());workspace.projects.forEach(p=>button(el,p.name,()=>showProject(p.id)))}
function projectFileVersions(projectId){
 const versions=[];
 for(const chat of workspace.chats.filter(c=>c.projectId===projectId))chat.messages.forEach((message,index)=>{
  const files=(message.artifacts||[]).filter(f=>typeof f.content==='string'&&!f.data_base64&&!f.download_url);
  if(message.role==='assistant'&&files.length)versions.push({chatId:chat.id,index,title:chat.title,updated:chat.updated,files:structuredClone(files)});
 });
 return versions.sort((a,b)=>b.updated-a.updated||b.index-a.index);
}
async function restoreProjectVersion(projectId,chatId,index){
 if(busy())return;
 const project=workspace.projects.find(p=>p.id===projectId),source=workspace.chats.find(c=>c.id===chatId&&c.projectId===projectId);
 const version=projectFileVersions(projectId).find(v=>v.chatId===chatId&&v.index===index);
 if(!project||!source||!version)return notify('Esta versão não está mais disponível.');
 await saveChat();
 const files=new Map();
 for(const file of project.files||[])if(file.type==='text')files.set(file.name,{name:file.name,content:file.data});
 for(const chat of workspace.chats.filter(c=>c.projectId===projectId).sort((a,b)=>a.updated-b.updated))for(const message of chat.messages)for(const file of message.artifacts||[])if(typeof file.content==='string'&&!file.data_base64&&!file.download_url)files.set(file.name,structuredClone(file));
 for(const file of version.files)files.set(file.name,structuredClone(file));
 const now=Date.now(),chat={id:uid(),projectId,title:project.name+' · código restaurado',created:now,updated:now,files:[],messages:[
  {role:'user',content:'Restaurar os arquivos da resposta '+(index+1)+' da conversa '+source.title+'.'},
  {role:'assistant',content:'Código restaurado em uma nova conversa. As conversas anteriores foram preservadas. Arquivos não alterados nesta versão mantêm o conteúdo mais recente.',artifacts:Array.from(files.values())}
 ]};
 workspace.chats.unshift(chat);workspace.active=chat.id;await persist();renderChat();document.getElementById('modal').close();notify('Versão restaurada em nova conversa.');return chat;
}
function showProjectVersions(projectId){
 const project=workspace.projects.find(p=>p.id===projectId);if(!project)return;
 const el=modalContent('Versões de '+project.name,'Restaure código em uma nova conversa, preservando as anteriores. Arquivos que não foram alterados mantêm a versão mais recente.');
 const versions=projectFileVersions(projectId);
 if(!versions.length)el.append(document.createTextNode('As respostas com arquivos de código aparecerão aqui.'));
 for(const version of versions){
  const card=document.createElement('section');card.className='integration';const title=document.createElement('strong');title.textContent=version.title+' · resposta '+(version.index+1);card.append(title);
  const names=document.createElement('p');names.textContent=version.files.map(f=>f.name).join(', ');card.append(names);
  button(card,'Baixar arquivos desta resposta',()=>downloadZip('BBLIA-versao.zip',version.files));
  button(card,'Restaurar código em nova conversa',()=>restoreProjectVersion(projectId,version.chatId,version.index));el.append(card);
 }
}
function showProject(id){const p=workspace.projects.find(p=>p.id===id);if(!p)return;const el=modalContent(p.name,p.instructions||'Adicione os requisitos deste trabalho.');button(el,'＋ Nova conversa neste projeto',()=>newChat(id));button(el,'Editar objetivo e requisitos',()=>editProject(p));button(el,'Versões dos arquivos',()=>showProjectVersions(id));button(el,'Baixar código do projeto (.zip)',()=>{const files=new Map();(p.files||[]).filter(f=>f.type==='text').forEach(f=>files.set(f.name,f.data));workspace.chats.filter(c=>c.projectId===id).sort((a,b)=>a.updated-b.updated).forEach(c=>c.messages.forEach(m=>(m.artifacts||[]).filter(f=>!f.download_url).forEach(f=>files.set(f.name,f.data_base64?f:f.content))));files.set('BBLIA-PROJETO.md','# '+p.name+'\n\n'+p.instructions);downloadZip('BBLIA-projeto.zip',Array.from(files,([name,content])=>typeof content==='object'?content:{name,content})) });button(el,'Adicionar arquivos ao projeto',()=>chooseFiles(async files=>{if((p.files||[]).length+files.length>4)return notify('Até quatro arquivos por projeto.');p.files=(p.files||[]).concat(files);await persist();showProject(id)}));(p.files||[]).forEach((f,i)=>button(el,'Remover arquivo: '+f.name,()=>{p.files.splice(i,1);persist();showProject(id)}));workspace.chats.filter(c=>c.projectId===id).forEach(c=>button(el,c.title,()=>switchChat(c.id)))}
function showSettings(){const prefs=workspace.preferences;const el=modalContent('Configurações','Uso pessoal: sem limite diário de mensagens definido pela BBLIA.');button(el,'Minha conta e sincronização',()=>showAccount());const provider=document.createElement('select');provider.setAttribute('aria-label','Inteligência artificial');for(const [value,label] of [['openai','OpenAI · consome créditos da API']]){const option=document.createElement('option');option.value=value;option.textContent=label;provider.append(option)}provider.value=aiRequestOptions().provider;el.append(provider);const voiceNote=document.createElement('p');voiceNote.textContent='A voz é gerada por inteligência artificial. Chat, voz e trabalhos usam o provedor selecionado.';el.append(voiceNote);const name=field(el,'Como devo chamar você?',prefs.name);button(el,'Memória pessoal',()=>showMemories());button(el,'Gerenciar conversa atual',()=>manageConversation());const instructions=field(el,'Preferências e instruções pessoais',prefs.instructions,true);instructions.maxLength=2000;const detail=field(el,'Estilo da resposta',prefs.detail);const web=document.createElement('input');web.type='checkbox';web.checked=prefs.web!==false;const label=document.createElement('label');label.textContent=' Permitir pesquisa na internet';label.prepend(web);el.append(label);button(el,'Salvar configurações',async()=>{workspace.preferences={...prefs,provider:provider.value,name:name.value.slice(0,100),instructions:instructions.value,detail:detail.value.slice(0,100),web:web.checked};await persist();notify('Configurações salvas');document.getElementById('modal').close()});button(el,'Exportar backup de projetos e conversas',()=>{saveChat();downloadText('BBLIA-backup.json',JSON.stringify(workspace,null,2),'application/json')});button(el,'Importar backup',()=>{const input=document.createElement('input');input.type='file';input.accept='.json';input.onchange=async()=>{try{const f=input.files[0];if(!f||f.size>30000000)throw Error('Backup muito grande.');const value=JSON.parse(await f.text());validateBackup(value);saveChat();for(const p of value.projects){const old=p.id;p.id=uid();value.chats.filter(c=>c.projectId===old).forEach(c=>c.projectId=p.id)}value.chats.forEach(c=>c.id=uid());workspace.projects.push(...value.projects);workspace.chats.push(...value.chats);await persist();showHistory()}catch(e){notify('Não foi possível importar: '+e.message)}};input.click()})}
function validateBackup(v){if(v?.version!==1||!Array.isArray(v.projects)||!Array.isArray(v.chats)||v.projects.length>200||v.chats.length>2000)throw Error('Formato inválido.');for(const p of v.projects){if(typeof p.id!=='string'||typeof p.name!=='string'||typeof p.instructions!=='string'||!Array.isArray(p.files)||p.files.length>4)throw Error('Projeto inválido.');p.files.forEach(validateAttachment)}for(const c of v.chats){if(typeof c.id!=='string'||typeof c.title!=='string'||!Array.isArray(c.messages)||c.messages.some(m=>!['user','assistant'].includes(m.role)||typeof m.content!=='string'||(m.artifacts&&!Array.isArray(m.artifacts))||(m.sources&&!Array.isArray(m.sources))))throw Error('Conversa inválida.')}}
function validateAttachment(f){if(!f||typeof f.name!=='string'||typeof f.data!=='string'||!['text','pdf','image'].includes(f.type)||f.data.length>7000000)throw Error('Anexo inválido.')}
async function showIntegrations(){const el=modalContent('Ferramentas e conexões','O estado indica configuração, não um teste de funcionamento do serviço externo.');try{const r=await fetch('/api/integrations');if(!r.ok)throw Error();const data=await r.json();for(const item of data.items){if(item.id==='computer'&&typeof readComputer==='function'){const connection=await readComputer();if(connection?.device_id){item.state='selected';item.detail='Computador selecionado neste navegador: '+(connection.device_name||connection.device_id)+'. A execução depende do Commander online.'}}const card=document.createElement('section');card.className='integration';const h=document.createElement('strong');h.textContent=item.name+' · '+({configured:'Configurado',external:'Serviço externo',missing:'Não conectado',connected:'Conectado',ready:'Aguardando autorização',selected:'Selecionado'}[item.state]||item.state);const p=document.createElement('p');p.className='muted';p.textContent=item.detail;card.append(h,p);if(item.id==='computer'&&typeof showComputerConnection==='function')button(card,'Computador e TV Box',()=>showComputerConnection());if(item.id==='sync')button(card,'Minha conta e sincronização',()=>showAccount());if(item.id==='accounts')button(card,'Conectar e gerenciar Google',()=>showGoogleConnections());el.append(card)}}catch(e){el.append(document.createTextNode('Não consegui consultar o servidor agora.'))}}
function chooseFiles(done){const picker=document.createElement('input');picker.type='file';picker.multiple=true;picker.accept='*/*';picker.onchange=async()=>{try{const files=Array.from(picker.files);if(files.length>4)throw Error('Escolha até quatro arquivos.');const result=[];for(const file of files){const ext=file.name.split('.').pop().toLowerCase();if(!['apk','zip','png','jpg','jpeg','webp','pdf','txt','md','json','csv','xml','html','css','js','ts','tsx','jsx','py','java','kt','kts','gradle','yaml','yml','sh','properties'].includes(ext))throw Error('Formato não suportado. Escolha ZIP, APK, foto, PDF ou texto/código.');if(ext==='apk'||ext==='zip'){if(file.size>100*1024*1024)throw Error('Máximo de 100 MB por ZIP ou APK.');notify('Enviando e analisando '+file.name+'...');const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),180000);try{const response=await fetch('/api/'+ext+'/analyze',{method:'POST',headers:{'Content-Type':ext==='zip'?'application/zip':'application/vnd.android.package-archive','X-Filename':encodeURIComponent(file.name)},body:file,signal:controller.signal});const payload=await response.json();if(!response.ok)throw Error(payload.error||'Não foi possível analisar o APK.');validateAttachment(payload.attachment);result.push(payload.attachment);notify(ext.toUpperCase()+' analisado: '+(payload.attachment.apk?.package||file.name));}catch(error){throw Error(error.name==='AbortError'?'O envio do arquivo demorou demais. Tente novamente.':error.message)}finally{clearTimeout(timer)}continue;}if(file.size>5*1024*1024)throw Error('Máximo de 5 MB por foto/PDF ou texto.');let type,data;if(['png','jpg','jpeg','webp','pdf'].includes(ext)){type=ext==='pdf'?'pdf':'image';data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(file)});const mime=ext==='pdf'?'application/pdf':ext==='jpg'||ext==='jpeg'?'image/jpeg':'image/'+ext;data='data:'+mime+';base64,'+data.split(',')[1]}else{type='text';data=await file.text();if(data.length>120000||data.includes('\u0000'))throw Error('Envie código/texto UTF-8 de até 120 mil caracteres.')}result.push({name:file.name,type,data})}await done(result)}catch(e){notify(e.message)}};picker.click()}
function renderAttachments(){const bar=document.getElementById('attachmentBar');bar.replaceChildren();attachments.forEach((f,i)=>button(bar,'✕ '+(f.apk?'APK analisado: '+f.apk.name:f.name),()=>{attachments.splice(i,1);renderAttachments()}));if(attachments.some(f=>f.type==='image'))button(bar,'🎬 Animar imagem em vídeo',async()=>{if(send.disabled)return;const reference=attachments.find(f=>f.type==='image');const movement=prompt.value.trim()||'The same character from the reference image moves and dances naturally. Preserve the face, clothes, art style and background. Smooth motion, static camera.';prompt.value='';attachments=[];renderAttachments();await submitMedia('video',movement,reference)});if(attachments.some(f=>f.type==='image'))button(bar,'🎨 Editar foto com meu pedido',async()=>{const text=prompt.value.trim();if(text.length<5)return notify('Descreva a alteração no campo de mensagem.');if(send.disabled)return;const reference=attachments.find(f=>f.type==='image');prompt.value='';attachments=[];renderAttachments();await generateMedia('image',text,null,reference)})}
sendMessage=async function(){
 if(!workspaceReady||send.disabled)return;let text=prompt.value.trim();if(!text&&attachments.length)text='Analise os arquivos anexados.';if(!text)return;const project=currentProject();const projectFiles=project?.files||[];const selected=[...projectFiles,...(attachments.length?attachments:(currentChat()?.files||[]))];if(selected.length>4)return notify('Use até quatro anexos somando os arquivos do projeto.');if(text.length>60000)return notify('Mensagem muito longa. Anexe o código como arquivo.');
 const kind=selected.length||/\b(launcher|aplicativo|app|código|codigo|programar|programação|programacao)\b/i.test(text)?null:mediaIntent(text);if(kind){prompt.value='';await submitMedia(kind,text);saveChat();return}
 currentChat().files=selected.slice(projectFiles.length);prompt.value='';attachments=[];renderAttachments();const label=selected.length?'\n[Anexos: '+selected.map(f=>f.name).join(', ')+']':'';add('user',text+label);history.push({role:'user',content:text+label});saveChat();send.disabled=true;waitingVoice=true;const bubble=add('assistant','Trabalhando...');notify('Processando...');
 try{let messages=history.slice(-48).map(({role,content,artifacts})=>({role,content:(content+(artifacts?.length?'\nArquivos gerados nesta resposta:\n'+artifacts.map(f=>'Arquivo: '+f.name+'\n'+f.content).join('\n'):'')).slice(0,60000)}));if(messages[0]?.role==='assistant')messages.shift();const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...aiRequestOptions(),messages,attachments:selected,preferences:{...workspace.preferences,conversation_mode:voiceMode?'voice':'text'},project:project?{name:project.name,instructions:project.instructions}:{}})});const data=await r.json();if(!r.ok)throw Error(data.error||'Falha na conexão.');if(data.action?.kind==='work'){const useComputer=typeof computerReady==='function'&&await computerReady();if(wantsAndroidBuild(data.action.prompt||text)&&!useComputer){if(typeof queueComputerTask==='function')await queueComputerTask(text,selected);bubble.textContent='Pedido salvo. Conecte o computador para compilar e entregar o APK.';if(typeof showComputerConnection==='function')await showComputerConnection();return}send.disabled=false;waitingVoice=false;await runAutonomousWork(data.action.prompt||text,selected,{useComputer,reuseUser:true,bubble});return}if(data.action){history.pop();await generateMedia(data.action.kind,data.action.prompt,bubble,data.action.kind==='video'?selected.find(f=>f.type==='image')||null:null);saveChat();return}paintResponse(bubble,data.answer,data.artifacts||[],data.sources||[]);history.push({role:'assistant',content:data.answer,artifacts:data.artifacts||[],sources:data.sources||[]});await saveChat();button(bubble,'Guardar na memória',()=>rememberNote(data.answer));button(bubble,'Continuar em nova conversa',()=>branchConversation(history.length));notify('Resposta concluída');await replyByVoice(data.answer)}catch(e){bubble.textContent='Não foi possível concluir: '+e.message;history.pop();attachments=selected.slice(projectFiles.length);renderAttachments();prompt.value=text;saveChat();notify('Pedido não concluído. Você pode tentar novamente.');if(voiceMode)await replyByVoice('Não consegui responder agora. '+e.message)}finally{send.disabled=false;waitingVoice=false;feed.scrollTop=feed.scrollHeight;if(voiceMode&&!realtimePC&&document.getElementById('auto').checked)scheduleVoiceListen(500)}
};
const originalOpenSection=openSection;
openSection=function(which){if(!workspaceReady)return notify('Carregando seus projetos...');if(which==='projects')return showProjects();if(which==='history')return showHistory();if(which==='settings')return showSettings();if(which==='plugins')return showIntegrations();if(which==='plans')return modalContent('Uso pessoal','A BBLIA está em desenvolvimento para seu uso. Limites comerciais e preços serão definidos depois. Não há limite diário de mensagens no aplicativo.');return originalOpenSection(which)};
async function initWorkbench(){
 const title=document.createElement('div');title.id='workTitle';title.className='work-title';document.querySelector('.app').prepend(title);const bar=document.createElement('div');bar.id='attachmentBar';document.querySelector('.composer').before(bar);const attach=document.createElement('button');attach.className='dictate';attach.textContent='＋';attach.setAttribute('aria-label','Anexar ZIP, APK, fotos, PDF ou código');attach.onclick=()=>chooseFiles(files=>{if(attachments.length+files.length>4)return notify('Até quatro anexos.');attachments.push(...files);renderAttachments()});document.querySelector('.composer').prepend(attach);
 const nav=document.querySelector('.panel');const projects=document.createElement('button');projects.className='navbtn';projects.textContent='📁 Projetos';projects.onclick=()=>showProjects();nav.insertBefore(projects,nav.querySelector('.navbtn'));const pluginButton=nav.querySelector('[onclick*="plugins"]');pluginButton.textContent='🧩 Ferramentas e conexões';
 try{db=await new Promise((resolve,reject)=>{const req=indexedDB.open('bblia-workbench',1);req.onupgradeneeded=()=>req.result.createObjectStore('work');req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error)});const saved=await new Promise((resolve,reject)=>{const req=db.transaction('work').objectStore('work').get('state');req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error)});if(saved){validateBackup(saved);workspace=saved}}catch(e){notify('Histórico não disponível neste navegador. Exporte backups para guardar o trabalho.')}
 workspaceReady=true;if(!currentChat()){workspace.active=uid();workspace.chats.unshift({id:workspace.active,title:'Nova conversa',projectId:null,messages:history.slice(),created:Date.now(),updated:Date.now()})}renderChat();resumeMedia();notify('Uso pessoal · sem limite diário de mensagens');
 const online=document.getElementById('online');online.textContent='Verificando';fetch('/health').then(r=>{online.textContent=r.ok?(aiRequestOptions().provider==='openai'?'OpenAI · créditos da API':'Gemini · cota gratuita'):'Falha no servidor'}).catch(()=>online.textContent='Sem conexão');
 document.getElementById('auto').checked=workspace.preferences.auto!==false;document.getElementById('auto').addEventListener('change',e=>{workspace.preferences.auto=e.target.checked;persist()});
 const accountButton=document.createElement('button');accountButton.className='navbtn';accountButton.textContent='👤 Minha conta e sincronização';accountButton.onclick=()=>showAccount();nav.prepend(accountButton);
 workspaceReady=false;try{await cloudInit()}finally{workspaceReady=true}
}



// Notes remain in this browser's private workspace and are included in its backups.
function showMemories(){
 const el=modalContent('Memória pessoal','Escolha o que a BBLIA deve lembrar neste espaço. Com sua conta conectada, as memórias também entram na sincronização. Você pode editar ou apagar.');
 const enabled=document.createElement('input');enabled.type='checkbox';enabled.checked=workspace.preferences.memory_enabled!==false;
 const label=document.createElement('label');label.textContent=' Usar minhas memórias nas respostas';label.prepend(enabled);el.append(label);
 const notes=field(el,'Uma memória por linha',(workspace.preferences.memories||[]).join('\n'),true);notes.maxLength=12000;
 button(el,'Salvar memórias',async()=>{const values=notes.value.split('\n').map(n=>n.trim()).filter(Boolean);if(values.length>40||values.some(n=>n.length>1000))return notify('Use até 40 memórias de até 1000 caracteres.');workspace.preferences.memories=values;workspace.preferences.memory_enabled=enabled.checked;await persist();document.getElementById('modal').close();notify('Memórias salvas neste aparelho')});
 button(el,'Apagar todas as memórias',async()=>{workspace.preferences.memories=[];await persist();showMemories()});
}
function rememberNote(text){
 const el=modalContent('Guardar uma memória','Revise o trecho antes de salvar. Evite senhas e informações que não queira enviar nas próximas conversas.');
 const note=field(el,'O que lembrar',String(text).slice(0,1000),true);note.maxLength=1000;
 button(el,'Guardar',async()=>{const value=note.value.trim();if(!value)return;const notes=workspace.preferences.memories||[];if(notes.length>=40)return notify('Edite suas memórias para liberar espaço.');if(!notes.includes(value))notes.push(value);workspace.preferences.memories=notes;await persist();document.getElementById('modal').close();notify('Memória guardada')});
}
function branchConversation(index){
 if(busy())return;saveChat();const original=currentChat();const edited=original.messages[index];
 const c={...structuredClone(original),id:uid(),title:original.title+' · continuação',messages:structuredClone(original.messages.slice(0,index)),created:Date.now(),updated:Date.now()};
 workspace.chats.unshift(c);workspace.active=c.id;persist();renderChat();if(edited?.role==='user')prompt.value=edited.content;document.getElementById('modal').close();prompt.focus();
}
function manageConversation(){
 if(busy())return;const c=currentChat();if(!c)return;const el=modalContent('Gerenciar conversa','A continuação preserva a conversa original.');
 const title=field(el,'Nome da conversa',c.title);title.maxLength=100;
 button(el,'Salvar nome',async()=>{c.title=title.value.trim()||'Nova conversa';await persist();renderChat();document.getElementById('modal').close()});
 button(el,'Continuar em nova conversa',()=>branchConversation(c.messages.length));
 button(el,'Excluir esta conversa',()=>{const confirm=modalContent('Excluir conversa?',cloudUser?'Esta conversa será removida dos aparelhos sincronizados. Exporte um backup se quiser guardá-la.':'Esta conversa será removida deste aparelho. Exporte um backup se quiser guardá-la.');button(confirm,'Confirmar exclusão',async()=>{workspace.chats=workspace.chats.filter(item=>item.id!==c.id);workspace.active=workspace.chats[0]?.id||null;history=[];if(!workspace.active){newChat(c.projectId);return}await persist();renderChat();document.getElementById('modal').close()});button(confirm,'Voltar',()=>manageConversation())});
}



async function googleCall(path,data){
 const r=await fetch('/api/google/'+path,{method:data?'POST':'GET',headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined});
 const value=await r.json();if(!r.ok)throw Error(value.error||'Falha na conexão Google.');return value;
}
async function showGoogleConnections(){
 const el=modalContent('E-mail, agenda e Drive','Conecte sua conta Google para consultar seus dados na BBLIA.');
 try{
  const s=await googleCall('status');const info=document.createElement('p');info.textContent=s.connected?'Conta conectada neste navegador.':s.detail;el.append(info);
  const note=document.createElement('p');note.textContent=s.session_note;el.append(note);
  const choices=[];for(const [key,name] of [['email','Gmail'],['calendar','Agenda Google'],['drive','Google Drive'],['login','Login da BBLIA'],['sync','Histórico e projetos na nuvem']]){
   const label=document.createElement('label');label.style.display='block';const input=document.createElement('input');input.type='checkbox';input.checked=s.services.includes(key)||key==='login'||key==='sync';if(key==='login'||key==='sync'){input.disabled=true;input.title='Obrigatório para manter a conta e a sincronização da BBLIA'}label.append(input,document.createTextNode(' '+name));el.append(label);choices.push([key,input]);
  }
  const saveNote=document.createElement('p');saveNote.textContent='Marque os serviços e toque em Salvar. As permissões já autorizadas serão salvas sem abrir o Google novamente.';el.append(saveNote);
  const detail=document.createElement('p');detail.textContent='Gmail, Agenda e Drive são acessados somente com as permissões concedidas. Login e sincronização mantêm o espaço privado da BBLIA.';el.append(detail);
  if(s.configured){
   const saveButton=button(el,s.connected?'Salvar':'Conectar com Google',async()=>{
    const prior=saveButton.textContent;
    saveButton.disabled=true;saveButton.textContent='Salvando…';
    feedback.textContent='Enviando configurações…';feedback.style.color='#ffda82';
    try{
     const selected=choices.filter(x=>x[1].checked).map(x=>x[0]);
     if(!selected.length)throw Error('Escolha pelo menos um serviço.');
     if(!s.connected){const result=await googleCall('start',{services:selected});location.assign(result.url);return}
     let result;
     try{result=await googleCall('save',{services:selected})}
     catch(error){
      if(/adicionar novas permissões|autorizar no Google/i.test(error.message)){
       feedback.textContent='Abrindo o Google para autorizar as permissões adicionais…';
       const authorization=await googleCall('start',{services:selected});
       location.assign(authorization.url);return;
      }
      throw error;
     }
     feedback.style.color='#8cf0b5';feedback.textContent='✓ '+(result.message||'Salvo com sucesso.');
    }catch(e){
     feedback.style.color='#ff9999';feedback.textContent='Não foi possível salvar: '+e.message;
    }finally{saveButton.disabled=false;saveButton.textContent=prior}
   });
   const feedback=document.createElement('p');feedback.setAttribute('role','status');feedback.setAttribute('aria-live','polite');feedback.style.cssText='min-height:24px;font-weight:700';el.append(feedback);
  }
  else {const help=document.createElement('p');help.textContent='Falta configurar o cliente Google da BBLIA no servidor. Não envie sua senha. Depois da configuração, o botão Conectar com Google será liberado.';el.append(help)}
  if(s.connected){
   for(const [service,label,tool] of [['email','Testar Gmail','consultar_email'],['calendar','Testar agenda','consultar_agenda'],['drive','Testar Drive','buscar_drive']]){
    if(!s.services.includes(service))continue;
    button(el,label,async()=>{try{notify('Consultando Google...');const result=await googleCall('query',{tool,args:{consulta:''}});const out=document.createElement('pre');out.style.whiteSpace='pre-wrap';out.style.overflowWrap='anywhere';out.textContent=JSON.stringify(result,null,2);el.append(out);notify('Consulta concluída')}catch(e){notify(e.message)}});
   }

  }
 }catch(e){el.append(document.createTextNode(e.message))}
}
if(typeof location!=='undefined' && new URLSearchParams(location.search).get('google')==='connected'){
 window.history.replaceState(null,'',location.pathname);setTimeout(()=>showGoogleConnections(),800);
}



// Account workspaces are isolated in IndexedDB. Google tokens remain in HttpOnly server sessions.
let cloudUser=null,cloudReady=false,cloudIgnore=false,cloudRunning=false,cloudTimer=null;
let cloudGeneration=0,cloudSavedGeneration=0,cloudLast='',cloudError='',cloudDevice='';
let cloudKnown={chats:new Map(),projects:new Map(),preferences:''};
function cloudFingerprint(item){const {updated,...rest}=item;return JSON.stringify(rest)}
function cloudRemember(){cloudKnown={chats:new Map(workspace.chats.map(x=>[x.id,cloudFingerprint(x)])),projects:new Map(workspace.projects.map(x=>[x.id,cloudFingerprint(x)])),preferences:JSON.stringify(workspace.preferences)}}
function cloudTrack(){
 if(!cloudUser||!cloudReady||cloudIgnore)return;
 let changed=false;workspace.deleted=workspace.deleted||{};
 for(const kind of ['chats','projects']){
  const next=new Map();for(const item of workspace[kind]){const fingerprint=cloudFingerprint(item);if(cloudKnown[kind].get(item.id)!==fingerprint){item.updated=Date.now();changed=true}next.set(item.id,fingerprint)}
  for(const id of cloudKnown[kind].keys())if(!next.has(id)){workspace.deleted[kind+':'+id]=Date.now();changed=true}
  cloudKnown[kind]=next;
 }
 const prefs=JSON.stringify(workspace.preferences);if(prefs!==cloudKnown.preferences){workspace.preferencesUpdated=Date.now();cloudKnown.preferences=prefs;changed=true}
 if(changed){cloudGeneration++;clearTimeout(cloudTimer);cloudTimer=setTimeout(()=>cloudSync(false),1800);cloudBadge('Alterações salvas no aparelho; sincronização pendente')}
}
function cloudBadge(message){const el=document.getElementById('accountState');if(el)el.textContent=message}
async function accountRequest(path,data){
 const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),120000);
 try{const r=await fetch(path,{method:data?'POST':'GET',headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined,signal:controller.signal});const value=await r.json();if(!r.ok)throw Error(value.error||'Falha na sincronização.');return value}finally{clearTimeout(timer)}
}
async function cloudRead(key){if(!db)return null;return new Promise((resolve,reject)=>{const req=db.transaction('work').objectStore('work').get(key);req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error)})}
async function cloudWrite(key,value){if(!db)throw Error('Armazenamento local indisponível.');return new Promise((resolve,reject)=>{const tx=db.transaction('work','readwrite');tx.objectStore('work').put(structuredClone(value),key);tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error)})}
function cloudEmpty(){return {version:1,projects:[],chats:[],active:null,preferences:{name:'',instructions:'',detail:'Detalhada',web:true,auto:true},deleted:{},preferencesUpdated:0}}
function cloudRender(){
 const draft=prompt.value,selected=attachments.slice();renderChat();prompt.value=draft;attachments=selected;renderAttachments();document.getElementById('auto').checked=workspace.preferences.auto!==false;
}
async function cloudInit(){
 const badge=document.createElement('div');badge.id='accountState';badge.className='muted';badge.style.cssText='font-size:12px;padding:4px 12px;overflow-wrap:anywhere';document.getElementById('workTitle').after(badge);
 cloudBadge('Neste aparelho · entre na sua conta para sincronizar');
 try{
  const state=await accountRequest('/api/account');
  if(!state.user||!state.services.includes('sync'))return;
  if(!db){cloudBadge('Conta reconhecida; navegador sem armazenamento local. Sincronização não iniciada.');return}
  await saveChat(); // Preserve the previous guest workspace before changing account keys.
  cloudDevice=await cloudRead('sync-device');if(!cloudDevice){cloudDevice=uid();await cloudWrite('sync-device',cloudDevice)}
  const cached=await cloudRead('account:'+state.user.id);
  if(cached)validateBackup(cached);
  cloudUser=state.user;workspace=cached||cloudEmpty();cloudReady=true;cloudRemember();
  if(!currentChat()){cloudIgnore=true;history=[];newChat();cloudIgnore=false;cloudRemember()}
  cloudRender();await cloudSync(false);
 }catch(e){cloudError=e.message;cloudBadge('Sincronização indisponível: '+e.message)}
}
function cloudConversationBusy(){return send.disabled||(typeof waitingVoice!=='undefined'&&waitingVoice)||(typeof voiceSpeaking!=='undefined'&&voiceSpeaking)}
async function cloudSync(manual=false){
 if(!cloudUser||!cloudReady)return;
 if(cloudRunning){if(manual)notify('A sincronização já está em andamento.');return}
 if(cloudConversationBusy()){clearTimeout(cloudTimer);cloudTimer=setTimeout(()=>cloudSync(false),4000);if(manual)notify('A sincronização continuará após a resposta.');return}
 cloudTrack();clearTimeout(cloudTimer);cloudRunning=true;const generation=cloudGeneration;const account=cloudUser.id;
 cloudBadge('Sincronizando '+cloudUser.email+'…');
 try{
  const value=await accountRequest('/api/sync',{account,device:cloudDevice,workspace:structuredClone(workspace)});
  if(!cloudUser||cloudUser.id!==account||value.user?.id!==account)throw Error('A conta mudou. Atualize a página.');
  validateBackup(value.workspace);
  if(generation!==cloudGeneration||cloudConversationBusy()){cloudTimer=setTimeout(()=>cloudSync(false),2000);return}
  const active=workspace.active;workspace={...value.workspace,active};
  if(!currentChat())workspace.active=workspace.chats[0]?.id||null;
  cloudIgnore=true;
  if(!currentChat()){history=[];newChat()}
  await persist();cloudRemember();cloudIgnore=false;
  cloudSavedGeneration=generation;cloudLast=new Date(value.saved_at).toLocaleTimeString('pt-BR');cloudError='';
  cloudRender();cloudBadge(cloudUser.email+' · sincronizado às '+cloudLast);
  if(manual)notify('Conversas e projetos sincronizados.');
 }catch(e){cloudIgnore=false;cloudError=e.name==='AbortError'?'Tempo de sincronização esgotado.':e.message;cloudBadge('Dados locais preservados · '+cloudError);if(manual)notify(cloudError)}
 finally{cloudRunning=false}
}
async function showAccount(){
 const el=modalContent('Minha conta e sincronização','Entre com a mesma conta Google em cada aparelho para continuar seus projetos.');
 if(!cloudUser){
  const p=document.createElement('p');p.textContent='Você está usando o histórico deste navegador. Ao entrar, a BBLIA abrirá um espaço separado para sua conta.';el.append(p);
  button(el,'Entrar com Google e ativar sincronização',async()=>{try{if(send.disabled||voiceMode)return notify('Finalize a resposta ou a conversa por voz antes de entrar.');if(!db)throw Error('Este navegador não permite salvar os dados locais. Abra no Chrome ou Safari.');await saveChat();const result=await accountRequest('/api/account/start',{});location.assign(result.url)}catch(e){notify(e.message)}});
 }else{
  const p=document.createElement('p');p.textContent='Conta: '+cloudUser.email+' · '+(cloudLast?'Última sincronização: '+cloudLast:'Ainda sem sincronização confirmada');el.append(p);
  if(cloudError){const error=document.createElement('p');error.textContent=cloudError;el.append(error)}
  button(el,'Sincronizar agora',()=>cloudSync(true));
  button(el,'Importar conversas anteriores deste navegador',async()=>{
   try{const guest=await cloudRead('state');if(!guest)return notify('Não há histórico anterior para importar.');validateBackup(guest);
    const existingChats=new Set(workspace.chats.map(x=>x.id)),existingProjects=new Set(workspace.projects.map(x=>x.id));
    const candidate=structuredClone(workspace);candidate.chats.push(...structuredClone(guest.chats.filter(x=>!existingChats.has(x.id))));candidate.projects.push(...structuredClone(guest.projects.filter(x=>!existingProjects.has(x.id))));
    validateBackup(candidate);workspace=candidate;await persist();await cloudSync(true);showAccount();
   }catch(e){notify('Importação não concluída: '+e.message)}
  });
  button(el,'Sair da conta neste aparelho',async()=>{if(send.disabled||voiceMode)return notify('Finalize a resposta ou a conversa por voz antes de sair.');try{await saveChat();if(cloudGeneration!==cloudSavedGeneration){await cloudSync(true);if(cloudGeneration!==cloudSavedGeneration)return notify('Existem alterações pendentes. Exporte um backup ou conclua a sincronização antes de sair.')}await accountRequest('/api/account/logout',{});await cloudLeave();showAccount()}catch(e){notify(e.message)}});
 }
 const note=document.createElement('p');note.textContent='Conversas, arquivos anexados aos projetos e preferências ficam no espaço privado da BBLIA no seu Google Drive. Login expira em até 12 horas e pode precisar ser refeito após reinício do servidor. Sair não apaga seus dados salvos. Não compartilhe o mesmo perfil de navegador com outras pessoas.';el.append(note);
 button(el,'Exportar backup deste espaço',()=>downloadText('BBLIA-backup.json',JSON.stringify(workspace,null,2),'application/json'));
}
async function cloudLeave(){
 clearTimeout(cloudTimer);cloudReady=false;cloudUser=null;cloudGeneration=0;cloudSavedGeneration=0;cloudLast='';cloudError='';
 workspace=await cloudRead('state')||cloudEmpty();history=[];
 if(!currentChat()){cloudIgnore=true;newChat();cloudIgnore=false}
 cloudRender();cloudBadge('Neste aparelho · entre na sua conta para sincronizar');
}
if(typeof window!=='undefined'){
 window.addEventListener('online',()=>cloudSync(false));
 window.addEventListener('focus',()=>{if(cloudUser)cloudSync(false)});
 window.addEventListener('pagehide',()=>{if(cloudUser&&cloudGeneration!==cloudSavedGeneration)cloudBadge('Há alterações pendentes; mantenha a BBLIA aberta para sincronizar')});
 setInterval(()=>{if(cloudUser&&document.visibilityState==='visible')cloudSync(false)},60000);
}

initWorkbench();




async function bbliaMenuLogout(){
 closeDrawer();
 if(send.disabled||voiceMode)return notify('Finalize a resposta ou a conversa por voz antes de sair.');
 try{
  await saveChat();
  if(cloudUser&&cloudGeneration!==cloudSavedGeneration){
   await cloudSync(true);
   if(cloudGeneration!==cloudSavedGeneration)return notify('Sincronização pendente. Faça backup antes de sair.');
  }
  await accountRequest('/api/account/logout',{});
  await cloudLeave();
  location.replace('/?logged_out=1');
 }catch(e){notify('Não foi possível sair: '+e.message)}
}
function bbliaLoginGate(){
 if(document.getElementById('bbliaLoginGate'))return;
 const gate=document.createElement('div');gate.id='bbliaLoginGate';
 gate.style.cssText='position:fixed;inset:0;z-index:99999;background:#080e24;color:white;display:flex;align-items:center;justify-content:center;padding:22px;font:16px system-ui';
 const box=document.createElement('section');box.style.cssText='max-width:430px;width:100%;text-align:center;background:#152247;border:1px solid #a78348;border-radius:20px;padding:28px';
 const title=document.createElement('h2');title.textContent='BBLIA — Entre na sua conta';
 const p=document.createElement('p');p.textContent='Você saiu da BBLIA. Para usar o chat e os recursos novamente, entre com uma conta Google.';
 const b=document.createElement('button');b.textContent='Entrar com Google';b.className='choice';b.style.textAlign='center';
 b.onclick=async()=>{b.disabled=true;try{const result=await accountRequest('/api/account/start',{});location.assign(result.url)}catch(e){p.textContent='Não foi possível entrar: '+e.message;b.disabled=false}};
 box.append(title,p,b);gate.append(box);document.body.append(gate);
}
(async function bbliaCheckLoginOnLoad(){
 try{
  const state=await accountRequest('/api/account');
  if(!state.authenticated)bbliaLoginGate();
 }catch(e){bbliaLoginGate()}
})();
