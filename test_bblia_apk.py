import io
import json
import struct
import unittest
import zipfile
from bblia_apk import inspect_apk, xml_nodes
from bblia_work import prepare_messages


def pool(strings, utf8=True):
    data = bytearray(); offsets = []
    for text in strings:
        offsets.append(len(data))
        raw = text.encode('utf-8' if utf8 else 'utf-16le')
        data.extend((bytes([len(text),len(raw)])+raw+b'\0') if utf8 else struct.pack('<H',len(text))+raw+b'\0\0')
    start = 28+len(strings)*4
    data.extend(b'\0'*((-(start+len(data)))%4))
    return struct.pack('<HHIIIIII',1,28,start+len(data),len(strings),0,0x100 if utf8 else 0,start,0)+b''.join(struct.pack('<I',o) for o in offsets)+data


def manifest(utf8=True):
    strings = ['manifest','package','br.bbl.demo','versionCode','versionName','2.0','uses-permission','name','android.permission.INTERNET','application','label','Meu aplicativo','activity','.MainActivity']
    def node(tag,attrs):
        entries=b''
        for key,val in attrs.items():
            kind,number=(0x10,val) if isinstance(val,int) else (3,strings.index(val))
            entries+=struct.pack('<IIIHBBI',0xffffffff,strings.index(key),0xffffffff,8,0,kind,number)
        ext=struct.pack('<IIHHHHHH',0xffffffff,strings.index(tag),20,20,len(attrs),0,0,0)
        return struct.pack('<HHIII',0x102,16,16+len(ext)+len(entries),1,0xffffffff)+ext+entries
    chunks=pool(strings,utf8)+node('manifest',{'package':'br.bbl.demo','versionCode':2,'versionName':'2.0'})+node('uses-permission',{'name':'android.permission.INTERNET'})+node('application',{'label':'Meu aplicativo'})+node('activity',{'name':'.MainActivity'})
    return struct.pack('<HHI',3,8,8+len(chunks))+chunks


def apk_bytes(binary=True,utf8=True):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('AndroidManifest.xml',manifest(utf8) if binary else '<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="br.bbl.demo"><application android:label="Demo"/></manifest>')
        z.writestr('res/layout/main.xml','<LinearLayout><TextView text="Seja bem-vindo"/></LinearLayout>')
        z.writestr('assets/readme.txt','example')
        z.writestr('lib/arm64-v8a/libdemo.so',b'not executed')
    return out.getvalue()


class APKTests(unittest.TestCase):
    def test_real_binary_formats(self):
        for utf8 in (True,False):
            a=inspect_apk(io.BytesIO(apk_bytes(utf8=utf8)),'demo.apk')
            report=json.loads(a['data'].split('\n',1)[1])
            self.assertEqual(report['package'],'br.bbl.demo')
            self.assertEqual(report['version_code'],2)
            self.assertEqual(report['application']['label'],'Meu aplicativo')
            self.assertIn('android.permission.INTERNET',report['permissions'])
            self.assertEqual(report['components'][0]['name'],'.MainActivity')
            self.assertEqual(report['layouts'][0]['views'][1]['text'],'Seja bem-vindo')
            self.assertEqual(a['type'],'text')
            safe=prepare_messages({'messages':[{'role':'user','content':'Crie um parecido'}],'attachments':[a]})
            self.assertIn('br.bbl.demo',safe[-1]['content'][1]['text'])
    def test_plain_manifest(self):
        self.assertEqual(inspect_apk(io.BytesIO(apk_bytes(binary=False)))['apk']['package'],'br.bbl.demo')
    def test_bad_zip(self):
        for raw in (b'not a zip',apk_bytes()[:40]):
            with self.assertRaises(ValueError):inspect_apk(io.BytesIO(raw))
    def test_missing_manifest(self):
        raw=io.BytesIO()
        with zipfile.ZipFile(raw,'w') as z:z.writestr('hello.txt','hello')
        with self.assertRaisesRegex(ValueError,'Manifest'):inspect_apk(raw)
    def test_compression_bomb(self):
        raw=io.BytesIO()
        with zipfile.ZipFile(raw,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('AndroidManifest.xml',b'x'*1000000)
        with self.assertRaisesRegex(ValueError,'compressão'):inspect_apk(raw)
    def test_bad_binary(self):
        raw=io.BytesIO()
        with zipfile.ZipFile(raw,'w') as z:z.writestr('AndroidManifest.xml',manifest()[:-10])
        with self.assertRaises(ValueError):inspect_apk(raw)
    def test_no_extraction(self):
        raw=io.BytesIO()
        with zipfile.ZipFile(raw,'w') as z:
            z.writestr('AndroidManifest.xml',manifest())
            z.writestr('../../never-write.txt','do not extract')
        self.assertEqual(inspect_apk(raw)['apk']['package'],'br.bbl.demo')

class APKHTTPTests(unittest.TestCase):
    def test_upload_then_chat_context_and_invalid_file(self):
        import threading
        import urllib.request
        import urllib.error
        from bblia_app import Handler, ThreadingHTTPServer
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        try:
            request=urllib.request.Request(base+'/api/apk/analyze',data=apk_bytes(),headers={'X-Filename':'Meu%20app.apk','Content-Type':'application/vnd.android.package-archive'})
            with urllib.request.urlopen(request) as response:
                self.assertEqual(response.status,200)
                attachment=json.load(response)['attachment']
            self.assertEqual(attachment['apk']['name'],'Meu app.apk')
            self.assertIn('br.bbl.demo',attachment['data'])
            request=urllib.request.Request(base+'/api/apk/analyze',data=b'not an apk')
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
            self.assertEqual(error.exception.code,400)
            self.assertIn('error',json.load(error.exception))
        finally:server.shutdown();server.server_close()


if __name__=='__main__':unittest.main()
