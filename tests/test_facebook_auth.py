import os
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs
import bblia_facebook_auth as fb

ENV = {
    "BBLIA_FACEBOOK_APP_ID": "12345",
    "BBLIA_FACEBOOK_APP_SECRET": "test-secret",
    "BBLIA_FACEBOOK_REDIRECT_URI": "https://example.test/facebook-callback",
}

class FacebookAuthTests(unittest.TestCase):
    def setUp(self):
        fb.PENDING.clear()
        self.patch = patch.dict(os.environ, ENV)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()

    def test_start_uses_random_state_and_callback(self):
        result = fb.start(now=100)
        args = parse_qs(urlsplit(result["url"]).query)
        self.assertEqual(args["state"][0], result["state"])
        self.assertEqual(args["redirect_uri"][0], ENV["BBLIA_FACEBOOK_REDIRECT_URI"])
        self.assertNotIn("client_secret", args)

    def test_callback_returns_verified_subject(self):
        state = fb.start(now=100)["state"]
        def fake(url):
            return {"access_token": "token"} if "oauth/access_token" in url else {"id": "123456789", "name": "Teste"}
        result = fb.callback(state, "code", now=101, request_json=fake)
        self.assertEqual(result["subject"], "facebook:123456789")
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback(state, "code", now=102, request_json=fake)

    def test_expired_state_rejected(self):
        state = fb.start(now=100)["state"]
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback(state, "code", now=701, request_json=lambda _: {})

    def test_missing_token_rejected(self):
        state = fb.start(now=100)["state"]
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback(state, "code", now=101, request_json=lambda _: {})

    def test_untrusted_profile_rejected(self):
        state = fb.start(now=100)["state"]
        def fake(url):
            return {"access_token": "token"} if "oauth/access_token" in url else {"id": "<script>"}
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback(state, "code", now=101, request_json=fake)

    def test_unconfigured_rejected(self):
        with patch.dict(os.environ, {"BBLIA_FACEBOOK_APP_SECRET": ""}):
            with self.assertRaises(fb.FacebookAuthError):
                fb.start(now=100)

if __name__ == "__main__":
    unittest.main()
