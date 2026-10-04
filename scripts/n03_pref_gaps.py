"""N03 のシェープファイルを都道府県ごとにまとめ、隣り合う都道府県の間の重なりとすき間を調べる。

.shp と .dbf は標準ライブラリで読み、形の計算には Shapely（1.8 以降）を使う（このスクリプトだけ Shapely が必要）。

使い方（.shp と同じ名前の .dbf が必要）:
    python n03_pref_gaps.py N03-20260101_prefecture.shp
    python n03_pref_gaps.py N03-20260101.shp          （比べたいとき。市区町村単位のファイル）

結果は画面に出し、同じ内容を、実行したフォルダの n03_pref_gaps_<ファイル名>.txt（UTF-8）にも書く。
ファイル全体を読んで計算するので、数分〜数十分かかることがある。
"""

import math
import struct
import sys
import time
from pathlib import Path

try:
    from shapely.geometry import MultiPolygon, Point, Polygon
    from shapely.ops import unary_union
except ImportError:  # テストなど、読み込むだけの場面で止めないため、実行するときに知らせる
    MultiPolygon = Point = Polygon = unary_union = None

POLYGON_SHAPES = {5, 15, 25}
TOUCH = 1e-9  # 度。穴の縁と都道府県の境界がこれより近ければ「接している」とみなす
M2_PER_DEG2_AT_EQUATOR = 111320.0 ** 2


def read_prefecture_names(dbf_path):
    data = Path(dbf_path).read_bytes()
    count, header_len, record_len = struct.unpack("<IHH", data[4:12])
    offset = 1
    for i in range(32, header_len - 1, 32):
        name = data[i:i + 11].split(b"\0")[0].decode("ascii")
        length = data[i + 16]
        if name == "N03_001":
            break
        offset += length
    else:
        raise ValueError(f"N03_001 の列がありません: {dbf_path}")
    names = []
    for k in range(count):
        start = header_len + k * record_len + offset
        names.append(data[start:start + length].decode("utf-8", "replace").strip())
    return names


def signed_area(ring):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:])) / 2.0


def record_to_geometry(content):
    """シェープファイルの1レコードを Shapely の形にする。外周は時計回り、穴は反時計回りの決まりを使う。"""
    nparts, npoints = struct.unpack("<ii", content[36:44])
    starts = list(struct.unpack(f"<{nparts}i", content[44:44 + 4 * nparts])) + [npoints]
    base = 44 + 4 * nparts
    values = struct.unpack(f"<{2 * npoints}d", content[base:base + 16 * npoints])
    points = list(zip(values[0::2], values[1::2]))
    shells, holes = [], []
    for a, b in zip(starts, starts[1:]):
        ring = points[a:b]
        if len(ring) < 4:
            continue
        (shells if signed_area(ring) < 0 else holes).append(ring)
    if not shells:  # 向きが決まりどおりでないデータに備える
        shells, holes = holes, []
    polygons = [[shell, []] for shell in shells]
    for hole in holes:
        point = Point(hole[0])
        for item in polygons:
            if Polygon(item[0]).contains(point):
                item[1].append(hole)
                break
    geometries = [Polygon(shell, rings) for shell, rings in polygons]
    return geometries[0] if len(geometries) == 1 else MultiPolygon(geometries)


def read_by_prefecture(shp_path):
    names = read_prefecture_names(Path(shp_path).with_suffix(".dbf"))
    groups, invalid = {}, 0
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
                geometry = record_to_geometry(content)
                if not geometry.is_valid:
                    invalid += 1
                    geometry = geometry.buffer(0)
                groups.setdefault(names[index], []).append(geometry)
            index += 1
    return groups, invalid


def polygon_parts(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        return [geometry]
    if hasattr(geometry, "geoms"):
        parts = []
        for g in geometry.geoms:
            parts.extend(polygon_parts(g))
        return parts
    return []


def square_meters(area_deg2, latitude):
    return area_deg2 * M2_PER_DEG2_AT_EQUATOR * math.cos(math.radians(latitude))


def boxes_overlap(a, b, margin=TOUCH):
    return not (a[2] + margin < b[0] or b[2] + margin < a[0] or a[3] + margin < b[1] or b[3] + margin < a[1])


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 1
    if unary_union is None:
        print("エラー: Shapely が見つかりません。python -m pip install shapely を実行してください。")
        return 1
    shp = Path(argv[1])
    if not shp.is_file() or not shp.with_suffix(".dbf").is_file():
        print(f"エラー: .shp か .dbf が見つかりません: {shp}")
        return 1
    started = time.time()
    lines = [f"### {shp.name}"]
    print(f"{shp.name} を読んでいます…")
    groups, invalid = read_by_prefecture(shp)
    lines.append(f"   都道府県の数: {len(groups)}、ポリゴンの数: {sum(len(v) for v in groups.values())}、"
                 f"無効な形（buffer(0) で直して計算した）: {invalid}")

    print("都道府県ごとにまとめています…")
    prefectures = {}
    for name, geometries in groups.items():
        prefectures[name] = unary_union(geometries)
    boxes = {name: g.bounds for name, g in prefectures.items()}
    print(f"   {time.time() - started:.0f}秒")

    print("隣り合う都道府県の重なりを調べています…")
    names = sorted(prefectures)
    touching, overlaps = 0, []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if not boxes_overlap(boxes[a], boxes[b]) or not prefectures[a].intersects(prefectures[b]):
                continue
            touching += 1
            parts = polygon_parts(prefectures[a].intersection(prefectures[b]))
            if parts:
                area = sum(p.area for p in parts)
                lat = sum(p.centroid.y for p in parts) / len(parts)
                lon = sum(p.centroid.x for p in parts) / len(parts)
                overlaps.append((area, a, b, len(parts), lon, lat))
    lines.append(f"   接している都道府県の組: {touching}")
    lines.append(f"   面の重なりがある組: {len(overlaps)}")
    for area, a, b, count, lon, lat in sorted(overlaps, reverse=True):
        lines.append(f"     {a}-{b}: 面のかけら {count}個、合計 {area:.3e} 平方度"
                     f"（約 {square_meters(area, lat):.6f} 平方メートル）、中心付近 東経{lon:.4f} 北緯{lat:.4f}")
    print(f"   {time.time() - started:.0f}秒")

    print("すき間を調べています…")
    union = unary_union(list(prefectures.values()))
    holes = [Polygon(ring) for part in polygon_parts(union) for ring in part.interiors]
    boundaries = {name: g.boundary for name, g in prefectures.items()}
    gaps, single = [], 0
    for hole in holes:
        near = [name for name in names
                if boxes_overlap(boxes[name], hole.bounds) and boundaries[name].distance(hole.exterior) <= TOUCH]
        if len(near) >= 2:
            gaps.append((hole.area, near, hole.representative_point()))
        else:
            single += 1
    lines.append(f"   全体をまとめた形の中の穴: {len(holes)}（1つの都道府県だけに囲まれた穴 {single}、"
                 f"2つ以上の都道府県に囲まれた穴＝すき間 {len(gaps)}）")
    for area, near, point in sorted(gaps, key=lambda g: -g[0])[:50]:
        lines.append(f"     {'・'.join(near)}: {area:.3e} 平方度（約 {square_meters(area, point.y):.6f} 平方メートル）"
                     f"、東経{point.x:.5f} 北緯{point.y:.5f}")
    if len(gaps) > 50:
        lines.append(f"     ほか {len(gaps) - 50}個")
    lines.append(f"   かかった時間: {time.time() - started:.0f}秒")

    text = "\n".join(lines)
    output = Path(f"n03_pref_gaps_{shp.stem}.txt")
    output.write_text(text + "\n", encoding="utf-8")
    try:
        print(text)
    except UnicodeEncodeError:
        print(f"画面に表示できない文字がありました。{output} を見てください。")
    print(f"結果を {output} に書きました。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
