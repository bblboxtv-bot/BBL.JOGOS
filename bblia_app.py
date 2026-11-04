import os, json, urllib.request, urllib.error, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
BASE=Path(__file__).resolve().parent
HTML=(BASE/'bblia_index.html').read_bytes()
LIMIT_LOCK=threading.Lock()
REQUESTS={}
DAILY_TOTAL={'day':0,'count':0}
IN_FLIGHT=threading.BoundedSemaphore(2)
class Handler(BaseHTTPRequestHandler):
 def reply(self,code,obj):
  body=json.dumps(obj,ensure_ascii=False).encode()
  self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def do_GET(self):
  if urlsplit(self.path).path in ('/','/index.html'):
   self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store, max-age=0');self.send_header('Content-Length',str(len(HTML)));self.end_headers();self.wfile.write(HTML)
  elif urlsplit(self.path).path=='/health':self.reply(200,{'status':'ok','app':'BBLIA'})
  else:self.reply(404,{'error':'Nao encontrado'})
 def do_POST(self):
  if self.path!='/api/chat':return self.reply(404,{'error':'Nao encontrado'})
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
   # Temporary free-preview guard: 3 requests per IP/day and 60 globally/day.
   # Counts attempted requests to prevent abuse; resets on restart.
   ip=self.headers.get('X-Forwarded-For','').split(',')[0].strip() or self.client_address[0]
   day=int(time.time()//86400)
   with LIMIT_LOCK:
    if DAILY_TOTAL['day']!=day:
     DAILY_TOTAL.update(day=day,count=0)
     REQUESTS.clear()
    if REQUESTS.get(ip,0)>=3:return self.reply(429,{'error':'Limite gratuito de 3 mensagens por dia atingido.'})
    if DAILY_TOTAL['count']>=60:return self.reply(429,{'error':'Limite de testes do dia atingido. Tente amanha.'})
    REQUESTS[ip]=REQUESTS.get(ip,0)+1
    DAILY_TOTAL['count']+=1
   if not IN_FLIGHT.acquire(blocking=False):return self.reply(429,{'error':'Servidor ocupado. Tente novamente em instantes.'})
   try:
    self.call_openai(key,safe)
   finally:
    IN_FLIGHT.release()
  except Exception:
   self.reply(500,{'error':'Falha temporaria. Tente novamente.'})
 def call_openai(self,key,safe):
  try:
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
