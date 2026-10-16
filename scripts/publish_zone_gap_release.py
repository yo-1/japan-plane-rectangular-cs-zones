"""Resume verified draft asset uploads, then publish the investigation prerelease."""
from pathlib import Path
import hashlib,json,os,subprocess
import argparse
ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument("--directory",type=Path,required=True)
root=ap.parse_args().directory.resolve()
repo='yo-1/japan-plane-rectangular-cs-zones'; tag='zone-gap-audit-20261015'
env=os.environ.copy()
if env.get('GH_RELEASE_UPLOAD_TOKEN'):env['GH_TOKEN']=env['GH_RELEASE_UPLOAD_TOKEN']
def gh(*args):return subprocess.check_output(['gh',*args],env=env,text=True)
def api(path):return json.loads(gh('api',path))
manifest=json.loads((root/'package-verification.json').read_text())
for row in manifest['archives']:
 p=root/row['file']
 assert p.stat().st_size==row['bytes']
 assert hashlib.file_digest(p.open('rb'),'sha256').hexdigest()==row['sha256']
release=api(f'repos/{repo}/releases/413430612')
assert release['id']==413430612 and release['prerelease']
files=[r['file'] for r in manifest['archives']]+['SHA256SUMS.txt','RELEASE-README.txt','package-verification.json']
for name in files:
 p=root/name;digest='sha256:'+hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
 assets={r['name']:r for r in api(f'repos/{repo}/releases/{release["id"]}')['assets']}
 if name not in assets:
  assert release['draft'], 'Refuse to add missing assets to an already published release'
  gh('release','upload',tag,str(p),'--repo',repo)
  assets={r['name']:r for r in api(f'repos/{repo}/releases/{release["id"]}')['assets']}
 assert assets[name]['size']==p.stat().st_size
 assert assets[name].get('digest')==digest, 'Remote digest mismatch or unavailable'
 print('verified',name,flush=True)
if release['draft']:gh('release','edit',tag,'--draft=false','--prerelease','--latest=false','--repo',repo)
assert not api(f'repos/{repo}/releases/tags/{tag}')['draft']
assert api(f'repos/{repo}/releases/latest')['tag_name']=='v2026.2'
print(f'https://github.com/{repo}/releases/tag/{tag}')
