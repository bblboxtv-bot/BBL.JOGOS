import unittest,os,json,time
from unittest.mock import patch
import bblia_runtime as r
import bblia_agent as a

class RuntimeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  r.prepare()
  if r.status()['state']!='ready':raise RuntimeError('Runtime preparation failed; tests must execute for real')
 def runjs(self,code,test):
  return r.execute({'logic.js':code,'tests.js':test},{'arquivos':['logic.js'],'teste':'tests.js'})
 def test_success(self):
  v=self.runjs('function total(items){return items.reduce((n,i)=>n+i.price*i.qty,0)}',"test('total em centavos',()=>assert.equal(total([{price:3500,qty:2}]),7000));test('carrinho vazio',()=>assert.equal(total([]),0))")
  self.assertTrue(v['ok']);self.assertEqual(v['passed'],2);self.assertTrue(v['executed'])
 def test_wrong_result_is_failure(self):
  v=self.runjs('function add(a,b){return a-b}',"test('soma',()=>assert.equal(add(2,3),5))")
  self.assertFalse(v['ok']);self.assertEqual(v['failed'],1)
 def test_empty_suite_not_success(self):self.assertFalse(self.runjs('const x=1;','')['ok'])
 def test_syntax_and_runtime_errors(self):
  self.assertFalse(self.runjs('function {','')['ok'])
  self.assertFalse(self.runjs("throw Error('falha real')",'')['ok'])
 def test_timeout_then_recovery(self):
  began=time.monotonic();v=self.runjs('while(true){}','');self.assertFalse(v['ok']);self.assertLess(time.monotonic()-began,5)
  self.assertTrue(self.runjs('',"test('recuperado',()=>assert(true))")['ok'])
 def test_memory_bound(self):
  v=self.runjs('const list=[];while(true) list.push(new Array(100000).fill(1));','');self.assertFalse(v['ok'])
 def test_no_host_bindings_or_secrets(self):
  code="test('sem acesso ao hospedeiro',()=>{for(const name of ['process','require','fetch','XMLHttpRequest','document','std','os','Deno','Bun','Python'])assert.equal(typeof globalThis[name],'undefined')})"
  with patch.dict(os.environ,{'OPENAI_API_KEY':'MUST_NOT_LEAK','GOOGLE_CLIENT_SECRET':'MUST_NOT_LEAK'}):v=self.runjs('',code)
  self.assertTrue(v['ok']);self.assertNotIn('MUST_NOT_LEAK',json.dumps(v))
 def test_context_does_not_leak_between_runs(self):
  self.runjs('globalThis.hidden=123',"test('um',()=>assert(true))")
  self.assertTrue(self.runjs('',"test('isolado',()=>assert.equal(typeof hidden,'undefined'))")['ok'])
 def test_invalid_inputs_and_unavailable(self):
  self.assertFalse(r.execute({}, {'arquivos':[{}],'teste':'t.js'})['ok'])
  with patch.dict(r.STATE,{'state':'unavailable'}):self.assertFalse(self.runjs('',"test('x',()=>assert(true))")['executed'])
 def test_changed_project_invalidates_report(self):
  files={'logic.js':'function add(a,b){return a+b}','test.js':"test('soma',()=>assert.equal(add(2,3),5))"}
  v=r.execute(files,{'arquivos':['logic.js'],'teste':'test.js'});files['logic.js']='function add(a,b){return 0}'
  self.assertNotEqual(v['project_hash'],r.fingerprint(files))
 def test_agent_repairs_and_retests_actual_logic(self):
  seen=[];answers=[]
  def response(i,calls):return {'id':str(i),'output':[{'type':'function_call','call_id':str(i)+'-'+str(n),'name':name,'arguments':json.dumps(args)} for n,(name,args) in enumerate(calls)]}
  finish={'resumo':'Calculadora criada.','tipo':'web','limitacoes':['Interface não testada visualmente.']}
  files={'index.html':'<html><script src="logic.js"></script></html>','logic.js':'function add(a,b){return a-b}','tests.js':"test('soma correta',()=>assert.equal(add(2,3),5))"}
  tests={'arquivos':['logic.js'],'teste':'tests.js'}
  answers=[response(1,[('testar_javascript',tests),('finalizar_trabalho',finish)]),response(2,[('criar_arquivo',{'nome':'logic.js','conteudo':'function add(a,b){return a+b}'}),('testar_javascript',tests),('finalizar_trabalho',finish)])]
  def model(payload,key):seen.append(payload);return answers.pop(0)
  with patch.dict(os.environ,{'OPENAI_API_KEY':'not-exposed'}),patch.object(a,'request_model',side_effect=model):
   started=a.start_work({'messages':[{'role':'user','content':'Corrija a soma e teste'}],'files':[{'name':k,'content':v} for k,v in files.items()]})
   for _ in range(100):
    result=a.get_work(started['id'])
    if result['status'] not in ('processing','cancelling'):break
    time.sleep(.05)
  self.assertEqual(result['status'],'completed');self.assertEqual(result['runtime_tests']['passed'],1)
  self.assertTrue(result['validation']['runtime_tested']);self.assertNotIn('not-exposed',json.dumps(result))
  outputs=[json.loads(x['output']) for x in seen[1]['input']]
  self.assertTrue(any(x.get('executed') and not x['ok'] for x in outputs))

if __name__=='__main__':unittest.main()
