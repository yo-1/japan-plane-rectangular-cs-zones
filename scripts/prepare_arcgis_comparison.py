"""Create typed comparison GeoPackages, preserving every feature value byte.

SQL geometry declarations and gpkg_geometry_columns use the actual geometry
type. Mixed-type layers split by type, retaining FIDs, columns and full geometry
BLOBs. Core SRS metadata is retained. Styling, auxiliary tables and spatial
indexes are outside this comparison copy. ArcGIS execution is still required.
"""
import argparse
import collections
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import struct

from geometry_audit.common import decode, hashfile
from validate_zone_gap_outputs import verify_package

TYPES={'Point','MultiPoint','LineString','MultiLineString','Polygon','MultiPolygon'}


def quote(name):
    return '"'+name.replace('"','""')+'"'


def row_hash(row):
    h=hashlib.sha256()
    for value in row:
        if value is None: kind,data=b'N',b''
        elif isinstance(value,bytes): kind,data=b'B',value
        elif isinstance(value,str): kind,data=b'S',value.encode('utf-8')
        elif isinstance(value,int): kind,data=b'I',str(value).encode('ascii')
        elif isinstance(value,float): kind,data=b'F',struct.pack('>d',value)
        else: raise TypeError(type(value))
        h.update(kind+struct.pack('>Q',len(data))+data)
    return h.hexdigest()


def fingerprint(rows):
    hashes=sorted(row_hash(row) for row in rows)
    return dict(count=len(hashes),all_columns_sha256=hashlib.sha256(''.join(hashes).encode('ascii')).hexdigest())


def typed_schema(sql, source_table, target_table, geom_column, old_type, new_type):
    name=lambda n: '(?:'+re.escape(quote(n))+'|'+re.escape(n)+')'
    pattern=r'^(CREATE\s+TABLE\s+)'+name(source_table)+r'(?=\s|\()'
    result,count=re.subn(pattern,lambda m:m[1]+quote(target_table),sql,count=1,flags=re.I)
    if count!=1: raise ValueError('Unsupported source table declaration')
    if re.search(r'\bREFERENCES\b',sql,re.I):
        raise ValueError('Feature foreign keys require a separate preservation strategy')
    pattern=r'([,(]\s*'+name(geom_column)+r'\s+)(?:'+re.escape(quote(old_type))+'|'+re.escape(old_type)+r')(?=\s|,|\))'
    result,count=re.subn(pattern,lambda m:m[1]+new_type,result,count=1,flags=re.I)
    if count!=1: raise ValueError('Unsupported geometry column declaration')
    return result


def prepare_file(source, destination):
    source=source.resolve();destination=destination.resolve()
    if destination.exists(): raise FileExistsError(destination)
    initial_hash=hashfile(source)
    src=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
    src.row_factory=sqlite3.Row
    plans=[];names=set()
    try:
        for meta in src.execute('SELECT * FROM gpkg_geometry_columns').fetchall():
            table,column=meta['table_name'],meta['column_name']
            info=src.execute('PRAGMA table_info('+quote(table)+')').fetchall()
            columns=[r['name'] for r in info];gindex=columns.index(column)
            old_type=info[gindex]['type']
            sql=src.execute('SELECT sql FROM sqlite_master WHERE type="table" AND name=?',(table,)).fetchone()[0]
            groups=collections.defaultdict(list);bounds={}
            for values in src.execute('SELECT * FROM '+quote(table)):
                row=tuple(values);blob=row[gindex]
                if blob is None: raise ValueError('NULL geometry requires explicit handling')
                srid,g=decode(blob)
                if srid!=meta['srs_id'] or not g.is_valid or g.is_empty:
                    raise ValueError('Invalid, empty or mismatched-SRS geometry')
                if g.geom_type not in TYPES or g.has_z or getattr(g,'has_m',False):
                    raise ValueError('Unsupported geometry type or dimension: '+g.geom_type)
                kind=g.geom_type.upper();groups[kind].append(row)
                b=g.bounds
                prev=bounds.get(kind,b)
                bounds[kind]=(min(prev[0],b[0]),min(prev[1],b[1]),max(prev[2],b[2]),max(prev[3],b[3]))
            if not groups: raise ValueError('Empty source layer: '+table)
            layers=[]
            for kind,rows in sorted(groups.items()):
                target=table if len(groups)==1 else table+'_'+kind.lower()
                if target in names: raise ValueError('Duplicate target layer: '+target)
                names.add(target)
                new_sql=typed_schema(sql,table,target,column,old_type,kind)
                layers.append(dict(table=target,kind=kind,rows=rows,bounds=bounds[kind],sql=new_sql))
            contents=src.execute('SELECT * FROM gpkg_contents WHERE table_name=?',(table,)).fetchone()
            plans.append(dict(table=table,column=column,columns=columns,sql=sql,meta=dict(meta),
                contents=dict(contents),before=fingerprint(row for rows in groups.values() for row in rows),layers=layers))
        if not plans: raise ValueError('No feature layers')
        dest=sqlite3.connect(destination)
        try:
            dest.execute('PRAGMA application_id=1196444487')
            dest.execute('PRAGMA user_version=10300')
            dest.execute('PRAGMA foreign_keys=ON')
            for name in ['gpkg_spatial_ref_sys','gpkg_contents','gpkg_geometry_columns']:
                ddl=src.execute('SELECT sql FROM sqlite_master WHERE name=?',(name,)).fetchone()[0]
                dest.execute(ddl)
            srs=src.execute('SELECT * FROM gpkg_spatial_ref_sys').fetchall()
            dest.executemany('INSERT INTO gpkg_spatial_ref_sys VALUES ('+','.join('?' for _ in srs[0])+')',srs)
            results=[]
            for p in plans:
                copied=[];layers=[]
                for layer in p['layers']:
                    dest.execute(layer['sql'])
                    dest.executemany('INSERT INTO '+quote(layer['table'])+' VALUES ('+','.join('?' for _ in p['columns'])+')',layer['rows'])
                    c=dict(p['contents']);c.update(table_name=layer['table'],identifier=layer['table'],
                        description=(c.get('description') or '')+' | Typed comparison copy from '+p['table'],
                        last_change=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ'))
                    c.update(zip(['min_x','min_y','max_x','max_y'],layer['bounds']))
                    dest.execute('INSERT INTO gpkg_contents ('+','.join(quote(k) for k in c)+') VALUES ('+','.join('?' for _ in c)+')',tuple(c.values()))
                    m=dict(p['meta']);m.update(table_name=layer['table'],geometry_type_name=layer['kind'])
                    dest.execute('INSERT INTO gpkg_geometry_columns ('+','.join(quote(k) for k in m)+') VALUES ('+','.join('?' for _ in m)+')',tuple(m.values()))
                    rows=dest.execute('SELECT * FROM '+quote(layer['table'])).fetchall()
                    before=fingerprint(layer['rows']);after=fingerprint(rows)
                    if before!=after: raise AssertionError('Feature values changed')
                    copied.extend(rows)
                    layers.append(dict(table=layer['table'],geometry_type=layer['kind'],before=before,after=after,sql=layer['sql']))
                after=fingerprint(copied)
                if p['before']!=after: raise AssertionError('Feature loss or duplication')
                results.append(dict(source_layer=p['table'],source_sql=p['sql'],source_geometry_metadata=p['meta'],
                    columns=p['columns'],before=p['before'],after=after,layers=layers))
            dest.commit()
            if dest.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise AssertionError('Integrity check failed')
            if dest.execute('PRAGMA foreign_key_check').fetchall():raise AssertionError('Foreign-key check failed')
            # Fingerprints must survive reopening the file as well.
        finally:dest.close()
        check=sqlite3.connect(destination.as_uri()+'?mode=ro',uri=True)
        try:
            for result in results:
                for layer in result['layers']:
                    actual=fingerprint(check.execute('SELECT * FROM '+quote(layer['table'])))
                    if actual!=layer['after']:raise AssertionError('Read-back mismatch')
            if check.execute('SELECT * FROM gpkg_spatial_ref_sys').fetchall()!=[tuple(r) for r in srs]:
                raise AssertionError('SRS metadata changed')
        finally:check.close()
        expected={layer['table']:layer['after']['count'] for result in results for layer in result['layers']}
        gdal_counts=verify_package(destination)
        if gdal_counts!=expected:raise AssertionError('GDAL layer/count mismatch')
        if hashfile(source)!=initial_hash:raise AssertionError('Source file changed')
        return dict(source=str(source),source_sha256=initial_hash,output=str(destination),
            output_sha256=hashfile(destination),tables=results,source_unchanged=True,
            all_feature_values_identical=True,geometry_blobs_identical=True,sqlite_integrity='ok',
            srs_metadata_identical=True,gdal_readback=gdal_counts,arcgis_status='not run')
    finally:src.close()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input',action='append',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    if len({p.name for p in args.input})!=len(args.input):raise ValueError('Input basenames must be unique')
    args.output.mkdir(parents=True,exist_ok=False)
    results=[]
    for src in args.input:
        dst=args.output/(src.stem+'-typed.gpkg')
        result=prepare_file(src,dst);results.append(result)
        print('verified',src.name,sum(r['before']['count'] for r in result['tables']),flush=True)
    report=dict(files=results,hash_algorithm='SHA-256 of sorted per-row hashes with explicit value types and length prefixes; includes raw geometry BLOB and FID',
        scope='Comparison copies only. SQL declarations, core geometry metadata, names and extents may change. All feature column values preserved. Mixed layers partition by actual type.',
        auxiliary_metadata='Core SRS and feature columns retained; styles, auxiliary tables and spatial indexes are not copied.',
        arcgis_status='Pending user execution; GDAL read-back is a separate check',repair='None')
    (args.output/'comparison-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
