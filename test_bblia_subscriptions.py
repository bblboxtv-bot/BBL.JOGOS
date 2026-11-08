"""Isolated subscription database regression tests."""
import os,tempfile,unittest
from datetime import datetime,timezone
from unittest.mock import patch
import bblia_subscriptions as subs

def ts(y,m,d):
    return int(datetime(y,m,d,tzinfo=timezone.utc).timestamp())

class SubscriptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.original=subs.DB
        subs.DB=__import__('pathlib').Path(self.tmp.name)/"test.sqlite3"
    def tearDown(self):
        subs.DB=self.original
        self.tmp.cleanup()
    def test_no_plan(self):
        self.assertEqual(subs.status("u",ts(2026,11,8))["state"],"inactive")
    def test_purchase(self):
        r=subs.renew("u","normal",now=ts(2026,11,8))
        self.assertEqual(r["expires_at"],ts(2026,12,8))
    def test_renew_before_expiry(self):
        subs.renew("u","normal",now=ts(2026,11,8))
        r=subs.renew("u","normal",now=ts(2026,11,10))
        self.assertEqual(r["expires_at"],ts(2027,1,8))
    def test_expired(self):
        subs.renew("u","normal",now=ts(2026,11,8))
        self.assertEqual(subs.status("u",ts(2026,12,8))["state"],"expired")
    def test_suspension(self):
        subs.renew("u","normal",now=ts(2026,11,8))
        self.assertTrue(subs.suspend("u"))
        self.assertEqual(subs.status("u",ts(2026,11,9))["state"],"blocked")
    def test_invalid_tier(self):
        with self.assertRaises(ValueError):
            subs.renew("u","ilimitado",now=ts(2026,11,8))
    def test_no_unsuspend_on_renew(self):
        subs.renew("u","normal",now=ts(2026,11,8))
        subs.suspend("u")
        self.assertEqual(subs.renew("u","normal",now=ts(2026,11,9))["state"],"blocked")

if __name__=="__main__":unittest.main()
