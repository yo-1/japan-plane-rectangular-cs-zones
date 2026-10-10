"""別の地物の頂点どうしの近さの分布。境界が正確に共有されていれば距離≒1e-13度(同一点)、
共有されていない隙間・重なりの細片があれば1e-9〜1e-5度の帯に点が現れる。numpy/scipyのみ。
使い方: python3 -I scripts/verify_layers/near.py <gpkg> <layer> [R=5e-6]"""
import os
import numpy as np, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from load import load
from scipy.spatial import cKDTree
path, layer = sys.argv[1], sys.argv[2]; Rr = float(sys.argv[3]) if len(sys.argv) > 3 else 5e-6
d = load(path, layer)
XY = np.concatenate([a[:-1] for a in d["coords"]]); F = np.concatenate([np.full(len(a) - 1, d["ring_feat"][i], np.int32) for i, a in enumerate(d["coords"])])
print(layer, "vertices", len(XY), flush=True)
t = cKDTree(XY); bins = [0, 1e-9, 1e-8, 1e-7, 1e-6, Rr]; hist = np.zeros(len(bins) - 1, np.int64)
# 各頂点について、別の地物の最近傍までの距離がどの帯にあるか(頂点ごとに1回数える)
CH = 500000; worst = []
for s in range(0, len(XY), CH):
    q = XY[s:s + CH]; k = 6
    dist, idx = t.query(q, k=k, distance_upper_bound=Rr)
    other = (idx < len(XY))
    idx2 = np.where(other, idx, 0); diff = other & (F[idx2] != F[s:s + CH, None])
    dd = np.where(diff, dist, np.inf).min(1)
    h, _ = np.histogram(dd[np.isfinite(dd)], bins=bins); hist += h
    sel = np.where((dd > 1e-8) & (dd < Rr))[0]
    for i in sel[:3]: worst.append((float(dd[i]), q[i].tolist()))
print("別の地物の最近傍頂点までの距離(度)の帯と頂点数:")
for i in range(len(hist)): print(f"  {bins[i]:.0e} 〜 {bins[i+1]:.0e}: {hist[i]}")
print("1e-8超〜R未満の例(距離, 座標):", worst[:8])
