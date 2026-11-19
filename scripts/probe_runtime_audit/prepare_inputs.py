"""Verify the three published v2026.3 ZIPs and prepare read-only test inputs."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import zipfile
import xml.etree.ElementTree as ET

EXPECTED = {
    'zones': 'cbc87ceffa22c3453d6dae04c17c31a4276aeee6aa183c91eb87c85598074f3f',
    'prefectures': 'c09c41214e81965dfb9ade1a4ff883edc8429a05e1a0b9a555793cd72994e241',
    'municipalities': 'bec2b2fc41bec44bd43e969dcc75e4338748ad26c4772f94eb451d7f579cef72',
}


def hashfile(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def prepare(root):
    data = root / 'data'
    if data.exists() or (root / 'input-manifest.json').exists():
        raise FileExistsError('Use a new test directory; earlier inputs are preserved')
    data.mkdir()
    manifest = {}
    for kind, expected in EXPECTED.items():
        archive = root / 'downloads' / f'plane_rectangular_{kind}_2026.zip'
        actual = hashfile(archive)
        if actual != expected:
            raise ValueError(f'Published ZIP hash mismatch: {kind}')
        with zipfile.ZipFile(archive) as source:
            if source.testzip() is not None:
                raise ValueError(f'ZIP CRC failure: {kind}')
            members = [name for name in source.namelist() if name.endswith('.gpkg')]
            if len(members) != 1:
                raise ValueError('Expected one GeoPackage per archive')
            output = data / Path(members[0]).name
            with source.open(members[0]) as stream, output.open('xb') as target:
                shutil.copyfileobj(stream, target)
        with closing(sqlite3.connect(output.resolve().as_uri() + '?mode=ro', uri=True)) as db:
            layers = db.execute('SELECT table_name,column_name,srs_id FROM gpkg_geometry_columns').fetchall()
            if len(layers) != 1:
                raise ValueError('Expected one feature layer')
            table = '"' + layers[0][0].replace('"', '""') + '"'
            fields = [row[1] for row in db.execute('PRAGMA table_info(' + table + ')') if row[1] != layers[0][1]]
            styles = db.execute('SELECT f_table_name,styleName,useAsDefault,length(styleQML) FROM layer_styles').fetchall()
            qml = db.execute('SELECT styleQML FROM layer_styles WHERE useAsDefault=1').fetchone()
            labels_enabled = ET.fromstring(qml[0]).get('labelsEnabled') == '1'
        manifest[kind] = dict(zip_sha256=actual, gpkg_name=output.name, gpkg_sha256=hashfile(output),
                              layers=layers, fields=fields, styles=styles, style_labels_enabled=labels_enabled)
    with (root / 'input-manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, indent=2)
        stream.write('\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    prepare(args.root.resolve())
