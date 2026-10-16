"""Package the fixed zone-gap investigation, checking all member hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=Path, required=True)
    dest = ap.parse_args().output
    dest.mkdir(parents=True, exist_ok=False)
    roots = ['docs/zone-gap-audit-20261015', 'scripts', 'tests', 'data',
             '.github/workflows/publish-zone-gap-audit.yml', 'README.md',
             'VALIDATION.txt', 'LICENSE', 'DATA_LICENSE.md']
    paths = subprocess.check_output(['git', 'ls-files', *roots], text=True).splitlines()
    files = {Path(p): Path(p) for p in paths}
    for directory in ['output/zone-gap-audit-20261015', 'output/zone-exterior-screen-20261015',
                      'output/n03-municipality-recheck-20261015', 'output/rock-followup-20261015']:
        for p in Path(directory).iterdir():
            if p.is_file() and p.suffix in ['.json', '.csv', '.gpkg', '.geojson']:
                files[p] = p
    context = Path('docs/zone-gap-audit-20261015/rock-followup/vector-context/vector-context.gpkg')
    files[context] = context
    copies = {p: p for p in Path('output/arcgis-comparison-20261015').iterdir() if p.is_file()}
    for p in Path('docs/zone-gap-audit-20261015/arcgis-comparison').iterdir():
        if p.is_file():
            copies[p] = p
    copies[Path('DATA_LICENSE.md')] = Path('DATA_LICENSE.md')
    readme = '''19系区域の調査資料・図形型比較コピーです。補修版ではありません。
原典・正式公開v2026.2は変更せず、岩礁付近2件は原典維持・補修保留です。
調査報告: docs/zone-gap-audit-20261015/README.md
調査結果・図の記録は初回実施時のものです。今回の再生成結果はoutput/以下にあります。
再生成時刻やFID順序により、初回GeoPackageやZIPのハッシュと異なる場合があります。
今回のファイルはPACKAGE-MANIFEST.jsonと添付SHA256SUMS.txtで照合してください。
ArcGIS実機検証は未完了です。正式データやN03原典本体は同梱しません。
出典・利用条件はDATA_LICENSE.mdと各報告の地理院タイル等の出典を参照してください。
'''
    records = []
    for name, mapping in [('zone-gap-audit-20261015-complete.zip', files),
                          ('zone-gap-arcgis-comparison-20261015.zip', copies)]:
        manifest = [dict(path=str(arc), bytes=src.stat().st_size, sha256=digest(src))
                    for arc, src in sorted(mapping.items())]
        target = dest / name
        with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr('RELEASE-README.txt', readme)
            archive.writestr('PACKAGE-MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
            for arc, src in sorted(mapping.items()):
                archive.write(src, str(arc))
        with zipfile.ZipFile(target) as archive:
            assert archive.testzip() is None
            for row in manifest:
                assert hashlib.sha256(archive.read(row['path'])).hexdigest() == row['sha256']
        records.append(dict(file=name, bytes=target.stat().st_size, sha256=digest(target), members=len(manifest)))
        print(json.dumps(records[-1]), flush=True)
    (dest/'SHA256SUMS.txt').write_text(''.join(r['sha256']+'  '+r['file']+'\n' for r in records))
    (dest/'RELEASE-README.txt').write_text(readme)
    (dest/'package-verification.json').write_text(json.dumps(dict(archives=records,
        zip_crc='passed', all_member_sha256='passed', repair='none',
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip()), indent=2)+'\n')


if __name__ == '__main__':
    main()
