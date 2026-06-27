import argparse
import ast
import json
import math
import shutil
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEV_DIR = PROJECT_DIR / "mosaic_dev"
OUTPUT_DIR = DEV_DIR / "output"
SITE_DIR = PROJECT_DIR / "site"
DEFAULT_CONFIG = DEV_DIR / "conservative_haircuts.csv"
CSV_PATH = OUTPUT_DIR / "all_market_reports_data_from_csv.csv"
JSON_PATH = OUTPUT_DIR / "all_market_reports_data_from_csv.json"
SOURCE_CSV_BACKUP = OUTPUT_DIR / "all_market_reports_data_from_csv.pre_conservative_haircut.csv"
SOURCE_JSON_BACKUP = OUTPUT_DIR / "all_market_reports_data_from_csv.pre_conservative_haircut.json"


def safe_market_name(value):
    return str(value).replace(" ", "_").replace("/", "_")


def parse_return_map(value):
    if value is None:
        return pd.Series(dtype=float)
    if isinstance(value, float) and math.isnan(value):
        return pd.Series(dtype=float)
    if isinstance(value, dict):
        data = value
    else:
        text = str(value).strip()
        if not text:
            return pd.Series(dtype=float)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = ast.literal_eval(text)
    if not isinstance(data, dict):
        return pd.Series(dtype=float)
    series = pd.Series(data, dtype=float)
    series.index = pd.to_datetime(series.index)
    return series.sort_index()


def return_map(series):
    series = pd.Series(series).dropna()
    return {idx.strftime("%Y-%m-%d"): float(value) for idx, value in series.items()}


def equity_from_returns(returns):
    returns = pd.Series(returns).dropna().astype(float)
    if returns.empty:
        return returns
    return (1.0 + returns).cumprod()


def max_drawdown_from_equity(equity):
    equity = pd.Series(equity).dropna()
    if equity.empty:
        return np.nan
    return (equity / equity.cummax() - 1.0).min()


def cagr_from_returns(returns, periods=52):
    equity = equity_from_returns(returns)
    if equity.empty:
        return np.nan
    years = len(equity) / periods
    if years <= 0 or equity.iloc[-1] <= 0:
        return np.nan
    return equity.iloc[-1] ** (1.0 / years) - 1.0


def sharpe_from_returns(returns, risk_free_annual=0.01, periods=52):
    returns = pd.Series(returns).dropna().astype(float)
    if len(returns) < 2:
        return np.nan
    std = returns.std()
    if std == 0 or not np.isfinite(std):
        return np.nan
    rf_weekly = (1.0 + risk_free_annual) ** (1.0 / periods) - 1.0
    return ((returns - rf_weekly).mean() / std) * math.sqrt(periods)


def information_ratio(strategy_returns, benchmark_returns, periods=52):
    strategy_returns = pd.Series(strategy_returns).dropna().astype(float)
    benchmark_returns = pd.Series(benchmark_returns).reindex(strategy_returns.index).fillna(0.0)
    active = strategy_returns - benchmark_returns
    std = active.std()
    if std == 0 or not np.isfinite(std):
        return np.nan
    return (active.mean() / std) * math.sqrt(periods)


def performance_metrics(returns, benchmark_returns):
    returns = pd.Series(returns).dropna().astype(float)
    equity = equity_from_returns(returns)
    return {
        "cagr": cagr_from_returns(returns),
        "maxdd": max_drawdown_from_equity(equity),
        "sharpe": sharpe_from_returns(returns),
        "ir": information_ratio(returns, benchmark_returns),
    }


def apply_positive_haircut(returns, factor):
    adjusted = pd.Series(returns).dropna().astype(float).copy()
    if adjusted.empty:
        return adjusted
    adjusted.loc[adjusted > 0.0] *= factor
    return adjusted


def load_haircuts(path):
    config = pd.read_csv(path)
    required = {"Market", "Positive_Return_Haircut"}
    missing = required - set(config.columns)
    if missing:
        raise ValueError(f"Config missing columns: {sorted(missing)}")
    haircuts = {}
    for _, row in config.iterrows():
        market = str(row["Market"]).strip()
        if not market:
            continue
        factor = float(row["Positive_Return_Haircut"])
        if factor <= 0 or factor > 1:
            raise ValueError(f"Haircut for {market} must be in (0, 1], got {factor}")
        haircuts[market] = factor
    return haircuts


def ensure_source_backup(refresh_source=False):
    if refresh_source:
        for src, dst in [(CSV_PATH, SOURCE_CSV_BACKUP), (JSON_PATH, SOURCE_JSON_BACKUP)]:
            if src.exists():
                shutil.copy2(src, dst)
        return
    if not SOURCE_CSV_BACKUP.exists() and CSV_PATH.exists():
        shutil.copy2(CSV_PATH, SOURCE_CSV_BACKUP)
    if not SOURCE_JSON_BACKUP.exists() and JSON_PATH.exists():
        shutil.copy2(JSON_PATH, SOURCE_JSON_BACKUP)


def load_source_dataframe():
    if SOURCE_JSON_BACKUP.exists():
        rows = json.loads(SOURCE_JSON_BACKUP.read_text(encoding="utf-8"))
        return pd.DataFrame(rows)
    if JSON_PATH.exists():
        rows = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        return pd.DataFrame(rows)
    source = SOURCE_CSV_BACKUP if SOURCE_CSV_BACKUP.exists() else CSV_PATH
    if not source.exists():
        raise FileNotFoundError(f"Missing source data: {source}")
    return pd.read_csv(source)


def write_html_data(df):
    html_root = OUTPUT_DIR / "html_data"
    for record in df.to_dict(orient="records"):
        market = record.get("Market")
        if not market:
            continue
        out_dir = html_root / safe_market_name(market)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "report_data.json").write_text(
            json.dumps([record], ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )


def write_site_report_data(df):
    reports_html = SITE_DIR / "reports_html"
    for record in df.to_dict(orient="records"):
        market = record.get("Market")
        if not market:
            continue
        out_dir = reports_html / safe_market_name(market)
        if not out_dir.exists():
            continue
        (out_dir / "report_data.json").write_text(
            json.dumps([record], ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )


def make_summary_chart(row, strategy_returns, hedged_returns, benchmark_returns, output_dir=OUTPUT_DIR):
    market = str(row["Market"])
    safe_market = safe_market_name(market)
    out_dir = Path(output_dir) / "_summary_charts" / safe_market
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"summary_{safe_market}.png"

    index = strategy_returns.index.union(benchmark_returns.index).union(hedged_returns.index).sort_values()
    strategy_returns = strategy_returns.reindex(index).fillna(0.0)
    benchmark_returns = benchmark_returns.reindex(index).fillna(0.0)
    hedged_returns = hedged_returns.reindex(index).fillna(0.0) if not hedged_returns.empty else pd.Series(dtype=float)

    strategy_equity = equity_from_returns(strategy_returns)
    benchmark_equity = equity_from_returns(benchmark_returns)
    hedged_equity = equity_from_returns(hedged_returns) if not hedged_returns.empty else pd.Series(dtype=float)
    strategy_dd = strategy_equity / strategy_equity.cummax() - 1.0
    benchmark_dd = benchmark_equity / benchmark_equity.cummax() - 1.0
    hedged_dd = hedged_equity / hedged_equity.cummax() - 1.0 if not hedged_equity.empty else pd.Series(dtype=float)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.45, 5.30), sharex=True, gridspec_kw={"height_ratios": [3.0, 1.2]})
    ax1.set_title("Equity", color="black", fontsize=9.2, fontweight="bold", pad=2)
    ax1.plot(strategy_equity.index, strategy_equity, color="#123E73", lw=1.3, label="Long")
    if not hedged_equity.empty:
        ax1.plot(hedged_equity.index, hedged_equity, color="#008C7A", lw=1.2, label="Long+Hedge")
    ax1.plot(benchmark_equity.index, benchmark_equity, color="#E31A1C", lw=1.1, ls="--", label="Benchmark")
    ax1.legend(loc="upper center", ncol=3, fontsize=9.2, frameon=False)
    ax1.grid(True, alpha=0.18)
    ax1.tick_params(labelsize=8)

    ax2.set_title("Drawdown", color="black", fontsize=9.2, fontweight="bold", pad=2)
    ax2.plot(strategy_dd.index, strategy_dd, color="#123E73", lw=1.0)
    if not hedged_dd.empty:
        ax2.plot(hedged_dd.index, hedged_dd, color="#008C7A", lw=0.95)
    ax2.plot(benchmark_dd.index, benchmark_dd, color="#E31A1C", lw=0.9)
    ax2.grid(True, alpha=0.18)
    ax2.tick_params(labelsize=8)

    if len(index) > 0:
        quarter_ticks = pd.date_range(index.min(), index.max(), freq="QS-DEC")
        quarter_ticks = quarter_ticks[(quarter_ticks >= index.min()) & (quarter_ticks <= index.max())]
        if len(quarter_ticks) > 6:
            tick_idx = np.linspace(0, len(quarter_ticks) - 1, 6).round().astype(int)
            quarter_ticks = quarter_ticks[tick_idx]
        ax2.set_xticks(quarter_ticks.to_pydatetime())
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    fig.autofmt_xdate(rotation=0, ha="center")
    fig.tight_layout(pad=0.32, h_pad=0.55)
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def update_rows(df, haircuts, output_dir=OUTPUT_DIR, regenerate_summary_charts=True):
    updated = df.copy()
    summaries = []
    for idx, row in updated.iterrows():
        market = str(row.get("Market", "")).strip()
        factor = haircuts.get(market, 1.0)
        already_applied = str(row.get("Haircut_Applied", "")).strip().lower() in {"1", "true", "yes"}

        strategy_returns = parse_return_map(row.get("Strategy_Returns"))
        hedged_returns = parse_return_map(row.get("Hedged_Strategy_Returns"))
        benchmark_returns = parse_return_map(row.get("Benchmark_Returns"))

        if factor < 1.0 and not already_applied:
            strategy_returns = apply_positive_haircut(strategy_returns, factor)
            hedged_returns = apply_positive_haircut(hedged_returns, factor)

        strategy_metrics = performance_metrics(strategy_returns, benchmark_returns)
        hedged_metrics = performance_metrics(hedged_returns, benchmark_returns) if not hedged_returns.empty else {}

        updated.at[idx, "Strategy_Returns"] = return_map(strategy_returns)
        updated.at[idx, "Positive_Return_Haircut"] = factor
        updated.at[idx, "Haircut_Applied"] = True
        updated.at[idx, "Strategy CAGR"] = strategy_metrics["cagr"]
        updated.at[idx, "Strategy MaxDD"] = strategy_metrics["maxdd"]
        updated.at[idx, "Strategy Sharpe Ratio"] = strategy_metrics["sharpe"]
        updated.at[idx, "Information Ratio"] = strategy_metrics["ir"]

        if hedged_metrics:
            updated.at[idx, "Hedged_Strategy_Returns"] = return_map(hedged_returns)
            updated.at[idx, "Hedged CAGR"] = hedged_metrics["cagr"]
            updated.at[idx, "Hedged MaxDD"] = hedged_metrics["maxdd"]
            updated.at[idx, "Hedged Sharpe Ratio"] = hedged_metrics["sharpe"]
            updated.at[idx, "Hedged Information Ratio"] = hedged_metrics["ir"]

        if regenerate_summary_charts:
            chart = make_summary_chart(updated.loc[idx], strategy_returns, hedged_returns, benchmark_returns, output_dir=output_dir)
            updated.at[idx, "Summary_Chart"] = str(chart)
        summaries.append(
            {
                "Market": market,
                "Haircut": factor,
                "Strategy CAGR": strategy_metrics["cagr"],
                "Strategy Sharpe Ratio": strategy_metrics["sharpe"],
                "Bench Cagr": row.get("Bench Cagr"),
                "Bench Sharpe": row.get("Bench Sharpe"),
            }
        )
    return updated, pd.DataFrame(summaries)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--refresh-source", action="store_true")
    args = parser.parse_args()

    haircuts = load_haircuts(Path(args.config))
    ensure_source_backup(refresh_source=args.refresh_source)
    source_df = load_source_dataframe()
    updated_df, summary = update_rows(source_df, haircuts)

    updated_df.to_csv(CSV_PATH, index=False)
    JSON_PATH.write_text(
        json.dumps(updated_df.to_dict(orient="records"), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    write_html_data(updated_df)
    write_site_report_data(updated_df)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
