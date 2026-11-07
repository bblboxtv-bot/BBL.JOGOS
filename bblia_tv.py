"""Fixed-host relay; device-scoped credentials never enter model context."""
import json,re,urllib.request,urllib.error
BASE='https://152.67.55.60'
class TVError(Exception):
 def __init__(self,message,status=502):super().__init__(message);self.status=status
def relay(operation,data):
 if not isinstance(data,dict):raise TVError('Pedido inválido',400)
 token=str(data.get('token',''))
 if operation=='exchange':path='/api/agent/owner/exchange';payload={'code':str(data.get('code',''))[:100]}
 elif operation=='command':path='/api/agent/owner/command';payload={'text':str(data.get('text',''))[:1000]}
 elif operation=='job':
  jid=str(data.get('id',''))
  if not re.fullmatch(r'[A-Za-z0-9_-]{12,80}',jid):raise TVError('Comando inválido',400)
  path='/api/agent/owner/jobs/'+jid;payload=None
 else:raise TVError('Operação inválida',400)
 headers={'Content-Type':'application/json'}
 if operation!='exchange':
  if not re.fullmatch(r'[A-Za-z0-9_-]{30,100}',token):raise TVError('Vincule a TV Box no menu da BBLIA',401)
  headers['Authorization']='Bearer '+token
 req=urllib.request.Request(BASE+path,data=json.dumps(payload).encode() if payload is not None else None,headers=headers)
 try:
  with urllib.request.urlopen(req,timeout=18) as response:return json.load(response)
 except urllib.error.HTTPError as exc:
  try:message=json.load(exc).get('detail','Falha na conexão com a TV Box')
  except Exception:message='Falha na conexão com a TV Box'
  raise TVError(str(message)[:500],exc.code) from exc
 except OSError as exc:raise TVError('Não foi possível acessar o painel da TV Box agora') from exc
