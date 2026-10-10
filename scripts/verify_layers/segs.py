import os
import numpy as np, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from load import load
def segments(path, layer):
    d = load(path, layer)
    P0 = []; P1 = []; F = []; R = []
    for ri, a in enumerate(d["coords"]):
        P0.append(a[:-1]); P1.append(a[1:]); n = len(a) - 1
        F.append(np.full(n, d["ring_feat"][ri], np.int32)); R.append(np.full(n, ri, np.int32))
    return d, np.concatenate(P0), np.concatenate(P1), np.concatenate(F), np.concatenate(R)
if __name__ == "__main__":
    t = time.time(); d, a, b, f, r = segments(sys.argv[1], sys.argv[2])
    L = np.hypot(*(b - a).T)
    print("segments", len(a), "load s", round(time.time() - t))
    print("len percentiles (deg)", np.percentile(L, [50, 90, 99, 99.9, 100]))
    print("n>0.01deg", (L > 0.01).sum(), "n>0.002", (L > 0.002).sum(), "zero-length", (L == 0).sum())
