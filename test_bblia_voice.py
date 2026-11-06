import io
import json
import os
import threading
import unittest
import urllib.request
from unittest.mock import patch
from bblia_app import Handler, ThreadingHTTPServer


class VoiceSessionTests(unittest.TestCase):
    def test_quiet_turn_detection_and_no_automatic_interruption(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        original=urllib.request.urlopen
        payloads=[]
        def upstream(request,*args,**kwargs):
            if request.full_url.startswith('https://api.openai.com/v1/realtime/client_secrets'):
                payloads.append(json.loads(request.data))
                return io.BytesIO(b'{"value":"test-ephemeral"}')
            return original(request,*args,**kwargs)
        try:
            with patch.dict(os.environ,{'OPENAI_API_KEY':'server-secret'}),patch('urllib.request.urlopen',side_effect=upstream):
                request=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/api/realtime-token',data=b'{"paid_authorized":true}')
                with urllib.request.urlopen(request) as response:result=json.load(response)
            self.assertEqual(result,{'token':'test-ephemeral'})
            audio=payloads[0]['session']['audio']['input']
            self.assertFalse(audio['turn_detection']['interrupt_response'])
            self.assertTrue(audio['turn_detection']['create_response'])
            self.assertGreaterEqual(audio['turn_detection']['threshold'],0.7)
            self.assertGreaterEqual(audio['turn_detection']['silence_duration_ms'],900)
            self.assertEqual(audio['noise_reduction']['type'],'near_field')
            self.assertNotIn('idle_timeout_ms',audio['turn_detection'])
        finally:
            server.shutdown();server.server_close()


if __name__=='__main__':unittest.main()
