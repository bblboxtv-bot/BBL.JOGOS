import os, tempfile, sqlite3, time, secrets, unittest
from unittest.mock import patch
from cryptography.fernet import Fernet
import bblia_google_store as store

class SessionStoreTests(unittest.TestCase):
    def test_encryption_restart_and_revocation(self):
        with tempfile.TemporaryDirectory() as folder:
            path=os.path.join(folder,'session.sqlite3')
            with patch.dict(os.environ,{'BBLIA_SESSION_KEY':Fernet.generate_key().decode()}), patch.object(store.db,'using_postgres',return_value=True), patch.object(store.db,'connect',side_effect=lambda _:sqlite3.connect(path)):
                sid=secrets.token_urlsafe(32)
                data={'expires':time.time()+3600,'token':'TEST_PRIVATE_TOKEN','user':{'id':'google-test-user'}}
                store.save(sid,data)
                self.assertEqual(store.load(sid),data)
                row=sqlite3.connect(path).execute('SELECT sid_hash,payload FROM bblia_google_sessions').fetchone()
                self.assertNotIn(sid,str(row))
                self.assertNotIn('TEST_PRIVATE_TOKEN',str(row))
                self.assertIsNone(store.load('wrong-session'))
                store.delete(sid)
                self.assertIsNone(store.load(sid))

if __name__=='__main__':unittest.main()
