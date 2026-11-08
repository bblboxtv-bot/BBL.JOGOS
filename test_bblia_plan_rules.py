"""Regression tests for BBLIA subscription date rules. Run: python -m unittest test_bblia_plan_rules"""
import unittest
from datetime import datetime, timezone
from bblia_plan_rules import expires_at, plan_state, access_allowed

def ts(y,m,d):
    return int(datetime(y,m,d,tzinfo=timezone.utc).timestamp())

class PlanRulesTests(unittest.TestCase):
    def test_new_subscription(self):
        self.assertEqual(expires_at(ts(2026,11,8)),ts(2026,12,8))
    def test_renew_active_from_expiry(self):
        self.assertEqual(expires_at(ts(2026,11,8),ts(2026,12,8)),ts(2027,1,8))
    def test_renew_expired_from_now(self):
        self.assertEqual(expires_at(ts(2026,11,8),ts(2026,10,8)),ts(2026,12,8))
    def test_february_non_leap(self):
        self.assertEqual(expires_at(ts(2027,1,31)),ts(2027,2,28))
    def test_february_leap(self):
        self.assertEqual(expires_at(ts(2028,1,31)),ts(2028,2,29))
    def test_exact_expiry_denied(self):
        self.assertEqual(plan_state(100,100),"expired")
    def test_suspended_denied(self):
        self.assertFalse(access_allowed(50,100,True))
    def test_active_allowed(self):
        self.assertTrue(access_allowed(50,100))
    def test_inactive_denied(self):
        self.assertFalse(access_allowed(50,None))
    def test_invalid_months(self):
        with self.assertRaises(ValueError):
            expires_at(ts(2026,11,8),months=0)

if __name__=="__main__":
    unittest.main()
