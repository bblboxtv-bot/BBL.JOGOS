"""Isolated Facebook OAuth 2.0 helper for BBLIA.

Not wired to the HTTP server. Uses state-bound authorization and server-side
code exchange. Never accepts profile fields from the browser as identity.
"""
import json
import os
import secrets
import threading
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

AUTH_URL = "https://www.facebook.com/v21.0/dialog/oauth"
TOKEN_URL = "https://graph.facebook.com/v21.0/oauth/access_token"
PROFILE_URL = "https://graph.facebook.com/v21.0/me"
PENDING = {}
LOCK = threading.RLock()
TTL = 600

class FacebookAuthError(ValueError):
    pass

def configuration():
    app_id = os.environ.get("BBLIA_FACEBOOK_APP_ID", "").strip()
    secret = os.environ.get("BBLIA_FACEBOOK_APP_SECRET", "").strip()
    redirect = os.environ.get("BBLIA_FACEBOOK_REDIRECT_URI", "").strip()
    if not app_id or not secret or not redirect.startswith("https://"):
        raise FacebookAuthError("Login Facebook ainda não configurado.")
    return app_id, secret, redirect

def start(*, now=None):
    app_id, _, redirect = configuration()
    now = time.time() if now is None else now
    state = secrets.token_urlsafe(32)
    with LOCK:
        for key, entry in list(PENDING.items()):
            if entry["expires"] <= now:
                PENDING.pop(key, None)
        if len(PENDING) >= 1000:
            raise FacebookAuthError("Muitas autorizações simultâneas.")
        PENDING[state] = {"expires": now + TTL}
    return {"url": AUTH_URL + "?" + urlencode({
        "client_id": app_id,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": "public_profile,email",
        "state": state,
    }), "state": state}

def _get_json(url):
    with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=15) as response:
        data = response.read(65537)
    if len(data) > 65536:
        raise FacebookAuthError("Resposta do provedor inválida.")
    return json.loads(data)

def callback(state, code, *, now=None, request_json=None):
    now = time.time() if now is None else now
    if not isinstance(state, str) or not isinstance(code, str) or not code or len(code) > 4096:
        raise FacebookAuthError("Autorização inválida.")
    with LOCK:
        pending = PENDING.pop(state, None)
    if not pending or pending["expires"] <= now:
        raise FacebookAuthError("Autorização expirada ou reutilizada.")
    app_id, secret, redirect = configuration()
    fetch = request_json or _get_json
    try:
        token = fetch(TOKEN_URL + "?" + urlencode({
            "client_id": app_id, "client_secret": secret,
            "redirect_uri": redirect, "code": code}))
        access_token = token.get("access_token", "")
        if not access_token:
            raise FacebookAuthError("Provedor não confirmou a autorização.")
        profile = fetch(PROFILE_URL + "?" + urlencode({
            "fields": "id,name", "access_token": access_token}))
    except FacebookAuthError:
        raise
    except Exception as exc:
        raise FacebookAuthError("Não foi possível verificar a conta Facebook.") from exc
    subject = profile.get("id")
    if not isinstance(subject, str) or not subject.isdecimal() or len(subject) > 32:
        raise FacebookAuthError("Identidade Facebook inválida.")
    return {"subject": "facebook:" + subject, "name": str(profile.get("name", ""))[:150]}
