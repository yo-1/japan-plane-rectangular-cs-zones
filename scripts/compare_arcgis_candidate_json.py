"""Compare this audit's single-ring polygons with an Esri JSON export.

Read-only diagnostics; neither Esri validation nor a polygon repair algorithm.
Requires NumPy, Shapely >= 2 and pyproj (geometry-audit requirements).
"""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import struct

import numpy as np
import pyproj
import shapely
from shapely.geometry import Polygon
from shapely.ops import transform

XY_RESOLUTION = 1e-9
XY_TOLERANCE = 8.98315284119521e-9


def hashfile(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def decode_polygon(blob):
    if not isinstance(blob, bytes) or blob[:2] != b'GP' or len(blob) < 8:
        raise ValueError('Expected a GeoPackage geometry header')
    order = '<' if blob[3] & 1 else '>'
    if struct.unpack(order + 'i', blob[4:8])[0] != 6668:
        raise ValueError('Expected EPSG:6668 geometry')
    envelope = (blob[3] >> 1) & 7
    if envelope not in (0, 1, 2, 3, 4):
        raise ValueError('Unsupported GeoPackage envelope')
    offset = 8 + {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[envelope]
    geometry = shapely.from_wkb(blob[offset:])
    require_simple_polygon(geometry)
    return geometry


def require_simple_polygon(geometry):
    # Esri ring orientation/grouping needs a different parser for multi-ring data.
    if (geometry.geom_type != 'Polygon' or geometry.is_empty
            or len(geometry.interiors) or geometry.has_z
            or getattr(geometry, 'has_m', False)):
        raise ValueError('This audit supports nonempty, single-ring XY Polygons only')


def nearby_pairs(coords, tolerance):
    """Exclude closure and cyclic adjacency; do not simulate Esri clustering."""
    points = coords[:-1]
    found = []
    for i in range(len(points)):
        for j in np.flatnonzero(np.linalg.norm(points[i + 2:] - points[i], axis=1) <= tolerance) + i + 2:
            if i == 0 and j == len(points) - 1:
                continue
            distance = float(np.linalg.norm(points[j] - points[i]))
            found.append({'positions_zero_based': [i, int(j)], 'distance_degree': distance})
    return found


def local_geometry(source, exported):
    center = source.representative_point()
    crs = pyproj.CRS.from_proj4(
        f'+proj=laea +lat_0={center.y} +lon_0={center.x} +ellps=GRS80 +units=m')
    project = pyproj.Transformer.from_crs(6668, crs, always_xy=True).transform
    return transform(project, source), transform(project, exported)


def rectangle_width(geometry):
    corners = np.asarray(geometry.minimum_rotated_rectangle.exterior.coords)
    return float(min(np.linalg.norm(np.diff(corners, axis=0), axis=1)))


def compare_feature(row, feature):
    attributes = feature['attributes']
    rings = feature['geometry']['rings']
    if len(rings) != 1:
        raise ValueError('Esri multi-ring polygons need a separate parser')
    coords = np.asarray(rings[0], dtype=float)
    if (coords.ndim != 2 or coords.shape[1] != 2 or len(coords) < 4
            or not np.isfinite(coords).all() or not np.array_equal(coords[0], coords[-1])):
        raise ValueError('Expected finite, closed XY ring')
    exported = Polygon(coords)
    source = decode_polygon(row['geom'])
    require_simple_polygon(exported)
    original_coords = shapely.get_coordinates(source)
    same_count = original_coords.shape == coords.shape
    deltas = np.abs(original_coords - coords) if same_count else None
    local_source, local_exported = local_geometry(source, exported)
    grids = []
    for grid in (1e-10, XY_RESOLUTION, 1e-8):
        # In-memory diagnostic copy; it is never written as replacement data.
        rounded = shapely.set_precision(source, grid, mode='pointwise')
        grids.append({'grid_degree': grid, 'valid': bool(rounded.is_valid),
                      'validity': shapely.is_valid_reason(rounded),
                      'area_degree2': rounded.area})
    rounded_coords = shapely.get_coordinates(
        shapely.set_precision(source, XY_RESOLUTION, mode='pointwise'))
    geod = pyproj.Geod(ellps='GRS80')
    clearance = float(exported.minimum_clearance)
    return {
        'objectid': attributes['OBJECTID'], 'candidate_id': attributes['candidate_id'],
        'source_valid': bool(source.is_valid), 'json_valid': bool(exported.is_valid),
        'json_validity': shapely.is_valid_reason(exported),
        'source_coordinate_count': len(original_coords), 'json_coordinate_count': len(coords),
        'ordered_coordinate_max_delta_degree': float(deltas.max()) if same_count else None,
        'changed_coordinate_count': int(np.count_nonzero(np.any(deltas != 0, axis=1))) if same_count else None,
        'grid_1e9_to_json_max_delta_degree': float(np.max(np.abs(rounded_coords - coords))) if same_count else None,
        'json_minimum_clearance_degree': clearance,
        'clearance_over_xy_tolerance': clearance / XY_TOLERANCE,
        'nonadjacent_pairs_within_xy_tolerance': nearby_pairs(coords, XY_TOLERANCE),
        'source_nonadjacent_pairs_within_xy_tolerance': nearby_pairs(original_coords, XY_TOLERANCE),
        'source_area_m2_geodesic': abs(geod.geometry_area_perimeter(source)[0]),
        'json_area_m2_geodesic': abs(geod.geometry_area_perimeter(exported)[0]),
        'source_local_laea_area_m2': local_source.area,
        'json_local_laea_area_m2': local_exported.area,
        'source_local_laea_rectangle_width_m': rectangle_width(local_source),
        'json_local_laea_rectangle_width_m': rectangle_width(local_exported),
        'source_local_laea_centroid': [local_source.centroid.x, local_source.centroid.y],
        'attribute_mismatches': [key for key, value in row.items()
                                 if key not in ('fid', 'geom') and attributes.get(key) != value],
        'source_area_degree2': source.area, 'json_area_degree2': exported.area,
        'pointwise_grid_diagnostics': grids,
    }


def compare(json_input, gpkg_input):
    before = {str(path): hashfile(path) for path in (json_input, gpkg_input)}
    document = json.loads(Path(json_input).read_text(encoding='utf-8'))
    spatial_reference = document.get('spatialReference', {})
    if spatial_reference.get('latestWkid', spatial_reference.get('wkid')) != 6668:
        raise ValueError('Expected EPSG:6668 Esri JSON')
    with closing(sqlite3.connect(Path(gpkg_input).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        rows = list(db.execute('SELECT * FROM void_candidates ORDER BY fid'))
    source = {row['candidate_id']: dict(row) for row in rows}
    features = document['features']
    keys = [feature['attributes']['candidate_id'] for feature in features]
    objectids = [feature['attributes']['OBJECTID'] for feature in features]
    if len(source) != len(rows) or len(keys) != len(set(keys)) or set(source) != set(keys):
        raise ValueError('Missing, extra or duplicate candidate IDs')
    if len(set(objectids)) != len(objectids):
        raise ValueError('Duplicate OBJECTID')
    result = {
        'json_sha256': before[str(json_input)], 'gpkg_sha256': before[str(gpkg_input)],
        'spatialReference': spatial_reference, 'shapely': shapely.__version__,
        'geos': shapely.geos_version_string, 'pyproj': pyproj.__version__,
        'xy_resolution_degree': XY_RESOLUTION, 'xy_tolerance_degree': XY_TOLERANCE,
        'xy_settings_origin': 'User screenshot of output GDB; not read from JSON',
        'features': [compare_feature(source[feature['attributes']['candidate_id']], feature)
                     for feature in sorted(features, key=lambda item: item['attributes']['OBJECTID'])],
    }
    if any(hashfile(path) != digest for path, digest in before.items()):
        raise RuntimeError('An input changed during comparison')
    result['input_hashes_unchanged'] = True
    return result


def plot_comparison(json_input, gpkg_input, output):
    """Plot the four observed Esri failure IDs with deliberately unequal scales."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    document = json.loads(Path(json_input).read_text(encoding='utf-8'))
    with closing(sqlite3.connect(Path(gpkg_input).resolve().as_uri() + '?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        rows = {row['candidate_id']: dict(row) for row in db.execute('SELECT * FROM void_candidates')}
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), constrained_layout=True)
    selected = [feature for feature in document['features']
                if feature['attributes']['OBJECTID'] in (3, 6, 7, 11)]
    if len(selected) != 4:
        raise ValueError('Expected the four observed failure IDs for this figure')
    for axis, feature in zip(axes.flat, selected):
        source = decode_polygon(rows[feature['attributes']['candidate_id']]['geom'])
        exported = Polygon(feature['geometry']['rings'][0])
        source, exported = local_geometry(source, exported)
        coords = shapely.get_coordinates(source)
        edges = np.diff(coords, axis=0)
        along = edges[np.argmax(np.linalg.norm(edges, axis=1))]
        along /= np.linalg.norm(along)
        normal = np.array([-along[1], along[0]])
        center = coords[:-1].mean(axis=0)
        for geometry, label, color in ((source, 'Source GPKG', '#235789'),
                                       (exported, 'GDB JSON', '#d1495b')):
            points = shapely.get_coordinates(geometry) - center
            x, y = points @ along, points @ normal * 1000
            axis.plot(x, y, marker='o', markersize=4, label=label, color=color)
            axis.fill(x, y, alpha=.10, color=color)
        axis.set_title('OBJECTID ' + str(feature['attributes']['OBJECTID']))
        axis.set_xlabel('Along longest source edge (m)')
        axis.set_ylabel('Across edge (mm; exaggerated)')
        axis.grid(alpha=.25)
        axis.legend(fontsize=8)
    fig.suptitle('Source vs GDB coordinates: unequal axis units/scales\n'
                 'Diagnostic shapes, not locations reported by Esri')
    fig.savefig(output, dpi=170)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('json_input', type=Path)
    parser.add_argument('gpkg_input', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--figure', type=Path, help='Optional four-candidate diagnostic PNG')
    args = parser.parse_args()
    if args.figure and args.figure.exists():
        parser.error('Figure exists; use a new filename')
    if args.output.exists():
        parser.error('Output exists; use a new filename to preserve earlier results')
    result = compare(args.json_input, args.gpkg_input)
    if args.figure:
        args.figure.parent.mkdir(parents=True, exist_ok=True)
        plot_comparison(args.json_input, args.gpkg_input, args.figure)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(f"Compared {len(result['features'])} features; wrote {args.output}")


if __name__ == '__main__':
    main()
