import builtins
import hashlib
import json
import os
import shutil
import traceback
from datetime import datetime
from pathlib import Path

import matplotlib
import pandas as pd

from apply_conservative_haircuts import DEFAULT_CONFIG, load_haircuts, update_rows

matplotlib.use("Agg")

PROJECT_DIR = Path(__file__).resolve().parents[1]
DEV_DIR = PROJECT_DIR / "mosaic_dev"
SITE_DIR = PROJECT_DIR
NOTEBOOK = DEV_DIR / "TA_Portfolios.ipynb"
MARKET_DATA_DIR = DEV_DIR / "market_data"
SITE_SNAPSHOT_DIR = DEV_DIR / "output" / "site_snapshots"


def display(value=None, *args, **kwargs):
    if value is not None:
        print(value)


namespace = {
    "__name__": "__main__",
    "traceback": traceback,
    "display": display,
}


def fake_input(prompt=""):
    print(prompt + "all", flush=True)
    return "all"


def safe_market_name(value):
    return str(value).replace(" ", "_").replace("/", "_")


def load_prices_from_csv(tickers, start_date, end_date=None, benchmark_ticker=None, market_name=None):
    safe_market = safe_market_name(market_name or "")
    csv_path = MARKET_DATA_DIR / safe_market / "prices_daily.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV market data non trovato: {csv_path}")

    print(f"Load CSV market_data: {market_name or 'market'} | {csv_path}", flush=True)
    prices = pd.read_csv(csv_path, parse_dates=["Date"]).set_index("Date")
    prices.index = pd.to_datetime(prices.index).tz_localize(None)
    prices = prices.sort_index()

    if start_date:
        prices = prices.loc[prices.index >= pd.to_datetime(start_date)]
    if end_date:
        prices = prices.loc[prices.index < pd.to_datetime(end_date)]

    requested = [ticker for ticker in tickers if ticker in prices.columns]
    missing = [ticker for ticker in tickers if ticker not in prices.columns]
    prices = prices[requested].dropna(axis=1, how="all")
    missing_after = [ticker for ticker in tickers if ticker not in prices.columns]
    if missing_after:
        print("Ticker senza dati o non presenti nel CSV:", missing_after, flush=True)

    benchmark_check = benchmark_ticker if benchmark_ticker is not None else tickers[0]
    if benchmark_check not in prices.columns:
        raise ValueError(f"Benchmark {benchmark_check} non presente nei dati CSV.")

    return prices


def write_html_data(market_reports_df):
    html_root = DEV_DIR / "output" / "html_data"
    for record in market_reports_df.to_dict(orient="records"):
        market = record.get("Market")
        if not market:
            continue
        out_dir = html_root / safe_market_name(market)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "report_data.json").write_text(
            json.dumps([record], ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    print(f"Runner postprocess: wrote html_data for {len(market_reports_df)} markets", flush=True)


def archive_existing_pipeline_outputs():
    reports_dir = SITE_DIR / "reports"
    output_dir = DEV_DIR / "output"
    candidates = [
        reports_dir / "reports_index.json",
        reports_dir / "reports_index.csv",
        reports_dir / "positions.json",
        reports_dir / "latest_prices.json",
        reports_dir / "market_scatter_history.json",
        output_dir / "all_market_reports_data_from_csv.json",
        output_dir / "all_market_reports_data_from_csv.csv",
        output_dir / "all_market_reports_data_from_csv.pre_conservative_haircut.json",
        output_dir / "all_market_reports_data_from_csv.pre_conservative_haircut.csv",
    ]
    candidate_dirs = [
        output_dir / "html_data",
    ]
    existing = [path for path in candidates if path.exists()]
    existing_dirs = [path for path in candidate_dirs if path.exists()]
    if not existing and not existing_dirs:
        print("Runner snapshot: no previous pipeline outputs to archive", flush=True)
        return None

    snapshot_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_dir = SITE_SNAPSHOT_DIR / snapshot_id
    suffix = 1
    while snapshot_dir.exists():
        suffix += 1
        snapshot_dir = SITE_SNAPSHOT_DIR / f"{snapshot_id}_{suffix}"
    snapshot_dir.mkdir(parents=True, exist_ok=False)

    manifest = {
        "snapshot_id": snapshot_dir.name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_dirs": [str(reports_dir), str(output_dir)],
        "inputs": {},
        "files": [],
        "directories": [],
        "immutable": True,
        "reprocess_policy": "Do not rerun or recalculate this snapshot when portfolio construction logic changes. Use it only as historical evidence for coherence checks.",
        "note": "Previous pipeline output snapshot saved before writing the new run. Not published by the site.",
    }
    for path in existing:
        destination = snapshot_dir / path.name
        shutil.copy2(path, destination)
        manifest["files"].append(path.name)
    for path in existing_dirs:
        destination = snapshot_dir / path.name
        shutil.copytree(path, destination)
        manifest["directories"].append(path.name)
    inputs_dir = snapshot_dir / "inputs"
    input_files = [
        DEV_DIR / "Tickers.xlsx",
        DEV_DIR / "conservative_haircuts.csv",
    ]
    for path in input_files:
        if not path.exists():
            continue
        inputs_dir.mkdir(exist_ok=True)
        destination = inputs_dir / path.name
        shutil.copy2(path, destination)
        manifest["inputs"][path.name] = {
            "path": str(destination.relative_to(snapshot_dir)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    (snapshot_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Runner snapshot: archived previous pipeline outputs -> {snapshot_dir}", flush=True)
    return snapshot_dir


def write_site_index(market_reports_df):
    reports_dir = SITE_DIR / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for record in market_reports_df.to_dict(orient="records"):
        market = record.get("Market")
        if not market:
            continue
        market_slug = str(market).replace(" ", "_")
        report_file = f"Report_{market_slug}.html"
        report_url = f"reports_html/{market_slug}/{report_file}"
        rows.append(
            {
                "Market": market,
                "Benchmark": record.get("Benchmark"),
                "Status": record.get("Status"),
                "Report_File": report_file,
                "Report_Path": report_url,
                "Report_URL": report_url,
                "Updated_At": record.get("Updated_At"),
                "Last_Hedge_Short": record.get("Benchmark Hedge Short"),
                "Last_Hedge_Score": record.get("Hedge Portfolio Score"),
                "Benchmark_Hedge_Short": record.get("Benchmark Hedge Short"),
                "Benchmark_Hedge_Ticker": record.get("Benchmark Hedge Ticker"),
            }
        )
    (reports_dir / "reports_index.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    pd.DataFrame(rows).to_csv(reports_dir / "reports_index.csv", index=False)
    print("Runner postprocess: wrote enriched site reports_index", flush=True)


def apply_configured_haircuts(market_reports_df):
    haircuts = load_haircuts(DEFAULT_CONFIG)
    adjusted_df, summary = update_rows(market_reports_df, haircuts, output_dir=DEV_DIR / "output")
    print("Runner postprocess: applied conservative positive-return haircuts", flush=True)
    print(summary.to_string(index=False), flush=True)
    return adjusted_df


old_input = builtins.input
old_cwd = Path.cwd()
builtins.input = fake_input
os.chdir(DEV_DIR)

try:
    data = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    for idx, cell in enumerate(data.get("cells", []), start=1):
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell.get("source", []))
        if not source.strip():
            continue

        source = source.replace('MARKETS_TO_PROCESS = ""', 'MARKETS_TO_PROCESS = "all"')
        source = source.replace("PROCESS_ALL_MARKETS = False", "PROCESS_ALL_MARKETS = True")
        source = source.replace(
            'print(f"ERRORE su {selected_market}: {e}")',
            'print(f"ERRORE su {selected_market}: {e}")\n        traceback.print_exc()',
        )

        print(f"\n--- Executing cell {idx} ---", flush=True)
        exec(compile(source, f"{NOTEBOOK}:cell-{idx}", "exec"), namespace)

        if idx == 2:
            namespace["MARKETS_TO_PROCESS"] = "all"
            namespace["PROCESS_ALL_MARKETS"] = True
            namespace["GENERATE_PDF_REPORTS"] = False
            namespace["UPDATE_SITE_REPORTS"] = True
            namespace["SITE_PROJECT_DIR"] = SITE_DIR
            namespace["SITE_REPORTS_DIR"] = SITE_DIR / "reports"
            namespace["SITE_REPORT_URLS"] = {}
            print("Runner override: all markets, site reports ->", namespace["SITE_REPORTS_DIR"], flush=True)
            print("Runner override: GENERATE_PDF_REPORTS ->", namespace["GENERATE_PDF_REPORTS"], flush=True)

        if idx == 5:
            namespace["download_prices_yfinance"] = load_prices_from_csv
            print("Runner override: download_prices_yfinance -> market_data CSV", flush=True)

    market_reports_df = namespace.get("market_reports_df")
    if market_reports_df is not None and not market_reports_df.empty:
        output_dir = DEV_DIR / "output"
        full_json = output_dir / "all_market_reports_data_from_csv.json"
        full_csv = output_dir / "all_market_reports_data_from_csv.csv"
        output_dir.mkdir(parents=True, exist_ok=True)
        archive_existing_pipeline_outputs()
        market_reports_df.to_json(
            output_dir / "all_market_reports_data_from_csv.pre_conservative_haircut.json",
            orient="records",
            indent=2,
            force_ascii=False,
            default_handler=str,
        )
        market_reports_df.to_csv(output_dir / "all_market_reports_data_from_csv.pre_conservative_haircut.csv", index=False)
        market_reports_df = apply_configured_haircuts(market_reports_df)
        full_json = DEV_DIR / "output" / "all_market_reports_data_from_csv.json"
        full_csv = DEV_DIR / "output" / "all_market_reports_data_from_csv.csv"
        market_reports_df.to_json(full_json, orient="records", indent=2, force_ascii=False, default_handler=str)
        market_reports_df.to_csv(full_csv, index=False)
        write_html_data(market_reports_df)
        write_site_index(market_reports_df)
finally:
    builtins.input = old_input
    os.chdir(old_cwd)
