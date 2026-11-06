"""Read-only bounded ZIP reports. Never extract or run archive contents."""
import io
import json
import re
import stat
import struct
import threading
import zipfile
from pathlib import PurePosixPath

MAX_ZIP = 100*1024*1024
ZIP_SLOTS = threading.BoundedSemaphore(1)
TEXT_EXTENSIONS = {'.txt','.md','.json','.csv','.xml','.html','.css','.js','.ts','.tsx','.jsx','.py',
                   '.java','.kt','.kts','.gradle','.yaml','.yml','.sh','.properties','.toml','.ini','.cfg','.sql'}


def inspect_zip(stream, name='arquivo.zip'):
    stream.seek(0, 2)
    size = stream.tell()
    if not 22 <= size <= MAX_ZIP:raise ValueError('Envie um ZIP de até 100 MB.')
    # Bound central-directory allocation before ZipFile creates its entry objects.
    stream.seek(max(0, size-65557))
    tail = stream.read()
    end = tail.rfind(b'PK\x05\x06')
    if end < 0 or len(tail)-end < 22:raise ValueError('ZIP inválido ou incompleto.')
    record = struct.unpack_from('<4s4H2LH', tail, end)
    _, disk, cd_disk, disk_count, count, cd_size, cd_offset, comment = record
    if disk or cd_disk or disk_count != count:raise ValueError('ZIP dividido em volumes: reúna as partes antes de enviar.')
    if count > 5000 or cd_size > 4*1024*1024 or cd_offset+cd_size > size:
        raise ValueError('ZIP excede o limite de 5 mil entradas ou possui diretório inválido.')
    if len(tail)-end != 22+comment:raise ValueError('Final do ZIP inválido.')
    stream.seek(0)
    listing, texts, warnings = [], [], []
    remaining = 75000
    text_count = 0
    try:
        with zipfile.ZipFile(stream) as archive:
            infos = archive.infolist()
            for info in infos:
                path = info.filename.replace('\\','/')
                suspicious = path.startswith('/') or '..' in PurePosixPath(path).parts or bool(re.match(r'^[A-Za-z]:',path))
                link = stat.S_ISLNK(info.external_attr >> 16)
                encrypted = bool(info.flag_bits & 1)
                listing.append({'path':path[:250],'bytes':info.file_size,'compressed_bytes':info.compress_size,
                                'directory':info.is_dir(),'encrypted':encrypted,'suspicious_path':suspicious,'symlink':link})
                if suspicious or link or encrypted:
                    warnings.append(path[:180]+': '+('caminho suspeito' if suspicious else 'link simbólico' if link else 'protegido por senha'))
                    continue
                if info.is_dir() or PurePosixPath(path).suffix.lower() not in TEXT_EXTENSIONS:
                    continue
                if text_count >= 30 or remaining <= 0:
                    continue
                if info.file_size > 1024*1024 or info.file_size > max(1024,info.compress_size)*250:
                    warnings.append(path[:180]+': texto grande ou compressão excessiva; somente listado')
                    continue
                limit = min(8000,remaining)
                with archive.open(info) as file:
                    raw = file.read(limit+1)
                if b'\x00' in raw:continue
                text = raw[:limit].decode('utf-8-sig','replace')
                remaining -= len(text)
                texts.append({'path':path[:250],'content':text,'truncated':info.file_size>limit})
                text_count += 1
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError, EOFError) as exc:
        raise ValueError('Não foi possível ler este ZIP. Confira se está completo e usa compressão ZIP comum.') from exc
    report = {'name':name,'compressed_bytes':size,'entry_count':len(listing),
              'uncompressed_bytes':sum(i['bytes'] for i in listing),'entries':listing[:350],
              'listing_truncated':len(listing)>350,'text_previews':texts,'warnings':warnings[:30],
              'scope':'Listagem e leitura limitada de texto UTF-8. Binários, ROMs e ZIPs internos são somente identificados. Nada foi extraído ou executado.'}
    # Keep the report inside the existing attachment text budget.
    while True:
        data = 'RELATÓRIO DE ZIP (dados do arquivo anexado):\n'+json.dumps(report,ensure_ascii=False)
        if len(data)<=119000:break
        if report['entries']:report['entries'].pop();report['listing_truncated']=True
        elif report['text_previews']:report['text_previews'].pop()
        else:raise ValueError('Relatório do ZIP excede o tamanho permitido.')
    return {'name':name+'.relatorio.txt','type':'text','data':data,
            'zip':{'name':name,'entry_count':len(listing),'compressed_bytes':size,'text_count':len(texts)}}
