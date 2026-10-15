"""Read-only inventory of enclosed voids in the 19 coordinate-system zones.

No size cutoff, snapping, repair, or source writes. Exterior-connected water and
open slits cannot be distinguished from legal exterior boundaries by these
datasets alone; they are explicitly outside the exhaustive closed-void census.
"""
import argparse
import collections
import concurrent.futures
import csv
import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import pyogrio
from pyogrio.raw import read, write
import pyproj
import shapely
from shapely.ops import transform

from geometry_audit.common import area, holes, parts, hashfile
from build_zone_data import assign_zones
from zone_rules import load_rules


def log(*args):
    print(*args, flush=True)


def signature(g):
    return hashlib.sha256(shapely.to_wkb(shapely.normalize(g))).hexdigest()


def read_layer(path):
    layers = [name for name, geometry_type in pyogrio.list_layers(path) if geometry_type is not None]
    assert len(layers) == 1, (path, layers)
    meta, _, wkb, attrs = read(str(path), layer=layers[0])
    assert pyproj.CRS(meta['crs']) == pyproj.CRS.from_epsg(6668)
    geoms = shapely.from_wkb(wkb)
    assert bool(shapely.is_valid(geoms).all())
    assert not bool(shapely.is_empty(geoms).any())
    return geoms, dict(zip(meta['fields'], attrs))


def table(path, rows):
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=keys, lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def layer(path, name, features):
    if not features:
        return
    keys = list(features[0][1])
    arrays = [np.array([p[k] for _, p in features]) for k in keys]
    write(str(path), layer=name, driver='GPKG', crs='EPSG:6668',
          geometry=shapely.to_wkb([g for g, _ in features]),
          field_data=arrays, fields=keys, geometry_type='Unknown')


def local_coverage(g, geoms, tree):
    # Clip first: never dissolve all of Japan just to inspect one small hole.
    ids = [int(i) for i in tree.query(g, predicate='intersects')]
    clipped = [geoms[i].intersection(g) for i in ids]
    return shapely.union_all(clipped), ids


def covered_indices(geoms, tree, point):
    ids = tree.query(point)
    return ids[shapely.covers(np.asarray(geoms, dtype=object)[ids], point)]


def measure(g):
    p = g.representative_point()
    crs = pyproj.CRS.from_proj4(
        f'+proj=aeqd +lat_0={p.y} +lon_0={p.x} +ellps=GRS80 +units=m')
    metric = transform(pyproj.Transformer.from_crs(6668, crs, always_xy=True).transform, g)
    rect = metric.minimum_rotated_rectangle
    coords = list(rect.exterior.coords) if rect.geom_type == 'Polygon' else []
    edges = [float(np.linalg.norm(np.subtract(a, b))) for a, b in zip(coords, coords[1:])]
    length, width = (max(edges), min(edges)) if edges else (0., 0.)
    # P/2 and 2A/P are proxies, not a medial-axis length or minimum neck width.
    perimeter = metric.length
    return dict(longitude=p.x, latitude=p.y, area_m2=area(g),
                perimeter_m=perimeter, obb_length_m=length, obb_width_m=width,
                length_proxy_m=perimeter/2,
                width_proxy_m=2*metric.area/perimeter if perimeter else 0.,
                obb_aspect=length/width if width else 0.)


def classify_void(h, zones, zone_tree, source, source_tree, muni, muni_tree,
                  source_fields, muni_fields, source_zones, public_zones):
    zcov, zi = local_coverage(h, zones, zone_tree)
    scov, si = local_coverage(h, source, source_tree)
    mcov, mi = local_coverage(h, muni, muni_tree)
    # The enclosing ring can contain another island or a different zone.
    void = h.difference(zcov)
    source_inside = void.intersection(scov)
    municipality_inside = void.intersection(mcov)
    missing_source = void.difference(scov)
    missing_muni = void.difference(mcov)
    point = void.representative_point() if not void.is_empty else h.representative_point()
    source_point = covered_indices(source, source_tree, point)
    muni_point = covered_indices(muni, muni_tree, point)
    # Full-geometry evidence and original-feature point evidence are both retained.
    sa, ma = area(source_inside), area(municipality_inside)
    if void.is_empty:
        cause, reason = '未確定', '内部リングは公開領域で被覆される。空白ではない'
    elif sa == 0 and ma == 0 and not len(source_point) and not len(muni_point):
        cause, reason = '原典由来', '候補空白に原典・市町村版の面被覆なし。代表点も未被覆'
    elif sa > 0 and ma > 0 and len(source_point) and len(muni_point):
        cause, reason = '加工で発生', '原典・市町村版が被覆する領域が19系版で欠ける。補修の可否は別判断'
    else:
        cause, reason = '未確定', '面差分と代表点の整合または入力段階間の差を追加確認。演算残差を含み得る'
    touching_source = source_tree.query(h, predicate='intersects')
    touching_muni = muni_tree.query(h, predicate='intersects')
    adjacent_zones = sorted(set(int(source_zones[i]) for i in touching_source) |
                            set(int(public_zones[i]) for i in touching_muni))
    context = '系間・外周として維持' if len(adjacent_zones) > 1 else '同一系内部'
    covered_zones = sorted(set(int(public_zones[i]) for i in mi
                               if area(muni[i].intersection(h)) > 0))
    codes = sorted(set(str(source_fields['N03_007'][i]) for i in touching_source))
    names = sorted(set(str(source_fields['N03_001'][i]) +
                       str(source_fields['N03_004'][i] or '') +
                       str(source_fields['N03_005'][i] or '') for i in touching_source))
    decision = ('境界・他系の領域を維持' if context != '同一系内部' or covered_zones else
                '追加確認（湖面等の意味・所属）')
    return void, dict(cause=cause, evidence=reason, context=context,
        adjacent_zones=';'.join(map(str, adjacent_zones)),
        ring_covered_zones=';'.join(map(str, covered_zones)),
        adjacent_codes=';'.join(codes), adjacent_names=';'.join(names),
        source_inside_m2=sa, municipality_inside_m2=ma,
        source_void_m2=area(missing_source), municipality_void_m2=area(missing_muni),
        source_point_features=';'.join(str(int(i)) for i in source_point),
        municipality_point_features=';'.join(str(int(i)) for i in muni_point),
        decision=decision)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source-shp', type=Path, required=True)
    ap.add_argument('--municipalities', type=Path, required=True)
    ap.add_argument('--zones', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--workers', type=int, default=3)
    args = ap.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    start = time.time()
    paths = [*args.source_shp.parent.glob(args.source_shp.stem+'.*'), args.municipalities, args.zones]
    inputs = [dict(path=str(p.resolve()), bytes=p.stat().st_size, sha256=hashfile(p)) for p in paths]
    source, sf = read_layer(args.source_shp)
    muni, mf = read_layer(args.municipalities)
    zones, zf = read_layer(args.zones)
    public_zones = np.asarray(mf['ZONE'], dtype=int)
    zone_numbers = np.asarray(zf['ZONE'], dtype=int)
    assert sorted(zone_numbers.tolist()) == list(range(1, 20))
    rows = [{str(k): str(v[i]) if v[i] is not None else '' for k, v in sf.items()} for i in range(len(source))]
    source_zones = np.array(assign_zones(rows, shapely.bounds(source).tolist(), load_rules()))
    st, mt, zt = shapely.STRtree(source), shapely.STRtree(muni), shapely.STRtree(zones)
    shapely.prepare(muni)
    shapely.prepare(zones)
    log('loaded', len(source), len(muni), len(zones))
    # Reuse previous municipality comparison implementation as a separate check;
    # here compare exactly by ZONE, which was not covered by the earlier audit.
    comparisons, differences = [], []
    cache = out/'cache'
    cache.mkdir()
    def compare_zone(n):
        result, delta = [], []
        original = shapely.union_all(source[source_zones == n])
        municipal = shapely.union_all(muni[public_zones == n])
        published = zones[np.flatnonzero(zone_numbers == n)[0]]
        log('zone dissolved', n, 'elapsed', round(time.time()-start))
        for label, expected, actual in [('source_to_municipality_zone', original, municipal),
                                        ('municipality_to_zone', municipal, published)]:
            exact = bool(shapely.equals_exact(expected, actual, 0, normalize=True))
            lost, added = expected.difference(actual), actual.difference(expected)
            r = dict(zone=n, stage=label, normalized_exact=exact,
                     lost_empty=bool(lost.is_empty), added_empty=bool(added.is_empty),
                     lost_m2=area(lost), added_m2=area(added),
                     expected_holes=len(holes(expected)), actual_holes=len(holes(actual)))
            result.append(r)
            for direction, g in [('lost', lost), ('added', added)]:
                for j, p in enumerate(parts(g)):
                    if not p.is_empty:
                        point = p.representative_point()
                        delta.append((p, dict(zone=n, stage=label, direction=direction,
                            area_m2=area(p), source_point_count=len(covered_indices(source, st, point)),
                            municipality_point_count=len(covered_indices(muni, mt, point)),
                            zone_point_count=len(covered_indices(zones, zt, point)))))
        (cache/f'source-zone-{n:02d}.wkb').write_bytes(shapely.to_wkb(original))
        (cache/f'municipality-zone-{n:02d}.wkb').write_bytes(shapely.to_wkb(municipal))
        log('zone comparison', n, 'elapsed', round(time.time()-start))
        return result, delta
    assert 1 <= args.workers <= 4
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        tasks = [pool.submit(compare_zone, n) for n in range(1, 20)]
        for task in concurrent.futures.as_completed(tasks):
            result, delta = task.result()
            comparisons.extend(result)
            differences.extend(delta)
            comparisons.sort(key=lambda r: (r['zone'], r['stage']))
            table(out/'zone-comparison.csv', comparisons)
    # Interior rings of individual zones plus national union: the latter catches
    # enclosed cross-zone gaps that touch the exterior of each individual zone.
    raw = {}
    for n, g in zip(zone_numbers, zones):
        for h in holes(g):
            raw.setdefault(signature(h), [h, set(), set()])[1].add(int(n))
    national = shapely.union_all(zones)
    assert national.is_valid
    for h in holes(national):
        raw.setdefault(signature(h), [h, set(), set()])[2].add('national')
    log('enclosing rings', len(raw))
    candidates, features, rings = [], [], []
    for index, (sig, (h, owners, national_flag)) in enumerate(sorted(raw.items()), 1):
        cid = 'gap-'+sig[:16]
        void, evidence = classify_void(h, zones, zt, source, st, muni, mt, sf, mf, source_zones, public_zones)
        metric = measure(void if not void.is_empty else h)
        r = dict(candidate_id=cid, zone=';'.join(map(str, sorted(owners))),
                 national_ring=bool(national_flag), **metric, **evidence,
                 ring_area_m2=area(h), void_empty=bool(void.is_empty), geometry_sha256=sig)
        candidates.append(r)
        rings.append((h, dict(candidate_id=cid, zone=r['zone'], cause=r['cause'], context=r['context'])))
        if not void.is_empty:
            features.append((void, {k: int(v) if isinstance(v, bool) else v for k, v in r.items()}))
        if index % 25 == 0:
            log('classified', index, '/', len(raw))
    table(out/'candidates.csv', candidates)
    layer(out/'candidates.gpkg', 'void_candidates', features)
    layer(out/'candidates.gpkg', 'enclosing_rings', rings)
    layer(out/'candidates.gpkg', 'stage_differences', differences)
    # Copy as a review context layer; input GPKG remains untouched.
    layer(out/'candidates.gpkg', 'zone_reference', [(g, dict(zone=int(n))) for n, g in zip(zone_numbers, zones)])
    summary = dict(source_features=len(source), municipality_features=len(muni), zone_features=len(zones),
        candidates=len(candidates), void_candidates=len(features),
        cause_counts=dict(collections.Counter(r['cause'] for r in candidates)),
        context_counts=dict(collections.Counter(r['context'] for r in candidates)),
        area_ge_1=sum(r['area_m2'] >= 1 for r in candidates),
        elongated_ge_1=sum(r['area_m2'] >= 1 and r['obb_aspect'] >= 10 for r in candidates),
        difference_features=len(differences), inputs=inputs, elapsed_seconds=time.time()-start,
        versions=dict(python=sys.version, shapely=shapely.__version__, geos=shapely.geos_version_string,
                      pyproj=pyproj.__version__, pyogrio=pyogrio.__version__, numpy=np.__version__),
        scope='All closed interior void rings; no area cutoff. Open exterior-connected slits are not exhaustively detected.',
        metric='GRS80 ellipsoidal area; local AEQD minimum rotated rectangle; P/2 length and 2A/P mean-width proxies',
        display_only='Not assigned: requires matching rendered location/settings; no screenshot supplied',
        repair='None. No candidate is approved for repair by geometry alone.')
    db = sqlite3.connect((out/'candidates.gpkg').resolve().as_uri()+'?mode=ro', uri=True)
    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    db.close()
    for p in paths:
        assert hashfile(p) == next(r['sha256'] for r in inputs if r['path'] == str(p.resolve()))
    (out/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    log('SUMMARY', json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
