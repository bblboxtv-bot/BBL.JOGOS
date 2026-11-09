"""Isolated HTTP adapter for BBLIA identity sessions.

Only mount on a dedicated staging server after configuring durable database.
Does not issue sessions from unverified browser claims.
"""
import json
from http.cookies import SimpleCookie
import bblia_session_sqlite as store

COOKIE_NAME = "__Host-bblia_session"

def read_cookie(header):
    jar = SimpleCookie()
    try:
        jar.load(header or "")
        item = jar.get(COOKIE_NAME)
        return item.value if item else None
    except Exception:
        return None

def status(db_path, cookie_header, *, now=None):
    sid = read_cookie(cookie_header)
    session = store.load(db_path, sid, now=now) if sid else None
    if not session:
        return {"authenticated": False, "provider": None}
    return {"authenticated": True, "provider": session["provider"],
            "subject": session["subject"]}

def login_verified(db_path, provider, verified_subject, *, now=None):
    # Must only be called after provider token/code has been validated server-side.
    sid = store.create(db_path, provider, verified_subject, now=now)
    return {"authenticated": True, "provider": provider}, (
        COOKIE_NAME + "=" + sid + "; Path=/; Max-Age=" + str(store.TTL)
        + "; Secure; HttpOnly; SameSite=Lax"
    )

def logout(db_path, cookie_header):
    sid = read_cookie(cookie_header)
    if sid:
        store.revoke(db_path, sid)
    return {"authenticated": False}, (
        COOKIE_NAME + "=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax"
    )
