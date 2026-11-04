import io
import json
import os
import unittest
from unittest.mock import patch

from bblia_media import FREE_VIDEO_HOST, MediaError, generate_video, capabilities


class FreeVideoTests(unittest.TestCase):
    def provider(self, event, requests):
        def open_request(req, **kwargs):
            requests.append(req)
            if req.full_url.endswith('/config'):
                return io.BytesIO(json.dumps({'dependencies': [
                    {'id': 19, 'api_name': 'text_to_video'}]}).encode())
            if req.full_url.endswith('/queue/join'):
                self.assertEqual(json.loads(req.data)['fn_index'], 19)
                return io.BytesIO(b'{"event_id":"test123"}')
            self.assertIn('/queue/data?session_hash=', req.full_url)
            unrelated = {'msg': 'process_completed', 'event_id': 'other',
                         'success': False, 'output': {'error': 'ignore'}}
            lines = [unrelated, {'msg': 'process_starts', 'event_id': 'test123'}, event]
            return io.BytesIO(''.join('data: '+json.dumps(e)+'\n\n' for e in lines).encode())
        return open_request

    def test_quota_error_is_preserved_and_not_retried(self):
        requests = []
        event = {'msg': 'process_completed', 'event_id': 'test123', 'success': False,
                 'output': {'error': 'You have exceeded your ZeroGPU quota (120s requested vs. -60s left)'}}
        with patch.dict(os.environ, {'HF_TOKEN': ''}), patch('urllib.request.urlopen', side_effect=self.provider(event, requests)):
            with self.assertRaises(MediaError) as context:
                generate_video('A golden sphere')
        self.assertEqual(context.exception.code, 'video_quota_exceeded')
        self.assertEqual(context.exception.status, 429)
        self.assertIn('conta gratuita', str(context.exception))
        self.assertEqual(len(requests), 3)

    def test_authenticated_success_and_provider_contract(self):
        requests = []
        video = FREE_VIDEO_HOST+'/gradio_api/file=/tmp/generated.mp4'
        event = {'msg': 'process_completed', 'event_id': 'test123', 'success': True,
                 'output': {'data': [{'video': {'url': video}}, 42]}}
        with patch.dict(os.environ, {'HF_TOKEN': 'test-token'}), patch('urllib.request.urlopen', side_effect=self.provider(event, requests)):
            result = generate_video('A golden sphere')
            self.assertTrue(capabilities()['video_account_connected'])
        self.assertEqual(result['video'], video)
        self.assertTrue(result['free'])
        self.assertTrue(all(r.get_header('Authorization') == 'Bearer test-token' for r in requests))

    def test_rejects_untrusted_video_location(self):
        event = {'msg': 'process_completed', 'event_id': 'test123', 'success': True,
                 'output': {'data': [{'video': {'url': 'http://localhost/private'}}]}}
        with patch('urllib.request.urlopen', side_effect=self.provider(event, [])):
            with self.assertRaises(MediaError) as context:
                generate_video('A golden sphere')
        self.assertEqual(context.exception.code, 'video_invalid_response')


if __name__ == '__main__':
    unittest.main()
