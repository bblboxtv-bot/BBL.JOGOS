"""Bounded JavaScript-only execution, without host bindings, in a separate process."""
import hashlib,json,os,pathlib,subprocess,sys,tempfile,threading,time
BASE=pathlib.Path(__file__).resolve().parent
ENGINE=pathlib.Path(tempfile.gettempdir())/'bblia-quickjs-ng-0.18.0.1'
INSTALL_LOCK=threading.Lock()
SLOT=threading.BoundedSemaphore(1)
STATE={'state':'not_ready','detail':'Preparando o ambiente de testes JavaScript.'}


def safe_env():
    return {'PATH':os.defpath,'LANG':'C.UTF-8','PYTHONIOENCODING':'utf-8','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}


def worker(payload,timeout=4):
    return subprocess.run([sys.executable,'-I',str(BASE/'bblia_runtime_worker.py'),str(ENGINE)],input=json.dumps(payload),text=True,capture_output=True,timeout=timeout,env=safe_env(),cwd=tempfile.gettempdir())


def prepare():
    with INSTALL_LOCK:
        try:
            check=worker({'sources':[],'tests':"test('ambiente',()=>assert(2+2===4));"})
            if check.returncode==0 and json.loads(check.stdout).get('ok'):
                STATE.update(state='ready',detail='Testes de lógica JavaScript disponíveis.');return
        except Exception:pass
        STATE.update(state='installing',detail='Instalando o ambiente de testes JavaScript.')
        try:
            ENGINE.mkdir(parents=True,exist_ok=True)
            install=subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check','--no-input','--no-deps','--only-binary=:all:','--require-hashes','--target',str(ENGINE),'-r',str(BASE/'bblia_runtime_requirements.txt')],capture_output=True,text=True,timeout=100,env=safe_env())
            if install.returncode:raise RuntimeError()
            check=worker({'sources':[],'tests':"test('ambiente',()=>assert(2+2===4));"})
            if check.returncode or not json.loads(check.stdout).get('ok'):raise RuntimeError()
            STATE.update(state='ready',detail='Testes de lógica JavaScript disponíveis.')
        except Exception:STATE.update(state='unavailable',detail='O ambiente de testes não pôde iniciar. As funções de conversa continuam disponíveis.')


def start_prepare():
    threading.Thread(target=prepare,daemon=True).start()


def status():return dict(STATE)


def fingerprint(files):
    return hashlib.sha256(json.dumps(files,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def execute(files,args):
    digest=fingerprint(files)
    if STATE['state']!='ready':return {'ok':False,'executed':False,'project_hash':digest,'error':STATE['detail']}
    names=args.get('arquivos');test_name=args.get('teste')
    if not isinstance(names,list) or not 1<=len(names)<=8 or any(not isinstance(n,str) for n in names) or len(set(names))!=len(names) or not isinstance(test_name,str) or test_name in names:
        return {'ok':False,'executed':False,'error':'Informe arquivos de lógica e um arquivo separado de testes.'}
    if any(not isinstance(n,str) or not n.endswith('.js') or n not in files for n in names+[test_name]):
        return {'ok':False,'executed':False,'error':'Os arquivos JavaScript e o teste devem existir no projeto.'}
    if sum(len(files[n]) for n in names+[test_name])>250000:return {'ok':False,'executed':False,'error':'Máximo de 250 mil caracteres por execução.'}
    if not SLOT.acquire(blocking=False):return {'ok':False,'executed':False,'error':'Outro teste está em andamento. Tente novamente.'}
    began=time.monotonic()
    try:
        result=worker({'sources':[{'name':n,'code':files[n]} for n in names],'tests':files[test_name]})
        if result.returncode:report={'ok':False,'executed':True,'error':'O processo de testes foi encerrado. Verifique memória, recursão e código.'}
        else:
            report=json.loads(result.stdout)
            if not isinstance(report,dict):raise ValueError()
        report.update(project_hash=digest,source_files=names,test_file=test_name,elapsed_ms=round((time.monotonic()-began)*1000),scope='lógica JavaScript; sem DOM, rede, Node, arquivos ou testes visuais')
        return report
    except subprocess.TimeoutExpired:return {'ok':False,'executed':True,'project_hash':digest,'error':'Tempo limite de execução excedido.'}
    except Exception:return {'ok':False,'executed':False,'project_hash':digest,'error':'Não foi possível confirmar o resultado dos testes.'}
    finally:SLOT.release()
