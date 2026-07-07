from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML_DIR = ROOT / "reports_html"

MARKETS = [
    "USA100",
    "NASDAQ100",
    "Europe50",
    "Italy40",
    "Germany40",
    "UK30",
    "Australia50",
]

REQUIRED_MARKERS = [
    "Performance Table",
    "Month / Year Performance",
    "Top / Bottom Profit Contributors",
]


def safe_market_name(value):
    return str(value).replace(" ", "_").replace("/", "_")


def main():
    failures = []
    for market in MARKETS:
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

    print(f"Weekly report validation OK: {len(MARKETS)} full reports")


if __name__ == "__main__":
    main()
