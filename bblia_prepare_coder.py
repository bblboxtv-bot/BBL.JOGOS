import urllib.request,json,pathlib,shutil,time
root=pathlib.Path(__file__).resolve().parent
model='qwen2.5-coder:1.5b'
free=shutil.disk_usage(pathlib.Path.home()).free
if free<3*1024**3:raise RuntimeError('Espaco insuficiente para preparar modelo de codigo sem apagar arquivos.')
with urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=15) as r:tags=json.load(r)
if model in [m['name'] for m in tags.get('models',[])]:
 print('Modelo de codigo ja instalado.',flush=True)
else:
 req=urllib.request.Request('http://127.0.0.1:11434/api/pull',data=json.dumps({'model':model,'stream':True}).encode(),headers={'Content-Type':'application/json'})
 last=-1
 with urllib.request.urlopen(req,timeout=180) as response:
  for line in response:
   item=json.loads(line)
   if item.get('error'):raise RuntimeError(item['error'])
   if item.get('total'):
    pct=int(item.get('completed',0)*100/item['total'])
    if pct//10!=last:print('Modelo de codigo: '+str(pct)+'%',flush=True);last=pct//10
   elif item.get('status')=='success':print('Modelo de codigo instalado.',flush=True)
(root/'MODELO-CODIGO-PREPARADO-20261116.json').write_text(json.dumps({'model':model,'prepared':True,'free_disk_before_gb':round(free/1024**3,1),'paid_api_used':False}),encoding='utf-8')
