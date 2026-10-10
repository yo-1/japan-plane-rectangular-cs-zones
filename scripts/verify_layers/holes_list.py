"""系ごと層の面積1m2以上の内部リング(=実在の穴)を、周囲の市町村名つきでCSVに出す。numpyのみ。
入力のgpkgは読み取り専用で開く。使い方: 環境変数 ZONES_GPKG / MUNI_GPKG に各gpkgのパスを入れて、
  python3 -I scripts/verify_layers/holes_list.py  → カレントに real_holes.csv (QGISで「区切りテキスト」から読める。lon/lat列)"""
import os, sys, sqlite3, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from load import load
ZONES = os.environ.get("ZONES_GPKG", "plane_rectangular_zones_2026.gpkg")
MUNI = os.environ.get("MUNI_GPKG", "plane_rectangular_municipalities_2026.gpkg")
R = 6371008.8
def area(a):
    lam = np.radians(a[:, 0]); sp = np.sin(np.radians(a[:, 1]))
    return abs(0.5 * R * R * np.sum((lam[1:] - lam[:-1]) * (sp[:-1] + sp[1:])))
def centroid(a):
    x, y = a[:-1, 0], a[:-1, 1]; x1, y1 = a[1:, 0], a[1:, 1]
    cr = x * y1 - x1 * y; A = cr.sum() / 2
    return ((x + x1) * cr).sum() / (6 * A), ((y + y1) * cr).sum() / (6 * A)
Z = load(ZONES, "plane_rectangular_zones_2026")
M = load(MUNI, "plane_rectangular_municipalities_2026")
c = sqlite3.connect(f"file:{MUNI}?mode=ro", uri=True)
names = {fid: (n1, n2, n3, n4, n5) for fid, n1, n2, n3, n4, n5 in c.execute(
    "select fid,N03_001,N03_002,N03_003,N03_004,N03_007 from plane_rectangular_municipalities_2026")}
# 市町村の頂点を丸めたキー(1e-9度)で索引
key = lambda a: np.round(a / 1e-9).astype(np.int64)
from collections import defaultdict
vx = defaultdict(set)
for ri, a in enumerate(M["coords"]):
    f = int(M["feat_ids"][M["ring_feat"][ri]])
    for k in map(tuple, key(a)): vx[k].add(f)
rows = []
for ri, a in enumerate(Z["coords"]):
    if Z["ring_idx"][ri] == 0: continue
    s = area(a)
    if s < 1: continue
    cnt = defaultdict(int)
    for k in map(tuple, key(a)):
        for f in vx.get(k, ()): cnt[f] += 1
    top = sorted(cnt.items(), key=lambda t: -t[1])[:4]
    nb = " / ".join(f"{names[f][0]}{''.join(x or '' for x in names[f][1:4])}({n}点)" for f, n in top)
    x, y = centroid(a)
    rows.append((s, x, y, a[:, 0].min(), a[:, 1].min(), a[:, 0].max(), a[:, 1].max(), len(a), nb))
rows.sort(reverse=True)
import csv
with open("real_holes.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["no", "area_m2", "lon", "lat", "xmin", "ymin", "xmax", "ymax", "vertices", "neighbor_municipalities(共有頂点数)", "qgis_wkt_point"])
    for i, r in enumerate(rows, 1):
        w.writerow([i, f"{r[0]:.1f}", f"{r[1]:.6f}", f"{r[2]:.6f}", *[f"{v:.6f}" for v in r[3:7]], r[7], r[8], f"POINT({r[1]:.6f} {r[2]:.6f})"])
for i, r in enumerate(rows, 1): print(i, f"{r[0]:.1f}", f"({r[1]:.5f},{r[2]:.5f})", r[7], r[8])
