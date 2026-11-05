import unittest,threading,json,http.client
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import bblia_app as app
import bblia_google as g

class HTTPTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
  threading.Thread(target=cls.server.serve_forever,daemon=True).start()
 @classmethod
 def tearDownClass(cls):cls.server.shutdown();cls.server.server_close()
 def request(self,method,path,data=None,headers=None):
  c=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
  c.request(method,path,body=json.dumps(data) if data is not None else None,headers=headers or {})
  r=c.getresponse();body=r.read();status=r.status;h=dict(r.getheaders());c.close();return status,h,body
 def test_status_does_not_expose_secrets(self):
  code,h,b=self.request('GET','/api/google/status');self.assertEqual(code,200);self.assertFalse(json.loads(b)['connected']);self.assertEqual(h['Cache-Control'],'no-store')
 def test_cross_origin_rejected(self):
  code,_,_=self.request('POST','/api/google/start',{'services':['email']},{'Origin':'https://evil.test'})
  self.assertEqual(code,403)
 def test_configured_start_and_real_callback_routing(self):
  with patch.dict('os.environ',{'GOOGLE_CLIENT_ID':'client','GOOGLE_CLIENT_SECRET':'secret'}):
   code,h,b=self.request('POST','/api/google/start',{'services':['email']},{'Origin':'https://bblia-teste.onrender.com'})
  self.assertEqual(code,200);self.assertIn('HttpOnly',h['Set-Cookie']);self.assertIn('accounts.google.com',json.loads(b)['url'])
  code,_,b=self.request('GET','/google-callback?state=bad&code=secret')
  self.assertEqual(code,403);self.assertNotIn(b'secret',b)
 def test_unauthenticated_tool_rejected(self):
  code,_,_=self.request('POST','/api/google/query',{'tool':'consultar_email','args':{}},{'Origin':'https://bblia-teste.onrender.com'})
  self.assertEqual(code,401)
 def test_integrations_are_not_marked_connected(self):
  code,_,b=self.request('GET','/api/integrations');self.assertEqual(code,200)
  self.assertNotEqual(next(x for x in json.loads(b)['items'] if x['id']=='accounts')['state'],'connected')
 def test_disconnect_rejects_get(self):
  code,_,_=self.request('GET','/api/google/disconnect');self.assertEqual(code,404)
if __name__=='__main__':unittest.main()
