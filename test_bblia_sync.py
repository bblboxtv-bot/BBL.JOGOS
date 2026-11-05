import unittest,copy,json
from unittest.mock import patch
import bblia_sync as s
import bblia_google as g

class SyncTests(unittest.TestCase):
 def state(self,text='a',updated=1):
  v=s.empty();v['chats']=[{'id':'chat','title':'Conversa','messages':[{'role':'user','content':text}],'updated':updated}];return v
 def test_two_devices_keep_new_chats(self):
  a=self.state();b=self.state('b');b['chats'][0]['id']='other'
  self.assertEqual(len(s.merge([a,b])['chats']),2)
 def test_continuation_no_duplicate(self):
  a=self.state();b=copy.deepcopy(a);b['chats'][0]['messages'].append({'role':'assistant','content':'resposta'});b['chats'][0]['updated']=2
  result=s.merge([a,b]);self.assertEqual(len(result['chats']),1);self.assertEqual(len(result['chats'][0]['messages']),2)
 def test_divergent_edits_preserved_and_idempotent(self):
  a=self.state();b=self.state('outro',2)
  result=s.merge([a,b]);self.assertEqual(len(result['chats']),2)
  again=s.merge([result,a,b]);self.assertEqual({c['id'] for c in result['chats']},{c['id'] for c in again['chats']})
 def test_delete_does_not_resurrect(self):
  a=self.state();b=s.empty();b['deleted']={'chats:chat':3}
  self.assertEqual(s.merge([a,b])['chats'],[])
  self.assertEqual(s.merge([self.state('changed',99),b])['chats'],[])
 def test_preferences_latest(self):
  a=s.empty();a['preferences']={'name':'A'};a['preferencesUpdated']=1
  b=s.empty();b['preferences']={'name':'B'};b['preferencesUpdated']=2
  self.assertEqual(s.merge([b,a])['preferences']['name'],'B')
 def test_credentials_stripped_and_invalid_data_rejected(self):
  a=self.state();a['access_token']='no';a['chats'][0]['computer_connection']={'access_token':'no'};a['preferences']['client_secret']='no'
  self.assertNotIn('access_token',json.dumps(s.validate(a)))
  with self.assertRaises(g.GoogleError):s.validate({'version':1,'chats':'x','projects':[]})
 def test_unknown_account_denied(self):
  with patch.object(g,'session',return_value=None):
   with self.assertRaises(g.GoogleError):s.load('')
  with patch.object(g,'session',return_value={'user':{'id':'a'}}):
   with self.assertRaises(g.GoogleError):s.identity('','b')
 def test_no_drive_permission_denied(self):
  with patch.object(g,'session',return_value={'user':{'id':'a'}}),patch.object(g,'access',side_effect=g.GoogleError('denied',403)):
   with self.assertRaises(g.GoogleError):s.load('')
 def test_remote_write_targets_only_listed_own_snapshot(self):
  user={'id':'a'};file={'id':'listed-id','name':'bblia-workspace-browser123.json'}
  with patch.object(s,'identity',return_value=user),patch.object(s,'snapshots',return_value=[(file,self.state())]),patch.object(s,'drive',return_value={}) as remote:
   result=s.save('cookie',{'account':'a','device':'browser123','workspace':self.state('new',2)})
   self.assertEqual(result['user']['id'],'a');self.assertEqual(remote.call_args.args[1],'files/listed-id?uploadType=media')
 def test_create_uses_private_folder(self):
  with patch.object(s,'identity',return_value={'id':'a'}),patch.object(s,'snapshots',return_value=[]),patch.object(s,'drive',return_value={}) as remote:
   s.save('cookie',{'account':'a','device':'browser123','workspace':self.state()})
   self.assertIn(b'appDataFolder',remote.call_args.args[3]);self.assertTrue(remote.call_args.kwargs['upload'])
 def test_failure_does_not_report_saved(self):
  with patch.object(s,'identity',return_value={'id':'a'}),patch.object(s,'snapshots',side_effect=g.GoogleError('offline',502)):
   with self.assertRaises(g.GoogleError):s.save('',{'account':'a','device':'browser123','workspace':self.state()})
 def test_deterministic_merge(self):
  a=self.state();b=self.state('b',2)
  self.assertEqual(s.merge([a,b]),s.merge([b,a]))
 def test_bad_device_cannot_choose_file_path(self):
  with patch.object(s,'identity',return_value={'id':'a'}):
   with self.assertRaises(g.GoogleError):s.save('',{'account':'a','device':'../file','workspace':self.state()})
 def test_identity_from_google_only(self):
  with patch.dict('os.environ',{'GOOGLE_CLIENT_ID':'client','GOOGLE_CLIENT_SECRET':'secret'}):
   result,cookie=g.start('',['login','sync'])
   from urllib.parse import parse_qs,urlsplit
   state=parse_qs(urlsplit(result['url']).query)['state'][0]
   with patch.object(g,'token_request',return_value={'access_token':'server-token','scope':'openid '+g.SCOPES['sync']}),patch.object(g,'request_json',return_value={'sub':'google-account','email':'example@example.test','email_verified':True}):
    new_cookie=g.callback(cookie,'state='+state+'&code=a')
   self.assertEqual(g.status(new_cookie)['user']['id'],'google-account')
   self.assertIn('sync',g.status(new_cookie)['services'])
   g.SESSIONS.clear()

if __name__=='__main__':unittest.main()
