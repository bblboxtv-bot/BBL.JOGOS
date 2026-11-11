"""Offline Facebook OAuth tests; no Facebook API calls or real accounts."""
import os
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs
import bblia_facebook_auth as fb

ENV = {
    "BBLIA_FACEBOOK_APP_ID": "123456789",
    "BBLIA_FACEBOOK_APP_SECRET": "test-only-not-real",
    "BBLIA_FACEBOOK_REDIRECT_URI": "https://bblia-login-integrado-stage-20261109.onrender.com/auth/facebook/callback",
    "BBLIA_ISOLATED_GOOGLE_ORIGIN": "https://bblia-login-integrado-stage-20261109.onrender.com",
}

class FacebookOAuthTests(unittest.TestCase):
    def setUp(self):
        fb.PENDING.clear()
        self.env = patch.dict(os.environ, ENV)
        self.env.start()

    def tearDown(self):
        fb.PENDING.clear()
        self.env.stop()

    def test_authorization_has_state_and_staging_redirect(self):
        result = fb.start(now=1000)
        params = parse_qs(urlsplit(result["url"]).query)
        self.assertEqual(params["state"], [result["state"]])
        self.assertEqual(params["redirect_uri"], [ENV["BBLIA_FACEBOOK_REDIRECT_URI"]])
        self.assertIn(result["state"], fb.PENDING)

    def test_verified_callback_and_one_time_state(self):
        state = fb.start(now=1000)["state"]
        def fake_fetch(url):
            if "access_token?" in url:
                return {"access_token": "test-token"}
            return {"id": "123456789", "name": "Test User"}
        result = fb.callback(state, "test-code", now=1001, request_json=fake_fetch)
        self.assertEqual(result["subject"], "facebook:123456789")
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback(state, "test-code", now=1002, request_json=fake_fetch)

    def test_expired_state_fails_without_network(self):
        state = fb.start(now=1000)["state"]
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback(state, "test-code", now=1600, request_json=lambda _: self.fail("network called"))

    def test_invalid_profile_identity_rejected(self):
        state = fb.start(now=1000)["state"]
        def fake_fetch(url):
            return {"access_token": "test-token"} if "access_token?" in url else {"id": "not-numeric"}
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback(state, "test-code", now=1001, request_json=fake_fetch)

    def test_unknown_state_rejected_before_provider_request(self):
        def forbidden_fetch(_):
            self.fail("Unknown state must not contact Facebook")
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback("unknown-state", "test-code", now=1001, request_json=forbidden_fetch)

    def test_missing_access_token_rejected(self):
        state = fb.start(now=1000)["state"]
        def fake_fetch(url):
            if "access_token?" in url:
                return {"error": {"message": "invalid code"}}
            self.fail("Profile must not be fetched without access token")
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback(state, "test-code", now=1001, request_json=fake_fetch)

    def test_provider_network_failure_does_not_reuse_state(self):
        state = fb.start(now=1000)["state"]
        def broken_fetch(_):
            raise OSError("simulated provider outage")
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback(state, "test-code", now=1001, request_json=broken_fetch)
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback(state, "test-code", now=1002, request_json=broken_fetch)

    def test_mismatched_callback_origin_rejected(self):
        with patch.dict(os.environ, {"BBLIA_FACEBOOK_REDIRECT_URI": "https://unrelated.example/auth/facebook/callback"}):
            with self.assertRaises(fb.FacebookAuthError):
                fb.start(now=1000)

if __name__ == "__main__":
    unittest.main()
