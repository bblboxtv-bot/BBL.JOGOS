import concurrent.futures
import hashlib
import io
import json
import os
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from unittest.mock import patch
from http.server import ThreadingHTTPServer

import bblia_app as app
import bblia_local_relay as relay
from bblia_local_worker import Worker
from types import SimpleNamespace


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'BBLIA_LOCAL_RELAY_ENABLED': '1', 'BBLIA_LOCAL_WORKER_KEY': 'test-private-worker-' * 4})
        self.env.start()
        relay.JOBS.clear()
        relay.LAST_SEEN = 0
        self.account = patch.object(app.google, 'status', side_effect=lambda cookie: {
            'authenticated': cookie == 'owner-test', 'role': 'admin' if cookie == 'owner-test' else 'guest',
            'user': {'id': 'verified-owner', 'email': 'owner@example.test'}, 'services': [], 'connected': cookie == 'owner-test'})
        self.account.start()
        self.origin = patch.object(app.google, 'check_origin', side_effect=lambda headers: None if headers.get('Origin') == 'https://bblia-teste.onrender.com' else (_ for _ in ()).throw(app.google.GoogleError('Origem inválida', 403)))
        self.origin.start()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.origin.stop()
        self.account.stop()
        self.env.stop()

    def request(self, path, data=None, owner=False, worker=False, headers=None):
        extra = {'Content-Type': 'application/json'}
        if owner:
            extra.update(Cookie='owner-test', Origin='https://bblia-teste.onrender.com')
        if worker:
            extra['Authorization'] = 'Bearer ' + os.environ['BBLIA_LOCAL_WORKER_KEY']
        extra.update(headers or {})
        raw = data if isinstance(data, bytes) else json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(self.base + path, data=raw, headers=extra)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                body = response.read()
                return response.status, json.loads(body) if 'application/json' in response.headers.get('Content-Type', '') else body
        except urllib.error.HTTPError as exc:
            return exc.code, json.load(exc)

    def poll(self):
        return self.request('/api/local-worker/poll', {}, worker=True)[1]['job']

    def test_worker_auth_and_owner_auth(self):
        self.assertEqual(self.request('/api/local-worker/poll', {})[0], 401)
        self.assertEqual(self.request('/api/local-worker/status')[0], 401)
        self.assertIsNone(self.poll())
        status = self.request('/api/local-worker/status', owner=True)[1]
        self.assertTrue(status['connected'])
        self.assertNotIn('key', status)

    def test_offline_fails_without_paid_provider(self):
        code, result = self.request('/api/chat', {'messages': [{'role': 'user', 'content': 'Oi'}]}, owner=True)
        self.assertEqual(code, 503)
        self.assertIn('desconectado', result['error'])
        self.assertEqual(len(relay.JOBS), 0)

    def test_authenticated_chat_roundtrip_and_lease_binding(self):
        self.poll()
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            future = pool.submit(self.request, '/api/chat', {'messages': [{'role': 'user', 'content': '2+2'}]}, True)
            job = None
            for _ in range(40):
                job = self.poll()
                if job:
                    break
                time.sleep(.02)
            self.assertEqual(job['owner']['id'], 'verified-owner')
            code, _ = self.request('/api/local-worker/result', {'id': job['id'], 'lease': 'wrong', 'response': {'answer': 'x'}}, worker=True)
            self.assertEqual(code, 400)
            self.request('/api/local-worker/result', {'id': job['id'], 'lease': job['lease'], 'response': {'answer': '4'}}, worker=True)
            self.assertEqual(future.result(), (200, {'answer': '4'}))
            self.assertEqual(self.request('/api/local-worker/result', {'id': job['id'], 'lease': job['lease'], 'response': {'answer': 'duplicate'}}, worker=True)[0], 400)

    def test_google_and_sync_routes_remain_original(self):
        self.assertFalse(relay.route_post(type('Request', (), {'path': '/api/account/start'})()))
        self.assertFalse(relay.route_post(type('Request', (), {'path': '/api/sync'})()))
        self.assertFalse(relay.route_get(type('Request', (), {'path': '/google-callback'})()))

    def test_work_and_verified_apk_download(self):
        self.poll()
        code, started = self.request('/api/work/jobs', {'messages': [{'role': 'user', 'content': 'Crie APK'}]}, owner=True)
        self.assertEqual(code, 202)
        job = self.poll()
        self.assertEqual(job['id'], started['id'])
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('AndroidManifest.xml', b'fixture-manifest')
            z.writestr('classes.dex', b'fixture-dex')
        raw = buf.getvalue()
        digest = hashlib.sha256(raw).hexdigest()
        fields = {'id': job['id'], 'lease': job['lease']}
        ticket = self.request('/api/local-worker/artifact', {**fields, 'name': 'test.apk', 'sha256': digest}, worker=True)[1]['ticket']
        headers = {'Content-Type': 'application/vnd.android.package-archive', 'X-BBLIA-Job': job['id'], 'X-BBLIA-Lease': job['lease'], 'X-BBLIA-Ticket': ticket}
        self.assertEqual(self.request('/api/local-worker/upload', raw, worker=True, headers=headers)[0], 200)
        self.request('/api/local-worker/result', {**fields, 'response': {'status': 'completed', 'answer': 'Fixture', 'artifacts': []}}, worker=True)
        result = self.request('/api/work/jobs/' + job['id'], owner=True)[1]
        self.assertEqual(result['status'], 'completed')
        item = result['artifacts'][0]
        self.assertEqual(self.request(item['download_url'])[0], 401)
        self.assertEqual(hashlib.sha256(self.request(item['download_url'], owner=True)[1]).hexdigest(), digest)

    def test_cancel_before_worker_claim_and_stale_worker(self):
        self.poll()
        ident = self.request('/api/work/jobs', {'messages': []}, owner=True)[1]['id']
        result = self.request('/api/work/jobs/' + ident + '/cancel', {}, owner=True)[1]
        self.assertEqual(result['status'], 'cancelled')
        self.assertIsNone(self.poll())
        ident = self.request('/api/work/jobs', {'messages': []}, owner=True)[1]['id']
        job = self.poll()
        relay.JOBS[ident]['updated'] -= 91
        result = self.request('/api/work/jobs/' + ident, owner=True)[1]
        self.assertEqual(result['status'], 'failed')

    def test_disabled_relay_leaves_native_chat_untouched(self):
        with patch.dict(os.environ, {'BBLIA_LOCAL_RELAY_ENABLED': '0'}):
            self.assertFalse(relay.route_post(type('Request', (), {'path': '/api/chat'})()))

    def test_owner_html_selects_free_worker_only_when_enabled(self):
        code, page = self.request('/', owner=True)
        self.assertEqual(code, 200)
        self.assertIn(b'window.BBLIA_LOCAL_RELAY=true', page)
        with patch.dict(os.environ, {'BBLIA_LOCAL_RELAY_ENABLED': '0'}):
            self.assertEqual(self.request('/', owner=True)[1], app.HTML)
        guest = self.request('/')[1]
        self.assertIn(b'Entrar com Google', guest)
        self.assertNotIn(b'window.BBLIA_LOCAL_RELAY=true', guest)

    def test_browser_origin_cannot_submit_cross_site_work(self):
        self.poll()
        code, _ = self.request('/api/work/jobs', {}, owner=True, headers={'Origin': 'https://untrusted.example'})
        self.assertNotEqual(code, 202)
        self.assertFalse(relay.JOBS)

    def test_worker_executes_local_chat_with_free_provider_and_owner_identity(self):
        self.poll()
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            future = pool.submit(self.request, '/api/chat', {'messages': [{'role': 'user', 'content': 'Oi'}], 'provider': 'openai', 'paid_authorized': True}, True)
            job = None
            for _ in range(40):
                job = self.poll()
                if job:
                    break
                time.sleep(.02)
            worker = Worker.__new__(Worker)
            owners, requests = [], []
            worker.cookie_for = lambda owner: owners.append(owner) or 'private-local-cookie'
            worker.local = SimpleNamespace(login=SimpleNamespace(DB='test-only'))
            worker.auth = SimpleNamespace(logout=lambda *args: None)
            def local_request(path, cookie, data=None):
                requests.append((path, cookie, data))
                return {'answer': 'Olá'}
            worker.local_request = local_request
            def remote(path, data, extra=None):
                status, result = self.request(path, data, worker=True, headers=extra)
                self.assertEqual(status, 200, result)
                return result
            worker.remote = remote
            worker.execute(job)
            self.assertEqual(future.result(), (200, {'answer': 'Olá'}))
            self.assertEqual(owners[0]['id'], 'verified-owner')
            self.assertEqual(requests[0][2]['provider'], 'ollama')
            self.assertIs(requests[0][2]['paid_authorized'], False)

    def test_worker_rejects_arbitrary_artifact_urls(self):
        worker = Worker.__new__(Worker)
        with self.assertRaises(ValueError):
            worker.upload_artifacts({'id': 'x', 'lease': 'x'}, {'artifacts': [{'download_url': 'http://localhost/private'}]}, 'private-local-cookie')


if __name__ == '__main__':
    unittest.main()
