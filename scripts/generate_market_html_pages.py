import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools" / "build_mosaic_html_report.py"
DEV_DIR = ROOT / "mosaic_dev"
HTML_DIR = ROOT / "reports_html"

MARKETS = [
    "USA100",
    "NASDAQ100",
    "Europe50",
    "Italy40",
    "Germany40",
    "UK30",
]

REQUIRED_REPORT_MARKERS = [
    "Performance Table",
    "Month / Year Performance",
    "Top / Bottom Profit Contributors",
]


def safe_market_name(value):
    return str(value).replace(" ", "_").replace("/", "_")


def build_market(market, choice):
    command = [
        sys.executable,
        str(BUILDER),
        "--dev-dir",
        str(DEV_DIR),
        "--site-dir",
        str(ROOT),
        "--market",
        market,
        "--market-choice",
        str(choice),
    ]
    print(" ".join(command), flush=True)
    subprocess.run(command, check=True)


def validate_market(market):
    safe_market = safe_market_name(market)
    report_path = HTML_DIR / safe_market / f"Report_{safe_market}.html"
    if not report_path.exists():
        raise FileNotFoundError(f"Missing generated report: {report_path}")

    text = report_path.read_text(encoding="utf-8")
    missing = [marker for marker in REQUIRED_REPORT_MARKERS if marker not in text]
    if missing:
        raise RuntimeError(
            f"Incomplete weekly report generated for {market}: missing {', '.join(missing)}"
        )
    print(f"validated full report: {report_path}", flush=True)


def main():
    for choice, market in enumerate(MARKETS, start=1):
        build_market(market, choice)
        validate_market(market)


if __name__ == "__main__":
    main()
