"""Four-view retail sales dashboard with explicit data and aggregation contracts.
"""
import os
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from data_utils import (load_local_data, transaction_table, monthly_means,
                        promotion_difference, comparable_month_change, oil_daily,
                        MONTH_NAMES, WEEKDAYS)

ROOT = Path(__file__).parent
COLOURS = {'sales': '#288ad1', 'transactions': '#2ecc71', 'families': '#e67e22',
           'promotions': '#e74c3c', 'time': '#2ed0b0'}
PAGES = ['Global overview', 'Store analysis', 'State analysis', 'Exploratory insights']
st.set_page_config(page_title='Retail sales dashboard', page_icon='📊', layout='wide')


@st.cache_data
def load_csv(csv_path, metadata_path, csv_modified, metadata_modified):
    """Cache by local path and modification time; no downloads or remote access."""
    return load_local_data(csv_path, metadata_path)


def draw(figure):
    figure.update_layout(height=400)
    st.plotly_chart(figure, width='stretch')


def horizontal_ranking(values, sales_label, colour='Blues'):
    values = values.sort_values().tail(10)
    figure = px.bar(x=values.values, y=values.index.astype(str), orientation='h',
                    labels={'x': sales_label, 'y': ''}, text=values.values,
                    color=values.values, color_continuous_scale=colour)
    figure.update_traces(texttemplate='%{text:.3s}', textposition='outside')
    return figure


def global_overview(frame, sales_label):
    st.header('Global overview')
    columns = st.columns(4)
    for column, label, value in zip(columns, ['Stores', 'Product families', 'States', 'Observed months'],
                                    [frame.store_nbr.nunique(), frame.family.nunique(), frame.state.nunique(), frame.date.dt.to_period('M').nunique()]):
        column.metric(label, value)
    st.subheader('Sales totals and rankings')
    st.markdown('#### Top product families by total sales')
    draw(horizontal_ranking(frame.groupby('family').sales.sum().nlargest(10), sales_label, 'Oranges'))
    st.markdown('#### Total sales by store')
    totals = frame.groupby('store_nbr').sales.sum().sort_values(ascending=False)
    figure = px.bar(x=totals.index.astype(str), y=totals.values,
                    labels={'x': 'Store', 'y': sales_label}, color=totals.values, color_continuous_scale='Blues')
    draw(figure)
    st.markdown('#### Top stores: sales on rows with a promotion')
    promoted = frame.loc[frame.onpromotion.gt(0)].groupby('store_nbr').sales.sum().nlargest(10)
    if promoted.empty:
        st.info('No observations have a promotion in this selection.')
    else:
        promoted.index = ['Store ' + str(number) for number in promoted.index]
        draw(horizontal_ranking(promoted, sales_label, 'Reds'))
    st.caption('A row with onpromotion > 0 may include other sales. This is not isolated sales of promoted items.')
    st.subheader('Seasonal patterns')
    st.caption('These means are per observed store–family–day row, not total company sales per day. Missing months remain missing.')
    columns = st.columns(3)
    daily = frame.groupby('day_of_week').sales.mean().reindex(WEEKDAYS)
    weekly = frame.groupby('week').sales.mean().sort_index()
    monthly = monthly_means(frame)
    with columns[0]:
        figure = px.bar(x=WEEKDAYS, y=daily.values, labels={'x': 'Weekday', 'y': 'Mean ' + sales_label},
                        color_discrete_sequence=[COLOURS['sales']])
        draw(figure)
        st.info(f'Highest observed weekday mean: {daily.idxmax()}')
    with columns[1]:
        figure = px.line(x=weekly.index, y=weekly.values, markers=True,
                         labels={'x': 'ISO week number', 'y': 'Mean ' + sales_label})
        figure.update_traces(line_color=COLOURS['time'])
        draw(figure)
        st.info(f'Highest observed week mean: week {weekly.idxmax()}')
    with columns[2]:
        figure = px.bar(x=MONTH_NAMES, y=monthly.values, labels={'x': 'Month', 'y': 'Mean ' + sales_label},
                        color_discrete_sequence=[COLOURS['sales']])
        draw(figure)
        st.info(f'Highest observed month mean: {MONTH_NAMES[monthly.idxmax() - 1]}')


def store_analysis(frame, sales_label):
    st.header('Store analysis')
    selected = st.selectbox('Choose a store', sorted(frame.store_nbr.unique()), key='selected_store', index=None, placeholder='Select a store')
    if selected is None:
        st.info('Choose a store to see this view.')
        return
    subset = frame.loc[frame.store_nbr.eq(selected)]
    if subset.empty:
        st.info('No records match this store.')
        return
    columns = st.columns(4)
    for column, label, value in zip(columns, ['Total ' + sales_label, 'Product families', 'State', 'Store type'],
                                    [f'{subset.sales.sum():,.1f}', subset.family.nunique(), subset.state.iloc[0], subset.store_type.iloc[0]]):
        column.metric(label, value)
    columns = st.columns(2)
    with columns[0]:
        st.subheader('Total sales by year')
        totals = subset.groupby('year').sales.sum().sort_index()
        draw(px.bar(x=totals.index.astype(str), y=totals.values,
                    labels={'x': 'Year', 'y': sales_label}, text=totals.values,
                    color=totals.values, color_continuous_scale='Blues'))
    with columns[1]:
        st.subheader('Top five product families')
        draw(horizontal_ranking(subset.groupby('family').sales.sum().nlargest(5), sales_label, 'Oranges'))
    st.subheader('Families observed with a promotion')
    promoted = subset.loc[subset.onpromotion.gt(0)]
    count = promoted.family.nunique()
    st.metric('Families with at least one promotion row', count)
    st.metric('Share of observed families', f'{100 * count / subset.family.nunique():.1f}%')
    ranking = promoted.groupby('family').sales.sum().nlargest(3)
    if ranking.empty:
        st.info('No promotion rows in this store.')
    else:
        st.markdown('**Top three families by sales on promotion rows**')
        for rank, (family, sales) in enumerate(ranking.items(), 1):
            st.write(f'{rank}. {family}: {sales:,.1f} ({sales_label})')


def state_analysis(frame, metadata, sales_label):
    st.header('State analysis')
    selected = st.selectbox('Choose a state', sorted(frame.state.unique()), key='selected_state', index=None, placeholder='Select a state')
    if selected is None:
        st.info('Choose a state to see this view.')
        return
    subset = frame.loc[frame.state.eq(selected)]
    if subset.empty:
        st.info('No records match this state.')
        return
    transactions = transaction_table(subset, metadata['transactions_grain'])
    columns = st.columns(4)
    for column, label, value in zip(columns, ['Stores', 'Total ' + sales_label, 'Transactions', 'Cities'],
        [subset.store_nbr.nunique(), f'{subset.sales.sum():,.1f}',
         'Unverified' if transactions is None else f'{transactions.transactions.sum():,.0f}', subset.city.nunique()]):
        column.metric(label, value)
    st.subheader('Transactions by year')
    if transactions is None:
        st.info('Transaction totals are hidden until their grain is declared in the metadata file.')
    else:
        totals = transactions.groupby('year').transactions.sum().sort_index()
        figure = px.line(x=totals.index.astype(str), y=totals.values, markers=True,
                         labels={'x': 'Year', 'y': 'Transactions'})
        figure.update_traces(line_color=COLOURS['transactions'])
        draw(figure)
        st.dataframe(totals.rename('Transactions').rename_axis('Year').reset_index(), hide_index=True, width='stretch')
    columns = st.columns(2)
    with columns[0]:
        st.subheader('Store ranking by total sales')
        ranking = subset.groupby('store_nbr').sales.sum().nlargest(10)
        ranking.index = ['Store ' + str(number) for number in ranking.index]
        draw(horizontal_ranking(ranking, sales_label))
        for rank, (store, sales) in enumerate(ranking.head(3).items(), 1):
            st.write(f'{rank}. {store}: {sales:,.1f} ({sales_label})')
    with columns[1]:
        st.subheader('Leading product families')
        ranking = subset.groupby('family').sales.sum().nlargest(10)
        draw(horizontal_ranking(ranking, sales_label, 'Oranges'))
        st.info(f'Largest observed family total: {ranking.idxmax()}')


def exploratory_insights(frame, metadata, sales_label):
    st.header('Exploratory insights')
    st.caption('Descriptive associations only. Promotions, oil prices and sales may share confounders and time trends.')
    columns = st.columns(2)
    with columns[0]:
        st.subheader('Sales on promotion vs non-promotion rows')
        changes = promotion_difference(frame).head(10)
        if changes.empty:
            st.info('No family has both groups and a positive non-promotion mean.')
        else:
            draw(px.bar(x=changes.index, y=changes.values, color=changes.values,
                        labels={'x': 'Product family', 'y': 'Unadjusted difference in mean sales (%)'},
                        color_continuous_scale='Reds'))
            st.info(f'Largest observed difference: {changes.index[0]} ({changes.iloc[0]:+.1f}%). This is not a causal effect.')
    with columns[1]:
        st.subheader('Monthly sales totals')
        monthly = frame.groupby(frame.date.dt.to_period('M')).sales.sum().sort_index()
        periods = pd.period_range(monthly.index.min(), monthly.index.max(), freq='M')
        monthly = monthly.reindex(periods)
        figure = px.line(x=monthly.index.astype(str), y=monthly.values, markers=True,
                         labels={'x': 'Month', 'y': sales_label})
        figure.update_traces(line_color=COLOURS['time'], connectgaps=False)
        draw(figure)
        change, reason = comparable_month_change(frame)
        if change:
            st.info(f"Same-month change, {change['first']} to {change['last']}: {change['percentage']:+.1f}%.")
            st.caption('Both months have full date/store/family coverage and matching pairs. This is not adjusted for business conditions.')
        else:
            st.info(reason)
    st.subheader('Totals by store type')
    grouped = frame.groupby('store_type').agg(sales=('sales', 'sum'), stores=('store_nbr', 'nunique'))
    transactions = transaction_table(frame, metadata['transactions_grain'])
    grouped['transactions'] = transactions.groupby('store_type').transactions.sum() if transactions is not None else float('nan')
    grouped['sales_per_store'] = grouped.sales / grouped.stores
    grouped = grouped.rename(columns={'sales': 'Total ' + sales_label, 'stores': 'Stores', 'transactions': 'Transactions', 'sales_per_store': 'Sales per observed store'})
    st.dataframe(grouped, width='stretch')
    st.subheader('Sales calendar')
    calendar = frame.groupby(['year', 'month']).sales.sum().unstack().reindex(columns=range(1, 13))
    figure = px.imshow(calendar.to_numpy(dtype=float), x=MONTH_NAMES, y=calendar.index.astype(str),
                        labels={'x': 'Month', 'y': 'Year', 'color': sales_label}, color_continuous_scale='YlOrRd', aspect='auto')
    draw(figure)
    st.caption('Blank cells are unobserved months, not zero sales.')
    st.subheader('Daily oil-price and sales association')
    try:
        daily = oil_daily(frame)
    except ValueError as error:
        st.warning(str(error))
        return
    if daily.empty:
        st.info('No non-missing oil observations are available.')
        return
    columns = st.columns(2)
    varied = len(daily) >= 3 and daily.sales.nunique() > 1 and daily.dcoilwtico.nunique() > 1
    oil_label = 'Oil value (' + metadata['oil_unit'] + ')'
    with columns[0]:
        figure = px.scatter(daily, x='dcoilwtico', y='sales',
                            labels={'dcoilwtico': oil_label, 'sales': 'Daily total ' + sales_label},
                            trendline='ols' if varied else None)
        draw(figure)
        st.caption('The OLS line is an unadjusted descriptive fit, not a causal or forecasting model.')
    with columns[1]:
        monthly = daily.groupby(daily.date.dt.to_period('M')).dcoilwtico.mean().sort_index()
        periods = pd.period_range(monthly.index.min(), monthly.index.max(), freq='M')
        monthly = monthly.reindex(periods)
        figure = px.line(x=monthly.index.astype(str), y=monthly.values, markers=True,
                         labels={'x': 'Month', 'y': 'Mean ' + oil_label})
        figure.update_traces(connectgaps=False)
        draw(figure)
        if varied:
            correlation = daily.sales.corr(daily.dcoilwtico)
            st.info(f'Pearson correlation across observed days: {correlation:.3f} (n={len(daily)}).')
        else:
            st.info('Correlation is undefined or uninformative: too few observations or a constant variable.')


def main():
    custom_csv = os.environ.get('RETAIL_DATA_PATH')
    csv_path = Path(custom_csv) if custom_csv else ROOT / 'data/synthetic_sales.csv'
    configured_metadata = os.environ.get('RETAIL_METADATA_PATH')
    metadata_path = Path(configured_metadata) if configured_metadata else (None if custom_csv else ROOT / 'data/synthetic_metadata.json')
    try:
        frame, metadata = load_csv(str(csv_path), str(metadata_path) if metadata_path else None,
                                   csv_path.stat().st_mtime_ns if csv_path.exists() else 0,
                                   metadata_path.stat().st_mtime_ns if metadata_path and metadata_path.exists() else 0)
    except (ValueError, OSError, TypeError) as error:
        st.error(f'Cannot load the local dataset: {error}')
        st.stop()
    st.title('Retail sales dashboard')
    if metadata['synthetic']:
        st.warning('SYNTHETIC DEMONSTRATION — all records are fictitious. These are not results from a real retailer.')
    else:
        st.info('Local data supplied by the user. Source permissions, units and observation coverage require verification.')
    if frame.empty:
        st.info('The dataset contains no observations. Supply a non-empty authorised CSV or use the synthetic example.')
        st.stop()
    sales_label = 'Sales (' + metadata['sales_unit'] + ')'
    with st.sidebar:
        st.title('Retail sales')
        page = st.selectbox('View', PAGES, key='page')
        st.metric('Stores', frame.store_nbr.nunique())
        st.metric('Product families', frame.family.nunique())
        st.metric('States', frame.state.nunique())
        st.caption('Sales by product family, store and time')
        st.caption('Source: ' + metadata['source'])
    if metadata['transactions_grain'] == 'unknown':
        st.warning('Transaction grain is unverified; transaction totals are not displayed.')
    elif metadata['transactions_grain'] == 'date_store':
        st.caption('Transactions are declared daily store totals; repeated family rows are counted once per date/store after consistency checks.')
    else:
        st.caption('Metadata declares transactions additive per sales row. This assumption must match the source documentation.')
    if page == PAGES[0]:
        global_overview(frame, sales_label)
    elif page == PAGES[1]:
        store_analysis(frame, sales_label)
    elif page == PAGES[2]:
        state_analysis(frame, metadata, sales_label)
    elif page == PAGES[3]:
        exploratory_insights(frame, metadata, sales_label)
    st.caption('Streamlit and Plotly · descriptive analysis')


main()
