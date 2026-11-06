import base64,hashlib,io,json,threading,unittest,urllib.request,urllib.error,zipfile,tempfile
from pathlib import Path
from unittest.mock import patch
import bblia_apk_delivery as d
import bblia_agent as a
from bblia_app import Handler,ThreadingHTTPServer

class DeliveryTests(unittest.TestCase):
 def apk(self):
  stream=io.BytesIO()
  with zipfile.ZipFile(stream,'w') as z:z.writestr('AndroidManifest.xml',b'fixture');z.writestr('classes.dex',b'dex fixture')
  return stream.getvalue()
 def test_scoped_one_time_upload_checks_hash_and_returns_real_bytes(self):
  raw=self.apk();digest=hashlib.sha256(raw).hexdigest()
  with tempfile.TemporaryDirectory() as folder,patch.object(d,'ROOT',Path(folder)),patch.object(d,'TICKETS',{}):
   ticket=d.prepare('job1','Aplicativo.apk',digest)
   self.assertEqual(d.artifacts('job1'),[])
   self.assertTrue(d.pending('job1'))
   d.receive(ticket,io.BytesIO(raw),len(raw))
   self.assertEqual(d.pending('job1'),[])
   self.assertEqual(d.artifacts('other'),[])
   artifact=d.artifacts('job1')[0]
   file=d.download(artifact['download_url'].rsplit('/',1)[-1])
   self.assertEqual(Path(file['path']).read_bytes(),raw)
   with self.assertRaises(ValueError):d.receive(ticket,io.BytesIO(raw),len(raw))
 def test_wrong_hash_is_rejected(self):
  raw=self.apk()
  with tempfile.TemporaryDirectory() as folder,patch.object(d,'ROOT',Path(folder)),patch.object(d,'TICKETS',{}):
   ticket=d.prepare('job','App.apk','0'*64)
   with self.assertRaisesRegex(ValueError,'hash'):d.receive(ticket,io.BytesIO(raw),len(raw))
   self.assertEqual(d.artifacts('job'),[])
   self.assertEqual(list(Path(folder).iterdir()),[])
 def test_http_download_uses_attachment_and_correct_bytes(self):
  raw=self.apk();server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
  try:
   with tempfile.TemporaryDirectory() as folder,patch.object(d,'ROOT',Path(folder)),patch.object(d,'TICKETS',{}):
    ticket=d.prepare('job','Teste.apk',hashlib.sha256(raw).hexdigest());base='http://127.0.0.1:'+str(server.server_port)
    request=urllib.request.Request(base+'/api/apk/upload/'+ticket,data=raw)
    with urllib.request.urlopen(request) as response:self.assertTrue(json.load(response)['ok'])
    with urllib.request.urlopen(base+d.artifacts('job')[0]['download_url']) as response:
     self.assertIn('attachment;',response.headers['Content-Disposition']);self.assertEqual(response.read(),raw)
  finally:server.shutdown();server.server_close()
 def test_bad_filename_does_not_create_ticket(self):
  for name in ('../evil.apk','x\r\nHeader.apk','secret.txt','/root.apk'):
   with self.assertRaises(ValueError):d.prepare('job',name,'0'*64)

if __name__=='__main__':unittest.main()
