"""Encrypted, durable Google OAuth sessions. Requires BBLIA_SESSION_KEY (Fernet key) and BBLIA_DATABASE_URL."""
import os, json, time, hashlib
import bblia_db as db

def _cipher():
    from cryptography.fernet import Fernet
    key=os.getenv('BBLIA_SESSION_KEY','').strip()
    if not key or not db.using_postgres():
        return None
    return Fernet(key.encode())

def _connection():
    conn=db.connect('bblia_auth.sqlite3')
    conn.execute("CREATE TABLE IF NOT EXISTS bblia_google_sessions (sid_hash TEXT PRIMARY KEY, payload TEXT NOT NULL, expires DOUBLE PRECISION NOT NULL)")
    conn.commit()
    return conn

def enabled():
    return _cipher() is not None

def save(sid, value):
    cipher=_cipher()
    if not cipher:return
    token=cipher.encrypt(json.dumps(value,separators=(',',':')).encode()).decode()
    conn=_connection()
    try:
        conn.execute("INSERT INTO bblia_google_sessions(sid_hash,payload,expires) VALUES(?,?,?) ON CONFLICT(sid_hash) DO UPDATE SET payload=excluded.payload, expires=excluded.expires",
                     (hashlib.sha256(sid.encode()).hexdigest(),token,float(value['expires'])))
        conn.commit()
    finally:conn.close()

def load(sid):
    cipher=_cipher()
    if not cipher or not sid:return None
    conn=_connection()
    try:
        row=conn.execute("SELECT payload,expires FROM bblia_google_sessions WHERE sid_hash=?",(hashlib.sha256(sid.encode()).hexdigest(),)).fetchone()
        if not row:return None
        if float(row[1])<=time.time():return None
        from cryptography.fernet import InvalidToken
        try:return json.loads(cipher.decrypt(row[0].encode()).decode())
        except (InvalidToken,ValueError,TypeError):return None
    finally:conn.close()

def delete(sid):
    if not enabled() or not sid:return
    conn=_connection()
    try:
        conn.execute("DELETE FROM bblia_google_sessions WHERE sid_hash=?",(hashlib.sha256(sid.encode()).hexdigest(),))
        conn.commit()
    finally:conn.close()
