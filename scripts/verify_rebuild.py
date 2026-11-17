# Verify the rebuilt plane-zone products against the published v2026.2.
import geopandas as gpd, shapely, numpy as np, json, hashlib
FP = '/home/hatch/workspace/forest-planning-zones'
A = f'{FP}/plane-audit'; OUT = '/home/hatch/workspace/plane-zones-rebuild'
PRODUCTS = [
 ('municipalities', f'{A}/x_plane_rectangular_municipalities_2026/plane_rectangular_municipalities_2026.gpkg',
  f'{OUT}/plane_rectangular_municipalities_2026.gpkg', 'plane_rectangular_municipalities_2026', ['N03_007', 'ZONE']),
 ('prefectures', f'{A}/x_plane_rectangular_prefectures_2026/plane_rectangular_prefectures_2026.gpkg',
  f'{OUT}/plane_rectangular_prefectures_2026.gpkg', 'plane_rectangular_prefectures_2026', ['UNIT_CODE', 'ZONE']),
 ('zones', f'{A}/x_plane_rectangular_zones_2026/plane_rectangular_zones_2026.gpkg',
  f'{OUT}/plane_rectangular_zones_2026.gpkg', 'plane_rectangular_zones_2026', ['ZONE'])]
res = {}
for name, pub_p, new_p, layer, keys in PRODUCTS:
    pub = gpd.read_file(pub_p, layer=layer)
    new = gpd.read_file(new_p, layer=layer)
    r = {'pub_features': len(pub), 'new_features': len(new)}
    # attributes keyed comparison
    pk = pub.drop(columns='geometry').copy(); nk = new.drop(columns='geometry').copy()
    for df in (pk, nk):
        for c in df.columns:
            if df[c].dtype.kind in 'if':
                df[c] = df[c].astype('Int64')
    pk = pk.sort_values(keys).reset_index(drop=True); nk = nk.sort_values(keys).reset_index(drop=True)
    r['attributes_identical'] = bool(pk.astype(str).equals(nk.astype(str)))
    # grid audit on the new product
    coords = shapely.get_coordinates(new.geometry.values)
    scaled = coords * 1e9
    off = np.abs(scaled - np.round(scaled)) > 1e-6
    r['new_vertices'] = int(len(coords)); r['new_offgrid_pct'] = round(100 * float(off.any(axis=1).mean()), 4)
    r['new_invalid'] = int((~shapely.is_valid(new.geometry.values)).sum())
    r['new_empty'] = int(shapely.is_empty(new.geometry.values).sum())
    # area + symmetric difference per key (EPSG:6933)
    pub = pub.set_index(keys); new = new.set_index(keys)
    assert set(pub.index) == set(new.index)
    pub_m = pub.to_crs(6933); new_m = new.to_crs(6933)
    deltas = []; sym = 0.0
    for k in pub_m.index:
        a1 = pub_m.geometry.loc[k]; a2 = new_m.geometry.loc[k]
        deltas.append(a2.area - a1.area)
        sym += a1.symmetric_difference(a2).area
    deltas = np.array(deltas)
    r['area_delta_total_m2'] = round(float(deltas.sum()), 3)
    r['area_delta_max_abs_m2'] = round(float(np.abs(deltas).max()), 3)
    r['symdiff_total_m2'] = round(float(sym), 3)
    res[name] = r
    print(name, json.dumps(r, ensure_ascii=False), flush=True)
    if name == 'zones':
        # pairwise overlaps among new zones
        ov = []
        geoms = list(new.geometry.values)
        for i in range(len(geoms)):
            for j in range(i + 1, len(geoms)):
                a = geoms[i].intersection(geoms[j]).area
                if a > 0:
                    ov.append([int(new.index[i]), int(new.index[j]), a])
        res['zones_overlap_pairs_deg2'] = ov
        print('zone overlaps (deg2):', ov, flush=True)
json.dump(res, open(f'{OUT}/verify_results.json', 'w'), ensure_ascii=False, indent=1)
print('VERIFY DONE')
