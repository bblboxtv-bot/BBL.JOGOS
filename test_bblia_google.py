import os,unittest,time,json
from unittest.mock import patch
from urllib.parse import urlsplit,parse_qs
import bblia_google as g

class GoogleTests(unittest.TestCase):
 def setUp(self):
  g.SESSIONS.clear()
  self.env=patch.dict(os.environ,{'GOOGLE_CLIENT_ID':'client','GOOGLE_CLIENT_SECRET':'secret','GOOGLE_REDIRECT_URI':'https://bblia-teste.onrender.com/google-callback'});self.env.start()
 def tearDown(self):self.env.stop();g.SESSIONS.clear()
 def begin(self,services=None):
  result,cookie=g.start('',services or ['email','drive']);q=parse_qs(urlsplit(result['url']).query)
  return cookie,q
 def connected(self):
  cookie,q=self.begin()
  with patch.object(g,'token_request',return_value={'access_token':'private','refresh_token':'refresh','scope':' '.join([g.SCOPES['email'],g.SCOPES['drive']]),'expires_in':3600}):
   new=g.callback(cookie,'state='+q['state'][0]+'&code=abc')
  return new
 def test_not_configured(self):
  with patch.dict(os.environ,{'GOOGLE_CLIENT_SECRET':''}):
   self.assertFalse(g.status('')['configured'])
   with self.assertRaises(g.GoogleError):g.start('',['email'])
 def test_pkce_and_cookie(self):
  c,q=self.begin();self.assertEqual(q['code_challenge_method'],['S256'])
  self.assertIn('HttpOnly',c);self.assertIn('Secure',c);self.assertNotIn('secret',q)
 def test_state_and_replay(self):
  c,q=self.begin()
  with self.assertRaises(g.GoogleError):g.callback(c,'state=wrong&code=a')
  new=self.connected();self.assertIsNotNone(g.session(new));self.assertFalse(g.status(c)['connected'])
 def test_browser_isolation_and_no_credentials_in_status(self):
  c=self.connected();self.assertEqual(g.tools(''),[])
  self.assertNotIn('private',json.dumps(g.status(c)));self.assertNotIn('refresh',json.dumps(g.status(c)))
  self.assertEqual({x['name'] for x in g.tools(c)},{'consultar_email','ler_email','buscar_drive','ler_arquivo_drive'})
 def test_session_expiry(self):
  c=self.connected();g.session(c)['expires']=0;self.assertFalse(g.status(c)['connected'])
 def test_permission_denied(self):
  c=self.connected()
  with self.assertRaises(g.GoogleError):g.execute(c,'consultar_agenda',{})
 def test_origin(self):
  for origin in ('','https://evil.example','https://bblia-teste.onrender.com.evil.test'):
   with self.assertRaises(g.GoogleError):g.check_origin({'Origin':origin})
  g.check_origin({'Origin':'https://bblia-teste.onrender.com','Host':'bblia-teste.onrender.com'})
 def test_refresh(self):
  c=self.connected();g.session(c)['token_expires']=0
  with patch.object(g,'token_request',return_value={'access_token':'renewed','expires_in':3600}) as p:
   self.assertEqual(g.access(c,'email'),'renewed');self.assertEqual(p.call_args.args[0]['grant_type'],'refresh_token')
 def test_query_encoding_and_projection(self):
  c=self.connected()
  with patch.object(g,'api',return_value={'files':[{'id':'a','name':'a'}]}) as p:
   self.assertEqual(g.execute(c,'buscar_drive',{'consulta':"a' or trashed=true"})['arquivos'][0]['id'],'a')
   self.assertIn("a\\'",p.call_args.args[3]['q'])
 def test_disconnect_even_when_revocation_fails(self):
  c=self.connected()
  with patch.object(g,'urlopen',side_effect=OSError):result,_=g.disconnect(c)
  self.assertTrue(result['disconnected']);self.assertFalse(result['revoked']);self.assertFalse(g.status(c)['connected'])
 def test_replay_after_success(self):
  c,q=self.begin()
  with patch.object(g,'token_request',return_value={'access_token':'t','scope':g.SCOPES['email']}):g.callback(c,'state='+q['state'][0]+'&code=a')
  with self.assertRaises(g.GoogleError):g.callback(c,'state='+q['state'][0]+'&code=a')
 def test_invalid_services_and_file_path(self):
  for v in (None,[],['other'],'email'):
   with self.assertRaises(g.GoogleError):g.start('',v)
  with self.assertRaises(g.GoogleError):g.execute(self.connected(),'ler_arquivo_drive',{'id':'../x'})

if __name__=='__main__':unittest.main()
