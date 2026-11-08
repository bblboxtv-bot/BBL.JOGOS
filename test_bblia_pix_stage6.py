"""Mock Mercado Pago verification; never charges real money."""
import os,unittest,tempfile
from unittest.mock import patch
from pathlib import Path
class PixStage6Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.old=os.environ.get('BBLIA_CREDITS_DB')
  os.environ['BBLIA_CREDITS_DB']=str(Path(self.tmp.name)/'credits.sqlite3')
  import bblia_wallet as wallet
  wallet.DB=Path(os.environ['BBLIA_CREDITS_DB'])
  import bblia_pix as pix
  self.wallet=wallet;self.pix=pix
 def tearDown(self):
  if self.old is None:os.environ.pop('BBLIA_CREDITS_DB',None)
  else:os.environ['BBLIA_CREDITS_DB']=self.old
  self.tmp.cleanup()
 def test_missing_provider_token_fails_closed(self):
  with patch.dict(os.environ,{'BBLIA_MP_ACCESS_TOKEN':''}):
   with self.assertRaises(self.wallet.WalletError) as ctx:self.pix.create_pix('user','test@example.com',1000)
   self.assertEqual(ctx.exception.status,503)
 def test_verified_pix_and_duplicate_webhook(self):
  order=self.wallet.create_order('user',1000)
  self.wallet.provider_link(order['order_id'],'12345')
  payment={'id':12345,'external_reference':order['order_id'],'currency_id':'BRL','transaction_amount':10.0,'status':'approved'}
  with patch.object(self.pix,'_request',return_value=payment):
   self.assertTrue(self.pix.reconcile('12345')['credited'])
   self.assertFalse(self.pix.reconcile('12345')['credited'])
  self.assertEqual(self.wallet.balance('user')['balance'],100)
 def test_wrong_amount_does_not_credit(self):
  order=self.wallet.create_order('user2',1000)
  self.wallet.provider_link(order['order_id'],'12346')
  payment={'id':12346,'external_reference':order['order_id'],'currency_id':'BRL','transaction_amount':1.0,'status':'approved'}
  with patch.object(self.pix,'_request',return_value=payment):
   with self.assertRaises(self.wallet.WalletError) as ctx:self.pix.reconcile('12346')
   self.assertEqual(ctx.exception.status,409)
  self.assertEqual(self.wallet.balance('user2')['balance'],0)
if __name__=='__main__':unittest.main()
