import os
import unittest
from unittest.mock import patch
import bblia_google_isolated_bridge as bridge

ENV = {
 "BBLIA_ISOLATED_GOOGLE_OAUTH_ENABLED":"1",
 "BBLIA_ISOLATED_GOOGLE_ORIGIN":"https://bblia-auth-isolated.example.test",
 "GOOGLE_REDIRECT_URI":"https://bblia-auth-isolated.example.test/auth/google/callback",
 "GOOGLE_CLIENT_ID":"test-client",
 "GOOGLE_CLIENT_SECRET":"test-secret"
}

class IsolatedGoogleBridgeTests(unittest.TestCase):
 def test_disabled_by_default(self):
  with patch.dict(os.environ, ENV, clear=True):
   os.environ.pop("BBLIA_ISOLATED_GOOGLE_OAUTH_ENABLED")
   with self.assertRaises(bridge.IsolatedGoogleError): bridge.start()

 def test_refuses_stage6_redirect(self):
  with patch.dict(os.environ, {**ENV,"GOOGLE_REDIRECT_URI":"https://bblia-stage6-validacao.onrender.com/auth/google/callback",
   "BBLIA_ISOLATED_GOOGLE_ORIGIN":"https://bblia-stage6-validacao.onrender.com"}, clear=True):
   with self.assertRaises(bridge.IsolatedGoogleError): bridge.start()

 def test_refuses_http(self):
  with patch.dict(os.environ, {**ENV,"GOOGLE_REDIRECT_URI":"http://bblia-auth-isolated.example.test/auth/google/callback"}, clear=True):
   with self.assertRaises(bridge.IsolatedGoogleError): bridge.start()

 def test_start_calls_google_only_after_guard(self):
  with patch.dict(os.environ, ENV, clear=True), patch.object(bridge.google,"start",return_value=({"url":"https://accounts.google.com/test"},"cookie")) as mock:
   self.assertEqual(bridge.start()[0]["url"],"https://accounts.google.com/test")
   mock.assert_called_once_with("",["login"])

 def test_complete_uses_verified_google_subject(self):
  with patch.dict(os.environ, ENV, clear=True), patch.object(bridge.google,"callback",return_value="cookie") as cb, patch.object(bridge.google,"session",return_value={"user":{"id":"sub123"},"token":"mock"}) as session:
   self.assertEqual(bridge.complete("incoming","state=ok&code=mock"),"google:sub123")
   cb.assert_called_once_with("incoming","state=ok&code=mock")
   session.assert_called_once_with("cookie")

 def test_rejects_unverified_identity(self):
  with patch.dict(os.environ, ENV, clear=True), patch.object(bridge.google,"callback",return_value="cookie"), patch.object(bridge.google,"session",return_value={"user":{"id":"email:fake"},"token":"mock"}):
   with self.assertRaises(bridge.IsolatedGoogleError): bridge.complete("incoming","state=ok")

if __name__=="__main__": unittest.main()
