'use strict';
let tvConnection=null,tvPending=null;
async function tvStore(key,value){
 if(!db)throw Error('Armazenamento local indisponível.');
 return new Promise((resolve,reject)=>{const tx=db.transaction('work','readwrite');tx.objectStore('work').put(value,key);tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error)});
}
async function tvRead(key){return new Promise((resolve,reject)=>{const req=db.transaction('work').objectStore('work').get(key);req.onsuccess=()=>resolve(req.result||null);req.onerror=()=>reject(req.error)})}
async function tvCall(operation,data={}){
 const response=await fetch('/api/tv/'+operation,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...data,token:tvConnection?.token})});
 const result=await response.json();if(!response.ok)throw Error(result.error||'Falha no comando da TV Box.');return result;
}
function tvReportText(job){
 const result=job.result||{};
 if(result.report){const r=result.report,gb=n=>(Number(n||0)/1073741824).toFixed(2);
  let answer='Diagnóstico de '+(r.model||job.device_id||tvConnection.device_id)+': Android informado '+r.android+', API '+r.sdk+'. Memória livre '+gb(r.memory_free)+' de '+gb(r.memory_total)+' GB. Armazenamento livre '+gb(r.storage_free)+' de '+gb(r.storage_total)+' GB. Root '+(r.root?'disponível':'não disponível')+'. Rede '+(r.network||'não identificada')+'.';
  if(r.storage_free<1073741824)answer+=' Atenção: pouco espaço livre.';
  if(r.memory_free<150*1048576)answer+=' Atenção: pouca memória livre neste momento.';
  if(r.temperature_c)answer+=' Temperatura reportada: '+r.temperature_c+' °C.';
  answer+=' Aplicativos encontrados: '+(r.apps||[]).length+'. O diagnóstico verifica software e dados expostos pelo Android; não testa fisicamente fonte, placa ou conectores.';
  return answer;
 }
 return (result.results||[]).map(r=>r.package+': '+r.message).join('\n')||result.error||('Comando '+job.status+'.');
}
async function tvWait(job,bubble,{speak=true}={}){
 const end=Date.now()+120000;
 while(Date.now()<end){
  const current=await tvCall('job',{id:job.id});
  if(['completed','partial','failed'].includes(current.status)){
   const answer=tvReportText(current);paintResponse(bubble,answer,[],[]);
   if(current.result?.report?.apps){const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent='Aplicativos e pacotes';details.append(summary);const pre=document.createElement('pre');pre.textContent=current.result.report.apps.map(a=>a.label+' — '+a.package+(a.system?' [sistema]':'')).join('\n');details.append(pre);bubble.append(details)}
   history.push({role:'assistant',content:answer});await saveChat();tvPending=null;await tvStore('tv-pending',null);if(speak)await replyByVoice(answer);return {status:current.status,summary:answer};
  }
  bubble.textContent=current.status==='pending'?'Comando enviado ao painel. Aguardando a TV Box conectar...':'A TV Box está executando o comando...';await new Promise(r=>setTimeout(r,2000));
 }
 const message='O comando continua registrado no painel, mas ainda não recebi o resultado. Não foi confirmado como concluído.';bubble.textContent=message;return {status:'pending',summary:message};
}
async function runTVCommand(text,{fromVoice=false}={}){
 if(!tvConnection)throw Error('Vincule a TV Box em TV Box remota.');
 if(send.disabled)throw Error('Aguarde a tarefa atual terminar.');
 send.disabled=true;waitingVoice=true;if(typeof syncRealtimeMicrophone==='function')syncRealtimeMicrophone();
 const bubble=add('assistant','Enviando comando para a TV Box...');
 try{const job=await tvCall('command',{text});tvPending=job;await tvStore('tv-pending',job);return await tvWait(job,bubble,{speak:!fromVoice})}
 catch(error){bubble.textContent=error.message;throw error}
 finally{send.disabled=false;waitingVoice=false;if(typeof syncRealtimeMicrophone==='function')syncRealtimeMicrophone();if(voiceMode)scheduleVoiceListen(500)}
}
async function handleRealtimeTV(call,channel){
 if(realtimeMediaCalls.has(call.call_id))return;realtimeMediaCalls.add(call.call_id);let result;
 try{result=await runTVCommand(JSON.parse(call.arguments||'{}').pedido,{fromVoice:true})}catch(error){result={status:'failed',error:error.message}}
 sendRealtimeEvent(channel,{type:'conversation.item.create',item:{type:'function_call_output',call_id:call.call_id,output:JSON.stringify(result)}});sendRealtimeEvent(channel,{type:'response.create'});
}
function tvIntent(text){
 const value=text.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
 if(/computador|windows|\bpc\b/.test(value))return false;
 return !!tvConnection&&/diagnos|analise|analisar|verifique|desinstal|remov/.test(value)&&(/tv\s*box|\bbox\b|aparelho/.test(value)||workspace.preferences.tvMode===true);
}
const tvPreviousSend=sendMessage;
sendMessage=async function(){
 const text=prompt.value.trim();if(!tvIntent(text))return tvPreviousSend();
 if(send.disabled)return;prompt.value='';add('user',text);history.push({role:'user',content:text});await saveChat();
 try{await runTVCommand(text)}catch(error){notify(error.message)}
};
async function tvMenu(){
 const el=modalContent('TV Box remota',tvConnection?'Vinculada: '+tvConnection.device_id:'No painel da launcher, abra Agente BBLIA e use Vincular esta TV Box à BBLIA do celular.');
 if(!tvConnection)return;
 const toggle=document.createElement('input');toggle.type='checkbox';toggle.checked=workspace.preferences.tvMode===true;toggle.onchange=()=>{workspace.preferences.tvMode=toggle.checked;persist()};const label=document.createElement('label');label.textContent=' Direcionar diagnóstico e desinstalação para esta TV Box';label.prepend(toggle);el.append(label);
 button(el,'Diagnosticar TV Box',async()=>{document.getElementById('modal').close();await runTVCommand('Diagnóstico da TV Box').catch(e=>notify(e.message))});
 if(tvPending)button(el,'Conferir comando pendente',async()=>{document.getElementById('modal').close();await tvWait(tvPending,add('assistant','Conferindo resultado...')).catch(e=>notify(e.message))});
 button(el,'Desvincular deste navegador',async()=>{tvConnection=null;await tvStore('tv-connection',null);workspace.preferences.tvMode=false;await persist();tvMenu()});
}
async function initTV(){
 while(!workspaceReady)await new Promise(r=>setTimeout(r,100));
 tvConnection=await tvRead('tv-connection');tvPending=await tvRead('tv-pending');
 const nav=document.querySelector('.panel'),entry=document.createElement('button');entry.className='navbtn';entry.textContent='📺 TV Box remota';entry.onclick=tvMenu;nav.insertBefore(entry,nav.querySelector('.navbtn'));
 const url=new URL(location.href),code=url.searchParams.get('tv_pair');if(!code)return;
 url.searchParams.delete('tv_pair');window.history.replaceState(null,'',url.pathname+url.search+url.hash);
 try{tvConnection=await tvCall('exchange',{code});await tvStore('tv-connection',tvConnection);workspace.preferences.tvMode=true;await persist();notify('TV Box vinculada. Pode pedir um diagnóstico ou comandar os aplicativos.');tvMenu()}catch(error){notify(error.message)}
}
initTV();
