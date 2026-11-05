"""Structured document export. Accepts data, never executable Python or templates."""
import base64,json,pathlib,re,subprocess,sys,threading,time
import bblia_runtime as runtime
BASE=pathlib.Path(__file__).resolve().parent
STATE={'state':'not_ready','detail':'Preparando exportação de documentos.'}
SLOT=threading.BoundedSemaphore(1)
MIMES={'docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document','xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','pptx':'application/vnd.openxmlformats-officedocument.presentationml.presentation','pdf':'application/pdf'}

def worker(payload):
 return subprocess.run([sys.executable,'-I',str(BASE/'bblia_document_worker.py'),str(runtime.ENGINE)],input=json.dumps(payload,ensure_ascii=False),text=True,capture_output=True,timeout=20,env=runtime.safe_env(),cwd=str(runtime.ENGINE))

def prepare():
 try:
  probe=worker({'probe':True})
  if probe.returncode==0 and json.loads(probe.stdout).get('ready'):STATE.update(state='ready',detail='Word, PDF, Excel e PowerPoint disponíveis.');return
 except Exception:pass
 STATE.update(state='installing',detail='Preparando bibliotecas para documentos.')
 try:
  runtime.ENGINE.mkdir(parents=True,exist_ok=True)
  result=subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check','--no-input','--no-deps','--only-binary=:all:','--require-hashes','--upgrade','--target',str(runtime.ENGINE),'-r',str(BASE/'bblia_document_requirements.txt')],capture_output=True,text=True,timeout=120,env=runtime.safe_env())
  if result.returncode:raise RuntimeError()
  probe=worker({'probe':True})
  if probe.returncode or not json.loads(probe.stdout).get('ready'):raise RuntimeError()
  STATE.update(state='ready',detail='Word, PDF, Excel e PowerPoint disponíveis.')
 except Exception:STATE.update(state='unavailable',detail='Exportação de documentos indisponível neste momento.')

def status():return dict(STATE)

def create(args):
 if STATE['state']!='ready':raise ValueError(STATE['detail'])
 kind=args.get('formato');name=args.get('nome','')
 if kind not in MIMES or not isinstance(name,str) or not re.fullmatch(r'[\w .-]{1,100}',name) or name.startswith('.') or '/' in name or '\\' in name:raise ValueError('Nome ou formato do documento inválido.')
 if not name.lower().endswith('.'+kind):name+='.'+kind
 raw=args.get('dados')
 if not isinstance(raw,str) or len(raw)>120000:raise ValueError('Informe os dados do documento em JSON, até 120 mil caracteres.')
 data=json.loads(raw)
 if not isinstance(data,dict):raise ValueError('Os dados do documento devem ser um objeto JSON.')
 if not SLOT.acquire(blocking=False):raise ValueError('Outro documento está sendo gerado. Tente novamente.')
 try:
  result=worker({'kind':kind,'data':data})
  if result.returncode:raise ValueError('Não foi possível gerar o documento. Confira tamanho e estrutura dos dados.')
  value=json.loads(result.stdout)
  if not value.get('ok'):raise ValueError(value.get('error','Documento não confirmado.'))
  binary=base64.b64decode(value['base64'],validate=True)
  if len(binary)>4*1024*1024:raise ValueError('Documento excede 4 MB.')
  return {'name':name,'content':'Documento '+kind+' gerado com dados estruturados:\n'+raw,'data_base64':value['base64'],'mime':MIMES[kind],'validation':value['validation']}
 except subprocess.TimeoutExpired:raise ValueError('Tempo limite de geração atingido. Reduza o documento.')
 finally:SLOT.release()
