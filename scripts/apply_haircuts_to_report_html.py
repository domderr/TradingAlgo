import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS_HTML = ROOT / "reports_html"
HAIRCUTS_CSV = ROOT / "haircuts.csv"


def normalize_market_name(value):
    aliases = {
        "South_Africa30": "South Africa30",
        "South_Korea30": "South Korea30",
        "Nasdaq100": "NASDAQ100",
    }
    key = str(value or "").strip()
    return aliases.get(key, key)


def load_haircuts():
    haircuts = {}
    if not HAIRCUTS_CSV.exists():
        return haircuts
    for line in HAIRCUTS_CSV.read_text(encoding="utf-8").splitlines()[1:]:
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            haircuts[normalize_market_name(parts[0])] = float(parts[1])
        except ValueError:
            continue
    return haircuts


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pct(value):
    value = number(value)
    return "-" if value is None else f"{value * 100:.2f}%"


def num(value):
    value = number(value)
    return "-" if value is None else f"{value:.2f}"


def apply_metric_haircut(mosaic, benchmark, haircut):
    mosaic = number(mosaic)
    benchmark = number(benchmark)
    haircut = number(haircut)
    if mosaic is None or benchmark is None:
        return mosaic
    if haircut is None:
        haircut = 1.0
    return benchmark + haircut * (mosaic - benchmark)


def performance_section(row, haircut):
    strategy_cagr = apply_metric_haircut(row.get("Strategy CAGR"), row.get("Bench Cagr"), haircut)
    hedged_cagr = apply_metric_haircut(row.get("Hedged CAGR"), row.get("Bench Cagr"), haircut)
    strategy_sharpe = apply_metric_haircut(row.get("Strategy Sharpe Ratio"), row.get("Bench Sharpe"), haircut)
    hedged_sharpe = apply_metric_haircut(row.get("Hedged Sharpe Ratio"), row.get("Bench Sharpe"), haircut)
    return f"""<section class="performance-section">
        <h2>Performance Table</h2>
        <table class="asset-table performance-table">
          <thead><tr><th>Metric</th><th>Long</th><th>Long + Hedge</th><th>Benchmark</th></tr></thead>
          <tbody>
            <tr><td>CAGR</td><td>{pct(strategy_cagr)}</td><td>{pct(hedged_cagr)}</td><td>{pct(row.get("Bench Cagr"))}</td></tr>
            <tr><td>MaxDD</td><td>{pct(row.get("Strategy MaxDD"))}</td><td>{pct(row.get("Hedged MaxDD"))}</td><td>{pct(row.get("Bench_MaxDD"))}</td></tr>
            <tr><td>Sharpe</td><td>{num(strategy_sharpe)}</td><td>{num(hedged_sharpe)}</td><td>{num(row.get("Bench Sharpe"))}</td></tr>
            <tr><td>Information Ratio</td><td>{num(row.get("Information Ratio"))}</td><td>{num(row.get("Hedged Information Ratio"))}</td><td>-</td></tr>
          </tbody>
        </table>
      </section>"""


def main():
    haircuts = load_haircuts()
    pattern = re.compile(
        r'<section class="performance-section">\s*<h2>Performance Table</h2>.*?</section>',
        re.DOTALL,
    )
    updated = 0
    for data_path in sorted(REPORTS_HTML.glob("*/report_data.json")):
        rows = json.loads(data_path.read_text(encoding="utf-8"))
        row = rows[0] if isinstance(rows, list) and rows else rows
        market = normalize_market_name(data_path.parent.name)
        haircut = haircuts.get(market, 1.0)
        report_path = data_path.parent / f"Report_{data_path.parent.name}.html"
        if not report_path.exists():
            continue
        html = report_path.read_text(encoding="utf-8")
        replacement = performance_section(row, haircut)
        new_html, count = pattern.subn(replacement, html, count=1)
        if count != 1:
            raise RuntimeError(f"Performance section not found in {report_path}")
        if new_html != html:
            report_path.write_text(new_html, encoding="utf-8")
            updated += 1
            print(f"updated {report_path.relative_to(ROOT)}")
    print(f"updated_reports={updated}")


if __name__ == "__main__":
    main()
