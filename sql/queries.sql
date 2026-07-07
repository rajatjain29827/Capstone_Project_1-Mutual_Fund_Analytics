-- Analytical queries for Bluestock MF dataset

-- 1) Top 5 funds by latest AUM
SELECT a.fund_code, f.scheme_name, a.aum_crore
FROM fact_aum a
JOIN dim_fund f ON a.fund_code = f.fund_code
JOIN dim_date d ON a.date_id = d.date_id
WHERE d.date_id = (SELECT MAX(date_id) FROM dim_date)
ORDER BY a.aum_crore DESC
LIMIT 5;

-- 2) Average NAV per fund per month
SELECT f.fund_code, f.scheme_name, d.year, d.month, AVG(fn.nav) AS avg_nav
FROM fact_nav fn
JOIN dim_fund f ON fn.fund_code = f.fund_code
JOIN dim_date d ON fn.date_id = d.date_id
GROUP BY f.fund_code, d.year, d.month
ORDER BY f.fund_code, d.year, d.month;

-- 3) SIP YoY growth: compare total SIP inflows by month (sum amounts where transaction_type='SIP')
SELECT d.year, d.month,
  SUM(CASE WHEN ft.transaction_type = 'SIP' THEN ft.amount_inr ELSE 0 END) AS sip_total
FROM fact_transactions ft
JOIN dim_date d ON ft.date_id = d.date_id
GROUP BY d.year, d.month
ORDER BY d.year, d.month;

-- 4) Transactions by state (counts and total amount)
SELECT ft.state, COUNT(*) AS txn_count, SUM(ft.amount_inr) AS total_amount
FROM fact_transactions ft
GROUP BY ft.state
ORDER BY total_amount DESC;

-- 5) Funds with expense_ratio < 1%
SELECT DISTINCT f.fund_code, f.scheme_name, p.expense_ratio_pct
FROM fact_performance p
JOIN dim_fund f ON p.fund_code = f.fund_code
WHERE p.expense_ratio_pct < 1.0
ORDER BY p.expense_ratio_pct ASC;

-- 6) Top 5 funds by NAV volatility (std dev of monthly NAV)
WITH nav_monthly AS (
  SELECT fn.fund_code, d.year, d.month, AVG(fn.nav) AS avg_nav
  FROM fact_nav fn JOIN dim_date d ON fn.date_id = d.date_id
  GROUP BY fn.fund_code, d.year, d.month
)
SELECT nm.fund_code, f.scheme_name, (AVG((nm.avg_nav - m.avg_nav)*(nm.avg_nav - m.avg_nav))) AS nav_variance
FROM (
  SELECT fund_code, AVG(avg_nav) AS avg_nav FROM nav_monthly GROUP BY fund_code
) m
JOIN nav_monthly nm ON m.fund_code = nm.fund_code
JOIN dim_fund f ON nm.fund_code = f.fund_code
GROUP BY nm.fund_code
ORDER BY nav_variance DESC
LIMIT 5;

-- 7) Funds with highest 1-year return (using fact_performance.return_1yr_pct)
SELECT f.fund_code, f.scheme_name, p.return_1yr_pct
FROM fact_performance p
JOIN dim_fund f ON p.fund_code = f.fund_code
WHERE p.return_1yr_pct IS NOT NULL
ORDER BY p.return_1yr_pct DESC
LIMIT 10;

-- 8) Average expense ratio by risk category
SELECT f.risk_category, ROUND(AVG(p.expense_ratio_pct), 2) AS avg_expense_ratio,
       COUNT(DISTINCT f.fund_code) AS fund_count
FROM fact_performance p
JOIN dim_fund f ON p.fund_code = f.fund_code
WHERE p.expense_ratio_pct IS NOT NULL
GROUP BY f.risk_category
ORDER BY avg_expense_ratio DESC;

-- 9) Top 10 investors by total investment amount
SELECT ft.investor_id, SUM(ft.amount_inr) AS total_invested
FROM fact_transactions ft
GROUP BY ft.investor_id
ORDER BY total_invested DESC
LIMIT 10;

-- 10) Funds with most unique investor counts
SELECT ft.fund_code, f.scheme_name, COUNT(DISTINCT ft.investor_id) AS unique_investors
FROM fact_transactions ft
JOIN dim_fund f ON ft.fund_code = f.fund_code
GROUP BY ft.fund_code
ORDER BY unique_investors DESC
LIMIT 10;
