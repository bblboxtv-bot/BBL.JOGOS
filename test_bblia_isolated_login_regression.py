"""Regression tests for isolated BBLIA login; no external credentials required."""
import os
import tempfile
import unittest
from unittest.mock import patch
import bblia_session_sqlite as store
import bblia_auth_http_stage as auth
import bblia_facebook_auth as facebook
import bblia_phone_auth as phone
import bblia_google_isolated_bridge as google

class IsolatedLoginRegression(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.temp.name, "sessions.sqlite3")
        store.initialize(self.db)
    def tearDown(self):
        self.temp.cleanup()
    def test_google_session_logout_and_reopen(self):
        data, cookie = auth.login_verified(self.db, "google", "google:verified-123", now=100)
        self.assertTrue(data["authenticated"])
        header = cookie.split(";", 1)[0]
        self.assertTrue(auth.status(self.db, header, now=101)["authenticated"])
        self.assertEqual(auth.status(self.db, header, now=101)["subject"], "google:verified-123")
        self.assertFalse(auth.status(self.db, "", now=101)["authenticated"])
        auth.logout(self.db, header)
        self.assertFalse(auth.status(self.db, header, now=102)["authenticated"])
    def test_provider_identity_isolation(self):
        for provider in ("google", "facebook", "phone"):
            subject = provider + ":unique-user"
            _, cookie = auth.login_verified(self.db, provider, subject, now=100)
            result = auth.status(self.db, cookie.split(";",1)[0], now=101)
            self.assertEqual(result["provider"], provider)
            self.assertEqual(result["subject"], subject)
    def test_expiry(self):
        _, cookie = auth.login_verified(self.db, "phone", "phone:+5521999999999", now=100)
        self.assertFalse(auth.status(self.db, cookie.split(";",1)[0], now=100+store.TTL)["authenticated"])
    def test_unverified_identity_rejected(self):
        with self.assertRaises(store.DurableSessionError):
            auth.login_verified(self.db, "google", "facebook:wrong")
    def test_facebook_missing_credentials_fail_closed(self):
        with patch.dict(os.environ, {"BBLIA_FACEBOOK_APP_ID":"", "BBLIA_FACEBOOK_APP_SECRET":""}):
            with self.assertRaises(facebook.FacebookAuthError):
                facebook.configuration()
    def test_phone_missing_secret_fail_closed(self):
        with patch.dict(os.environ, {"BBLIA_OTP_SECRET":""}):
            with self.assertRaises(phone.PhoneAuthError):
                phone.request_code("+5521999999999", lambda a,b: None)
    def test_google_missing_credentials_fail_closed(self):
        with patch.dict(os.environ, {"BBLIA_ISOLATED_GOOGLE_OAUTH_ENABLED":"0"}):
            with self.assertRaises(google.IsolatedGoogleError):
                google.require_isolated_config()

if __name__ == "__main__":
    unittest.main()
