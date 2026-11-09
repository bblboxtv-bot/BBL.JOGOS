"""BBLIA phone OTP service. Isolated prototype; not wired into production.

A configured SMS sender must deliver the OTP; this module never returns it to
the caller. Replace in-memory state with a shared transactional store before
deploying multiple workers/instances.
"""
import hashlib
import hmac
import os
import re
import secrets
import threading
import time

LOCK = threading.RLock()
PENDING = {}
ATTEMPTS = {}
TTL_SECONDS = 300
MAX_ATTEMPTS = 5
MAX_STARTS_PER_HOUR = 3

class PhoneAuthError(ValueError):
    pass

def normalize_phone(phone):
    if not isinstance(phone, str):
        raise PhoneAuthError("Telefone inválido.")
    phone = re.sub(r"[ ()-]", "", phone)
    if not re.fullmatch(r"\+[1-9][0-9]{7,14}", phone):
        raise PhoneAuthError("Use o telefone com DDI, por exemplo +55...")
    return phone

def _digest(phone, code, secret):
    return hmac.new(secret.encode(), (phone + ":" + code).encode(), hashlib.sha256).digest()

def request_code(phone, send_sms, *, now=None, secret=None):
    phone = normalize_phone(phone)
    now = time.time() if now is None else now
    secret = secret or os.environ.get("BBLIA_OTP_SECRET", "")
    if len(secret) < 32:
        raise PhoneAuthError("Serviço de verificação não configurado.")
    if not callable(send_sms):
        raise PhoneAuthError("Provedor SMS não configurado.")
    with LOCK:
        recent = [t for t in ATTEMPTS.get(phone, []) if t > now - 3600]
        if len(recent) >= MAX_STARTS_PER_HOUR:
            raise PhoneAuthError("Aguarde antes de solicitar outro código.")
        code = f"{secrets.randbelow(1000000):06d}"
        # Delivery must succeed before a verification attempt is enabled.
        send_sms(phone, "Seu código BBLIA é " + code + ". Válido por 5 minutos.")
        PENDING[phone] = {"digest": _digest(phone, code, secret),
                          "expires": now + TTL_SECONDS, "remaining": MAX_ATTEMPTS}
        ATTEMPTS[phone] = recent + [now]
    return {"sent": True, "expires_in": TTL_SECONDS}

def verify_code(phone, code, *, now=None, secret=None):
    phone = normalize_phone(phone)
    now = time.time() if now is None else now
    secret = secret or os.environ.get("BBLIA_OTP_SECRET", "")
    if not isinstance(code, str) or not re.fullmatch(r"[0-9]{6}", code):
        raise PhoneAuthError("Código inválido.")
    with LOCK:
        entry = PENDING.get(phone)
        if not entry or entry["expires"] <= now:
            PENDING.pop(phone, None)
            raise PhoneAuthError("Código expirado ou não solicitado.")
        entry["remaining"] -= 1
        valid = hmac.compare_digest(entry["digest"], _digest(phone, code, secret))
        if valid:
            PENDING.pop(phone, None)
            return {"verified": True, "subject": "phone:" + phone}
        if entry["remaining"] <= 0:
            PENDING.pop(phone, None)
        raise PhoneAuthError("Código incorreto.")
