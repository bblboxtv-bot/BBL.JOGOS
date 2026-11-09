import re
import unittest
from unittest.mock import patch
import bblia_phone_auth as auth

SECRET = "test-secret-that-is-long-enough-for-hmac-12345"
PHONE = "+5521999999999"

class PhoneAuthTests(unittest.TestCase):
    def setUp(self):
        auth.PENDING.clear()
        auth.ATTEMPTS.clear()
        self.sent = []
        self.sender = lambda phone, msg: self.sent.append((phone, msg))

    def test_valid_code_one_time(self):
        result = auth.request_code(PHONE, self.sender, now=100, secret=SECRET)
        self.assertTrue(result["sent"])
        code = re.search(r"([0-9]{6})", self.sent[0][1]).group(1)
        self.assertEqual(auth.verify_code(PHONE, code, now=101, secret=SECRET)["subject"], "phone:" + PHONE)
        with self.assertRaises(auth.PhoneAuthError):
            auth.verify_code(PHONE, code, now=102, secret=SECRET)

    def test_wrong_code_exhausts_attempts(self):
        auth.request_code(PHONE, self.sender, now=100, secret=SECRET)
        code = re.search(r"([0-9]{6})", self.sent[0][1]).group(1)
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(5):
            with self.assertRaises(auth.PhoneAuthError):
                auth.verify_code(PHONE, wrong, now=101, secret=SECRET)
        self.assertNotIn(PHONE, auth.PENDING)

    def test_expiry(self):
        auth.request_code(PHONE, self.sender, now=100, secret=SECRET)
        code = re.search(r"([0-9]{6})", self.sent[0][1]).group(1)
        with self.assertRaises(auth.PhoneAuthError):
            auth.verify_code(PHONE, code, now=401, secret=SECRET)

    def test_hourly_rate_limit(self):
        for i in range(3):
            auth.request_code(PHONE, self.sender, now=100+i, secret=SECRET)
        with self.assertRaises(auth.PhoneAuthError):
            auth.request_code(PHONE, self.sender, now=104, secret=SECRET)

    def test_sender_failure_does_not_create_code(self):
        def broken(*args):
            raise RuntimeError("SMS unavailable")
        with self.assertRaises(RuntimeError):
            auth.request_code(PHONE, broken, now=100, secret=SECRET)
        self.assertNotIn(PHONE, auth.PENDING)

    def test_verify_rejects_missing_secret_without_consuming_valid_code(self):\n        auth.request_code(PHONE, self.sender, now=100, secret=SECRET)\n        code = re.search(r"([0-9]{6})", self.sent[0][1]).group(1)\n        with patch.dict("os.environ", {"BBLIA_OTP_SECRET": ""}):\n            with self.assertRaisesRegex(auth.PhoneAuthError, "não configurado"):\n                auth.verify_code(PHONE, code, now=101)\n        self.assertEqual(auth.verify_code(PHONE, code, now=102, secret=SECRET)["subject"], "phone:" + PHONE)\n\n    def test_invalid_phone_and_missing_secret(self):
        with self.assertRaises(auth.PhoneAuthError):
            auth.request_code("21999999999", self.sender, now=100, secret=SECRET)
        with self.assertRaises(auth.PhoneAuthError):
            auth.request_code(PHONE, self.sender, now=100, secret="short")

if __name__ == "__main__":
    unittest.main()
