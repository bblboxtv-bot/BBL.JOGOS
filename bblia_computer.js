'use strict';
const COMPUTER_KEY='desktop-commander-private';
const OAUTH_FLOW='bblia-commander-oauth';
let computerCache=null,computerRefreshPromise=null;
async function saveComputer(connection){
 if(!db)throw Error('O navegador não disponibilizou armazenamento para esta conexão.');
 await new Promise((resolve,reject)=>{const tx=db.transaction('work','readwrite');const store=tx.objectStore('work');
  if(connection)store.put(connection,COMPUTER_KEY);else store.delete(COMPUTER_KEY);
  tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error)});
 computerCache=connection;
}
async function readComputer(){
 if(computerCache)return computerCache;
 if(!db)return null;
 computerCache=await new Promise((resolve,reject)=>{const request=db.transaction('work').objectStore('work').get(COMPUTER_KEY);request.onsuccess=()=>resolve(request.result||null);request.onerror=()=>reject(request.error)});
 return computerCache;
}
async function queueComputerTask(text,selected=[]){
 if(typeof cloudWrite!=='function'||!db)return;
 await cloudWrite('computer-pending-task',{text,selected,chat:workspace.active,
  account:typeof cloudUser!=='undefined'&&cloudUser?cloudUser.id:'guest',created:Date.now()});
}
async function resumeQueuedComputerTask(){
 if(typeof cloudRead!=='function'||send.disabled)return false;
 const task=await cloudRead('computer-pending-task');if(!task)return false;
 const account=typeof cloudUser!=='undefined'&&cloudUser?cloudUser.id:'guest';
 if(task.account!==account||Date.now()-task.created>3600000||task.chat!==workspace.active)return false;
 if(!await computerReady())return false;
 await cloudWrite('computer-pending-task',null);
 notify('Computador conectado. Retomando o pedido salvo...');
 if(document.getElementById('modal').open)document.getElementById('modal').close();
 await runAutonomousWork(task.text,task.selected||[],{useComputer:true});return true;
}
async function computerPost(path,payload){
 const response=await fetch('/api/computer/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
 const data=await response.json();if(!response.ok)throw Error(data.error||'Não foi possível conectar o Commander.');return data;
}
async function computerConnection(){
 let connection=await readComputer();if(!connection)return null;
 if(connection.expires_at>Date.now()+60000)return connection;
 if(!connection.refresh_token)throw Error('A autorização do Commander expirou. Reconecte sua conta.');
 if(!computerRefreshPromise)computerRefreshPromise=(async()=>{
  const tokens=await computerPost('oauth/refresh',{client_id:connection.client_id,client_binding:connection.client_binding,refresh_token:connection.refresh_token});
  connection={...connection,...tokens,refresh_token:tokens.refresh_token||connection.refresh_token,
   expires_at:Date.now()+Number(tokens.expires_in||3600)*1000};
  await saveComputer(connection);return connection;
 })().finally(()=>{computerRefreshPromise=null});
 return computerRefreshPromise;
}
async function computerReady(){
 try{const c=await computerConnection();return !!(c?.access_token&&c.device_id)}catch(error){notify(error.message);return false}
}
function computerConnectIntent(text){
 const clean=String(text).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
 return /^(?:(?:bblia|meu amor)[, ]+)?(?:conecta|conecte|conectar|reconecta|reconecte|reconectar|entre|entrar|acesse|acessar|conecte-se|conecta-se)\s+(?:(?:ai|agora|automaticamente)\s+)?(?:(?:a|ao|no|na|com|em)\s+)?(?:(?:o|meu|minha)\s+)*(?:computador|pc|desktop|commander)(?:\s+(?:pra mim|para mim|por favor|agora|automaticamente))*[.!?]*$/.test(clean);
}
async function connectRequestedComputer(){
 let connection;
 try{connection=await computerConnection()}catch(error){notify(error.message);return showComputerConnection()}
 if(!connection?.access_token){notify('Abrindo a autorização inicial do seu computador...');return connectCommander()}
 try{
  notify('Conferindo a conexão com seu computador...');
  const devices=computerDevices((await computerPost('devices',{access_token:connection.access_token})).result);
  const selected=connection.device_id?devices.find(d=>d.id===connection.device_id):devices.length===1?devices[0]:null;
  if(!selected){notify('Selecione o computador que deseja usar.');return showComputerConnection()}
  await saveComputer({...connection,device_id:selected.id,device_name:selected.name});
  const message=selected.online?'Conectada ao computador '+selected.name+'. Pode dizer o que deseja fazer.':'O computador '+selected.name+' está offline. Abra o Commander nele para continuar.';
  notify(message);add('assistant',message);history.push({role:'assistant',content:message});await saveChat();
  if(typeof replyByVoice==='function')await replyByVoice(message);
  return selected.online;
 }catch(error){notify(error.message);return showComputerConnection()}
}
// An explicit chat/voice command starts pairing once; future commands reuse and refresh it.
if(typeof sendMessage==='function'){
 const computerSendMessage=sendMessage;
 sendMessage=async function(){
  const text=prompt.value.trim();
  if(!computerConnectIntent(text))return computerSendMessage();
  if(!workspaceReady||send.disabled)return;
  prompt.value='';add('user',text);history.push({role:'user',content:text});await saveChat();
  send.disabled=true;
  try{return await connectRequestedComputer()}finally{send.disabled=false;waitingVoice=false;if(voiceMode)scheduleVoiceListen(300)}
 };
}
function wantsComputerWork(text){
 if(/^(como\b|o que\b|qual\b|explique\b|me explique\b)/i.test(text.trim()))return false;
 return /computador|tv\s*box|tvbox|\badb\b|\bno pc\b|\busb\b|\bpowershell\b|\bterminal\b/i.test(text)
  ||/(instale|instalar|desinstale|desinstalar|congele|congelar|descongele|compile|compilar|execute|executar)\b/i.test(text);
}
function base64url(bytes){return btoa(String.fromCharCode(...bytes)).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'')}
async function connectCommander(){
 try{
  notify('Preparando a autorização do Commander...');
  const verifier=base64url(crypto.getRandomValues(new Uint8Array(48)));
  const state=base64url(crypto.getRandomValues(new Uint8Array(32)));
  const challenge=base64url(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(verifier))));
  const start=await computerPost('oauth/start',{state,code_challenge:challenge});
  const url=new URL(start.authorization_url);
  if(url.protocol!=='https:'||!['mcp.desktopcommander.app','auth.desktopcommander.app'].includes(url.hostname))throw Error('O serviço retornou um endereço de autorização inesperado.');
  sessionStorage.setItem(OAUTH_FLOW,JSON.stringify({state,verifier,client_id:start.client_id,client_binding:start.client_binding,created:Date.now()}));
  location.assign(url.href);
 }catch(error){notify(error.message);const el=modalContent('Conectar Commander',error.message);const p=document.createElement('p');p.textContent='A conexão só será ativada depois da autorização na sua conta Commander.';el.append(p)}
}
function computerDevices(result){
 const candidates=result?.structuredContent?.devices||result?.devices;
 if(Array.isArray(candidates))return candidates.map(d=>({id:d.id||d.deviceId||d.device_id,name:d.name||d.deviceName||d.id,
  online:d.online===true||d.status?.toLowerCase()==='online'})).filter(d=>typeof d.id==='string');
 const text=(result?.content||[]).filter(c=>c.type==='text').map(c=>c.text).join('\n');
 const devices=[];
 for(const match of text.matchAll(/\d+\.\s+([^\n]+)\n\s*Status:\s*(Online|Offline)[\s\S]*?\n\s*ID:\s*([a-zA-Z0-9-]+)/g)){
  devices.push({id:match[3],name:match[1].trim(),online:match[2]==='Online'});
 }
 return devices;
}
async function showComputerConnection(){
 const connection=await readComputer();
 const el=modalContent('Computador e TV Box',connection?.device_id?'Computador selecionado: '+(connection.device_name||connection.device_id):'Conecte sua própria conta Commander para a BBLIA usar os arquivos e o terminal do seu computador.');
 const note=document.createElement('p');note.className='muted';note.textContent='O Commander precisa estar online no computador. Para a TV Box, conecte o USB e autorize a depuração no aparelho. A BBLIA usa as permissões disponíveis na sua conta e no sistema.';el.append(note);
 button(el,connection?'Reconectar conta Commander':'Conectar minha conta Commander',connectCommander);
 if(!connection)return;
 button(el,'Conferir e selecionar computador',async()=>{
  try{
   notify('Verificando os computadores da sua conta...');
   const current=await computerConnection();
   const data=await computerPost('devices',{access_token:current.access_token});
   const devices=computerDevices(data.result);
   const list=document.createElement('div');el.append(list);
   if(!devices.length){list.textContent='Não consegui identificar um computador nesta resposta. Confira os aparelhos no Commander.';return}
   for(const device of devices){
    button(list,(device.id===current.device_id?'✓ ':'')+device.name+' · '+(device.online?'Online':'Offline'),async()=>{
     await saveComputer({...current,device_id:device.id,device_name:device.name});notify('Computador selecionado: '+device.name);if(!await resumeQueuedComputerTask())showComputerConnection();
    });
   }
   if(devices.length===1&&devices[0].online){
    await saveComputer({...current,device_id:devices[0].id,device_name:devices[0].name});
    notify('Commander conectado: '+devices[0].name);
   }
  }catch(error){notify(error.message);const message=document.createElement('p');message.textContent=error.message;el.append(message)}
 });
 button(el,'Desconectar deste navegador',async()=>{
  if(activeWork){await fetch('/api/work/jobs/'+encodeURIComponent(activeWork.id)+'/cancel',{method:'POST'}).catch(()=>{})}
  await saveComputer(null);notify('Conexão removida deste navegador.');showComputerConnection();
 });
}
const computerRequestWork=requestWork;
requestWork=async function(payload){
 if(!payload.use_computer)return computerRequestWork(payload);
 const connection=await computerConnection();
 if(!connection?.access_token||!connection.device_id)throw Error('Conecte o Commander e selecione o computador no menu Computador e TV Box.');
 // Add credentials only to this network request, never to the saved job payload,
 // chat, exported backup, generated artifacts, or model instructions.
 return computerRequestWork({...payload,computer_connection:{access_token:connection.access_token,device_id:connection.device_id}});
};
async function finishComputerOAuth(){
 const query=new URLSearchParams(location.search);
 const code=query.get('code'),returnedState=query.get('state'),error=query.get('error');
 window.history.replaceState(null,'','/');
 let flow;try{flow=JSON.parse(sessionStorage.getItem(OAUTH_FLOW)||'null')}catch(e){}
 if(error){sessionStorage.removeItem(OAUTH_FLOW);notify('A autorização do Commander não foi concluída.');return showComputerConnection()}
 if(!flow||!code||flow.state!==returnedState||Date.now()-flow.created>10*60*1000){notify('O pareamento expirou ou não pertence a este navegador. Conecte novamente.');return showComputerConnection()}
 sessionStorage.removeItem(OAUTH_FLOW);
 try{
  const tokens=await computerPost('oauth/token',{client_id:flow.client_id,client_binding:flow.client_binding,code,code_verifier:flow.verifier});
  await saveComputer({...tokens,client_id:flow.client_id,client_binding:flow.client_binding,expires_at:Date.now()+Number(tokens.expires_in||3600)*1000});
  notify('Conta autorizada. Conferindo seu computador...');
  try{
   const devices=computerDevices((await computerPost('devices',{access_token:tokens.access_token})).result);
   if(devices.length===1){await saveComputer({...await readComputer(),device_id:devices[0].id,device_name:devices[0].name});notify('Computador conectado: '+devices[0].name)}
  }catch(e){notify(e.message)}
  if(!await resumeQueuedComputerTask())showComputerConnection();
 }catch(error){notify(error.message);showComputerConnection()}
}
async function initComputerConnection(){
 while(!workspaceReady)await workSleep(100);
 const nav=document.querySelector('.panel');const entry=document.createElement('button');entry.className='navbtn';entry.textContent='🖥️ Computador e TV Box';entry.onclick=showComputerConnection;
 nav.insertBefore(entry,nav.querySelector('.navbtn'));
 if(location.pathname==='/computer-callback')await finishComputerOAuth();
 else if(new URLSearchParams(location.search).get('connect_computer')==='1'){
  const url=new URL(location.href);url.searchParams.delete('connect_computer');window.history.replaceState(null,'',url.pathname+url.search+url.hash);
  await connectRequestedComputer();
 }
}
initComputerConnection();
