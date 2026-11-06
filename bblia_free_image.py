"""Free Qwen image generation/editing via the public Hugging Face demos.
No paid endpoint, identity rotation or quota retry is used.
"""
import base64
import json
import os
import time
import urllib.request
import urllib.error
import uuid
from urllib.parse import urlsplit
from bblia_media import MediaError

CREATE_HOST='https://qwen-qwen-image.hf.space'
EDIT_HOST='https://qwen-qwen-image-edit.hf.space'


def headers():
    result={'User-Agent':'BBLIA/1.0','Content-Type':'application/json'}
    token=os.getenv('HF_TOKEN','').strip()
    if token:result['Authorization']='Bearer '+token
    return result


def error(details):
    text=str(details).lower()
    if any(word in text for word in ('quota','exceed','limit')):
        return MediaError('A cota do gerador gratuito de imagens foi atingida. Aguarde a renovação ou conecte uma conta gratuita Hugging Face. Nenhum serviço pago foi acionado.',429,'image_quota_exceeded')
    if any(word in text for word in ('unauth','login','log in','sign in','forbidden')):
        return MediaError('O gerador gratuito de imagens exige conectar uma conta Hugging Face. Nenhum serviço pago foi acionado.',503,'image_auth_required')
    return MediaError('O gerador gratuito de imagens não concluiu o pedido. Tente mais tarde. Nenhum serviço pago foi acionado.',503,'image_provider_error')


def request(host,path,payload=None,timeout=25):
    data=json.dumps(payload).encode() if payload is not None else None
    req=urllib.request.Request(host+path,data=data,headers=headers())
    with urllib.request.urlopen(req,timeout=timeout) as response:
        return json.load(response)


def upload(host,reference):
    from bblia_work import attachment_parts
    attachment_parts([reference])
    if reference.get('type')!='image':raise ValueError('Anexe uma foto PNG, JPEG ou WEBP.')
    meta,encoded=reference['data'].split(';base64,',1)
    mime=meta[5:]
    boundary='bblia'+uuid.uuid4().hex
    body=('--'+boundary+'\r\nContent-Disposition: form-data; name="files"; filename="reference"\r\nContent-Type: '+mime+'\r\n\r\n').encode()+base64.b64decode(encoded,validate=True)+('\r\n--'+boundary+'--\r\n').encode()
    upload_headers=headers();upload_headers['Content-Type']='multipart/form-data; boundary='+boundary
    req=urllib.request.Request(host+'/gradio_api/upload',data=body,headers=upload_headers)
    with urllib.request.urlopen(req,timeout=30) as response:paths=json.load(response)
    if not isinstance(paths,list) or not paths or not isinstance(paths[0],str):raise error('upload failed')
    return {'path':paths[0],'orig_name':'reference','meta':{'_type':'gradio.FileData'}}


def generate(prompt,reference=None):
    host=EDIT_HOST if reference else CREATE_HOST
    try:
        config=request(host,'/config')
        definition=next((d for d in config.get('dependencies',[]) if d.get('api_name')=='infer'),None)
        if not definition or len(definition.get('inputs',[]))!=7:raise error('provider contract changed')
        data=([upload(host,reference),prompt,0,True,4.0,25,False] if reference
              else [prompt,0,True,'1:1',4.0,25,False])
        session=uuid.uuid4().hex
        event=request(host,'/gradio_api/queue/join',{'data':data,'fn_index':definition['id'],'session_hash':session})
        event_id=event.get('event_id')
        if not event_id:raise error(event)
        req=urllib.request.Request(host+'/gradio_api/queue/data?session_hash='+session,headers=headers())
        deadline=time.monotonic()+240
        image=None
        with urllib.request.urlopen(req,timeout=45) as response:
            for line in response:
                if time.monotonic()>deadline:raise error('queue timeout')
                if len(line)>1000000:raise error('provider response too large')
                if not line.startswith(b'data: '):continue
                value=json.loads(line[6:])
                if value.get('event_id') not in (None,event_id):continue
                if value.get('msg') in ('queue_full','unexpected_error'):raise error(value)
                if value.get('msg')!='process_completed':continue
                if not value.get('success'):raise error(value.get('output',{}))
                output=value.get('output',{}).get('data',[])
                image=output[0] if output else None
                break
        url=image.get('url') if isinstance(image,dict) else image
        if not isinstance(url,str) or not url.startswith(host+'/'):raise error('missing image')
        # Public result download needs no bearer credential; never forward it to redirects.
        req=urllib.request.Request(url,headers={'User-Agent':'BBLIA/1.0'})
        with urllib.request.urlopen(req,timeout=30) as response:
            raw=response.read(10*1024*1024+1)
        if len(raw)>10*1024*1024:raise error('image too large')
        mime=('image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else
              'image/jpeg' if raw.startswith(b'\xff\xd8\xff') else
              'image/webp' if raw.startswith(b'RIFF') and raw[8:12]==b'WEBP' else None)
        if not mime:raise error('invalid image bytes')
        return {'image':'data:'+mime+';base64,'+base64.b64encode(raw).decode(),'provider':'qwen-free','free':True}
    except MediaError:raise
    except urllib.error.HTTPError as exc:
        raise error('quota' if exc.code==429 else 'unauth' if exc.code in (401,403) else 'HTTP '+str(exc.code)) from exc
    except (OSError,TimeoutError,ValueError,KeyError,TypeError) as exc:raise error('connection failed') from exc
