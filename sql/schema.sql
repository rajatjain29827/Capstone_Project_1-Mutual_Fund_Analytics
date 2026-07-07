-- Schema for Bluestock Mutual Funds Star Schema
-- Drops and creates core dimension and fact tables with PK/FK constraints

PRAGMA foreign_keys = OFF;

DROP TABLE IF EXISTS fact_performance;
DROP TABLE IF EXISTS fact_transactions;
DROP TABLE IF EXISTS fact_aum;
DROP TABLE IF EXISTS fact_nav;
DROP TABLE IF EXISTS dim_fund;
DROP TABLE IF EXISTS dim_date;

PRAGMA foreign_keys = ON;

-- Dimension: funds
CREATE TABLE dim_fund (
  fund_code TEXT PRIMARY KEY,
  fund_house TEXT,
  scheme_name TEXT,
  category TEXT,
  sub_category TEXT,
  plan_type TEXT,
  fund_manager TEXT,
  risk_category TEXT,
  sebi_category_code TEXT
);

-- Dimension: dates (surrogate key)
CREATE TABLE dim_date (
  date_id INTEGER PRIMARY KEY,
  full_date TEXT NOT NULL UNIQUE,
  year INTEGER,
  quarter INTEGER,
  month INTEGER,
  day INTEGER
);

-- Fact: NAV history
CREATE TABLE fact_nav (
  nav_id INTEGER PRIMARY KEY,
  fund_code TEXT NOT NULL,
  date_id INTEGER NOT NULL,
  nav REAL,
  nav_price REAL,
  nav_share_price REAL,
  source_file TEXT,
  UNIQUE(fund_code, date_id),
  FOREIGN KEY (fund_code) REFERENCES dim_fund(fund_code),
  FOREIGN KEY (date_id) REFERENCES dim_date(date_id)
);

-- Fact: AUM by fund (periodic snapshots)
CREATE TABLE fact_aum (
  aum_id INTEGER PRIMARY KEY,
  fund_code TEXT,
  date_id INTEGER NOT NULL,
  fund_house TEXT,
  aum_crore REAL,
  num_schemes INTEGER,
  source_file TEXT,
  UNIQUE(fund_code, date_id),
  FOREIGN KEY (fund_code) REFERENCES dim_fund(fund_code),
  FOREIGN KEY (date_id) REFERENCES dim_date(date_id)
);

-- Fact: Investor transactions
CREATE TABLE fact_transactions (
  transaction_row_id INTEGER PRIMARY KEY,
  investor_id TEXT,
  fund_code TEXT,
  date_id INTEGER NOT NULL,
  transaction_type TEXT,
  amount_inr REAL,
  state TEXT,
  city TEXT,
  city_tier TEXT,
  age_group TEXT,
  gender TEXT,
  annual_income_lakh REAL,
  payment_mode TEXT,
  kyc_status TEXT,
  source_file TEXT,
  FOREIGN KEY (fund_code) REFERENCES dim_fund(fund_code),
  FOREIGN KEY (date_id) REFERENCES dim_date(date_id)
);

-- Fact: Scheme performance / holdings (one of the performance sources)
CREATE TABLE fact_performance (
  performance_id INTEGER PRIMARY KEY,
  fund_code TEXT,
  date_id INTEGER NOT NULL,
  sector TEXT,
  weight_pct REAL,
  market_value_cr REAL,
  current_price_inr REAL,
  -- if using scheme-level performance rows include numeric fields below (optional)
  return_1yr_pct REAL,
  return_3yr_pct REAL,
  return_5yr_pct REAL,
  expense_ratio_pct REAL,
  source_file TEXT,
  UNIQUE(fund_code, date_id, sector),
  FOREIGN KEY (fund_code) REFERENCES dim_fund(fund_code),
  FOREIGN KEY (date_id) REFERENCES dim_date(date_id)
);

-- Useful indexes
CREATE INDEX IF NOT EXISTS idx_nav_fund_date ON fact_nav(fund_code, date_id);
CREATE INDEX IF NOT EXISTS idx_aum_fund_date ON fact_aum(fund_code, date_id);
CREATE INDEX IF NOT EXISTS idx_tx_state ON fact_transactions(state);
CREATE INDEX IF NOT EXISTS idx_perf_fund_date ON fact_performance(fund_code, date_id);

-- End of schema
