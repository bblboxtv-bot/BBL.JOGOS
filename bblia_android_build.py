"""Build plain Android Java projects with the installed SDK. No Gradle scripts run.
Usage: python bblia_android_build.py --project DIR [--smoke] [--sdk DIR] [--jdk DIR]
Produces a debug-signed APK and JSON evidence. Does not install or modify devices.
"""
import argparse,hashlib,json,os,re,subprocess,sys,time,zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

class BuildError(Exception):pass

def discover(sdk=None,jdk=None):
    sdk_candidates=[sdk,os.getenv('ANDROID_SDK_ROOT'),os.getenv('ANDROID_HOME'),str(Path(os.getenv('LOCALAPPDATA',''))/'Android'/'Sdk'),str(Path.home()/'Android'/'Sdk')]
    sdk_path=next((Path(p) for p in sdk_candidates if p and (Path(p)/'platforms').is_dir()),None)
    jdk_candidates=[jdk,os.getenv('JAVA_HOME')]
    for folder in ('Android Studio','Android Studio1','Android Studio2'):
        jdk_candidates.append(str(Path(os.getenv('ProgramFiles',r'C:\Program Files'))/'Android'/folder/'jbr'))
    for base in (Path.home()/'Documents'/'jdk17',Path.home()/'Documents'/'jdk21'):
        if base.is_dir():jdk_candidates.extend(str(p) for p in sorted(base.glob('jdk*'),reverse=True) if p.is_dir())
    exe='.exe' if os.name=='nt' else ''
    jdk_path=next((Path(p) for p in jdk_candidates if p and (Path(p)/'bin'/('javac'+exe)).is_file()),None)
    if not sdk_path:raise BuildError('Android SDK não encontrado. Informe --sdk.')
    if not jdk_path:raise BuildError('JDK com javac não encontrado. Informe --jdk.')
    def version(p):return tuple(int(x) for x in re.findall(r'\d+',p.name))
    platforms=sorted([p for p in (sdk_path/'platforms').iterdir() if (p/'android.jar').is_file()],key=lambda p:(bool(re.fullmatch(r'android-\d+',p.name)),version(p)),reverse=True)
    builds=sorted([p for p in (sdk_path/'build-tools').iterdir() if (p/('aapt2'+exe)).is_file() and (p/'lib'/'d8.jar').is_file() and (p/'lib'/'apksigner.jar').is_file()],key=version,reverse=True)
    if not platforms or not builds:raise BuildError('Plataforma Android ou build-tools incompletos.')
    return {'sdk':sdk_path,'jdk':jdk_path,'platform':platforms[0],'tools':builds[0],'exe':exe}

def smoke(root):
    manifest=root/'AndroidManifest.xml';source=root/'src'/'com'/'bblia'/'compilacao'/'teste'/'MainActivity.java'
    if manifest.exists() or source.exists():raise BuildError('O projeto de teste já existe. Escolha uma pasta nova.')
    source.parent.mkdir(parents=True,exist_ok=True)
    manifest.write_text('''<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.bblia.compilacao.teste"><uses-sdk android:minSdkVersion="21" android:targetSdkVersion="28"/><application android:label="BBLIA Teste de Compilacao" android:theme="@android:style/Theme.Material.NoActionBar"><activity android:name=".MainActivity" android:exported="true"><intent-filter><action android:name="android.intent.action.MAIN"/><category android:name="android.intent.category.LAUNCHER"/></intent-filter></activity></application></manifest>''',encoding='utf-8')
    source.write_text('''package com.bblia.compilacao.teste;
import android.app.Activity;
import android.os.Bundle;
import android.widget.TextView;
public class MainActivity extends Activity {
 @Override public void onCreate(Bundle state) {
  super.onCreate(state);
  TextView view=new TextView(this);
  view.setText("BBLIA: compilacao Android funcionando");
  view.setTextSize(26); view.setPadding(32,48,32,32);setContentView(view);
 }
}''',encoding='utf-8')

def build(project,sdk=None,jdk=None):
    root=Path(project).resolve();env=discover(sdk,jdk);java=env['jdk']/'bin'/('java'+env['exe']);javac=env['jdk']/'bin'/('javac'+env['exe']);keytool=env['jdk']/'bin'/('keytool'+env['exe'])
    main=root/'app'/'src'/'main' if (root/'app'/'src'/'main'/'AndroidManifest.xml').is_file() else root
    manifest=main/'AndroidManifest.xml'
    if not manifest.is_file():raise BuildError('AndroidManifest.xml ausente. Suporte: projeto Java simples, sem bibliotecas externas/Kotlin.')
    package=ET.parse(manifest).getroot().attrib.get('package','')
    if not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+',package):raise BuildError('Manifesto precisa declarar package Android válido.')
    source_root=main/'java' if (main/'java').is_dir() else main/'src'
    sources=list(source_root.rglob('*.java'))
    if not sources or len(sources)>200:raise BuildError('Use de 1 a 200 arquivos Java no projeto.')
    if list(source_root.rglob('*.kt')):raise BuildError('Kotlin exige uma compilação Gradle separada.')
    output=root/'build-bblia'/('run-'+time.strftime('%Y%m%d-%H%M%S')+'-'+os.urandom(3).hex());output.mkdir(parents=True)
    classes=output/'classes';classes.mkdir();generated=output/'generated';generated.mkdir();dex=output/'dex';dex.mkdir()
    aapt=env['tools']/('aapt2'+env['exe']);android=env['platform']/'android.jar';logs=[]
    child_env=os.environ.copy();child_env['JAVA_HOME']=str(env['jdk'])
    child_env['PATH']=str(env['jdk']/'bin')+os.pathsep+child_env.get('PATH','')
    def run(label,args,timeout=120):
        result=subprocess.run([str(x) for x in args],cwd=str(root),env=child_env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
        detail=(result.stdout+'\n'+result.stderr)[-10000:];logs.append({'step':label,'exit_code':result.returncode,'output':detail})
        (output/'build-log.json').write_text(json.dumps(logs,ensure_ascii=False,indent=2),encoding='utf-8')
        if result.returncode:raise BuildError(label+' falhou: '+detail[-3000:])
        return result.stdout
    unsigned=output/'unsigned.apk';link=[aapt,'link','-o',unsigned,'--manifest',manifest,'-I',android,'--java',generated,'--auto-add-overlay']
    if (main/'res').is_dir():
        compiled=output/'resources.zip';run('compilar recursos',[aapt,'compile','--dir',main/'res','-o',compiled]);link.append(compiled)
    if (main/'assets').is_dir():link.extend(['-A',main/'assets'])
    run('empacotar manifesto e recursos',link)
    run('compilar Java',[javac,'-encoding','UTF-8','-source','8','-target','8','-proc:none','-bootclasspath',android,'-d',classes,*sources,*generated.rglob('*.java')])
    jar=output/'classes.jar'
    with zipfile.ZipFile(jar,'w',zipfile.ZIP_DEFLATED) as z:
        for f in classes.rglob('*.class'):z.write(f,f.relative_to(classes).as_posix())
    run('gerar DEX',[java,'-cp',env['tools']/'lib'/'d8.jar','com.android.tools.r8.D8','--lib',android,'--min-api','21','--output',dex,jar])
    with zipfile.ZipFile(unsigned,'a',zipfile.ZIP_DEFLATED) as z:
        for f in dex.glob('*.dex'):z.write(f,f.name)
    aligned=output/'aligned.apk';run('alinhar APK',[env['tools']/('zipalign'+env['exe']),'-f','-p','4',unsigned,aligned])
    keys=Path.home()/'.bblia-build';keys.mkdir(exist_ok=True);keystore=keys/'debug.keystore'
    if not keystore.exists():run('criar chave de teste',[keytool,'-genkeypair','-keystore',keystore,'-storetype','JKS','-storepass','android','-keypass','android','-alias','androiddebugkey','-keyalg','RSA','-keysize','2048','-validity','10000','-dname','CN=BBLIA Debug,O=BBLIA,C=BR'])
    apk=output/'BBLIA-debug.apk';signer=[java,'-jar',env['tools']/'lib'/'apksigner.jar']
    run('assinar APK de teste',signer+['sign','--ks',keystore,'--ks-key-alias','androiddebugkey','--ks-pass','pass:android','--key-pass','pass:android','--out',apk,aligned])
    run('verificar assinatura',signer+['verify','--verbose',apk]);run('verificar alinhamento',[env['tools']/('zipalign'+env['exe']),'-c','-p','4',apk])
    with zipfile.ZipFile(apk) as z:
        if z.testzip() or 'AndroidManifest.xml' not in z.namelist() or 'classes.dex' not in z.namelist():raise BuildError('APK incompleto.')
    report={'ok':True,'apk':str(apk),'bytes':apk.stat().st_size,'sha256':hashlib.sha256(apk.read_bytes()).hexdigest(),'package':package,'signature_verified':True,'alignment_verified':True,'sdk':str(env['sdk']),'jdk':str(env['jdk']),'platform':env['platform'].name,'build_tools':env['tools'].name,'installed':False,'runtime_tested':False,'log':str(output/'build-log.json')}
    (output/'build-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report

def inspect_apk(path,env):
    path=Path(path).resolve()
    if not path.is_file() or path.suffix.lower()!='.apk':raise BuildError('Arquivo APK não encontrado.')
    java=env['jdk']/'bin'/('java'+env['exe'])
    signer=env['tools']/'lib'/'apksigner.jar'
    signature=subprocess.run([str(java),'-jar',str(signer),'verify','--verbose',str(path)],capture_output=True,text=True,timeout=45,errors='replace')
    if signature.returncode:raise BuildError('A assinatura do APK não foi validada: '+signature.stderr[-1000:])
    badging=subprocess.run([str(env['tools']/('aapt'+env['exe'])),'dump','badging',str(path)],capture_output=True,text=True,timeout=45,errors='replace')
    package=re.search(r"package: name='([^']+)' versionCode='([^']+)' versionName='([^']*)'",badging.stdout)
    if badging.returncode or not package:raise BuildError('Não foi possível identificar pacote e versão do APK.')
    activity=re.search(r"launchable-activity: name='([^']+)'",badging.stdout)
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return {'apk':str(path),'bytes':path.stat().st_size,'sha256':digest.hexdigest(),
            'package':package[1],'version_code':package[2],'version_name':package[3],
            'activity':activity[1] if activity else None,'signature_verified':True}


def build_gradle(project,sdk=None,jdk=None,task='assembleDebug',gradle=None):
    root=Path(project).resolve();env=discover(sdk,jdk)
    if not any((root/name).is_file() for name in ('settings.gradle','settings.gradle.kts','build.gradle','build.gradle.kts')):
        raise BuildError('Projeto Gradle não encontrado.')
    if not re.fullmatch(r'[:A-Za-z0-9_-]{1,120}',task):raise BuildError('Tarefa Gradle inválida.')
    exe='.bat' if os.name=='nt' else ''
    wrapper=root/('gradlew'+exe)
    candidates=[Path(gradle)] if gradle else []
    candidates.extend(sorted((Path.home()/'Documents').glob('gradle-*/bin/gradle'+exe),reverse=True))
    system=__import__('shutil').which('gradle')
    if system:candidates.append(Path(system))
    command=wrapper if wrapper.is_file() else next((p for p in candidates if p.is_file()),None)
    if not command:raise BuildError('Gradle ausente. Use o wrapper do projeto ou informe --gradle.')
    output=root/'build-bblia'/('gradle-'+time.strftime('%Y%m%d-%H%M%S')+'-'+os.urandom(3).hex());output.mkdir(parents=True)
    child=os.environ.copy();child.update(JAVA_HOME=str(env['jdk']),ANDROID_HOME=str(env['sdk']),ANDROID_SDK_ROOT=str(env['sdk']))
    child['PATH']=str(env['jdk']/'bin')+os.pathsep+str(env['sdk']/'platform-tools')+os.pathsep+child.get('PATH','')
    started=time.time()
    result=subprocess.run([str(command),task,'--no-daemon','--console=plain'],cwd=root,env=child,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=1200)
    log=output/'build.log';log.write_text(result.stdout+'\n'+result.stderr,encoding='utf-8')
    if result.returncode:raise BuildError('Gradle falhou. Consulte '+str(log)+': '+(result.stdout+'\n'+result.stderr)[-2500:])
    apks=[p for p in root.glob('**/build/outputs/apk/**/*.apk') if p.is_file() and p.stat().st_mtime>=started-3]
    if not apks:raise BuildError('Gradle terminou, mas nenhum APK novo foi encontrado. Consulte '+str(log))
    reports=[inspect_apk(apk,env) for apk in apks[:30]]
    report={'ok':True,'engine':'gradle','task':task,'apks':reports,'installed':False,'runtime_tested':False,'log':str(log)}
    (output/'build-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--project',required=True);parser.add_argument('--smoke',action='store_true');parser.add_argument('--sdk');parser.add_argument('--jdk');parser.add_argument('--engine',choices=['auto','java','gradle'],default='auto');parser.add_argument('--task',default='assembleDebug');parser.add_argument('--gradle');args=parser.parse_args()
    try:
        root=Path(args.project);root.mkdir(parents=True,exist_ok=True)
        if args.smoke:smoke(root)
        use_gradle=args.engine=='gradle' or (args.engine=='auto' and any((root/name).is_file() for name in ('build.gradle','build.gradle.kts','settings.gradle','settings.gradle.kts')))
        result=build_gradle(root,args.sdk,args.jdk,args.task,args.gradle) if use_gradle else build(root,args.sdk,args.jdk)
        print(json.dumps(result,ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({'ok':False,'error':str(exc)[:4000]},ensure_ascii=False));sys.exit(1)
