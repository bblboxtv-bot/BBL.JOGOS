"""BBLIA Android workstation: evidence-based diagnostics, APK backup and install.
Firmware preparation is read-only; this module never flashes firmware.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import bblia_android_build as build

class WorkstationError(Exception):pass


def adb_path(sdk=None):
    exe='adb.exe' if os.name=='nt' else 'adb'
    bases=[sdk,os.getenv('ANDROID_HOME'),os.getenv('ANDROID_SDK_ROOT'),str(Path(os.getenv('LOCALAPPDATA',''))/'Android'/'Sdk'),str(Path.home()/'Android'/'Sdk')]
    for base in bases:
        if base and (Path(base)/'platform-tools'/exe).is_file():return str(Path(base)/'platform-tools'/exe)
    candidate=shutil.which('adb')
    if candidate:return candidate
    raise WorkstationError('ADB não encontrado no Android SDK.')


def command(args,timeout=45):
    result=subprocess.run([str(x) for x in args],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
    if result.returncode:raise WorkstationError((result.stdout+'\n'+result.stderr)[-4000:])
    return result.stdout.strip()


def devices(adb):
    result=[]
    for line in command([adb,'devices','-l']).splitlines():
        match=re.match(r'^(\S+)\s+(device|offline|unauthorized)\b(.*)',line)
        if match:result.append({'serial':match[1],'state':match[2],'details':match[3].strip()})
    return result


def select(adb,serial=None):
    listing=devices(adb);online=[d for d in listing if d['state']=='device']
    if serial:
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}',serial):raise WorkstationError('Identificador ADB inválido.')
        if not any(d['serial']==serial for d in online):raise WorkstationError('O aparelho selecionado não está online e autorizado: '+serial)
        return serial
    if len(online)!=1:raise WorkstationError('Selecione exatamente um aparelho autorizado; encontrados '+str(len(online))+'.')
    return online[0]['serial']


def inventory(sdk=None,serial=None):
    adb=adb_path(sdk);listing=devices(adb)
    result={'adb':adb,'devices':listing,'device':None,'read_only':True}
    if not serial and len([d for d in listing if d['state']=='device'])!=1:return result
    serial=select(adb,serial)
    props=command([adb,'-s',serial,'shell','getprop'])
    values=dict(re.findall(r'^\[([^]]+)\]: \[([^]]*)\]',props,re.M))
    result['device']={'serial':serial,**{key:values.get(key,'') for key in ('ro.product.manufacturer','ro.product.model','ro.product.board','ro.hardware','ro.board.platform','ro.build.version.release','ro.build.version.sdk','ro.product.cpu.abi','ro.build.fingerprint')}}
    return result


def package_paths(adb,serial,package):
    if not re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+',package):raise WorkstationError('Pacote Android inválido.')
    output=command([adb,'-s',serial,'shell','pm','path',package])
    return [line[8:].strip() for line in output.splitlines() if line.startswith('package:')]


def backup_apk(adb,serial,package,folder):
    paths=package_paths(adb,serial,package);folder=Path(folder)
    result={'package':package,'existed':bool(paths),'files':[],'scope':'Somente APKs; não inclui dados privados do aplicativo.'}
    if not paths:return result
    folder.mkdir(parents=True,exist_ok=False)
    for index,path in enumerate(paths):
        if not path.startswith('/') or not path.lower().endswith('.apk') or '\n' in path:raise WorkstationError('O aparelho retornou um caminho APK inválido.')
        target=folder/('base.apk' if index==0 else 'split-'+str(index)+'.apk')
        command([adb,'-s',serial,'pull',path,str(target)],timeout=120)
        if not target.is_file() or not target.stat().st_size:raise WorkstationError('Backup do APK não confirmado.')
        digest=hashlib.sha256(target.read_bytes()).hexdigest()
        result['files'].append({'path':str(target),'sha256':digest,'bytes':target.stat().st_size})
    (folder/'backup.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def install(apk,folder,sdk=None,jdk=None,serial=None,launch=False):
    env=build.discover(sdk,jdk);metadata=build.inspect_apk(apk,env);adb=adb_path(str(env['sdk']));serial=select(adb,serial)
    output=Path(folder)/('install-'+time.strftime('%Y%m%d-%H%M%S')+'-'+os.urandom(3).hex());output.mkdir(parents=True)
    report={'ok':False,'serial':serial,'apk':metadata,'installed':False,'launch_verified':False,'visual_tested':False}
    report['backup']=backup_apk(adb,serial,metadata['package'],output/'backup')
    (output/'install-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    response=command([adb,'-s',serial,'install','-r',metadata['apk']],timeout=180)
    if 'Success' not in response:raise WorkstationError('Instalação não foi confirmada: '+response)
    report.update(installation_reported_success=True,installed=None,phase='checking_version')
    (output/'install-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    paths=package_paths(adb,serial,metadata['package'])
    dump=command([adb,'-s',serial,'shell','dumpsys','package',metadata['package']])
    version=re.search(r'\bversionCode=(\d+)',dump)
    if not paths or not version or version[1]!=metadata['version_code']:raise WorkstationError('A versão instalada não corresponde ao APK enviado. Consulte '+str(output))
    report.update(ok=True,installed=True,installed_version_code=version[1],installed_paths=paths)
    (output/'install-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if launch:
        activity=metadata.get('activity')
        if not activity or not re.fullmatch(r'[A-Za-z0-9_.$]+',activity):
            report.update(ok=False,error='Atividade inicial não identificada; instalação confirmada, abertura não testada.')
            (output/'install-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            return report
        response=command([adb,'-s',serial,'shell','am','start','-W','-n',metadata['package']+'/'+activity])
        report['launch_output']=response
        report['launch_verified']='Status: ok' in response
        report['ok']=report['launch_verified']
    (output/'install-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    report['report']=str(output/'install-result.json');return report


def firmware_plan(image,profile,device):
    """Validate exact operator-provided compatibility facts; never infer compatibility."""
    path=Path(image).resolve();missing=[]
    if not path.is_file():raise WorkstationError('Arquivo de ROM não encontrado.')
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    actual=digest.hexdigest()
    for name in ('sha256','model','board','hardware','source','recovery_procedure'):
        if not isinstance(profile.get(name),str) or not profile[name].strip():missing.append(name)
    matches={
        'sha256':actual==profile.get('sha256'),
        'model':bool(device.get('ro.product.model')) and device.get('ro.product.model')==profile.get('model'),
        'board':bool(device.get('ro.product.board')) and device.get('ro.product.board')==profile.get('board'),
        'hardware':bool(device.get('ro.hardware')) and device.get('ro.hardware')==profile.get('hardware')}
    return {'image':str(path),'bytes':path.stat().st_size,'sha256':actual,'checks':matches,'missing':missing,
            'facts_match':not missing and all(matches.values()),'flash_ready':False,'flashed':False,
            'detail':'Pré-análise somente. Igualdade desses campos não comprova compatibilidade completa de RAM, armazenamento, Wi-Fi, partições ou bootloader. A gravação exige um procedimento validado para a placa e não é executada por esta ferramenta.'}


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['inventory','install','backup-apk','firmware-plan']);p.add_argument('--sdk');p.add_argument('--jdk');p.add_argument('--serial');p.add_argument('--apk');p.add_argument('--package');p.add_argument('--output',default=str(Path.home()/'Documents'/'BBLIA-Execucoes'));p.add_argument('--launch',action='store_true');p.add_argument('--image');p.add_argument('--profile');args=p.parse_args()
    if args.action=='inventory':return inventory(args.sdk,args.serial)
    if args.action=='install':return install(args.apk,args.output,args.sdk,args.jdk,args.serial,args.launch)
    if args.action=='backup-apk':
        adb=adb_path(args.sdk);serial=select(adb,args.serial);return backup_apk(adb,serial,args.package,Path(args.output)/('backup-'+time.strftime('%Y%m%d-%H%M%S')+'-'+os.urandom(3).hex()))
    device=inventory(args.sdk,args.serial)['device']
    if not device:raise WorkstationError('Nenhum aparelho foi identificado. Conecte e autorize a TV Box.')
    return firmware_plan(args.image,json.loads(Path(args.profile).read_text(encoding='utf-8')),device)

if __name__=='__main__':
    try:print(json.dumps(main(),ensure_ascii=False))
    except Exception as exc:print(json.dumps({'ok':False,'error':str(exc)[:4000]},ensure_ascii=False));sys.exit(1)
