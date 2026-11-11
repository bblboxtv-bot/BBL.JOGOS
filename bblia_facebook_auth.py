"""Isolated Facebook OAuth 2.0 helper for BBLIA.

Not wired to the HTTP server. Uses state-bound authorization and server-side
code exchange. Never accepts profile fields from the browser as identity.
"""
import json
import os
import secrets
import threading
import time
from urllib.parse import urlencode, urlsplit
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
    uri = urlsplit(redirect)
    allowed = urlsplit(os.environ.get("BBLIA_ISOLATED_GOOGLE_ORIGIN", "").strip())
    if (not app_id or not secret or uri.scheme != "https"
        or uri.path != "/auth/facebook/callback" or uri.query or uri.fragment
        or not uri.netloc or allowed.scheme != "https"
        or uri.netloc.lower() != allowed.netloc.lower()
        or uri.hostname in ("bblia-stage6-validacao.onrender.com", "bblia-teste.onrender.com")):
        raise FacebookAuthError("Login Facebook ainda não configurado.")
    return app_id, secret, redirect

def _session_digest(session_key):
    """Bind the OAuth transaction to an opaque server-side browser session key."""
    import hashlib
    if not isinstance(session_key, str) or len(session_key) < 32 or len(session_key) > 512:
        raise FacebookAuthError("Sessão de autenticação inválida.")
    return hashlib.sha256(session_key.encode("utf-8")).hexdigest()

def start(*, session_key, now=None):
    digest = _session_digest(session_key)
    app_id, _, redirect = configuration()
    now = time.time() if now is None else now
    state = secrets.token_urlsafe(32)
    with LOCK:
        for key, entry in list(PENDING.items()):
            if entry["expires"] <= now:
                PENDING.pop(key, None)
        if len(PENDING) >= 1000:
            raise FacebookAuthError("Muitas autorizações simultâneas.")
        PENDING[state] = {"expires": now + TTL, "session_digest": digest}
    return {"url": AUTH_URL + "?" + urlencode({
        "client_id": app_id,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": "public_profile,email",
        "state": state,
    }), "state": state}

def _get_json(url, *, data=None, headers=None):
    request_headers = {"Accept": "application/json", **(headers or {})}
    if data is not None:
        request_headers["Content-Type"] = "application/x-www-form-urlencoded"
    with urlopen(Request(url, data=data, headers=request_headers), timeout=15) as response:
        data = response.read(65537)
    if len(data) > 65536:
        raise FacebookAuthError("Resposta do provedor inválida.")
    return json.loads(data)

def callback(state, code, *, session_key, now=None, request_json=None):
    digest = _session_digest(session_key)
    now = time.time() if now is None else now
    if not isinstance(state, str) or not isinstance(code, str) or not code or len(code) > 4096:
        raise FacebookAuthError("Autorização inválida.")
    with LOCK:
        pending = PENDING.pop(state, None)
    if not pending or pending["expires"] <= now or not secrets.compare_digest(pending["session_digest"], digest):
        raise FacebookAuthError("Autorização expirada ou reutilizada.")
    app_id, secret, redirect = configuration()
    fetch = request_json or _get_json
    try:
        token = fetch(TOKEN_URL, data=urlencode({
            "client_id": app_id, "client_secret": secret,
            "redirect_uri": redirect, "code": code}).encode("ascii"))
        if not isinstance(token, dict):
            raise FacebookAuthError("Resposta de autorização Facebook inválida.")
        access_token = token.get("access_token", "")
        if not isinstance(access_token, str) or not access_token:
            raise FacebookAuthError("Provedor não confirmou a autorização.")
        if len(access_token) > 8192:
            raise FacebookAuthError("Provedor não confirmou a autorização.")
        profile = fetch(PROFILE_URL + "?fields=id%2Cname",
                        headers={"Authorization": "Bearer " + access_token})
    except FacebookAuthError:
        raise
    except Exception as exc:
        raise FacebookAuthError("Não foi possível verificar a conta Facebook.") from exc
    if not isinstance(profile, dict):
        raise FacebookAuthError("Resposta de identidade Facebook inválida.")
    subject = profile.get("id")
    if not isinstance(subject, str) or not subject or (not subject.isascii() or not subject.isdecimal()) or len(subject) > 32:
        raise FacebookAuthError("Identidade Facebook inválida.")
    return {"subject": "facebook:" + subject, "name": str(profile.get("name", ""))[:150]}
