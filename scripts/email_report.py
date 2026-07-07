"""
Bluestock MF — Automated Weekly Email Report (B5)

Usage:
    python scripts/email_report.py [--recipients email1,email2] [--smtp-host HOST]

Reads SMTP config from environment variables or CLI args.
Sends an HTML email with key metrics, top/bottom performers, VaR snapshot.
"""

import argparse
import os
import smtplib
import sys
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIR = PROJECT_ROOT / "reports"


def load_weekly_metrics() -> dict:
    nav = pd.read_csv(DATA_DIR / "02_nav_history.csv", parse_dates=["date"])
    perf = pd.read_csv(DATA_DIR / "07_scheme_performance.csv")
    fm = pd.read_csv(DATA_DIR / "01_fund_master.csv")
    aum = pd.read_csv(DATA_DIR / "03_aum_by_fund_house.csv", parse_dates=["date"])

    nav["amfi_code"] = nav["amfi_code"].astype(str)
    fm["amfi_code"] = fm["amfi_code"].astype(str)
    perf["amfi_code"] = perf["amfi_code"].astype(str)

    latest_date = nav["date"].max()
    week_ago = latest_date - timedelta(days=7)

    metrics = {}

    week_nav = nav[nav["date"] >= week_ago]
    metrics["week_nav_change_pct"] = round(
        week_nav.groupby("amfi_code")["nav"].last().mean() /
        week_nav.groupby("amfi_code")["nav"].first().mean() - 1, 4
    )

    latest_aum = aum.sort_values("date").groupby("fund_house")["aum_crore"].last().sum()
    metrics["total_aum_crore"] = f"{latest_aum:,.0f}"

    avg_sharpe = perf["sharpe_ratio"].astype(float).mean()
    metrics["avg_sharpe"] = round(avg_sharpe, 2)

    merged = perf.merge(fm, on="amfi_code", how="left")
    merged["return_1yr_pct"] = pd.to_numeric(merged["return_1yr_pct"], errors="coerce")
    top5 = merged.nlargest(5, "return_1yr_pct")[["scheme_name", "return_1yr_pct", "sharpe_ratio"]]
    bottom5 = merged.nsmallest(5, "return_1yr_pct")[["scheme_name", "return_1yr_pct", "sharpe_ratio"]]

    metrics["top5"] = top5.to_dict("records")
    metrics["bottom5"] = bottom5.to_dict("records")

    return metrics


def build_html(metrics: dict) -> str:
    week = datetime.now().strftime("%b %d, %Y")
    top_rows = "".join(
        f"<tr><td>{r['scheme_name']}</td><td>{r['return_1yr_pct']:.1f}%</td><td>{r['sharpe_ratio']}</td></tr>"
        for r in metrics["top5"]
    )
    bottom_rows = "".join(
        f"<tr><td>{r['scheme_name']}</td><td>{r['return_1yr_pct']:.1f}%</td><td>{r['sharpe_ratio']}</td></tr>"
        for r in metrics["bottom5"]
    )

    return f"""
    <html>
    <head><style>
        body {{ font-family: Arial, sans-serif; color: #333; }}
        .header {{ background: #1a3a5c; color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 20px; }}
        .kpi {{ display: inline-block; margin: 10px; padding: 15px; background: #f5f8fc; border-radius: 8px; text-align: center; min-width: 150px; }}
        .kpi h3 {{ margin: 0; font-size: 14px; color: #666; }}
        .kpi p {{ margin: 5px 0 0; font-size: 24px; font-weight: bold; color: #1a3a5c; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th {{ background: #1a3a5c; color: white; padding: 8px; text-align: left; }}
        td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
        .footer {{ text-align: center; padding: 20px; font-size: 12px; color: #999; }}
    </style></head>
    <body>
        <div class="header"><h1>Bluestock MF Weekly Performance</h1><p>{week}</p></div>
        <div class="content">
            <h2>Key Metrics</h2>
            <div>
                <div class="kpi"><h3>Total AUM</h3><p>Rs {metrics['total_aum_crore']} Cr</p></div>
                <div class="kpi"><h3>Avg Sharpe</h3><p>{metrics['avg_sharpe']}</p></div>
                <div class="kpi"><h3>Weekly NAV Change</h3><p>{metrics['week_nav_change_pct']:+.2%}</p></div>
            </div>

            <h2>Top 5 Performers (1Y Return)</h2>
            <table><tr><th>Fund</th><th>Return</th><th>Sharpe</th></tr>{top_rows}</table>

            <h2>Bottom 5 Performers (1Y Return)</h2>
            <table><tr><th>Fund</th><th>Return</th><th>Sharpe</th></tr>{bottom_rows}</table>

            <p><a href="#" style="color:#1a3a5c;">View Full Dashboard</a></p>
        </div>
        <div class="footer">Generated automatically by Bluestock MF ETL Pipeline</div>
    </body>
    </html>
    """


def send_email(html_content: str, recipients: list, smtp_host: str = None,
               smtp_port: int = 587, smtp_user: str = None, smtp_pass: str = None):
    smtp_host = smtp_host or os.environ.get("SMTP_HOST", "localhost")
    smtp_port = smtp_port or int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = smtp_user or os.environ.get("SMTP_USER", "")
    smtp_pass = smtp_pass or os.environ.get("SMTP_PASS", "")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Bluestock MF Weekly Report — {datetime.now():%b %d, %Y}"
    msg["From"] = smtp_user or "noreply@bluestock-mf.com"
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_content, "html"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        if smtp_user and smtp_pass:
            server.starttls()
            server.login(smtp_user, smtp_pass)
        server.sendmail(msg["From"], recipients, msg.as_string())

    print(f"Weekly report sent to {len(recipients)} recipient(s)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bluestock MF Weekly Email Report")
    parser.add_argument("--recipients", type=str, help="Comma-separated email recipients")
    parser.add_argument("--smtp-host", type=str, help="SMTP server hostname")
    parser.add_argument("--smtp-port", type=int, default=587)
    parser.add_argument("--smtp-user", type=str, help="SMTP username")
    parser.add_argument("--smtp-pass", type=str, help="SMTP password")
    parser.add_argument("--dry-run", action="store_true", help="Print HTML to stdout instead of sending")
    args = parser.parse_args()

    metrics = load_weekly_metrics()
    html = build_html(metrics)

    if args.dry_run:
        print(html)
        return 0

    recipients_str = args.recipients or os.environ.get("EMAIL_RECIPIENTS", "")
    recipients = [r.strip() for r in recipients_str.split(",") if r.strip()]

    if not recipients:
        print("No recipients specified. Use --recipients or EMAIL_RECIPIENTS env var.")
        print("Use --dry-run to preview the HTML.")
        return 1

    send_email(html, recipients, args.smtp_host, args.smtp_port,
               args.smtp_user, args.smtp_pass)
    return 0


if __name__ == "__main__":
    sys.exit(main())
