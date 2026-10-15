"""Read back audit artifacts and check input preservation and spatial evidence."""
import argparse
import csv
import json
import sqlite3
from pathlib import Path

import numpy as np
import pyogrio
from pyogrio.raw import read
import pyproj
import shapely

from geometry_audit.common import hashfile, holes, parts, ring_area
from audit_zone_gaps import covered_indices, read_layer, signature, table


def verify_package(path):
    connection = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)
    assert connection.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    connection.close()
    result = {}
    for name, kind in pyogrio.list_layers(path):
        if kind is None:
            continue
        m, _, wkb, _ = read(str(path), layer=name)
        assert pyproj.CRS(m['crs']) == pyproj.CRS.from_epsg(6668)
        g = shapely.from_wkb(wkb)
        assert bool(shapely.is_valid(g).all()), (path, name, 'invalid geometry')
        assert not bool(shapely.is_empty(g).any()), (path, name, 'empty geometry')
        assert bool(np.isfinite(shapely.get_coordinates(g)).all())
        result[name] = len(g)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--audit', type=Path, required=True)
    ap.add_argument('--exterior-screen', type=Path, required=True)
    ap.add_argument('--municipality-review', type=Path, required=True)
    args = ap.parse_args()
    summary = json.loads((args.audit/'summary.json').read_text())
    exterior = json.loads((args.exterior_screen/'summary.json').read_text())
    municipality = json.loads((args.municipality_review/'summary.json').read_text())
    assert municipality['compared'] == 1905 and municipality['errors'] == 0
    with (args.audit/'zone-comparison.csv').open() as f:
        comparisons = list(csv.DictReader(f))
    assert len(comparisons) == 38
    assert {int(r['zone']) for r in comparisons} == set(range(1,20))
    for item in summary['inputs']:
        assert hashfile(Path(item['path'])) == item['sha256'], item['path']
    layers = verify_package(args.audit/'candidates.gpkg')
    assert layers['void_candidates'] == summary['void_candidates']
    assert layers['enclosing_rings'] == summary['candidates']
    assert layers.get('stage_differences', 0) == summary['difference_features']
    assert layers['zone_reference'] == 19
    exterior_layers = verify_package(args.exterior_screen/'exterior-screen.gpkg')
    assert exterior_layers['connectors'] == exterior['candidates']
    m, _, wkb, attrs = read(str(args.audit/'candidates.gpkg'), layer='zone_reference')
    reference_fields = dict(zip(m['fields'], attrs))
    refs = dict(zip(reference_fields['zone'], shapely.from_wkb(wkb)))
    zone_path = next(Path(r['path']) for r in summary['inputs'] if Path(r['path']).name == 'plane_rectangular_zones_2026.gpkg')
    original, fields = read_layer(zone_path)
    for n, g in zip(fields['ZONE'], original):
        assert shapely.equals_exact(refs[int(n)], g, 0, normalize=True)
    exterior_rows = []
    for n, g in zip(fields['ZONE'], original):
        expected = shapely.from_wkb((args.audit/'cache'/f'municipality-zone-{int(n):02d}.wkb').read_bytes())
        expected_shells = sorted(signature(shapely.Polygon(p.exterior)) for p in parts(expected))
        actual_shells = sorted(signature(shapely.Polygon(p.exterior)) for p in parts(g))
        actual_holes = {signature(h) for h in holes(g)}
        expected_holes = {signature(h) for h in holes(expected)}
        removed = [h for h in holes(expected) if signature(h) not in actual_holes]
        exterior_rows.append(dict(zone=int(n), exteriors_exact=expected_shells == actual_shells,
            new_hole_signatures=len(actual_holes-expected_holes), removed_holes=len(removed),
            removed_threshold_max_m2=max([ring_area(h.exterior) for h in removed] or [0.]),
            all_removed_below_release_1m2=all(ring_area(h.exterior) < 1 for h in removed)))
    table(args.audit/'exterior-preservation.csv', exterior_rows)
    shapely.prepare(original)
    tree = shapely.STRtree(original)
    _, _, wkb, _ = read(str(args.audit/'candidates.gpkg'), layer='void_candidates')
    for g in shapely.from_wkb(wkb):
        assert not len(covered_indices(original, tree, g.representative_point()))
    outcome = dict(status='passed', input_hashes_unchanged=True,
        original_zone_reference_unchanged=True, zone_comparisons=38,
        municipality_comparisons=1905, audit_layers=layers, exterior_layers=exterior_layers,
        crs='EPSG:6668', sqlite_integrity='ok', invalid=0, empty=0,
        public_exteriors_exact_against_municipality_union=all(r['exteriors_exact'] for r in exterior_rows),
        removed_holes=sum(r['removed_holes'] for r in exterior_rows),
        new_hole_signatures=sum(r['new_hole_signatures'] for r in exterior_rows),
        removed_holes_all_below_release_threshold=all(r['all_removed_below_release_1m2'] for r in exterior_rows),
        note='Machine-readable validation; QGIS GUI was not run.')
    (args.audit/'artifact-validation.json').write_text(json.dumps(outcome, indent=2)+'\n')
    print(json.dumps(outcome, indent=2))


if __name__ == '__main__':
    main()
