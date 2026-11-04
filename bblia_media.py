"""Bounded, asynchronous media jobs. Provider keys remain on the server."""
import os
import json
import secrets
import threading
import time
import urllib.request
import urllib.error

LOCK = threading.Lock()
SLOTS = threading.BoundedSemaphore(2)
JOBS = {}
USAGE = {}


class MediaError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def capabilities():
    return {'image': bool(os.getenv('OPENAI_API_KEY')),
            'video': bool(os.getenv('RUNWAYML_API_SECRET')),
            'video_notice': 'Vídeos precisam da conexão do serviço de geração de vídeo.'}


def request_json(url, key, payload=None, runway=False, timeout=30):
    headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}
    if runway:
        headers['X-Runway-Version'] = '2024-11-06'
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


def generate_video(prompt):
    key = os.environ['RUNWAYML_API_SECRET']
    created = request_json('https://api.dev.runwayml.com/v1/text_to_video', key,
                           {'model': 'gen4.5', 'promptText': prompt,
                            'ratio': '1280:720', 'duration': 5}, runway=True)
    task_id = created['id']
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        result = request_json('https://api.dev.runwayml.com/v1/tasks/' + task_id,
                              key, runway=True)
        if result['status'] == 'SUCCEEDED':
            url = result['output'][0]
            if not url.startswith('https://'):
                raise MediaError('O serviço retornou um vídeo inválido.', 502)
            return {'video': url}
        if result['status'] in ('FAILED', 'CANCELED'):
            raise MediaError('O serviço não concluiu este vídeo. Tente outra descrição.', 502)
        time.sleep(8)
    raise MediaError('O vídeo demorou mais que o esperado. Consulte o serviço antes de tentar novamente.', 504)


def start_job(kind, prompt, client):
    if kind not in ('image', 'video') or not isinstance(prompt, str) or not 5 <= len(prompt.strip()) <= 900:
        raise MediaError('Descreva sua imagem ou vídeo em até 900 caracteres.')
    if not capabilities()[kind]:
        raise MediaError('A geração de vídeos ainda precisa conectar a conta de vídeo.' if kind == 'video'
                         else 'A geração de imagens ainda precisa conectar a conta OpenAI.', 503)
    if not SLOTS.acquire(blocking=False):
        raise MediaError('A criação de mídia está ocupada. Tente em alguns instantes.', 429)
    day = int(time.time() // 86400)
    token = (day, kind, client)
    with LOCK:
        for job_id in list(JOBS):
            if time.time() - JOBS[job_id]['created'] > 3600 and JOBS[job_id]['status'] != 'processing':
                del JOBS[job_id]
        for usage_key in list(USAGE):
            if usage_key[0] < day:
                del USAGE[usage_key]
        total = sum(v for (d, k, _), v in USAGE.items() if d == day and k == kind)
        # Keep total image budget unchanged; allow retries when providers fail.
        if USAGE.get(token, 0) >= (3 if kind == 'image' else 1) or total >= (8 if kind == 'image' else 2):
            SLOTS.release()
            raise MediaError('Limite diário de criação atingido. Tente novamente amanhã.', 429)
        USAGE[token] = USAGE.get(token, 0) + 1
        job_id = secrets.token_urlsafe(24)
        JOBS[job_id] = {'id': job_id, 'kind': kind, 'status': 'processing', 'created': time.time()}

    def work():
        try:
            result = generate_image(prompt.strip()) if kind == 'image' else generate_video(prompt.strip())
            with LOCK:
                JOBS[job_id].update(status='completed', **result)
        except Exception as exc:
            message = str(exc) if isinstance(exc, MediaError) else 'Não foi possível concluir a criação. Tente novamente.'
            with LOCK:
                JOBS[job_id].update(status='failed', error=message)
                # Refund image errors. Video jobs may have incurred a charge before failing.
                if kind == 'image':
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
        return {key: value for key, value in job.items() if key != 'created'}
