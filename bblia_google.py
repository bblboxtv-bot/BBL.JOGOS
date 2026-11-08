"""Google OAuth and account-isolated, read-only tools. Secrets never reach JS.
Sessions are intentionally in memory; restart requires reconnection.
"""
import os, time, json, secrets, hashlib, base64, threading
import bblia_email_auth as email_auth
from http.cookies import SimpleCookie
from urllib.parse import urlencode, parse_qs, urlsplit, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError

SCOPES = {'email': 'https://www.googleapis.com/auth/gmail.readonly',
          'calendar': 'https://www.googleapis.com/auth/calendar.readonly',
          'drive': 'https://www.googleapis.com/auth/drive.readonly',
          'login': 'openid', 'sync': 'https://www.googleapis.com/auth/drive.appdata'}
SESSIONS = {}
LOCK = threading.RLock()
TTL = 12 * 3600
class GoogleError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message); self.status = status

def config():
    return (os.getenv('GOOGLE_CLIENT_ID','').strip(), os.getenv('GOOGLE_CLIENT_SECRET','').strip(),
            os.getenv('GOOGLE_REDIRECT_URI','https://bblia-teste.onrender.com/google-callback').strip())

def session(cookie):
    local=email_auth.session(cookie)
    if local:return local
    try:
        c=SimpleCookie(); c.load(cookie or ''); sid=c.get('__Host-bblia_google')
        sid=sid.value if sid else ''
    except Exception: return None
    with LOCK:
        value=SESSIONS.get(sid)
        if value and value['expires']>time.time(): return value
        SESSIONS.pop(sid,None)
    return None

def cookie_value(sid, age=TTL):
    return '__Host-bblia_google='+sid+'; Path=/; Max-Age='+str(age)+'; Secure; HttpOnly; SameSite=Lax'

def status(cookie):
    client,secret,redirect=config(); s=session(cookie)
    configured=bool(client and secret and redirect.startswith('https://'))
    user = s.get('user') if s and s.get('token') else None
    owner_email = os.getenv('BBLIA_ADMIN_EMAIL', 'bbl.boxtv@gmail.com').strip().casefold()
    # A local account may be admin only when its immutable, server-configured user ID matches.
    # Email address alone is insufficient until ownership verification is implemented.
    admin_user_id = os.getenv('BBLIA_ADMIN_USER_ID','').strip()
    local_owner = bool(user and admin_user_id and secrets.compare_digest(str(user.get('id','')),admin_user_id))
    google_owner = bool(user and not str(user.get('id','')).startswith('email:') and user.get('email','').strip().casefold()==owner_email)
    role = ('admin' if local_owner or google_owner else 'client') if user else 'guest'
    return {'configured': configured, 'email_login_available': True, 'email_registration_enabled':os.getenv('BBLIA_EMAIL_REGISTRATION','disabled')=='enabled', 'connected': bool(user), 'authenticated': bool(user), 'role': role, 'user': user,
            'services': [k for k,v in SCOPES.items() if s and v in s.get('scopes',[])],
            'detail': ('Cadastro Google da BBLIA pendente: configurar cliente OAuth no servidor.' if not configured else
                       'Conexão disponível. Escolha os serviços e autorize sua conta Google.'),
            'session_note':'Conexão privada neste navegador por até 12 horas. Reinícios do servidor exigem reconectar.'}

def check_origin(headers):
    expected=urlsplit(config()[2]); origin=headers.get('Origin','')
    allowed={expected.scheme+'://'+expected.netloc}
    stage=os.getenv('BBLIA_STAGE6_ALLOWED_ORIGIN','').rstrip('/')
    if stage and urlsplit(stage).scheme=='https' and urlsplit(stage).netloc.endswith('.onrender.com'):
        allowed.add(stage)
    if origin not in allowed or urlsplit(origin).netloc != headers.get('Host',''):
        raise GoogleError('Origem da solicitação inválida.',403)

def start(cookie, services):
    client,secret,redirect=config()
    if not status(cookie)['configured']:
        raise GoogleError('O cadastro Google da BBLIA ainda precisa ser configurado no servidor.',503)
    if not isinstance(services,list) or not services or any(k not in SCOPES for k in services):
        raise GoogleError('Escolha os serviços que deseja conectar.')
    sid=secrets.token_urlsafe(32); state=secrets.token_urlsafe(32); verifier=secrets.token_urlsafe(48)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    with LOCK:
        for old in list(SESSIONS):
            if SESSIONS[old]['expires']<=time.time():SESSIONS.pop(old,None)
        if len(SESSIONS)>=1000:raise GoogleError('Conexões ocupadas. Tente novamente em instantes.',429)
        SESSIONS[sid]={'expires':time.time()+600,'state':state,'verifier':verifier,
                       'requested':[SCOPES[k] for k in dict.fromkeys(services)]}
    if 'login' in services:SESSIONS[sid]['requested']+=['email','profile']
    params={'client_id':client,'redirect_uri':redirect,'response_type':'code','scope':' '.join(SESSIONS[sid]['requested']),
            'state':state,'code_challenge':challenge,'code_challenge_method':'S256',
            'access_type':'offline','prompt':'consent select_account'}
    return {'url':'https://accounts.google.com/o/oauth2/v2/auth?'+urlencode(params)},cookie_value(sid,600)

def request_json(url, data=None, headers=None):
    try:
        with urlopen(Request(url,data=data,headers=headers or {}),timeout=20) as res:
            raw=res.read(2000001)
            if len(raw)>2000000:raise GoogleError('Resposta Google muito grande.',502)
            return json.loads(raw)
    except HTTPError as e:
        if e.code==401:raise GoogleError('Conexão Google expirada. Conecte novamente.',401)
        if e.code==403:raise GoogleError('O Google negou acesso. Confira permissões e ativação da API no projeto Google.',403)
        if e.code==429:raise GoogleError('Limite de consultas Google atingido. Tente depois.',429)
        raise GoogleError('Não foi possível concluir a consulta ao Google.',502)
    except GoogleError:raise
    except Exception:raise GoogleError('O Google não respondeu. Tente novamente.',502)

def token_request(values):
    client,secret,_=config()
    return request_json('https://oauth2.googleapis.com/token',urlencode({'client_id':client,'client_secret':secret,**values}).encode(),{'Content-Type':'application/x-www-form-urlencoded'})

def callback(cookie, query):
    s=session(cookie); q=parse_qs(query)
    state=q.get('state',[''])[0]
    if not s or not s.get('state') or not secrets.compare_digest(state,s['state']):
        raise GoogleError('Autorização inválida ou expirada. Inicie a conexão novamente.',403)
    # Consume the pending authorization before exchange to prevent replay.
    with LOCK:
        if not s.get('state'):raise GoogleError('Autorização já utilizada.',403)
        s.pop('state')
    if q.get('error'):raise GoogleError('A conexão não foi autorizada. Você pode tentar novamente.')
    code=q.get('code',[''])[0]
    if not code or len(code)>4096:raise GoogleError('Código de autorização inválido.')
    result=token_request({'code':code,'grant_type':'authorization_code','redirect_uri':config()[2],'code_verifier':s.pop('verifier')})
    if not result.get('access_token'):raise GoogleError('Google não retornou a autorização.',502)
    granted=result.get('scope','').split()
    if 'openid' in granted:
        profile=request_json('https://openidconnect.googleapis.com/v1/userinfo',headers={'Authorization':'Bearer '+result['access_token']})
        if not isinstance(profile.get('sub'),str) or not profile['sub'] or profile.get('email_verified') is not True:
            raise GoogleError('O Google não confirmou a identidade da conta.',403)
        s['user']={'id':profile['sub'],'email':str(profile.get('email',''))[:250],'name':str(profile.get('name',''))[:150]}

    if not any(v in granted for v in SCOPES.values()):raise GoogleError('Nenhum dos serviços solicitados foi autorizado.',403)
    s.update(token=result['access_token'],refresh=result.get('refresh_token',''),scopes=granted,
             token_expires=time.time()+int(result.get('expires_in',3600))-60,expires=time.time()+TTL)
    c=SimpleCookie();c.load(cookie);old=c['__Host-bblia_google'].value;new=secrets.token_urlsafe(32)
    with LOCK:SESSIONS.pop(old,None);SESSIONS[new]=s
    return cookie_value(new)


# Mobile handoff: browser authenticates, WebView redeems a single-use, proof-bound ticket.
MOBILE = {}
MOBILE_TTL = 300

def mobile_begin():
    tx=secrets.token_urlsafe(24);proof=secrets.token_urlsafe(32)
    with LOCK:
        for key in list(MOBILE):
            if MOBILE[key]['expires']<=time.time():MOBILE.pop(key,None)
        if len(MOBILE)>=500:raise GoogleError('Muitas autenticações simultâneas.',429)
        MOBILE[tx]={'proof_hash':hashlib.sha256(proof.encode()).digest(),'expires':time.time()+MOBILE_TTL,'sid':None}
    return {'transaction':tx,'proof':proof,'browser_url':'https://bblia-teste.onrender.com/mobile-login?tx='+quote(tx)}

def mobile_browser_start(tx):
    with LOCK:
        entry=MOBILE.get(tx)
        if not entry or entry['expires']<=time.time() or entry['sid'] is not None:
            raise GoogleError('Solicitação de login expirada ou inválida.',403)
    result,cookie=start('', ['login'])
    sid=SimpleCookie();sid.load(cookie);sid=sid['__Host-bblia_google'].value
    with LOCK:
        entry=MOBILE.get(tx)
        if not entry or entry['expires']<=time.time():raise GoogleError('Solicitação expirada.',403)
        entry['pending_sid']=sid
        SESSIONS[sid]['mobile_tx']=tx
    return result,cookie

def mobile_complete(cookie):
    s=session(cookie)
    if not s or not s.get('user') or not s.get('mobile_tx'):return None
    tx=s.pop('mobile_tx')
    sid=SimpleCookie();sid.load(cookie);sid=sid['__Host-bblia_google'].value
    with LOCK:
        entry=MOBILE.get(tx)
        if not entry or entry['expires']<=time.time():return None
        entry['sid']=sid
    return tx

def mobile_redeem(tx,proof):
    if not isinstance(tx,str) or not isinstance(proof,str) or len(tx)>100 or len(proof)>150:
        raise GoogleError('Solicitação inválida.',400)
    with LOCK:
        entry=MOBILE.get(tx)
        if not entry or entry['expires']<=time.time() or not entry.get('sid'):
            raise GoogleError('Login ainda não concluído ou expirado.',403)
        if not secrets.compare_digest(hashlib.sha256(proof.encode()).digest(),entry['proof_hash']):
            raise GoogleError('Comprovação de login inválida.',403)
        sid=entry['sid'];s=SESSIONS.get(sid)
        if not s or not s.get('user'):raise GoogleError('Sessão não encontrada.',403)
        MOBILE.pop(tx,None)
        new=secrets.token_urlsafe(32)
        SESSIONS[new]=dict(s)
        SESSIONS[new].pop('mobile_tx',None)
    return {'authenticated':True},cookie_value(new)

def access(cookie, service):
    s=session(cookie)
    if not s or not s.get('token'):raise GoogleError('Conecte sua conta Google em Ferramentas e conexões.',401)
    if SCOPES[service] not in s.get('scopes',[]):raise GoogleError('Autorize este serviço na conexão Google.',403)
    with LOCK:
        if s['token_expires']<=time.time():
            if not s.get('refresh'):raise GoogleError('Conecte sua conta Google novamente.',401)
            r=token_request({'grant_type':'refresh_token','refresh_token':s['refresh']})
            if not r.get('access_token'):raise GoogleError('Autorização Google expirada. Conecte novamente.',401)
            s.update(token=r['access_token'],token_expires=time.time()+int(r.get('expires_in',3600))-60)
    return s['token']

def api(cookie,service,path,params=None):
    roots={'email':'https://gmail.googleapis.com/gmail/v1/users/me/',
           'calendar':'https://www.googleapis.com/calendar/v3/',
           'drive':'https://www.googleapis.com/drive/v3/'}
    return request_json(roots[service]+path+('?' + urlencode(params) if params else ''),headers={'Authorization':'Bearer '+access(cookie,service)})

def execute(cookie, name, args):
    if not isinstance(args,dict):raise GoogleError('Consulta inválida.')
    query=str(args.get('consulta',''))[:500]
    if name=='consultar_email':
        result=api(cookie,'email','messages',{'q':query,'maxResults':10})
        messages=[]
        for item in result.get('messages',[]):
            m=api(cookie,'email','messages/'+quote(item['id'],safe=''),{'format':'full'})
            h={x['name'].lower():x['value'] for x in m.get('payload',{}).get('headers',[])}
            messages.append({'id':m['id'],'assunto':h.get('subject',''),'de':h.get('from',''),'data':h.get('date',''),'resumo':m.get('snippet','')})
        return {'mensagens':messages,'limite':10}
    if name=='ler_email':
        mid=str(args.get('id',''))
        if not mid or len(mid)>200 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in mid):raise GoogleError('Identificador de e-mail inválido.')
        m=api(cookie,'email','messages/'+mid,{'format':'full'})
        headers={x['name'].lower():x['value'] for x in m.get('payload',{}).get('headers',[])}
        parts=[]
        def extract(part,depth=0):
            if depth>12:return
            if part.get('mimeType')=='text/plain' and not part.get('filename'):
                raw=part.get('body',{}).get('data','')
                if raw:
                    try:parts.append(base64.urlsafe_b64decode(raw+'='*(-len(raw)%4)).decode('utf-8',errors='replace')[:30000])
                    except Exception:pass
            for child in part.get('parts',[])[:30]:extract(child,depth+1)
        extract(m.get('payload',{}))
        return {'assunto':headers.get('subject',''),'de':headers.get('from',''),'para':headers.get('to',''),'data':headers.get('date',''),
                'texto':('\n'.join(parts) or m.get('snippet',''))[:60000], 'nota':'Anexos e HTML não são executados nem baixados.'}
    if name=='consultar_agenda':
        from datetime import datetime,timezone
        result=api(cookie,'calendar','calendars/primary/events',{'timeMin':datetime.now(timezone.utc).isoformat(),'singleEvents':'true','orderBy':'startTime','maxResults':20,**({'q':query} if query else {})})
        return {'eventos':[{k:v for k,v in e.items() if k in ('id','summary','start','end','location','description','htmlLink')} for e in result.get('items',[])]}
    if name=='buscar_drive':
        safe=query.replace('\\','\\\\').replace("'","\\'")
        result=api(cookie,'drive','files',{'q':"trashed = false"+(" and (name contains '"+safe+"')" if safe else ''),'pageSize':20,'fields':'files(id,name,mimeType,modifiedTime,webViewLink),nextPageToken','orderBy':'modifiedTime desc'})
        return {'arquivos':result.get('files',[]),'mais_resultados':bool(result.get('nextPageToken'))}
    if name=='ler_arquivo_drive':
        fid=str(args.get('id',''))
        if not fid or len(fid)>200 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in fid):raise GoogleError('Identificador de arquivo inválido.')
        meta=api(cookie,'drive','files/'+fid,{'fields':'id,name,mimeType,size'})
        mime=meta.get('mimeType','');root='https://www.googleapis.com/drive/v3/files/'+fid
        if mime=='application/vnd.google-apps.document':url=root+'/export?mimeType=text%2Fplain'
        elif mime.startswith('text/') or mime in ('application/json','application/xml'):
            if int(meta.get('size','0'))>100000:raise GoogleError('Arquivo muito grande para leitura no chat.')
            url=root+'?alt=media'
        else:raise GoogleError('Leitura disponível para documentos Google e arquivos de texto. Para PDF e imagens, anexe o arquivo na conversa.')
        try:
            with urlopen(Request(url,headers={'Authorization':'Bearer '+access(cookie,'drive')}),timeout=20) as r:raw=r.read(100001)
        except Exception:raise GoogleError('Não foi possível ler o arquivo do Drive.',502)
        return {'nome':meta['name'],'texto':raw[:100000].decode('utf-8',errors='replace'),'truncado':len(raw)>100000}
    raise GoogleError('Ferramenta Google desconhecida.')

def disconnect(cookie, revoke=True):
    c=SimpleCookie();c.load(cookie or '');m=c.get('__Host-bblia_google')
    if not m and c.get('__Host-bblia_email'):return email_auth.logout(cookie)
    with LOCK:s=SESSIONS.pop(m.value,None) if m else None
    # Local session is always removed, even if Google is unavailable.
    revoked=False
    if revoke and s and s.get('token'):
        try:
            with urlopen(Request('https://oauth2.googleapis.com/revoke',data=urlencode({'token':s.get('refresh') or s['token']}).encode(),headers={'Content-Type':'application/x-www-form-urlencoded'}),timeout=10):revoked=True
        except Exception:pass
    return {'disconnected':True,'revoked':revoked},cookie_value('',0)

def tools(cookie):
    s=status(cookie); result=[]
    definitions=[('email','consultar_email','Buscar e-mails da conta Google conectada; retorna até 10 resumos. consulta usa a busca do Gmail.'),
                 ('email','ler_email','Ler texto de um e-mail pelo id retornado por consultar_email.'),
                 ('calendar','consultar_agenda','Consultar próximos eventos da agenda principal Google; consulta pode filtrar pelo título.'),
                 ('drive','buscar_drive','Buscar arquivos pelo nome no Drive da conta conectada.'),
                 ('drive','ler_arquivo_drive','Ler documento Google ou arquivo de texto pelo id retornado por buscar_drive.')]
    for service,name,desc in definitions:
        if service in s['services']:
            key='id' if name in ('ler_arquivo_drive','ler_email') else 'consulta'
            result.append({'type':'function','name':name,'description':desc,'parameters':{'type':'object','properties':{key:{'type':'string'}},'required':[key],'additionalProperties':False}})
    return result

NAMES={'ler_email','consultar_email','consultar_agenda','buscar_drive','ler_arquivo_drive'}
