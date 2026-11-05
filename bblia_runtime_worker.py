"""Internal worker. Input is JSON, never Python source or command-line code."""
import json,sys
from pathlib import Path

def main():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU,(2,2))
        resource.setrlimit(resource.RLIMIT_AS,(192*1024*1024,192*1024*1024))
        resource.setrlimit(resource.RLIMIT_FSIZE,(0,0))
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    except (ImportError,ValueError):pass
    sys.path.insert(0,sys.argv[1])
    import quickjs
    if not Path(quickjs.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve()):raise RuntimeError("Ambiente dedicado não instalado")
    payload=json.loads(sys.stdin.read(2000001))
    ctx=quickjs.Context();ctx.set_memory_limit(32*1024*1024);ctx.set_max_stack_size(256*1024);ctx.set_time_limit(.7)
    # No add_callable, modules, host objects, credentials, paths or I/O exposed to JS.
    setup=r'''
    (()=>{
      const records=[],logs=[];const encode=JSON.stringify.bind(JSON);
      const safe=(v)=>{try{return String(v).slice(0,500)}catch{return '[valor]'}};
      const assert=(condition,message='Condição não satisfeita')=>{if(!condition)throw Error(safe(message))};
      assert.equal=(a,b,message)=>assert(Object.is(a,b),message||('Esperado '+safe(b)+', recebido '+safe(a)));
      assert.deepEqual=(a,b,message)=>assert(encode(a)===encode(b),message||'Valores diferentes');
      assert.throws=(fn)=>{let threw=false;try{fn()}catch{threw=true}assert(threw,'Era esperado um erro')};
      Object.freeze(assert);
      const test=(name,fn)=>{if(records.length>=100)throw Error('Máximo de 100 testes');let error='';try{const r=fn();if(r&&typeof r.then==='function')throw Error('Testes assíncronos não suportados')}catch(e){error=safe(e.message||e)}records.push({name:safe(name),ok:!error,error})};
      Object.defineProperties(globalThis,{
        assert:{value:assert},test:{value:test},
        console:{value:Object.freeze({log:(...a)=>{if(logs.length<20)logs.push(a.map(safe).join(' '))},error:(...a)=>{if(logs.length<20)logs.push(a.map(safe).join(' '))}})},
        __bbliaReport:{value:()=>encode({ok:records.length>0&&records.every(r=>r.ok),executed:true,passed:records.filter(r=>r.ok).length,failed:records.filter(r=>!r.ok).length,tests:records,logs,error:records.length?'':'Nenhum teste foi executado.'})}
      });
    })();
    '''
    report=None
    try:
        ctx.eval(setup)
        for source in payload.get('sources',[]):ctx.eval(source['code'])
        ctx.eval(payload.get('tests',''))
        report=json.loads(ctx.eval('__bbliaReport()'))
    except Exception as e:report={'ok':False,'executed':True,'error':str(e)[:1500]}
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
