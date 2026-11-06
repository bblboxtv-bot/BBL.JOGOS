import base64
import io
import json
import os
import struct
import threading
import time
import unittest
import urllib.request
import urllib.error
import zipfile
from unittest.mock import patch
import bblia_gemini as g
import bblia_agent as agent
from bblia_zip import inspect_zip
from bblia_app import Handler, ThreadingHTTPServer


def upstream(parts, **extra):
    return {'candidates':[{'content':{'role':'model','parts':parts},**extra}]}


class IntegrationTests(unittest.TestCase):
    def test_preferences_memory_and_multimodal_are_sent_to_gemini(self):
        seen=[]
        def request(payload,model):
            seen.append(payload)
            return upstream([{'text':'Claro, gostosão!'}])
        image='data:image/png;base64,'+base64.b64encode(b'image-fixture').decode()
        pdf='data:application/pdf;base64,'+base64.b64encode(b'%PDF-1.7 fixture').decode()
        with patch.object(g,'request',side_effect=request):
            result=g.responder([{'role':'user','content':[{'type':'input_text','text':'Me chame de gostosão.'},
                {'type':'input_image','image_url':image},{'type':'input_file','file_data':pdf}]}],
                preferences={'name':'gostosão','memories':['Minha marca é BBL.BOXTV']},project={'name':'Meu projeto'})
        self.assertEqual(result['answer'],'Claro, gostosão!')
        system=seen[0]['systemInstruction']['parts'][0]['text']
        for term in ('gostosão','BBL.BOXTV','Meu projeto'):self.assertIn(term,system)
        self.assertEqual([p['inlineData']['mimeType'] for p in seen[0]['contents'][0]['parts'][1:]],['image/png','application/pdf'])

    def test_tool_result_and_signature_return_to_gemini(self):
        seen=[]
        def request(payload,model):
            seen.append(json.loads(json.dumps(payload)))
            if len(seen)==1:
                return upstream([{'functionCall':{'name':'criar_arquivo','args':{'nome':'resultado.txt','conteudo':'teste 42'}},'thoughtSignature':'opaque-signature'}])
            return upstream([{'text':'Arquivo pronto.'}])
        with patch.object(g,'request',side_effect=request):
            result=g.responder([{'role':'user','content':'Crie um arquivo.'}])
        self.assertEqual(result['artifacts'][0]['content'],'teste 42')
        self.assertEqual(seen[1]['contents'][1]['parts'][0]['thoughtSignature'],'opaque-signature')
        self.assertEqual(seen[1]['contents'][2]['parts'][0]['functionResponse']['response']['status'],'created')

    def test_search_sources_are_retained(self):
        with patch.object(g,'request',return_value=upstream([{'text':'Fonte consultada.'}],groundingMetadata={'groundingChunks':[{'web':{'uri':'https://developer.android.com','title':'Android'}}]})) as call:
            result=g.responder([{'role':'user','content':'Pesquise na internet a documentação Android.'}])
        self.assertTrue(result['web_used'])
        self.assertEqual(result['sources'][0]['url'],'https://developer.android.com')
        self.assertIn({'google_search':{}},call.call_args.args[0]['tools'])

    def test_default_agent_uses_gemini_and_delivers_without_openai(self):
        answers=[upstream([{'functionCall':{'name':'criar_arquivo','args':{'nome':'teste.txt','conteudo':'42'}}}]),
                 upstream([{'functionCall':{'name':'finalizar_trabalho','args':{'resumo':'Arquivo pronto.','tipo':'codigo','limitacoes':[]}}}])]
        with patch.dict(os.environ,{'GEMINI_API_KEY':'test','OPENAI_API_KEY':''}),patch.object(g,'request',side_effect=answers),patch.object(agent,'request_model') as paid:
            started=agent.start_work({'messages':[{'role':'user','content':'Crie teste.txt com 42.'}],'preferences':{'web':False}})
            for _ in range(200):
                result=agent.get_work(started['id'])
                if result['status']!='processing':break
                time.sleep(.005)
            paid.assert_not_called()
        self.assertEqual(result['status'],'completed',result)
        self.assertEqual(result['artifacts'][0]['content'],'42')

    def test_default_computer_job_calls_real_adapter_without_leaking_token(self):
        seen=[]
        class Computer:
            actions=[]
            def __init__(self,connection):self.connection=connection
            def initialize(self):return self
            def model_tools(self):return [{'type':'function','name':'pc_list_directory','description':'List directory','parameters':{'type':'object','properties':{'path':{'type':'string'}},'required':['path']}}]
            def call(self,name,args):
                self.actions=[{'tool':name,'confirmed':True}]
                seen.append((name,args))
                return {'content':[{'type':'text','text':'[FILE] exemplo.txt'}]}
        answers=[upstream([{'functionCall':{'name':'pc_list_directory','args':{'path':'C:\\Users\\Jorge\\Documents'}}}]),
                 upstream([{'functionCall':{'name':'finalizar_trabalho','args':{'resumo':'Encontrei exemplo.txt.','tipo':'computador','limitacoes':[]}}}])]
        with patch.dict(os.environ,{'GEMINI_API_KEY':'test','OPENAI_API_KEY':''}),patch.object(g,'request',side_effect=answers) as request,patch.object(agent,'CommanderClient',Computer):
            started=agent.start_work({'messages':[{'role':'user','content':'Liste Documentos no meu computador.'}],'use_computer':True,'computer_connection':{'access_token':'secret-owner-token','device_id':'my-pc'}})
            for _ in range(200):
                result=agent.get_work(started['id'])
                if result['status']!='processing':break
                time.sleep(.005)
            self.assertNotIn('secret-owner-token',str(request.call_args_list))
        self.assertEqual(result['status'],'completed',result)
        self.assertEqual(seen[0][0],'list_directory')
        self.assertNotIn('secret-owner-token',json.dumps(result))

    def test_apk_request_explains_missing_compiler_instead_of_text_only_refusal(self):
        with self.assertRaisesRegex(agent.WorkError,'Conecte o computador'):
            agent.start_work({'messages':[{'role':'user','content':'Crie um APK para Android.'}]})
        self.assertFalse(agent.requires_apk_delivery({'messages':[{'role':'user','content':'Crie somente o código-fonte de um APK.'}]}))
        with patch.object(g,'request',return_value=upstream([{'functionCall':{'name':'fazer_trabalho','args':{'pedido':'Crie um APK Android de calculadora.'}}}])):
            result=g.responder([{'role':'user','content':'Faça uma calculadora Android.'}])
        self.assertEqual(result['action']['kind'],'work')

    def test_no_default_fallback_when_only_paid_key_exists(self):
        with patch.dict(os.environ,{'GEMINI_API_KEY':'','GOOGLE_API_KEY':'','OPENAI_API_KEY':'paid'}):
            with self.assertRaisesRegex(agent.WorkError,'Nenhum serviço pago'):agent.start_work({'messages':[{'role':'user','content':'Oi'}]})
            with self.assertRaisesRegex(agent.WorkError,'autorização explícita'):agent.start_work({'provider':'openai','messages':[{'role':'user','content':'Oi'}]})


class ZipTests(unittest.TestCase):
    def archive(self,entries):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
            for name,content in entries:archive.writestr(name,content)
        stream.seek(0)
        return stream

    def test_zip_lists_binary_and_reads_code_without_extracting(self):
        result=inspect_zip(self.archive([('src/main.py','print(42)'),('firmware.img',bytes(range(256))*30)]),'projeto.zip')
        report=json.loads(result['data'].split('\n',1)[1])
        self.assertEqual(report['entry_count'],2)
        self.assertEqual(report['text_previews'][0]['content'],'print(42)')
        self.assertEqual(result['type'],'text')
        self.assertIn('Nada foi extraído ou executado',report['scope'])

    def test_zip_traversal_and_bomb_are_not_read(self):
        result=inspect_zip(self.archive([('../outside.py','DANGER'),('bomb.txt','A'*900000),('ok.txt','hello')]))
        self.assertNotIn('DANGER',result['data'])
        report=json.loads(result['data'].split('\n',1)[1])
        self.assertTrue(report['entries'][0]['suspicious_path'])
        self.assertEqual([t['path'] for t in report['text_previews']],['ok.txt'])
        self.assertTrue(report['warnings'])

    def test_truncated_zip_is_rejected(self):
        with self.assertRaises(ValueError):inspect_zip(io.BytesIO(b'PK\x03\x04bad'))

    def test_http_upload_reaches_existing_attachment_format(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            url='http://127.0.0.1:'+str(server.server_port)
            raw=self.archive([('README.md','Minha marca é BBL.BOXTV')]).getvalue()
            req=urllib.request.Request(url+'/api/zip/analyze',data=raw,headers={'Content-Type':'application/zip','X-Filename':'teste.zip'})
            result=json.load(urllib.request.urlopen(req))
            self.assertIn('BBL.BOXTV',result['attachment']['data'])
            for path,payload in [('/api/chat',{'provider':'openai','messages':[{'role':'user','content':'Oi'}]})]:
                with self.assertRaises(urllib.error.HTTPError) as raised:urllib.request.urlopen(urllib.request.Request(url+path,data=json.dumps(payload).encode()))
                self.assertEqual(raised.exception.code,400)
        finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
