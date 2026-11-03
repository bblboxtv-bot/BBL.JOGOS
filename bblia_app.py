import os, json, urllib.request, urllib.error, secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
BASE=Path(__file__).resolve().parent
HTML=(BASE/'bblia_index.html').read_bytes()
class Handler(BaseHTTPRequestHandler):
 def reply(self,code,obj):
  body=json.dumps(obj,ensure_ascii=False).encode()
  self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def do_GET(self):
  if self.path in ('/','/index.html'):
   self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(HTML)));self.end_headers();self.wfile.write(HTML)
  elif self.path=='/health':self.reply(200,{'status':'ok','app':'BBLIA'})
  else:self.reply(404,{'error':'Nao encontrado'})
 def do_POST(self):
  if self.path!='/api/chat':return self.reply(404,{'error':'Nao encontrado'})
  password=os.getenv('BBLIA_TEST_PASSWORD','')
  if not password:return self.reply(503,{'error':'Teste bloqueado ate configurar senha no Render'})
  if not secrets.compare_digest(self.headers.get('X-BBLIA-Password',''),password):return self.reply(401,{'error':'Senha de teste incorreta'})
  try:
   length=int(self.headers.get('Content-Length','0'))
   if length<1 or length>25000:return self.reply(413,{'error':'Pedido muito grande'})
   data=json.loads(self.rfile.read(length))
   messages=data.get('messages',[])
   if not isinstance(messages,list) or not 1<=len(messages)<=12:return self.reply(400,{'error':'Historico invalido'})
   safe=[{'role':m['role'],'content':str(m['content'])[:3500]} for m in messages if isinstance(m,dict) and m.get('role') in ('user','assistant') and isinstance(m.get('content'),str)]
   if not safe or safe[-1]['role']!='user':return self.reply(400,{'error':'Mensagem invalida'})
   key=os.getenv('OPENAI_API_KEY','')
   if not key:return self.reply(503,{'error':'Chave OpenAI ainda nao configurada no servidor'})
   payload={'model':os.getenv('BBLIA_MODEL','gpt-4.1-mini'),'instructions':'Voce e a BBLIA. Responda em portugues brasileiro, de modo objetivo. Nao enrole, nao prometa execucao sem ferramentas. Seja util e direto.','input':safe,'max_output_tokens':700}
   req=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
   with urllib.request.urlopen(req,timeout=45) as r: result=json.load(r)
   answer='\n'.join(c.get('text','') for item in result.get('output',[]) for c in item.get('content',[]) if c.get('type')=='output_text')
   usage=result.get('usage',{})
   self.reply(200,{'answer':answer or 'Sem resposta textual.','usage':{'input':usage.get('input_tokens',0),'output':usage.get('output_tokens',0)}})
  except urllib.error.HTTPError as e:self.reply(502,{'error':'Falha da API OpenAI (HTTP %s)'%e.code})
  except Exception:self.reply(500,{'error':'Falha temporaria. Tente novamente.'})
if __name__=='__main__':
 ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','10000'))),Handler).serve_forever()
