import unittest
from pathlib import Path

class LoginScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html=(Path(__file__).resolve().parent.parent/"bblia_login_isolado.html").read_text(encoding="utf-8")
    def test_only_three_provider_buttons(self):
        self.assertIn('id="google"',self.html)
        self.assertIn('id="facebook"',self.html)
        self.assertIn('id="phone"',self.html)
        self.assertNotIn('type="password"',self.html)
        self.assertNotIn('type="email"',self.html)
    def test_accessibility(self):
        self.assertIn('aria-live="polite"',self.html)
        self.assertIn('aria-expanded="false"',self.html)
        self.assertIn('autocomplete="one-time-code"',self.html)
    def test_real_routes_not_demo(self):
        self.assertIn('/api/account/start',self.html)
        self.assertIn('/api/auth/facebook/start',self.html)
        self.assertIn('/api/auth/phone/request',self.html)
        self.assertIn('/api/auth/phone/verify',self.html)
        self.assertNotIn('onclick="demo()"',self.html)
    def test_no_secret_in_html(self):
        self.assertNotIn('BBLIA_FACEBOOK_APP_SECRET',self.html)
        self.assertNotIn('BBLIA_OTP_SECRET',self.html)

if __name__=="__main__":
    unittest.main()
