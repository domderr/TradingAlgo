import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_DATA = ROOT / "mosaic_dev" / "output" / "all_market_reports_data_from_csv.json"
MARKET_DATA_DIR = ROOT / "mosaic_dev" / "market_data"
MARKET_MANIFEST = MARKET_DATA_DIR / "manifest.json"
REPORTS_DIR = ROOT / "reports"


def safe_market_name(value):
    return str(value).replace(" ", "_").replace("/", "_")


def positions_key(market):
    return str(market).replace("South Korea30", "SouthKorea30").replace("South Africa30", "SouthAfrica30")


def display_week(end_date_exclusive):
    end_date = datetime.strptime(end_date_exclusive, "%Y-%m-%d").date()
    week_date = end_date - timedelta(days=1)
    return week_date.strftime("%-d %b %Y") if hasattr(week_date, "strftime") else str(week_date)


def portable_display_week(end_date_exclusive):
    end_date = datetime.strptime(end_date_exclusive, "%Y-%m-%d").date()
    week_date = end_date - timedelta(days=1)
    return f"{week_date.day} {week_date.strftime('%b %Y')}"


def split_change_items(value):
    text = "" if value is None else str(value).strip()
    if not text or text == "-":
        return []
    parts = re.split(r"<br\s*/?>|\n", text)
    items = []
    for part in parts:
        part = re.sub(r"\s+", " ", part).strip()
        if not part or part == "-":
            continue
        if " - " in part:
            ticker, name = part.split(" - ", 1)
        else:
            ticker, name = part, ""
        ticker = ticker.strip(" -")
        name = name.strip(" -")
        if ticker:
            items.append({"ticker": ticker, "name": name})
    return items


def build_positions(rows, week):
    payload = {}
    for row in rows:
        market = row.get("Market")
        selection = row.get("Last Weekly Selection") or []
        positions = []
        if isinstance(selection, list):
            for item in selection:
                if not isinstance(item, dict):
                    continue
                ticker = item.get("Ticker")
                if not ticker:
                    continue
                positions.append(
                    {
                        "ticker": ticker,
                        "name": item.get("Name") or "",
                        "sector": item.get("Sector") or "",
                        "industry": item.get("Industry") or "",
                    }
                )
        payload[positions_key(market)] = {
            "week": week,
            "positions": positions,
            "changes": {
                "in": split_change_items(row.get("Added Tickers")),
                "out": split_change_items(row.get("Removed Tickers")),
            },
        }
    return payload


def build_latest_prices(markets):
    latest = {}
    for market in markets:
        market_dir = MARKET_DATA_DIR / safe_market_name(market)
        prices_path = market_dir / "prices_daily.csv"
        if not prices_path.exists():
            continue
        prices = pd.read_csv(prices_path, parse_dates=["Date"]).set_index("Date").sort_index()
        if prices.empty:
            continue
        last_by_ticker = {}
        last_dates = []
        for ticker in prices.columns:
            series = prices[ticker].dropna()
            if series.empty:
                continue
            last_dates.append(series.index[-1])
            last_by_ticker[ticker] = round(float(series.iloc[-1]), 6)
        if not last_by_ticker:
            continue
        as_of = max(last_dates).date().isoformat()
        latest[market_dir.name] = {"as_of": as_of, "prices": last_by_ticker}
    return latest


def main():
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    rows = json.loads(PIPELINE_DATA.read_text(encoding="utf-8"))
    manifest = json.loads(MARKET_MANIFEST.read_text(encoding="utf-8"))
    week = portable_display_week(manifest["end_date_exclusive"])

    positions = build_positions(rows, week)
    markets = [row.get("Market") for row in rows if row.get("Market")]
    latest_prices = build_latest_prices(markets)

    (REPORTS_DIR / "positions.json").write_text(json.dumps(positions, ensure_ascii=False, indent=2), encoding="utf-8")
    (REPORTS_DIR / "latest_prices.json").write_text(
        json.dumps(latest_prices, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote positions.json for {len(positions)} markets | week={week}")
    print(f"wrote latest_prices.json for {len(latest_prices)} markets")


if __name__ == "__main__":
    main()
