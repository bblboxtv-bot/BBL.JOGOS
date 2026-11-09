import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch
import bblia_login_preview_server as preview
import bblia_session_sqlite as sessions

class PreviewServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.db=str(Path(cls.tmp.name)/"sessions.db")
        sessions.initialize(cls.db)
        cls.dbpatch=patch.object(preview,"DB",Path(cls.db))
        cls.dbpatch.start()
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),preview.Handler)
        cls.base="http://127.0.0.1:"+str(cls.server.server_port)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.dbpatch.stop()
        cls.tmp.cleanup()
    def fetch(self,path,body=None,origin=None):
        headers={}
        if body is not None:
            headers["Content-Type"]="application/json"
        if origin:
            headers["Origin"]=origin
        req=Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:
            with urlopen(req,timeout=5) as res:
                return res.status,res.read().decode(),res.headers
        except HTTPError as exc:
            return exc.code,exc.read().decode(),exc.headers
    def test_page_served(self):
        code,body,_=self.fetch("/")
        self.assertEqual(code,200)
        self.assertIn("Continuar com Facebook",body)
        self.assertNotIn('type="password"',body)
    def test_status_anonymous(self):
        code,body,_=self.fetch("/api/auth/status")
        self.assertEqual(code,200)
        self.assertFalse(json.loads(body)["authenticated"])
    def test_logout_anonymous(self):
        code,body,headers=self.fetch("/api/auth/logout",{})
        self.assertEqual(code,200)
        self.assertIn("Max-Age=0",headers.get("Set-Cookie",""))
    def test_phone_without_requested_otp_fails_closed(self):
        code,body,_=self.fetch("/api/auth/phone/verify",{"phone":"+5521999999999","code":"123456"})
        self.assertEqual(code,401)
    def test_facebook_without_config_fails_closed(self):
        with patch.dict("os.environ",{"BBLIA_FACEBOOK_APP_ID":"","BBLIA_FACEBOOK_APP_SECRET":"","BBLIA_FACEBOOK_REDIRECT_URI":""}):
            code,body,_=self.fetch("/api/auth/facebook/start",{})
        self.assertEqual(code,503)
    def test_origin_rejected(self):
        code,body,_=self.fetch("/api/auth/logout",{},origin="https://evil.invalid")
        self.assertEqual(code,403)
    def test_facebook_callback_rejects_missing_browser_state(self):
        code, body, _ = self.fetch("/auth/facebook/callback?state=forged&code=fake")
        self.assertEqual(code, 403)

    def test_facebook_callback_with_verified_identity(self):
        from urllib.request import build_opener, HTTPRedirectHandler
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, request, fp, code, msg, headers, newurl):
                return None
        with patch.object(preview.facebook, "callback", return_value={"subject": "facebook:123", "name": "Teste"}) as mocked:
            req = Request(self.base + "/auth/facebook/callback?state=abc123&code=code123", headers={"Cookie": "__Host-bblia_fb_state=abc123"})
            try:
                build_opener(NoRedirect()).open(req, timeout=5)
                self.fail("Expected redirect response")
            except HTTPError as response:
                self.assertEqual(response.code, 303)
                self.assertIn("__Host-bblia_session=", str(response.headers.get_all("Set-Cookie")))
            mocked.assert_called_once_with("abc123", "code123")

    def test_phone_validated_otp_issues_session(self):
        with patch.object(preview.phone, "verify_code", return_value={"verified": True, "subject": "phone:+5521999999999"}) as checked:
            code, body, headers = self.fetch("/api/auth/phone/verify", {"phone": "+5521999999999", "code": "123456"})
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(body)["authenticated"])
        self.assertIn("__Host-bblia_session=", headers.get("Set-Cookie", ""))
        checked.assert_called_once_with("+5521999999999", "123456")

    def test_phone_wrong_code_rejected(self):
        code, body, headers = self.fetch("/api/auth/phone/verify", {"phone": "+5521999999999", "code": "000000"})
        self.assertEqual(code, 401)
        self.assertNotIn("__Host-bblia_session=", headers.get("Set-Cookie", ""))

    def test_status_after_verified_login_and_logout(self):
        with patch.object(preview.phone, "verify_code", return_value={"verified": True, "subject": "phone:+5521988887777"}):
            code, body, headers = self.fetch("/api/auth/phone/verify", {"phone": "+5521988887777", "code": "654321"})
        self.assertEqual(code, 200)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        req = Request(self.base + "/api/auth/status", headers={"Cookie": cookie})
        with urlopen(req, timeout=5) as response:
            self.assertTrue(json.load(response)["authenticated"])
        req = Request(self.base + "/api/auth/logout", data=b"{}", headers={"Cookie": cookie, "Content-Type": "application/json"})
        with urlopen(req, timeout=5) as response:
            self.assertEqual(response.status, 200)
        req = Request(self.base + "/api/auth/status", headers={"Cookie": cookie})
        with urlopen(req, timeout=5) as response:
            self.assertFalse(json.load(response)["authenticated"])

    def test_google_start_without_isolated_configuration_fails_closed(self):
        code, body, headers = self.fetch("/api/account/start", {})
        self.assertEqual(code, 503)
        self.assertNotIn("Set-Cookie", headers)
        self.assertIn("Google", json.loads(body)["error"])

    def test_session_survives_server_reinitialization_and_logout(self):
        with patch.object(preview.phone, "verify_code", return_value={"verified": True, "subject": "phone:+5521977776666"}):
            code, _, headers = self.fetch("/api/auth/phone/verify", {"phone": "+5521977776666", "code": "123456"})
        self.assertEqual(code, 200)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        # Reinitialize the same durable DB, equivalent to opening it in a new worker.
        sessions.initialize(self.db)
        req = Request(self.base + "/api/auth/status", headers={"Cookie": cookie})
        with urlopen(req, timeout=5) as response:
            data = json.load(response)
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["provider"], "phone")
        req = Request(self.base + "/api/auth/logout", data=b"{}", headers={"Cookie": cookie, "Content-Type": "application/json"})
        with urlopen(req, timeout=5) as response:
            self.assertEqual(response.status, 200)
        sessions.initialize(self.db)
        req = Request(self.base + "/api/auth/status", headers={"Cookie": cookie})
        with urlopen(req, timeout=5) as response:
            self.assertFalse(json.load(response)["authenticated"])

    def test_cross_site_fetch_metadata_rejected(self):
        req = Request(self.base + "/api/auth/logout", data=b"{}", headers={
            "Content-Type": "application/json", "Sec-Fetch-Site": "cross-site"
        })
        with self.assertRaises(HTTPError) as caught:
            urlopen(req, timeout=5)
        self.assertEqual(caught.exception.code, 403)

    def test_same_origin_fetch_metadata_allowed(self):
        req = Request(self.base + "/api/auth/logout", data=b"{}", headers={
            "Content-Type": "application/json", "Sec-Fetch-Site": "same-origin"
        })
        with urlopen(req, timeout=5) as response:
            self.assertEqual(response.status, 200)

    def test_unknown_route(self):
        code,body,_=self.fetch("/api/auth/unknown",{})
        self.assertEqual(code,404)

if __name__=="__main__":
    unittest.main()
