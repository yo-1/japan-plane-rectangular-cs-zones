"""Quantify two N03 holes against GSI experimental vector water/coast layers.

This compares dataset encodings at different editions, not legal jurisdiction
or observed water at a known tide. No alignment, snapping, or repair is applied.
"""
import argparse
from datetime import datetime
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo

import mapbox_vector_tile
import numpy as np
import pyproj
from pyogrio.raw import read
import shapely
from shapely.geometry import shape
from shapely.ops import transform
from audit_zone_gaps import table, layer


def tile_to_mercator(x,y,z,extent):
    half=math.pi*6378137.;width=2*half/(2**z)
    def project(a,b,c=None):
        return (-half+(x+np.asarray(a)/extent)*width,
                 half-(y+np.asarray(b)/extent)*width)
    return project


def fetch(url,path):
    assert not path.exists(),path
    subprocess.run(['curl','-fLsS','--retry','1','--max-time','45',url,'-o',str(path)],check=True)
    return dict(url=url,file=path.name,sha256=hashlib.file_digest(path.open('rb'),'sha256').hexdigest(),
                retrieved_jst=datetime.now(ZoneInfo('Asia/Tokyo')).isoformat())


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--evidence',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    sources=[('https://maps.gsi.go.jp/help/pdf/vector/dataspec.pdf','dataspec.pdf'),
             ('https://maps.gsi.go.jp/help/pdf/vector/attribute.pdf','attribute.pdf'),
             ('https://raw.githubusercontent.com/gsi-cyberjapan/gsimaps-vector-experiment/master/README.md','gsi-vector-readme.md'),
             ('https://gsi-cyberjapan.github.io/gsivectortile-mapbox-gl-js/std.json','gsi-vector-style.json')]
    manifest=[fetch(u,args.output/n) for u,n in sources]
    m,_,w,a=read(str(args.evidence/'source-ring-evidence.gpkg'),layer='evidence')
    attrs=dict(zip(m['fields'],a));rows=[];features=[]
    mercator=pyproj.Transformer.from_crs(6668,3857,always_xy=True).transform
    for cid,role,h in zip(attrs['candidate_id'],attrs['role'],shapely.from_wkb(w)):
        if role!='source_hole':continue
        p=h.representative_point();z=16;n=2**z;x=int((p.x+180)/360*n);y=int((1-math.asinh(math.tan(math.radians(p.y)))/math.pi)/2*n)
        name=f'{cid}-{z}-{x}-{y}.pbf';url=f'https://cyberjapandata.gsi.go.jp/xyz/experimental_bvmap/{z}/{x}/{y}.pbf'
        manifest.append(fetch(url,args.output/name))
        d=mapbox_vector_tile.decode((args.output/name).read_bytes(),default_options={'y_coord_down':True})
        crs=f'+proj=aeqd +lat_0={p.y} +lon_0={p.x} +ellps=GRS80 +units=m'
        to_local=pyproj.Transformer.from_crs(3857,crs,always_xy=True).transform
        from_local=pyproj.Transformer.from_crs(crs,6668,always_xy=True).transform
        hm=transform(to_local,transform(mercator,h))
        water=[];coast=[]
        for lname,record in d.items():
            if lname not in ['waterarea','coastline']:continue
            project=tile_to_mercator(x,y,z,record['extent'])
            for feat in record['features']:
                g=transform(to_local,transform(project,shape(feat['geometry'])))
                if lname=='waterarea' and feat['properties'].get('ftCode')==5000:
                    assert g.is_valid
                    water.append(g)
                if lname=='coastline' and feat['properties'].get('ftCode')==5102:coast.append(g)
        assert water and coast
        wa=shapely.union_all(water);cl=shapely.union_all(coast)
        inside=hm.intersection(wa);outside=hm.difference(wa)
        # A dense sample limits claims about the maximum distance. Distance to
        # a fixed set is 1-Lipschitz, so +0.125m bounds gaps between 0.25m samples.
        boundary=shapely.segmentize(hm.boundary,.25)
        sample=shapely.points(shapely.get_coordinates(boundary))
        distances=shapely.distance(sample,cl)
        r=dict(candidate_id=cid,vector_zoom=z,tile_x=x,tile_y=y,
               waterarea_ftCode=5000,coastline_ftCode=5102,point_in_waterarea=bool(wa.covers(hm.representative_point())),
               local_candidate_area_m2=hm.area,local_water_overlap_m2=inside.area,
               water_fraction=inside.area/hm.area,outside_water_m2=outside.area,
               boundary_sample_spacing_max_m=.25,boundary_samples=len(sample),
               coast_nearest_sample_median_m=float(np.median(distances)),
               coast_nearest_sample_max_m=float(np.max(distances)),
               coast_distance_conservative_upper_bound_m=float(np.max(distances)+.125),
               interpretation='水域面との整合あり。境界細部・法的所属・潮位条件は未確定',
               decision='原典の内環を維持。補修しない')
        rows.append(r)
        for label,g in [('N03_hole',hm),('GSI_water_intersection',inside),('outside_GSI_water',outside)]:
            if not g.is_empty:features.append((transform(from_local,g),dict(candidate_id=cid,role=label)))
    table(args.output/'vector-context.csv',rows)
    layer(args.output/'vector-context.gpkg','context',features)
    result=dict(results=rows,sources=manifest,versions=dict(mapbox_vector_tile=importlib.metadata.version('mapbox-vector-tile')),
        source='国土地理院ベクトルタイル提供実験',
        caution='N03 January edition versus vector edition. Shared upstream GSI sources; not independent ground survey. Fractions are not legal ownership or water confidence probabilities.',
        repair='None')
    (args.output/'vector-context.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(rows,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
