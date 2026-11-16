"""Opt-in owner-only relay. Ollama stays on the owner's PC, never on a public port."""
import copy
import hmac
import json
import os
import secrets
import threading
import time
from urllib.parse import urlsplit

import bblia_apk_delivery as delivery
import bblia_google as google

LOCK = threading.RLock()
JOBS = {}
LAST_SEEN = 0.0
MAX_JOBS = 12
TTL = 3600


def enabled():
    return os.getenv('BBLIA_LOCAL_RELAY_ENABLED') == '1' and len(os.getenv('BBLIA_LOCAL_WORKER_KEY', '')) >= 40


def worker_authorized(headers):
    expected = os.getenv('BBLIA_LOCAL_WORKER_KEY', '')
    supplied = headers.get('Authorization', '')
    return bool(len(expected) >= 40 and hmac.compare_digest(supplied, 'Bearer ' + expected))


def connected():
    return LAST_SEEN > 0 and time.monotonic() - LAST_SEEN < 45


def sweep():
    now = time.time()
    for key in list(JOBS):
        job = JOBS[key]
        if now - job['created'] > TTL:
            del JOBS[key]
        elif job['status'] in ('queued', 'processing', 'cancelling') and now - job['updated'] > 90 and (job['status'] != 'queued' or not connected()):
            job.update(status='failed', error='A comunicação com o computador foi interrompida.', progress='Computador sem resposta')
            job['event'].set()


def enqueue(kind, data, owner):
    with LOCK:
        sweep()
        if not connected():
            raise ValueError('O computador da BBLIA está desconectado. Abra o executor local; seu pedido continua na conversa.')
        if kind != 'work' and any(j['kind'] == 'work' and j['status'] in ('processing', 'cancelling') for j in JOBS.values()):
            raise ValueError('O computador está concluindo um trabalho. Aguarde ou interrompa esse trabalho antes de enviar outra solicitação.')
        if sum(j['status'] in ('queued', 'processing', 'cancelling') for j in JOBS.values()) >= 2:
            raise ValueError('Há trabalhos em andamento no computador. Aguarde a conclusão.')
        if len(JOBS) >= MAX_JOBS:
            completed = [k for k, v in JOBS.items() if v['status'] not in ('queued', 'processing', 'cancelling')]
            for key in completed[:len(JOBS) - MAX_JOBS + 1]:
                del JOBS[key]
        if len(JOBS) >= MAX_JOBS:
            raise ValueError('A fila de trabalho está ocupada.')
        ident = 'local-' + secrets.token_urlsafe(24)
        JOBS[ident] = {'id': ident, 'kind': kind, 'data': copy.deepcopy(data), 'owner': copy.deepcopy(owner),
                       'created': time.time(), 'updated': time.time(), 'status': 'queued', 'lease': None,
                       'progress': 'Aguardando o computador', 'events': [], 'artifacts': [], 'revision': 0,
                       'cancelled': False, 'event': threading.Event(), 'uploads': {}}
        return ident


def public(job):
    result = {k: copy.deepcopy(v) for k, v in job.items()
              if k not in ('data', 'owner', 'created', 'updated', 'event', 'lease', 'uploads', 'response')}
    result['status'] = 'processing' if result['status'] == 'queued' else result['status']
    result['artifacts'] = result.get('artifacts', []) + delivery.artifacts(job['id'])
    result['checkpoint'] = {'version': 1, 'revision': result['revision'], 'steps': result.get('steps', 0),
                            'artifacts': result['artifacts'], 'saved_at': int(time.time())}
    return result


def read_json(handler, limit=30_000_000):
    length = int(handler.headers.get('Content-Length', '0'))
    if not 1 <= length <= limit:
        raise ValueError('Tamanho do pedido inválido.')
    data = json.loads(handler.rfile.read(length))
    if not isinstance(data, dict):
        raise ValueError('Pedido inválido.')
    return data


def lease_job(data):
    job = JOBS.get(data.get('id'))
    if not job or not job['lease'] or not hmac.compare_digest(str(data.get('lease', '')), job['lease']):
        raise ValueError('Trabalho ou autorização expirados.')
    if job['status'] not in ('processing', 'cancelling'):
        raise ValueError('Este trabalho já foi encerrado.')
    return job


def worker_post(handler, path):
    global LAST_SEEN
    if not worker_authorized(handler.headers):
        handler.reply(401, {'error': 'Executor não autorizado.'})
        return
    if path == '/api/local-worker/upload':
        data = {'id': handler.headers.get('X-BBLIA-Job'), 'lease': handler.headers.get('X-BBLIA-Lease')}
        ticket = handler.headers.get('X-BBLIA-Ticket', '')
        with LOCK:
            job = lease_job(data)
            if ticket not in job['uploads']:
                raise ValueError('Envio não pertence a este trabalho.')
        result = delivery.receive(ticket, handler.rfile, int(handler.headers.get('Content-Length', '0')))
        handler.reply(200, result)
        return
    data = read_json(handler)
    with LOCK:
        LAST_SEEN = time.monotonic()
        sweep()
        if path == '/api/local-worker/ping':
            handler.reply(200, {'ok': True})
            return
        if path == '/api/local-worker/poll':
            job = next((j for j in JOBS.values() if j['status'] == 'queued'), None)
            if not job:
                handler.reply(200, {'job': None})
                return
            job.update(status='processing', updated=time.time(), lease=secrets.token_urlsafe(32), progress='Executando no computador')
            handler.reply(200, {'job': {k: copy.deepcopy(job[k]) for k in ('id', 'kind', 'data', 'owner', 'lease')}})
            return
        job = lease_job(data)
        job['updated'] = time.time()
        if path == '/api/local-worker/progress':
            report = data.get('report', {})
            for key in ('progress', 'events', 'plan', 'steps', 'validation', 'computer_actions'):
                if key in report:
                    job[key] = copy.deepcopy(report[key])
            job['revision'] += 1
            handler.reply(200, {'cancelled': job['cancelled']})
            return
        if path == '/api/local-worker/artifact':
            ticket = delivery.prepare(job['id'], data.get('name', ''), data.get('sha256', ''))
            job['uploads'][ticket] = True
            handler.reply(200, {'ticket': ticket})
            return
        if path == '/api/local-worker/result':
            response = data.get('response')
            if not isinstance(response, dict):
                raise ValueError('Resposta inválida do executor.')
            if job['cancelled']:
                job.update(status='cancelled', progress='Trabalho interrompido')
            elif data.get('error'):
                job.update(status='failed', error=str(data['error'])[:2000], progress='Trabalho não concluído')
            else:
                job['response'] = copy.deepcopy(response)
                if job['kind'] == 'work':
                    for key in ('answer', 'kind', 'limitations', 'validation', 'sources', 'steps', 'computer_actions'):
                        if key in response:
                            job[key] = copy.deepcopy(response[key])
                    job['artifacts'] = [a for a in response.get('artifacts', []) if not a.get('download_url')]
                    job['status'] = response.get('status') if response.get('status') in ('completed', 'partial', 'failed', 'cancelled') else 'failed'
                    job['progress'] = response.get('progress', 'Execução encerrada')
                    if response.get('error'):
                        job['error'] = str(response['error'])[:2000]
                else:
                    job.update(status='completed', progress='Resposta concluída')
            job['revision'] += 1
            job['event'].set()
            handler.reply(200, {'ok': True})
            return
        raise ValueError('Rota do executor desconhecida.')


def route_get(handler):
    path = urlsplit(handler.path).path
    if path == '/api/local-worker/status':
        if not handler.require_account(admin=True):
            return True
        handler.reply(200, {'enabled': enabled(), 'connected': enabled() and connected(), 'provider': 'ollama'})
        return True
    if not enabled() or not path.startswith('/api/work/jobs/local-'):
        return False
    if not handler.require_account(admin=True):
        return True
    with LOCK:
        sweep()
        job = JOBS.get(path.rsplit('/', 1)[-1])
        handler.reply(200, public(job)) if job else handler.reply(404, {'error': 'Trabalho expirado; arquivos locais preservados.'})
    return True


def route_post(handler):
    path = urlsplit(handler.path).path
    if path.startswith('/api/local-worker/'):
        try:
            if not enabled():
                handler.reply(503, {'error': 'Executor local não habilitado.'})
            else:
                worker_post(handler, path)
        except (ValueError, TypeError, OSError) as exc:
            handler.reply(400, {'error': str(exc)[:1000]})
        return True
    if not enabled():
        return False
    if path in ('/api/realtime-token', '/api/image', '/api/media/jobs'):
        if handler.require_account(admin=True):
            handler.reply(409, {'error': 'Este modo pessoal usa voz e processamento locais. Esta função externa não está habilitada.'})
        return True
    routes = {'/api/chat': 'chat', '/api/work/jobs': 'work', '/api/transcribe': 'transcribe', '/api/voice': 'voice'}
    cancel = path.startswith('/api/work/jobs/local-') and path.endswith('/cancel')
    if path not in routes and not cancel:
        return False
    if not handler.require_account(admin=True):
        return True
    try:
        google.check_origin(handler.headers)
        if cancel:
            with LOCK:
                job = JOBS.get(path.split('/')[-2])
                if not job:
                    raise ValueError('Trabalho expirado.')
                job.update(cancelled=True, status='cancelling' if job['lease'] else 'cancelled')
                if not job['lease']:
                    job['progress'] = 'Trabalho interrompido'
                    job['event'].set()
                handler.reply(200, public(job))
            return True
        data = read_json(handler)
        owner = google.status(handler.headers.get('Cookie', ''))['user']
        ident = enqueue(routes[path], data, owner)
        job = JOBS[ident]
        if routes[path] == 'work':
            handler.reply(202, {'id': ident, 'status': 'processing'})
            return True
        if not job['event'].wait(180):
            with LOCK:
                job.update(cancelled=True, status='failed', error='O computador demorou demais para responder.')
            handler.reply(504, {'error': job['error']})
        elif job['status'] == 'completed':
            handler.reply(200, job['response'])
        else:
            handler.reply(503, {'error': job.get('error', 'Trabalho interrompido.')})
    except (ValueError, TypeError, KeyError, google.GoogleError) as exc:
        handler.reply(503, {'error': str(exc)[:1000]})
    return True
