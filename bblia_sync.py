"""Per-account workspaces in Drive appDataFolder; one snapshot per browser.
No database on ephemeral Render disk; no credentials in snapshots.
"""
import json, re, copy, hashlib, threading, time
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import bblia_google as google
MAX_BYTES=18_000_000
SYNC_LOCK=threading.RLock()  # This service runs one Python process/instance.
PATTERN=re.compile(r'^[a-zA-Z0-9_-]{8,100}$')


def empty():
    return {'version':1,'projects':[],'chats':[],'active':None,'preferences':{},'deleted':{},'preferencesUpdated':0}


def validate(value):
    if not isinstance(value,dict) or type(value.get('version')) is not int or value['version']!=1:raise google.GoogleError('Formato de histórico inválido.')
    result=empty()
    for key,maximum in [('chats',2000),('projects',200)]:
        items=value.get(key)
        if not isinstance(items,list) or len(items)>maximum:raise google.GoogleError('Histórico excede o limite de '+key+'.')
        seen=set()
        for item in items:
            if not isinstance(item,dict) or not isinstance(item.get('id'),str) or not 1<=len(item['id'])<=200 or item['id'] in seen:raise google.GoogleError('Identificador de histórico inválido ou repetido.')
            seen.add(item['id'])
            if key=='chats':
                if not isinstance(item.get('title'),str) or not isinstance(item.get('messages'),list):raise google.GoogleError('Conversa inválida.')
                for m in item['messages']:
                    if not isinstance(m,dict) or m.get('role') not in ('user','assistant') or not isinstance(m.get('content'),str):raise google.GoogleError('Mensagem inválida.')
            else:
                if not all(isinstance(item.get(k),str) for k in ('name','instructions')) or not isinstance(item.get('files'),list):raise google.GoogleError('Projeto inválido.')
            safe=copy.deepcopy(item)
            # Never save execution credentials even if a client sends extra fields.
            for field in ('computer_connection','access_token','refresh_token','client_secret'):safe.pop(field,None)
            result[key].append(safe)
    prefs=value.get('preferences',{})
    if not isinstance(prefs,dict):raise google.GoogleError('Preferências inválidas.')
    result['preferences']={k:copy.deepcopy(v) for k,v in prefs.items() if k in ('name','instructions','detail','web','auto','memory_enabled','memories')}
    deleted=value.get('deleted',{})
    if not isinstance(deleted,dict) or len(deleted)>5000 or any(not isinstance(k,str) or len(k)>220 or not isinstance(v,(int,float)) for k,v in deleted.items()):raise google.GoogleError('Registro de exclusões inválido.')
    result['deleted']=copy.deepcopy(deleted)
    result['preferencesUpdated']=stamp(value.get('preferencesUpdated'))
    result['active']=value.get('active') if isinstance(value.get('active'),str) else None
    if len(json.dumps(result,ensure_ascii=False,allow_nan=False).encode())>MAX_BYTES:raise google.GoogleError('Histórico maior que 18 MB. Exporte um backup antes de remover anexos.',413)
    return result


def stamp(value):
    return value if isinstance(value,(int,float)) and 0<=value<=10**14 else 0


def signature(item):
    return hashlib.sha256(json.dumps(item,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def merge(states):
    result=empty();groups={'chats':{},'projects':{}};conflicts={}
    for raw in states:
        s=validate(raw)
        for key,value in s['deleted'].items():result['deleted'][key]=max(result['deleted'].get(key,0),value)
        if (s['preferencesUpdated']>result['preferencesUpdated'] or
            (s['preferencesUpdated']==result['preferencesUpdated'] and
             (bool(s['preferences']),signature(s['preferences']))>
             (bool(result['preferences']),signature(result['preferences'])))):
            result['preferences']=s['preferences'];result['preferencesUpdated']=s['preferencesUpdated']
        for kind in groups:
            for item in s[kind]:
                old=groups[kind].get(item['id'])
                if old and kind=='chats' and old['messages']!=item['messages']:
                    a,b=old['messages'],item['messages']
                    # A normal continuation is not a conflict; preserve divergent transcripts.
                    if a[:len(b)]!=b and b[:len(a)]!=a:
                        loser=min([old,item],key=lambda x:(stamp(x.get('updated')),signature(x)))
                        fork=copy.deepcopy(loser);fork['id']=item['id']+'-conflict-'+signature(loser['messages'])[:12];fork['title']=loser['title']+' · cópia preservada'
                        conflicts[fork['id']]=(item['id'],fork)
                if not old or (stamp(item.get('updated')),signature(item))>(stamp(old.get('updated')),signature(old)):groups[kind][item['id']]=copy.deepcopy(item)
                if old and kind=='chats':
                    a,b=old['messages'],item['messages']
                    if a[:len(b)]==b or b[:len(a)]==a:
                        # Device clocks may differ: never discard a verified continuation.
                        groups[kind][item['id']]['messages']=copy.deepcopy(a if len(a)>=len(b) else b)
    for kind,items in groups.items():
        result[kind]=[item for key,item in items.items() if kind+':'+key not in result['deleted']]
    for fid,(parent,fork) in conflicts.items():
        if 'chats:'+parent not in result['deleted'] and 'chats:'+fid not in result['deleted'] and fid not in groups['chats']:result['chats'].append(fork)
    result['chats'].sort(key=lambda x:(-stamp(x.get('updated')),x['id']))
    result['projects'].sort(key=lambda x:x['id'])
    return validate(result)


def identity(cookie, expected=None):
    s=google.session(cookie)
    if not s or not s.get('user'):raise google.GoogleError('Entre na sua conta da BBLIA para sincronizar.',401)
    if expected is not None and expected!=s['user']['id']:raise google.GoogleError('A conta mudou. Atualize a página antes de sincronizar.',409)
    google.access(cookie,'sync')
    return s['user']


def drive(cookie,path,method='GET',data=None,content_type=None,upload=False):
    token=google.access(cookie,'sync')
    root='https://www.googleapis.com/'+('upload/' if upload else '')+'drive/v3/'
    headers={'Authorization':'Bearer '+token}
    if content_type:headers['Content-Type']=content_type
    try:
        with urlopen(Request(root+path,method=method,data=data,headers=headers),timeout=35) as r:
            raw=r.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES:raise google.GoogleError('Backup remoto excede o limite. Nenhum dado local foi substituído.',413)
            return json.loads(raw) if raw else {}
    except google.GoogleError:raise
    except HTTPError as e:
        if e.code in (401,403):raise google.GoogleError('Autorize o login e a sincronização Google novamente.',e.code)
        if e.code==429:raise google.GoogleError('Google limitou a sincronização. Tente novamente mais tarde.',429)
        raise google.GoogleError('Falha ao salvar no Google Drive. Os dados continuam no aparelho.',502)
    except Exception:raise google.GoogleError('Não foi possível sincronizar. Os dados continuam no aparelho.',502)


def snapshots(cookie):
    params={'spaces':'appDataFolder','q':"trashed = false and appProperties has { key='bblia' and value='workspace-v1' }",'fields':'files(id,name),nextPageToken','pageSize':100}
    listing=drive(cookie,'files?'+urlencode(params))
    if listing.get('nextPageToken'):raise google.GoogleError('Muitos aparelhos sincronizados. Exporte um backup para manutenção.',409)
    result=[]
    for f in listing.get('files',[]):
        if not re.fullmatch(r'bblia-workspace-[a-zA-Z0-9_-]{8,100}\.json',f.get('name','')):continue
        payload=drive(cookie,'files/'+quote(f['id'],safe='')+'?alt=media')
        # Invalid cloud snapshots fail closed, never silently overwrite missing data.
        result.append((f,validate(payload)))
    return result


def load(cookie):
    user=identity(cookie)
    with SYNC_LOCK:state=merge([s for _,s in snapshots(cookie)])
    return {'user':user,'workspace':state,'saved_at':int(time.time()*1000)}


def save(cookie,payload):
    user=identity(cookie,payload.get('account'))
    device=payload.get('device','')
    if not isinstance(device,str) or not PATTERN.fullmatch(device):raise google.GoogleError('Identificador de aparelho inválido.')
    incoming=validate(payload.get('workspace'));name='bblia-workspace-'+device+'.json'
    with SYNC_LOCK:
        existing=snapshots(cookie);state=merge([s for _,s in existing]+[incoming]);raw=json.dumps(state,ensure_ascii=False,allow_nan=False).encode()
        mine=next((f for f,_ in existing if f['name']==name),None)
        if mine:drive(cookie,'files/'+quote(mine['id'],safe='')+'?uploadType=media','PATCH',raw,'application/json',upload=True)
        else:
            boundary='bblia_'+hashlib.sha256(device.encode()).hexdigest()[:24]
            meta=json.dumps({'name':name,'parents':['appDataFolder'],'appProperties':{'bblia':'workspace-v1'}}).encode()
            body=b'--'+boundary.encode()+b'\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'+meta+b'\r\n--'+boundary.encode()+b'\r\nContent-Type: application/json\r\n\r\n'+raw+b'\r\n--'+boundary.encode()+b'--\r\n'
            drive(cookie,'files?uploadType=multipart','POST',body,'multipart/related; boundary='+boundary,upload=True)
    return {'user':user,'workspace':state,'saved_at':int(time.time()*1000)}
