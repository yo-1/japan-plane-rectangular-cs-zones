"""Comparison copies must preserve raw feature values, including IDs."""
import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
AVAILABLE = all(importlib.util.find_spec(p) for p in ['numpy', 'shapely', 'pyproj', 'pyogrio'])
if AVAILABLE:
    from shapely.geometry import box, MultiPolygon, GeometryCollection
    from audit_zone_gaps import layer
    from geometry_audit.common import Audit, hashfile
    from prepare_arcgis_comparison import prepare_file


@unittest.skipUnless(AVAILABLE, 'Optional geometry-audit libraries are not installed')
class ArcGISComparisonTests(unittest.TestCase):
    def test_mixed_types_partition_without_feature_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'source.gpkg'
            layer(source, 'context', [(box(139, 35, 140, 36), {'label': '日本', 'n': 7}),
                (MultiPolygon([box(141, 35, 142, 36)]), {'label': '島', 'n': 9})])
            before = hashfile(source)
            result = prepare_file(source, root / 'typed.gpkg')
            self.assertEqual(before, hashfile(source))
            self.assertEqual(result['tables'][0]['before'], result['tables'][0]['after'])
            with sqlite3.connect(source) as original, sqlite3.connect(root / 'typed.gpkg') as copy:
                rows = original.execute('SELECT * FROM context ORDER BY fid').fetchall()
                actual = []
                for name, kind in copy.execute('SELECT table_name,geometry_type_name FROM gpkg_geometry_columns'):
                    self.assertIn(kind, ['POLYGON', 'MULTIPOLYGON'])
                    self.assertIn('"geom" '+kind, copy.execute('SELECT sql FROM sqlite_master WHERE name=?', (name,)).fetchone()[0])
                    actual.extend(copy.execute('SELECT * FROM "'+name+'"').fetchall())
                self.assertEqual(rows, sorted(actual))

    def test_blob_declaration_and_raw_geometry_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audit = Audit(root)
            audit.feature(box(139, 35, 140, 36), dict(stage='test', key='1', direction='lost', area_m2=1.0))
            audit.write({})
            result = prepare_file(root / 'differences.gpkg', root / 'typed.gpkg')
            self.assertIn('geom POLYGON', result['tables'][0]['layers'][0]['sql'])
            self.assertEqual(result['tables'][0]['before'], result['tables'][0]['after'])

    def test_geometry_collection_rejected_before_output_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, target = root / 'source.gpkg', root / 'typed.gpkg'
            layer(source, 'mixed', [(GeometryCollection([box(139, 35, 140, 36)]), {'n': 1})])
            with self.assertRaisesRegex(ValueError, 'Unsupported geometry'):
                prepare_file(source, target)
            self.assertFalse(target.exists())

    def test_existing_destination_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / 'existing.gpkg'
            target.write_bytes(b'keep')
            with self.assertRaises(FileExistsError):
                prepare_file(root / 'missing.gpkg', target)
            self.assertEqual(target.read_bytes(), b'keep')
