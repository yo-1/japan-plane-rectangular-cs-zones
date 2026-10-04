"""N03 の市区町村単位と都道府県単位のファイルで、座標の値の作られ方が違うかを調べる（標準ライブラリだけで動く）。

調べること:
  1. それぞれのファイルで、頂点の座標が小数9桁でぴったり表せる値の割合（10個おきに数える）。
  2. 決めた県（鳥取県・長野県）について、都道府県単位のファイルの頂点が、
     市区町村単位のファイルの頂点と同じ値か。違う場合は、いちばん近い頂点との差。

使い方（N03-20260101.shp と N03-20260101_prefecture.shp と、それぞれの .dbf があるフォルダを指定）:
    python n03_compare.py C:\\work\\N03-20260101_GML

結果は画面に出し、同じ内容を、実行したフォルダの n03_compare_result.txt（UTF-8）にも書きます。
数分かかることがあります。
"""

import math
import statistics
import struct
import sys
from pathlib import Path

MUNICIPALITY = "N03-20260101.shp"
PREFECTURE = "N03-20260101_prefecture.shp"
PREFECTURE_CODES = {"31": "鳥取県", "20": "長野県"}
SAMPLE_STEP = 10
NEAR = 1e-6  # 度。これより遠い頂点は「近くに頂点なし」とする
POLYGON_SHAPES = {5, 15, 25}


def read_codes(dbf_path):
    data = Path(dbf_path).read_bytes()
    count, header_len, record_len = struct.unpack("<IHH", data[4:12])
    offset = 1
    for i in range(32, header_len - 1, 32):
        name = data[i:i + 11].split(b"\0")[0].decode("ascii")
        length = data[i + 16]
        if name == "N03_007":
            break
        offset += length
    else:
        raise ValueError(f"N03_007 の列がありません: {dbf_path}")
    return [
        data[header_len + k * record_len + offset:header_len + k * record_len + offset + length].decode("ascii", "replace").strip()
        for k in range(count)
    ]


def iter_records(shp_path):
    """(レコード番号, 頂点の (x, y) の一覧) を順に返す。"""
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
                nparts, npoints = struct.unpack("<ii", content[36:44])
                start = 44 + 4 * nparts
                values = struct.unpack(f"<{2 * npoints}d", content[start:start + 16 * npoints])
                yield index, list(zip(values[0::2], values[1::2]))
            index += 1


def is_nine_decimals(value):
    return float(f"{value:.9f}") == value


def scan(shp_path, codes):
    """小数9桁の割合を数え、対象の県の頂点を県ごとに集める。"""
    total = sampled = nine = 0
    vertices = {key: set() for key in PREFECTURE_CODES}
    for index, points in iter_records(shp_path):
        total += len(points)
        for x, y in points[::SAMPLE_STEP]:
            sampled += 1
            if is_nine_decimals(x) and is_nine_decimals(y):
                nine += 1
        key = codes[index][:2]
        if key in vertices:
            vertices[key].update(points)
    return total, sampled, nine, vertices


def nearest_differences(targets, references):
    """targets の各頂点について、references の中でいちばん近い頂点との距離（度）を返す。"""
    cell = NEAR
    grid = {}
    for x, y in references:
        grid.setdefault((math.floor(x / cell), math.floor(y / cell)), []).append((x, y))
    exact = 0
    differences = []
    missing = 0
    for x, y in targets:
        if (x, y) in references:
            exact += 1
            continue
        cx, cy = math.floor(x / cell), math.floor(y / cell)
        best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for rx, ry in grid.get((cx + dx, cy + dy), ()):
                    d = math.hypot(rx - x, ry - y)
                    if best is None or d < best:
                        best = d
        if best is None or best > NEAR:
            missing += 1
        else:
            differences.append(best)
    return exact, differences, missing


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 1
    folder = Path(argv[1])
    lines = []
    results = {}
    for name in (MUNICIPALITY, PREFECTURE):
        shp = folder / name
        if not shp.is_file() or not shp.with_suffix(".dbf").is_file():
            print(f"エラー: .shp か .dbf が見つかりません: {shp}")
            return 1
        print(f"{name} を読んでいます…")
        total, sampled, nine, vertices = scan(shp, read_codes(shp.with_suffix(".dbf")))
        results[name] = vertices
        lines.append(f"### {name}")
        lines.append(f"   頂点の数（閉じる点を含む）: {total}")
        lines.append(f"   小数9桁でぴったり表せる頂点: {nine} / {sampled}（{SAMPLE_STEP}個おき）"
                     f" = {nine / sampled:.4f}")
    lines.append("")
    for key, label in PREFECTURE_CODES.items():
        prefecture_vertices = results[PREFECTURE][key]
        municipality_vertices = results[MUNICIPALITY][key]
        exact, differences, missing = nearest_differences(prefecture_vertices, municipality_vertices)
        lines.append(f"### {label}（都道府県単位の頂点 {len(prefecture_vertices)}個、市区町村単位の頂点 {len(municipality_vertices)}個。重複は除く）")
        lines.append(f"   市区町村単位にまったく同じ値がある: {exact}")
        lines.append(f"   0.000001度以内に近い頂点がある（値は違う）: {len(differences)}")
        lines.append(f"   0.000001度以内に頂点がない: {missing}")
        if differences:
            lines.append(f"   近い頂点との差（度）: 最小 {min(differences):.3e}、中央値 {statistics.median(differences):.3e}、"
                         f"最大 {max(differences):.3e}")
        lines.append("")
    text = "\n".join(lines)
    Path("n03_compare_result.txt").write_text(text + "\n", encoding="utf-8")
    try:
        print(text)
    except UnicodeEncodeError:
        print("画面に表示できない文字がありました。n03_compare_result.txt を見てください。")
    print("結果を n03_compare_result.txt に書きました。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
