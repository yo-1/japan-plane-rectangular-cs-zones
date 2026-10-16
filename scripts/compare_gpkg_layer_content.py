"""Compare one GeoPackage layer read-only, separating file identity and feature identity.

This compares bytes/attributes and declared schema; it does not run ArcGIS or
validate geometric topology. Styles can change the file hash without changing
feature values. FID is included and duplicate row multiplicity is preserved.
"""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import struct


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def quote(name):
    return '"'+name.replace('"', '""')+'"'


def fingerprint(rows):
    hashes = []
    for row in rows:
        h = hashlib.sha256()
        for value in row:
            if value is None: kind, data = b'N', b''
            elif isinstance(value, bytes): kind, data = b'B', value
            elif isinstance(value, str): kind, data = b'S', value.encode('utf-8')
            elif isinstance(value, int): kind, data = b'I', str(value).encode('ascii')
            elif isinstance(value, float): kind, data = b'F', struct.pack('>d', value)
            else: raise TypeError(type(value))
            h.update(kind+struct.pack('>Q', len(data))+data)
        hashes.append(h.hexdigest())
    return dict(count=len(hashes), sha256=hashlib.sha256(''.join(sorted(hashes)).encode('ascii')).hexdigest())


def inspect(path, layer, key_field=None, key_value=None):
    path = path.resolve()
    before = digest(path)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite integrity failure')
        meta = db.execute('SELECT column_name,geometry_type_name,srs_id,z,m FROM gpkg_geometry_columns WHERE table_name=?', (layer,)).fetchone()
        if meta is None: raise ValueError('Missing layer: '+layer)
        info = db.execute('PRAGMA table_info('+quote(layer)+')').fetchall()
        columns = sorted(r[1] for r in info)
        attrs = [c for c in columns if c != meta[0]]
        if key_field is not None and key_field not in columns:
            raise ValueError('Unknown selection field: '+key_field)
        where = ' WHERE '+quote(key_field)+'=?' if key_field is not None else ''
        params = (key_value,) if key_field is not None else ()
        full = fingerprint(db.execute('SELECT '+','.join(quote(c) for c in columns)+' FROM '+quote(layer)+where, params))
        attributes = fingerprint(db.execute('SELECT '+','.join(quote(c) for c in attrs)+' FROM '+quote(layer)+where, params))
        if full['count']==0:
            raise ValueError('No features match the selection')
        geom_type = next(r[2].upper() for r in info if r[1] == meta[0])
        ordered = hashlib.sha256()
        for blob, in db.execute('SELECT '+quote(meta[0])+' FROM '+quote(layer)+where+' ORDER BY fid', params):
            ordered.update(blob)
        style_info = None
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='layer_styles'").fetchone():
            style_info = fingerprint(db.execute('SELECT * FROM layer_styles'))
        srs = db.execute('SELECT * FROM gpkg_spatial_ref_sys WHERE srs_id=?', (meta[2],)).fetchone()
    if digest(path) != before: raise AssertionError('Input changed')
    return dict(path=str(path), file_sha256=before, columns=columns,
                all_columns=full, attributes=attributes, geometry_blobs_ordered_by_fid_sha256=ordered.hexdigest(),
                geometry_metadata=list(meta), geometry_sql_type=geom_type,
                column_schema=sorted([list(r[1:]) for r in info]), srs_definition=list(srs),
                style_table=style_info, input_unchanged=True)


def compare(left, right, layer, right_layer=None, key_field=None, key_value=None):
    a = inspect(left, layer, key_field, key_value)
    b = inspect(right, right_layer or layer, key_field, key_value)
    return dict(layer=layer, right_layer=right_layer or layer, selection=dict(field=key_field,value=key_value), left=a, right=b,
        same_file=a['file_sha256']==b['file_sha256'],
        same_feature_values=a['columns']==b['columns'] and a['all_columns']==b['all_columns'],
        same_geometry_blobs=a['geometry_blobs_ordered_by_fid_sha256']==b['geometry_blobs_ordered_by_fid_sha256'],
        same_attributes=a['columns']==b['columns'] and a['attributes']==b['attributes'],
        same_feature_schema=a['column_schema']==b['column_schema'],
        same_geometry_declaration=a['geometry_metadata']==b['geometry_metadata'] and a['geometry_sql_type']==b['geometry_sql_type'],
        same_srs_definition=a['srs_definition']==b['srs_definition'],
        same_style_table=a['style_table']==b['style_table'],
        scope='File, full feature values (including FID), schema and SRS comparison only; no ArcGIS or new topology check')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--left', type=Path, required=True)
    ap.add_argument('--right', type=Path, required=True)
    ap.add_argument('--layer', required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--right-layer')
    ap.add_argument('--key-field')
    ap.add_argument('--key-value')
    args = ap.parse_args()
    if (args.key_field is None)!=(args.key_value is None): ap.error('--key-field and --key-value must be supplied together')
    if args.output.exists(): raise FileExistsError(args.output)
    result = compare(args.left, args.right, args.layer, args.right_layer, args.key_field, args.key_value)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k.startswith('same_')}, indent=2))


if __name__=='__main__':
    main()
