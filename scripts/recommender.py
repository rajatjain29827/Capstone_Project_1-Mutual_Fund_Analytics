"""
Bluestock MF — Fund Recommender Engine

Usage:
    python scripts/recommender.py --profile aggressive
    python scripts/recommender.py --profile conservative --top 5
    python scripts/recommender.py --all-profiles --output data/processed/recommendations.csv

Rule-based scoring for Conservative / Moderate / Aggressive investor profiles.
Each profile weighs different metrics to produce a composite score (0-100).
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "processed"


def load_scheme_performance() -> pd.DataFrame:
    path = DATA_DIR / "07_scheme_performance.csv"
    df = pd.read_csv(path)
    df["amfi_code"] = df["amfi_code"].astype(str)
    return df


def load_fund_master() -> pd.DataFrame:
    path = DATA_DIR / "01_fund_master.csv"
    df = pd.read_csv(path)
    df["amfi_code"] = df["amfi_code"].astype(str)
    return df


def load_metrics() -> pd.DataFrame:
    path = DATA_DIR / "fund_scorecard.csv"
    if path.exists():
        return pd.read_csv(path)
    return None


# Scoring weights per profile
PROFILES = {
    "conservative": {
        "description": "Capital preservation, low risk tolerance",
        "weights": {
            "expense_ratio": -0.20,
            "std_dev_ann": -0.25,
            "max_drawdown": -0.15,
            "aum_size": 0.15,
            "return_3yr": 0.10,
            "return_1yr": 0.05,
            "sharpe": 0.10,
        },
        "filters": {
            "expense_ratio_max": 1.5,
            "category_include": ["Large Cap", "Liquid", "Overnight", "Gilt"],
        },
    },
    "moderate": {
        "description": "Balanced risk-return, medium tolerance",
        "weights": {
            "sharpe": 0.25,
            "return_3yr": 0.20,
            "return_1yr": 0.15,
            "std_dev_ann": -0.10,
            "max_drawdown": -0.10,
            "expense_ratio": -0.10,
            "aum_size": 0.10,
        },
        "filters": {
            "expense_ratio_max": 2.0,
            "category_include": ["Large Cap", "Mid Cap", "Flexi Cap", "Balanced"],
        },
    },
    "aggressive": {
        "description": "High growth, high risk tolerance",
        "weights": {
            "return_1yr": 0.25,
            "return_3yr": 0.20,
            "return_5yr": 0.10,
            "sortino": 0.15,
            "sharpe": 0.10,
            "std_dev_ann": 0.05,
            "max_drawdown": -0.05,
            "expense_ratio": -0.05,
            "aum_size": 0.05,
        },
        "filters": {
            "expense_ratio_max": 2.5,
            "category_include": ["Small Cap", "Mid Cap", "Sectoral", "ELSS"],
        },
    },
}


def score_funds(profile_name: str, top_n: int = 3) -> pd.DataFrame:
    if profile_name not in PROFILES:
        print(f"Unknown profile: {profile_name}. Choose from: {list(PROFILES.keys())}")
        return pd.DataFrame()

    profile = PROFILES[profile_name]
    perf = load_scheme_performance()
    fm = load_fund_master()

    df = perf.merge(fm, on="amfi_code", suffixes=("_perf", "_master"))

    df["std_dev_ann"] = pd.to_numeric(df.get("std_dev_ann_pct", 0), errors="coerce")
    df["max_drawdown"] = pd.to_numeric(df.get("max_drawdown_pct", 0), errors="coerce")
    df["aum_size"] = pd.to_numeric(df.get("aum_crore", 0), errors="coerce")

    # Apply filters
    filters = profile["filters"]
    if "expense_ratio_max" in filters:
        expense_col = "expense_ratio_pct"
        if expense_col in df.columns:
            df = df[pd.to_numeric(df[expense_col], errors="coerce") <= filters["expense_ratio_max"]]
    if "category_include" in filters:
        category_col = "category"
        if category_col in df.columns:
            df = df[df[category_col].isin(filters["category_include"])]

    if df.empty:
        return pd.DataFrame()

    # Normalise numeric columns to 0-1 for scoring
    weights = profile["weights"]
    score_fields = list(weights.keys())
    available = [c for c in score_fields if c in df.columns]

    for col in available:
        vals = pd.to_numeric(df[col], errors="coerce")
        min_v, max_v = vals.min(), vals.max()
        if max_v > min_v:
            df[f"norm_{col}"] = (vals - min_v) / (max_v - min_v)
        else:
            df[f"norm_{col}"] = 0.5

    # Compute weighted score
    df["score"] = 0.0
    for col in available:
        w = weights[col]
        df["score"] += w * df[f"norm_{col}"]

    df = df.sort_values("score", ascending=False).head(top_n).copy()
    df["profile"] = profile_name
    df["rationale"] = df.apply(
        lambda r: _generate_rationale(r, profile_name), axis=1
    )

    out_cols = ["amfi_code", "scheme_name", "fund_house", "category",
                "risk_category", "score", "profile", "rationale",
                "return_1yr_pct", "return_3yr_pct", "sharpe_ratio",
                "std_dev_ann_pct", "expense_ratio_pct"]
    out_cols = [c for c in out_cols if c in df.columns]
    return df[out_cols]


def _generate_rationale(row: pd.Series, profile: str) -> str:
    parts = []
    for label, col, direction in [
        ("return", "return_1yr_pct", "high"),
        ("risk (std dev)", "std_dev_ann_pct", "low" if profile == "conservative" else "high"),
        ("expense ratio", "expense_ratio_pct", "low"),
        ("Sharpe", "sharpe_ratio", "high"),
    ]:
        val = row.get(col)
        if pd.notna(val):
            parts.append(f"{label}={val:.1f}")
    return f"[{profile}] " + ", ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="MF Fund Recommender")
    parser.add_argument("--profile", choices=list(PROFILES.keys()), help="Investor profile")
    parser.add_argument("--all-profiles", action="store_true", help="Score for all profiles")
    parser.add_argument("--top", type=int, default=3, help="Number of top recommendations")
    parser.add_argument("--output", type=str, help="Output CSV path")
    args = parser.parse_args()

    if args.all_profiles:
        all_results = []
        for p in PROFILES:
            result = score_funds(p, args.top)
            if not result.empty:
                all_results.append(result)
        if all_results:
            df = pd.concat(all_results, ignore_index=True)
        else:
            df = pd.DataFrame()
    elif args.profile:
        df = score_funds(args.profile, args.top)
    else:
        parser.print_help()
        return 1

    if df.empty:
        print("No matching funds found for the selected profile.")
        return 0

    if args.output:
        df.to_csv(args.output, index=False)
        print(f"Saved {len(df)} recommendations to {args.output}")
    else:
        print(df.to_string(index=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
