"""Geracao de UI Android em estrutura Java verificada, sem dependencias externas."""
import json,pathlib,urllib.request,uuid,time,html,re,os
import bblia_android_build as builder
import bblia_apk_delivery as delivery
from bblia_android_compat import adapt_java
ROOT=pathlib.Path(__file__).resolve().parent.parent/'APKs-criados'
SCHEMA={'type':'object','properties':{'title':{'type':'string'},'java':{'type':'string'},'limitations':{'type':'array','items':{'type':'string'}}},'required':['title','java','limitations'],'additionalProperties':False}
def wrap_java(body,package):
    if not isinstance(body,str) or not body.strip() or len(body)>100000:raise ValueError('Corpo Java vazio ou grande demais.')
    if re.search(r'androidx|AppCompatActivity|\bR\s*\.',body):raise ValueError('Nao use AndroidX nem R: crie todas as views em Java com LinearLayout, TextView e Button.')
    if re.search(r'\b(package|import)\s|class\s+MainActivity|void\s+onCreate',body):raise ValueError('Retorne apenas as instrucoes DENTRO de onCreate, sem package, import, classe ou definicao de metodo.')
    if 'super.onCreate' in body:raise ValueError('O esqueleto ja chama super.onCreate; retorne somente o corpo da interface.')
    return ('package '+package+';\nimport android.app.Activity;import android.os.Bundle;import android.view.*;import android.widget.*;import android.content.*;import android.graphics.Color;import java.util.*;\n'
            'public class MainActivity extends Activity { @Override public void onCreate(Bundle savedInstanceState) {super.onCreate(savedInstanceState);\n'+body+'\n}}')

def generate_stream(body,job,agent,timeout=600):
    body=dict(body);body['stream']=True
    request=urllib.request.Request('http://127.0.0.1:11434/api/chat',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    parts=[];size=0;last=0;started=time.monotonic();final=None
    with urllib.request.urlopen(request,timeout=timeout) as response:
        for line in response:
            if job['cancelled']:raise InterruptedError('Geracao interrompida pelo usuario.')
            if time.monotonic()-started>timeout:raise TimeoutError('A geracao excedeu o tempo desta etapa; arquivos parciais preservados.')
            chunk=json.loads(line)
            if chunk.get('error'):raise ValueError(str(chunk['error'])[:1000])
            text=chunk.get('message',{}).get('content','')
            if text:
                parts.append(text);size+=len(text)
                if size>150000:raise ValueError('Codigo gerado excede o limite desta etapa.')
                if size-last>=200:
                    agent.progress(job,'Ollama escrevendo o aplicativo: '+str(size)+' caracteres')
                    last=size
            if chunk.get('done'):final=chunk;break
    if final is None:raise ValueError('A resposta do modelo foi interrompida antes de terminar.')
    final['message']={'role':'assistant','content':''.join(parts)}
    return final

def run(job,messages,data,files,agent):
    folder=ROOT/('gerado-'+uuid.uuid4().hex[:12]);folder.mkdir(parents=True)
    package='com.bblia.gerado.p'+uuid.uuid4().hex[:8]
    instruction=('You are an Android Java programmer. Return JSON with title, java, limitations. '
      'java contains complete working source for MainActivity extending android.app.Activity, or the complete statements inside an existing onCreate method. '
      'Build the interface programmatically using android.widget.LinearLayout, TextView, Button and other standard SDK widgets. '
      'Use setContentView(layout), addView and View.OnClickListener. Mutable values captured by listeners use final arrays or instance fields. '
      'Implement the exact requested functionality, including initial values. Keep the application concise and finish every method and listener. '
      'The installed compiler provides the Android SDK and Java 8. Record unavailable external services in limitations.')
    original=messages[-1].get('content','') if messages else ''
    history=[{'role':'system','content':instruction},{'role':'user','content':original}]
    started=time.monotonic()
    try:
        if files:raise ValueError('Esta rota cria novos projetos Java. Atualizacao de projetos anexados ainda nao validada.')
        if not isinstance(original,str):raise ValueError('Use um pedido de aplicativo em texto nesta rota local.')
        builder.discover()
        for attempt in range(2):
            if job['cancelled']:break
            agent.progress(job,'Ollama criando a funcionalidade Android' if attempt==0 else 'Corrigindo o codigo com base no erro verificado')
            body={'model':os.getenv('BBLIA_ANDROID_MODEL','qwen2.5-coder:1.5b'),'messages':history,'stream':False,'format':SCHEMA,'keep_alive':'30m','options':{'temperature':0,'num_ctx':3072,'num_predict':1800,'num_thread':1}}
            raw=generate_stream(body,job,agent)
            (folder/('geracao-'+str(attempt+1)+'-metadata.json')).write_text(json.dumps({k:raw.get(k) for k in ('model','done_reason','eval_count','prompt_eval_count','total_duration','eval_duration')}),encoding='utf-8')
            text=raw.get('message',{}).get('content','')
            (folder/('geracao-'+str(attempt+1)+'.json')).write_text(text,encoding='utf-8')
            try:
                generated=json.loads(text);java,compat_changes=adapt_java(generated['java'],package,original);title=str(generated['title'])[:60]
                src=folder/'src'/pathlib.Path(*package.split('.'));src.mkdir(parents=True,exist_ok=True)
                (src/'MainActivity.java').write_text(java,encoding='utf-8')
                manifest=('<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="'+package+'" android:versionCode="1" android:versionName="1.0"><uses-sdk android:minSdkVersion="21" android:targetSdkVersion="28"/><application android:label="'+html.escape(title,quote=True)+'" android:theme="@android:style/Theme.Material.NoActionBar"><activity android:name=".MainActivity" android:exported="true"><intent-filter><action android:name="android.intent.action.MAIN"/><category android:name="android.intent.category.LAUNCHER"/></intent-filter></activity></application></manifest>')
                (folder/'AndroidManifest.xml').write_text(manifest,encoding='utf-8')
                with agent.LOCK:
                    job['artifacts']=[{'name':'AndroidManifest.xml','content':manifest},{'name':'src/'+package.replace('.','/')+'/MainActivity.java','content':java}]
                    job['steps']=attempt+1;job['revision']+=1
                if job['cancelled']:break
                agent.progress(job,'Compilando e verificando assinatura do APK local')
                report=builder.build(folder)
                if not report.get('signature_verified'):raise ValueError('Assinatura nao confirmada.')
                apk=pathlib.Path(report['apk']);ticket=delivery.prepare(job['id'],'BBLIA-aplicativo-debug.apk',report['sha256'])
                with apk.open('rb') as stream:delivery.receive(ticket,stream,apk.stat().st_size)
                with agent.LOCK:
                    job.pop('error',None)
                    job.update(status='completed',progress='APK compilado e pronto para baixar',answer='APK criado pelo Ollama e compilado localmente. Assinatura e integridade verificadas. Instalacao e teste no Android ainda pendentes.',kind='codigo',limitations=list(generated.get('limitations',[]))+['Android Java sem bibliotecas externas nesta rota.','Instalacao e funcionamento no aparelho ainda nao testados.'],validation={'ok':True,'signature_verified':True,'sha256':report['sha256'],'runtime_tested':False,'adaptations':compat_changes},computer_actions=[{'tool':'local_android_build','confirmed':True}],seconds=round(time.monotonic()-started,2));job['revision']+=1
                return
            except (ValueError,KeyError,builder.BuildError) as exc:
                # Keep the system contract and original request on EVERY repair.
                history=[{'role':'system','content':instruction},{'role':'user','content':original+'\nCorrija este corpo Java: '+str(generated.get('java','') if 'generated' in locals() else text)[:4000]+'\nErro verificado: '+str(exc)[-1400:]}]
                with agent.LOCK:job['error']=str(exc)[:2000]
        with agent.LOCK:job.update(status='cancelled' if job['cancelled'] else 'partial',progress='Arquivos preservados; APK ainda nao concluido')
    except InterruptedError as exc:
        with agent.LOCK:job.update(status='cancelled',progress='Geracao interrompida',error=str(exc))
    except Exception as exc:
        with agent.LOCK:job.update(status='partial' if job['artifacts'] else 'failed',progress='Geracao local nao concluida',error=str(exc)[:2000])
    finally:agent.SLOTS.release()
