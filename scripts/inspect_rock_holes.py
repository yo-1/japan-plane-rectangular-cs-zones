"""Trace two unresolved rock-adjacent voids to raw SHP and GML ring roles.

No repair or coordinate changes. GML coordinates are B,L (lat,lon), while
SHP and the audit use lon,lat. GML's rounded coordinates are compared in a
local metric CRS; matching does not assert legal ownership or physical meaning.
"""
import argparse
import collections
import io
import json
from pathlib import Path
import struct
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
import pyproj
import shapely
from pyogrio.raw import read
from shapely.ops import transform

from audit_zone_gaps import read_layer, signature, layer
from geometry_audit.common import holes, parts, hashfile, area

TARGETS = ['gap-9795735d3cabea7c', 'gap-bfb40440ce6f5ac1']
GML = '{http://www.opengis.net/gml/3.2}'
XLINK = '{http://www.w3.org/1999/xlink}'


def raw_rings(path, index):
    with path.with_suffix('.shx').open('rb') as f:
        f.seek(100 + index*8)
        offset, length = struct.unpack('>2i', f.read(8))
    with path.open('rb') as f:
        f.seek(offset*2)
        number, actual_length = struct.unpack('>2i', f.read(8))
        assert actual_length == length and number == index+1
        data = f.read(length*2)
    assert struct.unpack_from('<i', data)[0] == 5
    count, points = struct.unpack_from('<2i', data, 36)
    starts = list(struct.unpack_from('<'+'i'*count, data, 44)) + [points]
    xy = np.frombuffer(data, dtype='<f8', count=points*2, offset=44+count*4).reshape(-1,2)
    return [xy[a:b].copy() for a,b in zip(starts,starts[1:])]


def signed_area(xy):
    a = np.asarray(xy, dtype=float) - xy[0]
    return float(np.sum(a[:-1,0]*a[1:,1] - a[1:,0]*a[:-1,1])/2)


def inspect_gml(stream, targets, max_distance_m=.01):
    """Stream all top-level XML members; retain only matching small curves."""
    found, surfaces, features = [], [], []
    transforms = {}
    for cid, g in targets.items():
        p = g.representative_point()
        crs = f'+proj=aeqd +lat_0={p.y} +lon_0={p.x} +ellps=GRS80 +units=m'
        transforms[cid] = pyproj.Transformer.from_crs(6668, crs, always_xy=True).transform
    root = None
    depth = 0
    curves_checked = 0
    for event, el in ET.iterparse(stream, events=('start','end')):
        if event == 'start':
            depth += 1
            if root is None: root = el
            continue
        if el.tag == GML+'Curve':
            curves_checked += 1
            pos = el.find('.//'+GML+'posList')
            if pos is not None and pos.text:
                a = np.fromstring(pos.text, sep=' ').reshape(-1,2)[:,::-1]
                if len(a) >= 4:
                    bounds = np.r_[a.min(0),a.max(0)]
                    for cid, g in targets.items():
                        if np.max(np.abs(bounds-np.asarray(g.bounds))) > 1e-5:
                            continue
                        ring = shapely.Polygon(a)
                        if not ring.is_valid: continue
                        project = transforms[cid]
                        distance = float(transform(project,ring).hausdorff_distance(transform(project,g)))
                        if distance <= max_distance_m:
                            found.append(dict(candidate_id=cid, curve_id=el.attrib.get(GML+'id'),
                                coordinates_lon_lat=a.tolist(), coordinate_count=len(a),
                                hausdorff_m=distance, normalized_exact=bool(shapely.equals_exact(ring,g,0,normalize=True))))
        elif el.tag == GML+'Surface':
            ids = {r['curve_id'] for r in found}
            references = []
            for role in ['exterior','interior']:
                for ring in el.findall('.//'+GML+role):
                    for member in ring.iter(GML+'curveMember'):
                        href=member.attrib.get(XLINK+'href','')
                        # Preserve original href. The producer uses #_cv... for
                        # Curve ids cv...; this is not a schema-validity claim.
                        if href.lstrip('#_') in ids:
                            references.append(dict(role=role,href=href,matched_curve_id=href.lstrip('#_')))
            if references:
                surfaces.append(dict(surface_id=el.attrib.get(GML+'id'),references=references))
        elif el.tag.split('}')[-1] == 'AdministrativeBoundary':
            surface_ids={r['surface_id'] for r in surfaces}
            refs=[v for c in el.iter() for k,v in c.attrib.items() if k == XLINK+'href']
            if any(v.lstrip('#_') in surface_ids for v in refs):
                features.append(dict(feature_id=el.attrib.get(GML+'id'),
                    properties={c.tag.split('}')[-1]:c.text for c in el if c.text and c.text.strip()},
                    surface_hrefs=refs,xml=ET.tostring(el,encoding='unicode')))
        if depth == 2:
            el.clear()
            root.clear()
        depth -= 1
    return dict(curves_checked=curves_checked, curves=found, surfaces=surfaces, features=features,
                max_match_hausdorff_m=max_distance_m,
                href_note='Original producer href strings preserved; #_ prefix normalized only for cross-reference lookup.')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source-shp',type=Path,required=True)
    ap.add_argument('--source-zip',type=Path,required=True)
    ap.add_argument('--audit',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    inputs=[args.source_zip,*args.source_shp.parent.glob(args.source_shp.stem+'.*')]
    manifest=[dict(path=str(p.resolve()),sha256=hashfile(p)) for p in inputs]
    source,fields=read_layer(args.source_shp);tree=shapely.STRtree(source)
    m,_,w,a=read(str(args.audit/'candidates.gpkg'),layer='void_candidates')
    attrs=dict(zip(m['fields'],a));targets={c:g for c,g in zip(attrs['candidate_id'],shapely.from_wkb(w)) if c in TARGETS}
    assert set(targets)==set(TARGETS)
    dbf=args.source_shp.with_suffix('.dbf').read_bytes()
    row_count,header_length,record_length=struct.unpack_from('<IHH',dbf,4)
    flags=collections.Counter(dbf[header_length:header_length+row_count*record_length:record_length])
    assert flags.get(42,0)==0, 'Deleted DBF rows require explicit SHP/FID mapping'
    findings=[];spatial=[]
    for cid,h in targets.items():
        matches=[]
        for i in tree.query(h):
            i=int(i)
            for part_number,p in enumerate(parts(source[i])):
                for hole_number,ring in enumerate(p.interiors):
                    if signature(shapely.Polygon(ring)) != signature(h):continue
                    raw=raw_rings(args.source_shp,i)
                    rings=[(j,xy) for j,xy in enumerate(raw) if signature(shapely.Polygon(xy))==signature(h)]
                    assert len(rings)==1
                    j,xy=rings[0]
                    parent=shapely.Polygon(p.exterior)
                    matches.append(dict(source_record_zero_based=i,shp_record_one_based=i+1,
                        dbf_deleted=False,attributes={k:str(v[i]) if v[i] is not None else '' for k,v in fields.items()},
                        polygon_part_zero_based=part_number,hole_zero_based=hole_number,raw_ring_zero_based=j,
                        raw_ring_signed_area_deg2=signed_area(xy),raw_ring_orientation='CCW' if signed_area(xy)>0 else 'CW',
                        raw_hole_coords_lon_lat=xy.tolist(),source_geometry_area_m2=area(source[i]),
                        parent_exterior_bounds=list(parent.bounds),hole_bounds=list(h.bounds),
                        hole_interior_covered_by_any_source=bool(len(tree.query(h.representative_point(),predicate='covered_by')))))
                    spatial.append((source[i],dict(candidate_id=cid,role='source_feature',source_record=i,code=str(fields['N03_007'][i]))))
                    spatial.append((h,dict(candidate_id=cid,role='source_hole',source_record=i,code=str(fields['N03_007'][i]))))
        assert len(matches)==1,(cid,matches)
        findings.append(dict(candidate_id=cid,matches=matches))
    with zipfile.ZipFile(args.source_zip) as z:
        entry=z.getinfo('N03-20260101.xml')
        with z.open(entry) as f:gml=inspect_gml(f,targets)
        for r in gml['curves']:
            cid=r['candidate_id'];g=shapely.Polygon(r['coordinates_lon_lat'])
            spatial.append((g,dict(candidate_id=cid,role='GML_curve_polygon',source_record=-1,code='')))
        gml['zip_member']=entry.filename;gml['uncompressed_bytes']=entry.file_size
        # XML hashed independently of archive compression; repeatable input identity.
        import hashlib
        with z.open(entry) as f:gml['member_sha256']=hashlib.file_digest(f,'sha256').hexdigest()
    assert {r['candidate_id'] for r in gml['curves']}==set(TARGETS)
    layer(args.output/'source-ring-evidence.gpkg','evidence',spatial)
    result=dict(findings=findings,gml=gml,dbf_rows=row_count,dbf_flag_counts={str(k):v for k,v in flags.items()},
                inputs=manifest,repair='None',legal_membership='Not inferred from surrounding feature attributes')
    for item in manifest:assert hashfile(Path(item['path']))==item['sha256']
    (args.output/'source-ring-evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(candidates=len(findings),gml_curves=len(gml['curves']),surfaces=gml['surfaces'],features=gml['features']),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
