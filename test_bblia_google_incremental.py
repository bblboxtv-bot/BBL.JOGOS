import os, unittest
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs
import bblia_google as g

class IncrementalConsentTests(unittest.TestCase):
 def setUp(self):
  g.SESSIONS.clear()
  self.env=patch.dict(os.environ,{'GOOGLE_CLIENT_ID':'client','GOOGLE_CLIENT_SECRET':'secret','GOOGLE_REDIRECT_URI':'https://bblia-stage6-validacao.onrender.com/google-callback'})
  self.env.start()
  self.durable=patch.object(g.durable,'enabled',return_value=False)
  self.durable.start()
  self.save=patch.object(g.durable,'save',return_value=None);self.save.start()
  self.delete=patch.object(g.durable,'delete',return_value=None);self.delete.start()
 def tearDown(self):
  self.delete.stop();self.save.stop();self.durable.stop();self.env.stop();g.SESSIONS.clear()
 def authorize(self,cookie,services,scopes,identity='google-user-1',refresh=''):
  result,temporary=g.start(cookie,services)
  query=parse_qs(urlsplit(result['url']).query)
  with patch.object(g,'token_request',return_value={'access_token':'access-new','refresh_token':refresh,'scope':' '.join(scopes),'expires_in':3600}),patch.object(g,'request_json',return_value={'sub':identity,'email':'user@example.com','email_verified':True}):
   new=g.callback(temporary,'state='+query['state'][0]+'&code=example')
  return new
 def test_incremental_consent_preserves_identity_and_services(self):
  first=self.authorize('', ['login','sync'],['openid',g.SCOPES['sync']],'google-user-1','refresh-old')
  self.assertTrue(g.status(first)['connected'])
  g.save_services(first,['login','sync'])
  second=self.authorize(first,['login','sync','calendar','drive'],['openid',g.SCOPES['sync'],g.SCOPES['calendar'],g.SCOPES['drive']])
  sess=g.session(second)
  self.assertEqual(sess['user']['id'],'google-user-1')
  self.assertEqual(sess['selected_services'],['login','sync'])
  self.assertEqual(sess['refresh'],'refresh-old')
  self.assertEqual(set(g.save_services(second,['login','sync','calendar','drive'])['services']),{'login','sync','calendar','drive'})
 def test_reject_switching_google_account(self):
  first=self.authorize('', ['login','sync'],['openid',g.SCOPES['sync']])
  with self.assertRaisesRegex(g.GoogleError,'outra conta Google'):
   self.authorize(first,['login','sync','calendar'],['openid',g.SCOPES['sync'],g.SCOPES['calendar']],identity='different-user')
 def test_incremental_consent_requires_verified_identity(self):
  first=self.authorize('', ['login','sync'],['openid',g.SCOPES['sync']])
  result,temporary=g.start(first,['calendar'])
  query=parse_qs(urlsplit(result['url']).query)
  self.assertIn('openid',query['scope'][0].split())
  with patch.object(g,'token_request',return_value={'access_token':'access-new','scope':g.SCOPES['calendar'],'expires_in':3600}):
   with self.assertRaisesRegex(g.GoogleError,'não confirmou a identidade'):
    g.callback(temporary,'state='+query['state'][0]+'&code=example')
 def test_missing_scope_not_saved(self):
  first=self.authorize('', ['login','sync'],['openid',g.SCOPES['sync']])
  with self.assertRaises(g.GoogleError) as err:g.save_services(first,['login','sync','calendar'])
  self.assertEqual(err.exception.status,409)

if __name__=='__main__':unittest.main()
