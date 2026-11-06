import io,json,os,unittest,base64
from unittest.mock import patch
import bblia_free_image as image
from bblia_media import MediaError,capabilities

class FreeImageTests(unittest.TestCase):
    def provider(self,success=True,reference=False):
        seen=[]
        def open_request(req,**kw):
            seen.append(req)
            if req.full_url.endswith('/config'):
                return io.BytesIO(json.dumps({'dependencies':[{'id':2,'api_name':'infer','inputs':list(range(7))}]}).encode())
            if req.full_url.endswith('/upload'):
                self.assertIn(b'png-fixture',req.data)
                return io.BytesIO(b'["/tmp/reference.png"]')
            if req.full_url.endswith('/queue/join'):
                data=json.loads(req.data)
                self.assertEqual(len(data['data']),7)
                if reference:self.assertEqual(data['data'][0]['meta']['_type'],'gradio.FileData')
                return io.BytesIO(b'{"event_id":"image-test"}')
            if '/queue/data?' in req.full_url:
                event={'msg':'process_completed','event_id':'image-test','success':success,
                       'output':{'data':[{'url':image.CREATE_HOST+'/gradio_api/file=/tmp/result.png'}]} if success else {'error':'ZeroGPU quota exceeded'}}
                return io.BytesIO(('data: '+json.dumps(event)+'\n\n').encode())
            self.assertTrue(req.full_url.startswith(image.CREATE_HOST+'/gradio_api/file='))
            self.assertIsNone(req.get_header('Authorization'))
            return io.BytesIO(b'\x89PNG\r\n\x1a\nimage-fixture')
        return seen,open_request

    def test_real_image_bytes_and_no_paid_endpoint(self):
        seen,provider=self.provider()
        with patch.dict(os.environ,{'HF_TOKEN':'test-owner-token'}),patch('urllib.request.urlopen',side_effect=provider):
            result=image.generate('Golden BBL logo')
        self.assertTrue(result['image'].startswith('data:image/png;base64,'))
        self.assertTrue(result['free']);self.assertFalse(capabilities()['image_paid_fallback'])
        self.assertTrue(all('openai.com' not in r.full_url for r in seen))

    def test_quota_error_is_reported_once_without_paid_fallback(self):
        seen,provider=self.provider(False)
        with patch('urllib.request.urlopen',side_effect=provider):
            with self.assertRaises(MediaError) as error:image.generate('Golden BBL logo')
        self.assertEqual(error.exception.code,'image_quota_exceeded')
        self.assertEqual(len(seen),3)
        self.assertIn('Nenhum serviço pago',str(error.exception))

    def test_reference_is_uploaded_and_no_success_invented_on_quota(self):
        seen,provider=self.provider(False,True)
        reference={'type':'image','name':'reference.png','data':'data:image/png;base64,'+base64.b64encode(b'png-fixture').decode()}
        with patch('urllib.request.urlopen',side_effect=provider):
            with self.assertRaises(MediaError):image.generate('Make this golden',reference)
        self.assertTrue(all(r.full_url.startswith(image.EDIT_HOST) for r in seen))

if __name__=='__main__':unittest.main()
