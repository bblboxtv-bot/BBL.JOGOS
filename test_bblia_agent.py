import base64
import json
import os
import threading
import time
import unittest
from unittest.mock import patch

import bblia_agent as agent


def response(number, calls):
    return {'id': 'response-'+str(number), 'output': [
        {'type': 'function_call', 'name': name, 'call_id': 'call-'+str(number)+'-'+str(i),
         'arguments': json.dumps(args)} for i, (name, args) in enumerate(calls)]}


def finish_args():
    return {'resumo': 'Painel criado com produtos e carrinho.', 'tipo': 'web',
            'limitacoes': ['Pagamentos externos não conectados.']}


class AgentTests(unittest.TestCase):
    def wait(self, job_id):
        for _ in range(200):
            result=agent.get_work(job_id)
            if result['status'] not in ('processing', 'cancelling'):
                return result
            time.sleep(0.005)
        self.fail('worker did not finish')

    def test_reference_build_validation_repair_and_delivery(self):
        seen=[]
        bad='<!doctype html><html><script src="app.js"></script></html>'
        answers=[response(1,[('planejar_trabalho',{'objetivo':'PDV','etapas':['Analisar referência','Construir','Revisar']}),
                             ('criar_arquivo',{'nome':'index.html','conteudo':bad}),
                             ('finalizar_trabalho',finish_args())]),
                 response(2,[('criar_arquivo',{'nome':'app.js','conteudo':'const cart=[];'}),
                             ('validar_projeto',{'tipo':'web'}),('finalizar_trabalho',finish_args())])]
        def model(payload,key):
            seen.append(payload)
            return answers.pop(0)
        image='data:image/png;base64,'+base64.b64encode(b'fixture-image').decode()
        with patch.dict(os.environ,{'OPENAI_API_KEY':'secret'}),patch.object(agent,'request_model',side_effect=model):
            job=agent.start_work({'provider':'openai','paid_authorized':True,'messages':[{'role':'user','content':'Crie um PDV igual à foto'}],
                                 'attachments':[{'name':'PDV.png','type':'image','data':image}],
                                 'preferences':{'web':True}})
            result=self.wait(job['id'])
        self.assertEqual(result['status'],'completed')
        self.assertEqual(len(result['artifacts']),2)
        self.assertTrue(result['validation']['ok'])
        self.assertFalse(result['validation']['runtime_tested'])
        self.assertEqual(seen[0]['input'][0]['content'][1]['type'],'input_image')
        self.assertTrue(any(tool['type']=='web_search_preview' for tool in seen[0]['tools']))
        tool_outputs=[json.loads(item['output']) for item in seen[1]['input']]
        self.assertTrue(any('app.js' in str(item.get('errors',[])) for item in tool_outputs))
        self.assertNotIn('secret',json.dumps(result))

    def test_plan_only_answer_does_not_claim_completion(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'secret'}),patch.object(agent,'request_model',return_value={'id':'plan','output':[]}):
            job=agent.start_work({'provider':'openai','paid_authorized':True,'messages':[{'role':'user','content':'Crie um sistema'}]})
            result=self.wait(job['id'])
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['artifacts'],[])

    def test_file_revisions_preserve_other_files_and_cannot_escape(self):
        files={'index.html':'old','app.js':'unchanged'}
        agent.put_file(files,'index.html','new')
        self.assertEqual(files,{'index.html':'new','app.js':'unchanged'})
        for name in ('../secret','/etc/passwd','C:\\secret','a/../../b'):
            with self.assertRaises(agent.WorkError):
                agent.put_file(files,name,'data')
        report=agent.validate_files({'index.html':'<html><button id="x"></button><button id="x"></button></html>'},'web')
        self.assertFalse(report['ok'])

    def test_cancel_stops_next_model_step_and_preserves_seed(self):
        entered=threading.Event();release=threading.Event()
        def model(payload,key):
            entered.set();release.wait(2)
            return response(1,[('criar_arquivo',{'nome':'new.txt','conteudo':'must not be applied'})])
        with patch.dict(os.environ,{'OPENAI_API_KEY':'secret'}),patch.object(agent,'request_model',side_effect=model):
            job=agent.start_work({'provider':'openai','paid_authorized':True,'messages':[{'role':'user','content':'Continue'}],
                                 'files':[{'name':'seed.txt','content':'preserve'}]})
            self.assertTrue(entered.wait(1))
            self.assertNotIn('artifacts',agent.get_work(job['id']))
            self.assertEqual(agent.cancel_work(job['id'])['status'],'cancelling')
            release.set();result=self.wait(job['id'])
        self.assertEqual(result['status'],'cancelled')
        self.assertEqual(result['artifacts'],[{'name':'seed.txt','content':'preserve'}])

    def test_checkpoint_preserves_files_while_worker_is_still_running(self):
        entered=threading.Event();release=threading.Event();calls=[]
        def model(payload,key):
            calls.append(payload)
            if len(calls)==1:return response(1,[('criar_arquivo',{'nome':'parcial.txt','conteudo':'salvo antes da queda'})])
            entered.set();release.wait(2)
            return response(2,[('finalizar_trabalho',{'tipo':'codigo','resumo':'Pronto','limitacoes':[]})])
        with patch.dict(os.environ,{'OPENAI_API_KEY':'secret'}),patch.object(agent,'request_model',side_effect=model):
            job=agent.start_work({'provider':'openai','paid_authorized':True,'messages':[{'role':'user','content':'Crie um arquivo'}]})
            self.assertTrue(entered.wait(1))
            snapshot=agent.get_work(job['id'])
            self.assertEqual(snapshot['checkpoint']['artifacts'][0]['content'],'salvo antes da queda')
            unchanged=agent.get_work(job['id'],snapshot['checkpoint']['revision'])
            self.assertNotIn('artifacts',unchanged['checkpoint'])
            self.assertNotIn('secret',json.dumps(snapshot))
            release.set();self.wait(job['id'])

    def test_unknown_job_does_not_expose_other_jobs(self):
        with self.assertRaises(agent.WorkError):
            agent.get_work('unknown-id')


if __name__=='__main__':unittest.main()
