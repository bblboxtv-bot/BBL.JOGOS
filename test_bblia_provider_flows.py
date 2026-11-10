"""Offline provider flow tests: simulated transport, never fake real-provider approval."""
import os
import unittest
from unittest.mock import patch
import bblia_phone_auth as phone
import bblia_facebook_auth as facebook

class ProviderFlows(unittest.TestCase):
    def test_phone_sms_round_trip_and_replay_rejected(self):
        sent = []
        number = "+5521999999999"
        secret = "t" * 40
        with patch.dict(os.environ, {"BBLIA_OTP_SECRET":secret}):
            phone.PENDING.clear()
            phone.ATTEMPTS.clear()
            phone.request_code(number, lambda to, msg: sent.append((to,msg)))
            self.assertEqual(len(sent), 1)
            self.assertEqual(sent[0][0], number)
            code = sent[0][1].split(" é ")[1][:6]
            self.assertEqual(phone.verify_code(number, code)["subject"], "phone:"+number)
            with self.assertRaises(phone.PhoneAuthError):
                phone.verify_code(number, code)
    def test_phone_delivery_failure_cannot_verify(self):
        number = "+5521888888888"
        phone.PENDING.clear()
        phone.ATTEMPTS.clear()
        with patch.dict(os.environ, {"BBLIA_OTP_SECRET":"s"*40}):
            def failed(to, message):
                raise RuntimeError("SMS transport failed")
            with self.assertRaises(RuntimeError):
                phone.request_code(number, failed)
            self.assertNotIn(number, phone.PENDING)
    def test_facebook_callback_validated_and_one_time(self):
        env = {
            "BBLIA_FACEBOOK_APP_ID":"123456",
            "BBLIA_FACEBOOK_APP_SECRET":"test-only-secret",
            "BBLIA_FACEBOOK_REDIRECT_URI":"https://bblia-login-integrado-stage-20261109.onrender.com/auth/facebook/callback",
            "BBLIA_ISOLATED_GOOGLE_ORIGIN":"https://bblia-login-integrado-stage-20261109.onrender.com"
        }
        with patch.dict(os.environ, env):
            facebook.PENDING.clear()
            started = facebook.start()
            self.assertIn("state=", started["url"])
            def provider_response(url):
                if "access_token?" in url:
                    return {"access_token":"mock-access-token"}
                return {"id":"123456789", "name":"Test User"}
            result = facebook.callback(started["state"], "mock-code", request_json=provider_response)
            self.assertEqual(result["subject"], "facebook:123456789")
            with self.assertRaises(facebook.FacebookAuthError):
                facebook.callback(started["state"], "mock-code", request_json=provider_response)

if __name__ == "__main__":
    unittest.main()
