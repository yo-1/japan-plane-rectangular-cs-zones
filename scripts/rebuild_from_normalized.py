# Rebuild the plane-rectangular zone products from the 9-digit-normalized admin source.
# Mirrors the forest v0.7 approach: attributes and grouping from the published v2026.2,
# geometry re-dissolved from normalized fragments so shared boundaries stay bit-identical.
import geopandas as gpd, pandas as pd, shapely, json, time, sqlite3, shutil, os
t0 = time.time()
FP = '/home/hatch/workspace/forest-planning-zones'
A = f'{FP}/plane-audit'
OUT = '/home/hatch/workspace/plane-zones-rebuild'
SRC = f'{FP}/v07-candidate/source_normalized.gpkg'
PUB_M = f'{A}/x_plane_rectangular_municipalities_2026/plane_rectangular_municipalities_2026.gpkg'
PUB_P = f'{A}/x_plane_rectangular_prefectures_2026/plane_rectangular_prefectures_2026.gpkg'
PUB_Z = f'{A}/x_plane_rectangular_zones_2026/plane_rectangular_zones_2026.gpkg'
log = {}

frag = gpd.read_file(SRC, layer='admin_fragments_2026_normalized9')
print('fragments', len(frag), flush=True)
table = pd.read_csv('/home/hatch/workspace/japan-plane-rectangular-cs-zones/data/municipality_zones.csv',
                    dtype={'code': str})
zones_of = {r.code: [int(z) for z in str(r.zones).split(';')] for r in table.itertuples()}
straddlers = {c: zs for c, zs in zones_of.items() if len(zs) > 1}
log['straddlers'] = straddlers
print('straddlers', straddlers, flush=True)

pub_z = gpd.read_file(PUB_Z, layer='plane_rectangular_zones_2026')
zone_geom = {int(r.ZONE): r.geometry for r in pub_z.itertuples()}

def assign(row):
    zs = zones_of[row.N03_007]
    if len(zs) == 1:
        return zs[0]
    pt = row.geometry.representative_point()
    for z in zs:
        if zone_geom[z].covers(pt):
            return z
    # fall back to the largest overlap
    best, best_area = None, -1.0
    for z in zs:
        a = row.geometry.intersection(zone_geom[z]).area
        if a > best_area:
            best, best_area = z, a
    return best

frag['ZONE'] = [assign(r) for r in frag.itertuples()]
assert frag['ZONE'].notna().all()
log['fragments'] = len(frag)

pieces = frag.dissolve(by=['N03_007', 'ZONE'], as_index=False)[['N03_007', 'ZONE', 'geometry']]
print('pieces', len(pieces), flush=True)

pub_m = gpd.read_file(PUB_M, layer='plane_rectangular_municipalities_2026')
pub_keys = set(zip(pub_m['N03_007'], pub_m['ZONE'].astype(int)))
new_keys = set(zip(pieces['N03_007'], pieces['ZONE'].astype(int)))
assert pub_keys == new_keys, (len(pub_keys), len(new_keys))
attrs = pub_m.drop(columns='geometry').copy()
attrs['ZONE'] = attrs['ZONE'].astype(int)
muni = attrs.merge(pieces, on=['N03_007', 'ZONE'], how='left', validate='one_to_one')
muni = gpd.GeoDataFrame(muni, geometry='geometry', crs=pub_m.crs)
assert len(muni) == len(pub_m) == 1911
muni.to_file(f'{OUT}/plane_rectangular_municipalities_2026.gpkg',
             layer='plane_rectangular_municipalities_2026', driver='GPKG')
log['municipalities'] = len(muni)
print('municipalities written', flush=True)

SPECIAL = {'北海道', '東京都', '鹿児島県', '沖縄県'}
def unit_of(r):
    if r.N03_001 in SPECIAL:
        name = r.N03_005 if isinstance(r.N03_005, str) and r.N03_005 else r.N03_004
        return r.N03_007, name
    return r.N03_007[:2] + '000', r.N03_001
units = [unit_of(r) for r in muni.itertuples()]
muni['UNIT_CODE'] = [u[0] for u in units]
muni['UNIT_NAME_DERIVED'] = [u[1] for u in units]
pref_pieces = muni.dissolve(by=['UNIT_CODE', 'ZONE'], as_index=False)[['UNIT_CODE', 'ZONE', 'geometry']]
pub_p = gpd.read_file(PUB_P, layer='plane_rectangular_prefectures_2026')
pp_keys = set(zip(pub_p['UNIT_CODE'], pub_p['ZONE'].astype(int)))
np_keys = set(zip(pref_pieces['UNIT_CODE'], pref_pieces['ZONE'].astype(int)))
assert pp_keys == np_keys, (len(pp_keys), len(np_keys), pp_keys ^ np_keys)
pattrs = pub_p.drop(columns='geometry').copy()
pattrs['ZONE'] = pattrs['ZONE'].astype(int)
pref = pattrs.merge(pref_pieces, on=['UNIT_CODE', 'ZONE'], how='left', validate='one_to_one')
pref = gpd.GeoDataFrame(pref, geometry='geometry', crs=pub_p.crs)
assert len(pref) == len(pub_p) == 392
pref.to_file(f'{OUT}/plane_rectangular_prefectures_2026.gpkg',
             layer='plane_rectangular_prefectures_2026', driver='GPKG')
log['prefectures'] = len(pref)
print('prefectures written', flush=True)

zone_pieces = muni.dissolve(by=['ZONE'], as_index=False)[['ZONE', 'geometry']]
zattrs = pub_z.drop(columns='geometry').copy()
zattrs['ZONE'] = zattrs['ZONE'].astype(int)
zones = zattrs.merge(zone_pieces, on='ZONE', how='left', validate='one_to_one')
zones = gpd.GeoDataFrame(zones, geometry='geometry', crs=pub_z.crs)
assert len(zones) == 19
zones.to_file(f'{OUT}/plane_rectangular_zones_2026.gpkg',
              layer='plane_rectangular_zones_2026', driver='GPKG')
log['zones'] = len(zones)
print('zones written', flush=True)

# carry over layer_styles from the published GPKGs
for new, pub in [(f'{OUT}/plane_rectangular_municipalities_2026.gpkg', PUB_M),
                 (f'{OUT}/plane_rectangular_prefectures_2026.gpkg', PUB_P),
                 (f'{OUT}/plane_rectangular_zones_2026.gpkg', PUB_Z)]:
    src = sqlite3.connect(pub)
    try:
        rows = src.execute('SELECT * FROM layer_styles').fetchall()
        cols = [d[0] for d in src.execute('SELECT * FROM layer_styles LIMIT 0').description]
    except sqlite3.OperationalError:
        rows = []
    src.close()
    if rows:
        dst = sqlite3.connect(new)
        dst.execute('ATTACH DATABASE ? AS pub', (pub,))
        dst.execute('CREATE TABLE IF NOT EXISTS layer_styles AS SELECT * FROM pub.layer_styles WHERE 0')
        dst.execute('INSERT INTO layer_styles SELECT * FROM pub.layer_styles')
        dst.commit(); dst.execute('DETACH DATABASE pub'); dst.close()
    print('styles copied', os.path.basename(new), len(rows), flush=True)

log['seconds'] = round(time.time() - t0, 1)
json.dump(log, open(f'{OUT}/build_log.json', 'w'), ensure_ascii=False, indent=1)
print('BUILD DONE', log['seconds'], flush=True)
