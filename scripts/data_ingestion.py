import pandas as pd
from pathlib import Path


def get_repo_root() -> Path:
    script_dir = Path(__file__).resolve().parent
    return next(p for p in [script_dir] + list(script_dir.parents) if (p / ".git").exists())


def load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8")


def print_dataframe_overview(name: str, df: pd.DataFrame) -> None:
    print(f"\n=== {name} ===")
    print("shape:", df.shape)
    print("dtypes:")
    print(df.dtypes)
    print("head:")
    print(df.head())


def print_unique_values(df: pd.DataFrame, column: str) -> None:
    values = df[column].dropna().unique()
    print(f"\nUnique values in '{column}' ({len(values)}):")
    for value in sorted(values):
        print(" ", value)


def main() -> None:
    repo_root = get_repo_root()
    raw_dir = repo_root / "data" / "raw"

    expected_files = [
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

    print("Repo root:", repo_root)
    print("Raw folder:", raw_dir)

    loaded = {}
    missing_files = []
    for filename in expected_files:
        path = raw_dir / filename
        if not path.exists():
            missing_files.append(filename)
            continue
        df = load_csv(path)
        loaded[filename] = df
        print_dataframe_overview(filename, df)

    if missing_files:
        print("\nMissing expected files:", missing_files)
    else:
        print("\nAll expected raw files were found.")

    if "01_fund_master.csv" in loaded:
        fund_master = loaded["01_fund_master.csv"]
        print("\n=== Fund master exploration ===")
        for column in ["fund_house", "category", "sub_category", "risk_category"]:
            if column in fund_master.columns:
                print_unique_values(fund_master, column)
            else:
                print(f"\nColumn not found in fund_master: '{column}'")

        if "amfi_code" in fund_master.columns:
            codes = fund_master["amfi_code"].dropna().astype(str)
            print("\nFund master AMFI code structure:")
            print(" total scheme rows:", len(codes))
            print(" unique AMFI codes:", codes.nunique())
            print(" code lengths:", sorted(set(len(code) for code in codes)))
            print(" sample codes:", list(codes.head(10)))
        else:
            print("\nfund_master is missing 'amfi_code' column")

    if "01_fund_master.csv" in loaded and "02_nav_history.csv" in loaded:
        fund_master = loaded["01_fund_master.csv"]
        nav_history = loaded["02_nav_history.csv"]
        if "amfi_code" in fund_master.columns and "amfi_code" in nav_history.columns:
            master_codes = set(fund_master["amfi_code"].dropna().astype(str))
            nav_codes = set(nav_history["amfi_code"].dropna().astype(str))
            missing_codes = sorted(master_codes - nav_codes)
            print("\n=== AMFI validation ===")
            print(" fund_master AMFI codes:", len(master_codes))
            print(" nav_history AMFI codes:", len(nav_codes))
            print(" missing in nav_history:", len(missing_codes))
            if missing_codes:
                print(" first missing:", missing_codes[:10])
                print(" Data quality note: some fund_master AMFI codes are not present in nav_history.")
            else:
                print(" All fund_master AMFI codes are present in nav_history.")
        else:
            print("\nCannot validate AMFI codes because 'amfi_code' is missing in one of the files.")

    print("\n=== Data quality summary ===")
    print(" expected datasets:", len(expected_files))
    print(" loaded datasets:", len(loaded))
    if missing_files:
        print(" missing datasets:", missing_files)


if __name__ == "__main__":
    main()
