"""Durable BBLIA session storage for an isolated staging environment.

SQLite is suitable for a single local instance with persistent disk; use
managed PostgreSQL for multi-instance Render. Never store OAuth access tokens
in this table. Session identifiers are hashed at rest.
"""
import hashlib
import os
import secrets
import sqlite3
import time

TTL = 30 * 24 * 3600

class DurableSessionError(ValueError):
    pass

def _hash(sid):
    if not isinstance(sid, str) or len(sid) < 32:
        raise DurableSessionError("Sessão inválida.")
    return hashlib.sha256(sid.encode("ascii")).hexdigest()

def initialize(path):
    with sqlite3.connect(path, timeout=10) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS bblia_sessions (
            sid_hash TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            subject TEXT NOT NULL,
            expires REAL NOT NULL
        )""")

def create(path, provider, subject, *, now=None):
    if provider not in ("google", "facebook", "phone"):
        raise DurableSessionError("Provedor inválido.")
    if not isinstance(subject, str) or not subject.startswith(provider + ":") or len(subject) > 256:
        raise DurableSessionError("Identidade inválida.")
    now = time.time() if now is None else now
    sid = secrets.token_urlsafe(32)
    with sqlite3.connect(path, timeout=10) as db:
        db.execute("INSERT INTO bblia_sessions VALUES (?,?,?,?)",
                   (_hash(sid), provider, subject, now + TTL))
    return sid

def load(path, sid, *, now=None):
    now = time.time() if now is None else now
    try:
        sid_hash = _hash(sid)
    except (DurableSessionError, UnicodeEncodeError):
        return None
    with sqlite3.connect(path, timeout=10) as db:
        row = db.execute("SELECT provider,subject,expires FROM bblia_sessions WHERE sid_hash=?",
                         (sid_hash,)).fetchone()
        if not row:
            return None
        if row[2] <= now:
            db.execute("DELETE FROM bblia_sessions WHERE sid_hash=?", (sid_hash,))
            return None
        return {"provider": row[0], "subject": row[1], "expires": row[2]}

def revoke(path, sid):
    try:
        sid_hash = _hash(sid)
    except (DurableSessionError, UnicodeEncodeError):
        return False
    with sqlite3.connect(path, timeout=10) as db:
        result = db.execute("DELETE FROM bblia_sessions WHERE sid_hash=?", (sid_hash,))
        return result.rowcount == 1
