#!/usr/bin/env python3
"""Installer safety checks use disposable ELF fixtures, not a release acceptance test."""
import hashlib, importlib.util, io, json, os
from pathlib import Path
import platform, subprocess, sys, tarfile, tempfile, unittest
TOOL=Path(__file__).with_name('native-bundle.py')
class BundleSafetyTest(unittest.TestCase):
 def run_install(self, payload, extra=None, digest=None):
  temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);root=Path(temporary.name)
  archive=root/'bundle.tar.gz';files=[]
  with tarfile.open(archive,'w:gz') as tar:
   for name,body in payload.items():
    info=tarfile.TarInfo(name);info.size=len(body);tar.addfile(info,io.BytesIO(body))
    files.append(dict(path=name,bytes=len(body),sha256=hashlib.sha256(body).hexdigest()))
   if extra:
    info=tarfile.TarInfo(extra);info.size=1;tar.addfile(info,io.BytesIO(b'x'))
   body=json.dumps(dict(schema=1,architecture=platform.machine(),files=files)).encode();info=tarfile.TarInfo('manifest.json');info.size=len(body);tar.addfile(info,io.BytesIO(body))
  config=root/'config/vaani/config.toml';config.parent.mkdir(parents=True);config.write_text('# user configuration\n')
  env=dict(os.environ,XDG_CONFIG_HOME=str(root/'config'),XDG_DATA_HOME=str(root/'data'),VAANI_BIN_ROOT=str(root/'bin'))
  result=subprocess.run([sys.executable,str(TOOL),'install',str(archive),'--sha256',digest or hashlib.sha256(archive.read_bytes()).hexdigest()],env=env,capture_output=True,text=True)
  self.assertEqual(config.read_text(),'# user configuration\n')
  return result,root
 def payload(self):
  return {'bin/'+n:Path('/usr/bin/true').read_bytes() for n in ('vaanid','vaani','vaani-worker','vaani-desktop','vaani-linux','whisper-cli','llama-cli','vaani-whisper-session','vaani-llama-session')}
 def test_checksum_failure_changes_nothing(self):
  result,root=self.run_install(self.payload(),digest='0'*64);self.assertNotEqual(result.returncode,0);self.assertFalse((root/'bin').exists())
 def test_path_traversal_changes_nothing(self):
  result,root=self.run_install(self.payload(),extra='../escape');self.assertNotEqual(result.returncode,0);self.assertFalse((root/'bin').exists())
 def test_valid_fixture_installs_without_overwriting_config(self):
  result,root=self.run_install(self.payload());self.assertEqual(result.returncode,0,result.stderr);self.assertTrue((root/'bin/vaani-linux').is_file())
 def test_unowned_destination_rolls_back(self):
  payload=self.payload();payload['share/applications/unrelated.desktop']=b'no';result,root=self.run_install(payload)
  self.assertNotEqual(result.returncode,0);self.assertFalse((root/'bin/vaani-linux').exists());self.assertFalse((root/'data/applications/unrelated.desktop').exists())
if __name__=='__main__':unittest.main()
