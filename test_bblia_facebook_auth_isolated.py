"""Offline Facebook OAuth tests; no Facebook API calls or real accounts."""
import os
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs
import bblia_facebook_auth as fb

SESSION = "test-session-key-that-is-at-least-32-chars-long"
OTHER_SESSION = "different-session-key-that-is-also-long-enough"
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
        result = fb.start(session_key=SESSION, now=1000)
        params = parse_qs(urlsplit(result["url"]).query)
        self.assertEqual(params["state"], [result["state"]])
        self.assertEqual(params["redirect_uri"], [ENV["BBLIA_FACEBOOK_REDIRECT_URI"]])
        self.assertIn(result["state"], fb.PENDING)

    def test_verified_callback_and_one_time_state(self):
        state = fb.start(session_key=SESSION, now=1000)["state"]
        def fake_fetch(url, *, data=None, headers=None):
            if url == fb.TOKEN_URL:
                return {"access_token": "test-token"}
            return {"id": "123456789", "name": "Test User"}
        result = fb.callback(state, "test-code", now=1001, session_key=SESSION, request_json=fake_fetch)
        self.assertEqual(result["subject"], "facebook:123456789")
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback(state, "test-code", now=1002, session_key=SESSION, request_json=fake_fetch)

    def test_expired_state_fails_without_network(self):
        state = fb.start(session_key=SESSION, now=1000)["state"]
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback(state, "test-code", now=1600, session_key=SESSION, request_json=lambda _: self.fail("network called"))

    def test_invalid_profile_identity_rejected(self):
        state = fb.start(session_key=SESSION, now=1000)["state"]
        def fake_fetch(url, *, data=None, headers=None):
            return {"access_token": "test-token"} if url == fb.TOKEN_URL else {"id": "not-numeric"}
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback(state, "test-code", now=1001, session_key=SESSION, request_json=fake_fetch)

    def test_unknown_state_rejected_before_provider_request(self):
        def forbidden_fetch(*args, **kwargs):
            self.fail("Unknown state must not contact Facebook")
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback("unknown-state", "test-code", now=1001, session_key=SESSION, request_json=forbidden_fetch)

    def test_missing_access_token_rejected(self):
        state = fb.start(session_key=SESSION, now=1000)["state"]
        def fake_fetch(url, *, data=None, headers=None):
            if url == fb.TOKEN_URL:
                return {"error": {"message": "invalid code"}}
            self.fail("Profile must not be fetched without access token")
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback(state, "test-code", now=1001, session_key=SESSION, request_json=fake_fetch)

    def test_provider_network_failure_does_not_reuse_state(self):
        state = fb.start(session_key=SESSION, now=1000)["state"]
        def broken_fetch(*args, **kwargs):
            raise OSError("simulated provider outage")
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback(state, "test-code", now=1001, session_key=SESSION, request_json=broken_fetch)
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback(state, "test-code", now=1002, session_key=SESSION, request_json=broken_fetch)

    def test_malformed_token_payload_rejected_safely(self):
        state = fb.start(session_key=SESSION, now=1000)["state"]
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback(state, "test-code", now=1001, session_key=SESSION, request_json=lambda *args, **kwargs: ["unexpected"])

    def test_malformed_profile_payload_rejected_safely(self):
        state = fb.start(session_key=SESSION, now=1000)["state"]
        def fake_fetch(url, *, data=None, headers=None):
            return {"access_token": "test-token"} if url == fb.TOKEN_URL else ["unexpected"]
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback(state, "test-code", now=1001, session_key=SESSION, request_json=fake_fetch)

    def test_empty_profile_id_rejected(self):
        state = fb.start(session_key=SESSION, now=1000)["state"]
        def fake_fetch(url, *, data=None, headers=None):
            return {"access_token": "test-token"} if url == fb.TOKEN_URL else {"id": ""}
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback(state, "test-code", now=1001, session_key=SESSION, request_json=fake_fetch)

    def test_non_ascii_numeric_profile_id_rejected(self):
        state = fb.start(session_key=SESSION, now=1000)["state"]
        def fake_fetch(url, *, data=None, headers=None):
            return {"access_token": "test-token"} if url == fb.TOKEN_URL else {"id": "１２３４５"}
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback(state, "test-code", now=1001, session_key=SESSION, request_json=fake_fetch)

    def test_non_string_access_token_rejected_before_profile_lookup(self):
        state = fb.start(session_key=SESSION, now=1000)["state"]
        def fake_fetch(url, *, data=None, headers=None):
            if url == fb.TOKEN_URL:
                return {"access_token": 12345}
            self.fail("Profile must not be requested with invalid token")
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback(state, "test-code", now=1001, session_key=SESSION, request_json=fake_fetch)

    def test_missing_callback_code_rejected_without_consuming_state(self):
        state = fb.start(session_key=SESSION, now=1000)["state"]
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback(state, "", now=1001,
                        session_key=SESSION, request_json=lambda _: self.fail("network called"))
        self.assertIn(state, fb.PENDING)

    def test_secrets_not_in_urls(self):
        state = fb.start(session_key=SESSION, now=1000)["state"]
        calls = []
        def fake_fetch(url, *, data=None, headers=None):
            calls.append((url, data, headers))
            if url == fb.TOKEN_URL:
                return {"access_token": "sample-access-token"}
            return {"id": "12345"}
        fb.callback(state, "sample-code", now=1001, session_key=SESSION, request_json=fake_fetch)
        self.assertEqual(len(calls), 2)
        self.assertNotIn("test-only-not-real", calls[0][0])
        self.assertIn(b"client_secret=test-only-not-real", calls[0][1])
        self.assertNotIn("sample-access-token", calls[1][0])
        self.assertEqual(calls[1][2]["Authorization"], "Bearer sample-access-token")

    def test_callback_rejects_different_browser_session(self):
        state = fb.start(session_key=SESSION, now=1000)["state"]
        def forbidden_fetch(*args, **kwargs):
            self.fail("Mismatched session must not contact provider")
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback(state, "test-code", session_key=OTHER_SESSION, now=1001, request_json=forbidden_fetch)

    def test_missing_or_short_session_rejected(self):
        with self.assertRaises(fb.FacebookAuthError):
            fb.start(session_key="short", now=1000)
        with self.assertRaises(fb.FacebookAuthError):
            fb.callback("state", "code", session_key="short", now=1000)

    def test_mismatched_callback_origin_rejected(self):
        with patch.dict(os.environ, {"BBLIA_FACEBOOK_REDIRECT_URI": "https://unrelated.example/auth/facebook/callback"}):
            with self.assertRaises(fb.FacebookAuthError):
                fb.start(session_key=SESSION, now=1000)

if __name__ == "__main__":
    unittest.main()
