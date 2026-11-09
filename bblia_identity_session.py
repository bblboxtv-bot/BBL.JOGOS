"""Provider-neutral BBLIA session store for isolated authentication tests.

Prototype only. Store is process-local; replace with durable shared storage
before enabling accounts on Render. Provider identity is server-verified.
"""
import secrets
import threading
import time

LOCK = threading.RLock()
SESSIONS = {}
TTL = 30 * 24 * 3600

class SessionError(ValueError):
    pass

def create(provider, subject, *, now=None):
    if provider not in ("google", "facebook", "phone"):
        raise SessionError("Provedor não autorizado.")
    if not isinstance(subject, str) or not subject.startswith(provider + ":"):
        raise SessionError("Identidade não verificada.")
    now = time.time() if now is None else now
    sid = secrets.token_urlsafe(32)
    with LOCK:
        SESSIONS[sid] = {"subject": subject, "provider": provider,
                         "expires": now + TTL}
    return sid

def get(sid, *, now=None):
    if not isinstance(sid, str) or not sid:
        return None
    now = time.time() if now is None else now
    with LOCK:
        session = SESSIONS.get(sid)
        if not session:
            return None
        if session["expires"] <= now:
            SESSIONS.pop(sid, None)
            return None
        return dict(session)

def logout(sid):
    with LOCK:
        return SESSIONS.pop(sid, None) is not None

def cookie(sid, *, max_age=TTL):
    if not isinstance(sid, str) or (sid and not all(c.isalnum() or c in "-_" for c in sid)):
        raise SessionError("Identificador de sessão inválido.")
    return "__Host-bblia_session=" + sid + "; Path=/; Max-Age=" + str(max_age) + "; Secure; HttpOnly; SameSite=Lax"
