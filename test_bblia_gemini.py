import os, unittest
from unittest.mock import patch
import bblia_gemini

class GeminiTests(unittest.TestCase):
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
   return Response()
  with patch.dict(os.environ,{'GEMINI_API_KEY':'fake-test-key'}),patch.object(bblia_gemini.urllib.request,'urlopen',side_effect=mock_open):
   self.assertEqual(bblia_gemini.responder([{'role':'user','content':'Oi'}])['answer'],'Ola!')
if __name__=='__main__':unittest.main()
