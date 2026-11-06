import io, json, os, unittest, urllib.error
from unittest.mock import patch
import bblia_gemini

class GeminiTests(unittest.TestCase):
 def test_voice_mode_requests_direct_answers_without_shortening_tasks(self):
  voice=bblia_gemini.instructions({'conversation_mode':'voice'})
  self.assertIn('uma a três frases',voice)
  self.assertIn('cumpra o pedido inteiro',voice)
  self.assertNotIn('Conversa por voz ativa',bblia_gemini.instructions({}))
 def test_missing_key(self):
  with patch.dict(os.environ, {'GEMINI_API_KEY':''}):
   with self.assertRaisesRegex(bblia_gemini.GeminiError,'não configurado'):
    bblia_gemini.responder([{'role':'user','content':'Oi'}])
 def test_chat_payload(self):
  class Response:
   def __enter__(self):return self
   def __exit__(self,*args):return False
   def read(self):return b'{"candidates":[{"content":{"parts":[{"text":"Ola!"}]}}]}'
  def mock_open(req,timeout):
   self.assertIn(b'"role": "user"',req.data)
   self.assertIn(b'"text": "Oi"',req.data)
   self.assertIn('português brasileiro',json.loads(req.data)['systemInstruction']['parts'][0]['text'])
   return Response()
  with patch.dict(os.environ,{'GEMINI_API_KEY':'fake-test-key'}),patch.object(bblia_gemini.urllib.request,'urlopen',side_effect=mock_open):
   self.assertEqual(bblia_gemini.responder([{'role':'user','content':'Oi'}])['answer'],'Ola!')
 def test_temporary_failure_retries_once(self):
  response=io.BytesIO(b'{"candidates":[{"content":{"parts":[{"text":"Quatro."}]}}]}')
  temporary=urllib.error.HTTPError('https://provider',503,'busy',{},None)
  with patch.dict(os.environ,{'GEMINI_API_KEY':'fake'}),patch.object(bblia_gemini.urllib.request,'urlopen',side_effect=[temporary,response]) as request,patch.object(bblia_gemini.time,'sleep'):
   self.assertEqual(bblia_gemini.responder([{'role':'user','content':'2+2?'}])['answer'],'Quatro.')
   self.assertEqual(request.call_count,2)
 def test_quota_does_not_retry_or_fallback(self):
  limited=urllib.error.HTTPError('https://provider',429,'quota',{},None)
  with patch.dict(os.environ,{'GEMINI_API_KEY':'fake'}),patch.object(bblia_gemini.urllib.request,'urlopen',side_effect=limited) as request:
   with self.assertRaisesRegex(bblia_gemini.GeminiError,'Limite gratuito'):bblia_gemini.responder([{'role':'user','content':'Oi'}])
   self.assertEqual(request.call_count,1)
if __name__=='__main__':unittest.main()

