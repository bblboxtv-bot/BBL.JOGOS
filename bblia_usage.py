"""Per-account daily free usage, backed by SQLite. Requires persistent storage in production."""
import os
import sqlite3
from datetime import datetime, timezone

DAILY_TEXT_LIMIT = 20

def database_path():
    return os.getenv("BBLIA_USAGE_DB", "").strip()

def _connect():
    path = database_path()
    if not path:
        raise RuntimeError("Armazenamento persistente de cotas não configurado.")
    db = sqlite3.connect(path, timeout=10, isolation_level=None)
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("CREATE TABLE IF NOT EXISTS daily_usage (google_sub TEXT NOT NULL, day TEXT NOT NULL, kind TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (google_sub, day, kind))")
    return db

def usage(google_sub):
    if not google_sub:
        raise ValueError("Conta Google não autenticada.")
    day = datetime.now(timezone.utc).date().isoformat()
    with _connect() as db:
        row = db.execute("SELECT used FROM daily_usage WHERE google_sub=? AND day=? AND kind='text'", (google_sub, day)).fetchone()
    used = row[0] if row else 0
    return {"day_utc": day, "text_limit": DAILY_TEXT_LIMIT, "text_used": used, "text_remaining": max(0, DAILY_TEXT_LIMIT - used)}

def reserve_text(google_sub):
    if not google_sub:
        raise ValueError("Conta Google não autenticada.")
    day = datetime.now(timezone.utc).date().isoformat()
    with _connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("INSERT OR IGNORE INTO daily_usage (google_sub,day,kind,used) VALUES (?,?,'text',0)", (google_sub,day))
        changed = db.execute("UPDATE daily_usage SET used=used+1 WHERE google_sub=? AND day=? AND kind='text' AND used<?", (google_sub,day,DAILY_TEXT_LIMIT)).rowcount
        db.commit()
    return bool(changed)
