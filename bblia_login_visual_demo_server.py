"""Public visual test only: no account data, login, SMS or payments."""
import os, base64, json
from pathlib import Path
from urllib.parse import urlsplit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
ROOT=Path(__file__).resolve().parent
HTML=(ROOT/"bblia_login_visual_demo.html").read_bytes()
LOGO=base64.b64decode((ROOT/"bblia_login_logo_base64.txt").read_text().strip())
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  if urlsplit(self.path).path=="/":
   body,typ,status=HTML,"text/html; charset=utf-8",200
  elif urlsplit(self.path).path=="/logo.webp":
   body,typ,status=LOGO,"image/webp",200
  elif urlsplit(self.path).path=="/api/auth/status":
   body,typ,status=b'{"authenticated":false}',"application/json",200
  else:
   body,typ,status=b'{"error":"Nao encontrado"}',"application/json",404
  self.send_response(status);self.send_header("Content-Type",typ);self.send_header("Cache-Control","no-store");self.send_header("X-Content-Type-Options","nosniff");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
 def do_POST(self):
  body=json.dumps({"error":"Demonstração visual: autenticação real ainda não habilitada. Nenhum SMS ou cobrança foi enviado."},ensure_ascii=False).encode()
  self.send_response(503);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Cache-Control","no-store");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)
if __name__=="__main__":
 ThreadingHTTPServer(("0.0.0.0",int(os.getenv("PORT","10000"))),Handler).serve_forever()
