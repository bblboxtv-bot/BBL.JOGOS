import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen
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

if __name__=="__main__":
    unittest.main()
