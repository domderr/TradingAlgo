import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"
HTML_DIR = ROOT / "reports_html"

MARKETS = [
    ("DJ30", "DJ30"),
    ("USA100", "USA100"),
    ("NASDAQ100", "Nasdaq100"),
    ("Canada50", "Canada50"),
    ("Mexico30", "Mexico30"),
    ("Europe50", "Europe50"),
    ("UK30", "UK30"),
    ("France40", "France40"),
    ("Spain40", "Spain40"),
    ("Germany30", "Germany30"),
    ("Japan50", "Japan50"),
    ("South Korea30", "S.Korea30"),
    ("Australia50", "Australia50"),
    ("South Africa30", "S.Africa30"),
]


def pdf_name(market):
    return f"Report_{market.replace(' ', '_')}.pdf"


def fmt_pct(value):
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "-"


def read_json(path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def position_rows(positions):
    if not positions:
        return '<tr><td colspan="2">-</td></tr>'
    return "\n".join(
        f"<tr><td>{html.escape(item.get('ticker', ''))}</td><td>{html.escape(item.get('name', ''))}</td></tr>"
        for item in positions
    )


def change_text(items):
    if not items:
        return "-"
    return ", ".join(html.escape(item.get("ticker", "")) for item in items)


def render_page(market, display_name, index_row, pos_row):
    pdf = pdf_name(market)
    benchmark = html.escape(index_row.get("Benchmark") or "-")
    status = html.escape(index_row.get("Status") or "-")
    updated = html.escape(index_row.get("Updated_At") or "-")
    hedge_ticker = html.escape(index_row.get("Benchmark_Hedge_Ticker") or index_row.get("Benchmark") or "-")
    hedge = fmt_pct(index_row.get("Last_Hedge_Short"))
    week = html.escape(pos_row.get("week") or "-")
    positions = position_rows(pos_row.get("positions") or [])
    changes = pos_row.get("changes") or {}
    added = change_text(changes.get("in") or [])
    removed = change_text(changes.get("out") or [])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(display_name)} Weekly Report | TradingAlgo Mosaic</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #071014;
      --panel: #101a20;
      --panel-2: #152229;
      --line: rgba(255,255,255,.12);
      --text: #eaf2f6;
      --muted: #8fa0aa;
      --accent: #68d391;
      --red: #ff6b6b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, Segoe UI, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    a {{ color: inherit; }}
    .shell {{ width: min(1440px, calc(100% - 40px)); margin: 0 auto; padding: 22px 0 34px; }}
    .top-actions {{ display: flex; justify-content: space-between; gap: 14px; align-items: center; margin-bottom: 18px; }}
    .back-link {{
      display: inline-flex;
      align-items: center;
      min-height: 38px;
      padding: 0 14px;
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 6px;
      text-decoration: none;
      font-size: 14px;
      color: var(--muted);
    }}
    .hero {{
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 16px;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 18px;
    }}
    .brand {{ color: var(--muted); font-size: 13px; text-transform: uppercase; letter-spacing: .08em; }}
    h1 {{ margin: 6px 0 8px; font-size: clamp(28px, 4vw, 46px); letter-spacing: 0; }}
    .subtitle {{ margin: 0; color: var(--muted); font-size: 15px; }}
    .meta {{ text-align: right; color: var(--muted); line-height: 1.7; font-size: 14px; }}
    .meta strong {{ color: var(--text); }}
    .grid {{
      display: grid;
      grid-template-columns: minmax(280px, 380px) 1fr;
      gap: 16px;
      align-items: start;
    }}
    .panel {{
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      overflow: hidden;
    }}
    .panel h2 {{
      margin: 0;
      padding: 15px 16px;
      font-size: 18px;
      border-bottom: 1px solid var(--line);
      background: var(--panel-2);
    }}
    .summary {{ padding: 16px; display: grid; gap: 14px; }}
    .stat {{ display: grid; gap: 3px; }}
    .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }}
    .value {{ font-size: 18px; }}
    .value.hedge {{ color: var(--red); font-weight: 700; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid rgba(255,255,255,.08); text-align: left; vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 600; }}
    .changes {{ color: var(--muted); line-height: 1.5; }}
    .pdf-frame {{
      height: calc(100vh - 255px);
      min-height: 620px;
      background: #0b1115;
    }}
    .pdf-frame object {{ display: block; width: 100%; height: 100%; border: 0; }}
    @media (max-width: 900px) {{
      .shell {{ width: min(100% - 24px, 1440px); }}
      .hero, .grid {{ grid-template-columns: 1fr; }}
      .meta {{ text-align: left; }}
      .pdf-frame {{ height: 74vh; min-height: 520px; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <nav class="top-actions">
      <a class="back-link" href="../../reserved-area.html">Back to Reserved Area</a>
    </nav>

    <section class="hero">
      <div>
        <div class="brand">TradingAlgo Mosaic</div>
        <h1>{html.escape(display_name)} Weekly Report</h1>
        <p class="subtitle">Benchmark: {benchmark}</p>
      </div>
      <div class="meta">
        Week ending: <strong>{week}</strong><br />
        Status: <strong>{status}</strong><br />
        Updated: <strong>{updated}</strong>
      </div>
    </section>

    <section class="grid">
      <div class="panel">
        <h2>Current Selection</h2>
        <table>
          <thead><tr><th>Ticker</th><th>Name</th></tr></thead>
          <tbody>{positions}</tbody>
        </table>
        <div class="summary">
          <div class="stat">
            <div class="label">Hedge</div>
            <div class="value hedge">Short {hedge_ticker}: {hedge}</div>
          </div>
          <div class="stat">
            <div class="label">Weekly Changes</div>
            <div class="changes">IN: {added}<br />OUT: {removed}</div>
          </div>
        </div>
      </div>

      <div class="panel">
        <h2>Report</h2>
        <div class="pdf-frame">
          <object data="../../reports/{html.escape(pdf)}#toolbar=1&navpanes=0" type="application/pdf">
            <iframe src="../../reports/{html.escape(pdf)}#toolbar=1&navpanes=0" title="{html.escape(display_name)} PDF report"></iframe>
          </object>
        </div>
      </div>
    </section>
  </main>
</body>
</html>
"""


def main():
    index = {row["Market"]: row for row in read_json(REPORTS_DIR / "reports_index.json", [])}
    positions = read_json(REPORTS_DIR / "positions.json", {})

    for market, display_name in MARKETS:
        market_dir = HTML_DIR / market.replace(" ", "_")
        market_dir.mkdir(parents=True, exist_ok=True)
        pos_key = market.replace("South Korea30", "SouthKorea30").replace("South Africa30", "SouthAfrica30")
        page = render_page(market, display_name, index.get(market, {}), positions.get(pos_key, {}))
        out = market_dir / f"Report_{market.replace(' ', '_')}.html"
        out.write_text(page, encoding="utf-8")
        print(out)


if __name__ == "__main__":
    main()
