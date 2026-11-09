"""Guarded Google OAuth bridge for an isolated HTTPS-only BBLIA test host.

Never enable against the production or existing stage6 redirect. The caller
must mount these functions on a separate HTTPS host and set the exact callback.
"""
import os
from urllib.parse import urlsplit
try:
    import bblia_google as google
except ModuleNotFoundError:
    google = None

class IsolatedGoogleError(ValueError):
    pass

def require_isolated_config():
    redirect = os.getenv("GOOGLE_REDIRECT_URI", "").strip()
    allowed = os.getenv("BBLIA_ISOLATED_GOOGLE_ORIGIN", "").strip().rstrip("/")
    if os.getenv("BBLIA_ISOLATED_GOOGLE_OAUTH_ENABLED") != "1":
        raise IsolatedGoogleError("Google isolado desabilitado.")
    uri = urlsplit(redirect)
    origin = urlsplit(allowed)
    if (uri.scheme != "https" or not uri.netloc or uri.path != "/auth/google/callback"
        or uri.query or uri.fragment or origin.scheme != "https" or not origin.netloc
        or origin.path or origin.query or origin.fragment
        or uri.netloc.lower() != origin.netloc.lower()
        or uri.hostname in ("bblia-stage6-validacao.onrender.com", "bblia-teste.onrender.com")
        or not os.getenv("GOOGLE_CLIENT_ID") or not os.getenv("GOOGLE_CLIENT_SECRET")):
        raise IsolatedGoogleError("Configure uma origem HTTPS separada e credenciais OAuth de teste.")
    return redirect

def start():
    require_isolated_config()
    if google is None:
        raise IsolatedGoogleError("Dependências Google indisponíveis neste ambiente.")
    return google.start("", ["login"])

def complete(cookie_header, query):
    require_isolated_config()
    if google is None:
        raise IsolatedGoogleError("Dependências Google indisponíveis neste ambiente.")
    google_cookie = google.callback(cookie_header, query)
    verified = google.session(google_cookie)
    user = verified.get("user") if verified else None
    if (not isinstance(user, dict) or not isinstance(user.get("id"), str)
        or not user["id"] or user["id"].startswith("email:")
        or not verified.get("token")):
        raise IsolatedGoogleError("Identidade Google não confirmada.")
    return "google:" + user["id"]
