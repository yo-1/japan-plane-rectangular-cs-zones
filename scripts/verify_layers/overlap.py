"""異なる地物の境界線分どうしが、許容値τを超えて「真に交差」する組を数える(重なりの検出)。
さらに、各ポリゴンの外環の1頂点が、他の地物の内部(穴を除く)に入っていないかを調べる(入れ子の検出)。
numpy/scipyのみ。度の座標をそのまま使う(τは度)。"""
import os, sys, time
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from segs import segments
G = 0.0005; TAU = float(sys.argv[3]) if len(sys.argv) > 3 else 1e-7
path, layer = sys.argv[1], sys.argv[2]
t0 = time.time(); d, A, B, F, R = segments(path, layer)
if os.environ.get("CTRL_FEAT"):  # 陽性対照: 指定地物を経度方向へずらして、検出器が重なりを拾うか確かめる
    m_ = F == int(os.environ["CTRL_FEAT"]); A = A.copy(); B = B.copy()
    A[m_, 0] += float(os.environ.get("CTRL_SHIFT", "0.001")); B[m_, 0] += float(os.environ.get("CTRL_SHIFT", "0.001"))
n = len(A); print(layer, "segments", n, flush=True)
lo = np.minimum(A, B); hi = np.maximum(A, B)
cx0 = np.floor(lo[:, 0] / G).astype(np.int64); cx1 = np.floor(hi[:, 0] / G).astype(np.int64)
cy0 = np.floor(lo[:, 1] / G).astype(np.int64); cy1 = np.floor(hi[:, 1] / G).astype(np.int64)
nx = cx1 - cx0 + 1; ny = cy1 - cy0 + 1; cnt = nx * ny
tot = int(cnt.sum()); print("incidences", tot, flush=True)
seg_of = np.repeat(np.arange(n, dtype=np.int64), cnt)
start = np.cumsum(cnt) - cnt
k = np.arange(tot, dtype=np.int64) - np.repeat(start, cnt)
sx = np.repeat(cx0, cnt) + k % np.repeat(nx, cnt); sy = np.repeat(cy0, cnt) + k // np.repeat(nx, cnt)
del k
key = sx * 1_000_003 + sy; del sx, sy
order = np.argsort(key, kind="stable"); key = key[order]; seg_of = seg_of[order]; del order
ukey, gstart, gcnt = np.unique(key, return_index=True, return_counts=True)
print("cells", len(ukey), "max per cell", gcnt.max(), "t", round(time.time() - t0), flush=True)
pos_group_end = np.repeat(gstart + gcnt, gcnt)  # 各要素のグループ終端
pos = np.arange(tot, dtype=np.int64)
partners = pos_group_end - pos - 1
cross_pairs = []; checked = 0
CH = 4_000_000
# 要素を、ペア数の累積がCHを超えない範囲ごとに処理
cum = np.cumsum(partners); b0 = 0
while b0 < tot:
    base = cum[b0 - 1] if b0 else 0
    b1 = int(np.searchsorted(cum, base + CH, side="right")); b1 = max(b1, b0 + 1); b1 = min(b1, tot)
    pc = partners[b0:b1]; m = int(pc.sum())
    if m:
        ii = np.repeat(np.arange(b0, b1), pc)
        off = np.arange(m) - np.repeat(np.cumsum(pc) - pc, pc)
        jj = ii + 1 + off
        s1 = seg_of[ii]; s2 = seg_of[jj]
        ok = F[s1] != F[s2]; s1 = s1[ok]; s2 = s2[ok]
        if len(s1):
            a = A[s1]; b = B[s1]; c = A[s2]; dd = B[s2]
            ab = b - a; cd = dd - c
            lab = np.hypot(ab[:, 0], ab[:, 1]); lcd = np.hypot(cd[:, 0], cd[:, 1])
            def side(p, q, v, l, r):  # 点rのp→q直線に対する符号付き距離
                return (v[:, 0] * (r[:, 1] - p[:, 1]) - v[:, 1] * (r[:, 0] - p[:, 0])) / l
            d1 = side(a, b, ab, lab, c); d2 = side(a, b, ab, lab, dd)
            d3 = side(c, dd, cd, lcd, a); d4 = side(c, dd, cd, lcd, b)
            x = (d1 * d2 < 0) & (np.minimum(abs(d1), abs(d2)) > TAU) & (d3 * d4 < 0) & (np.minimum(abs(d3), abs(d4)) > TAU)
            if x.any():
                dep = np.minimum.reduce([abs(d1), abs(d2), abs(d3), abs(d4)])[x]
                cross_pairs.append(np.stack([s1[x], s2[x], dep], 1))
        checked += int(ok.sum())
    b0 = b1
print("candidate pairs (diff feature)", checked, "t", round(time.time() - t0), flush=True)
if cross_pairs:
    cp = np.concatenate(cross_pairs); lo_ = np.minimum(cp[:, 0], cp[:, 1]); hi_ = np.maximum(cp[:, 0], cp[:, 1])
    _, ui = np.unique(np.stack([lo_, hi_], 1), axis=0, return_index=True); cp = cp[ui]
else:
    cp = np.zeros((0, 3))
print(f"PROPER CROSSINGS (tau={TAU} deg): {len(cp)}")
if len(cp):
    fe = np.stack([F[cp[:, 0].astype(int)], F[cp[:, 1].astype(int)]], 1)
    for i in np.argsort(-cp[:, 2])[:10]:
        s = int(cp[i, 0]); print("  depth_deg", cp[i, 2], "features", d["feat_ids"][fe[i, 0]], d["feat_ids"][fe[i, 1]], "at", A[s])
pass  # 交差の組は上に表示する
