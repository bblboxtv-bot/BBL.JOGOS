import base64
import io
import json
import os
import unittest
from unittest.mock import patch
import bblia_speech as speech


class PaidVoiceTests(unittest.TestCase):
    def setUp(self):
        speech._AUDIO_CACHE.clear()

    def test_requires_authorization_before_network_even_when_cached(self):
        raw = base64.b64encode(b'audio-bytes-for-test').decode()
        with patch.dict(os.environ, {'OPENAI_API_KEY':'test'}), patch.object(speech.urllib.request,'urlopen') as request:
            with self.assertRaises(ValueError): speech.synthesize('Oi',provider='openai')
            with self.assertRaises(ValueError): speech.transcribe(raw,'audio/webm',provider='openai')
            request.assert_not_called()

    def test_selected_voice_and_cache_are_provider_specific(self):
        calls=[]
        def upstream(req, **kwargs):
            calls.append(req)
            return io.BytesIO(b'ID3audio')
        with patch.dict(os.environ, {'OPENAI_API_KEY':'test'}), patch.object(speech.urllib.request,'urlopen',side_effect=upstream):
            self.assertEqual(speech.synthesize('Oi','nova',True,'openai',True),[b'ID3audio'])
            speech.synthesize('Oi','nova',False,'openai',True)
            speech.synthesize('Oi','shimmer',False,'openai',True)
            with self.assertRaises(ValueError):speech.synthesize('Oi','nova',False,'openai',False)
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0].full_url,'https://api.openai.com/v1/audio/speech')
        self.assertEqual(json.loads(calls[1].data)['voice'],'shimmer')

    def test_transcription_upload_preserves_audio_and_format(self):
        raw=b'RIFF-test-audio-data'
        captured=[]
        def upstream(req, **kwargs):
            captured.append(req)
            return io.BytesIO(json.dumps({'text':'Teste de conversa'}).encode())
        with patch.dict(os.environ, {'OPENAI_API_KEY':'test'}), patch.object(speech.urllib.request,'urlopen',side_effect=upstream):
            result=speech.transcribe(base64.b64encode(raw).decode(),'audio/webm;codecs=opus','openai',True)
        self.assertEqual(result,'Teste de conversa')
        self.assertIn(raw,captured[0].data)
        self.assertIn(b'filename="fala.webm"',captured[0].data)
        self.assertEqual(captured[0].full_url,'https://api.openai.com/v1/audio/transcriptions')

    def test_failure_never_silently_uses_another_provider(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY':'test'}), patch.object(speech.urllib.request,'urlopen',side_effect=TimeoutError) as request:
            with self.assertRaises(speech.SpeechError):speech.synthesize('Oi',provider='openai',paid_authorized=True)
            self.assertEqual(request.call_count,1)

if __name__=='__main__':unittest.main()
