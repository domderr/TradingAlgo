import builtins
import json
import os
import sys
import traceback
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

DEV_DIR = Path(__file__).resolve().parent
SITE_DIR = DEV_DIR.parent
NOTEBOOK = DEV_DIR / "TA_Portfolios.ipynb"


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

        source = source.replace("MARKETS_TO_PROCESS = \"\"", "MARKETS_TO_PROCESS = \"all\"")
        source = source.replace("PROCESS_ALL_MARKETS = False", "PROCESS_ALL_MARKETS = True")
        source = source.replace("yf.Ticker(ticker)", "yf.Ticker(ticker, session=YF_SESSION)")
        source = source.replace(
            'print(f"ERRORE su {selected_market}: {e}")',
            'print(f"ERRORE su {selected_market}: {e}")\n        traceback.print_exc()',
        )

        print(f"\n--- Executing cell {idx} ---", flush=True)
        exec(compile(source, f"{NOTEBOOK}:cell-{idx}", "exec"), namespace)

        if idx == 1:
            from curl_cffi import requests

            yf = namespace["yf"]
            yf_session = requests.Session(impersonate="chrome", verify=False)
            original_download = yf.download

            def download_with_session(*args, **kwargs):
                kwargs.setdefault("session", yf_session)
                return original_download(*args, **kwargs)

            yf.download = download_with_session
            namespace["YF_SESSION"] = yf_session
            print("Runner override: yfinance session verify=False", flush=True)

        if idx == 2:
            namespace["MARKETS_TO_PROCESS"] = "all"
            namespace["PROCESS_ALL_MARKETS"] = True
            namespace["UPDATE_SITE_REPORTS"] = True
            namespace["SITE_PROJECT_DIR"] = SITE_DIR
            namespace["SITE_REPORTS_DIR"] = SITE_DIR / "reports"
            namespace["SITE_REPORT_URLS"] = {}
            print("Runner override: all markets, site reports ->", namespace["SITE_REPORTS_DIR"], flush=True)

    market_reports_df = namespace.get("market_reports_df")
    if market_reports_df is not None and not market_reports_df.empty:
        reports_dir = SITE_DIR / "reports"
        full_json = DEV_DIR / "output" / "all_market_reports_data.json"
        full_csv = DEV_DIR / "output" / "all_market_reports_data.csv"
        market_reports_df.to_json(full_json, orient="records", indent=2, force_ascii=False)
        market_reports_df.to_csv(full_csv, index=False)

        rows = []
        for record in market_reports_df.to_dict(orient="records"):
            market = record.get("Market")
            if not market:
                continue
            row = {
                "Market": market,
                "Benchmark": record.get("Benchmark"),
                "Status": record.get("Status"),
                "Report_File": f"Report_{str(market).replace(' ', '_')}.pdf",
                "Report_Path": f"reports/Report_{str(market).replace(' ', '_')}.pdf",
                "Report_URL": f"reports/Report_{str(market).replace(' ', '_')}.pdf",
                "Updated_At": record.get("Updated_At"),
                "Last_Hedge_Short": record.get("Benchmark Hedge Short"),
                "Last_Hedge_Score": record.get("Benchmark Hedge Score"),
                "Benchmark_Hedge_Short": record.get("Benchmark Hedge Short"),
                "Benchmark_Hedge_Ticker": record.get("Benchmark Hedge Ticker"),
            }
            rows.append(row)

        (reports_dir / "reports_index.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print("Runner postprocess: wrote full market data and enriched reports_index.json", flush=True)
finally:
    builtins.input = old_input
    os.chdir(old_cwd)
