# Bluestock MF Data Dictionary

## Overview
This document describes cleaned tables, column types, business definitions, and sources.

---

## `dim_fund` (data/processed/01_fund_master.csv)
- fund_code (TEXT): AMFI code; primary key for funds.
- fund_house (TEXT): Asset manager name.
- scheme_name (TEXT): Full scheme name and plan.
- category (TEXT): Fund category (Large Cap, Mid Cap, Debt, etc.).
- sub_category (TEXT): More granular category.
- plan_type (TEXT): `Regular` or `Direct`.
- fund_manager (TEXT): Lead manager name.
- risk_category (TEXT): Qualitative risk label (Low, Moderate, High).
- sebi_category_code (TEXT): SEBI classification code.

## `dim_date`
- date_id (INTEGER): Surrogate key.
- full_date (TEXT, YYYY-MM-DD): Calendar date.
- year (INTEGER): Year.
- quarter (INTEGER): Quarter 1..4.
- month (INTEGER): Month number 1..12.
- day (INTEGER): Day of month.

## `fact_nav` (data/processed/02_nav_history.csv)
- nav_id (INTEGER): PK.
- fund_code (TEXT): FK -> `dim_fund(fund_code)`.
- date_id (INTEGER): FK -> `dim_date(date_id)`.
- nav (REAL): Net Asset Value per unit; must be > 0.
- nav_price (REAL): Optional alternate NAV measure.
- nav_share_price (REAL): Optional; sometimes present for ETFs.
- source_file (TEXT): Source CSV reference.

## `fact_aum` (data/processed/03_aum_by_fund_house.csv)
- aum_id (INTEGER): PK.
- fund_code (TEXT): Fund AMFI code when available.
- date_id (INTEGER): FK -> `dim_date`.
- fund_house (TEXT): Fund house name.
- aum_crore (REAL): Assets under management in crore INR.
- num_schemes (INTEGER): Number of schemes in the fund house.
- source_file (TEXT): Source CSV reference.

## `fact_transactions` (data/processed/08_investor_transactions.csv)
- transaction_row_id (INTEGER): PK.
- investor_id (TEXT): Investor identifier.
- fund_code (TEXT): AMFI code the transaction relates to.
- date_id (INTEGER): FK -> `dim_date`.
- transaction_type (TEXT): Standardised values: `SIP`, `Lumpsum`, `Redemption`.
- amount_inr (REAL): Transaction amount in INR; must be > 0.
- state (TEXT): Investor state.
- city (TEXT): City.
- city_tier (TEXT): City tier (T30, B30 etc.).
- age_group (TEXT): Age bracket.
- gender (TEXT): Male/Female/Other.
- annual_income_lakh (REAL): Annual income in lakhs.
- payment_mode (TEXT): UPI, Net Banking, Mandate, Cheque, etc.
- kyc_status (TEXT): `Verified`, `Pending`, `Rejected`.
- source_file (TEXT): Source CSV reference.

## `fact_performance` (data/processed/07_scheme_performance.csv or 09_portfolio_holdings.csv)
- performance_id (INTEGER): PK.
- fund_code (TEXT): AMFI code.
- date_id (INTEGER): FK -> `dim_date`.
- sector (TEXT): Holding sector (if holdings file used).
- weight_pct (REAL): Holding weight percent.
- market_value_cr (REAL): Market value in crore INR.
- current_price_inr (REAL): Current price.
- return_1yr_pct (REAL): 1-year return percent (scheme-level file).
- return_3yr_pct (REAL): 3-year return percent.
- return_5yr_pct (REAL): 5-year return percent.
- expense_ratio_pct (REAL): Expense ratio percent; expected range 0.1 - 2.5.
- source_file (TEXT): Source CSV reference.

---

## Sources and processing notes
- Source CSVs located in `data/raw/` and cleaned copies written to `data/processed/`.
- Dates standardised to `YYYY-MM-DD`. Monthly fields (e.g., `2022-01`) are mapped to first-of-month `YYYY-MM-01`.
- NAV forward-fill performed per `fund_code` to fill business days; weekends/holidays forward-filled using previous available NAV.
- Duplicate rows (exact key duplicates) are removed prior to DB load.
- Validation rules: `nav` > 0, `amount_inr` > 0, `expense_ratio_pct` between 0.1 and 2.5 (if present), `kyc_status` in (`Verified`,`Pending`,`Rejected`).

