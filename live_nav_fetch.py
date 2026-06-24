import pandas as pd
import requests
from pathlib import Path


def get_repo_root() -> Path:
    script_dir = Path(__file__).resolve().parent
    return next(p for p in [script_dir] + list(script_dir.parents) if (p / ".git").exists())


def fetch_nav(name: str, scheme_id: int, out_dir: Path) -> None:
    url = f"https://api.mfapi.in/mf/{scheme_id}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") != "SUCCESS":
        print(f"Failed to fetch {name} ({scheme_id}): {data.get('status')}")
        return

    if data["meta"].get("scheme_code") != scheme_id:
        print(f"Unexpected scheme_code for {name}: {data['meta'].get('scheme_code')}")

    df = pd.DataFrame(data["data"])
    out_path = out_dir / f"{name}.csv"
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False, encoding="utf-8")
    print(f"Saved {name} NAV to {out_path}")


def main() -> None:
    repo_root = get_repo_root()
    out_dir = repo_root / "data" / "raw"

    schemes = [
        ("HDFC_Top_100_Direct", 125497),
        ("SBI_Bluechip", 119551),
        ("ICICI_Bluechip", 120503),
        ("Nippon_Large_Cap", 118632),
        ("Axis_Bluechip", 119092),
        ("Kotak_Bluechip", 120841),
    ]

    for name, scheme_id in schemes:
        fetch_nav(name, scheme_id, out_dir)


if __name__ == "__main__":
    main()
