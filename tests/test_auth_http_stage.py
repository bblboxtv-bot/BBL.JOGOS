import tempfile
import unittest
from pathlib import Path
import bblia_auth_http_stage as http
import bblia_session_sqlite as store

class HttpAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "session.db")
        store.initialize(self.path)
    def tearDown(self):
        self.tmp.cleanup()
    def test_login_status_logout(self):
        result, cookie = http.login_verified(self.path, "google", "google:123", now=100)
        self.assertTrue(result["authenticated"])
        header = cookie.split(";", 1)[0]
        self.assertTrue(http.status(self.path, header, now=101)["authenticated"])
        result, clear = http.logout(self.path, header)
        self.assertFalse(result["authenticated"])
        self.assertIn("Max-Age=0", clear)
        self.assertFalse(http.status(self.path, header, now=102)["authenticated"])
    def test_missing_cookie(self):
        self.assertFalse(http.status(self.path, "", now=100)["authenticated"])
    def test_invalid_identity(self):
        with self.assertRaises(store.DurableSessionError):
            http.login_verified(self.path, "google", "facebook:123", now=100)
    def test_cookie_security(self):
        _, cookie = http.login_verified(self.path, "phone", "phone:+5521999999999", now=100)
        for flag in ("Secure", "HttpOnly", "SameSite=Lax", "Path=/"):
            self.assertIn(flag, cookie)

if __name__ == "__main__":
    unittest.main()
