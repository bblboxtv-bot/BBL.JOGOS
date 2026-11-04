import base64
import io
import json
import os
import threading
import unittest
import urllib.request
from unittest.mock import patch
from bblia_work import prepare_messages, execute_work_tool
from bblia_app import Handler, ThreadingHTTPServer


class WorkbenchTests(unittest.TestCase):
    def test_multimodal_inputs_and_rejection(self):
        pdf = 'data:application/pdf;base64,'+base64.b64encode(b'%PDF-1.7 test').decode()
        result=prepare_messages({'messages':[{'role':'user','content':'Analise'}], 'attachments':[{'name':'a.pdf','type':'pdf','data':pdf}]})
        self.assertEqual(result[-1]['content'][1]['type'],'input_file')
        with self.assertRaises(ValueError):
            prepare_messages({'messages':[{'role':'user','content':'x'}],'attachments':[{'type':'image','data':'http://localhost/private'}]})

    def test_file_tool_does_not_write_to_server(self):
        files=[]
        result=execute_work_tool('criar_arquivo',{'nome':'../../MainActivity.kt','conteudo':'class MainActivity'},files)
        self.assertEqual(files[0]['name'],'MainActivity.kt')
        self.assertFalse(result['executed'])

    def test_four_chat_requests_have_no_daily_limit_and_tools_deliver(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url='http://127.0.0.1:'+str(server.server_port)
        original=urllib.request.urlopen
        payloads=[]
        def fake(request,*args,**kwargs):
            target=request if isinstance(request,str) else request.full_url
            if target.startswith('https://api.openai.com/v1/responses'):
                body=json.loads(request.data);payloads.append(body)
                if 'previous_response_id' not in body:
                    data={'id':'test','output':[{'type':'function_call','name':'criar_arquivo','call_id':'file1','arguments':json.dumps({'nome':'MainActivity.kt','conteudo':'class MainActivity'})}]}
                else:
                    data={'id':'answer','output':[{'content':[{'type':'output_text','text':'Arquivo criado.'}]}]}
                return io.BytesIO(json.dumps(data).encode())
            return original(request,*args,**kwargs)
        try:
            with patch.dict(os.environ,{'OPENAI_API_KEY':'test'}),patch('urllib.request.urlopen',side_effect=fake):
                for _ in range(4):
                    request=urllib.request.Request(url+'/api/chat',data=json.dumps({'messages':[{'role':'user','content':'Crie código'}],'preferences':{'web':False},'project':{'name':'BBL Launcher','instructions':'Android TV'}}).encode(),headers={'Content-Type':'application/json'})
                    data=json.load(urllib.request.urlopen(request))
                    self.assertEqual(data['artifacts'][0]['name'],'MainActivity.kt')
                self.assertEqual(json.load(urllib.request.urlopen(url+'/api/integrations'))['chat_daily_limit'],None)
                self.assertIn('Android TV',payloads[0]['instructions'])
                self.assertNotIn('web_search_preview',[t['type'] for t in payloads[0]['tools']])
        finally:
            server.shutdown();server.server_close()


if __name__=='__main__': unittest.main()
