"""Guard the evidence comparator against silently accepting different inputs."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
AVAILABLE = all(importlib.util.find_spec(name) for name in ('numpy', 'shapely', 'pyproj'))
if AVAILABLE:
    import shapely
    from shapely.geometry import Polygon
    from compare_arcgis_candidate_json import compare, nearby_pairs


@unittest.skipUnless(AVAILABLE, 'Optional geometry-audit libraries are not installed')
class CandidateJsonTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)
        gpkg, exported = root / 'source.gpkg', root / 'export.json'
        ring = [[139, 35], [139.001, 35], [139.001, 35.001], [139, 35.001], [139, 35]]
        blob = b'GP\x00\x01' + struct.pack('<i', 6668) + shapely.to_wkb(Polygon(ring))
        with sqlite3.connect(gpkg) as db:
            db.execute('CREATE TABLE void_candidates (fid INTEGER, candidate_id TEXT, geom BLOB, label TEXT)')
            db.execute('INSERT INTO void_candidates VALUES (1, ?, ?, ?)', ('one', blob, '日本'))
        document = {'spatialReference': {'wkid': 6668}, 'features': [
            {'attributes': {'OBJECTID': 7, 'candidate_id': 'one', 'label': '日本'},
             'geometry': {'rings': [ring]}}]}
        exported.write_text(json.dumps(document), encoding='utf-8')
        return gpkg, exported, document

    def test_exact_content_preserved_and_nonsequential_id(self):
        with tempfile.TemporaryDirectory() as directory:
            gpkg, exported, _ = self.fixture(directory)
            result = compare(exported, gpkg)
            self.assertTrue(result['input_hashes_unchanged'])
            row = result['features'][0]
            self.assertEqual(row['objectid'], 7)
            self.assertEqual(row['ordered_coordinate_max_delta_degree'], 0)
            self.assertEqual(row['attribute_mismatches'], [])
            self.assertEqual(row['nonadjacent_pairs_within_xy_tolerance'], [])

    def test_duplicate_and_missing_candidates_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            gpkg, exported, document = self.fixture(directory)
            document['features'] *= 2
            exported.write_text(json.dumps(document), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'candidate IDs'):
                compare(exported, gpkg)
            document['features'] = []
            exported.write_text(json.dumps(document), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'candidate IDs'):
                compare(exported, gpkg)

    def test_wrong_crs_and_multiple_rings_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            gpkg, exported, document = self.fixture(directory)
            document['spatialReference']['wkid'] = 4326
            exported.write_text(json.dumps(document), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'EPSG:6668'):
                compare(exported, gpkg)
            document['spatialReference']['wkid'] = 6668
            document['features'][0]['geometry']['rings'] *= 2
            exported.write_text(json.dumps(document), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'multi-ring'):
                compare(exported, gpkg)

    def test_attribute_change_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            gpkg, exported, document = self.fixture(directory)
            document['features'][0]['attributes']['label'] = 'changed'
            exported.write_text(json.dumps(document), encoding='utf-8')
            self.assertEqual(compare(exported, gpkg)['features'][0]['attribute_mismatches'], ['label'])

    def test_close_pair_excludes_closure_and_adjacent_vertices(self):
        import numpy as np
        coords = np.array([[0, 0], [5, 0], [10, 0], [5, 1e-9], [0, 0]])
        pairs = nearby_pairs(coords, 9e-9)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0]['positions_zero_based'], [1, 3])


if __name__ == '__main__':
    unittest.main()
