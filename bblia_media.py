"""Bounded, asynchronous media jobs. Provider keys remain on the server."""
import os
import json
import secrets
import re
import tempfile
import base64
import uuid
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
    def __init__(self, message, status=400, code=None):
        super().__init__(message)
        self.status = status
        self.code = code


def capabilities():
    return {'image': bool(os.getenv('OPENAI_API_KEY')),
            'video': True, 'video_provider': 'ltx-free', 'video_paid_fallback': False, 'video_app_daily_limit': None,
            'video_account_connected': bool(os.getenv('HF_TOKEN', '').strip()),
            'video_notice': 'Vídeos gratuitos pelo LTX Video, sujeitos à cota do Hugging Face e à disponibilidade da fila.'}


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


def generate_image(prompt, reference=None):
    if reference:
        return edit_image(prompt, reference)
    result = request_json('https://api.openai.com/v1/images/generations',
                          os.environ['OPENAI_API_KEY'],
                          {'model': 'gpt-image-1-mini', 'prompt': prompt,
                           'size': '1024x1024', 'quality': 'low', 'n': 1}, timeout=180)
    encoded = result['data'][0]['b64_json']
    return {'image': 'data:image/png;base64,' + encoded}


def edit_image(prompt, reference):
    data = reference['data']
    mime, encoded = data.split(';base64,', 1)
    mime = mime.removeprefix('data:')
    ext = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp'}[mime]
    boundary = 'bblia' + uuid.uuid4().hex
    chunks = []
    fields = {'model': 'gpt-image-1-mini', 'prompt': prompt, 'size': '1024x1024', 'quality': 'low', 'n': '1'}
    for name, value in fields.items():
        chunks.append(('--'+boundary+'\r\nContent-Disposition: form-data; name="'+name+'"\r\n\r\n'+value+'\r\n').encode())
    chunks.append(('--'+boundary+'\r\nContent-Disposition: form-data; name="image"; filename="reference.'+ext+'"\r\nContent-Type: '+mime+'\r\n\r\n').encode())
    chunks.append(base64.b64decode(encoded, validate=True))
    chunks.append(('\r\n--'+boundary+'--\r\n').encode())
    req = urllib.request.Request('https://api.openai.com/v1/images/edits', data=b''.join(chunks), headers={'Authorization': 'Bearer '+os.environ['OPENAI_API_KEY'], 'Content-Type': 'multipart/form-data; boundary='+boundary})
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            result = json.load(response)
        return {'image': 'data:image/png;base64,'+result['data'][0]['b64_json']}
    except urllib.error.HTTPError as exc:
        raise MediaError('Não foi possível editar a foto (HTTP %s). Confira a disponibilidade do serviço de imagens.' % exc.code, 503)


# Fixed public demo endpoint: no provider key, billing, or paid fallback.
FREE_VIDEO_HOST = 'https://lightricks-ltx-video-distilled.hf.space'


def free_video_headers():
    headers = {'Content-Type': 'application/json', 'User-Agent': 'BBLIA/1.0'}
    token = os.getenv('HF_TOKEN', '').strip()
    if token:
        headers['Authorization'] = 'Bearer ' + token
    return headers


def free_video_error(details):
    # The public /call endpoint hides some upstream errors as `data: null`.
    # Queue events retain the structured ZeroGPU quota/authentication error.
    text = str(details).lower()
    if any(term in text for term in ('quota', 'limit', 'exceed')):
        if os.getenv('HF_TOKEN', '').strip():
            message = 'A cota gratuita de vídeo da conta Hugging Face foi atingida. Aguarde a renovação da cota. Nenhuma cobrança foi feita pela BBLIA.'
        else:
            message = 'A cota gratuita de vídeo usada pelo servidor está esgotada. É necessário conectar uma conta gratuita Hugging Face ou aguardar a renovação da cota. Nenhuma cobrança foi feita pela BBLIA.'
        return MediaError(message, 429, 'video_quota_exceeded')
    if any(term in text for term in ('sign in', 'log in', 'login', 'unauth', 'forbidden', 'token invalid')):
        return MediaError('A conexão gratuita com o Hugging Face precisa ser autenticada. O vídeo não foi criado.', 503, 'video_auth_required')
    if 'queue' in text and any(term in text for term in ('full', 'busy')):
        return MediaError('A fila do gerador gratuito está cheia. Tente novamente mais tarde.', 503, 'video_queue_full')
    return MediaError('O gerador gratuito de vídeo não concluiu o pedido. O vídeo não foi criado e não houve cobrança pela BBLIA.', 503, 'video_provider_error')


def generate_video(prompt):
    headers = free_video_headers()
    parameters = [prompt, 'blurry, distorted, inconsistent motion, jittery',
                  None, None, 480, 832, 'text-to-video', 4.0, 9, 42, True, 1.0, False]
    session = uuid.uuid4().hex
    try:
        # Resolve the function index from the live contract, instead of assuming
        # it stays the same when the provider changes its UI.
        config_req = urllib.request.Request(FREE_VIDEO_HOST + '/config', headers=headers)
        with urllib.request.urlopen(config_req, timeout=30) as response:
            config = json.load(response)
        dependency = next((item for item in config.get('dependencies', [])
                           if item.get('api_name') == 'text_to_video'), None)
        if not dependency or not isinstance(dependency.get('id'), int):
            raise MediaError('O gerador gratuito mudou sua integração. A conexão precisa ser atualizada.', 503, 'video_contract_changed')
        payload = {'data': parameters, 'fn_index': dependency['id'], 'session_hash': session}
        request = urllib.request.Request(FREE_VIDEO_HOST + '/gradio_api/queue/join',
                                         data=json.dumps(payload).encode(), headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            event_id = json.load(response).get('event_id')
        if not isinstance(event_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', event_id):
            raise MediaError('O gerador gratuito retornou um pedido inválido.', 502, 'video_invalid_response')
        deadline = time.monotonic() + 900
        stream = urllib.request.Request(FREE_VIDEO_HOST + '/gradio_api/queue/data?session_hash=' + session,
                                        headers=headers)
        with urllib.request.urlopen(stream, timeout=60) as response:
            for raw in response:
                if time.monotonic() > deadline:
                    raise MediaError('A fila gratuita demorou demais. Tente mais tarde.', 504, 'video_timeout')
                line = raw.decode('utf-8').strip()
                if not line.startswith('data:'):
                    continue
                event = json.loads(line[5:])
                if not isinstance(event, dict) or event.get('event_id') not in (None, event_id):
                    continue
                if event.get('msg') in ('queue_full', 'unexpected_error'):
                    raise free_video_error(event)
                if event.get('msg') != 'process_completed':
                    continue
                output = event.get('output') or {}
                if not event.get('success') or not isinstance(output, dict) or output.get('error'):
                    raise free_video_error(output)
                data = output.get('data')
                if not isinstance(data, list) or not data or not isinstance(data[0], dict):
                    raise MediaError('O gerador não entregou o arquivo de vídeo.', 502, 'video_invalid_response')
                file_data = data[0].get('video') or {}
                url = file_data.get('url', '') if isinstance(file_data, dict) else ''
                if not isinstance(url, str) or not url.startswith(FREE_VIDEO_HOST + '/gradio_api/file='):
                    raise MediaError('O serviço retornou um vídeo inválido.', 502, 'video_invalid_response')
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
        raise MediaError('A conexão com o gerador gratuito demorou demais. Tente mais tarde.', 504, 'video_timeout')


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


def start_job(kind, prompt, client, reference=None):
    if kind not in ('image', 'video') or not isinstance(prompt, str) or not 5 <= len(prompt.strip()) <= 900:
        raise MediaError('Descreva sua imagem ou vídeo em até 900 caracteres.')
    if reference:
        from bblia_work import attachment_parts
        attachment_parts([reference])
        if reference.get('type') != 'image' or kind != 'image':
            raise MediaError('Anexe uma imagem para editar.')
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
        USAGE[token] = USAGE.get(token, 0) + 1
        job_id = secrets.token_urlsafe(24)
        JOBS[job_id] = {'id': job_id, 'kind': kind, 'status': 'processing', 'created': time.time()}

    def work():
        try:
            result = generate_image(prompt.strip(), reference) if kind == 'image' else generate_video(prompt.strip())
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
                JOBS[job_id].update(status='failed', error=message, error_code=exc.code if isinstance(exc, MediaError) else None)
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

