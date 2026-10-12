"""Reject personal data and private keys in a public NextUp distribution."""
import argparse, json, re, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.release import files

FORBIDDEN_NAMES={'accounts.json','studio.json','config.json','credentials.json','tokens.json',
    'twitch_tokens.json','overlay-key.txt','private-key.txt','moderators.json','cloud-settings.json',
    'before-cloud-restore.json','admin-token.txt','.env','.dev.vars','.ready'}
FORBIDDEN_PARTS={'userdata','data','signing-keys','.git','node_modules','songid','songscout','cloud'}
PRIVATE_HEADER=re.compile(rb'^-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----',re.M)

def audit(items):
    count=0
    for path,rel in items:
        parts=set(rel.parts)
        if parts & FORBIDDEN_PARTS or path.name in FORBIDDEN_NAMES or path.name.startswith(('.env.','.dev.vars.')):
            raise ValueError('Personal or excluded file in distribution: '+str(rel))
        if path.suffix.lower() in {'.key','.pem','.pfx','.p12','.sqlite3','.db','.log','.jsonl'}:
            raise ValueError('Private/data file type in distribution: '+str(rel))
        if path.suffix.lower() in {'.json','.py','.js','.txt','.md','.yml','.yaml','.lock'}:
            if PRIVATE_HEADER.search(path.read_bytes()):
                raise ValueError('Private signing material in distribution: '+str(rel))
        count+=1
    return count

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--payload',type=Path)
    args=parser.parse_args()
    if args.payload:
        root=args.payload
        # Vendor runtime may contain its own data folders; audit all application
        # files, and explicitly reject recognition dependencies in the runtime.
        items=[(p,p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.relative_to(root).parts[0]!='runtime']
        site=root/'runtime/Lib/site-packages'
        for prefix in ('shazamio','soundcard','streamlink','av','pydub'):
            if (site/prefix).exists():raise ValueError('Recognition dependency bundled: '+prefix)
    else:items=list(files())
    print('PASS: distribution audit checked',audit(items),'application files; no local data or private-key files found.')

if __name__=='__main__':main()
