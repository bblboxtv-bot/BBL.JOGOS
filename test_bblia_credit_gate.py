"""Regression tests for paid OpenAI credit authorization."""
import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import bblia_wallet as wallet
import bblia_credit_gate as gate

class CreditGateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.old=wallet.DB
        wallet.DB=Path(self.temp.name)/"credits.sqlite3"
        self.env=patch.dict(os.environ,{"BBLIA_COST_CHAT_CREDITS":"2"},clear=False)
        self.env.start()
    def tearDown(self):
        self.env.stop();wallet.DB=self.old;self.temp.cleanup()
    def fund(self):
        with wallet.LOCK:
            c=wallet._db()
            try:
                c.execute("INSERT INTO wallets(user_id,balance) VALUES(?,?)",("alice",5))
            finally:c.close()
    def test_no_consent(self):
        with self.assertRaises(gate.CreditGateError) as e:gate.preflight("alice","chat",False)
        self.assertEqual(e.exception.status,403)
    def test_no_balance(self):
        with self.assertRaises(gate.CreditGateError) as e:gate.preflight("alice","chat",True)
        self.assertEqual(e.exception.status,402)
    def test_successful_debit(self):
        self.fund()
        self.assertTrue(gate.charge("alice","chat","req1",True)["charged"])
        self.assertEqual(wallet.balance("alice")["balance"],3)
    def test_duplicate_is_idempotent(self):
        self.fund()
        gate.charge("alice","chat","req1",True)
        self.assertFalse(gate.charge("alice","chat","req1",True)["charged"])
        self.assertEqual(wallet.balance("alice")["balance"],3)
    def test_insufficient_after_spend(self):
        self.fund()
        gate.charge("alice","chat","req1",True)
        gate.charge("alice","chat","req2",True)
        with self.assertRaises(gate.CreditGateError) as e:gate.charge("alice","chat","req3",True)
        self.assertEqual(e.exception.status,402)
    def test_admin_no_charge(self):
        self.assertFalse(gate.charge("admin","chat","r",True,admin=True)["charged"])
    def test_missing_price_fails_closed(self):
        with patch.dict(os.environ,{"BBLIA_COST_CHAT_CREDITS":""}):
            with self.assertRaises(gate.CreditGateError) as e:gate.preflight("alice","chat",True)
            self.assertEqual(e.exception.status,503)
    def test_refund_restores_balance(self):
        self.fund()
        wallet.spend("alice",2,"chat:failed")
        self.assertTrue(wallet.refund_spend("alice","chat:failed")["refunded"])
        self.assertEqual(wallet.balance("alice")["balance"],5)
    def test_duplicate_refund_no_double_credit(self):
        self.fund()
        wallet.spend("alice",2,"chat:failed")
        wallet.refund_spend("alice","chat:failed")
        self.assertFalse(wallet.refund_spend("alice","chat:failed")["refunded"])
        self.assertEqual(wallet.balance("alice")["balance"],5)
    def test_missing_charge_cannot_mint_credits(self):
        self.fund()
        with self.assertRaises(wallet.WalletError):
            wallet.refund_spend("alice","chat:missing")
        self.assertEqual(wallet.balance("alice")["balance"],5)
    def test_bad_feature(self):
        with self.assertRaises(gate.CreditGateError):gate.preflight("alice","unknown",True)

if __name__=="__main__":unittest.main()
