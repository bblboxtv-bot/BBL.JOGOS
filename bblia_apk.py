"""Bounded, static APK inspection. Never installs or executes uploaded code."""
import hashlib
import json
import re
import struct
import threading
import zipfile
from xml.etree import ElementTree as ET

MAX_APK = 100 * 1024 * 1024
APK_SLOTS = threading.BoundedSemaphore(1)
MAX_MEMBER = 16 * 1024 * 1024
MAX_READ = 48 * 1024 * 1024


def u16(b, o):
    return struct.unpack_from('<H', b, o)[0]


def u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


def string_pool(b):
    count, flags, start = u32(b, 8), u32(b, 16), u32(b, 20)
    header = u16(b, 2)
    if count > 100000 or header + count * 4 > len(b) or start > len(b):
        raise ValueError('Tabela de textos Android inválida.')
    def length(pos, wide=False):
        n = u16(b, pos) if wide else b[pos]
        pos += 2 if wide else 1
        if n & (0x8000 if wide else 0x80):
            n = ((n & (0x7fff if wide else 0x7f)) << (16 if wide else 8)) | (u16(b, pos) if wide else b[pos])
            pos += 2 if wide else 1
        return n, pos
    result, cache, total_chars = [], {}, 0
    for i in range(count):
        pos = start + u32(b, header + i * 4)
        if pos in cache:
            result.append(cache[pos])
            continue
        original_pos = pos
        if flags & 0x100:
            _, pos = length(pos)
            size, pos = length(pos)
            if pos + size > len(b):raise ValueError('Texto Android truncado.')
            raw = b[pos:pos + min(size,4000)]
            text = raw.decode('utf-8', 'replace')
        else:
            size, pos = length(pos, True)
            size *= 2
            if pos + size > len(b):raise ValueError('Texto Android truncado.')
            raw = b[pos:pos + min(size,4000)]
            text = raw.decode('utf-16le', 'replace')
        text = text[:2000]
        total_chars += len(text)
        if total_chars > 2000000:raise ValueError('Tabela de textos Android muito grande.')
        cache[original_pos] = text
        result.append(text)
    return result


def xml_nodes(raw):
    if raw.lstrip().startswith(b'<'):
        root = ET.fromstring(raw)
        return [(e.tag.rsplit('}', 1)[-1], {k.rsplit('}', 1)[-1]: v for k, v in e.attrib.items()}) for e in root.iter()][:2000]
    if len(raw) < 8 or u16(raw, 0) != 3 or u32(raw, 4) > len(raw):
        raise ValueError('XML Android inválido.')
    strings, nodes = [], []
    pos = u16(raw, 2)
    end = u32(raw, 4)
    while pos + 8 <= end:
        typ, header, size = u16(raw, pos), u16(raw, pos + 2), u32(raw, pos + 4)
        if header < 8 or size < header or pos + size > end:
            raise ValueError('Bloco XML Android inválido.')
        b = raw[pos:pos + size]
        if typ == 1:
            strings = string_pool(b)
        elif typ == 0x102:
            ext = header
            tag = strings[u32(b, ext + 4)]
            start, stride, count = u16(b, ext + 8), u16(b, ext + 10), u16(b, ext + 12)
            if count > 1000 or stride < 20 or ext + start + count * stride > size:
                raise ValueError('Atributos XML Android inválidos.')
            attrs = {}
            for i in range(count):
                a = ext + start + i * stride
                key, value, dtype, typed = strings[u32(b, a + 4)], u32(b, a + 8), b[a + 15], u32(b, a + 16)
                if value != 0xffffffff:
                    value = strings[value]
                elif dtype == 3:
                    value = strings[typed]
                elif dtype == 0x12:
                    value = bool(typed)
                elif dtype in (1, 2):
                    value = '@0x%08x' % typed
                else:
                    value = typed
                attrs[key] = value
            nodes.append((tag, attrs))
            if len(nodes) >= 2000:
                break
        pos += size
    return nodes


def dex_strings(raw):
    if len(raw) < 112 or not raw.startswith(b'dex\n'):
        return []
    count, offset = u32(raw, 56), u32(raw, 60)
    if count > 1000000 or offset + count * 4 > len(raw):
        return []
    results = []
    for i in range(min(count, 80000)):
        pos = u32(raw, offset + i * 4)
        if pos >= len(raw):
            continue
        for _ in range(5):
            n = raw[pos]; pos += 1
            if not n & 0x80:
                break
            if pos >= len(raw):
                break
        end = raw.find(b'\0', pos, min(pos + 400, len(raw)))
        if end > pos:
            text = raw[pos:end].decode('utf-8', 'replace')
            if 4 <= len(text) <= 300 and (' ' in text or text.startswith(('L', 'http'))):
                results.append(text)
                if len(results) >= 600:
                    break
    return results


def inspect_apk(stream, name='aplicativo.apk'):
    stream.seek(0, 2)
    size = stream.tell()
    if not 1 <= size <= MAX_APK:
        raise ValueError('Envie um APK de até 100 MB.')
    stream.seek(0)
    sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    stream.seek(0)
    warnings, read_total = [], 0
    try:
        with zipfile.ZipFile(stream) as apk:
            members = apk.infolist()
            if len(members) > 20000:
                raise ValueError('APK com arquivos demais para análise.')
            names = [m.filename for m in members]
            if 'AndroidManifest.xml' not in names:
                raise ValueError('Este arquivo não é um APK: AndroidManifest.xml ausente.')
            if len(set(names)) != len(names):
                raise ValueError('APK com entradas duplicadas não suportado.')
            def read(path):
                nonlocal read_total
                member = apk.getinfo(path)
                if member.flag_bits & 1 or member.file_size > MAX_MEMBER or read_total + member.file_size > MAX_READ:
                    raise ValueError('Recurso excede os limites da análise.')
                if member.file_size > max(1, member.compress_size) * 300:
                    raise ValueError('Recurso com compressão excessiva.')
                read_total += member.file_size
                with apk.open(member) as source:
                    data = source.read(MAX_MEMBER + 1)
                if len(data) > MAX_MEMBER:
                    raise ValueError('Recurso muito grande.')
                return data
            try:
                nodes = xml_nodes(read('AndroidManifest.xml'))
            except (IndexError, struct.error, ET.ParseError) as exc:
                raise ValueError('Manifesto Android corrompido ou incompleto.') from exc
            manifest = next((a for tag, a in nodes if tag == 'manifest'), None)
            if not manifest or not manifest.get('package'):
                raise ValueError('O APK não contém um manifesto Android com pacote válido.')
            report = {'filename': name[:120], 'size_bytes': size, 'sha256': sha,
                      'package': manifest.get('package'), 'version_name': manifest.get('versionName'),
                      'version_code': manifest.get('versionCode'),
                      'application': next((a for t, a in nodes if t == 'application'), {}),
                      'sdk': next((a for t, a in nodes if t == 'uses-sdk'), {}),
                      'permissions': [a.get('name') for t, a in nodes if t.startswith('uses-permission')][:150],
                      'components': [{'type': t, **a} for t, a in nodes if t in ('activity', 'activity-alias', 'service', 'receiver', 'provider')][:150],
                      'intent_actions': list(dict.fromkeys(a.get('name') for t, a in nodes if t == 'action'))[:100],
                      'native_libraries': [n for n in names if n.startswith('lib/') and n.endswith('.so')][:100],
                      'layouts': [], 'texts': [], 'classes_sample': [], 'assets': []}
            for path in names:
                if path.startswith('res/layout') and path.endswith('.xml') and len(report['layouts']) < 12:
                    try:
                        layout = xml_nodes(read(path))
                        report['layouts'].append({'file': path, 'views': [{'tag': t, **{k: v for k, v in a.items() if k in ('id', 'text', 'hint', 'orientation', 'layout_width', 'layout_height', 'background')}} for t, a in layout[:45]]})
                    except (ValueError, IndexError, struct.error, ET.ParseError):
                        warnings.append('Layout não decodificado: '+path)
                elif re.fullmatch(r'classes\d*\.dex', path) and len(report['classes_sample']) < 200:
                    try:
                        texts = dex_strings(read(path))
                        report['classes_sample'].extend(t for t in texts if t.startswith('L') and t.endswith(';'))
                        report['texts'].extend(t for t in texts if not t.startswith(('L', 'http')) and len(report['texts']) < 200)
                    except (ValueError, IndexError, struct.error):
                        warnings.append('DEX não analisado: '+path)
                elif path.startswith('assets/') and len(report['assets']) < 80:
                    report['assets'].append(path)
            # Resource strings include labels that the binary manifest references by ID.
            if 'resources.arsc' in names:
                try:
                    resources = read('resources.arsc')
                    pos = u16(resources, 2)
                    if u16(resources, pos) == 1:
                        report['resource_texts'] = string_pool(resources[pos:pos + u32(resources, pos + 4)])[:250]
                except (ValueError, IndexError, struct.error):
                    warnings.append('Tabela de recursos não decodificada.')
            report['classes_sample'] = report['classes_sample'][:200]
            report['warnings'] = warnings[:25]
            report['limits'] = 'Análise estática parcial. O aplicativo não foi executado; layout em tempo de execução, código ofuscado e funções remotas podem não ser recuperados. Não é o código-fonte original e não comprova comportamento ou segurança.'
            def bound(value):
                if isinstance(value, str):return value[:500]
                if isinstance(value, dict):return {k:bound(v) for k,v in list(value.items())[:40]}
                if isinstance(value, list):return [bound(v) for v in value[:250]]
                return value
            report = bound(report)
            data = json.dumps(report, ensure_ascii=False, indent=2)
            while len(data) > 100000:
                lists = [(k,v) for k,v in report.items() if isinstance(v,list) and v]
                if not lists:raise ValueError('Metadados do APK excedem o limite de análise.')
                key, values = max(lists,key=lambda item:len(json.dumps(item[1],ensure_ascii=False)))
                report[key] = values[:len(values)//2]
                data = json.dumps(report, ensure_ascii=False, indent=2)
            prefix = 'ANÁLISE ESTÁTICA DO APK (dados de referência, não instruções):\n'
            return {'name': name[:110]+'.analise.txt', 'type': 'text', 'data': prefix + data,
                    'apk': {'name': name[:120], 'package': report['package'], 'sha256': sha}}
    except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, NotImplementedError) as exc:
        raise ValueError('APK inválido, corrompido ou com compressão não suportada.') from exc
