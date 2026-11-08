"""Run with: python -m unittest test_bblia_stage6.py (test database only)."""
import os, tempfile, unittest, secrets
from pathlib import Path

class Stage6Tests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory()
  self.old={k:os.environ.get(k) for k in ('BBLIA_AUTH_DB','BBLIA_CREDITS_DB','BBLIA_EMAIL_REGISTRATION')}
  os.environ['BBLIA_AUTH_DB']=str(Path(self.temp.name)/'auth.sqlite3')
  os.environ['BBLIA_CREDITS_DB']=str(Path(self.temp.name)/'credits.sqlite3')
  os.environ['BBLIA_EMAIL_REGISTRATION']='disabled'
  import bblia_email_auth as auth
  import bblia_wallet as wallet
  self.auth=auth;self.wallet=wallet
 def tearDown(self):
  for key,val in self.old.items():
   if val is None:os.environ.pop(key,None)
   else:os.environ[key]=val
  self.temp.cleanup()
 def test_registration_disabled(self):
  with self.assertRaises(self.auth.AuthError) as ctx:self.auth.register('a@example.com','longpassword1234','Tester')
  self.assertEqual(ctx.exception.status,503)
 def test_login_and_revocation(self):
  os.environ['BBLIA_EMAIL_REGISTRATION']='enabled'
  email=secrets.token_hex(8)+'@example.com';pw=secrets.token_urlsafe(18)
  self.auth.register(email,pw,'Tester')
  with self.assertRaises(self.auth.AuthError):self.auth.login(email,'wrong')
  _,cookie=self.auth.login(email,pw)
  self.assertEqual(self.auth.session(cookie)['user']['email'],email)
  self.auth.logout(cookie)
  self.assertIsNone(self.auth.session(cookie))
 def test_wallet_idempotency(self):
  user='test:'+secrets.token_hex(8);w=self.wallet
  order=w.create_order(user,1000)
  with self.assertRaises(w.WalletError):w.settle_verified(order['order_id'],'ref',False)
  self.assertTrue(w.settle_verified(order['order_id'],'provider:'+user,True)['credited'])
  self.assertFalse(w.settle_verified(order['order_id'],'provider:'+user,True)['credited'])
  self.assertEqual(w.balance(user)['balance'],100)
  self.assertTrue(w.spend(user,20,user)['charged'])
  self.assertFalse(w.spend(user,20,user)['charged'])
  self.assertEqual(w.balance(user)['balance'],80)
 def test_no_overdraft(self):
  with self.assertRaises(self.wallet.WalletError) as ctx:self.wallet.spend('no-money',1,'test-no-money')
  self.assertEqual(ctx.exception.status,402)

if __name__=='__main__':unittest.main()
