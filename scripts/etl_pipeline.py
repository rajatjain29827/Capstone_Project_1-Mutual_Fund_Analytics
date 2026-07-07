"""
Bluestock MF - ETL Pipeline

Usage:
    python scripts/etl_pipeline.py [--data-dir PATH] [--db-path PATH] [--log-level INFO]
                                   [--fetch-live] [--schedule] [--validate-only]

Reads raw CSVs from data/raw/, cleans, and loads into SQLite star schema.
Uses pathlib.Path everywhere - no hardcoded absolute paths.
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


def get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


PATHS = {
    "raw": "data/raw",
    "processed": "data/processed",
    "db": "data/db",
    "sql": "sql",
    "notebooks": "notebooks",
    "reports": "reports",
    "scripts": "scripts",
    "dashboard": "dashboard",
}


def setup_logging(level: str) -> logging.Logger:
    logger = logging.getLogger("etl")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    log_file = get_project_root() / f"etl_{datetime.now():%Y%m%d_%H%M%S}.log"
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.info("ETL started - log file: %s", log_file)
    return logger


EXPECTED_RAW_FILES = [
    "01_fund_master.csv",
    "02_nav_history.csv",
    "03_aum_by_fund_house.csv",
    "04_monthly_sip_inflows.csv",
    "05_category_inflows.csv",
    "06_industry_folio_count.csv",
    "07_scheme_performance.csv",
    "08_investor_transactions.csv",
    "09_portfolio_holdings.csv",
    "10_benchmark_indices.csv",
]


def read_raw_csv(path: Path, logger: logging.Logger) -> pd.DataFrame:
    try:
        df = pd.read_csv(path, encoding="utf-8", low_memory=False)
        logger.info("  Loaded %s - %d rows x %d cols", path.name, len(df), len(df.columns))
        return df
    except Exception as exc:
        logger.error("  Failed to load %s: %s", path.name, exc)
        raise


def build_dim_date(logger: logging.Logger) -> pd.DataFrame:
    date_range = pd.date_range("2022-01-01", "2026-12-31", freq="D")
    df = pd.DataFrame({"full_date": date_range})
    df["date_id"] = df["full_date"].dt.strftime("%Y%m%d").astype(int)
    df["year"] = df["full_date"].dt.year
    df["quarter"] = df["full_date"].dt.quarter
    df["month"] = df["full_date"].dt.month
    df["day"] = df["full_date"].dt.day
    df["full_date"] = df["full_date"].dt.strftime("%Y-%m-%d")
    logger.info("  Built dim_date - %d rows", len(df))
    return df


def build_dim_fund(df: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    cols = {
        "amfi_code": "fund_code",
        "fund_house": "fund_house",
        "scheme_name": "scheme_name",
        "category": "category",
        "sub_category": "sub_category",
        "plan": "plan_type",
        "fund_manager": "fund_manager",
        "risk_category": "risk_category",
        "sebi_category_code": "sebi_category_code",
    }
    rename = {k: v for k, v in cols.items() if k in df.columns}
    out = df[list(rename.keys())].rename(columns=rename).copy()
    out["fund_code"] = out["fund_code"].astype(str)
    logger.info("  Built dim_fund - %d rows", len(out))
    return out


def build_fact_nav(
    df_nav: pd.DataFrame,
    dim_fund: pd.DataFrame,
    dim_date: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    df = df_nav.copy()
    df["fund_code"] = df["amfi_code"].astype(str)
    df["date"] = pd.to_datetime(df["date"])
    df["date_id"] = df["date"].dt.strftime("%Y%m%d").astype(int)
    df["nav"] = pd.to_numeric(df["nav"], errors="coerce")

    valid_funds = set(dim_fund["fund_code"])
    df = df[df["fund_code"].isin(valid_funds)].copy()
    valid_dates = set(dim_date["date_id"])
    df = df[df["date_id"].isin(valid_dates)].copy()

    full_dates = dim_date[["date_id", "full_date"]].copy()
    full_dates["date"] = pd.to_datetime(full_dates["full_date"])

    filled_parts = []
    for code, grp in df.groupby("fund_code"):
        grp = grp.drop_duplicates(subset=["date_id"]).set_index("date_id")
        grp = grp.reindex(full_dates["date_id"])
        grp["fund_code"] = code
        grp["nav"] = grp["nav"].ffill()
        grp["nav_price"] = grp["nav"]
        grp["nav_share_price"] = grp["nav"]
        grp["source_file"] = "02_nav_history.csv"
        filled_parts.append(grp.reset_index())

    if filled_parts:
        out = pd.concat(filled_parts, ignore_index=True)
    else:
        out = pd.DataFrame(columns=["date_id", "fund_code", "nav", "nav_price", "nav_share_price", "source_file"])

    out = out.dropna(subset=["nav"])
    out = out[["fund_code", "date_id", "nav", "nav_price", "nav_share_price", "source_file"]]
    logger.info("  Built fact_nav - %d rows (after ffill)", len(out))
    return out


def build_fact_aum(
    df_aum: pd.DataFrame,
    dim_date: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    df = df_aum.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["date_id"] = df["date"].dt.strftime("%Y%m%d").astype(int)
    df["fund_code"] = "FH_" + df["fund_house"].str.replace(r"\s+", "_", regex=True)
    df["aum_crore"] = pd.to_numeric(df["aum_crore"], errors="coerce")
    df["num_schemes"] = pd.to_numeric(df["num_schemes"], errors="coerce").fillna(0).astype(int)
    df["source_file"] = "03_aum_by_fund_house.csv"

    valid_dates = set(dim_date["date_id"])
    df = df[df["date_id"].isin(valid_dates)].copy()
    df = df[["fund_code", "date_id", "fund_house", "aum_crore", "num_schemes", "source_file"]]

    logger.info("  Built fact_aum - %d rows", len(df))
    return df


def build_fact_transactions(
    df_tx: pd.DataFrame,
    dim_fund: pd.DataFrame,
    dim_date: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    df = df_tx.copy()
    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    df["date_id"] = df["transaction_date"].dt.strftime("%Y%m%d").astype(int)
    df["fund_code"] = df["amfi_code"].astype(str)

    valid_funds = set(dim_fund["fund_code"])
    df = df[df["fund_code"].isin(valid_funds)].copy()
    valid_dates = set(dim_date["date_id"])
    df = df[df["date_id"].isin(valid_dates)].copy()

    df["source_file"] = "08_investor_transactions.csv"
    tx_cols = ["investor_id", "fund_code", "date_id", "transaction_type", "amount_inr",
               "state", "city", "city_tier", "age_group", "gender", "annual_income_lakh",
               "payment_mode", "kyc_status", "source_file"]
    df = df[[c for c in tx_cols if c in df.columns]]
    logger.info("  Built fact_transactions - %d rows", len(df))
    return df


def build_fact_performance(
    df_perf: pd.DataFrame,
    df_holdings: pd.DataFrame,
    dim_fund: pd.DataFrame,
    dim_date: pd.DataFrame,
    logger: logging.Logger,
) -> pd.DataFrame:
    parts = []

    if df_perf is not None and not df_perf.empty:
        p = df_perf.copy()
        p["fund_code"] = p["amfi_code"].astype(str)
        latest_date_id = dim_date["date_id"].max()
        p["date_id"] = latest_date_id
        p["sector"] = "_SCHEME_LEVEL_"
        p["weight_pct"] = None
        p["market_value_cr"] = None
        p["current_price_inr"] = None
        for col in ["return_1yr_pct", "return_3yr_pct", "return_5yr_pct", "expense_ratio_pct"]:
            if col in p.columns:
                p[col] = pd.to_numeric(p[col], errors="coerce")
        cols_out = [
            "fund_code", "date_id", "sector", "weight_pct", "market_value_cr",
            "current_price_inr", "return_1yr_pct", "return_3yr_pct", "return_5yr_pct",
            "expense_ratio_pct",
        ]
        p = p[[c for c in cols_out if c in p.columns]]
        for c in ["return_1yr_pct", "return_3yr_pct", "return_5yr_pct", "expense_ratio_pct"]:
            if c not in p.columns:
                p[c] = None
        valid_funds = set(dim_fund["fund_code"])
        p = p[p["fund_code"].isin(valid_funds)].copy()
        p["source_file"] = "07_scheme_performance.csv"
        parts.append(p)

    if df_holdings is not None and not df_holdings.empty:
        h = df_holdings.copy()
        h["fund_code"] = h["amfi_code"].astype(str)
        h["portfolio_date"] = pd.to_datetime(h["portfolio_date"])
        h["date_id"] = h["portfolio_date"].dt.strftime("%Y%m%d").astype(int)
        h["weight_pct"] = pd.to_numeric(h["weight_pct"], errors="coerce")
        h["market_value_cr"] = pd.to_numeric(h["market_value_cr"], errors="coerce")
        h["current_price_inr"] = pd.to_numeric(h["current_price_inr"], errors="coerce")
        valid_funds = set(dim_fund["fund_code"])
        h = h[h["fund_code"].isin(valid_funds)].copy()
        valid_dates = set(dim_date["date_id"])
        h = h[h["date_id"].isin(valid_dates)].copy()
        h["return_1yr_pct"] = None
        h["return_3yr_pct"] = None
        h["return_5yr_pct"] = None
        h["expense_ratio_pct"] = None
        h["source_file"] = "09_portfolio_holdings.csv"
        cols_h = [
            "fund_code", "date_id", "sector", "weight_pct", "market_value_cr",
            "current_price_inr", "return_1yr_pct", "return_3yr_pct", "return_5yr_pct",
            "expense_ratio_pct", "source_file",
        ]
        parts.append(h[cols_h])

    perf_cols = ["fund_code", "date_id", "sector", "weight_pct", "market_value_cr",
                 "current_price_inr", "return_1yr_pct", "return_3yr_pct", "return_5yr_pct",
                 "expense_ratio_pct", "source_file"]
    if parts:
        out = pd.concat(parts, ignore_index=True)
        out = out[[c for c in perf_cols if c in out.columns]]
    else:
        out = pd.DataFrame(columns=perf_cols)

    logger.info("  Built fact_performance - %d rows", len(out))
    return out


def load_to_sqlite(
    db_path: Path,
    schema_path: Path,
    dim_fund_df: pd.DataFrame,
    dim_date_df: pd.DataFrame,
    fact_nav_df: pd.DataFrame,
    fact_aum_df: pd.DataFrame,
    fact_tx_df: pd.DataFrame,
    fact_perf_df: pd.DataFrame,
    logger: logging.Logger,
) -> None:
    from sqlalchemy import create_engine, text

    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}")
    logger.info("  Connected to SQLite: %s", db_path)

    ddl = schema_path.read_text(encoding="utf-8")
    statements = []
    current = []
    for line in ddl.split("\n"):
        if line.strip().startswith("--"):
            continue
        current.append(line)
        if ";" in line:
            stmt = " ".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
    if current:
        stmt = " ".join(current).strip()
        if stmt:
            statements.append(stmt)
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))
    logger.info("  Schema DDL executed - all tables created")

    dim_fund_df = dim_fund_df.drop_duplicates(subset=["fund_code"]).copy()
    dim_date_df = dim_date_df.drop_duplicates(subset=["date_id"]).copy()

    if fact_aum_df is not None and not fact_aum_df.empty:
        existing_codes = set(dim_fund_df["fund_code"])
        fh_codes = fact_aum_df[["fund_code", "fund_house"]].drop_duplicates()
        new_fh = fh_codes[~fh_codes["fund_code"].isin(existing_codes)].copy()
        if not new_fh.empty:
            new_fh["scheme_name"] = new_fh["fund_house"]
            for col in ["category", "sub_category", "plan_type", "fund_manager", "risk_category", "sebi_category_code"]:
                new_fh[col] = None
            dim_fund_df = pd.concat([dim_fund_df, new_fh], ignore_index=True)
            logger.info("  Added %d fund_house entries to dim_fund", len(new_fh))

    dim_fund_df.to_sql("dim_fund", engine, if_exists="append", index=False, chunksize=500)
    logger.info("  Inserted %d rows into dim_fund", len(dim_fund_df))

    dim_date_df.to_sql("dim_date", engine, if_exists="append", index=False, chunksize=500)
    logger.info("  Inserted %d rows into dim_date", len(dim_date_df))

    for name, df, unique_cols in [
        ("fact_nav", fact_nav_df, ["fund_code", "date_id"]),
        ("fact_aum", fact_aum_df, ["fund_code", "date_id"]),
        ("fact_transactions", fact_tx_df, None),
        ("fact_performance", fact_perf_df, ["fund_code", "date_id", "sector"]),
    ]:
        if df is not None and not df.empty:
            if unique_cols:
                before = len(df)
                df = df.drop_duplicates(subset=unique_cols)
                if len(df) < before:
                    logger.info("  Removed %d duplicate rows from %s", before - len(df), name)
            df.to_sql(name, engine, if_exists="append", index=False, chunksize=500)
            logger.info("  Inserted %d rows into %s", len(df), name)
        else:
            logger.warning("  No data to insert into %s", name)

    index_sql = [
        "CREATE INDEX IF NOT EXISTS idx_nav_fund_date ON fact_nav(fund_code, date_id);",
        "CREATE INDEX IF NOT EXISTS idx_aum_fund_date ON fact_aum(fund_code, date_id);",
        "CREATE INDEX IF NOT EXISTS idx_tx_state ON fact_transactions(state);",
        "CREATE INDEX IF NOT EXISTS idx_perf_fund_date ON fact_performance(fund_code, date_id);",
    ]
    with engine.begin() as conn:
        for stmt in index_sql:
            conn.execute(text(stmt))
    logger.info("  Indexes created")

    engine.dispose()


def run_validation(db_path: Path, queries_path: Path, logger: logging.Logger) -> bool:
    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{db_path}")
    logger.info("  Running validation queries...")

    queries_txt = queries_path.read_text(encoding="utf-8")
    all_ok = True
    current = []
    for line in queries_txt.split("\n"):
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        current.append(line)
        if ";" in line:
            q = " ".join(current).strip()
            if q:
                try:
                    with engine.connect() as conn:
                        result = conn.execute(text(q))
                        rows = result.fetchall()
                        logger.info("  Query - returned %d rows", len(rows))
                except Exception as exc:
                    logger.warning("  Query - FAILED: %s", exc)
                    all_ok = False
            current = []

    engine.dispose()
    return all_ok


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bluestock MF ETL Pipeline")
    parser.add_argument("--data-dir", default=None, help="Override data directory (default: <project>/data)")
    parser.add_argument("--db-path", default=None, help="Override database path (default: <project>/data/db/bluestock_mf.db)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--fetch-live", action="store_true", help="Fetch latest NAV data before ETL")
    parser.add_argument("--schedule", action="store_true", help="Run in schedule mode (cron-like loop)")
    parser.add_argument("--validate-only", action="store_true", help="Only run validation against existing DB")
    return parser.parse_args()


def run_etl(
    raw_dir: Path,
    db_path: Path,
    schema_path: Path,
    queries_path: Path,
    logger: logging.Logger,
    fetch_live: bool = False,
) -> bool:
    start = time.time()
    logger.info("=" * 60)
    logger.info("ETL Pipeline - raw: %s  ->  db: %s", raw_dir, db_path)
    logger.info("=" * 60)

    if fetch_live:
        logger.info("Step 0 - Fetching live NAV data...")
        try:
            from scripts.live_nav_fetch import main as fetch_main
            fetch_main()
            logger.info("  Live NAV fetch complete")
        except Exception as exc:
            logger.warning("  Live NAV fetch skipped: %s", exc)

    logger.info("Step 1 - Loading raw CSVs...")
    loaded = {}
    for fname in EXPECTED_RAW_FILES:
        path = raw_dir / fname
        if path.exists():
            loaded[fname] = read_raw_csv(path, logger)
        else:
            logger.warning("  File not found (skipping): %s", fname)

    if not loaded:
        logger.error("No raw data files found at %s", raw_dir)
        return False

    logger.info("Step 2 - Building dimensions...")
    dim_date_df = build_dim_date(logger)
    fund_master = loaded.get("01_fund_master.csv")
    if fund_master is None:
        logger.error("fund_master.csv is required but missing")
        return False
    dim_fund_df = build_dim_fund(fund_master, logger)

    logger.info("Step 3 - Building fact tables...")
    fact_nav_df = build_fact_nav(
        loaded.get("02_nav_history.csv", pd.DataFrame()),
        dim_fund_df, dim_date_df, logger,
    )
    fact_aum_df = build_fact_aum(
        loaded.get("03_aum_by_fund_house.csv", pd.DataFrame()),
        dim_date_df, logger,
    )
    fact_tx_df = build_fact_transactions(
        loaded.get("08_investor_transactions.csv", pd.DataFrame()),
        dim_fund_df, dim_date_df, logger,
    )
    fact_perf_df = build_fact_performance(
        loaded.get("07_scheme_performance.csv"),
        loaded.get("09_portfolio_holdings.csv"),
        dim_fund_df, dim_date_df, logger,
    )

    logger.info("Step 4 - Loading into SQLite...")
    try:
        load_to_sqlite(
            db_path, schema_path,
            dim_fund_df, dim_date_df,
            fact_nav_df, fact_aum_df, fact_tx_df, fact_perf_df,
            logger,
        )
    except Exception as exc:
        logger.error("SQLite load failed: %s", exc)
        return False

    logger.info("Step 5 - Running validation...")
    ok = run_validation(db_path, queries_path, logger)

    elapsed = time.time() - start
    status = "PASS" if ok else "PASS_WITH_WARNINGS"
    logger.info("=" * 60)
    logger.info("ETL complete - %s - elapsed: %.1f seconds", status, elapsed)
    logger.info("=" * 60)
    return True


def main() -> int:
    args = parse_args()
    logger = setup_logging(args.log_level)
    root = get_project_root()

    data_dir = Path(args.data_dir) if args.data_dir else root / "data"
    db_path = Path(args.db_path) if args.db_path else data_dir / "db" / "bluestock_mf.db"
    raw_dir = data_dir / "raw"
    schema_path = root / "sql" / "schema.sql"
    queries_path = root / "sql" / "queries.sql"

    if args.validate_only:
        if not db_path.exists():
            logger.error("Database not found at %s", db_path)
            return 1
        ok = run_validation(db_path, queries_path, logger)
        return 0 if ok else 1

    if args.schedule:
        logger.info("Schedule mode enabled - watching for 8 PM weekday trigger")
        import schedule as sched_lib

        def job():
            logger.info("Scheduled ETL trigger at %s", datetime.now())
            run_etl(raw_dir, db_path, schema_path, queries_path, logger, fetch_live=True)

        sched_lib.every().day.at("20:00").do(job)
        while True:
            sched_lib.run_pending()
            time.sleep(60)

    ok = run_etl(raw_dir, db_path, schema_path, queries_path, logger, args.fetch_live)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
