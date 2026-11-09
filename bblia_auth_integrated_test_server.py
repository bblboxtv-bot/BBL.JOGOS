"""Local-only BBLIA login preview server. Never expose on public network.

Serves the isolated login screen, session status and logout. Provider routes
fail closed until credentials, verified callbacks and SMS transport are wired.
"""
import json
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from http.cookies import SimpleCookie
import bblia_auth_http_stage as auth
import bblia_session_sqlite as sessions
import bblia_facebook_auth as facebook
import bblia_phone_auth as phone
import bblia_google_isolated_bridge as google_bridge

BASE = Path(__file__).resolve().parent
HTML = (BASE / "bblia_login_visual_demo.html").read_bytes()\nLOGO = __import__("base64").b64decode((BASE / "bblia_login_logo_base64.txt").read_text().strip())
DB = Path(os.environ.get("BBLIA_ISOLATED_SESSION_DB", str(BASE / "preview_sessions.sqlite3")))

class Handler(BaseHTTPRequestHandler):
    def reply(self, code, payload, cookie=None):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'self'")
            self.send_header("Content-Length", str(len(HTML)))
            self.end_headers()
            self.wfile.write(HTML)
        elif path == "/logo.webp":
            self.send_response(200)
            self.send_header("Content-Type", "image/webp")
            self.send_header("Cache-Control", "public, max-age=3600")
            self.send_header("Content-Length", str(len(LOGO)))
            self.end_headers()
            self.wfile.write(LOGO)
        elif path == "/auth/facebook/callback":
            query = parse_qs(urlsplit(self.path).query)
            state = query.get("state", [""])[0]
            code = query.get("code", [""])[0]
            jar = SimpleCookie()
            try:
                jar.load(self.headers.get("Cookie", ""))
                expected = jar.get("__Host-bblia_fb_state")
                valid = expected and secrets.compare_digest(expected.value, state)
            except Exception:
                valid = False
            if not valid:
                return self.reply(403, {"error": "Estado de autorização inválido."})
            try:
                verified = facebook.callback(state, code)
                _, session_cookie = auth.login_verified(str(DB), "facebook", verified["subject"])
            except (facebook.FacebookAuthError, ValueError):
                return self.reply(401, {"error": "Não foi possível confirmar a conta Facebook."})
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", session_cookie)
            self.send_header("Set-Cookie", "__Host-bblia_fb_state=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path == "/auth/google/callback":
            try:
                subject = google_bridge.complete(self.headers.get("Cookie", ""), urlsplit(self.path).query)
                _, session_cookie = auth.login_verified(str(DB), "google", subject)
            except (google_bridge.IsolatedGoogleError, ValueError):
                return self.reply(403, {"error": "Não foi possível confirmar a conta Google neste teste."})
            except Exception:
                return self.reply(503, {"error": "Autenticação Google temporariamente indisponível."})
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie", session_cookie)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif path == "/api/auth/status":
            self.reply(200, auth.status(str(DB), self.headers.get("Cookie", "")))
        else:
            self.reply(404, {"error": "Não encontrado."})

    def do_POST(self):
        path = urlsplit(self.path).path
        fetch_site = self.headers.get("Sec-Fetch-Site", "")
        if fetch_site and fetch_site not in ("same-origin", "none"):
            return self.reply(403, {"error": "Solicitação entre sites bloqueada."})
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if origin and origin not in ("http://" + host, "https://" + host):
            return self.reply(403, {"error": "Origem não autorizada."})
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            return self.reply(415, {"error": "Envie JSON."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 2 <= length <= 4096:
                return self.reply(400, {"error": "Pedido inválido."})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                return self.reply(400, {"error": "Pedido inválido."})
        except (ValueError, TypeError):
            return self.reply(400, {"error": "Pedido inválido."})
        if path == "/api/auth/logout":
            result, cookie = auth.logout(str(DB), self.headers.get("Cookie", ""))
            return self.reply(200, result, cookie)
        if path == "/api/auth/facebook/start":
            try:
                result = facebook.start()
                body = json.dumps({"url": result["url"]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Set-Cookie", "__Host-bblia_fb_state=" + result["state"] + "; Path=/; Max-Age=600; Secure; HttpOnly; SameSite=Lax")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            except facebook.FacebookAuthError:
                return self.reply(503, {"error": "Facebook ainda não configurado neste teste."})
        if path == "/api/auth/phone/request":
            return self.reply(503, {"error": "SMS ainda não configurado neste teste."})
        if path == "/api/auth/phone/verify":
            try:
                verified = phone.verify_code(data.get("phone"), data.get("code"))
                result, cookie = auth.login_verified(str(DB), "phone", verified["subject"])
                return self.reply(200, result, cookie)
            except phone.PhoneAuthError:
                return self.reply(401, {"error": "Código inválido ou expirado."})
        if path == "/api/account/start":
            try:
                result, cookie = google_bridge.start()
                return self.reply(200, {"url": result["url"]}, cookie)
            except google_bridge.IsolatedGoogleError:
                return self.reply(503, {"error": "Google ainda não configurado neste teste isolado."})
            except Exception:
                return self.reply(503, {"error": "Google temporariamente indisponível."})
        return self.reply(404, {"error": "Não encontrado."})

def serve(host="127.0.0.1", port=8765):
    if host not in ("127.0.0.1", "localhost", "::1") and os.getenv("BBLIA_ISOLATED_PUBLIC_SERVER") != "1":
        raise ValueError("Preview permitido apenas em loopback.")
    sessions.initialize(str(DB))
    server = ThreadingHTTPServer((host, port), Handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()

if __name__ == "__main__":
    serve("0.0.0.0" if os.getenv("BBLIA_ISOLATED_PUBLIC_SERVER") == "1" else "127.0.0.1", int(os.getenv("PORT", "8765")))
