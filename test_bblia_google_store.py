import os, tempfile, sqlite3, time, secrets, unittest
from unittest.mock import patch
from cryptography.fernet import Fernet
import bblia_google_store as store

class SessionStoreTests(unittest.TestCase):
    def test_encryption_restart_and_revocation(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            path=os.path.join(folder,'session.sqlite3')
            with patch.dict(os.environ,{'BBLIA_SESSION_KEY':Fernet.generate_key().decode()}), patch.object(store.db,'using_postgres',return_value=True), patch.object(store,'_connection',side_effect=lambda:sqlite3.connect(path)):
                sid=secrets.token_urlsafe(32)
                data={'expires':time.time()+3600,'token':'TEST_PRIVATE_TOKEN','user':{'id':'google-test-user'}}
                with sqlite3.connect(path) as conn:
                    conn.execute('CREATE TABLE bblia_google_sessions (sid_hash TEXT PRIMARY KEY,payload TEXT,expires REAL,state_hash TEXT)')
                store.save(sid,data)
                self.assertEqual(store.load(sid),data)
                with sqlite3.connect(path) as connection:
                    row=connection.execute('SELECT sid_hash,payload FROM bblia_google_sessions').fetchone()
                connection.close()
                self.assertNotIn(sid,str(row))
                self.assertNotIn('TEST_PRIVATE_TOKEN',str(row))
                self.assertIsNone(store.load('wrong-session'))
                state=secrets.token_urlsafe(32)
                pending={'expires':time.time()+300,'state':state,'verifier':'secret-verifier'}
                store.save('pending-session',pending)
                self.assertEqual(store.consume_state(state),pending)
                self.assertIsNone(store.consume_state(state))
                store.delete(sid)
                self.assertIsNone(store.load(sid))

if __name__=='__main__':unittest.main()
