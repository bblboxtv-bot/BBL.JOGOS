"""Persistent per-account subscription store; disabled until commercial integration is validated."""
import os, threading, time
import bblia_db as sqlite3
from pathlib import Path
from bblia_plan_rules import expires_at, plan_state

_LOCK=threading.RLock()
DB=Path(os.getenv("BBLIA_PLANS_DB","bblia_plans.sqlite3"))
VALID={"normal","avancado","profissional"}

def _connect():
    DB.parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(str(DB),timeout=15,isolation_level=None)
    con.execute("PRAGMA busy_timeout=15000")
    con.execute("CREATE TABLE IF NOT EXISTS subscriptions (user_id TEXT PRIMARY KEY, tier TEXT NOT NULL, expires_at INTEGER NOT NULL, suspended INTEGER NOT NULL DEFAULT 0, updated_at INTEGER NOT NULL)")
    return con

def status(user_id,now=None):
    if not isinstance(user_id,str) or not 1<=len(user_id)<=200:raise ValueError("Conta invalida")
    now=int(time.time()) if now is None else int(now)
    with _LOCK:
        con=_connect()
        try:
            row=con.execute("SELECT tier,expires_at,suspended FROM subscriptions WHERE user_id=?",(user_id,)).fetchone()
            if not row:return {"tier":"gratis","expires_at":None,"state":"inactive"}
            tier,expiry,suspended=row
            return {"tier":tier,"expires_at":expiry,"state":plan_state(now,expiry,bool(suspended))}
        finally:con.close()

def renew(user_id,tier,months=1,now=None):
    if not isinstance(user_id,str) or not 1<=len(user_id)<=200:raise ValueError("Conta invalida")
    if tier not in VALID:raise ValueError("Plano invalido")
    now=int(time.time()) if now is None else int(now)
    with _LOCK:
        con=_connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            row=con.execute("SELECT expires_at,suspended FROM subscriptions WHERE user_id=?",(user_id,)).fetchone()
            expiry=expires_at(now,row[0] if row else None,months)
            con.execute("INSERT INTO subscriptions(user_id,tier,expires_at,suspended,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET tier=excluded.tier,expires_at=excluded.expires_at,updated_at=excluded.updated_at",(user_id,tier,expiry,0 if not row else row[1],now))
            con.commit()
            return status(user_id,now)
        except Exception:
            con.rollback();raise
        finally:con.close()

def suspend(user_id,blocked=True):
    with _LOCK:
        con=_connect()
        try:
            cur=con.execute("UPDATE subscriptions SET suspended=?,updated_at=? WHERE user_id=?",(int(bool(blocked)),int(time.time()),user_id))
            return cur.rowcount>0
        finally:con.close()
