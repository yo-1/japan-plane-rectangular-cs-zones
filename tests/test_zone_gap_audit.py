"""Synthetic evidence checks for gap/enclave classification and metric proxies."""
import sys
import importlib.util
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
AVAILABLE = all(importlib.util.find_spec(p) for p in ['numpy', 'shapely', 'pyproj', 'pyogrio'])
if AVAILABLE:
    import numpy as np
    import shapely
    from shapely.geometry import box
    from audit_zone_gaps import classify_void, measure, signature


@unittest.skipUnless(AVAILABLE, 'Optional geometry-audit libraries are not installed')
class ZoneGapAuditTests(unittest.TestCase):
    def classify(self, ring, source, muni, zones, numbers):
        fields = {'N03_007': ['01001'] * len(source),
                  'N03_001': ['Test'] * len(source),
                  'N03_004': ['Town'] * len(source), 'N03_005': [''] * len(source)}
        return classify_void(ring, zones, shapely.STRtree(zones), source,
            shapely.STRtree(source), muni, shapely.STRtree(muni), fields, {},
            np.array(numbers[:len(source)]), np.array(numbers[:len(muni)]))

    def test_long_large_source_void_is_retained(self):
        ring = box(139.002, 35.004, 139.008, 35.004001)
        shell = box(139, 35, 139.01, 35.01).difference(ring)
        void, row = self.classify(ring, [shell], [shell], [shell], [9])
        m = measure(void)
        self.assertEqual(row['cause'], '原典由来')
        self.assertEqual(row['context'], '同一系内部')
        self.assertGreater(m['area_m2'], 1)
        self.assertGreater(m['obb_aspect'], 1000)

    def test_other_zone_enclave_not_a_gap(self):
        ring = box(139.002, 35.002, 139.008, 35.008)
        shell = box(139, 35, 139.01, 35.01).difference(ring)
        void, row = self.classify(ring, [shell, ring], [shell, ring], [shell, ring], [9, 8])
        self.assertTrue(void.is_empty)
        self.assertIn('8', row['ring_covered_zones'])
        self.assertEqual(row['context'], '系間・外周として維持')

    def test_missing_public_zone_area_has_stage_evidence(self):
        ring = box(139.002, 35.002, 139.008, 35.008)
        full = box(139, 35, 139.01, 35.01)
        void, row = self.classify(ring, [full], [full], [full.difference(ring)], [9])
        self.assertEqual(row['cause'], '加工で発生')
        self.assertGreater(row['source_inside_m2'], 0)

    def test_multiple_zone_adjacency_is_preserved(self):
        ring = box(139.004, 35.004, 139.006, 35.006)
        left = box(139, 35, 139.005, 35.01).difference(ring)
        right = box(139.005, 35, 139.01, 35.01).difference(ring)
        _, row = self.classify(ring, [left, right], [left, right], [left, right], [9, 8])
        self.assertEqual(row['cause'], '原典由来')
        self.assertEqual(row['context'], '系間・外周として維持')

    def test_identifier_ignores_ring_orientation(self):
        g = box(139, 35, 139.01, 35.01)
        self.assertEqual(signature(g), signature(shapely.reverse(g)))


if __name__ == '__main__':
    unittest.main()
