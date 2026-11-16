import io
import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from bblia_android_local_job import generate_stream


class StreamTests(unittest.TestCase):
    def response(self, chunks):
        return io.BytesIO(b''.join(json.dumps(c).encode() + b'\n' for c in chunks))

    def test_complete_response_preserves_text_and_metrics(self):
        events = []
        job = {'cancelled': False}
        agent = SimpleNamespace(progress=lambda job, message: events.append(message))
        chunks = [{'message': {'content': 'x' * 210}}, {'message': {'content': ' end'}, 'done': True, 'eval_count': 8}]
        with patch('urllib.request.urlopen', return_value=self.response(chunks)) as network:
            result = generate_stream({'model': 'local-only'}, job, agent)
            sent = json.loads(network.call_args.args[0].data)
        self.assertIs(sent['stream'], True)
        self.assertEqual(result['message']['content'], 'x' * 210 + ' end')
        self.assertEqual(result['eval_count'], 8)
        self.assertTrue(events)

    def test_cancel_and_incomplete_stream_do_not_report_success(self):
        agent = SimpleNamespace(progress=lambda *args: None)
        with patch('urllib.request.urlopen', return_value=self.response([{'message': {'content': 'partial'}}])):
            with self.assertRaises(InterruptedError):
                generate_stream({}, {'cancelled': True}, agent)
        with patch('urllib.request.urlopen', return_value=self.response([{'message': {'content': 'partial'}}])):
            with self.assertRaises(ValueError):
                generate_stream({}, {'cancelled': False}, agent)

    def test_backend_error_does_not_become_an_application(self):
        with patch('urllib.request.urlopen', return_value=self.response([{'error': 'model unavailable'}])):
            with self.assertRaises(ValueError):
                generate_stream({}, {'cancelled': False}, SimpleNamespace(progress=lambda *args: None))


if __name__ == '__main__':
    unittest.main()
