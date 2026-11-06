import hashlib,json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import bblia_workstation as w
import bblia_android_build as b

class WorkstationTests(unittest.TestCase):
 def test_multiple_devices_require_an_explicit_selection(self):
  listing=[{'serial':'box1','state':'device'},{'serial':'box2','state':'device'}]
  with patch.object(w,'devices',return_value=listing):
   with self.assertRaises(w.WorkstationError):w.select('adb')
   self.assertEqual(w.select('adb','box2'),'box2')
   with self.assertRaises(w.WorkstationError):w.select('adb','other')
 def test_unauthorized_box_never_selected(self):
  with patch.object(w,'devices',return_value=[{'serial':'box','state':'unauthorized'}]):
   with self.assertRaises(w.WorkstationError):w.select('adb','box')
 def test_firmware_facts_do_not_enable_a_flash(self):
  with tempfile.TemporaryDirectory() as folder:
   rom=Path(folder)/'firmware.img';rom.write_bytes(b'test firmware')
   profile={'sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'model':'MODEL','board':'BOARD','hardware':'HARDWARE','source':'fabricante','recovery_procedure':'procedimento'}
   device={'ro.product.model':'MODEL','ro.product.board':'BOARD','ro.hardware':'HARDWARE'}
   report=w.firmware_plan(rom,profile,device)
   self.assertTrue(report['facts_match']);self.assertFalse(report['flash_ready']);self.assertFalse(report['flashed'])
   device['ro.product.board']='OTHER'
   self.assertFalse(w.firmware_plan(rom,profile,device)['facts_match'])
 def test_backup_failure_prevents_installation(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(b,'discover',return_value={'sdk':folder}),patch.object(b,'inspect_apk',return_value={'package':'br.test.app','apk':'app.apk','version_code':'3'}),patch.object(w,'adb_path',return_value='adb'),patch.object(w,'select',return_value='box'),patch.object(w,'backup_apk',side_effect=w.WorkstationError('backup failed')),patch.object(w,'command') as command:
   with self.assertRaises(w.WorkstationError):w.install('app.apk',folder)
   command.assert_not_called()
 def test_install_checks_version_and_reports_backup_scope(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(b,'discover',return_value={'sdk':folder}),patch.object(b,'inspect_apk',return_value={'package':'br.test.app','apk':'app.apk','version_code':'3','activity':'br.test.app.MainActivity'}),patch.object(w,'adb_path',return_value='adb'),patch.object(w,'select',return_value='box'),patch.object(w,'backup_apk',return_value={'scope':'Somente APKs'}),patch.object(w,'package_paths',return_value=['/data/app/base.apk']),patch.object(w,'command',side_effect=['Success','versionCode=3 minSdk=21','Status: ok']):
   result=w.install('app.apk',folder,launch=True)
   self.assertTrue(result['installed']);self.assertTrue(result['launch_verified']);self.assertFalse(result['visual_tested'])
   self.assertEqual(json.loads(Path(result['report']).read_text())['installed_version_code'],'3')
 def test_wrong_installed_version_is_not_a_success(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(b,'discover',return_value={'sdk':folder}),patch.object(b,'inspect_apk',return_value={'package':'br.test.app','apk':'app.apk','version_code':'3'}),patch.object(w,'adb_path',return_value='adb'),patch.object(w,'select',return_value='box'),patch.object(w,'backup_apk',return_value={}),patch.object(w,'package_paths',return_value=['/data/app/base.apk']),patch.object(w,'command',side_effect=['Success','versionCode=2']):
   with self.assertRaisesRegex(w.WorkstationError,'versão instalada'):w.install('app.apk',folder)
 def test_gradle_success_without_new_apk_is_not_success(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);(root/'settings.gradle').write_text('');gradle=root/'gradle';gradle.touch()
   env={'jdk':root,'sdk':root,'tools':root,'exe':''}
   with patch.object(b,'discover',return_value=env),patch.object(b.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'BUILD SUCCESSFUL','')):
    with self.assertRaisesRegex(b.BuildError,'nenhum APK novo'):b.build_gradle(root,gradle=str(gradle))

if __name__=='__main__':unittest.main()
