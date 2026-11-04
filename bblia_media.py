"""Bounded, asynchronous media jobs. Provider keys remain on the server."""
import os
import json
import secrets
import re
import tempfile
from pathlib import Path
import threading
import time
import urllib.request
import urllib.error

LOCK = threading.Lock()
SLOTS = threading.BoundedSemaphore(2)
JOBS = {}
USAGE = {}
VIDEO_DIR = Path(tempfile.gettempdir()) / "bblia-video-cache"
VIDEO_DIR.mkdir(exist_ok=True)


class MediaError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def capabilities():
    return {'image': bool(os.getenv('OPENAI_API_KEY')),
            'video': True, 'video_provider': 'ltx-free', 'video_paid_fallback': False, 'video_app_daily_limit': None,
            'video_notice': 'Vídeos gratuitos pelo LTX Video, sujeitos a fila, cota e disponibilidade.'}


def request_json(url, key, payload=None, timeout=30):
    headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            details = json.loads(exc.read(4000))
            error = details.get('error', {})
            message = error.get('message', '') if isinstance(error, dict) else str(error)
            code = error.get('code', '') if isinstance(error, dict) else ''
        except Exception:
            message = code = ''
        if exc.code == 401:
            raise MediaError('A conexão do serviço de mídia precisa ser atualizada.', 503)
        if exc.code == 429:
            raise MediaError('O serviço de mídia está sem saldo ou atingiu seu limite. Verifique os créditos.', 503)
        if 'verif' in message.lower():
            raise MediaError('A conta OpenAI precisa concluir a verificação para gerar imagens.', 503)
        if 'moderation' in str(code) or 'safety' in str(code):
            raise MediaError('O serviço recusou esta descrição. Tente outra imagem.', 422)
        raise MediaError('O serviço não conseguiu gerar a mídia (HTTP %s). Tente novamente.' % exc.code, 502)


def generate_image(prompt):
    result = request_json('https://api.openai.com/v1/images/generations',
                          os.environ['OPENAI_API_KEY'],
                          {'model': 'gpt-image-1-mini', 'prompt': prompt,
                           'size': '1024x1024', 'quality': 'low', 'n': 1}, timeout=180)
    encoded = result['data'][0]['b64_json']
    return {'image': 'data:image/png;base64,' + encoded}


# Fixed public demo endpoint: no provider key, billing, or paid fallback.
FREE_VIDEO_HOST = 'https://lightricks-ltx-video-distilled.hf.space'


def free_video_error(details):
    text = str(details).lower()
    if any(term in text for term in ('quota', 'limit', 'exceed')):
        return MediaError('A cota gratuita de vídeo foi atingida. Aguarde a renovação e tente novamente. Nenhuma cobrança será feita.', 429)
    if any(term in text for term in ('sign in', 'log in', 'login', 'unauth', 'forbidden')):
        return MediaError('O serviço gratuito está pedindo acesso pelo Hugging Face. A geração não foi concluída e não houve cobrança.', 503)
    return MediaError('O gerador gratuito de vídeo está indisponível ou não concluiu o pedido. Tente mais tarde. Nenhuma cobrança será feita.', 503)


def generate_video(prompt):
    parameters = [prompt, 'blurry, distorted, inconsistent motion, jittery',
                  None, None, 480, 832, 'text-to-video', 4.0, 9, 42, True, 1.0, False]
    endpoint = FREE_VIDEO_HOST + '/gradio_api/call/text_to_video'
    request = urllib.request.Request(endpoint, data=json.dumps({'data': parameters}).encode(),
                                     headers={'Content-Type': 'application/json', 'User-Agent': 'BBLIA/1.0'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            event_id = json.load(response)['event_id']
        if not isinstance(event_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', event_id):
            raise MediaError('O gerador gratuito retornou um pedido inválido.', 502)
        event = ''
        deadline = time.monotonic() + 900
        # Gradio streams heartbeat/complete/error SSE events while the free GPU is queued.
        with urllib.request.urlopen(endpoint + '/' + event_id, timeout=60) as response:
            for raw in response:
                if time.monotonic() > deadline:
                    raise MediaError('A fila gratuita demorou demais. Tente mais tarde; não houve cobrança.', 504)
                line = raw.decode('utf-8').strip()
                if line.startswith('event:'):
                    event = line[6:].strip()
                elif line.startswith('data:') and event in ('complete', 'error'):
                    data = json.loads(line[5:])
                    if event == 'error':
                        raise free_video_error(data)
                    if not isinstance(data, list) or not data:
                        raise free_video_error('empty result')
                    file_data = data[0].get('video', {})
                    url = file_data.get('url', '')
                    if not url.startswith(FREE_VIDEO_HOST + '/gradio_api/file='):
                        raise MediaError('O serviço retornou um vídeo inválido.', 502)
                    return {'video': url, 'provider': 'ltx-free', 'free': True}
        raise free_video_error('stream ended')
    except urllib.error.HTTPError as exc:
        details = exc.read(3000).decode('utf-8', 'replace')
        if exc.code in (401, 403):
            details += ' unauthorized'
        if exc.code == 429:
            details += ' quota'
        raise free_video_error(details)
    except (TimeoutError, OSError):
        raise MediaError('A conexão com o gerador gratuito demorou demais. Tente mais tarde; não houve cobrança.', 504)


def cache_video(url, job_id):
    if not url.startswith(FREE_VIDEO_HOST + '/gradio_api/file='):
        raise MediaError('O serviço retornou um vídeo inválido.', 502)
    target = VIDEO_DIR / (job_id + '.mp4')
    temporary = target.with_suffix('.part')
    try:
        with urllib.request.urlopen(url, timeout=45) as response, temporary.open('wb') as output:
            total = 0
            first = response.read(65536)
            if b'ftyp' not in first[:64]:
                raise MediaError('O gerador não entregou um arquivo de vídeo válido. Tente novamente.', 502)
            output.write(first)
            total += len(first)
            while True:
                chunk = response.read(262144)
                if not chunk:
                    break
                total += len(chunk)
                if total > 40 * 1024 * 1024:
                    raise MediaError('O vídeo excedeu o tamanho suportado.', 502)
                output.write(chunk)
        temporary.replace(target)
        return target
    except Exception:
        temporary.unlink(missing_ok=True)
        raise MediaError('O gerador não entregou o arquivo de vídeo. Tente criar novamente; não houve cobrança.', 502)


def get_video(job_id):
    with LOCK:
        job = JOBS.get(job_id, {})
        path = job.get('_video_path')
    if not path or not Path(path).is_file():
        raise MediaError('Este vídeo expirou ou o servidor reiniciou. Crie novamente.', 404)
    return Path(path)


def start_job(kind, prompt, client):
    if kind not in ('image', 'video') or not isinstance(prompt, str) or not 5 <= len(prompt.strip()) <= 900:
        raise MediaError('Descreva sua imagem ou vídeo em até 900 caracteres.')
    if not capabilities()[kind]:
        raise MediaError('A geração de imagens ainda precisa conectar a conta OpenAI.', 503)
    if not SLOTS.acquire(blocking=False):
        raise MediaError('A criação de mídia está ocupada. Tente em alguns instantes.', 429)
    day = int(time.time() // 86400)
    token = (day, kind, client)
    with LOCK:
        for job_id in list(JOBS):
            if time.time() - JOBS[job_id]['created'] > 3600 and JOBS[job_id]['status'] != 'processing':
                path = JOBS[job_id].get('_video_path')
                if path:
                    Path(path).unlink(missing_ok=True)
                del JOBS[job_id]
        for usage_key in list(USAGE):
            if usage_key[0] < day:
                del USAGE[usage_key]
        total = sum(v for (d, k, _), v in USAGE.items() if d == day and k == kind)
        # Only paid image generation has an app-level daily budget.
        # Free videos follow the provider's quota without a second daily cap.
        if kind == 'image' and (USAGE.get(token, 0) >= 3 or total >= 8):
            SLOTS.release()
            raise MediaError('Limite diário de criação atingido. Tente novamente amanhã.', 429)
        USAGE[token] = USAGE.get(token, 0) + 1
        job_id = secrets.token_urlsafe(24)
        JOBS[job_id] = {'id': job_id, 'kind': kind, 'status': 'processing', 'created': time.time()}

    def work():
        try:
            result = generate_image(prompt.strip()) if kind == 'image' else generate_video(prompt.strip())
            if kind == 'video':
                path = cache_video(result['video'], job_id)
                result.update(video='/api/media/jobs/' + job_id + '/video', _video_path=str(path))
            with LOCK:
                JOBS[job_id].update(status='completed', **result)
            print('BBLIA_MEDIA completed kind=' + kind, flush=True)
        except Exception as exc:
            message = str(exc) if isinstance(exc, MediaError) else 'Não foi possível concluir a criação. Tente novamente.'
            print('BBLIA_MEDIA failed kind=' + kind + ' reason=' + message, flush=True)
            with LOCK:
                JOBS[job_id].update(status='failed', error=message)
                # Failed free videos and images do not consume the app's success quota.
                USAGE[token] = max(0, USAGE.get(token, 0) - 1)
        finally:
            SLOTS.release()
    threading.Thread(target=work, daemon=True).start()
    return {'id': job_id, 'status': 'processing', 'kind': kind}


def get_job(job_id):
    with LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise MediaError('Criação não encontrada ou expirada. O servidor pode ter reiniciado.', 404)
        return {key: value for key, value in job.items() if key != 'created' and not key.startswith('_')}
