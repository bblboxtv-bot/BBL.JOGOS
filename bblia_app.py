import os, json, urllib.request, urllib.error, threading, time, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, urlencode
BASE=Path(__file__).resolve().parent
HTML=(BASE/'bblia_index.html').read_bytes()
LOGO=(BASE/'bblia_logo.svg').read_bytes()
LIMIT_LOCK=threading.Lock()
REQUESTS={}
DAILY_TOTAL={'day':0,'count':0}
IN_FLIGHT=threading.BoundedSemaphore(2)
TTS_REQUESTS={}
TTS_DAILY={'day':0,'count':0}
TTS_IN_FLIGHT=threading.BoundedSemaphore(1)
def weather_for(city):
 city=str(city).strip()[:90]
 if not city:return {'error':'Informe a cidade para consultar o tempo.'}
 match=re.fullmatch(r'(-?[0-9]{1,2}[.][0-9]+), *(-?[0-9]{1,3}[.][0-9]+)',city)
 if match:
  lat,lon=map(float,match.groups())
  if not (-90<=lat<=90 and -180<=lon<=180):return {'error':'Coordenadas invalidas'}
  p={'name':'localizacao autorizada','latitude':round(lat,2),'longitude':round(lon,2)}
 else:p=None
 headers={'User-Agent':'BBLIA/1.0'}
 geo='https://geocoding-api.open-meteo.com/v1/search?'+urlencode({'name':city,'count':1,'language':'pt','format':'json'})
 if p is None:
  with urllib.request.urlopen(urllib.request.Request(geo,headers=headers),timeout=10) as res:g=json.load(res)
  places=g.get('results') or []
  if not places:return {'error':'Cidade nao encontrada. Peça outra cidade.'}
  p=places[0]
 url='https://api.open-meteo.com/v1/forecast?'+urlencode({'latitude':p['latitude'],'longitude':p['longitude'],'current':'temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m','daily':'temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code','timezone':'auto','forecast_days':3})
 with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=10) as res:f=json.load(res)
 return {'local':p.get('name'),'estado':p.get('admin1'),'pais':p.get('country'),'atual':f.get('current'),'proximos_dias':f.get('daily'),'fonte':'Open-Meteo','consulta':'dados meteorologicos atualizados'}
def mega_sena(concurso=None):
 base='https://servicebus2.caixa.gov.br/portaldeloterias/api/megasena'
 url=base+('/'+str(int(concurso)) if concurso else '')
 req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
 with urllib.request.urlopen(req,timeout=12) as res:data=json.load(res)
 return {'concurso':data.get('numero'),'data':data.get('dataApuracao'),'dezenas':data.get('listaDezenas'),'acumulou':data.get('acumulado'),'proximo_concurso':data.get('numeroConcursoProximo'),'proximo_sorteio':data.get('dataProximoConcurso'),'fonte':'CAIXA Loterias'}
class Handler(BaseHTTPRequestHandler):
 def reply(self,code,obj):
  body=json.dumps(obj,ensure_ascii=False).encode()
  self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def do_GET(self):
  if urlsplit(self.path).path in ('/','/index.html'):
   self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store, max-age=0');self.send_header('Content-Length',str(len(HTML)));self.end_headers();self.wfile.write(HTML)
  elif urlsplit(self.path).path=='/bblia_logo.svg':
   self.send_response(200);self.send_header('Content-Type','image/svg+xml');self.send_header('Cache-Control','public, max-age=86400');self.send_header('Content-Length',str(len(LOGO)));self.end_headers();self.wfile.write(LOGO)
  elif urlsplit(self.path).path=='/health':self.reply(200,{'status':'ok','app':'BBLIA'})
  elif urlsplit(self.path).path=='/api/lottery':
   try:
    from urllib.parse import parse_qs
    contest=parse_qs(urlsplit(self.path).query).get('contest',[''])[0]
    if contest and (not contest.isdigit() or len(contest)>6):return self.reply(400,{'error':'Concurso invalido'})
    self.reply(200,mega_sena(contest or None))
   except Exception:self.reply(502,{'error':'Resultado oficial indisponivel no momento'})
  elif urlsplit(self.path).path=='/api/weather':
   try:
    from urllib.parse import parse_qs
    city=parse_qs(urlsplit(self.path).query).get('location',[''])[0]
    self.reply(200,weather_for(city))
   except Exception:self.reply(502,{'error':'Servico meteorologico temporariamente indisponivel'})
  else:self.reply(404,{'error':'Nao encontrado'})
 def do_POST(self):
  if self.path=='/api/voice':return self.voice_audio()
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
 def voice_audio(self):
  key=os.getenv('OPENAI_API_KEY','')
  if not key:return self.reply(503,{'error':'Voz natural indisponivel'})
  try:
   length=int(self.headers.get('Content-Length','0'))
   if length<1 or length>1500:return self.reply(413,{'error':'Texto muito longo'})
   payload=json.loads(self.rfile.read(length))
   text=str(payload.get('text','')).strip()
   voice=str(payload.get('voice','nova'))
   if not text or len(text)>350 or voice not in ('nova','onyx','shimmer','echo'):return self.reply(400,{'error':'Parametros invalidos'})
   ip=self.headers.get('X-Forwarded-For','').split(',')[0].strip() or self.client_address[0]
   day=int(time.time()//86400)
   with LIMIT_LOCK:
    if TTS_DAILY['day']!=day:
     TTS_DAILY.update(day=day,count=0)
     TTS_REQUESTS.clear()
    if TTS_REQUESTS.get(ip,0)>=4 or TTS_DAILY['count']>=25:return self.reply(429,{'error':'Limite de voz de teste atingido'})
    TTS_REQUESTS[ip]=TTS_REQUESTS.get(ip,0)+1
    TTS_DAILY['count']+=1
   if not TTS_IN_FLIGHT.acquire(blocking=False):return self.reply(429,{'error':'Voz ocupada'})
   try:
    req=urllib.request.Request('https://api.openai.com/v1/audio/speech',data=json.dumps({'model':'tts-1','voice':voice,'input':text,'response_format':'mp3'}).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=25) as res:audio=res.read(600000)
    if not audio or len(audio)>=600000:return self.reply(502,{'error':'Audio indisponivel'})
    self.send_response(200);self.send_header('Content-Type','audio/mpeg');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(audio)));self.end_headers();self.wfile.write(audio)
   finally:TTS_IN_FLIGHT.release()
  except urllib.error.HTTPError as e:
   self.reply(503,{'error':'Servico de voz indisponivel no momento'})
  except Exception:self.reply(502,{'error':'Nao foi possivel gerar a voz'})
 def call_openai(self,key,safe):
  try:
   instructions='Voce e a BBLIA, assistente em portugues brasileiro orientada a resolver tarefas. Seja objetiva e proativa. Use informacoes ja fornecidas e nao repita perguntas. Voce tem ferramentas para previsao do tempo, resultado da Mega-Sena e pesquisa na internet. Use-as sempre que solicitarem dados atuais. Para resultados de loteria, prefira a ferramenta oficial da CAIXA. Para perguntas sobre documentacao e tecnologia, pesquise na web quando necessario. Se o usuario fornecer coordenadas geograficas autorizadas no formato latitude,longitude, use-as como valor da cidade na ferramenta de clima, sem perguntar a cidade. Caso contrario, pergunte a cidade. Nao invente dados atualizados. Para instalar aplicativo, controlar TV Box, alterar painel, acessar computador ou recuperar senha, nao afirme execucao sem integracao e autorizacao. Recuperacao de senhas exige autenticacao; nao solicite nem exponha senhas. Faca uma unica pergunta indispensavel. Nunca afirme ter concluido uma tarefa sem confirmacao verificavel.'
   tools=[{'type':'function','name':'consultar_tempo','description':'Consultar temperatura e previsao meteorologica atualizada de uma cidade usando Open-Meteo','parameters':{'type':'object','properties':{'cidade':{'type':'string','description':'Nome da cidade, preferencialmente com estado e pais'}} ,'required':['cidade'],'additionalProperties':False}}]
   tools.append({'type':'function','name':'consultar_mega_sena','description':'Consultar resultados oficiais da Mega-Sena da CAIXA, ultimo sorteio ou numero de concurso','parameters':{'type':'object','properties':{'concurso':{'type':['integer','null'],'description':'Numero do concurso ou null para o mais recente'}},'required':['concurso'],'additionalProperties':False}})
   tools.append({'type':'web_search_preview'})
   # Force source-backed lookup for questions about current officials and public affairs.
   recent_terms=('lula','presidente','governo','ministro','eleiç','eleic','política','politica','notícia','noticia','hoje','atual','2026','bolsonaro')
   needs_fresh=any(term in safe[-1]['content'].lower() for term in recent_terms)
   if needs_fresh:instructions+=' Hoje e 03/11/2026. Para pessoas publicas, cargos, mandatos, politica e noticias, consulte a web antes de responder; inclua fontes e datas. Lula assumiu mandatos em 2003, 2007 e 2023; nunca afirme que 2013 foi inicio de mandato. Se a busca falhar, diga que nao conseguiu confirmar o estado atual.'
   payload={'model':os.getenv('BBLIA_MODEL','gpt-4.1-mini'),'instructions':instructions,'input':safe,'tools':tools,'max_output_tokens':700}
   req=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
   with urllib.request.urlopen(req,timeout=45) as r:result=json.load(r)
   for _ in range(2):
    calls=[item for item in result.get('output',[]) if item.get('type')=='function_call' and item.get('name') in ('consultar_tempo','consultar_mega_sena')]
    if not calls:break
    outputs=[]
    for item in calls[:2]:
     try:
      args=json.loads(item.get('arguments','{}'))
      if item['name']=='consultar_tempo':info=weather_for(args.get('cidade',''))
      else:info=mega_sena(args.get('concurso'))
     except Exception:info={'error':'Fonte oficial indisponivel neste momento. Nao invente resultados.'}
     outputs.append({'type':'function_call_output','call_id':item['call_id'],'output':json.dumps(info,ensure_ascii=False)})
    follow={'model':payload['model'],'instructions':instructions,'previous_response_id':result['id'],'input':outputs,'tools':tools,'max_output_tokens':700}
    req2=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(follow).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req2,timeout=45) as r:result=json.load(r)
   answer='\n'.join(c.get('text','') for item in result.get('output',[]) for c in item.get('content',[]) if c.get('type')=='output_text')
   usage=result.get('usage',{})
   self.reply(200,{'answer':answer or 'Sem resposta textual.','usage':{'input':usage.get('input_tokens',0),'output':usage.get('output_tokens',0)}})
  except urllib.error.HTTPError as e:
   try:
    details=json.loads(e.read(2048)).get('error',{})
    code=details.get('code','')
   except Exception:code=''
   if e.code==429:self.reply(503,{'error':'Limite ou saldo da API OpenAI atingido. Verifique os creditos antes de continuar.'})
   elif e.code==401:self.reply(503,{'error':'Chave da API OpenAI invalida ou sem permissao.'})
   elif e.code==400:self.reply(502,{'error':'Configuracao de modelo ou ferramenta incompatível na API.','codigo':str(code)[:60]})
   else:self.reply(502,{'error':'Falha da API OpenAI (HTTP %s)'%e.code})
  except Exception:self.reply(500,{'error':'Falha temporaria. Tente novamente.'})
if __name__=='__main__':
 ThreadingHTTPServer(('0.0.0.0',int(os.getenv('PORT','10000'))),Handler).serve_forever()
