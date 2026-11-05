import json
import os
import time
import unittest
from unittest.mock import patch
import bblia_agent as agent
from bblia_self import list_sources, read_source, validate_changes

class SelfTests(unittest.TestCase):
    def test_deployed_source_and_path_boundaries(self):
        source=read_source('bblia_work.js')
        self.assertIn('function chooseFiles',source['content'])
        self.assertEqual(len(source['sha256']),64)
        self.assertFalse(list_sources()['publication_connected'])
        for name in ('../bblia_work.js','.env','/etc/passwd','OPENAI_API_KEY'):
            with self.assertRaises(ValueError):read_source(name)
    def test_unchanged_and_invalid_python_cannot_finish(self):
        original=read_source('bblia_work.py')
        report=validate_changes({'bblia_work.py':original['content']},{'bblia_work.py':original},agent.validate_files)
        self.assertFalse(report['ok'])
        report=validate_changes({'bblia_work.py':'def broken('},{'bblia_work.py':original},agent.validate_files)
        self.assertFalse(report['ok'])
        self.assertTrue(any('bblia_work.py' in s for s in report['errors']))
    def test_self_improvement_reads_original_and_delivers_without_deployment(self):
        seen=[]
        source=read_source('bblia_work.js')
        def result(index,calls):
            return {'id':'r'+str(index),'output':[{'type':'function_call','name':n,'call_id':n+str(index),'arguments':json.dumps(a)} for n,a in calls]}
        def model(payload,key):
            seen.append(payload)
            if len(seen)==1:
                self.assertIn('ler_codigo_bblia',[t.get('name') for t in payload['tools']])
                self.assertFalse(any((t.get('name') or '').startswith('pc_') for t in payload['tools']))
                return result(1,[('ler_codigo_bblia',{'nome':'bblia_work.js'})])
            if len(seen)==2:
                self.assertIn(source['sha256'],json.dumps(payload))
                return result(2,[('editar_codigo_bblia',{'nome':'bblia_work.js','trecho_atual':"'use strict';",'trecho_novo':"'use strict';\n// test change"})])
            return result(3,[('finalizar_trabalho',{'resumo':'Melhoria preparada.','tipo':'codigo','limitacoes':[]})])
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test'}),patch.object(agent,'request_model',side_effect=model):
            job=agent.start_work({'messages':[{'role':'user','content':'Melhore a própria BBLIA'}], 'self_improvement':True,'use_computer':True})
            for _ in range(200):
                data=agent.get_work(job['id'])
                if data['status'] not in ('processing','cancelling'):break
                time.sleep(.01)
        self.assertEqual(data['status'],'completed',data)
        self.assertTrue(data['self_improvement'])
        self.assertEqual(data['publication'],'not_published')
        self.assertEqual(data['validation']['base_hashes']['bblia_work.js'],source['sha256'])
        self.assertEqual(data['artifacts'][0]['name'],'bblia_work.js')
        self.assertTrue(any('publicação' in item for item in data['limitations']))
        self.assertEqual(read_source('bblia_work.js')['sha256'],source['sha256'])

if __name__=='__main__':unittest.main()
