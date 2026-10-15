"""Fetch the pinned 2026-10-15 gap-audit inputs without overwriting files.

ZIP hashes freeze this audit's downloaded bytes. GitHub asset digests were also
checked against the Release API. N03's hash is locally measured, not an official
publisher signature. curl uses the inherited proxy and TLS trust.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ASSETS = [
    ('plane_rectangular_zones_2026.zip',
     'https://github.com/yo-1/japan-plane-rectangular-cs-zones/releases/download/v2026.2/plane_rectangular_zones_2026.zip',
     'c32ac8417ee604436e0a20280a6f2d3a1e73a3247c5a8db10230209daf9e3fbd'),
    ('plane_rectangular_municipalities_2026.zip',
     'https://github.com/yo-1/japan-plane-rectangular-cs-zones/releases/download/v2026.2/plane_rectangular_municipalities_2026.zip',
     'cfdefd12ea7114796b26d4d9d10d244bd4b03c110b9dd7f2fcc9a12d92c9051b'),
    ('N03-20260101_GML.zip',
     'https://nlftp.mlit.go.jp/ksj/gml/data/N03/N03-2026/N03-20260101_GML.zip',
     '1f714fca019e22e6f84012dba420384fc7b49c6ad8bd0a867ab1cfb593a78477')]


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, url, expected in ASSETS:
        target = args.output/name
        if not target.exists():
            partial = target.with_suffix('.zip.part')
            # Reserve our download path, preserving pre-existing partial files.
            with partial.open('xb'):
                pass
            subprocess.run(['curl', '-fLsS', '--retry', '2', '--max-time', '600',
                            '--output', str(partial), url], check=True)
            assert digest(partial) == expected, f'Checksum mismatch: {partial}'
            partial.rename(target)
        assert digest(target) == expected, f'Checksum mismatch: {target}'
        manifest.append(dict(name=name, url=url, sha256=expected, bytes=target.stat().st_size))
        with zipfile.ZipFile(target) as archive:
            for member in archive.infolist():
                p = Path(member.filename)
                if not (p.suffix.lower() == '.gpkg' or
                        p.stem == 'N03-20260101' and p.suffix.lower() in ['.shp', '.shx', '.dbf', '.prj', '.cpg']):
                    continue
                destination = args.output/p.name
                # Verify the member even on replay; never assume name equality.
                h = hashlib.sha256()
                with archive.open(member) as src:
                    while chunk := src.read(1024*1024):
                        h.update(chunk)
                expected_member = h.hexdigest()
                if not destination.exists():
                    with archive.open(member) as src, destination.open('xb') as out:
                        shutil.copyfileobj(src, out)
                assert digest(destination) == expected_member, destination
                manifest.append(dict(name=destination.name, archive=name,
                    sha256=expected_member, bytes=destination.stat().st_size))
        print('verified', name, flush=True)
    result = args.output/'pinned-download-manifest.json'
    content = json.dumps(manifest, indent=2)+'\n'
    if result.exists():
        assert result.read_text() == content
    else:
        result.write_text(content)


if __name__ == '__main__':
    main()
