"""Offline tests for isolated phone OTP; no real SMS is sent."""
import unittest
from unittest.mock import patch
import bblia_phone_auth as phone

SECRET = "test-only-secret-not-for-deployment-123456789"

class PhoneOtpTests(unittest.TestCase):
    def setUp(self):
        phone.PENDING.clear()
        phone.ATTEMPTS.clear()

    def tearDown(self):
        phone.PENDING.clear()
        phone.ATTEMPTS.clear()

    def test_delivery_failure_does_not_enable_code(self):
        def fail_send(number, message):
            raise RuntimeError("simulated SMS outage")
        with self.assertRaises(RuntimeError):
            phone.request_code("+5521999990000", fail_send, now=1000, secret=SECRET)
        self.assertFalse(phone.PENDING)
        self.assertFalse(phone.ATTEMPTS)

    def test_success_single_use_and_wrong_attempts(self):
        sent = []
        phone.request_code("+5521999990001", lambda n, m: sent.append(m), now=1000, secret=SECRET)
        code = sent[0].split(" é ")[1][:6]
        self.assertEqual(phone.verify_code("+5521999990001", code, now=1001, secret=SECRET)["subject"], "phone:+5521999990001")
        with self.assertRaises(phone.PhoneAuthError):
            phone.verify_code("+5521999990001", code, now=1002, secret=SECRET)

    def test_expiry_and_request_limit(self):
        sent = []
        number = "+5521999990002"
        for t in (1000, 1001, 1002):
            phone.request_code(number, lambda n, m: sent.append(m), now=t, secret=SECRET)
        with self.assertRaises(phone.PhoneAuthError):
            phone.request_code(number, lambda n, m: sent.append(m), now=1003, secret=SECRET)
        code = sent[-1].split(" é ")[1][:6]
        with self.assertRaises(phone.PhoneAuthError):
            phone.verify_code(number, code, now=1303, secret=SECRET)

    def test_wrong_code_locks_after_five_attempts(self):
        number = "+5521999990003"
        sent = []
        phone.request_code(number, lambda n, m: sent.append(m), now=1000, secret=SECRET)
        code = sent[0].split(" é ")[1][:6]
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(5):
            with self.assertRaises(phone.PhoneAuthError):
                phone.verify_code(number, wrong, now=1001, secret=SECRET)
        with self.assertRaises(phone.PhoneAuthError):
            phone.verify_code(number, code, now=1002, secret=SECRET)

    def test_reissued_code_invalidates_previous_code(self):
        sent = []
        number = "+5521999990004"
        with patch.object(phone.secrets, "randbelow", side_effect=[123456, 654321]):
            phone.request_code(number, lambda n, m: sent.append(m), now=1000, secret=SECRET)
            first = sent[-1].split(" é ")[1][:6]
            phone.request_code(number, lambda n, m: sent.append(m), now=1001, secret=SECRET)
            second = sent[-1].split(" é ")[1][:6]
        with self.assertRaises(phone.PhoneAuthError):
            phone.verify_code(number, first, now=1002, secret=SECRET)
        self.assertEqual(phone.verify_code(number, second, now=1002, secret=SECRET)["verified"], True)

    def test_invalid_phone_and_missing_secret_fail_closed(self):
        with self.assertRaises(phone.PhoneAuthError):
            phone.request_code("21999990000", lambda n, m: None, now=1000, secret=SECRET)
        with self.assertRaises(phone.PhoneAuthError):
            phone.request_code("+5521999990005", lambda n, m: None, now=1000, secret="short")
        self.assertFalse(phone.PENDING)

    def test_rate_limit_resets_after_hour(self):
        number = "+5521999990006"
        for t in (1000, 1001, 1002):
            phone.request_code(number, lambda n, m: None, now=t, secret=SECRET)
        with self.assertRaises(phone.PhoneAuthError):
            phone.request_code(number, lambda n, m: None, now=1003, secret=SECRET)
        self.assertEqual(phone.request_code(number, lambda n, m: None, now=4603, secret=SECRET)["sent"], True)

if __name__ == "__main__":
    unittest.main()
