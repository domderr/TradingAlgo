import argparse
import builtins
import html
import json
import os
import re
import shutil
import traceback
from datetime import datetime
from pathlib import Path


def safe_market_name(value):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(value)).strip("_")


def ticker_from_asset_png(path):
    name = path.name.replace("_asset_dashboard.png", "")
    return name.replace("_", ".")


def pct(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{number * 100:.2f}%"


def num(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"{number:.2f}"


def text(value):
    if value is None:
        return "-"
    if isinstance(value, float) and value != value:
        return "-"
    return str(value)


def html_text(value):
    return html.escape(text(value))


def read_tickers(tickers_xlsx, market):
    try:
        import openpyxl
    except ImportError:
        return []

    workbook = openpyxl.load_workbook(tickers_xlsx, read_only=True, data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if len(rows) < 3:
        return []

    headers = [str(cell).strip() if cell is not None else "" for cell in rows[0]]
    target_index = None
    for idx, header in enumerate(headers):
        if header.lower() == market.lower():
            target_index = idx
            break
    if target_index is None:
        return []

    tickers = []
    for row in rows[2:]:
        if target_index < len(row) and row[target_index]:
            tickers.append(str(row[target_index]).strip())
    return tickers


def sanitize_for_json(value):
    try:
        import pandas as pd
        import numpy as np
    except Exception:
        pd = None
        np = None

    if pd is not None:
        if isinstance(value, pd.DataFrame):
            return [sanitize_for_json(item) for item in value.to_dict(orient="records")]
        if isinstance(value, pd.Series):
            return sanitize_for_json(value.to_dict())
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
    if np is not None:
        if isinstance(value, np.generic):
            return sanitize_for_json(value.item())
        if isinstance(value, np.ndarray):
            return sanitize_for_json(value.tolist())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_for_json(item) for item in value]
    if isinstance(value, float) and value != value:
        return None
    return value


def run_notebook(dev_dir, market_choice):
    import matplotlib

    matplotlib.use("Agg")
    notebook = dev_dir / "TA_Portfolios.ipynb"
    namespace = {
        "__name__": "__main__",
        "traceback": traceback,
        "display": lambda value=None, *args, **kwargs: print(value) if value is not None else None,
    }

    def patch_source(source):
        source = source.replace("UPDATE_SITE_REPORTS = True", "UPDATE_SITE_REPORTS = False")
        source = source.replace('MARKETS_TO_PROCESS = ""', f'MARKETS_TO_PROCESS = "{market_choice}"')
        source = source.replace(
            'print(f"ERRORE su {selected_market}: {e}")',
            'print(f"ERRORE su {selected_market}: {e}")\n        traceback.print_exc()',
        )
        return source

    def fake_input(prompt=""):
        print(prompt + market_choice)
        return market_choice

    old_input = builtins.input
    old_cwd = Path.cwd()
    builtins.input = fake_input
    os.chdir(dev_dir)
    try:
        notebook_data = json.loads(notebook.read_text(encoding="utf-8"))
        for idx, cell in enumerate(notebook_data.get("cells", []), start=1):
            if cell.get("cell_type") != "code":
                continue
            source = "".join(cell.get("source", []))
            if not source.strip():
                continue
            print(f"\n--- Executing cell {idx} ---", flush=True)
            exec(compile(patch_source(source), f"{notebook}:cell-{idx}", "exec"), namespace)
    finally:
        builtins.input = old_input
        os.chdir(old_cwd)

    rows = sanitize_for_json(namespace.get("market_reports_df", []))
    if not rows:
        raise RuntimeError("Notebook completed but did not expose market_reports_df.")
    return rows


def load_or_create_report_data(dev_dir, market, market_choice, rerun):
    data_dir = dev_dir / "output" / "html_data" / market
    data_dir.mkdir(parents=True, exist_ok=True)
    data_path = data_dir / "report_data.json"

    if rerun or not data_path.exists():
        rows = run_notebook(dev_dir, market_choice)
        data_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    else:
        rows = json.loads(data_path.read_text(encoding="utf-8"))

    for row in rows:
        if str(row.get("Market", "")).lower() == market.lower():
            return row, data_path
    return rows[0], data_path


def copy_if_exists(src, dst):
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return True
    return False


def write_asset_page(out_dir, ticker, image_name, market):
    page_name = f"{safe_market_name(ticker)}.html"
    body = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html_text(ticker)} | {html_text(market)} Asset Chart</title>
  <link rel="stylesheet" href="report.css" />
</head>
<body>
  <main class="asset-shell">
    <nav class="top-actions">
      <a href="Report_{safe_market_name(market)}.html">Back to Report</a>
      <a href="all-assets.html">View All Benchmark Assets</a>
    </nav>
    <section class="report-page asset-page">
      <p class="eyebrow">{html_text(market)} Asset Detail</p>
      <h1>{html_text(ticker)}</h1>
      <img class="asset-chart" src="assets/{html.escape(image_name)}" alt="{html_text(ticker)} asset dashboard" />
    </section>
  </main>
</body>
</html>
"""
    (out_dir / page_name).write_text(body, encoding="utf-8")
    return page_name


def build_css(out_dir):
    css = """
* { box-sizing: border-box; }
body {
  margin: 0;
  background: #e8eef6;
  color: #071a33;
  font-family: Arial, Helvetica, sans-serif;
}
.report-shell, .asset-shell { padding: 24px; }
.top-actions {
  max-width: 1120px;
  margin: 0 auto 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.top-actions a, .button {
  display: inline-block;
  padding: 10px 14px;
  border-radius: 4px;
  background: #168eea;
  color: #fff;
  text-decoration: none;
  font-weight: 700;
  font-size: 13px;
}
.top-actions a.secondary { background: #334155; }
.report-page {
  width: 1120px;
  min-height: 790px;
  margin: 0 auto 24px;
  padding: 30px;
  background: #fff;
  border: 1px solid #dbe3ef;
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.14);
}
.report-header {
  display: flex;
  justify-content: space-between;
  gap: 22px;
  padding-bottom: 18px;
  border-bottom: 3px solid #071a33;
}
.brand { color: #0b5fa5; font-size: 13px; font-weight: 800; letter-spacing: 1.2px; text-transform: uppercase; }
h1 { margin: 6px 0 6px; font-family: Georgia, serif; font-size: 34px; line-height: 1.1; }
h2 { margin: 0 0 16px; color: #0b5fa5; font-family: Georgia, serif; font-size: 26px; }
h3 { margin: 0 0 10px; color: #071a33; font-size: 18px; }
p { line-height: 1.55; }
.eyebrow { margin: 0 0 8px; color: #0b5fa5; font-size: 12px; font-weight: 800; letter-spacing: 1.2px; text-transform: uppercase; }
.meta { color: #475569; font-size: 13px; text-align: right; line-height: 1.6; }
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 10px;
  margin: 20px 0;
}
.kpi {
  padding: 13px;
  border-radius: 6px;
  background: #071a33;
  color: #fff;
}
.kpi span { display: block; color: #93c5fd; font-size: 11px; text-transform: uppercase; letter-spacing: 0.8px; }
.kpi strong { display: block; margin-top: 6px; font-size: 20px; }
.two-col {
  display: grid;
  grid-template-columns: 1.2fr 0.8fr;
  gap: 18px;
}
.panel {
  padding: 18px;
  border: 1px solid #dbe3ef;
  border-radius: 6px;
  background: #f8fafc;
}
.chart-img {
  width: 100%;
  max-height: 525px;
  object-fit: contain;
  border: 1px solid #e2e8f0;
  background: #fff;
}
.asset-chart {
  width: 100%;
  display: block;
  border: 1px solid #dbe3ef;
}
.mini-table, .asset-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.mini-table th, .mini-table td, .asset-table th, .asset-table td {
  padding: 9px 10px;
  border-bottom: 1px solid #dbe3ef;
  text-align: left;
  vertical-align: top;
}
.mini-table th, .asset-table th {
  color: #0b5fa5;
  font-size: 11px;
  letter-spacing: 0.7px;
  text-transform: uppercase;
}
.status-badge {
  display: inline-block;
  padding: 5px 8px;
  border-radius: 999px;
  background: #dcfce7;
  color: #166534;
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}
.drivers {
  margin: 0;
  padding-left: 18px;
  line-height: 1.55;
}
.asset-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.asset-card {
  padding: 14px;
  border: 1px solid #dbe3ef;
  border-radius: 6px;
  background: #fff;
  text-decoration: none;
  color: #071a33;
}
.asset-card strong { display: block; margin-bottom: 6px; }
.asset-card span { color: #0b5fa5; font-size: 12px; font-weight: 700; }
.footer-note { margin-top: 18px; color: #64748b; font-size: 12px; }
@media (max-width: 1180px) {
  .report-page { width: 100%; min-height: 0; }
  .kpi-grid { grid-template-columns: repeat(2, 1fr); }
  .two-col { grid-template-columns: 1fr; }
  .asset-grid { grid-template-columns: repeat(2, 1fr); }
}
@media print {
  body { background: #fff; }
  .top-actions { display: none; }
  .report-shell, .asset-shell { padding: 0; }
  .report-page {
    width: 297mm;
    min-height: 210mm;
    margin: 0;
    box-shadow: none;
    page-break-after: always;
  }
}
"""
    (out_dir / "report.css").write_text(css.strip() + "\n", encoding="utf-8")


def build_html(dev_dir, site_dir, market, market_choice, rerun):
    row, data_path = load_or_create_report_data(dev_dir, market, market_choice, rerun)
    safe_market = safe_market_name(market)
    out_dir = site_dir / "reports_html" / safe_market
    asset_out_dir = out_dir / "assets"
    out_dir.mkdir(parents=True, exist_ok=True)
    asset_out_dir.mkdir(parents=True, exist_ok=True)

    output_dir = dev_dir / "output"
    summary_src = output_dir / "_summary_charts" / safe_market / f"summary_{safe_market}.png"
    exposure_src = output_dir / "_exposure_charts" / safe_market / f"exposure_long_net_{safe_market}.png"

    copy_if_exists(summary_src, asset_out_dir / summary_src.name)
    copy_if_exists(exposure_src, asset_out_dir / exposure_src.name)
    shutil.copy2(data_path, out_dir / "report_data.json")

    asset_src_dir = output_dir / "_asset_detail_pages" / safe_market
    asset_pages = []
    if asset_src_dir.exists():
        for image in sorted(asset_src_dir.glob("*_asset_dashboard.png")):
            ticker = ticker_from_asset_png(image)
            target_name = image.name
            shutil.copy2(image, asset_out_dir / target_name)
            page_name = write_asset_page(out_dir, ticker, target_name, market)
            asset_pages.append({"ticker": ticker, "image": target_name, "page": page_name})

    tickers = read_tickers(dev_dir / "Tickers.xlsx", market)
    page_by_ticker = {item["ticker"].upper(): item for item in asset_pages}
    all_assets = []
    for ticker in tickers:
        key = ticker.upper()
        item = page_by_ticker.get(key)
        all_assets.append({
            "ticker": ticker,
            "page": item["page"] if item else "",
            "has_chart": bool(item),
        })
    if not all_assets:
        all_assets = [{"ticker": item["ticker"], "page": item["page"], "has_chart": True} for item in asset_pages]

    build_css(out_dir)

    selection = row.get("Last Weekly Selection") or []
    if isinstance(selection, str):
        selection_rows = [line for line in re.split(r"<br\s*/?>|\n", selection) if line.strip()]
        selection_html = "".join(f"<tr><td>{html_text(item)}</td><td><span class=\"status-badge\">Selected</span></td></tr>" for item in selection_rows)
    else:
        selection_html = "".join(
            "<tr>"
            f"<td>{html_text(item.get('Ticker'))}</td>"
            f"<td>{html_text(item.get('Name'))}</td>"
            f"<td>{html_text(item.get('Sector'))}</td>"
            f"<td><span class=\"status-badge\">Selected</span></td>"
            "</tr>"
            for item in selection
        )
    if not selection_html:
        selection_html = "<tr><td colspan=\"4\">-</td></tr>"

    drivers = text(row.get("Selection Drivers"))
    driver_items = [item.strip() for item in re.split(r"<br\s*/?>|\n", drivers) if item.strip() and item.strip() != "-"]
    drivers_html = "".join(f"<li>{html_text(item)}</li>" for item in driver_items) or "<li>-</li>"

    updated = datetime.now().strftime("%Y-%m-%d %H:%M")
    report_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Report {html_text(market)} | TradingAlgo Mosaic</title>
  <link rel="stylesheet" href="report.css" />
</head>
<body>
  <main class="report-shell">
    <nav class="top-actions">
      <a href="all-assets.html">View All Benchmark Assets</a>
      <a class="secondary" href="mailto:domderrico@gmail.com?subject=TradingAlgo%20Mosaic%20PDF%20Access%20Request">Request PDF Extra</a>
      <a class="secondary" href="report_data.json">JSON Data</a>
    </nav>

    <section class="report-page">
      <header class="report-header">
        <div>
          <div class="brand">TradingAlgo Mosaic</div>
          <h1>{html_text(market)} Weekly Report</h1>
          <p class="eyebrow">Benchmark: {html_text(row.get("Benchmark"))}</p>
        </div>
        <div class="meta">
          Generated: {html_text(updated)}<br />
          Universe: {html_text(row.get("Number of Tickers"))} assets<br />
          Status: {html_text(row.get("Status"))}
        </div>
      </header>

      <div class="kpi-grid">
        <div class="kpi"><span>Strategy CAGR</span><strong>{pct(row.get("Strategy CAGR"))}</strong></div>
        <div class="kpi"><span>Hedged CAGR</span><strong>{pct(row.get("Hedged CAGR"))}</strong></div>
        <div class="kpi"><span>Strategy MaxDD</span><strong>{pct(row.get("Strategy MaxDD"))}</strong></div>
        <div class="kpi"><span>Hedged MaxDD</span><strong>{pct(row.get("Hedged MaxDD"))}</strong></div>
        <div class="kpi"><span>Sharpe</span><strong>{num(row.get("Strategy Sharpe Ratio"))}</strong></div>
        <div class="kpi"><span>Hedge Short</span><strong>{pct(row.get("Benchmark Hedge Short"))}</strong></div>
      </div>

      <div class="two-col">
        <div class="panel">
          <h2>Summary Page</h2>
          <img class="chart-img" src="assets/summary_{safe_market}.png" alt="{html_text(market)} summary chart" />
        </div>
        <div class="panel">
          <h2>Current Selection</h2>
          <table class="mini-table">
            <thead><tr><th>Ticker</th><th>Name</th><th>Sector</th><th>Status</th></tr></thead>
            <tbody>{selection_html}</tbody>
          </table>
          <h3>Weekly Changes</h3>
          <table class="mini-table">
            <tbody>
              <tr><th>Added</th><td>{html_text(row.get("Added Tickers"))}</td></tr>
              <tr><th>Removed</th><td>{html_text(row.get("Removed Tickers"))}</td></tr>
              <tr><th>Hedge</th><td>Short {html_text(row.get("Benchmark Hedge Ticker"))}: {pct(row.get("Benchmark Hedge Short"))}</td></tr>
              <tr><th>Hedge Score</th><td>{num(row.get("Hedge Portfolio Score"))}</td></tr>
            </tbody>
          </table>
        </div>
      </div>
      <p class="footer-note">This HTML report mirrors the PDF structure and is generated from the same market batch output.</p>
    </section>

    <section class="report-page">
      <h2>Equity, Drawdown and Hedge Exposure</h2>
      <div class="two-col">
        <div class="panel">
          <h3>Equity and Drawdown</h3>
          <img class="chart-img" src="assets/summary_{safe_market}.png" alt="{html_text(market)} equity and drawdown" />
        </div>
        <div class="panel">
          <h3>Long Exposure vs Net Exposure</h3>
          <img class="chart-img" src="assets/exposure_long_net_{safe_market}.png" alt="{html_text(market)} exposure chart" />
        </div>
      </div>
    </section>

    <section class="report-page">
      <h2>Selection Drivers</h2>
      <ol class="drivers">{drivers_html}</ol>
      <h2 style="margin-top: 28px;">Performance Table</h2>
      <table class="asset-table">
        <thead><tr><th>Metric</th><th>Strategy</th><th>Hedged</th><th>Benchmark</th></tr></thead>
        <tbody>
          <tr><td>CAGR</td><td>{pct(row.get("Strategy CAGR"))}</td><td>{pct(row.get("Hedged CAGR"))}</td><td>{pct(row.get("Bench Cagr"))}</td></tr>
          <tr><td>MaxDD</td><td>{pct(row.get("Strategy MaxDD"))}</td><td>{pct(row.get("Hedged MaxDD"))}</td><td>{pct(row.get("Bench_MaxDD"))}</td></tr>
          <tr><td>Sharpe</td><td>{num(row.get("Strategy Sharpe Ratio"))}</td><td>{num(row.get("Hedged Sharpe Ratio"))}</td><td>{num(row.get("Bench Sharpe"))}</td></tr>
          <tr><td>Information Ratio</td><td>{num(row.get("Information Ratio"))}</td><td>{num(row.get("Hedged Information Ratio"))}</td><td>-</td></tr>
        </tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""
    (out_dir / f"Report_{safe_market}.html").write_text(report_html, encoding="utf-8")

    asset_row_parts = []
    for item in all_assets:
        status = '<span class="status-badge">Chart Ready</span>' if item["has_chart"] else "No chart"
        chart_link = f'<a class="button" href="{html.escape(item["page"])}">View Chart</a>' if item["page"] else "-"
        asset_row_parts.append(
            "<tr>"
            f"<td>{html_text(item['ticker'])}</td>"
            f"<td>{status}</td>"
            f"<td>{chart_link}</td>"
            "</tr>"
        )
    asset_rows = "".join(asset_row_parts)
    asset_cards = "".join(
        f"<a class=\"asset-card\" href=\"{html.escape(item['page'])}\"><strong>{html_text(item['ticker'])}</strong><span>View Chart</span></a>"
        for item in all_assets
        if item["page"]
    )
    all_assets_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html_text(market)} Benchmark Assets | TradingAlgo Mosaic</title>
  <link rel="stylesheet" href="report.css" />
</head>
<body>
  <main class="report-shell">
    <nav class="top-actions">
      <a href="Report_{safe_market}.html">Back to Report</a>
    </nav>
    <section class="report-page">
      <p class="eyebrow">View All Benchmark Assets</p>
      <h1>{html_text(market)} Asset List</h1>
      <p>{len(all_assets)} assets in the benchmark universe. Each chart opens the individual dashboard generated by the Mosaic batch.</p>
      <table class="asset-table">
        <thead><tr><th>Ticker</th><th>Status</th><th>Chart</th></tr></thead>
        <tbody>{asset_rows}</tbody>
      </table>
    </section>
    <section class="report-page">
      <h2>Chart Gallery</h2>
      <div class="asset-grid">{asset_cards}</div>
    </section>
  </main>
</body>
</html>
"""
    (out_dir / "all-assets.html").write_text(all_assets_html, encoding="utf-8")

    return out_dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev-dir", required=True)
    parser.add_argument("--site-dir", default=".")
    parser.add_argument("--market", default="Italy30")
    parser.add_argument("--market-choice", default="3")
    parser.add_argument("--rerun", action="store_true")
    args = parser.parse_args()

    out_dir = build_html(
        Path(args.dev_dir).resolve(),
        Path(args.site_dir).resolve(),
        args.market,
        args.market_choice,
        args.rerun,
    )
    print(f"HTML report generated: {out_dir}")


if __name__ == "__main__":
    main()
