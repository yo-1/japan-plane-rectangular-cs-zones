import importlib.util
import io
from pathlib import Path
import struct
import sys
import tempfile
import unittest

AVAILABLE=all(importlib.util.find_spec(p) for p in ['numpy','shapely','pyproj','pyogrio'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
if AVAILABLE:
    import numpy as np
    from shapely.geometry import Polygon
    from inspect_rock_holes import raw_rings, signed_area, inspect_gml


@unittest.skipUnless(AVAILABLE,'Optional geometry-audit libraries are not installed')
class RockHoleInspectionTests(unittest.TestCase):
    def test_raw_shp_preserves_outer_and_inner_ring_orientation(self):
        outer=np.array([(139,35),(139,35.01),(139.01,35.01),(139.01,35),(139,35)])
        inner=np.array([(139.002,35.002),(139.003,35.002),(139.003,35.003),(139.002,35.003),(139.002,35.002)])
        body=struct.pack('<i4d2i2i',5,139,35,139.01,35.01,2,10,0,5)+np.vstack([outer,inner]).astype('<f8').tobytes()
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'test.shp'
            p.write_bytes(bytes(100)+struct.pack('>2i',1,len(body)//2)+body)
            p.with_suffix('.shx').write_bytes(bytes(100)+struct.pack('>2i',50,len(body)//2))
            rings=raw_rings(p,0)
        np.testing.assert_array_equal(rings[0],outer)
        np.testing.assert_array_equal(rings[1],inner)
        self.assertLess(signed_area(rings[0]),0)
        self.assertGreater(signed_area(rings[1]),0)

    def xml(self,shift=0):
        return f'''<ksj:Dataset xmlns:ksj="http://nlftp.mlit.go.jp/ksj/schemas/ksj-app" xmlns:gml="http://www.opengis.net/gml/3.2" xmlns:xlink="http://www.w3.org/1999/xlink">
        <gml:Curve gml:id="cv1_1"><gml:segments><gml:LineStringSegment><gml:posList>
        35 {139+shift} 35 {139.001+shift} 35.001 {139.001+shift} 35.001 {139+shift} 35 {139+shift}
        </gml:posList></gml:LineStringSegment></gml:segments></gml:Curve>
        <gml:Surface gml:id="sf1"><gml:patches><gml:PolygonPatch><gml:interior><gml:Ring><gml:curveMember xlink:href="#_cv1_1"/></gml:Ring></gml:interior></gml:PolygonPatch></gml:patches></gml:Surface>
        <ksj:AdministrativeBoundary gml:id="ab1"><ksj:bounds xlink:href="#_sf1"/><ksj:administrativeAreaCode>00123</ksj:administrativeAreaCode></ksj:AdministrativeBoundary></ksj:Dataset>'''.encode()

    def test_gml_axis_order_role_and_attribute_cross_reference(self):
        target=Polygon([(139,35),(139.001,35),(139.001,35.001),(139,35.001),(139,35)])
        evidence=inspect_gml(io.BytesIO(self.xml()),{'case':target})
        self.assertEqual(len(evidence['curves']),1)
        self.assertTrue(evidence['curves'][0]['normalized_exact'])
        self.assertEqual(evidence['surfaces'][0]['references'][0]['role'],'interior')
        self.assertEqual(evidence['features'][0]['properties']['administrativeAreaCode'],'00123')

    def test_similar_bbox_does_not_bypass_metric_match_limit(self):
        target=Polygon([(139,35),(139.001,35),(139.001,35.001),(139,35.001),(139,35)])
        evidence=inspect_gml(io.BytesIO(self.xml(1e-6)),{'case':target})
        self.assertFalse(evidence['curves'])


if __name__=='__main__':unittest.main()
