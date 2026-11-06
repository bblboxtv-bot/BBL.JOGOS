import ast,io,json,os,types,unittest,urllib.request,urllib.error
from unittest.mock import patch
from pathlib import Path

source=ast.parse(Path(__file__).with_name('bblia_app.py').read_text())
handler=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='Handler')
method=next(n for n in handler.body if isinstance(n,ast.FunctionDef) and n.name=='realtime_token')
namespace={'os':os,'json':json,'urllib':__import__('urllib'),'CREATIVE_GUIDANCE':''}
exec(compile(ast.Module(body=[method],type_ignores=[]),'realtime_token','exec'),namespace)

class FakeHandler:
 realtime_token=namespace['realtime_token']
 def __init__(self,payload):
  body=json.dumps(payload).encode();self.headers={'Content-Length':str(len(body))};self.rfile=io.BytesIO(body)
 def reply(self,status,value):self.status,self.value=status,value

class Tests(unittest.TestCase):
 @patch.dict(os.environ,{'OPENAI_API_KEY':'test-only'})
 def test_interruptions_and_ephemeral_token(self):
  captured=[]
  def request(req,timeout):
   captured.append(json.loads(req.data));return io.BytesIO(b'{"value":"ephemeral-test"}')
  with patch('urllib.request.urlopen',request):
   h=FakeHandler({'paid_authorized':True,'context':'Cliente Rodrigo'});h.realtime_token()
  self.assertEqual(h.status,200)
  session=captured[0]['session'];vad=session['audio']['input']['turn_detection']
  self.assertTrue(vad['interrupt_response']);self.assertLess(vad['silence_duration_ms'],1000)
  self.assertEqual(session['audio']['output']['voice'],'marin')
  self.assertIn('Cliente Rodrigo',session['instructions'])
  self.assertEqual(h.value['token'],'ephemeral-test')
 @patch.dict(os.environ,{'OPENAI_API_KEY':'test-only'})
 def test_missing_authorization_never_calls_api(self):
  with patch('urllib.request.urlopen') as call:
   h=FakeHandler({});h.realtime_token();self.assertEqual(h.status,400);call.assert_not_called()

if __name__=='__main__':unittest.main()
