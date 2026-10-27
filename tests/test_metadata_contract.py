"""Regression tests: metadata types are validated before any view is rendered."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from data_utils import load_local_data

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / 'data/synthetic_sales.csv'
VALID = json.loads((ROOT / 'data/synthetic_metadata.json').read_text())


class MetadataContract(unittest.TestCase):
    def write_metadata(self, directory, **changes):
        path = Path(directory) / 'metadata.json'
        path.write_text(json.dumps({**VALID, **changes}))
        return path

    def test_valid_metadata_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            _, metadata = load_local_data(CSV, self.write_metadata(directory))
        self.assertEqual(metadata['sales_unit'], VALID['sales_unit'])

    def test_wrong_types_are_rejected_with_a_clear_error(self):
        for changes in ({'sales_unit': 5}, {'oil_unit': ['index']}, {'source': None},
                        {'source': '  '}, {'synthetic': 'false'}):
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    load_local_data(CSV, self.write_metadata(directory, **changes))

    def test_unhashable_grain_and_non_object_files_are_rejected_with_value_error(self):
        for changes in ({'transactions_grain': ['date_store']}, {'transactions_grain': {'a': 1}},
                        {'transactions_grain': 3}):
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    load_local_data(CSV, self.write_metadata(directory, **changes))
        for content in ('[]', '"text"', 'null', '3'):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'metadata.json'
                path.write_text(content)
                with self.assertRaisesRegex(ValueError, 'JSON object'):
                    load_local_data(CSV, path)

    def test_app_reports_invalid_metadata_instead_of_raising(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = {'RETAIL_DATA_PATH': str(CSV),
                           'RETAIL_METADATA_PATH': str(self.write_metadata(directory, sales_unit=5))}
            with patch.dict(os.environ, environment):
                app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=60).run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any('sales_unit' in error.value for error in app.error))


if __name__ == '__main__':
    unittest.main()
