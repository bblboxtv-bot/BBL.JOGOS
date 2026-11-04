import os, json, urllib.request, urllib.error, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, urlencode
BASE=Path(__file__).resolve().parent
HTML=(BASE/'bblia_index.html').read_bytes()
LIMIT_LOCK=threading.Lock()
REQUESTS={}
DAILY_TOTAL={'day':0,'count':0}
IN_FLIGHT=threading.BoundedSemaphore(2)
def weather_for(city):
 city=str(city).strip()[:90]
 if not city:return {'error':'Informe a cidade para consultar o tempo.'}
 headers={'User-Agent':'BBLIA/1.0'}
 geo='https://geocoding-api.open-meteo.com/v1/search?'+urlencode({'name':city,'count':1,'language':'pt','format':'json'})
 with urllib.request.urlopen(urllib.request.Request(geo,headers=headers),timeout=10) as res:g=json.load(res)
 places=g.get('results') or []
 if not places:return {'error':'Cidade nao encontrada. Peça outra cidade.'}
 p=places[0]
 url='https://api.open-meteo.com/v1/forecast?'+urlencode({'latitude':p['latitude'],'longitude':p['longitude'],'current':'temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m','daily':'temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code','timezone':'auto','forecast_days':3})
 with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=10) as res:f=json.load(res)
 return {'local':p.get('name'),'estado':p.get('admin1'),'pais':p.get('country'),'atual':f.get('current'),'proximos_dias':f.get('daily'),'fonte':'Open-Meteo','consulta':'dados meteorologicos atualizados'}
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
   instructions='Voce e a BBLIA, assistente em portugues brasileiro orientada a resolver tarefas. Seja objetiva e proativa. Use informacoes ja fornecidas e nao repita perguntas. Voce tem uma ferramenta de previsao do tempo: use-a sempre que solicitarem clima ou previsao. Se o usuario nao informar cidade e ela nao constar do contexto, pergunte a cidade. Nao invente dados atualizados. Para instalar aplicativo, controlar TV Box, alterar painel, acessar computador ou recuperar senha, nao afirme execucao sem integracao e autorizacao. Recuperacao de senhas exige autenticacao; nao solicite nem exponha senhas. Faca uma unica pergunta indispensavel. Nunca afirme ter concluido uma tarefa sem confirmacao verificavel.'
   tools=[{'type':'function','name':'consultar_tempo','description':'Consultar temperatura e previsao meteorologica atualizada de uma cidade usando Open-Meteo','parameters':{'type':'object','properties':{'cidade':{'type':'string','description':'Nome da cidade, preferencialmente com estado e pais'}} ,'required':['cidade'],'additionalProperties':False}}]
   payload={'model':os.getenv('BBLIA_MODEL','gpt-4.1-mini'),'instructions':instructions,'input':safe,'tools':tools,'max_output_tokens':700}
   req=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
   with urllib.request.urlopen(req,timeout=45) as r:result=json.load(r)
   calls=[item for item in result.get('output',[]) if item.get('type')=='function_call' and item.get('name')=='consultar_tempo']
   if calls:
    outputs=[]
    for item in calls[:2]:
     try:
      args=json.loads(item.get('arguments','{}'))
      forecast=weather_for(args.get('cidade',''))
     except Exception:forecast={'error':'Consulta meteorologica indisponivel neste momento'}
     outputs.append({'type':'function_call_output','call_id':item['call_id'],'output':json.dumps(forecast,ensure_ascii=False)})
    follow={'model':payload['model'],'instructions':instructions,'previous_response_id':result['id'],'input':outputs,'max_output_tokens':700}
    req2=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(follow).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req2,timeout=45) as r:result=json.load(r)
   answer='\\n'.join(c.get('text','') for item in result.get('output',[]) for c in item.get('content',[]) if c.get('type')=='output_text')
   usage=result.get('usage',{})
   self.reply(200,{'answer':answer or 'Sem resposta textual.','usage':{'input':usage.get('input_tokens',0),'output':usage.get('output_tokens',0)}})
  except urllib.error.HTTPError as e:self.reply(502,{'error':'Falha da API OpenAI (HTTP %s)'%e.code})
  except Exception:self.reply(500,{'error':'Falha temporaria. Tente novamente.'})
if __name__=='__main__':
 ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','10000'))),Handler).serve_forever()
