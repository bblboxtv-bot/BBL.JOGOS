"""Pull-only worker for the owner's BBLIA. Never exposes Ollama to the network."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
import urllib.request
from urllib.parse import urlsplit


class Worker:
    def __init__(self, origin, key, runtime):
        parsed = urlsplit(origin)
        if parsed.scheme != 'https' or parsed.hostname != 'bblia-teste.onrender.com' or parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.username:
            raise ValueError('Use somente a origem HTTPS autorizada da BBLIA de testes.')
        if len(key) < 40:
            raise ValueError('Chave privada do executor ausente ou inválida.')
        self.origin, self.key = origin.rstrip('/'), key
        sys.path.insert(0, str(Path(runtime).resolve()))
        import servidor_integrado_local as local
        import bblia_auth_http_stage as auth
        self.local, self.auth = local, auth
        local.login.DB = Path(runtime).resolve() / 'worker-sessions.sqlite3'
        self.server = local.create_server(0)
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def remote(self, path, data, extra=None):
        payload = data if isinstance(data, bytes) else json.dumps(data).encode()
        headers = {'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'}
        headers.update(extra or {})
        request = urllib.request.Request(self.origin + path, data=payload, headers=headers)
        with urllib.request.urlopen(request, timeout=35) as response:
            return json.load(response)

    def local_request(self, path, cookie, data=None):
        request = urllib.request.Request(self.base + path, data=json.dumps(data).encode() if data is not None else None,
                                         headers={'Content-Type': 'application/json', 'Cookie': cookie})
        with urllib.request.urlopen(request, timeout=180) as response:
            raw = response.read(110 * 1024 * 1024)
            return json.loads(raw) if 'application/json' in response.headers.get('Content-Type', '') else raw

    def cookie_for(self, owner):
        # Identity comes from the authenticated server queue, never browser fields.
        ident = owner.get('id')
        if not isinstance(ident, str) or not ident or len(ident) > 200:
            raise ValueError('Identidade do proprietário não confirmada.')
        subject = 'google:' + ident
        with self.local.sessions.connection(str(self.local.login.DB)) as db:
            db.execute('CREATE TABLE IF NOT EXISTS local_profiles(subject TEXT PRIMARY KEY,name TEXT,email TEXT,role TEXT)')
            db.execute('INSERT OR REPLACE INTO local_profiles VALUES (?,?,?,?)',
                       (subject, str(owner.get('name', ''))[:150], str(owner.get('email', ''))[:250], 'admin'))
        _, header = self.auth.login_verified(str(self.local.login.DB), 'google', subject)
        return header.split(';', 1)[0]

    def upload_artifacts(self, job, response, cookie):
        for artifact in response.get('artifacts', []):
            path = artifact.get('download_url')
            if not path:
                continue
            if not re.fullmatch(r'/api/apk/download/[A-Za-z0-9_-]{20,100}', path):
                raise ValueError('Endereço de APK local inválido.')
            data = self.local_request(path, cookie)
            if not isinstance(data, bytes) or hashlib.sha256(data).hexdigest() != artifact.get('sha256'):
                raise ValueError('APK local não corresponde ao hash verificado.')
            fields = {'id': job['id'], 'lease': job['lease'], 'name': artifact['name'], 'sha256': artifact['sha256']}
            ticket = self.remote('/api/local-worker/artifact', fields)['ticket']
            self.remote('/api/local-worker/upload', data, {'Content-Type': 'application/vnd.android.package-archive',
                        'X-BBLIA-Job': job['id'], 'X-BBLIA-Lease': job['lease'], 'X-BBLIA-Ticket': ticket})

    def execute(self, job):
        fields = {'id': job['id'], 'lease': job['lease']}
        stop, cancelled = threading.Event(), threading.Event()
        cookie = self.cookie_for(job['owner'])
        progress = {'progress': 'Computador processando o pedido'}

        def heartbeat():
            while not stop.wait(8):
                try:
                    result = self.remote('/api/local-worker/progress', {**fields, 'report': dict(progress)})
                    if result.get('cancelled'):
                        cancelled.set()
                except Exception:
                    pass

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            kind = job['kind']
            data = dict(job['data'])
            data.update(provider='ollama', paid_authorized=False)
            if kind == 'work':
                data.update(use_computer=True)
                # This is an owner-authorized test executor, not public local access.
                os.environ['BBLIA_LOCAL_ANDROID_GENERATION_ENABLED'] = '1'
                local_job = self.local_request('/api/work/jobs', cookie, data)['id']
                while True:
                    if cancelled.is_set():
                        self.local_request('/api/work/jobs/' + local_job + '/cancel', cookie, {})
                    result = self.local_request('/api/work/jobs/' + local_job, cookie)
                    progress.clear()
                    progress.update({k: result[k] for k in ('progress', 'events', 'plan', 'steps', 'validation', 'computer_actions') if k in result})
                    if result['status'] not in ('processing', 'cancelling'):
                        break
                    time.sleep(2)
                self.upload_artifacts(job, result, cookie)
            elif kind in ('chat', 'transcribe', 'voice'):
                result = self.local_request('/api/' + kind, cookie, data)
                if isinstance(result, bytes):
                    result = {'segments': [base64.b64encode(result).decode()], 'mime': 'audio/wav'}
            else:
                raise ValueError('Tipo de tarefa não permitido.')
            self.remote('/api/local-worker/result', {**fields, 'response': result})
        except Exception as exc:
            # HTTP messages are intentionally concise; never send headers or secrets.
            self.remote('/api/local-worker/result', {**fields, 'response': {}, 'error': str(exc)[:1500]})
        finally:
            stop.set()
            thread.join(timeout=10)
            self.auth.logout(str(self.local.login.DB), cookie)

    def run(self):
        print('Executor BBLIA iniciado; conexão somente de saída, sem API paga.', flush=True)
        connected = False
        while True:
            try:
                job = self.remote('/api/local-worker/poll', {})['job']
                if not connected:
                    print('Executor BBLIA conectado ao servidor de testes.', flush=True)
                    connected = True
                if job:
                    self.execute(job)
                else:
                    time.sleep(3)
            except Exception as exc:
                connected = False
                print('Executor aguardando conexão: ' + type(exc).__name__, flush=True)
                time.sleep(8)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', required=True)
    args = parser.parse_args()
    Worker(os.getenv('BBLIA_LOCAL_RELAY_ORIGIN', 'https://bblia-teste.onrender.com'),
           os.getenv('BBLIA_LOCAL_WORKER_KEY', ''), args.runtime).run()
