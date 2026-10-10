"""内部リング(穴)≧1㎡ごとに、穴の中の標本点のうち、同じレイヤの地物で覆われていない割合を調べる。
覆われていない=実在の穴(水面・未割当など)。覆われている=別の地物が埋める飛び地(穴ではあるが隙間ではない)。"""
import os
import numpy as np, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from load import load
R = 6371008.8; NS = 120; rng = np.random.default_rng(1)
path, layer = sys.argv[1], sys.argv[2]
d = load(path, layer); coords = d["coords"]; rf = d["ring_feat"]; ri_ = d["ring_idx"]; nf = len(d["feat_ids"])
def area(a):
    lam = np.radians(a[:, 0]); sp = np.sin(np.radians(a[:, 1]))
    return abs(0.5 * R * R * np.sum((lam[1:] - lam[:-1]) * (sp[:-1] + sp[1:])))
feat_rings = [[] for _ in range(nf)]
for i, f in enumerate(rf): feat_rings[f].append(i)
fb = np.array([[min(coords[i][:, 0].min() for i in r), min(coords[i][:, 1].min() for i in r),
                max(coords[i][:, 0].max() for i in r), max(coords[i][:, 1].max() for i in r)] for r in feat_rings])
def pip_rings(p, ring_ids):  # 偶奇規則
    n = 0
    for i in ring_ids:
        a = coords[i]; x0, y0, x1, y1 = a[:-1, 0], a[:-1, 1], a[1:, 0], a[1:, 1]
        c = (y0 > p[1]) != (y1 > p[1])
        if c.any():
            xs = x0[c] + (p[1] - y0[c]) * (x1[c] - x0[c]) / (y1[c] - y0[c]); n += int((xs > p[0]).sum())
    return n % 2 == 1
rows = []
for i in np.where(ri_ > 0)[0]:
    a = coords[i]; s = area(a)
    if s < 1.0: continue
    lo, hi = a.min(0), a.max(0); pts = []; tries = 0
    while len(pts) < NS and tries < NS * 400:
        q = lo + rng.random(2) * (hi - lo); tries += 1
        if pip_rings(q, [i]): pts.append(q)
    if not pts: rows.append((s, np.nan, a[:, 0].mean(), a[:, 1].mean(), int(d["feat_ids"][rf[i]]))); continue
    cand = np.where((fb[:, 0] <= hi[0]) & (fb[:, 2] >= lo[0]) & (fb[:, 1] <= hi[1]) & (fb[:, 3] >= lo[1]))[0]
    unc = 0
    for q in pts:
        if not any(pip_rings(q, feat_rings[f]) for f in cand if fb[f, 0] <= q[0] <= fb[f, 2] and fb[f, 1] <= q[1] <= fb[f, 3]): unc += 1
    rows.append((s, unc / len(pts), a[:, 0].mean(), a[:, 1].mean(), int(d["feat_ids"][rf[i]])))
rows.sort(reverse=True)
real = [r for r in rows if r[1] >= 0.5]; filled = [r for r in rows if r[1] < 0.5]
print(f"{layer}: 内部リング>=1㎡ {len(rows)}件 | 覆われていない(実在の穴) {len(real)}件 | 別の地物が埋めている {len(filled)}件")
print("実在の穴(面積㎡ 未被覆率 経度 緯度 fid):")
for s, u, x, y, f in real: print(f"  {s:12.1f}  {u:.2f}  ({x:.4f},{y:.4f})  fid {f}")
part = [r for r in rows if 0 < r[1] < 0.5 or (r[1] >= 0.5 and r[1] < 0.95)]
print("部分的に覆われている(0<未被覆率<0.95):", [(round(r[0]), round(r[1], 2), round(r[2], 4), round(r[3], 4)) for r in part])
