"""Scoped, temporary APK delivery from the owner's computer to its BBLIA job."""
import hashlib
import os
from pathlib import Path
import re
import secrets
import struct
import tempfile
import threading
import time
import zipfile

LOCK=threading.RLock()
ROOT=Path(tempfile.gettempdir())/'bblia-apk-delivery'
TICKETS={}
MAX_APK=100*1024*1024


def prepare(job,filename,sha256):
    if not re.fullmatch(r'[A-Za-z0-9_. -]{1,100}\.apk',filename) or filename.startswith('.'):
        raise ValueError('Nome de APK inválido.')
    if not re.fullmatch(r'[a-fA-F0-9]{64}',sha256):raise ValueError('Informe o SHA-256 verificado pelo compilador.')
    with LOCK:
        for token in list(TICKETS):
            item=TICKETS[token]
            if item['expires']<time.time():
                if item.get('path'):Path(item['path']).unlink(missing_ok=True)
                del TICKETS[token]
        if sum(1 for item in TICKETS.values() if item['job']==job)>=4:raise ValueError('Máximo de quatro APKs por entrega.')
        if len(TICKETS)>=12:raise ValueError('Há entregas em andamento. Tente novamente mais tarde.')
        token=secrets.token_urlsafe(32)
        TICKETS[token]={'job':job,'name':filename,'sha256':sha256.lower(),'expires':time.time()+3600,'state':'pending'}
    return token


def receive(token,stream,length):
    with LOCK:
        item=TICKETS.get(token)
        if not item or item['expires']<time.time() or item['state']!='pending':raise ValueError('Envio de APK expirado ou já utilizado.')
        if not 22<=length<=MAX_APK:raise ValueError('Envie um APK de até 100 MB.')
        item['state']='uploading'
    ROOT.mkdir(exist_ok=True,mode=0o700)
    path=ROOT/(secrets.token_hex(20)+'.apk');digest=hashlib.sha256()
    try:
        with path.open('xb') as output:
            os.chmod(path,0o600);remaining=length
            while remaining:
                part=stream.read(min(1024*1024,remaining))
                if not part:raise ValueError('Envio do APK interrompido.')
                output.write(part);digest.update(part);remaining-=len(part)
        if digest.hexdigest()!=item['sha256']:raise ValueError('O hash do arquivo recebido não corresponde ao APK compilado.')
        with path.open('rb') as file:
            file.seek(max(0,length-65557));tail=file.read();offset=tail.rfind(b'PK\x05\x06')
            if offset<0 or len(tail)-offset<22:raise ValueError('APK ZIP incompleto.')
            _,disk,central_disk,entries_disk,entries,central_size,central_offset,comment=struct.unpack_from('<4s4H2LH',tail,offset)
            if disk or central_disk or entries_disk!=entries or entries>30000 or central_size>8*1024*1024 or central_offset+central_size>length:
                raise ValueError('Estrutura do APK excede os limites de leitura.')
        with zipfile.ZipFile(path) as archive:
            if 'AndroidManifest.xml' not in archive.namelist() or not any(re.fullmatch(r'classes\d*\.dex',n) for n in archive.namelist()):
                raise ValueError('O arquivo recebido não tem estrutura de APK instalável.')
        with LOCK:item.update(state='ready',path=str(path),bytes=length,download=secrets.token_urlsafe(32))
        return {'ok':True,'name':item['name'],'bytes':length,'sha256':item['sha256']}
    except Exception:
        path.unlink(missing_ok=True)
        with LOCK:item['state']='failed'
        raise


def artifacts(job):
    with LOCK:
        return [{'name':item['name'],'content':'APK compilado. Salve o arquivo: este link é temporário.',
                 'download_url':'/api/apk/download/'+item['download'],'mime':'application/vnd.android.package-archive',
                 'bytes':item['bytes'],'sha256':item['sha256']}
                for item in TICKETS.values() if item['job']==job and item['state']=='ready' and item['expires']>time.time()]


def pending(job):
    with LOCK:return [item['name'] for item in TICKETS.values() if item['job']==job and item['state']!='ready' and item['expires']>time.time()]


def download(token):
    with LOCK:
        item=next((i for i in TICKETS.values() if i.get('download')==token and i['state']=='ready' and i['expires']>time.time()),None)
        if not item or not Path(item['path']).is_file():raise ValueError('O link do APK expirou. Reenvie o APK compilado pelo computador.')
        return dict(item)
