"""検証に使ったスクリプト（n03_vertices.py・n03_compare.py・n03_pref_gaps.py）のテスト。

小さなシェープファイルをテストの中で作って動かす。n03_pref_gaps.py は Shapely がない環境ではスキップする。
"""

import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "tests"))

import n03_compare  # noqa: E402
import n03_pref_gaps  # noqa: E402
import n03_vertices  # noqa: E402
from test_check_coordinate_zones import write_dbf, write_shp  # noqa: E402

try:
    import shapely  # noqa: F401
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False


def write_layer(folder, name, rows_and_boxes):
    shp = Path(folder) / f"{name}.shp"
    write_dbf(shp.with_suffix(".dbf"), [row for row, _ in rows_and_boxes])
    write_shp(shp, [box for _, box in rows_and_boxes])
    return shp


@contextlib.contextmanager
def working_directory(path):
    previous = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class VerticesTest(unittest.TestCase):
    def test_writes_nearby_vertices_without_rounding(self):
        with tempfile.TemporaryDirectory() as folder:
            nagano = {"N03_001": "長野県", "N03_004": "軽井沢町", "N03_007": "20321"}
            gunma = {"N03_001": "群馬県", "N03_004": "嬬恋村", "N03_007": "10425"}
            for name in ("N03-20260101", "N03-20260101_prefecture"):
                write_layer(folder, name, [
                    (nagano, (138.5, 36.3, 138.5531988243335, 36.41666666850003)),
                    (gunma, (138.5531988243335, 36.416666669250105, 138.6, 36.5)),
                ])
            with working_directory(folder), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(n03_vertices.main(["n03_vertices.py", folder]), 0)
            text = (Path(folder) / "n03_vertices_result.txt").read_text(encoding="utf-8")
        self.assertIn("長野県 軽井沢町 20321 (138.5531988243335, 36.41666666850003)", text)
        self.assertIn("群馬県 嬬恋村 10425 (138.5531988243335, 36.416666669250105)", text)
        self.assertIn("近くに頂点なし", text)  # ほかの調べる点は、このデータにはない


class CompareTest(unittest.TestCase):
    def test_nearest_differences(self):
        references = {(133.2, 35.5), (133.3, 35.6)}
        targets = {(133.2, 35.5), (133.3000000001, 35.6), (134.0, 36.0)}
        exact, differences, missing = n03_compare.nearest_differences(targets, references)
        self.assertEqual(exact, 1)
        self.assertEqual(len(differences), 1)
        self.assertAlmostEqual(differences[0], 1e-10, delta=1e-12)
        self.assertEqual(missing, 1)

    def test_main_counts_nine_decimal_vertices(self):
        with tempfile.TemporaryDirectory() as folder:
            row = {"N03_001": "鳥取県", "N03_007": "31204"}
            write_layer(folder, "N03-20260101", [(row, (133.2, 35.5, 133.3, 35.6))])
            write_layer(folder, "N03-20260101_prefecture",
                        [({"N03_001": "鳥取県", "N03_007": "31000"}, (133.2000000001, 35.5, 133.3, 35.6))])
            with working_directory(folder), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(n03_compare.main(["n03_compare.py", folder]), 0)
            text = (Path(folder) / "n03_compare_result.txt").read_text(encoding="utf-8")
        self.assertIn("市区町村単位にまったく同じ値がある: 2", text)
        self.assertIn("0.000001度以内に近い頂点がある（値は違う）: 2", text)


@unittest.skipUnless(HAS_SHAPELY, "Shapely がないため未実行")
class PrefectureGapsTest(unittest.TestCase):
    def run_script(self, rows_and_boxes):
        with tempfile.TemporaryDirectory() as folder:
            shp = write_layer(folder, "sample", rows_and_boxes)
            with working_directory(folder), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(n03_pref_gaps.main(["n03_pref_gaps.py", str(shp)]), 0)
            return (Path(folder) / "n03_pref_gaps_sample.txt").read_text(encoding="utf-8")

    def test_touching_prefectures_have_no_overlap(self):
        text = self.run_script([
            ({"N03_001": "長野県"}, (138.0, 36.0, 138.5, 36.5)),
            ({"N03_001": "群馬県"}, (138.5, 36.0, 139.0, 36.5)),
        ])
        self.assertIn("接している都道府県の組: 1", text)
        self.assertIn("面の重なりがある組: 0", text)
        self.assertIn("すき間 0", text)

    def test_overlap_is_counted(self):
        text = self.run_script([
            ({"N03_001": "長野県"}, (138.0, 36.0, 138.6, 36.5)),   # 群馬県と 0.1度重なる
            ({"N03_001": "群馬県"}, (138.5, 36.0, 139.0, 36.5)),
        ])
        self.assertIn("面の重なりがある組: 1", text)
        self.assertIn("群馬県-長野県: 面のかけら 1個", text)  # 名前の文字コード順に並ぶ

    def test_gap_between_prefectures_is_counted(self):
        # 長野県の東に、群馬県の3つの帯で囲まれた空き（東経138.5〜138.6度）を作る。
        text = self.run_script([
            ({"N03_001": "長野県"}, (138.0, 36.0, 138.5, 36.5)),
            ({"N03_001": "群馬県"}, (138.6, 36.0, 139.0, 36.5)),
            ({"N03_001": "群馬県"}, (138.0, 36.5, 139.0, 37.0)),
            ({"N03_001": "群馬県"}, (138.0, 35.5, 139.0, 36.0)),
        ])
        self.assertIn("2つ以上の都道府県に囲まれた穴＝すき間 1", text)
        self.assertIn("群馬県・長野県: 5.000e-02 平方度", text)

    def test_reports_missing_shapely(self):
        saved = n03_pref_gaps.unary_union
        n03_pref_gaps.unary_union = None
        try:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(n03_pref_gaps.main(["n03_pref_gaps.py", "x.shp"]), 1)
            self.assertIn("Shapely が見つかりません", output.getvalue())
        finally:
            n03_pref_gaps.unary_union = saved


if __name__ == "__main__":
    unittest.main()
