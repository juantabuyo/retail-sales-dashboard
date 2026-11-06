# Dashboard views

These screenshots show the application with the bundled synthetic CSV and
metadata in a desktop browser. All figures describe fictitious records.

The [README](../README.md) shows Store analysis and Exploratory insights. The
two views below add the promotion and seasonal summaries and the state-level
transaction aggregation.

## Global overview

![Lower global overview section showing synthetic sales on promotion rows and observed weekday, week and month means](images/global-overview-macos-2026-10-26.png)

The visible lower section shows sales on rows with a promotion and seasonal
means. These are means per observed store–family–day row, not total daily
company sales. Missing months remain blank. Sales on a promotion row need not
be sales of promoted items alone.

## State analysis

![Lower state analysis section for Example North showing transaction totals and synthetic store and family rankings](images/state-analysis-macos-2026-10-26.png)

**State analysis → Example North**, lower visible section. The transaction table
uses the declared daily-store grain, so repeated family rows count once per
store and date. Year labels refer only to observed dates, not complete years.
The table reports 13,080 transactions in the included 2025 dates and 6,688 in
the included 2026 dates.

## Reproduce the views

After following the installation steps in the README, run this command from
the project folder on macOS or Linux to select the same bundled inputs:

```bash
RETAIL_DATA_PATH=data/synthetic_sales.csv \
RETAIL_METADATA_PATH=data/synthetic_metadata.json \
python -m streamlit run app.py --browser.gatherUsageStats=false
```

Open the local URL in a desktop browser. Use the **View** selector to visit
Global overview, Store analysis, State analysis and Exploratory insights. For
Store analysis select **1**; for State analysis select **Example North**.
Allow the charts to appear, then scroll to the section you want to capture.
The screenshots use a 1600 × 1100 viewport with the sidebar open; browser fonts
and versions may change the exact layout.

The screenshots show the visible scroll position rather than the whole page.
Some end labels
on horizontal bars are clipped by their chart areas; axes and explanatory text
remain visible. Some year axes use continuous scales and show fractional tick
labels between the observed integer years; those ticks are chart positions,
not additional reporting periods. No labels, values or layout were edited in
the image files.

`images/store-analysis.png` is a separate screenshot supplied with the original
coursework.
