# Bluestock MF Power BI Dashboard — Build Guide

## Prerequisites

1. **Power BI Desktop** installed (from Microsoft Store or powerbi.microsoft.com/desktop)
2. **SQLite ODBC Driver** (only if connecting via ODBC; otherwise use CSV import)

---

## Step 1: Launch Power BI & Load Data

### Option A: Import from CSVs (Recommended)

All pre-optimised CSV files are in `data/powerbi/`:

| File | Type |
|---|---|
| `dim_fund.csv` | Dimension — 40 funds |
| `dim_date.csv` | Dimension — 1,642 dates |
| `fact_nav.csv` | Fact — 46,000 NAV records |
| `fact_aum.csv` | Fact — AUM by fund house |
| `fact_transactions.csv` | Fact — 32,778 investor transactions |
| `fact_performance.csv` | Fact — scheme returns & ratios |
| `fact_holdings.csv` | Fact — portfolio holdings |
| `benchmark_indices.csv` | NIFTY 50 & NIFTY 100 levels |
| `agg_aum_monthly.csv` | Aggregated monthly AUM |
| `fund_scorecard_pbi.csv` | 40 funds with CAGR, Sharpe, StdDev, AUM |

**In Power BI Desktop:**
- `Home → Get Data → Text/CSV`
- Select all files from `data/powerbi/`
- Click **Transform Data** → ensure every column has the correct data type (especially `date_id` as Whole Number, dates as Date)

### Option B: SQLite ODBC

```
Connection string: Driver={SQLite3 ODBC Driver};Database=data/bluestock_mf.db
```

---

## Step 2: Create Relationships

Go to **Model** view and create these relationships:

| From | To | Cardinality |
|---|---|---|
| `fact_nav[fund_code]` | `dim_fund[amfi_code]` | Many:1 |
| `fact_nav[date_id]` | `dim_date[date_id]` | Many:1 |
| `fact_transactions[fund_code]` | `dim_fund[amfi_code]` | Many:1 |
| `fact_transactions[date_id]` | `dim_date[date_id]` | Many:1 |
| `fact_aum[date_id]` | `dim_date[date_id]` | Many:1 |
| `fund_scorecard_pbi[amfi_code]` | `dim_fund[amfi_code]` | Many:1 |

All cross-filter directions: **Single** (←).

---

## Step 3: Create Measures (DAX)

Open **Model → New measure** and add:

### KPI Measures

```dax
Total AUM Cr = SUMX(fact_aum, fact_aum[aum_crore])
SIP Inflows Cr = SUMX(fact_transactions, IF(fact_transactions[transaction_type]="SIP", fact_transactions[amount_inr], 0)) / 10000000
Total Folios = SUM(agg_folio[folio_count_crore])
Total Schemes = COUNTROWS(dim_fund)
Avg NAV = AVERAGE(fact_nav[nav])
Max NAV Date = MAX(fact_nav[date_id])
```

### Performance Measures

```dax
Avg CAGR 3yr = AVERAGE(fund_scorecard_pbi[CAGR_3yr])
Avg Sharpe = AVERAGE(fund_scorecard_pbi[Sharpe])
Avg StdDev = AVERAGE(fund_scorecard_pbi[StdDev_ann])
```

### Transaction Measures

```dax
SIP Amount = CALCULATE(SUM(fact_transactions[amount_inr]), fact_transactions[transaction_type]="SIP")
Lumpsum Amount = CALCULATE(SUM(fact_transactions[amount_inr]), fact_transactions[transaction_type]="Lumpsum")
Redemption Amount = CALCULATE(SUM(fact_transactions[amount_inr]), fact_transactions[transaction_type]="Redemption")
Avg SIP Age Group = AVERAGEX(VALUES(fact_transactions[age_group]), CALCULATE(SUM(fact_transactions[amount_inr]), fact_transactions[transaction_type]="SIP"))
Transaction Volume = COUNTROWS(fact_transactions)
```

### Benchmark Measures

```dax
NIFTY50 Return = 
    VAR Latest = MAX(benchmark_indices[date])
    VAR StartDate = EDATE(Latest, -36)
    VAR StartVal = CALCULATE(SUM(benchmark_indices[NIFTY50]), benchmark_indices[date]=StartDate)
    VAR EndVal = CALCULATE(SUM(benchmark_indices[NIFTY50]), benchmark_indices[date]=Latest)
    RETURN DIVIDE(EndVal-StartVal, StartVal)
```

---

## Step 4: Build Pages

### Page 1 — Industry Overview

**KPI Cards** (top row):
1. **Total AUM**: `Total AUM Cr` with format ₹0.00 "Cr" — displays ₹XX Cr
2. **SIP Inflows**: `SIP Inflows Cr` with format ₹0.00 "K Cr" — target ₹31K Cr
3. **Folios**: `Total Folios` with format 0.00 "Cr" — target 26.12 Cr
4. **Schemes**: `Total Schemes` with format 0 — target 1,908

**Chart 1 — Industry AUM Trend**: Stacked area chart
- X-axis: `dim_date[year_month]`
- Y-axis: `Total AUM Cr`
- Legend: none
- Filter: date between 2022–2025

**Chart 2 — AUM by AMC**: Horizontal bar chart
- Y-axis: `dim_fund[fund_house]`
- X-axis: `Total AUM Cr`
- Sort descending

### Page 2 — Fund Performance

**Chart 1 — Risk-Return Scatter**: Scatter chart
- X-axis: `fund_scorecard_pbi[CAGR_3yr]` (return)
- Y-axis: `fund_scorecard_pbi[StdDev_ann]` (risk)
- Size: `fund_scorecard_pbi[AUM_crore]` (AUM)
- Legend: `dim_fund[category]`
- Detail: `dim_fund[scheme_name]`

**Chart 2 — Fund Scorecard Table**: Table
- Columns: `scheme_name`, `CAGR_3yr`, `Sharpe`, `StdDev_ann`, `Max_DD`, `AUM_crore`
- Enable "Sort by column" on each numeric column

**Chart 3 — NAV vs Benchmark**: Line chart
- X-axis: `dim_date[full_date]`
- Y-axis: `fact_nav[nav]` and `benchmark_indices[NIFTY100]` (dual axis)
- Filter by selected fund via slicer

**Slicers** (right side):
- `dim_fund[fund_house]` — dropdown
- `dim_fund[category]` — dropdown
- `dim_fund[plan_type]` — tiles

### Page 3 — Investor Analytics

**Chart 1 — Transactions by State**: Bar chart
- X-axis: `fact_transactions[state]`
- Y-axis: sum of `fact_transactions[amount_inr]`

**Chart 2 — Transaction Type Split**: Donut chart
- Legend: `fact_transactions[transaction_type]`
- Values: sum of `fact_transactions[amount_inr]`

**Chart 3 — Age Group vs Avg SIP**: Clustered bar
- X-axis: `fact_transactions[age_group]`
- Y-axis: `Avg SIP Age Group`

**Chart 4 — Monthly Transaction Volume**: Line chart
- X-axis: `dim_date[year_month]`
- Y-axis: `Transaction Volume`

**Slicers** (top):
- `fact_transactions[state]` — dropdown
- `fact_transactions[age_group]` — dropdown
- `fact_transactions[city_tier]` — dropdown

### Page 4 — SIP & Market Trends

**Chart 1 — SIP vs NIFTY50 Dual Axis**: Combo chart
- Column: monthly SIP inflow from `agg_sip_monthly`
- Line: NIFTY 50 level from `benchmark_indices`
- Date range: 2022–2025

**Chart 2 — Category Inflow Heatmap**: Matrix visual
- Rows: `agg_category_inflows[category]`
- Columns: `agg_category_inflows[month]`
- Values: `agg_category_inflows[net_inflow_crore]`
- Enable heatmap formatting (conditional formatting by color scale)

**Chart 3 — Top 5 Categories FY25**: Bar chart
- Filter: `agg_category_inflows[financial_year]` = "FY25"
- X-axis: `agg_category_inflows[category]`
- Y-axis: sum of `agg_category_inflows[net_inflow_crore]`
- Top N = 5

---

## Step 5: Interactivity

### Drill-through

1. Right-click the **Fund Scorecard table** → **Create drill-through page**
2. Add `dim_fund[scheme_name]` and `dim_fund[amfi_code]` as drill-through fields
3. On the drill-through target page, add:
   - NAV line chart for selected fund vs benchmark
   - KPI cards (CAGR, Sharpe, Max DD)
   - Back button

### Tooltips

- For every visual: **Format → Tooltips → Enable**
- Add relevant measures (e.g., CAGR value on scatter points)

### Sync Slicers

- **View → Sync Slicers pane**
- Sync `fund_house`, `category`, `plan_type` slicers across pages 2–4

---

## Step 6: Theme & Branding

### Bluestock Colour Theme

```json
{
  "name": "Bluestock",
  "dataColors": ["#1E3A5F", "#2E86C1", "#3498DB", "#85C1E9", "#154360", "#2471A3", "#AED6F1", "#7FB3D8"],
  "background": "#F4F6F7",
  "foreground": "#1C2833",
  "tableAccent": "#1E3A5F",
  "visualStyles": {}
}
```

Save as `bluestock_theme.json` and import via **View → Themes → Browse for themes**.

### Logo

Place `assets/bluestock_logo.png` (create a simple 200x60 logo image or use a text box with blue background).

---

## Step 7: Export

### Save .pbix

`File → Save As → bluestock_mf_dashboard.pbix` → save to `reports/`

### Export to PDF

`File → Export → Export to PDF` → save as `reports/Dashboard.pdf`

### Export Page PNGs

For each page:
1. Navigate to page
2. Right-click canvas → **Export → Export as PNG**
3. Save as:
   - `reports/page1_industry_overview.png`
   - `reports/page2_fund_performance.png`
   - `reports/page3_investor_analytics.png`
   - `reports/page4_sip_trends.png`

---

## Appendix: SQLite ODBC Setup (Alternative)

1. Download & install SQLite ODBC driver from http://www.ch-werner.de/sqliteodbc/
2. Run as Admin:
   ```
   reg add "HKEY_LOCAL_MACHINE\SOFTWARE\ODBC\ODBC.INI\BluestockMF" /v Database /t REG_SZ /d "C:\path\to\bluestock_mf.db" /f
   ```
3. In Power BI: `Get Data → Other → ODBC → DSN=BluestockMF`
4. Select all tables
