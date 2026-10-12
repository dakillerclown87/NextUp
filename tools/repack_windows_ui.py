"""Rebuild a UI-only release using an existing extracted official NextUp payload.

Usage: python tools/repack_windows_ui.py --extracted /path/to/extracted-installer
--makensis /path/to/makensis. Extract an official installer with 7-Zip first.
Native sources must match: never silently reuse binaries after native code changes.
"""
import argparse,hashlib,json,os,shutil,subprocess,sys,re,zipfile,urllib.request,struct
from importlib.metadata import distributions
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from studio import __version__
from tools.release import files
from tools.audit_distribution import audit

def missing_requirements(site, lock):
 installed={re.sub(r"[-_.]+", "-", d.metadata["Name"]).lower():d.version for d in distributions(path=[str(site)])}
 missing=[]
 for line in lock.read_text().splitlines():
  match=re.match(r"([A-Za-z0-9_.-]+)==([^ ]+)",line)
  if match and installed.get(re.sub(r"[-_.]+", "-", match[1]).lower())!=match[2]:missing.append(line)
 return missing

def sync_dependencies(app, build, wheelhouse=None):
 site=app/'runtime/Lib/site-packages'
 missing=missing_requirements(site,ROOT/'requirements-windows.lock')
 if missing:
  lock=build/'missing-windows.lock';lock.write_text("\n".join(missing)+"\n")
  cmd=[sys.executable,'-m','pip','install','--disable-pip-version-check','--only-binary=:all:','--platform','win_amd64','--python-version','3.13','--implementation','cp','--abi','cp313','--no-compile','--no-deps','--upgrade','--target',str(site),'--require-hashes','-r',str(lock)]
  if wheelhouse:cmd+=['--no-index','--find-links',str(wheelhouse.resolve())]
  subprocess.run(cmd,check=True)
 if missing_requirements(site,ROOT/'requirements-windows.lock'):raise ValueError('Bundled dependencies do not match the Windows lock.')
 inventory=app/'BUNDLED-DEPENDENCIES.txt'
 header=inventory.read_text().split('\n\n',1)[0]
 inventory.write_text(header+'\n\n'+'\n'.join(sorted(p.name for p in site.glob('*.dist-info')))+'\n')
 for info in site.glob('*.dist-info'):(info/'direct_url.json').unlink(missing_ok=True)

def refresh_runtime(build, app, archive=None):
 from tools.build_windows import URL,check_runtime
 data=archive.read_bytes() if archive else urllib.request.urlopen(URL,timeout=60).read()
 check_runtime(data)
 bundle=build/'verified-python.zip';bundle.write_bytes(data)
 with zipfile.ZipFile(bundle) as z:
  if z.testzip():raise ValueError('Damaged Python runtime archive')
  for runtime in [build/'runtime',app/'runtime']:
   runtime.mkdir(parents=True,exist_ok=True)
   z.extractall(runtime)
   (runtime/'python313._pth').write_text('python313.zip\n.\nLib/site-packages\n',encoding='utf-8')

def check_pe(path):
 data=path.read_bytes()
 try:
  if data[:2]!=b'MZ':raise ValueError('Missing MZ header')
  pe=struct.unpack_from('<I',data,60)[0]
  if data[pe:pe+4]!=b'PE\0\0':raise ValueError('Missing PE header')
  count=struct.unpack_from('<H',data,pe+6)[0];opt=struct.unpack_from('<H',data,pe+20)[0]
  for i in range(count):
   size,offset=struct.unpack_from('<II',data,pe+24+opt+40*i+16)
   if size and offset+size>len(data):raise ValueError('Truncated section')
 except (ValueError,struct.error) as e:raise ValueError(f'Invalid Windows binary {path}: {e}') from e

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--extracted',required=True,type=Path);ap.add_argument('--makensis',default='makensis');ap.add_argument('--wheelhouse',type=Path);ap.add_argument('--python-zip',type=Path);a=ap.parse_args()
 previous=a.extracted.resolve();versions=list((previous/'versions').iterdir())
 if len(versions)!=1:raise ValueError('Expected exactly one original installer payload.')
 old=versions[0];meta=json.loads((old/'bundle.json').read_text())
 if meta.get('product')!='nextup' or meta.get('platform')!='windows-x64':raise ValueError('Not a NextUp Windows payload.')
 for name in ['audio_capture.c','launcher.c']:
  if (old/'packaging/windows'/name).read_bytes()!=(ROOT/'packaging/windows'/name).read_bytes():raise ValueError('Native source changed. Use build_windows.py for a full native build.')
 if (old/'studio/static/nextup.ico').read_bytes()!=(ROOT/'studio/static/nextup.ico').read_bytes():raise ValueError('Icon changed; full build required.')
 items=list(files());audit(items);build=ROOT/'build/ui-repack';dist=ROOT/'dist';dist.mkdir(exist_ok=True)
 if build.exists():shutil.rmtree(build)
 app=build/'app';app.mkdir(parents=True)
 for name in ['runtime','studio/native']:
  shutil.copytree(old/name,app/name)
 shutil.copy2(old/'BUNDLED-DEPENDENCIES.txt',app/'BUNDLED-DEPENDENCIES.txt')
 sync_dependencies(app,build,a.wheelhouse)
 for source,relative in items:
  target=app/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
 shutil.copy2(ROOT/'packaging/windows/entry.py',app/'entry.py')
 meta['version']=__version__; (app/'bundle.json').write_text(json.dumps(meta))
 refresh_runtime(build,app,a.python_zip);shutil.copy2(previous/'NextUp.exe',build/'NextUp.exe')
 webview=previous/'$PLUGINSDIR/MicrosoftEdgeWebview2Setup.exe'
 from tools.build_windows import WEBVIEW_SHA256
 if hashlib.sha256(webview.read_bytes()).hexdigest()!=WEBVIEW_SHA256:raise ValueError('WebView2 checksum mismatch')
 shutil.copy2(webview,build/webview.name)
 subprocess.run([sys.executable,str(ROOT/'tools/audit_distribution.py'),'--payload',str(app)],check=True)
 for binary in build.rglob('*'):
  if binary.suffix.lower() in ('.dll','.exe','.pyd'):check_pe(binary)
 exe=dist/f'NextUp-Setup-{__version__}-x64.exe'
 subprocess.run([a.makensis,'-DAPPNAME=NextUp','-DMUTEX=NextUpApp','-DINSTALLFOLDER=NextUp','-DREGKEY=NextUp',f'-DVERSION={__version__}',f'-DSOURCE={ROOT}',f'-DPAYLOAD={build}',f'-DOUTPUT={exe}',str(ROOT/'packaging/windows/installer.nsi')],check=True)
 (dist/(exe.name+'.sha256')).write_text(hashlib.sha256(exe.read_bytes()).hexdigest()+'  '+exe.name+'\n')
 print('Built',exe)
if __name__=='__main__':main()
