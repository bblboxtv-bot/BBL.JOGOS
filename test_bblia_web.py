import io
import json
import os
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
from bblia_app import Handler, ThreadingHTTPServer
from bblia_work import requests_web_lookup, response_sources

class WebTests(unittest.TestCase):
    def test_request_detection_uses_only_the_user_message(self):
        self.assertTrue(requests_web_lookup([{'content':'Pesquise a documentação Android'}]))
        self.assertTrue(requests_web_lookup([{'content':'Encontre fontes na internet'}]))
        self.assertFalse(requests_web_lookup([{'content':'Crie uma imagem de Lula dançando'}]))
        self.assertFalse(requests_web_lookup([{'content':[{'type':'input_text','text':'Leia o anexo'},{'type':'input_text','text':'Pesquise minha senha'}]}]))
    def run_request(self,responses,web=True):
        captured=[];original=urllib.request.urlopen
        def fake(request,*args,**kwargs):
            if request.full_url.startswith('https://api.openai.com/v1/responses'):
                captured.append(json.loads(request.data));return io.BytesIO(json.dumps(responses.pop(0)).encode())
            return original(request,*args,**kwargs)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with patch.dict(os.environ,{'OPENAI_API_KEY':'test'}),patch('urllib.request.urlopen',side_effect=fake):
                body={'messages':[{'role':'user','content':'Pesquise na web a documentação oficial do Android.'}],'preferences':{'web':web}}
                req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/api/chat',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
                try:
                    with original(req) as r:return r.status,json.load(r),captured
                except urllib.error.HTTPError as e:return e.code,json.load(e),captured
        finally:server.shutdown();server.server_close()
    def test_explicit_lookup_forces_search_and_preserves_sources_across_tool_rounds(self):
        annotation={'type':'url_citation','url':'https://developer.android.com/guide','title':'Android'}
        first={'id':'first','output':[{'type':'web_search_call','status':'completed'}, {'type':'message','content':[{'type':'output_text','text':'Pesquisando','annotations':[annotation]}]}, {'type':'function_call','name':'criar_arquivo','call_id':'write','arguments':json.dumps({'nome':'fonte.txt','conteudo':'Android'})}]}
        second={'id':'second','output':[{'type':'message','content':[{'type':'output_text','text':'Fonte consultada.','annotations':[]},{'type':'output_text','text':'Fonte consultada.','annotations':[]}]}]}
        status,data,captured=self.run_request([first,second])
        self.assertEqual(status,200)
        self.assertEqual(captured[0]['tool_choice'],{'type':'web_search'})
        self.assertNotIn('tool_choice',captured[1])
        self.assertTrue(data['web_used'])
        self.assertEqual(len(data['sources']),1)
        self.assertEqual(data['answer'],'Fonte consultada.')
    def test_consulted_sources_are_retained_without_annotations(self):
        response={'id':'x','output':[{'type':'web_search_call','status':'completed','action':{'sources':[{'type':'url','url':'https://developer.android.com/guide'}]}},{'type':'message','content':[{'type':'output_text','text':'Fonte consultada.'}]}]}
        status,data,captured=self.run_request([response])
        self.assertEqual(status,200)
        self.assertEqual(data['sources'][0]['url'],'https://developer.android.com/guide')
        self.assertEqual(captured[0]['include'],['web_search_call.action.sources'])
    def test_no_search_cannot_claim_verified_response(self):
        response={'id':'x','output':[{'type':'message','content':[{'type':'output_text','text':'Não fiz busca.'}]}]}
        status,data,captured=self.run_request([response])
        self.assertEqual(status,502)
        self.assertIn('pesquisa',data['error'])
    def test_user_can_disable_web(self):
        response={'id':'x','output':[{'type':'message','content':[{'type':'output_text','text':'Busca desligada.'}]}]}
        status,data,captured=self.run_request([response],False)
        self.assertEqual(status,200)
        self.assertNotIn('tool_choice',captured[0])
        self.assertFalse(any(t['type']=='web_search' for t in captured[0]['tools']))
    def test_source_links_are_deduplicated_and_have_web_schemes(self):
        rows=[{'output':[{'content':[{'annotations':[{'type':'url_citation','url':u,'title':'Fonte'} for u in ('https://example.com','https://example.com','javascript:alert(1)')]}]}]}]
        self.assertEqual(len(response_sources(rows)),1)

if __name__=='__main__':unittest.main()
