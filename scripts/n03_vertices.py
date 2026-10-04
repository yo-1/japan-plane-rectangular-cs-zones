"""N03 の2つのシェープファイルから、重なり・すき間のかけらがあった場所の頂点を、そのままの値で書き出す。

調べるファイル（同じフォルダにあるもの）:
    N03-20260101.shp            市区町村単位
    N03-20260101_prefecture.shp 都道府県単位
どちらも同じ名前の .dbf が必要です。標準ライブラリだけで動きます（Python 3.9 以降）。

使い方（OSGeo4W Shell など）:
    python n03_vertices.py C:\\work\\N03-20260101_GML

結果は画面に出し、同じ内容を、実行したフォルダの n03_vertices_result.txt（UTF-8）にも書きます。
"""

import struct
import sys
from pathlib import Path

SHAPEFILES = ["N03-20260101.shp", "N03-20260101_prefecture.shp"]

# 配布用 GeoPackage で、かけらの頂点だった点。近く（RADIUS 以内）にある元データの頂点をすべて書き出す。
TARGETS = [
    ("重なり I-II（長崎県・佐賀県の境）その1", 129.76435, 33.306394441),
    ("重なり I-II（長崎県・佐賀県の境）その2", 129.774331946, 33.327592775),
    ("重なり III-V（島根県・鳥取県の境）その1", 133.2, 35.523406135),
    ("重なり III-V（島根県・鳥取県の境）その2", 133.208333333, 35.509917171),
    ("すき間 VIII-IX（長野県・群馬県の境）その1", 138.5531988243335, 36.416666668),
    ("すき間 VIII-IX（長野県・群馬県の境）その2", 138.62104387366668, 36.416666668),
    ("すき間 VIII-IX（長野県・群馬県の境）その3", 138.62947489433333, 36.416666668),
    ("すき間 VIII-IX（長野県・群馬県の境）その4", 138.63762501466664, 36.416666668),
]
RADIUS = 1e-6  # 度（約0.1メートル）
POLYGON_SHAPES = {5, 15, 25}


def read_dbf_columns(path, names):
    """.dbf から、指定した列の値だけを行ごとに読む。"""
    data = Path(path).read_bytes()
    count, header_len, record_len = struct.unpack("<IHH", data[4:12])
    positions, offset = {}, 1
    for i in range(32, header_len - 1, 32):
        name = data[i:i + 11].split(b"\0")[0].decode("ascii")
        length = data[i + 16]
        positions[name] = (offset, length)
        offset += length
    rows = []
    for k in range(count):
        record = data[header_len + k * record_len:header_len + (k + 1) * record_len]
        rows.append(tuple(
            record[positions[n][0]:positions[n][0] + positions[n][1]].decode("utf-8", "replace").strip()
            for n in names if n in positions
        ))
    return rows


def find_vertices(shp_path):
    """TARGETS の点ごとに、近くにある頂点を (レコード番号, 頂点番号, x, y) の一覧で返す。"""
    found = {label: [] for label, _, _ in TARGETS}
    with open(shp_path, "rb") as f:
        if struct.unpack(">i", f.read(100)[:4])[0] != 9994:
            raise ValueError(f"シェープファイルではありません: {shp_path}")
        index = 0
        while True:
            head = f.read(8)
            if len(head) < 8:
                break
            content = f.read(struct.unpack(">ii", head)[1] * 2)
            if struct.unpack("<i", content[:4])[0] in POLYGON_SHAPES:
                xmin, ymin, xmax, ymax = struct.unpack("<4d", content[4:36])
                nparts, npoints = struct.unpack("<ii", content[36:44])
                start = 44 + 4 * nparts
                for label, x, y in TARGETS:
                    if not (xmin - RADIUS <= x <= xmax + RADIUS and ymin - RADIUS <= y <= ymax + RADIUS):
                        continue
                    for p in range(npoints):
                        px, py = struct.unpack("<2d", content[start + 16 * p:start + 16 * p + 16])
                        if abs(px - x) <= RADIUS and abs(py - y) <= RADIUS:
                            found[label].append((index, p, px, py))
            index += 1
    return found


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 1
    folder = Path(argv[1])
    lines = []
    for name in SHAPEFILES:
        shp = folder / name
        if not shp.is_file() or not shp.with_suffix(".dbf").is_file():
            lines.append(f"### {name}: .shp か .dbf が見つかりません（{shp}）")
            continue
        rows = read_dbf_columns(shp.with_suffix(".dbf"), ["N03_001", "N03_004", "N03_007"])
        lines.append(f"### {name}（{len(rows)}行）")
        for label, x, y in TARGETS:
            lines.append(f"== {label}  調べた点 ({x!r}, {y!r})")
            hits = find_vertices_cache(shp)[label]
            if not hits:
                lines.append("   近くに頂点なし")
            for index, point, px, py in hits:
                attributes = " ".join(v for v in rows[index] if v)
                lines.append(f"   record={index} 頂点={point} {attributes} ({px!r}, {py!r})")
        lines.append("")
    text = "\n".join(lines)
    Path("n03_vertices_result.txt").write_text(text + "\n", encoding="utf-8")
    try:
        print(text)
    except UnicodeEncodeError:
        print("画面に表示できない文字がありました。n03_vertices_result.txt を見てください。")
    print("\n結果を n03_vertices_result.txt に書きました。")
    return 0


_cache = {}


def find_vertices_cache(shp):
    # 1つのファイルは1回だけ読む（.shp が大きいため）。
    if shp not in _cache:
        _cache[shp] = find_vertices(shp)
    return _cache[shp]


if __name__ == "__main__":
    sys.exit(main(sys.argv))
