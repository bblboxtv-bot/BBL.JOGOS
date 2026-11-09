import unittest
import bblia_identity_session as auth

class SessionTests(unittest.TestCase):
    def setUp(self):
        auth.SESSIONS.clear()

    def test_create_and_resume(self):
        sid = auth.create("facebook", "facebook:12345", now=100)
        self.assertEqual(auth.get(sid, now=101)["subject"], "facebook:12345")
        self.assertEqual(auth.get(sid, now=102)["provider"], "facebook")

    def test_logout_invalidates(self):
        sid = auth.create("phone", "phone:+5521999999999", now=100)
        self.assertTrue(auth.logout(sid))
        self.assertIsNone(auth.get(sid, now=101))
        self.assertFalse(auth.logout(sid))

    def test_expiry(self):
        sid = auth.create("google", "google:123", now=100)
        self.assertIsNone(auth.get(sid, now=100 + auth.TTL))

    def test_invalid_provider_rejected(self):
        with self.assertRaises(auth.SessionError):
            auth.create("email", "email:test", now=100)

    def test_cross_provider_subject_rejected(self):
        with self.assertRaises(auth.SessionError):
            auth.create("facebook", "google:123", now=100)

    def test_cookie_flags_and_expiry(self):
        sid = auth.create("google", "google:123", now=100)
        cookie = auth.cookie(sid)
        for flag in ("Secure", "HttpOnly", "SameSite=Lax", "Path=/"):
            self.assertIn(flag, cookie)
        self.assertIn("Max-Age=0", auth.cookie("", max_age=0))

if __name__ == "__main__":
    unittest.main()
