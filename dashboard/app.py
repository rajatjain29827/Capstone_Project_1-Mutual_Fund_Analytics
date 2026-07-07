"""
Bluestock MF — Streamlit Web App
Multi-page: Overview, Fund Screener, Performance, Monte Carlo, Portfolio Optimizer
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "processed"

st.set_page_config(page_title="Bluestock MF Analytics", layout="wide")
st.markdown("<h1 style='color:#1a3a5c;'>Bluestock Mutual Fund Analytics</h1>", unsafe_allow_html=True)


@st.cache_data
def load_data():
    nav = pd.read_csv(DATA_DIR / "02_nav_history.csv", parse_dates=["date"])
    fm = pd.read_csv(DATA_DIR / "01_fund_master.csv")
    perf = pd.read_csv(DATA_DIR / "07_scheme_performance.csv")
    bench = pd.read_csv(DATA_DIR / "10_benchmark_indices.csv", parse_dates=["date"])
    aum = pd.read_csv(DATA_DIR / "03_aum_by_fund_house.csv", parse_dates=["date"])
    tx = pd.read_csv(DATA_DIR / "08_investor_transactions.csv", parse_dates=["transaction_date"])
    nav["amfi_code"] = nav["amfi_code"].astype(str)
    fm["amfi_code"] = fm["amfi_code"].astype(str)
    perf["amfi_code"] = perf["amfi_code"].astype(str)
    return nav, fm, perf, bench, aum, tx


@st.cache_data
def load_scorecard():
    path = DATA_DIR / "fund_scorecard.csv"
    if path.exists():
        return pd.read_csv(path)
    return None


nav_df, fm_df, perf_df, bench_df, aum_df, tx_df = load_data()
scorecard = load_scorecard()

# ─────────────────── Sidebar ───────────────────
st.sidebar.markdown("## Navigation")
page = st.sidebar.radio("Go to", [
    "Overview", "Fund Screener", "Performance", "Monte Carlo", "Portfolio Optimizer", "Reports"
])

# ─────────────────── Page: Overview ───────────────────
if page == "Overview":
    st.header("Market Overview")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        latest_nav = nav_df.groupby("amfi_code")["nav"].last().mean()
        st.metric("Avg Latest NAV", f"{latest_nav:.2f}")
    with col2:
        total_aum = aum_df.groupby("date")["aum_crore"].sum().iloc[-1] if not aum_df.empty else 0
        st.metric("Total AUM (Cr)", f"{total_aum:,.0f}")
    with col3:
        unique_funds = fm_df["amfi_code"].nunique()
        st.metric("Fund Schemes", unique_funds)
    with col4:
        avg_sharpe = perf_df["sharpe_ratio"].astype(float).mean()
        st.metric("Avg Sharpe", f"{avg_sharpe:.2f}")

    st.subheader("NAV Trend (Top 5 Funds)")
    top_codes = nav_df["amfi_code"].value_counts().head(5).index
    trend = nav_df[nav_df["amfi_code"].isin(top_codes)].pivot_table(
        index="date", columns="amfi_code", values="nav", aggfunc="mean"
    ).fillna(method="ffill")
    st.line_chart(trend)

    st.subheader("AUM by Fund House (Latest)")
    latest_aum = aum_df.sort_values("date").groupby("fund_house").last().sort_values("aum_crore", ascending=False).head(10)
    st.bar_chart(latest_aum["aum_crore"])

# ─────────────────── Page: Fund Screener ───────────────────
elif page == "Fund Screener":
    st.header("Fund Screener")

    cats = sorted(fm_df["category"].dropna().unique())
    selected_cats = st.multiselect("Category", cats, default=cats[:3])
    risk_opts = sorted(fm_df["risk_category"].dropna().unique())
    selected_risk = st.multiselect("Risk Category", risk_opts, default=risk_opts)

    merged = perf_df.merge(fm_df, on="amfi_code", how="left")
    merged = merged[merged["category"].isin(selected_cats)]
    merged = merged[merged["risk_category"].isin(selected_risk)]

    display_cols = ["scheme_name", "fund_house", "category", "risk_category",
                    "return_1yr_pct", "return_3yr_pct", "sharpe_ratio",
                    "alpha", "beta", "expense_ratio_pct", "aum_crore"]
    display_cols = [c for c in display_cols if c in merged.columns]
    st.dataframe(merged[display_cols].round(2), use_container_width=True)

# ─────────────────── Page: Performance ───────────────────
elif page == "Performance":
    st.header("Performance Analytics")

    fund_names = fm_df["scheme_name"].tolist()
    selected = st.selectbox("Select Fund", fund_names)
    code = fm_df[fm_df["scheme_name"] == selected]["amfi_code"].values[0]

    fund_nav = nav_df[nav_df["amfi_code"] == code].sort_values("date")
    fund_nav["returns"] = fund_nav["nav"].pct_change()

    st.subheader(f"{selected} — NAV & Returns")
    col1, col2 = st.columns(2)
    with col1:
        st.line_chart(fund_nav.set_index("date")["nav"])
    with col2:
        st.line_chart(fund_nav.set_index("date")["returns"].dropna())

    info = fm_df[fm_df["amfi_code"] == code].iloc[0]
    st.subheader("Fund Details")
    st.json(info.to_dict())

# ─────────────────── Page: Monte Carlo (B3) ───────────────────
elif page == "Monte Carlo":
    st.header("Monte Carlo Simulation — 5-Year NAV Projection")

    fund_names = fm_df["scheme_name"].tolist()
    selected = st.selectbox("Select Fund", fund_names, key="mc_fund")
    code = fm_df[fm_df["scheme_name"] == selected]["amfi_code"].values[0]

    n_simulations = st.slider("Number of Simulations", 500, 10000, 2000, step=500)
    years = st.slider("Projection Years", 1, 10, 5)

    fund_nav = nav_df[nav_df["amfi_code"] == code].sort_values("date")["nav"]
    if len(fund_nav) < 30:
        st.error("Insufficient historical data for this fund.")
    else:
        S0 = fund_nav.iloc[-1]
        returns = fund_nav.pct_change().dropna()
        mu = returns.mean() * 252
        sigma = returns.std() * np.sqrt(252)

        T = years * 252
        dt = 1 / 252
        np.random.seed(42)
        prices = np.zeros((T + 1, n_simulations))
        prices[0] = S0
        for t in range(1, T + 1):
            epsilon = np.random.normal(0, 1, n_simulations)
            prices[t] = prices[t - 1] * np.exp((mu - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * epsilon)

        sim_df = pd.DataFrame(prices)
        sim_df["median"] = sim_df.median(axis=1)
        sim_df["p5"] = sim_df.iloc[:, :n_simulations].quantile(0.05, axis=1)
        sim_df["p95"] = sim_df.iloc[:, :n_simulations].quantile(0.95, axis=1)
        sim_df.index = pd.date_range(start=fund_nav.index[-1], periods=T + 1, freq="B")

        st.subheader(f"Projected NAV: {selected}")
        st.info(f"S0={S0:.2f}, mu={mu:.2%}, sigma={sigma:.2%}")

        chart = sim_df[["median", "p5", "p95"]]
        st.line_chart(chart)

        final_median = sim_df["median"].iloc[-1]
        final_p5 = sim_df["p5"].iloc[-1]
        final_p95 = sim_df["p95"].iloc[-1]
        col1, col2, col3 = st.columns(3)
        col1.metric("Median (5yr)", f"{final_median:.2f}", f"{(final_median/S0 - 1)*100:.1f}%")
        col2.metric("Pessimistic (P5)", f"{final_p5:.2f}", f"{(final_p5/S0 - 1)*100:.1f}%")
        col3.metric("Optimistic (P95)", f"{final_p95:.2f}", f"{(final_p95/S0 - 1)*100:.1f}%")

# ─────────────────── Page: Portfolio Optimizer (B4) ───────────────────
elif page == "Portfolio Optimizer":
    st.header("Markowitz Efficient Frontier")

    fund_codes = nav_df["amfi_code"].unique()
    fund_names = fm_df.set_index("amfi_code")["scheme_name"].to_dict()
    name_list = [fund_names.get(c, c) for c in fund_codes]

    selected_names = st.multiselect(
        "Select 5 Funds for Optimization",
        name_list,
        default=name_list[:5],
        max_selections=5,
    )

    if len(selected_names) < 2:
        st.warning("Select at least 2 funds to run optimization.")
    else:
        code_map = {v: k for k, v in fund_names.items()}
        selected_codes = [code_map[n] for n in selected_names if n in code_map]

        returns_df = None
        for c in selected_codes:
            s = nav_df[nav_df["amfi_code"] == c].set_index("date")["nav"].pct_change().rename(c)
            if returns_df is None:
                returns_df = s.to_frame()
            else:
                returns_df = returns_df.join(s, how="outer")

        returns_df = returns_df.dropna()
        if len(returns_df) < 10:
            st.error("Insufficient overlapping data for selected funds.")
        else:
            mean_returns = returns_df.mean() * 252
            cov_matrix = returns_df.cov() * 252

            n_portfolios = 10000
            results = np.zeros((3, n_portfolios))
            weights_record = []

            for i in range(n_portfolios):
                weights = np.random.random(len(selected_codes))
                weights /= weights.sum()
                weights_record.append(weights)
                port_return = np.sum(mean_returns.values * weights)
                port_std = np.sqrt(np.dot(weights.T, np.dot(cov_matrix.values, weights)))
                results[0, i] = port_std
                results[1, i] = port_return
                results[2, i] = (port_return - 0.065) / port_std

            ef_df = pd.DataFrame({
                "Volatility": results[0] * 100,
                "Return": results[1] * 100,
                "Sharpe": results[2],
            })

            st.subheader("Efficient Frontier")
            st.scatter_chart(ef_df, x="Volatility", y="Return", size="Sharpe", color="Sharpe")

            max_sharpe_idx = results[2].argmax()
            min_vol_idx = results[0].argmin()

            st.subheader("Optimal Portfolios")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Max Sharpe Portfolio**")
                w_max = weights_record[max_sharpe_idx]
                for name, w in zip(selected_names, w_max):
                    st.write(f"{name}: {w:.1%}")
                st.write(f"Return: {results[1, max_sharpe_idx]*100:.2f}%")
                st.write(f"Volatility: {results[0, max_sharpe_idx]*100:.2f}%")
                st.write(f"Sharpe: {results[2, max_sharpe_idx]:.3f}")

            with col2:
                st.markdown("**Min Volatility Portfolio**")
                w_min = weights_record[min_vol_idx]
                for name, w in zip(selected_names, w_min):
                    st.write(f"{name}: {w:.1%}")
                st.write(f"Return: {results[1, min_vol_idx]*100:.2f}%")
                st.write(f"Volatility: {results[0, min_vol_idx]*100:.2f}%")
                st.write(f"Sharpe: {results[2, min_vol_idx]:.3f}")

# ─────────────────── Page: Reports ───────────────────
elif page == "Reports":
    st.header("Reports & Downloads")

    st.subheader("Downloadable Reports")
    report_path = PROJECT_ROOT / "reports" / "Final_Report.pdf"
    if report_path.exists():
        with open(report_path, "rb") as f:
            st.download_button("Download Final Report (PDF)", f, file_name="Final_Report.pdf")

    pptx_path = PROJECT_ROOT / "reports" / "Presentation.pptx"
    if pptx_path.exists():
        with open(pptx_path, "rb") as f:
            st.download_button("Download Presentation (PPTX)", f, file_name="Presentation.pptx")

    st.subheader("Send Weekly Email Report")
    if st.button("Generate & Send Weekly Report"):
        try:
            from scripts.email_report import main as email_main
            email_main()
            st.success("Weekly report sent successfully!")
        except Exception as e:
            st.error(f"Failed to send: {e}")
