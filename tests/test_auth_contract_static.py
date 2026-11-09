"""Non-network regression checks for the isolated BBLIA authentication branch.

Run: python -m unittest tests/test_auth_contract_static.py
This does not prove OAuth/SMS end-to-end.
"""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class AuthContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.google = (ROOT / "bblia_google.py").read_text(encoding="utf-8")
        cls.app = (ROOT / "bblia_app.py").read_text(encoding="utf-8")
        cls.google_tree = ast.parse(cls.google)
        cls.app_tree = ast.parse(cls.app)

    def test_google_has_session_and_logout(self):
        functions = {node.name for node in self.google_tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for name in ("status", "session", "start", "callback", "disconnect", "mobile_begin", "mobile_redeem"):
            with self.subTest(name=name):
                self.assertIn(name, functions)

    def test_google_uses_secure_cookie_flags(self):
        for flag in ("Secure", "HttpOnly", "SameSite=Lax"):
            with self.subTest(flag=flag):
                self.assertIn(flag, self.google)

    def test_mobile_ticket_requires_proof(self):
        self.assertIn("proof_hash", self.google)
        self.assertIn("compare_digest", self.google)
        self.assertIn("MOBILE.pop(tx,None)", self.google)

    def test_logout_endpoint_exists(self):
        self.assertIn("/api/account/logout", self.app)

    def test_facebook_and_phone_not_yet_implemented(self):
        # Explicit pending status prevents accidentally declaring the feature done.
        self.assertNotIn("/api/facebook/start", self.app)
        self.assertNotIn("/api/phone/start", self.app)

if __name__ == "__main__":
    unittest.main()
