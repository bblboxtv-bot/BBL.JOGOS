import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen
from unittest.mock import patch as mock_patch
_original_read_text = Path.read_text
def _read_text(path, *args, **kwargs):
    if path.name == 'bblia_login_logo_base64.txt':
        return 'UklGRgQAAABXRUJQ'
    return _original_read_text(path, *args, **kwargs)
with mock_patch.object(Path, 'read_text', _read_text):
    import bblia_auth_integrated_test_server as app
import bblia_session_sqlite as store

class ReadinessHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Path(self.tmp.name)/"sessions.db"
        store.initialize(str(self.db))
        self.old_db=app.DB
        app.DB=self.db
        self.server=ThreadingHTTPServer(("127.0.0.1",0),app.Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        app.DB=self.old_db
        self.tmp.cleanup()
    def test_unconfigured_providers_fail_closed(self):
        names=["BBLIA_ISOLATED_GOOGLE_OAUTH_ENABLED","GOOGLE_CLIENT_ID","GOOGLE_CLIENT_SECRET","GOOGLE_REDIRECT_URI","FACEBOOK_APP_ID","FACEBOOK_APP_SECRET","BBLIA_OTP_SECRET","TWILIO_ACCOUNT_SID","TWILIO_AUTH_TOKEN","TWILIO_FROM_NUMBER"]
        with patch.dict(os.environ,{k:"" for k in names}):
            url="http://127.0.0.1:%d/api/auth/readiness"%self.server.server_port
            with urlopen(url,timeout=4) as response:
                result=json.load(response)
            self.assertFalse(result["google"])
            self.assertFalse(result["facebook"])
            self.assertFalse(result["phone_sms"])
    def test_short_otp_secret_not_ready(self):
        values={"BBLIA_OTP_SECRET":"short","TWILIO_ACCOUNT_SID":"test","TWILIO_AUTH_TOKEN":"test","TWILIO_FROM_NUMBER":"+15551234567"}
        with patch.dict(os.environ,values):
            url="http://127.0.0.1:%d/api/auth/readiness"%self.server.server_port
            with urlopen(url,timeout=4) as response:
                result=json.load(response)
            self.assertFalse(result["phone_sms"])

    def test_logout_revokes_real_http_cookie(self):
        from urllib.request import Request
        _, cookie=app.auth.login_verified(str(self.db),"google","google:test-verified",now=1000000000)
        cookie_header=cookie.split(";",1)[0]
        base="http://127.0.0.1:%d"%self.server.server_port
        # This fixture bypasses provider login; it tests only HTTP session handling.
        with urlopen(Request(base+"/api/auth/status",headers={"Cookie":cookie_header}),timeout=4) as response:
            self.assertFalse(json.load(response)["authenticated"])
        _, fresh_cookie=app.auth.login_verified(str(self.db),"google","google:test-verified")
        cookie_header=fresh_cookie.split(";",1)[0]
        with urlopen(Request(base+"/api/auth/status",headers={"Cookie":cookie_header}),timeout=4) as response:
            self.assertTrue(json.load(response)["authenticated"])
        request=Request(base+"/api/auth/logout",data=b"{}",headers={"Cookie":cookie_header,"Content-Type":"application/json"},method="POST")
        with urlopen(request,timeout=4) as response:
            self.assertFalse(json.load(response)["authenticated"])
            self.assertIn("Max-Age=0",response.headers.get("Set-Cookie",""))
        with urlopen(Request(base+"/api/auth/status",headers={"Cookie":cookie_header}),timeout=4) as response:
            self.assertFalse(json.load(response)["authenticated"])

    def test_provider_routes_reject_missing_credentials(self):
        from urllib.request import Request
        from urllib.error import HTTPError
        base="http://127.0.0.1:%d"%self.server.server_port
        names=["BBLIA_ISOLATED_GOOGLE_OAUTH_ENABLED","GOOGLE_CLIENT_ID","GOOGLE_CLIENT_SECRET","GOOGLE_REDIRECT_URI","FACEBOOK_APP_ID","FACEBOOK_APP_SECRET","BBLIA_OTP_SECRET","TWILIO_ACCOUNT_SID","TWILIO_AUTH_TOKEN","TWILIO_FROM_NUMBER"]
        with patch.dict(os.environ,{k:"" for k in names}):
            for route,payload in [("/api/account/start",{}),("/api/auth/facebook/start",{}),("/api/auth/phone/request",{"phone":"+5521999999999"})]:
                with self.subTest(route=route):
                    request=Request(base+route,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"},method="POST")
                    with self.assertRaises(HTTPError) as raised:
                        urlopen(request,timeout=4)
                    self.assertEqual(raised.exception.code,503)

if __name__=="__main__":
    unittest.main()
