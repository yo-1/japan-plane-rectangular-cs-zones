"""GPKG(Polygon/MultiPolygon)をnumpy配列へ。numpyのみ。入力は読み取り専用で開く。"""
import sqlite3, struct, numpy as np, sys
ENV = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
def load(path, layer):
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    gc = c.execute("select column_name from gpkg_geometry_columns where table_name=?", (layer,)).fetchone()[0]
    pk = c.execute(f'select name from pragma_table_info("{layer}") where pk=1').fetchone()[0]
    coords = []; ring_feat = []; ring_idx = []; ring_len = []; feat_ids = []
    for fi, (fid, blob) in enumerate(c.execute(f'select "{pk}","{gc}" from "{layer}" order by "{pk}"')):
        feat_ids.append(fid)
        blob = bytes(blob); o = 8 + ENV[(blob[3] >> 1) & 7]; e = "<" if blob[o] == 1 else ">"
        t = struct.unpack_from(e + "I", blob, o + 1)[0]; assert t in (3, 6)
        def poly(p, e):
            nr = struct.unpack_from(e + "I", blob, p)[0]; p += 4
            for k in range(nr):
                n = struct.unpack_from(e + "I", blob, p)[0]; p += 4
                a = np.frombuffer(blob, e + "f8", 2 * n, p).reshape(-1, 2); p += 16 * n
                coords.append(a); ring_feat.append(fi); ring_idx.append(k); ring_len.append(n)
            return p
        if t == 3: poly(o + 5, e)
        else:
            n = struct.unpack_from(e + "I", blob, o + 5)[0]; p = o + 9
            for _ in range(n):
                e2 = "<" if blob[p] == 1 else ">"; p += 5; p = poly(p, e2)
    c.close()
    return dict(coords=coords, ring_feat=np.array(ring_feat), ring_idx=np.array(ring_idx),
                feat_ids=np.array(feat_ids))
if __name__ == "__main__":
    d = load(sys.argv[1], sys.argv[2])
    n = sum(len(a) for a in d["coords"])
    print(sys.argv[2], "features", len(d["feat_ids"]), "rings", len(d["coords"]), "vertices", n)
