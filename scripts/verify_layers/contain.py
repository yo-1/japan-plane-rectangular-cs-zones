"""各ポリゴン(外環)の1頂点が、別の地物の内部(穴を除く、境界から1e-6度超)にないかを調べる(入れ子の重なり)。"""
import os
import numpy as np, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from segs import segments
path, layer = sys.argv[1], sys.argv[2]
d, A, B, F, R = segments(path, layer)
order = np.argsort(F, kind="stable"); A = A[order]; B = B[order]; F = F[order]
nf = len(d["feat_ids"]); fs = np.searchsorted(F, np.arange(nf + 1))
bb = np.zeros((nf, 4))
for f in range(nf):
    a, b = A[fs[f]:fs[f + 1]], B[fs[f]:fs[f + 1]]
    bb[f] = [min(a[:, 0].min(), b[:, 0].min()), min(a[:, 1].min(), b[:, 1].min()),
             max(a[:, 0].max(), b[:, 0].max()), max(a[:, 1].max(), b[:, 1].max())]
def inside(p, f):  # 偶奇規則(全リング)
    a, b = A[fs[f]:fs[f + 1]], B[fs[f]:fs[f + 1]]
    c = ((a[:, 1] > p[1]) != (b[:, 1] > p[1]))
    a, b = a[c], b[c]
    x = a[:, 0] + (p[1] - a[:, 1]) * (b[:, 0] - a[:, 0]) / (b[:, 1] - a[:, 1])
    return int((x > p[0]).sum()) % 2 == 1
def dist(p, f):
    a, b = A[fs[f]:fs[f + 1]], B[fs[f]:fs[f + 1]]
    v = b - a; w = p - a; l2 = (v * v).sum(1); t = np.clip((w * v).sum(1) / np.where(l2 == 0, 1, l2), 0, 1)
    q = a + v * t[:, None]; return np.hypot(*(q - p).T).min()
res = []; tested = 0; amb = 0
for ri, ring in enumerate(d["coords"]):
    if d["ring_idx"][ri] != 0: continue
    fa = d["ring_feat"][ri]; p = ring[0]; tested += 1
    cand = np.where((bb[:, 0] <= p[0]) & (p[0] <= bb[:, 2]) & (bb[:, 1] <= p[1]) & (p[1] <= bb[:, 3]))[0]
    for fb in cand:
        if fb == fa: continue
        if inside(p, fb):
            dd = dist(p, fb)
            if dd > 1e-6: res.append((d["feat_ids"][fa], d["feat_ids"][fb], dd, p.tolist()))
            else: amb += 1
print(layer, "outer rings tested", tested, "| inside another feature (dist>1e-6 deg):", len(res), "| ambiguous on-boundary:", amb)
for r in res[:15]: print("  ", r)
