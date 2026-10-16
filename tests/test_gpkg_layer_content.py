"""Keep style-only changes separate from changed feature bytes/attributes."""
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from compare_gpkg_layer_content import compare


class LayerContentTests(unittest.TestCase):
    def make_pair(self, root):
        left, right = root/'left.gpkg', root/'right.gpkg'
        with sqlite3.connect(left) as db:
            db.executescript('''
                CREATE TABLE gpkg_geometry_columns(table_name TEXT,column_name TEXT,geometry_type_name TEXT,srs_id INTEGER,z INTEGER,m INTEGER);
                INSERT INTO gpkg_geometry_columns VALUES ('zones','geom','MULTIPOLYGON',6668,0,0);
                CREATE TABLE gpkg_spatial_ref_sys(srs_id INTEGER,definition TEXT);
                INSERT INTO gpkg_spatial_ref_sys VALUES (6668,'JGD2011');
                CREATE TABLE zones(fid INTEGER PRIMARY KEY,geom MULTIPOLYGON,label TEXT);
                CREATE TABLE layer_styles(id INTEGER PRIMARY KEY,style TEXT);
                INSERT INTO layer_styles VALUES (1,'old');
            ''')
            db.execute('INSERT INTO zones VALUES (?,?,?)', (1, b'geometry bytes', '日本'))
        shutil.copyfile(left, right)
        return left, right

    def test_style_changes_do_not_require_rechecking_identical_feature_values(self):
        with tempfile.TemporaryDirectory() as temp:
            left, right = self.make_pair(Path(temp))
            with sqlite3.connect(right) as db:
                db.execute("UPDATE layer_styles SET style='new'")
            result = compare(left, right, 'zones')
            self.assertFalse(result['same_file'])
            self.assertFalse(result['same_style_table'])
            self.assertTrue(result['same_feature_values'])
            self.assertTrue(result['same_geometry_declaration'])

    def test_changed_geometry_is_detected_with_equal_row_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            left, right = self.make_pair(Path(temp))
            with sqlite3.connect(right) as db:
                db.execute('UPDATE zones SET geom=?', (b'changed geometry',))
            result = compare(left, right, 'zones')
            self.assertFalse(result['same_geometry_blobs'])
            self.assertFalse(result['same_feature_values'])
            self.assertTrue(result['same_attributes'])

    def test_changed_attributes_do_not_pass_as_identical_layers(self):
        with tempfile.TemporaryDirectory() as temp:
            left, right = self.make_pair(Path(temp))
            with sqlite3.connect(right) as db:
                db.execute("UPDATE zones SET label='別名'")
            result = compare(left, right, 'zones')
            self.assertTrue(result['same_geometry_blobs'])
            self.assertFalse(result['same_attributes'])
            self.assertFalse(result['same_feature_values'])

    def test_selection_reuses_only_the_matching_feature(self):
        with tempfile.TemporaryDirectory() as temp:
            left, right = self.make_pair(Path(temp))
            for path, geometry in [(left, b'original'), (right, b'changed')]:
                with sqlite3.connect(path) as db:
                    db.execute('INSERT INTO zones VALUES (?,?,?)', (2, geometry, '別区域'))
            selected = compare(left, right, 'zones', key_field='label', key_value='日本')
            self.assertTrue(selected['same_feature_values'])
            self.assertEqual(selected['left']['all_columns']['count'], 1)
            self.assertFalse(compare(left, right, 'zones')['same_feature_values'])

    def test_empty_selection_does_not_certify_feature_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            left, right = self.make_pair(Path(temp))
            with self.assertRaisesRegex(ValueError, 'No features match'):
                compare(left, right, 'zones', key_field='label', key_value='not present')
