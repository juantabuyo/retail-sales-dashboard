"""Checks for the aggregation risks and all four Streamlit views."""
import base64
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest
from data_utils import (load_local_data, validate_data, transaction_table, monthly_means,
                        promotion_difference, comparable_month_change)

ROOT = Path(__file__).resolve().parents[1]


class DataChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frame, cls.metadata = load_local_data(ROOT / 'data/synthetic_sales.csv', ROOT / 'data/synthetic_metadata.json')

    def test_repeated_daily_transactions_count_once_only_when_declared(self):
        daily = transaction_table(self.frame, 'date_store')
        self.assertEqual(len(daily), 93 * 4)
        self.assertEqual(self.frame.transactions.sum(), 3 * daily.transactions.sum())
        self.assertIsNone(transaction_table(self.frame, 'unknown'))
        self.assertEqual(transaction_table(self.frame, 'sales_row').transactions.sum(), self.frame.transactions.sum())

    def test_conflicting_daily_transaction_values_rejected(self):
        changed = self.frame.copy()
        changed.loc[0, 'transactions'] += 1
        with self.assertRaisesRegex(ValueError, 'Conflicting transaction'):
            transaction_table(changed, 'date_store')

    def test_sales_duplicate_grain_and_missing_schema_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate date/store/family'):
            validate_data(pd.concat([self.frame, self.frame.iloc[[0]]], ignore_index=True))
        with self.assertRaisesRegex(ValueError, 'Missing required columns'):
            validate_data(self.frame.drop(columns='sales'))

    def test_missing_months_remain_nan(self):
        monthly = monthly_means(self.frame)
        self.assertEqual(len(monthly), 12)
        self.assertTrue(np.isnan(monthly.loc[2]))
        self.assertTrue(np.isfinite(monthly.loc[1]))

    def test_comparable_complete_months_and_zero_baseline(self):
        change, reason = comparable_month_change(self.frame)
        self.assertIsNone(reason)
        self.assertEqual((change['first'], change['last']), ('2025-01', '2026-01'))
        totals = self.frame.groupby(self.frame.date.dt.to_period('M')).sales.sum()
        expected = (totals.loc['2026-01'] / totals.loc['2025-01'] - 1) * 100
        self.assertAlmostEqual(change['percentage'], expected)
        partial = self.frame.loc[self.frame.date.ne(pd.Timestamp('2026-01-31'))]
        self.assertIsNone(comparable_month_change(partial)[0])
        changed = self.frame.copy()
        changed.loc[changed.date.dt.to_period('M').eq('2025-01'), 'sales'] = 0
        self.assertIsNone(comparable_month_change(changed)[0])
        changed['sales'] = 0
        self.assertTrue(promotion_difference(changed).empty)


class ViewChecks(unittest.TestCase):
    def start(self):
        app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=30).run()
        self.assertEqual(len(app.exception), 0, [error.message for error in app.exception])
        return app

    def assert_charts(self, app, expected):
        charts = app.get('plotly_chart')
        self.assertEqual(len(charts), expected)
        for chart in charts:
            spec = json.loads(chart.proto.spec)
            self.assertGreater(len(spec['data']), 0)
            self.assertIn('layout', spec)
        self.assertEqual(len(app.exception), 0, [error.message for error in app.exception])

    def test_all_four_views_and_selectors(self):
        with patch.dict(os.environ, {'RETAIL_DATA_PATH': '', 'RETAIL_METADATA_PATH': ''}):
            app = self.start()
            self.assert_charts(app, 6)
            self.assertTrue(any('SYNTHETIC' in message.value for message in app.warning))
            app.selectbox(key='page').set_value('Store analysis').run()
            app.selectbox(key='selected_store').set_value(1).run()
            self.assert_charts(app, 2)
            for store in [1, 4]:
                app.selectbox(key='selected_store').set_value(store).run()
                self.assert_charts(app, 2)
            app.selectbox(key='selected_store').set_value(None).run()
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(any('Choose a store' in message.value for message in app.info))
            app.selectbox(key='page').set_value('State analysis').run()
            app.selectbox(key='selected_state').set_value('Example North').run()
            self.assert_charts(app, 3)
            app.selectbox(key='selected_state').set_value('Example South').run()
            self.assert_charts(app, 3)
            app.selectbox(key='selected_state').set_value(None).run()
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(any('Choose a state' in message.value for message in app.info))
            app.selectbox(key='page').set_value('Exploratory insights').run()
            self.assert_charts(app, 5)
            specs = [json.loads(chart.proto.spec) for chart in app.get('plotly_chart')]
            self.assertTrue(any(len(spec['data']) == 2 for spec in specs))
            self.assertTrue(any('Pearson correlation' in message.value for message in app.info))
            # The final monthly oil trace must preserve every missing calendar month.
            oil_trace = specs[-1]['data'][0]
            self.assertEqual(list(oil_trace['x']), list(pd.period_range('2025-01', '2026-01', freq='M').astype(str)))
            self.assertFalse(oil_trace['connectgaps'])
            encoded = oil_trace['y']
            values = (np.frombuffer(base64.b64decode(encoded['bdata']), dtype=encoded['dtype'])
                      if isinstance(encoded, dict) else np.asarray(encoded, dtype=float))
            self.assertEqual(list(np.flatnonzero(np.isfinite(values))), [0, 2, 12])
            self.assertTrue(np.isnan(values[1]))

    def test_zero_constant_and_missing_oil_views(self):
        frame = pd.read_csv(ROOT / 'data/synthetic_sales.csv')
        frame['sales'] = 0
        frame['onpromotion'] = 0
        frame['dcoilwtico'] = 60
        with tempfile.TemporaryDirectory() as temporary:
            csv = Path(temporary) / 'test.csv'
            frame.to_csv(csv, index=False)
            with patch.dict(os.environ, {'RETAIL_DATA_PATH': str(csv), 'RETAIL_METADATA_PATH': str(ROOT / 'data/synthetic_metadata.json')}):
                app = self.start()
                app.selectbox(key='page').set_value('Exploratory insights').run()
                self.assertEqual(len(app.exception), 0)
                self.assertTrue(any('zero or negative baseline' in message.value for message in app.info))
                self.assertTrue(any('Correlation is undefined' in message.value for message in app.info))
            frame['dcoilwtico'] = np.nan
            frame.to_csv(csv, index=False)
            with patch.dict(os.environ, {'RETAIL_DATA_PATH': str(csv), 'RETAIL_METADATA_PATH': str(ROOT / 'data/synthetic_metadata.json')}):
                app = self.start()
                app.selectbox(key='page').set_value('Exploratory insights').run()
                self.assertEqual(len(app.exception), 0)
                self.assertTrue(any('No non-missing oil' in message.value for message in app.info))

    def test_unknown_grain_empty_data_and_missing_file(self):
        with patch.dict(os.environ, {'RETAIL_DATA_PATH': str(ROOT / 'data/synthetic_sales.csv'), 'RETAIL_METADATA_PATH': ''}):
            app = self.start()
            app.selectbox(key='page').set_value('State analysis').run()
            app.selectbox(key='selected_state').set_value('Example North').run()
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(any('totals are hidden' in message.value for message in app.info))
        with tempfile.TemporaryDirectory() as temporary:
            csv = Path(temporary) / 'empty.csv'
            pd.read_csv(ROOT / 'data/synthetic_sales.csv').iloc[:0].to_csv(csv, index=False)
            with patch.dict(os.environ, {'RETAIL_DATA_PATH': str(csv), 'RETAIL_METADATA_PATH': ''}):
                app = self.start()
                self.assertTrue(any('contains no observations' in message.value for message in app.info))
            with patch.dict(os.environ, {'RETAIL_DATA_PATH': str(csv.with_name('missing.csv')), 'RETAIL_METADATA_PATH': ''}):
                app = self.start()
                self.assertTrue(any('does not exist' in message.value for message in app.error))


if __name__ == '__main__':
    unittest.main()
