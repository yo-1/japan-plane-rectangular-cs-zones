import json
import tempfile
import unittest
from pathlib import Path
import sys,importlib.util
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
AVAILABLE=all(importlib.util.find_spec(p) for p in ['numpy','shapely','pyproj','pyogrio'])
if AVAILABLE:
    import numpy as np
    import shapely
    from shapely.geometry import Polygon
    from geometry_audit import prefectures as runner

@unittest.skipUnless(AVAILABLE, "Optional geometry-audit libraries are not installed")
class PrefectureCompletionTests(unittest.TestCase):
    def test_topologically_identical_inputs_with_different_vertices_finish(self):
        # Same region, one input has an extra collinear boundary vertex.
        # Normalized coordinate comparison differs but both overlays are empty.
        first=Polygon([(139,35),(140,35),(140,36),(139,36),(139,35)])
        second=Polygon([(139,35),(139.5,35),(140,35),(140,36),(139,36),(139,35)])
        runner.SG=np.array([first],dtype=object);runner.PG=np.array([second],dtype=object)
        runner.SI={'23000':[0]};runner.PI={'23000':[0]}
        runner.SF={'N03_001':['Test'],'N03_007':['23100']};runner.PF={'N03_007':['23000']}
        runner.ST=shapely.STRtree(runner.SG);runner.PT=shapely.STRtree(runner.PG)
        with tempfile.TemporaryDirectory() as cache:
            self.assertEqual(runner.work('23000',cache),'23000')
            result=json.loads((Path(cache)/'23000/result.json').read_text())
            self.assertFalse(result['row']['normalized_exact'])
            self.assertTrue(result['row']['lost_empty']);self.assertTrue(result['row']['added_empty'])
            self.assertEqual(result['samples'],[])
            self.assertEqual(set(result['geometry_files']),{'source_union.wkb','prefecture_union.wkb','lost.wkb','added.wkb'})

if __name__=='__main__':unittest.main()
