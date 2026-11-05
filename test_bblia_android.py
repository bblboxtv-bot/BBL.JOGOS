import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import bblia_android_build as b

class AndroidBuildTests(unittest.TestCase):
 def test_smoke_is_separate_and_cannot_overwrite_project(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);b.smoke(root)
   self.assertIn('com.bblia.compilacao.teste',(root/'AndroidManifest.xml').read_text())
   self.assertTrue((root/'src/com/bblia/compilacao/teste/MainActivity.java').is_file())
   with self.assertRaises(b.BuildError):b.smoke(root)
 def test_missing_sdk_fails_before_build(self):
  with patch.dict('os.environ',{'ANDROID_HOME':'','ANDROID_SDK_ROOT':'','LOCALAPPDATA':'/not-present'}),patch.object(Path,'home',return_value=Path('/not-present')):
   with self.assertRaises(b.BuildError):b.discover('/not-present','/not-present')
 def test_stable_sdk_preferred_to_preview(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);sdk=root/'sdk';jdk=root/'jdk';exe='.exe' if b.os.name=='nt' else ''
   (jdk/'bin').mkdir(parents=True);(jdk/'bin'/('javac'+exe)).touch()
   for name in ('android-35','android-37.0'):(sdk/'platforms'/name).mkdir(parents=True);(sdk/'platforms'/name/'android.jar').touch()
   tools=sdk/'build-tools/36.0.0';(tools/'lib').mkdir(parents=True)
   for name in ['aapt2'+exe,'lib/d8.jar','lib/apksigner.jar']:(tools/name).touch()
   result=b.discover(str(sdk),str(jdk));self.assertEqual(result['platform'].name,'android-35')

if __name__=='__main__':unittest.main()
