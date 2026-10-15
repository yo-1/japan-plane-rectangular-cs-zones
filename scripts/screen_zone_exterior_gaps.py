"""Bounded screening of narrow exterior-connected gaps, without buffering.

Find vertex pairs within a stated chord-distance radius on GRS80 ECEF, excluding
nearby vertices along the same boundary. Check each connector midpoint against
the original zones. This is a vertex screen, not an exhaustive segment-gap test
and not permission to change exterior or inter-zone boundaries.
"""
import argparse
import csv
import json
from pathlib import Path

import numpy as np
import pyproj
from scipy.spatial import cKDTree
import shapely
from shapely.geometry import LineString, Point

from audit_zone_gaps import read_layer, layer, table
from geometry_audit.common import parts, hashfile


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--zones', type=Path, required=True)
    ap.add_argument('--source-shp', type=Path, required=True)
    ap.add_argument('--municipalities', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--radius-m', type=float, default=1.)
    ap.add_argument('--boundary-separation-m', type=float, default=20.)
    args = ap.parse_args()
    assert args.radius_m > 0 and args.boundary_separation_m > args.radius_m
    args.output.mkdir(parents=True, exist_ok=False)
    digest = hashfile(args.zones)
    zones, fields = read_layer(args.zones)
    ll, xyz, owner, ring, arc, ring_length = [], [], [], [], [], []
    ecef = pyproj.Transformer.from_crs(6668, '+proj=geocent +ellps=GRS80 +units=m', always_xy=True)
    rid = 0
    for n, g in zip(fields['ZONE'], zones):
        for p in parts(g):
            a = np.asarray(p.exterior.coords)
            x, y, z = ecef.transform(a[:, 0], a[:, 1], np.zeros(len(a)))
            b = np.column_stack([x, y, z])
            length = np.linalg.norm(np.diff(b, axis=0), axis=1)
            ll.append(a[:-1]);xyz.append(b[:-1])
            owner.append(np.full(len(a)-1, int(n), dtype=np.int16))
            ring.append(np.full(len(a)-1, rid, dtype=np.int32))
            arc.append(np.r_[0., np.cumsum(length)[:-1]])
            ring_length.append(length.sum());rid += 1
    ll, xyz, owner, ring, arc = [np.concatenate(v) for v in [ll, xyz, owner, ring, arc]]
    lengths = np.asarray(ring_length)
    print('exterior vertices', len(ll), 'rings', rid, flush=True)
    tree = cKDTree(xyz)
    candidates = []
    # query_pairs finds all vertex pairs within R; no arbitrary k-neighbour cap.
    pairs = tree.query_pairs(args.radius_m, output_type='ndarray')
    print('near pairs', len(pairs), flush=True)
    delta = np.abs(arc[pairs[:, 0]]-arc[pairs[:, 1]])
    same = ring[pairs[:, 0]] == ring[pairs[:, 1]]
    delta = np.minimum(delta, np.abs(lengths[ring[pairs[:, 0]]]-delta))
    keep = ~same | (delta >= args.boundary_separation_m)
    pairs = pairs[keep]
    widths = np.linalg.norm(xyz[pairs[:, 0]]-xyz[pairs[:, 1]], axis=1)
    # Coincident endpoints are shared point contacts, not a positive-width gap.
    pairs, widths = pairs[widths > 0], widths[widths > 0]
    midpoints = shapely.points((ll[pairs[:, 0]]+ll[pairs[:, 1]])/2)
    print('nonlocal noncoincident pairs', len(pairs), flush=True)
    shapely.prepare(zones)
    covered = np.zeros(len(pairs), dtype=bool)
    for g in zones:
        covered |= shapely.covers(g, midpoints)
    pairs, widths = pairs[~covered], widths[~covered]
    points = midpoints[~covered]
    point_counts = []
    for path in [args.source_shp, args.municipalities]:
        geoms, _ = read_layer(path)
        shapely.prepare(geoms)
        matches = shapely.STRtree(geoms).query(points)
        present = shapely.covers(geoms[matches[1]], points[matches[0]])
        point_counts.append(np.bincount(matches[0][present], minlength=len(points)))
    for i, ((a, b), width) in enumerate(zip(pairs, widths), 1):
        p = (ll[a]+ll[b])/2
        row = dict(candidate_id=f'exterior-{i:07d}', zone_a=int(owner[a]), zone_b=int(owner[b]),
                   longitude=float(p[0]), latitude=float(p[1]), connector_width_m=float(width),
                   area_m2='not defined: connector, not a closed void',
                   context='同一系の外周に接続' if owner[a] == owner[b] else '異なる系の間',
                   cause='未確定', decision='外周・系間境界を維持。補修対象にしない',
                   source_point_count=int(point_counts[0][i-1]),
                   municipality_point_count=int(point_counts[1][i-1]),
                   evidence='公開外周頂点間の非ゼロ距離、接続線の中点は全19系で未被覆')
        candidates.append((LineString([ll[a], ll[b]]), row))
    table(args.output/'exterior-screen.csv', [p for _, p in candidates])
    layer(args.output/'exterior-screen.gpkg', 'connectors', candidates)
    summary = dict(exterior_vertices=len(ll), exterior_rings=rid, vertex_radius_m=args.radius_m,
                   minimum_same_ring_boundary_separation_m=args.boundary_separation_m,
                   candidates=len(candidates),
                   same_zone=sum(p['zone_a'] == p['zone_b'] for _, p in candidates),
                   different_zone=sum(p['zone_a'] != p['zone_b'] for _, p in candidates),
                   midpoint_uncovered_in_source_and_municipality=int(np.sum((point_counts[0] == 0) & (point_counts[1] == 0))),
                   chord_width_counts=dict(zip(['(0,1um]', '(1um,1mm]', '(1mm,0.1m]', '(0.1m,radius]'],
                       [int(np.sum((widths > a) & (widths <= b))) for a,b in [(0,1e-6),(1e-6,.001),(.001,.1),(.1,args.radius_m)]])),
                   scope='All vertex pairs at radius, not all segment pairs. Midpoint evidence does not establish a full void polygon, its area, cause, or legal membership.',
                   input_sha256=digest, repair='None')
    assert hashfile(args.zones) == digest
    (args.output/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
