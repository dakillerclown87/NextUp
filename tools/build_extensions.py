"""Build two browser packages from one source; Firefox output is unsigned."""
import argparse, copy, json, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def build(out):
    src=ROOT/'chrome-extension';base=json.loads((src/'manifest.json').read_text())
    firefox=copy.deepcopy(base);firefox['manifest_version']=2
    firefox['permissions']+=firefox.pop('host_permissions')
    firefox['browser_action']=firefox.pop('action')
    firefox['background']={'scripts':['background.js'],'persistent':True}
    firefox.pop('minimum_chrome_version',None)
    firefox['browser_specific_settings']={'gecko':{'id':'nextup-player@nextup.local','strict_min_version':'140.0','data_collection_permissions':{'required':['authenticationInfo','websiteActivity']}}}
    firefox['content_security_policy']="script-src 'self'; object-src 'self'; connect-src ws://127.0.0.1:8888"
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    version=base['version'].rsplit('.',1);label=version[0]+'-beta.'+version[1]
    paths=[]
    for browser,manifest in [('Chromium',base),('Firefox',firefox)]:
        p=out/f'NextUp-{browser}-Extension-{label}.zip'
        with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as z:
            for f in sorted(src.iterdir()):
                if f.is_file() and f.name!='manifest.json':z.write(f,f.name)
            z.writestr('manifest.json',json.dumps(manifest,indent=2)+'\n')
        paths.append(p)
    return paths

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',default=ROOT/'dist');args=parser.parse_args()
    for p in build(args.out):print(p)
