"""Restore recorded investigation rows; use pinned public data for the large zone reference."""
import argparse
import base64
import gzip
import json
from pathlib import Path
import sqlite3

from audit_zone_gaps import layer, read_layer
from geometry_audit.common import hashfile
from prepare_arcgis_comparison import fingerprint, quote

SNAPSHOT = Path('docs/zone-gap-audit-20261015/investigation-snapshot.json.gz')
INPUTS = [Path(p) for p in [
    'output/zone-gap-audit-20261015/candidates.gpkg',
    'output/n03-municipality-recheck-20261015/differences.gpkg',
    'output/zone-exterior-screen-20261015/exterior-screen.gpkg',
    'output/rock-followup-20261015/source-ring-evidence.gpkg',
    'docs/zone-gap-audit-20261015/rock-followup/vector-context/vector-context.gpkg']]
CORE = ['gpkg_spatial_ref_sys', 'gpkg_contents', 'gpkg_geometry_columns']


def encode(value):
    return {'blob_base64': base64.b64encode(value).decode('ascii')} if isinstance(value, bytes) else value


def decode(value):
    return base64.b64decode(value['blob_base64'], validate=True) if isinstance(value, dict) else value


def capture():
    records = []
    for path in INPUTS:
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True) as db:
            cores = []
            for name in CORE:
                rows = db.execute('SELECT * FROM '+quote(name)).fetchall()
                if name in ['gpkg_contents', 'gpkg_geometry_columns']:
                    rows = [r for r in rows if r[0] != 'zone_reference']
                cores.append(dict(sql=db.execute('SELECT sql FROM sqlite_master WHERE name=?', (name,)).fetchone()[0],
                                  name=name, rows=rows))
            tables = []
            for name, in db.execute('SELECT table_name FROM gpkg_geometry_columns'):
                rows = db.execute('SELECT * FROM '+quote(name)).fetchall()
                tables.append(dict(name=name, before=fingerprint(rows),
                    sql=db.execute('SELECT sql FROM sqlite_master WHERE name=?', (name,)).fetchone()[0],
                    rows=None if name=='zone_reference' else [[encode(v) for v in r] for r in rows]))
        records.append(dict(path=str(path), core=cores, tables=tables))
    data = dict(scope='Recorded evidence snapshot, not a new N03 audit', repair='none', files=records)
    with SNAPSHOT.open('xb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as stream:
        stream.write(json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode())


def restore(zones):
    assert hashfile(zones)=='9392e5e3fecedbab7ba774dc89c81bc353c265d16d66a1c86f6e341b5946eafc'
    with gzip.open(SNAPSHOT, 'rt') as stream:
        data = json.load(stream)
    # Refuse before creating any files if a destination exists.
    for record in data['files']:
        assert not Path(record['path']).exists(), record['path']
    results = []
    for record in data['files']:
        path = Path(record['path'])
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as db:
            db.execute('PRAGMA application_id=1196444487')
            db.execute('PRAGMA user_version=10300')
            for core in record['core']:
                db.execute(core['sql'])
                for row in core['rows']:
                    db.execute('INSERT INTO '+quote(core['name'])+' VALUES ('+','.join('?' for _ in row)+')', row)
            for table in record['tables']:
                if table['rows'] is None:
                    continue
                db.execute(table['sql'])
                for row in table['rows']:
                    db.execute('INSERT INTO '+quote(table['name'])+' VALUES ('+','.join('?' for _ in row)+')', tuple(decode(v) for v in row))
        if any(t['rows'] is None for t in record['tables']):
            geoms, fields = read_layer(zones)
            layer(path, 'zone_reference', [(g, dict(zone=int(n))) for g,n in zip(geoms, fields['ZONE'])])
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True) as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            for table in record['tables']:
                actual = fingerprint(db.execute('SELECT * FROM '+quote(table['name'])))
                assert actual==table['before'], (path, table['name'])
                results.append(dict(file=str(path), layer=table['name'], **actual))
        print('restored exact feature values', path, flush=True)
    report = dict(scope=data['scope'], snapshot_sha256=hashfile(SNAPSHOT), all_feature_values_identical=True, tables=results)
    Path('output/snapshot-restoration.json').write_text(json.dumps(report, indent=2)+'\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--capture', action='store_true')
    ap.add_argument('--zones', type=Path)
    args = ap.parse_args()
    if args.capture:
        capture()
    else:
        if args.zones is None:
            ap.error('--zones is required to restore')
        restore(args.zones)


if __name__=='__main__':
    main()
