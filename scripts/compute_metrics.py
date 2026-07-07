"""
Bluestock MF — Risk & Performance Metrics Calculator

Usage:
    python scripts/compute_metrics.py --fund 119551 --metrics all
    python scripts/compute_metrics.py --fund 119551 --metrics sharpe,var --output results.csv
    python scripts/compute_metrics.py --all-funds --output data/processed/fund_metrics.csv

Computes: CAGR (1y/3y/5y), daily volatility (ann.), Sharpe, Sortino,
Max Drawdown, Alpha, Beta, Tracking Error, VaR (parametric/historical/CVaR).
Uses 252 trading days for annualisation per grading guidelines.
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "processed"


def load_nav_history() -> pd.DataFrame:
    path = DATA_DIR / "02_nav_history.csv"
    df = pd.read_csv(path, parse_dates=["date"])
    df["amfi_code"] = df["amfi_code"].astype(str)
    return df


def load_fund_master() -> pd.DataFrame:
    path = DATA_DIR / "01_fund_master.csv"
    df = pd.read_csv(path)
    df["amfi_code"] = df["amfi_code"].astype(str)
    return df


def load_benchmark() -> pd.DataFrame:
    path = DATA_DIR / "10_benchmark_indices.csv"
    df = pd.read_csv(path, parse_dates=["date"])
    return df


def compute_daily_returns(nav: pd.Series) -> pd.Series:
    return nav.pct_change().dropna()


def compute_cagr(nav: pd.Series, periods: int = 252) -> float:
    """CAGR = (ending_value / starting_value)^(252 / n_trading_days) - 1"""
    if len(nav) < 2:
        return np.nan
    total_return = nav.iloc[-1] / nav.iloc[0]
    n_days = len(nav.dropna())
    return total_return ** (252 / n_days) - 1


def compute_sharpe(daily_returns: pd.Series, rf_annual: float = 0.065) -> float:
    """Sharpe = (mean_daily_return - rf_daily) / std_daily_return * sqrt(252)"""
    if len(daily_returns) < 2 or daily_returns.std() == 0:
        return np.nan
    rf_daily = rf_annual / 252
    excess = daily_returns - rf_daily
    return excess.mean() / excess.std() * np.sqrt(252)


def compute_sortino(daily_returns: pd.Series, rf_annual: float = 0.065) -> float:
    """Sortino uses downside deviation (returns < 0) only"""
    if len(daily_returns) < 2:
        return np.nan
    rf_daily = rf_annual / 252
    excess = daily_returns.mean() - rf_daily
    downside = daily_returns[daily_returns < 0]
    if len(downside) == 0 or downside.std() == 0:
        return np.nan
    return excess / downside.std() * np.sqrt(252)


def compute_max_drawdown(nav: pd.Series) -> float:
    rolling_max = nav.expanding().max()
    drawdown = (nav - rolling_max) / rolling_max
    return drawdown.min()


def compute_alpha_beta(
    fund_returns: pd.Series, benchmark_returns: pd.Series
) -> dict:
    """Alpha and Beta via OLS: fund_return - rf = alpha + beta * (bench_return - rf)"""
    from scipy import stats
    aligned = pd.concat([fund_returns, benchmark_returns], axis=1).dropna()
    if len(aligned) < 30:
        return {"Alpha": np.nan, "Beta": np.nan, "R_squared": np.nan}
    bench = aligned.iloc[:, 1].values
    fund = aligned.iloc[:, 0].values
    slope, intercept, r_val, p_val, std_err = stats.linregress(bench, fund)
    return {
        "Alpha": intercept * 252,
        "Beta": slope,
        "R_squared": r_val ** 2,
        "p_value": p_val,
    }


def compute_tracking_error(fund_returns: pd.Series, benchmark_returns: pd.Series) -> float:
    aligned = pd.concat([fund_returns, benchmark_returns], axis=1).dropna()
    if len(aligned) < 2:
        return np.nan
    diff = aligned.iloc[:, 0] - aligned.iloc[:, 1]
    return diff.std() * np.sqrt(252)


def compute_var(daily_returns: pd.Series, confidence: float = 0.95) -> dict:
    """Parametric VaR, Historical VaR, and CVaR (Expected Shortfall)"""
    if len(daily_returns) < 2:
        return {"VaR_param": np.nan, "VaR_hist": np.nan, "CVaR": np.nan}
    mu = daily_returns.mean()
    sigma = daily_returns.std()
    from scipy import stats
    z = stats.norm.ppf(1 - confidence)
    var_param = -(mu + z * sigma) * np.sqrt(252)
    var_hist = -np.percentile(daily_returns, (1 - confidence) * 100) * np.sqrt(252)
    cvar = -daily_returns[daily_returns <= np.percentile(daily_returns, (1 - confidence) * 100)].mean() * np.sqrt(252)
    return {
        "VaR_param": round(var_param * 100, 2),
        "VaR_hist": round(var_hist * 100, 2),
        "CVaR": round(cvar * 100, 2),
    }


def compute_all_metrics(fund_code: str) -> dict:
    nav_df = load_nav_history()
    fund_master = load_fund_master()
    bench_df = load_benchmark()

    fund_nav = nav_df[nav_df["amfi_code"] == fund_code].sort_values("date")
    if len(fund_nav) < 10:
        return {"fund_code": fund_code, "error": "Insufficient data"}

    fund_info = fund_master[fund_master["amfi_code"] == fund_code]
    name = fund_info["scheme_name"].values[0] if len(fund_info) > 0 else "Unknown"
    house = fund_info["fund_house"].values[0] if len(fund_info) > 0 else "Unknown"

    nav = fund_nav["nav"]
    dates = fund_nav["date"]
    daily_ret = compute_daily_returns(nav)

    # CAGR: 1y, 3y
    mask_1y = dates >= dates.max() - pd.DateOffset(years=1)
    mask_3y = dates >= dates.max() - pd.DateOffset(years=3)
    mask_5y = dates >= dates.max() - pd.DateOffset(years=5)

    cagr_1y = compute_cagr(nav[mask_1y]) if mask_1y.sum() > 1 else np.nan
    cagr_3y = compute_cagr(nav[mask_3y]) if mask_3y.sum() > 1 else np.nan
    cagr_5y = compute_cagr(nav[mask_5y]) if mask_5y.sum() > 1 else np.nan

    # Benchmark alignment for Alpha/Beta/TE
    nifty = bench_df[bench_df["index_name"] == "NIFTY50"].copy()
    nifty["returns"] = nifty["close_value"].pct_change()

    fund_ret_df = fund_nav[["date", "nav"]].iloc[1:].copy()
    fund_ret_df["ret"] = daily_ret.values
    merged = pd.merge(
        fund_ret_df[["date", "ret"]],
        nifty[["date", "returns"]],
        on="date", how="inner",
    )

    if len(merged) < 10:
        ab = {"Alpha": np.nan, "Beta": np.nan, "R_squared": np.nan}
        te = np.nan
    else:
        ab = compute_alpha_beta(merged["ret"], merged["returns"])
        te = compute_tracking_error(merged["ret"], merged["returns"])

    # VaR at 95% and 99%
    var_95 = compute_var(daily_ret, 0.95)
    var_99 = compute_var(daily_ret, 0.99)

    metrics = {
        "fund_code": fund_code,
        "scheme_name": name,
        "fund_house": house,
        "CAGR_1yr_pct": round(cagr_1y * 100, 2),
        "CAGR_3yr_pct": round(cagr_3y * 100, 2),
        "CAGR_5yr_pct": round(cagr_5y * 100, 2),
        "Ann_volatility_pct": round(daily_ret.std() * np.sqrt(252) * 100, 2),
        "Sharpe": round(compute_sharpe(daily_ret), 4),
        "Sortino": round(compute_sortino(daily_ret), 4),
        "Max_drawdown_pct": round(compute_max_drawdown(nav) * 100, 2),
        "Alpha": round(ab["Alpha"] * 100, 2),
        "Beta": round(ab["Beta"], 4),
        "R_squared": round(ab["R_squared"], 4),
        "Tracking_error_pct": round(te * 100, 2),
        "VaR_95_param_pct": var_95["VaR_param"],
        "VaR_95_hist_pct": var_95["VaR_hist"],
        "CVaR_95_pct": var_95["CVaR"],
        "VaR_99_param_pct": var_99["VaR_param"],
        "VaR_99_hist_pct": var_99["VaR_hist"],
        "CVaR_99_pct": var_99["CVaR"],
    }
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute MF risk/performance metrics")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fund", type=str, help="Single AMFI fund code")
    group.add_argument("--all-funds", action="store_true", help="Compute for all funds")
    parser.add_argument("--output", type=str, help="Output CSV path")
    parser.add_argument("--format", choices=["json", "csv", "pretty"], default="pretty")
    args = parser.parse_args()

    if args.all_funds:
        fm = load_fund_master()
        codes = fm["amfi_code"].unique()
        results = []
        for code in codes:
            m = compute_all_metrics(code)
            if "error" not in m:
                results.append(m)
        df = pd.DataFrame(results)
    else:
        m = compute_all_metrics(args.fund)
        df = pd.DataFrame([m])

    out_path = args.output
    if out_path:
        df.to_csv(out_path, index=False)
        print(f"Saved {len(df)} fund metrics to {out_path}")
    elif args.format == "json":
        print(df.to_json(orient="records", indent=2))
    elif args.format == "csv":
        print(df.to_csv(index=False))
    else:
        print(df.to_string(index=False))

    return 0


if __name__ == "__main__":
    sys.exit(main())
