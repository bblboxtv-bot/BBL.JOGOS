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
    def test_phone_fails_closed(self):
        code,body,_=self.fetch("/api/auth/phone/verify",{"phone":"+5521999999999","code":"123456"})
        self.assertEqual(code,503)
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
        from urllib.request import build_opener, HTTPHandler
        class NoRedirect(HTTPHandler):
            def http_response(self, request, response):
                return response
            https_response = http_response
        with patch.object(preview.facebook, "callback", return_value={"subject": "facebook:123", "name": "Teste"}) as mocked:
            req = Request(self.base + "/auth/facebook/callback?state=abc123&code=code123", headers={"Cookie": "__Host-bblia_fb_state=abc123"})
            with build_opener(NoRedirect()).open(req, timeout=5) as response:
                self.assertEqual(response.status, 303)
                self.assertIn("__Host-bblia_session=", str(response.headers.get_all("Set-Cookie")))
            mocked.assert_called_once_with("abc123", "code123")

    def test_unknown_route(self):
        code,body,_=self.fetch("/api/auth/unknown",{})
        self.assertEqual(code,404)

if __name__=="__main__":
    unittest.main()
