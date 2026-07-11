import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML_DIR = ROOT / "reports_html"
REPORTS_INDEX = ROOT / "reports" / "reports_index.json"

DEFAULT_MARKETS = ["USA100", "NASDAQ100", "Europe50", "Italy40", "UK100", "Germany40", "Australia50"]

REQUIRED_MARKERS = [
    "Performance Table",
    "Month / Year Performance",
    "Top / Bottom Profit Contributors",
]


def safe_market_name(value):
    return str(value).replace(" ", "_").replace("/", "_")


def active_markets():
    if not REPORTS_INDEX.exists():
        return DEFAULT_MARKETS

    rows = json.loads(REPORTS_INDEX.read_text(encoding="utf-8"))
    markets = []
    seen = set()
    for row in rows if isinstance(rows, list) else []:
        market = str(row.get("Market", "")).strip()
        if not market or market in seen:
            continue
        seen.add(market)
        markets.append(market)
    return markets or DEFAULT_MARKETS


def main():
    failures = []
    markets = active_markets()
    for market in markets:
        safe_market = safe_market_name(market)
        report_path = HTML_DIR / safe_market / f"Report_{safe_market}.html"
        if not report_path.exists():
            failures.append(f"{market}: missing {report_path}")
            continue

        text = report_path.read_text(encoding="utf-8")
        missing = [marker for marker in REQUIRED_MARKERS if marker not in text]
        if missing:
            failures.append(f"{market}: missing {', '.join(missing)}")

    if failures:
        print("Weekly report validation failed:")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)

    print(f"Weekly report validation OK: {len(markets)} full reports")


if __name__ == "__main__":
    main()
