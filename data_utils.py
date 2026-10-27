"""Local CSV validation and aggregation rules for the university dashboard."""
import calendar
import json
from pathlib import Path
import numpy as np
import pandas as pd

REQUIRED_COLUMNS = ['date', 'store_nbr', 'family', 'state', 'city', 'store_type',
                    'sales', 'transactions', 'onpromotion', 'dcoilwtico']
SALES_KEY = ['date', 'store_nbr', 'family']
MONTH_NAMES = list(calendar.month_abbr)[1:]
WEEKDAYS = list(calendar.day_name)


def validate_data(frame):
    """Require one sales observation per date/store/family; never sum duplicates silently."""
    missing = set(REQUIRED_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f'Missing required columns: {sorted(missing)}')
    frame = frame.copy()
    frame['date'] = pd.to_datetime(frame['date'], errors='coerce')
    if frame[SALES_KEY + ['state', 'city', 'store_type']].isna().any().any():
        raise ValueError('Dates and sales/store identity fields must not be missing.')
    if not frame['date'].eq(frame['date'].dt.normalize()).all():
        raise ValueError('This dashboard expects daily observations, not intraday timestamps.')
    for column in ['sales', 'transactions', 'onpromotion', 'dcoilwtico']:
        frame[column] = pd.to_numeric(frame[column], errors='raise')
        if np.isinf(frame[column]).any():
            raise ValueError(f'{column} contains an infinite value.')
    if frame[['sales', 'onpromotion']].isna().any().any():
        raise ValueError('Sales and promotion counts must not be missing.')
    if frame[['transactions', 'onpromotion']].lt(0).any().any():
        raise ValueError('Transaction and promotion counts must be non-negative.')
    if frame.duplicated(SALES_KEY).any():
        raise ValueError('Duplicate date/store/family rows: confirm the sales grain before aggregation.')
    for column in ['state', 'city', 'store_type']:
        if frame.groupby('store_nbr')[column].nunique().gt(1).any():
            raise ValueError(f'Store {column} changes within the file; a dated store mapping is required.')
    # Derive calendar fields from the actual date rather than trusting stale CSV helpers.
    frame['year'] = frame['date'].dt.year
    frame['month'] = frame['date'].dt.month
    frame['week'] = frame['date'].dt.isocalendar().week.astype(int)
    frame['day_of_week'] = frame['date'].dt.day_name()
    return frame


def load_local_data(csv_path, metadata_path=None):
    csv_path = Path(csv_path)
    if not csv_path.is_file():
        raise ValueError('The configured local CSV does not exist. No automatic download is attempted.')
    frame = pd.read_csv(csv_path, encoding='utf-8-sig', low_memory=False)
    frame = validate_data(frame)
    metadata = {'synthetic': False, 'source': 'Unverified local file',
                'sales_unit': 'source units (unverified)', 'oil_unit': 'source units (unverified)',
                'transactions_grain': 'unknown'}
    if metadata_path:
        metadata_path = Path(metadata_path)
        if not metadata_path.is_file():
            raise ValueError('The configured metadata file does not exist.')
        declared = json.loads(metadata_path.read_text())
        if not isinstance(declared, dict):
            raise ValueError('The metadata file must contain a JSON object.')
        metadata.update(declared)
    validate_metadata(metadata)
    transaction_table(frame, metadata['transactions_grain'])
    return frame, metadata


def validate_metadata(metadata):
    """Reject metadata whose types the application would otherwise fail on while rendering."""
    if not isinstance(metadata['synthetic'], bool):
        raise ValueError('Metadata "synthetic" must be a JSON boolean.')
    for field in ('source', 'sales_unit', 'oil_unit'):
        if not isinstance(metadata[field], str) or not metadata[field].strip():
            raise ValueError(f'Metadata "{field}" must be a non-empty string.')
    # A tuple, not a set: an unhashable JSON value (list or object) is then rejected like any other.
    if metadata['transactions_grain'] not in ('unknown', 'date_store', 'sales_row'):
        raise ValueError('transactions_grain must be unknown, date_store or sales_row.')


def transaction_table(frame, grain):
    """Return counts only when their meaning has been declared, then checked.

    date_store: the same daily shop total may repeat across family rows. Keep
    one value after confirming consistency. sales_row: counts are explicitly
    additive at the sales-row grain. unknown: do not report a transaction total.
    """
    if grain == 'unknown':
        return None
    if frame['transactions'].isna().any():
        raise ValueError('Declared transaction counts contain missing values.')
    if grain == 'sales_row':
        return frame[['date', 'store_nbr', 'state', 'store_type', 'year', 'transactions']].copy()
    if grain != 'date_store':
        raise ValueError('Unrecognised transaction grain.')
    grouped = frame.groupby(['date', 'store_nbr'])['transactions']
    if grouped.nunique().gt(1).any():
        raise ValueError('Conflicting transaction totals within a date/store: cannot deduplicate safely.')
    return frame.drop_duplicates(['date', 'store_nbr'])[
        ['date', 'store_nbr', 'state', 'store_type', 'year', 'transactions']].copy()


def monthly_means(frame):
    """Missing months remain missing, never fabricated zero-sales months."""
    return frame.groupby('month')['sales'].mean().reindex(range(1, 13))


def promotion_difference(frame):
    """Unadjusted difference in row means, not a treatment-effect estimate."""
    absent = frame.loc[frame.onpromotion.eq(0)].groupby('family')['sales'].mean()
    present = frame.loc[frame.onpromotion.gt(0)].groupby('family')['sales'].mean()
    comparison = pd.concat([absent.rename('without'), present.rename('with')], axis=1).dropna()
    comparison = comparison.loc[comparison['without'].gt(0)]
    return ((comparison['with'] - comparison['without']) / comparison['without'] * 100).sort_values(ascending=False)


def complete_months(frame):
    """A complete month covers each day for each observed store/family pair.

    This checks observation coverage, not whether the source recorded every sale.
    """
    result = {}
    for period, subset in frame.groupby(frame.date.dt.to_period('M')):
        pairs = set(map(tuple, subset[['store_nbr', 'family']].drop_duplicates().to_numpy()))
        if len(subset) == len(pairs) * period.days_in_month and subset.date.nunique() == period.days_in_month:
            result[period] = (float(subset.sales.sum()), pairs)
    return result


def comparable_month_change(frame):
    """Compare the same calendar month across years with identical observed pairs."""
    complete = complete_months(frame)
    for latest in sorted(complete, reverse=True):
        earlier = [period for period in complete if period < latest and period.month == latest.month
                   and complete[period][1] == complete[latest][1]]
        if earlier:
            first = min(earlier)
            baseline, current = complete[first][0], complete[latest][0]
            if baseline <= 0:
                return None, 'A comparable earlier month has a zero or negative baseline; no percentage is shown.'
            return {'first': str(first), 'last': str(latest), 'percentage': (current - baseline) / baseline * 100}, None
    return None, 'No two fully observed, matching calendar months with the same store/family coverage are available.'


def oil_daily(frame):
    """Compare daily sales with a daily source oil value; omit missing oil days."""
    known = frame.loc[frame.dcoilwtico.notna()]
    if known.groupby('date').dcoilwtico.nunique().gt(1).any():
        raise ValueError('Oil values differ within one date; clarify their grain before comparison.')
    daily = frame.groupby('date').agg(sales=('sales', 'sum'), dcoilwtico=('dcoilwtico', 'first')).dropna()
    return daily.reset_index()
