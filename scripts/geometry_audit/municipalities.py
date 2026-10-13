"""Replay N03 municipality audit only, retaining previous public audit outputs.

No repair, snapping, buffering or rounding. All split coordinate-zone features
are reunited by N03_007 for the source comparison.
"""
import argparse
import collections
import hashlib
import json
import time
from pathlib import Path
import numpy as np
import pyogrio
from pyogrio.raw import read
import pyproj
import shapely
from shapely.geometry import shape
from .common import Audit, load, holes, area, parts, hashfile


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source-shp',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--municipalities',type=Path,required=True);ap.add_argument('--codes');ap.add_argument('--points-json',type=Path)
    args=ap.parse_args();out=args.output.resolve();out.mkdir(exist_ok=False);start=time.time()
    source=args.source_shp.resolve();meta,_,wkb,attrs=read(str(source));assert pyproj.CRS(meta['crs'])==pyproj.CRS.from_epsg(6668)
    fields=dict(zip(meta['fields'],attrs));source_geoms=shapely.from_wkb(wkb);assert bool(shapely.is_valid(source_geoms).all()) and not bool(shapely.is_empty(source_geoms).any())
    sg=collections.defaultdict(list)
    for i,c in enumerate(fields['N03_007']):
        assert c is not None and len(str(c))==5
        sg[str(c)].append(i)
    original=args.municipalities.resolve()
    public=load(original)['plane_rectangular_municipalities_2026'];pg=collections.defaultdict(list)
    for r in public:pg[str(r['N03_007'])].append(r['geometry'])
    assert set(sg)==set(pg),(sorted(set(sg)-set(pg)),sorted(set(pg)-set(sg)))
    audit=Audit(out);hole_rows=[];differences=[]
    selected=sorted(sg) if not args.codes else sorted(set(args.codes.split(',')))
    assert set(selected).issubset(sg)
    for i,c in enumerate(selected,1):
        expected=shapely.union_all(source_geoms[sg[c]]);actual=shapely.union_all(pg[c])
        assert expected.is_valid and actual.is_valid
        r=audit.compare('N03_to_public_municipality',c,expected,actual,force_overlay=True)
        r.update(source_features=len(sg[c]),public_split_features=len(pg[c]),prefecture=str(fields['N03_001'][sg[c][0]]),municipality=str(fields['N03_004'][sg[c][0]]))
        if not(r['lost_empty'] and r['added_empty']):differences.append(c)
        for version,g in [('N03',expected),('public_municipality',actual)]:
            for h in holes(g):hole_rows.append(dict(code=c,version=version,area_m2=area(h)))
        if i%25==0:
            (out/'checkpoint.json').write_text(json.dumps(audit.rows,ensure_ascii=False)+'\n')
            print('compared',i,'of',len(sg),'differences',differences,'elapsed',round(time.time()-start),flush=True)
    # Test known forest difference representatives directly against original
    # N03 features, without dissolving; do not infer polygon coverage from points.
    tree=shapely.STRtree(source_geoms);sample_rows=[]
    prior=json.loads(args.points_json.read_text()) if args.points_json else {'samples':[]}
    for row in prior['samples']:
        p=shapely.Point(row['longitude'],row['latitude'])
        candidates=[int(j) for j in tree.query(p)]
        sample_rows.append(dict(**row,N03_feature_ids_covering_point=[j for j in candidates if source_geoms[j].covers(p)],N03_codes_covering_point=sorted({str(fields['N03_007'][j]) for j in candidates if source_geoms[j].covers(p)})))
    source_difference_points=[]
    for g,p in audit.features:
        if not list(parts(g)):continue
        for component in parts(g):
            if component.is_empty:continue
            point=component.representative_point()
            if point.is_empty:continue
            code=p['key'];candidates=[int(j) for j in tree.query(point)]
            source_difference_points.append(dict(**p,component_m2=area(component),longitude=point.x,latitude=point.y,N03_feature_ids_covering_point=[j for j in candidates if source_geoms[j].covers(point)],public_features_covering_point=[r['fid'] for r in public if r['geometry'].covers(point)]))
    summary=dict(selected_codes=selected,normalized_exact=sum(r['normalized_exact'] for r in audit.rows),source_count=len(source_geoms),public_count=len(public),source_codes=len(sg),public_codes=len(pg),source_crs=meta['crs'],public_crs='EPSG:6668',source_invalid=0,public_invalid=0,source_only_codes=[],public_only_codes=[],compared=len(audit.rows),exact_empty=sum(r['lost_empty'] and r['added_empty'] for r in audit.rows),different_codes=differences,errors=0,lost_m2=sum(r['lost_m2'] for r in audit.rows),added_m2=sum(r['added_m2'] for r in audit.rows),source_holes=sum(r['expected_holes'] for r in audit.rows),public_holes=sum(r['actual_holes'] for r in audit.rows),tolerance={'coordinate':0,'area_pass_threshold':None,'policy':'No rounding, snapping, buffering, repair or difference suppression'},area_metric='GRS80 ellipsoidal area',versions=dict(shapely=shapely.__version__,geos=shapely.geos_version_string,pyogrio=pyogrio.__version__,gdal=pyogrio.__gdal_version_string__,pyproj=pyproj.__version__,numpy=np.__version__),inputs=[dict(path=str(p),bytes=p.stat().st_size,sha256=hashfile(p)) for p in source.parent.glob(source.stem+'.*') if p.is_file()]+[dict(path=str(original),bytes=original.stat().st_size,sha256=hashfile(original))],elapsed_seconds=time.time()-start)
    audit.write(summary,original)
    (out/'hole-inventory.json').write_text(json.dumps(hole_rows,indent=2)+'\n')
    (out/'forest-sample-source-point-evidence.json').write_text(json.dumps(sample_rows,ensure_ascii=False,indent=2)+'\n')
    (out/'source-difference-point-evidence.json').write_text(json.dumps(source_difference_points,ensure_ascii=False,indent=2)+'\n')
    print('SUMMARY',json.dumps(summary,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
