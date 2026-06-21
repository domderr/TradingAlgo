import argparse
import builtins
import html
import json
import os
import re
import shutil
import traceback
from datetime import datetime, timedelta
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


def useful_value(value):
    value = text(value).strip()
    return value if value and value != "-" else ""


def last_available_friday(today=None):
    today = today or datetime.now().date()
    return today - timedelta(days=(today.weekday() - 4) % 7)


def report_date_label():
    return last_available_friday().strftime("%d %b %Y")


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


def read_ticker_metadata(dev_dir, market, tickers):
    metadata_path = dev_dir / "output" / "html_data" / market / "ticker_metadata.json"
    if not metadata_path.exists():
        metadata_path = dev_dir / "output" / "html_data" / safe_market_name(market) / "ticker_metadata.json"
    metadata = {}
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            metadata = {}

    normalized = {str(key).upper(): value for key, value in metadata.items() if isinstance(value, dict)}
    missing = [ticker for ticker in tickers if ticker.upper() not in normalized]
    if missing:
        try:
            from curl_cffi import requests
            import yfinance as yf

            session = requests.Session(impersonate="chrome", verify=False)
            for ticker in missing:
                try:
                    info = yf.Ticker(ticker, session=session).get_info()
                    normalized[ticker.upper()] = {
                        "Name": info.get("shortName") or info.get("longName") or ticker,
                        "Sector": info.get("sector") or "-",
                        "Industry": info.get("industry") or "-",
                    }
                except Exception:
                    normalized[ticker.upper()] = {"Name": ticker, "Sector": "-", "Industry": "-"}
        except Exception:
            for ticker in missing:
                normalized.setdefault(ticker.upper(), {"Name": ticker, "Sector": "-", "Industry": "-"})

        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8")

    return normalized


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
    data_root = dev_dir / "output" / "html_data"
    safe_data_dir = data_root / safe_market_name(market)
    display_data_dir = data_root / market
    data_dir = safe_data_dir if (safe_data_dir / "report_data.json").exists() else display_data_dir
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
  padding: 12px;
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 6px;
  background: #071423;
  box-shadow: 0 12px 30px rgba(7,20,35,0.24);
}
.top-actions a {
  display: inline-block;
  padding: 10px 14px;
  border-radius: 4px;
  border: 1px solid rgba(255,255,255,0.18);
  background: rgba(255,255,255,0.06);
  color: #f8fafc;
  text-decoration: none;
  font-weight: 700;
  font-size: 13px;
}
.top-actions a:hover { background: rgba(74,163,255,0.18); }
.top-actions a.secondary { background: rgba(255,255,255,0.1); }
.button {
  display: inline-block;
  padding: 10px 14px;
  border-radius: 4px;
  background: #168eea;
  color: #fff;
  text-decoration: none;
  font-weight: 700;
  font-size: 13px;
}
.report-dashboard {
  width: 1120px;
  margin: 0 auto 24px;
  padding: 30px;
  background: #fff;
  border: 1px solid #dbe3ef;
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.14);
}
.dashboard-header {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: flex-start;
  padding-bottom: 18px;
  border-bottom: 3px solid #071a33;
}
.dashboard-header h1 {
  margin: 4px 0 8px;
  color: #071a33;
  font-size: 46px;
}
.dashboard-meta {
  color: #475569;
  font-size: 13px;
  line-height: 1.55;
  text-align: right;
}
.dashboard-grid {
  display: grid;
  grid-template-columns: 1.05fr 0.95fr;
  gap: 18px;
  margin-top: 22px;
}
.dashboard-card {
  padding: 18px;
  border: 1px solid #dbe3ef;
  border-radius: 6px;
  background: #f8fafc;
}
.dashboard-card h2,
.chart-section h2,
.performance-section h2 {
  margin: 0 0 14px;
  color: #0b5fa5;
  font-family: Georgia, serif;
  font-size: 31px;
}
.changes-table th {
  width: 42%;
}
.changes-table .in-label {
  color: #07850d;
  font-weight: 800;
}
.changes-table .out-label {
  color: #e00000;
  font-weight: 800;
}
.chart-section,
.performance-section {
  margin-top: 22px;
}
.chart-stack {
  display: grid;
  gap: 16px;
}
.chart-frame {
  padding: 12px;
  border: 1px solid #dbe3ef;
  border-radius: 6px;
  background: #fff;
}
.chart-frame h3 {
  margin: 0 0 10px;
  color: #071a33;
  font-size: 19px;
}
.dashboard-chart {
  width: 100%;
  max-height: 620px;
  display: block;
  object-fit: contain;
  border: 1px solid #e2e8f0;
  background: #fff;
}
.exposure-chart {
  max-height: 420px;
}
.performance-table td,
.performance-table th {
  font-size: 16px;
}
.ticker-link {
  color: #0b5fa5;
  font-weight: 800;
  text-decoration: none;
}
.ticker-link:hover {
  text-decoration: underline;
}
.pdf-summary-page {
  padding: 34px 44px;
  font-size: 14px;
}
.pdf-summary-header {
  display: grid;
  grid-template-columns: 185px 1fr 185px;
  align-items: center;
  gap: 18px;
  padding-bottom: 14px;
  border-bottom: 2px solid #234f7c;
}
.pdf-logo {
  width: 116px;
  display: block;
}
.pdf-title {
  margin: 0;
  color: #214f7d;
  font-family: Arial, Helvetica, sans-serif;
  font-size: 29px;
  font-weight: 800;
  line-height: 1.1;
  text-align: center;
}
.pdf-week {
  color: #111;
  font-size: 14px;
  text-align: right;
  white-space: nowrap;
}
.pdf-section-title {
  margin: 38px 0 14px;
  color: #214f7d;
  font-size: 22px;
  font-weight: 800;
}
.portfolio-summary-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  border: 1px solid #e2e2e2;
  font-size: 14px;
}
.portfolio-summary-table th {
  padding: 14px 12px;
  background: #214f7d;
  color: #fff;
  font-size: 15px;
  font-weight: 800;
  text-align: center;
}
.portfolio-summary-table td {
  height: 238px;
  padding: 14px 12px;
  border-left: 1px solid #e2e2e2;
  vertical-align: middle;
}
.portfolio-summary-table td:first-child {
  border-left: 0;
}
.market-cell strong {
  display: block;
}
.metric-mini-table {
  width: auto;
  margin: 0 auto;
  border-collapse: collapse;
}
.metric-mini-table th,
.metric-mini-table td {
  height: auto;
  padding: 4px 4px;
  border: 0;
  background: transparent;
  color: #111;
  font-size: 12px;
  text-align: right;
  white-space: nowrap;
}
.metric-mini-table th:first-child,
.metric-mini-table td:first-child {
  text-align: left;
  font-weight: 800;
}
.selection-list,
.changes-list {
  margin: 0;
  padding: 0;
  list-style: none;
  line-height: 2.05;
}
.changes-label-in {
  color: #07850d;
  font-weight: 800;
}
.changes-label-out {
  color: #f00;
  font-weight: 800;
}
.pdf-info-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0;
  margin-top: 20px;
}
.pdf-info-block {
  min-height: 170px;
  padding: 0 20px;
  border-left: 1px solid #d7dce4;
}
.pdf-info-block:first-child {
  border-left: 0;
}
.pdf-info-block h2 {
  margin: 0 0 8px;
  color: #214f7d;
  font-family: Arial, Helvetica, sans-serif;
  font-size: 22px;
  font-weight: 800;
}
.pdf-info-block p {
  margin: 0;
  color: #111;
  font-size: 12.5px;
  line-height: 1.2;
}
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
h1 { margin: 6px 0 6px; font-family: Georgia, serif; font-size: 42px; line-height: 1.1; }
h2 { margin: 0 0 16px; color: #0b5fa5; font-family: Georgia, serif; font-size: 31px; }
h3 { margin: 0 0 10px; color: #071a33; font-size: 21px; }
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
.two-col.balanced {
  grid-template-columns: 1fr 1fr;
}
.panel {
  padding: 18px;
  border: 1px solid #dbe3ef;
  border-radius: 6px;
  background: #f8fafc;
}
.full-chart-panel { padding: 12px; }
.chart-img {
  width: 100%;
  max-height: 525px;
  object-fit: contain;
  border: 1px solid #e2e8f0;
  background: #fff;
}
.wide-chart { max-height: 660px; }
.asset-chart {
  width: 100%;
  display: block;
  border: 1px solid #dbe3ef;
}
.mini-table, .asset-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 15px;
}
.mini-table th, .mini-table td, .asset-table th, .asset-table td {
  padding: 12px 12px;
  border-bottom: 1px solid #dbe3ef;
  text-align: left;
  vertical-align: top;
}
.mini-table th, .asset-table th {
  color: #0b5fa5;
  font-size: 13px;
  letter-spacing: 0.7px;
  text-transform: uppercase;
}
.status-badge {
  display: inline-block;
  padding: 5px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
}
.status-selected { background: #dcfce7; color: #166534; }
.status-watchlist { background: #fef3c7; color: #92400e; }
.status-rejected { background: #fee2e2; color: #991b1b; }
.status-neutral { background: #e2e8f0; color: #334155; }
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
.gallery-page {
  width: min(1440px, calc(100vw - 48px));
}
.gallery-page h1 { font-size: 48px; }
.gallery-table td {
  vertical-align: middle;
  font-size: 16px;
}
.gallery-table th {
  font-size: 14px;
}
.thumb-button {
  width: 210px;
  padding: 0;
  border: 1px solid #dbe3ef;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  overflow: hidden;
}
.thumb-button img {
  width: 100%;
  aspect-ratio: 16 / 10;
  display: block;
  object-fit: contain;
  background: #f8fafc;
}
.chart-modal {
  position: fixed;
  inset: 0;
  z-index: 20;
  display: none;
  align-items: center;
  justify-content: center;
  padding: 28px;
  background: rgba(7, 26, 51, 0.88);
}
.chart-modal.is-open { display: flex; }
.chart-modal img {
  max-width: min(1280px, 96vw);
  max-height: 88vh;
  border: 1px solid #dbe3ef;
  border-radius: 6px;
  background: #fff;
}
.chart-modal-close {
  position: fixed;
  top: 18px;
  right: 18px;
  padding: 10px 14px;
  border: 0;
  border-radius: 4px;
  background: #168eea;
  color: #fff;
  cursor: pointer;
  font-weight: 800;
}
.footer-note { margin-top: 18px; color: #64748b; font-size: 12px; }
@media (max-width: 1180px) {
  .report-dashboard { width: 100%; }
  .dashboard-header { display: block; }
  .dashboard-meta { text-align: left; }
  .dashboard-grid { grid-template-columns: 1fr; }
  .report-page { width: 100%; min-height: 0; }
  .pdf-summary-header { grid-template-columns: 1fr; text-align: left; }
  .pdf-title, .pdf-week { text-align: left; }
  .portfolio-summary-table { table-layout: auto; }
  .portfolio-summary-table td { height: auto; }
  .pdf-info-grid { grid-template-columns: 1fr; gap: 18px; }
  .pdf-info-block { border-left: 0; padding: 0; }
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
  .pdf-summary-page {
    width: 297mm;
    min-height: 210mm;
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
    copy_if_exists(summary_src, asset_out_dir / summary_src.name)
    exposure_src = output_dir / "_exposure_charts" / safe_market / f"exposure_long_net_{safe_market}.png"
    exposure_asset_name = exposure_src.name if copy_if_exists(exposure_src, asset_out_dir / exposure_src.name) else ""
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
    ticker_metadata = read_ticker_metadata(dev_dir, market, tickers)

    selection = row.get("Last Weekly Selection") or []
    selection_name_map = {}
    selection_sector_map = {}
    selection_industry_map = {}
    if isinstance(selection, str):
        selection_rows = [line for line in re.split(r"<br\s*/?>|\n", selection) if line.strip()]
        selection_html = "".join(f"<tr><td>{html_text(item)}</td><td>-</td><td>-</td><td>-</td></tr>" for item in selection_rows)
    else:
        selection_parts = []
        for item in selection:
            ticker_key = text(item.get("Ticker")).upper()
            metadata = ticker_metadata.get(ticker_key, {})
            name = useful_value(item.get("Name")) or metadata.get("Name") or text(item.get("Ticker"))
            sector = useful_value(item.get("Sector")) or metadata.get("Sector") or "-"
            industry = useful_value(item.get("Industry")) or metadata.get("Industry") or "-"
            selection_name_map[ticker_key] = name
            selection_sector_map[ticker_key] = sector
            selection_industry_map[ticker_key] = industry
            selection_parts.append(
                "<tr>"
                f"<td>{html_text(item.get('Ticker'))}</td>"
                f"<td>{html_text(name)}</td>"
                f"<td>{html_text(sector)}</td>"
                f"<td>{html_text(industry)}</td>"
                "</tr>"
            )
        selection_html = "".join(selection_parts)
    if not selection_html:
        selection_html = "<tr><td colspan=\"4\">-</td></tr>"

    status_history = row.get("Status_History") if isinstance(row.get("Status_History"), dict) else {}
    status_map = {}
    for status_row in status_history.get("rows", []):
        statuses = status_row.get("Statuses") or []
        if statuses:
            status_map[text(status_row.get("Ticker")).upper()] = text(statuses[-1])

    page_by_ticker = {item["ticker"].upper(): item for item in asset_pages}
    all_assets = []
    for ticker in tickers:
        key = ticker.upper()
        item = page_by_ticker.get(key)
        metadata = ticker_metadata.get(key, {})
        all_assets.append({
            "ticker": ticker,
            "name": selection_name_map.get(key) or metadata.get("Name") or ticker,
            "status": status_map.get(key, "-"),
            "sector": selection_sector_map.get(key) or metadata.get("Sector") or "-",
            "industry": selection_industry_map.get(key) or metadata.get("Industry") or "-",
            "page": item["page"] if item else "",
            "image": item["image"] if item else "",
            "has_chart": bool(item),
        })
    if not all_assets:
        all_assets = [
            {
                "ticker": item["ticker"],
                "name": selection_name_map.get(item["ticker"].upper(), item["ticker"]),
                "status": status_map.get(item["ticker"].upper(), "-"),
                "sector": selection_sector_map.get(item["ticker"].upper(), "-"),
                "industry": selection_industry_map.get(item["ticker"].upper(), "-"),
                "page": item["page"],
                "image": item["image"],
                "has_chart": True,
            }
            for item in asset_pages
        ]
    all_assets.sort(key=lambda item: text(item.get("ticker")).upper())

    def linked_ticker_html(ticker):
        ticker_text = html_text(ticker)
        item = page_by_ticker.get(text(ticker).upper())
        if item and item.get("page"):
            return f"<a class=\"ticker-link\" href=\"{html.escape(item['page'])}\">{ticker_text}</a>"
        return ticker_text

    def status_class(status):
        value = text(status).lower()
        if "selected" in value:
            return "status-selected"
        if "watchlist" in value:
            return "status-watchlist"
        if "rejected" in value:
            return "status-rejected"
        return "status-neutral"

    if isinstance(selection, str):
        selection_rows = [line for line in re.split(r"<br\s*/?>|\n", selection) if line.strip()]
        linked_rows = []
        for item in selection_rows:
            ticker_part, sep, name_part = item.partition(" - ")
            ticker_key = text(ticker_part).upper()
            metadata = ticker_metadata.get(ticker_key, {})
            linked_rows.append(
                "<tr>"
                f"<td>{linked_ticker_html(ticker_part)}</td>"
                f"<td>{html_text(name_part if sep else metadata.get('Name') or '')}</td>"
                f"<td>{html_text(metadata.get('Sector') or '-')}</td>"
                f"<td>{html_text(metadata.get('Industry') or '-')}</td>"
                "</tr>"
            )
        selection_html = "".join(linked_rows)
    else:
        linked_rows = []
        for item in selection:
            ticker_key = text(item.get("Ticker")).upper()
            linked_rows.append(
                "<tr>"
                f"<td>{linked_ticker_html(item.get('Ticker'))}</td>"
                f"<td>{html_text(selection_name_map.get(ticker_key) or item.get('Name'))}</td>"
                f"<td>{html_text(selection_sector_map.get(ticker_key) or item.get('Sector'))}</td>"
                f"<td>{html_text(selection_industry_map.get(ticker_key) or item.get('Industry'))}</td>"
                "</tr>"
            )
        selection_html = "".join(linked_rows)
    if not selection_html:
        selection_html = "<tr><td colspan=\"4\">-</td></tr>"

    build_css(out_dir)

    updated = report_date_label()
    hedge_ticker = html_text(row.get("Benchmark Hedge Ticker"))
    hedge_short = pct(row.get("Benchmark Hedge Short"))
    hedge_score = num(row.get("Hedge Portfolio Score"))
    metric_summary_html = (
        "<table class=\"metric-mini-table\">"
        "<thead><tr><th></th><th>Long</th><th>L+H</th><th>B</th></tr></thead>"
        "<tbody>"
        f"<tr><td>CAGR</td><td>{pct(row.get('Strategy CAGR'))}</td><td>{pct(row.get('Hedged CAGR'))}</td><td>{pct(row.get('Bench Cagr'))}</td></tr>"
        f"<tr><td>MaxDD</td><td>{pct(row.get('Strategy MaxDD'))}</td><td>{pct(row.get('Hedged MaxDD'))}</td><td>{pct(row.get('Bench_MaxDD'))}</td></tr>"
        f"<tr><td>Sharpe</td><td>{num(row.get('Strategy Sharpe Ratio'))}</td><td>{num(row.get('Hedged Sharpe Ratio'))}</td><td>{num(row.get('Bench Sharpe'))}</td></tr>"
        f"<tr><td>IR</td><td>{num(row.get('Information Ratio'))}</td><td>{num(row.get('Hedged Information Ratio'))}</td><td>-</td></tr>"
        "</tbody></table>"
    )
    selection_summary_items = re.findall(r"<td>(.*?)</td><td>(.*?)</td><td>", selection_html)
    if selection_summary_items:
        selection_summary_html = "".join(
            f"<li>{html_text(ticker)} - {html_text(name)}</li>"
            for ticker, name in selection_summary_items
        )
    else:
        selection_summary_html = "<li>-</li>"
    processing_objective = (
        "TradingAlgo Mosaic automatically selects and monitors a weekly portfolio of five stocks from any analyzed market. "
        "The framework uses systematic trend, stability, and portfolio-contribution analysis to identify opportunities, "
        "track portfolio positions, and evaluate performance relative to the benchmark. Market currently monitored: "
        "US100, Europe50, Italy30"
    )
    bio_text = (
        "Domenico D'Errico, after holding various managerial roles within multinational companies, has been working as a quant developer "
        "for algorithmic hedge funds for the past 15 years. He is a CSTA (Certified SIAT Technical Analyst), an EasyLanguage specialist, "
        "a two-time winner of the 2011 TradeStation Developers Contest, author of *TradeStation EasyLanguage for Algorithmic Trading*, "
        "and contributor to *Technical Analysis of Stocks & Commodities*. He is also a member of research initiatives focused on the "
        "application of artificial intelligence to financial markets."
    )
    disclaimer_text = (
        "This report is provided for research and educational purposes only and does not constitute investment advice, portfolio management, "
        "solicitation, or an offer to buy or sell any financial instrument. TradingAlgo Mosaic is a quantitative research framework designed "
        "to support investment analysis and decision-making. All information, rankings, simulations, and backtests are provided for informational "
        "purposes only. Past performance is not indicative of future results. Investing in financial markets involves risk, including the possible "
        "loss of capital. Investors are solely responsible for their investment decisions and should independently assess the suitability of any "
        "investment strategy."
    )
    exposure_chart_html = ""

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
      <a href="../../reserved-area.html">Back to Reserved Area</a>
      <a href="all-assets.html">View All Benchmark Assets</a>
      <a class="secondary" href="mailto:domderrico@gmail.com?subject=TradingAlgo%20Mosaic%20PDF%20Access%20Request">Request PDF Extra</a>
    </nav>

    <section class="report-dashboard">
      <header class="dashboard-header">
        <div>
          <div class="brand">TradingAlgo Mosaic</div>
          <h1>{html_text(market)} Weekly Report</h1>
          <p class="eyebrow">Benchmark: {html_text(row.get("Benchmark"))}</p>
        </div>
        <div class="dashboard-meta">
          Week ending: {html_text(updated)}<br />
          Universe: {html_text(row.get("Number of Tickers"))} assets<br />
          Status: {html_text(row.get("Status"))}
        </div>
      </header>

      <div class="dashboard-grid">
        <section class="dashboard-card">
          <h2>Current Selection</h2>
          <table class="mini-table">
            <thead><tr><th>Ticker</th><th>Name</th><th>Sector</th><th>Industry</th></tr></thead>
            <tbody>{selection_html}</tbody>
          </table>
        </section>
        <section class="dashboard-card">
          <h2>Weekly Changes</h2>
          <table class="mini-table changes-table">
            <tbody>
              <tr><th>Capital Invested</th><td>{pct(row.get("Capital Invested"))}</td></tr>
              <tr><th><span class="in-label">IN</span></th><td>{html_text(row.get("Added Tickers"))}</td></tr>
              <tr><th><span class="out-label">OUT</span></th><td>{html_text(row.get("Removed Tickers"))}</td></tr>
              <tr><th>Current Hedge Short ETF</th><td>{hedge_ticker}: {hedge_short}</td></tr>
              <tr><th>Hedge Score</th><td>{hedge_score}</td></tr>
            </tbody>
          </table>
        </section>
      </div>

      <section class="chart-section">
        <h2>Equity, Drawdown &amp; Exposure</h2>
        <div class="chart-stack">
          <div class="chart-frame">
            <h3>Equity / Drawdown</h3>
            <img class="dashboard-chart" src="assets/summary_{safe_market}.png" alt="{html_text(market)} equity and drawdown" />
          </div>{exposure_chart_html}
        </div>
      </section>

      <section class="performance-section">
        <h2>Performance Table</h2>
        <table class="asset-table performance-table">
          <thead><tr><th>Metric</th><th>Long</th><th>Long + Hedge</th><th>Benchmark</th></tr></thead>
          <tbody>
            <tr><td>CAGR</td><td>{pct(row.get("Strategy CAGR"))}</td><td>{pct(row.get("Hedged CAGR"))}</td><td>{pct(row.get("Bench Cagr"))}</td></tr>
            <tr><td>MaxDD</td><td>{pct(row.get("Strategy MaxDD"))}</td><td>{pct(row.get("Hedged MaxDD"))}</td><td>{pct(row.get("Bench_MaxDD"))}</td></tr>
            <tr><td>Sharpe</td><td>{num(row.get("Strategy Sharpe Ratio"))}</td><td>{num(row.get("Hedged Sharpe Ratio"))}</td><td>{num(row.get("Bench Sharpe"))}</td></tr>
            <tr><td>Information Ratio</td><td>{num(row.get("Information Ratio"))}</td><td>{num(row.get("Hedged Information Ratio"))}</td><td>-</td></tr>
          </tbody>
        </table>
      </section>
    </section>
  </main>
</body>
</html>
"""
    (out_dir / f"Report_{safe_market}.html").write_text(report_html, encoding="utf-8")

    gallery_rows = []
    for item in all_assets:
        status = html_text(item.get("status") or "-")
        status_css = status_class(item.get("status"))
        thumb = (
            f'<button class="thumb-button" type="button" data-full="assets/{html.escape(item["image"])}" aria-label="Open {html_text(item["ticker"])} chart">'
            f'<img src="assets/{html.escape(item["image"])}" alt="{html_text(item["ticker"])} asset chart" />'
            '</button>'
            if item.get("image") else "-"
        )
        gallery_rows.append(
            "<tr>"
            f"<td>{linked_ticker_html(item['ticker'])}</td>"
            f"<td>{html_text(item.get('name'))}</td>"
            f"<td>{html_text(item.get('sector'))}</td>"
            f"<td>{html_text(item.get('industry'))}</td>"
            f"<td><span class=\"status-badge {status_css}\">{status}</span></td>"
            f"<td>{thumb}</td>"
            "</tr>"
        )
    gallery_body = "".join(gallery_rows)

    all_assets_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html_text(market)} Chart Gallery | TradingAlgo Mosaic</title>
  <link rel="stylesheet" href="report.css" />
</head>
<body>
  <main class="report-shell">
    <nav class="top-actions">
      <a href="Report_{safe_market}.html">Back to Report</a>
    </nav>
    <section class="report-page gallery-page">
      <p class="eyebrow">View All Benchmark Assets</p>
      <h1>{html_text(market)} Chart Gallery</h1>
      <p>{len(all_assets)} plotted asset dashboards from the benchmark universe. Click any thumbnail to enlarge it.</p>
      <table class="asset-table gallery-table">
        <thead><tr><th>Ticker</th><th>Name</th><th>Sector</th><th>Industry</th><th>Status</th><th>Chart</th></tr></thead>
        <tbody>{gallery_body}</tbody>
      </table>
    </section>
  </main>

  <div class="chart-modal" id="chart-modal" aria-hidden="true">
    <button class="chart-modal-close" type="button" aria-label="Close chart">Close</button>
    <img src="" alt="Expanded asset chart" />
  </div>

  <script>
    var modal = document.getElementById("chart-modal");
    var modalImage = modal ? modal.querySelector("img") : null;
    var closeButton = modal ? modal.querySelector("button") : null;

    document.querySelectorAll(".thumb-button").forEach(function (button) {{
      button.addEventListener("click", function () {{
        if (!modal || !modalImage) return;
        modalImage.src = button.getAttribute("data-full");
        modal.classList.add("is-open");
        modal.setAttribute("aria-hidden", "false");
      }});
    }});

    function closeModal() {{
      if (!modal || !modalImage) return;
      modal.classList.remove("is-open");
      modal.setAttribute("aria-hidden", "true");
      modalImage.src = "";
    }}

    if (closeButton) closeButton.addEventListener("click", closeModal);
    if (modal) modal.addEventListener("click", function (event) {{ if (event.target === modal) closeModal(); }});
    document.addEventListener("keydown", function (event) {{ if (event.key === "Escape") closeModal(); }});
  </script>
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
