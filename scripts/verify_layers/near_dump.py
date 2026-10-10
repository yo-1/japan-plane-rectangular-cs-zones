"""別の地物の頂点との距離が1e-9〜5e-6度の頂点を書き出し、相手の辺までの距離で分類する。numpy/scipyのみ。
使い方: python3 -I scripts/verify_layers/near_dump.py <gpkg> <layer> <out.csv>"""
import sys, csv, numpy as np
import os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from load import load
from scipy.spatial import cKDTree
path, layer, out = sys.argv[1:4]; LO, HI = 1e-9, 5e-6
d = load(path, layer)
XY = np.concatenate([a[:-1] for a in d["coords"]])
F = np.concatenate([np.full(len(a) - 1, d["ring_feat"][i], np.int32) for i, a in enumerate(d["coords"])])
RS = np.concatenate([np.full(len(a) - 1, i, np.int32) for i, a in enumerate(d["coords"])])
start = np.cumsum([0] + [len(a) - 1 for a in d["coords"]])
t = cKDTree(XY); res = []
CH = 400000
def segd(p, a, b):
    ab = b - a; L = ab @ ab
    u = 0.0 if L == 0 else max(0.0, min(1.0, ((p - a) @ ab) / L)); return float(np.linalg.norm(p - (a + u * ab)))
for s in range(0, len(XY), CH):
    q = XY[s:s + CH]; dist, idx = t.query(q, k=6, distance_upper_bound=HI)
    ok = idx < len(XY); i2 = np.where(ok, idx, 0); diff = ok & (F[i2] != F[s:s + CH, None])
    dd = np.where(diff, dist, np.inf); j = dd.argmin(1); dm = dd[np.arange(len(q)), j]
    for qi in np.where((dm >= LO) & (dm < HI))[0]:
        gi = s + qi; w = int(idx[qi, j[qi]]); r = RS[w]; n = start[r + 1] - start[r]; loc = w - start[r]
        a0 = XY[start[r] + (loc - 1) % n]; a1 = XY[w]; a2 = XY[start[r] + (loc + 1) % n]
        sd = min(segd(XY[gi], a0, a1), segd(XY[gi], a1, a2))
        res.append((XY[gi, 0], XY[gi, 1], dm[qi], sd, int(d["feat_ids"][F[gi]]), int(d["feat_ids"][F[w]])))
with open(out, "w", newline="") as f:
    wr = csv.writer(f); wr.writerow(["lon", "lat", "vertex_dist_deg", "dist_to_other_segment_deg", "fid_a", "fid_b"]); wr.writerows(res)
print(layer, len(res), "points")
