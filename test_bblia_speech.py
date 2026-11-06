import base64
import io
import json
import os
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from bblia_app import Handler, ThreadingHTTPServer
import bblia_speech as speech

class Audio(io.BytesIO):
    headers={'Content-Type':'audio/mpeg'}

class SpeechTests(unittest.TestCase):
    def test_long_reply_keeps_all_words_without_paid_requests(self):
        calls=[]
        def upstream(req, **kw):
            self.assertTrue(req.full_url.startswith('https://translate.google.com/translate_tts?'))
            text=parse_qs(urlsplit(req.full_url).query)['q'][0]
            self.assertLessEqual(len(text),170)
            calls.append(text)
            return Audio(b'ID3test-audio')
        text=' '.join('palavra'+str(i) for i in range(90))
        with patch.object(speech.urllib.request,'urlopen',side_effect=upstream):
            result=speech.synthesize(text)
        self.assertEqual(' '.join(calls),text)
        self.assertTrue(result.startswith(b'ID3'))
        self.assertGreater(len(calls),1)

    def test_segment_mode_preserves_order_and_legacy_mp3(self):
        def upstream(req, **kw):
            text=parse_qs(urlsplit(req.full_url).query)['q'][0]
            return Audio(('ID3:'+text).encode())
        text=' '.join('palavra'+str(i) for i in range(70))
        with patch.object(speech.urllib.request,'urlopen',side_effect=upstream):
            parts=speech.synthesize(text,segments=True)
            combined=speech.synthesize(text)
        self.assertGreater(len(parts),1)
        self.assertEqual(b''.join(parts),combined)
        self.assertEqual(' '.join(p.decode()[4:] for p in parts),text)

    def test_invalid_upstream_audio_is_not_reported_as_success(self):
        response=Audio(b'<html>blocked</html>');response.headers={'Content-Type':'text/html'}
        with patch.object(speech.urllib.request,'urlopen',return_value=response):
            with self.assertRaises(speech.SpeechError):speech.synthesize('Olá')

    def test_transcription_uses_audio_and_returns_only_text(self):
        seen=[]
        def upstream(req,**kw):
            self.assertIn('generativelanguage.googleapis.com',req.full_url)
            payload=json.loads(req.data);seen.append(payload)
            content=json.dumps({'text':'Bom dia, BBLIA.'})
            return io.BytesIO(json.dumps({'candidates':[{'content':{'parts':[{'text':content}]}}]}).encode())
        encoded=base64.b64encode(b'test-audio-data').decode()
        with patch.dict(os.environ,{'GEMINI_API_KEY':'fake'}),patch.object(speech.urllib.request,'urlopen',side_effect=upstream):
            self.assertEqual(speech.transcribe(encoded,'audio/webm;codecs=opus'),'Bom dia, BBLIA.')
        self.assertEqual(seen[0]['contents'][0]['parts'][1]['inlineData']['data'],encoded)

    def test_transient_transcription_failure_retries_once(self):
        content=json.dumps({'text':'Olá'})
        response=io.BytesIO(json.dumps({'candidates':[{'content':{'parts':[{'text':content}]}}]}).encode())
        temporary=urllib.error.HTTPError('https://provider',503,'busy',{},None)
        with patch.dict(os.environ,{'GEMINI_API_KEY':'fake'}),patch.object(speech.urllib.request,'urlopen',side_effect=[temporary,response]) as request,patch.object(speech.time,'sleep'):
            self.assertEqual(speech.transcribe(base64.b64encode(b'test-audio-data').decode(),'audio/webm'),'Olá')
            self.assertEqual(request.call_count,2)

    def test_quota_error_does_not_retry_or_use_paid_provider(self):
        limited=urllib.error.HTTPError('https://provider',429,'quota',{},None)
        with patch.dict(os.environ,{'GEMINI_API_KEY':'fake'}),patch.object(speech.urllib.request,'urlopen',side_effect=limited) as request:
            with self.assertRaisesRegex(speech.SpeechError,'Limite gratuito'):
                speech.transcribe(base64.b64encode(b'test-audio-data').decode(),'audio/webm')
            self.assertEqual(request.call_count,1)

    def test_bad_audio_never_reaches_provider(self):
        with patch.object(speech.urllib.request,'urlopen') as request:
            for data,mime in [('bad','audio/webm'),('x'*20,'text/plain'),('!'*20,'audio/webm')]:
                with self.assertRaises(ValueError):speech.transcribe(data,mime)
            request.assert_not_called()

    def test_http_voice_works_without_openai_key_and_handles_errors(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            url='http://127.0.0.1:'+str(server.server_port)
            with patch.dict(os.environ,{'OPENAI_API_KEY':''}),patch('bblia_app.synthesize',return_value=b'ID3audio'):
                req=urllib.request.Request(url+'/api/voice',data=json.dumps({'text':'Olá'}).encode())
                with urllib.request.urlopen(req) as response:
                    self.assertEqual(response.status,200);self.assertEqual(response.headers['Content-Type'],'audio/mpeg');self.assertEqual(response.read(),b'ID3audio')
            with patch('bblia_app.synthesize',return_value=[b'ID3first',b'ID3next']):
                req=urllib.request.Request(url+'/api/voice',data=json.dumps({'text':'Primeira frase. Segunda frase.','segments':True}).encode())
                with urllib.request.urlopen(req) as response:
                    self.assertTrue(response.headers['Content-Type'].startswith('application/json'))
                    payload=json.load(response)
                    self.assertEqual([base64.b64decode(p) for p in payload['segments']],[b'ID3first',b'ID3next'])
            with patch('bblia_app.transcribe',return_value='Teste de microfone'):
                req=urllib.request.Request(url+'/api/transcribe',data=json.dumps({'audio':'encoded','mime':'audio/webm'}).encode())
                with urllib.request.urlopen(req) as response:self.assertEqual(json.load(response)['text'],'Teste de microfone')
            for path in ('voice','transcribe'):
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(urllib.request.Request(url+'/api/'+path,data=b'[]'))
                self.assertEqual(error.exception.code,400 if path=='voice' else 413)
        finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
