'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync(process.argv[2],'utf8');
const start=src.indexOf('function realtimeTranscript(event,role,final){');
const end=src.indexOf('\nasync function handleRealtimeEvent(',start);
assert(start>=0&&end>start,'realtimeTranscript function exists');
function run(events,expected){
 const feed={children:[],append(node){node.parentNode=this;this.children.push(node)},insertBefore(node,next){this.children.splice(this.children.indexOf(node),1);this.children.splice(this.children.indexOf(next),0,node)}};
 const ctx={realtimeTranscripts:new Map(),realtimeOrder:new Map(),history:[],feed,saveChat(){},add(role,text){const node={role,textContent:text};feed.append(node);return node}};
 vm.createContext(ctx);vm.runInContext(src.slice(start,end),ctx);
 for(const e of events){if(e.order!==undefined)ctx.realtimeOrder.set(e.id,e.order);ctx.realtimeTranscript({item_id:e.id,transcript:e.text},e.role,true)}
 assert.deepStrictEqual(feed.children.map(n=>n.role+':'+n.textContent),expected);
 assert.deepStrictEqual(Array.from(ctx.history,x=>x.role+':'+x.content),expected);
}
run([{id:'u1',role:'user',text:'pergunta',order:0},{id:'a1',role:'assistant',text:'resposta',order:1}],['user:pergunta','assistant:resposta']);
run([{id:'a1',role:'assistant',text:'resposta',order:1},{id:'u1',role:'user',text:'pergunta',order:0}],['user:pergunta','assistant:resposta']);
run([{id:'u1',role:'user',text:'primeira',order:0},{id:'a1',role:'assistant',text:'resposta 1',order:1},{id:'u2',role:'user',text:'segunda',order:2},{id:'a2',role:'assistant',text:'resposta 2',order:3}],['user:primeira','assistant:resposta 1','user:segunda','assistant:resposta 2']);
console.log('VOICE_ORDER_TESTS_PASS 3/3');
