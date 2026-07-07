"""
Bluestock MF — Live NAV Fetcher (Enhanced for B1)

Fetches live NAV data from mfapi.in for all schemes in the fund master.
Supports retry logic, batch fetching, and scheduled operation.

Usage:
    python scripts/live_nav_fetch.py                          # fetch all schemes
    python scripts/live_nav_fetch.py --scheme 119551          # single scheme
    python scripts/live_nav_fetch.py --output-dir data/raw    # custom output
"""

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"


def get_repo_root() -> Path:
    return PROJECT_ROOT


def fetch_scheme(scheme_id: int, retries: int = 3) -> dict | None:
    url = f"https://api.mfapi.in/mf/{scheme_id}"
    for attempt in range(retries):
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "SUCCESS" or "data" in data:
                return data
            print(f"  Attempt {attempt+1}: {data.get('status', 'unknown error')}")
        except requests.RequestException as e:
            print(f"  Attempt {attempt+1} failed for {scheme_id}: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return None


def fetch_all_schemes(out_dir: Path) -> list[str]:
    fm_path = RAW_DIR / "01_fund_master.csv"
    if not fm_path.exists():
        print(f"Fund master not found at {fm_path}")
        return []

    fm = pd.read_csv(fm_path, dtype={"amfi_code": str})
    codes = fm["amfi_code"].dropna().unique()
    saved = []

    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Fetching {len(codes)} schemes...")

    for i, code in enumerate(codes, 1):
        scheme_id = int(code)
        print(f"  [{i}/{len(codes)}] Fetching {scheme_id}...", end=" ")
        data = fetch_scheme(scheme_id)
        if data and "data" in data:
            df = pd.DataFrame(data["data"])
            safe_name = data.get("meta", {}).get("scheme_name", str(scheme_id)).replace("/", "_")[:50]
            out_path = out_dir / f"{safe_name}_{scheme_id}.csv"
            df.to_csv(out_path, index=False, encoding="utf-8")
            print(f"Saved ({len(df)} rows)")
            saved.append(str(out_path))
        else:
            print("Failed")
        time.sleep(0.3)

    print(f"Fetched {len(saved)} / {len(codes)} schemes")
    return saved


def fetch_single_scheme(scheme_id: int, out_dir: Path) -> Path | None:
    out_dir.mkdir(parents=True, exist_ok=True)
    data = fetch_scheme(scheme_id)
    if data and "data" in data:
        df = pd.DataFrame(data["data"])
        out_path = out_dir / f"scheme_{scheme_id}.csv"
        df.to_csv(out_path, index=False, encoding="utf-8")
        print(f"Saved {len(df)} NAV records to {out_path}")
        return out_path
    print(f"Failed to fetch scheme {scheme_id}")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Live NAV Fetcher")
    parser.add_argument("--scheme", type=int, help="Single scheme ID to fetch")
    parser.add_argument("--output-dir", type=str, default=str(RAW_DIR), help="Output directory")
    parser.add_argument("--delay", type=float, default=0.3, help="Delay between fetches (seconds)")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)

    if args.scheme:
        fetch_single_scheme(args.scheme, out_dir)
    else:
        fetch_all_schemes(out_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
