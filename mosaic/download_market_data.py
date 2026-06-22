import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

os.environ.setdefault("CURL_CA_BUNDLE", "")

try:
    from curl_cffi import requests
except Exception:
    requests = None

import yfinance as yf


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_TICKERS_XLSX = BASE_DIR / "Tickers.xlsx"
DEFAULT_OUTPUT_DIR = BASE_DIR / "market_data"
DEFAULT_START_DATE = "2024-01-01"
PRICE_FIELD_PRIORITY = ["Adj Close", "Close"]


def last_available_friday(today=None):
    today = today or datetime.now(ZoneInfo("Europe/Rome")).date()
    days_since_friday = (today.weekday() - 4) % 7
    return today - timedelta(days=days_since_friday)


def default_end_date():
    return (last_available_friday() + timedelta(days=1)).isoformat()


def clean_cell(value):
    text = str(value).strip()
    return "" if not text or text.lower() == "nan" else text


def unique_preserve_order(values):
    seen = set()
    unique = []
    duplicates = []
    for value in values:
        key = value.upper()
        if key in seen:
            duplicates.append(value)
            continue
        seen.add(key)
        unique.append(value)
    return unique, duplicates


def read_markets(tickers_xlsx):
    raw = pd.read_excel(tickers_xlsx, header=None)
    if raw.shape[0] < 3:
        raise ValueError("Tickers.xlsx deve avere almeno 3 righe: Market, Benchmark, Tickers.")

    markets = []
    for col in raw.columns:
        market = clean_cell(raw.iloc[0, col])
        benchmark = clean_cell(raw.iloc[1, col])
        if not market:
            continue
        if not benchmark:
            raise ValueError(f"Benchmark mancante per mercato {market}.")

        tickers = [clean_cell(value) for value in raw.iloc[2:, col].tolist()]
        tickers = [ticker for ticker in tickers if ticker]
        unique_tickers, duplicate_tickers = unique_preserve_order(tickers)
        benchmark_in_universe = benchmark.upper() in {ticker.upper() for ticker in unique_tickers}

        download_tickers = [benchmark] + [ticker for ticker in unique_tickers if ticker.upper() != benchmark.upper()]
        markets.append(
            {
                "market": market,
                "benchmark": benchmark,
                "tickers": unique_tickers,
                "download_tickers": download_tickers,
                "duplicate_tickers": duplicate_tickers,
                "benchmark_in_universe": benchmark_in_universe,
                "raw_ticker_count": len(tickers),
                "unique_ticker_count": len(unique_tickers),
            }
        )
    if not markets:
        raise ValueError("Nessun mercato valido trovato in Tickers.xlsx.")
    return markets


def safe_market_name(value):
    return str(value).replace(" ", "_").replace("/", "_")


def extract_price_table(raw, tickers):
    if raw is None or raw.empty:
        raise ValueError("Download yfinance vuoto.")

    if isinstance(raw.columns, pd.MultiIndex):
        level0 = list(raw.columns.get_level_values(0))
        level1 = list(raw.columns.get_level_values(1))
        for field in PRICE_FIELD_PRIORITY:
            if field in level0:
                return raw[field].copy()
            if field in level1:
                return raw.xs(field, axis=1, level=1).copy()

    for field in PRICE_FIELD_PRIORITY:
        if field in raw.columns:
            if len(tickers) == 1:
                return pd.DataFrame({tickers[0]: raw[field]})
            return raw[[field]].copy()

    raise ValueError(f"Nessun campo prezzo trovato tra: {PRICE_FIELD_PRIORITY}")


def make_yf_session():
    if requests is None:
        return None
    return requests.Session(impersonate="chrome", verify=False)


def download_market(market_info, start_date, end_date):
    tickers = market_info["download_tickers"]
    session = make_yf_session()
    kwargs = {
        "tickers": tickers,
        "start": start_date,
        "end": end_date,
        "auto_adjust": False,
        "progress": False,
        "group_by": "column",
        "threads": True,
    }
    if session is not None:
        kwargs["session"] = session

    raw = yf.download(**kwargs)
    prices = extract_price_table(raw, tickers)
    prices = prices.sort_index()
    prices.index = pd.to_datetime(prices.index).tz_localize(None)

    available = [ticker for ticker in tickers if ticker in prices.columns]
    prices = prices[available].dropna(axis=1, how="all")
    missing = [ticker for ticker in tickers if ticker not in prices.columns]

    benchmark = market_info["benchmark"]
    if benchmark not in prices.columns:
        raise ValueError(f"Benchmark {benchmark} non presente nei dati scaricati.")

    return prices, missing


def write_market_data(output_dir, market_info, prices, missing, start_date, end_date):
    market_dir = output_dir / safe_market_name(market_info["market"])
    market_dir.mkdir(parents=True, exist_ok=True)

    prices_path = market_dir / "prices_daily.csv"
    metadata_path = market_dir / "metadata.json"
    tickers_path = market_dir / "tickers.json"

    prices.to_csv(prices_path, index_label="Date")

    tickers_payload = {
        "market": market_info["market"],
        "benchmark": market_info["benchmark"],
        "universe": market_info["tickers"],
        "download_tickers": market_info["download_tickers"],
        "available_columns": list(prices.columns),
        "missing_tickers": missing,
    }
    tickers_path.write_text(json.dumps(tickers_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    metadata = {
        "market": market_info["market"],
        "benchmark": market_info["benchmark"],
        "start_date": start_date,
        "end_date_exclusive": end_date,
        "downloaded_at": datetime.now(ZoneInfo("Europe/Rome")).isoformat(timespec="seconds"),
        "rows": int(len(prices)),
        "columns": int(len(prices.columns)),
        "first_date": prices.index.min().date().isoformat() if len(prices) else None,
        "last_date": prices.index.max().date().isoformat() if len(prices) else None,
        "raw_ticker_count": market_info["raw_ticker_count"],
        "unique_ticker_count": market_info["unique_ticker_count"],
        "duplicate_tickers": market_info["duplicate_tickers"],
        "benchmark_in_universe": market_info["benchmark_in_universe"],
        "missing_tickers": missing,
        "prices_file": str(prices_path),
        "tickers_file": str(tickers_path),
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def select_markets(markets, requested):
    if not requested or requested.lower() == "all":
        return markets
    wanted = {item.strip().lower() for item in requested.split(",") if item.strip()}
    selected = [market for market in markets if market["market"].lower() in wanted]
    missing = wanted - {market["market"].lower() for market in selected}
    if missing:
        raise ValueError(f"Mercati non trovati: {', '.join(sorted(missing))}")
    return selected


def main():
    parser = argparse.ArgumentParser(description="Download market prices from yfinance into market_data.")
    parser.add_argument("--tickers", default=str(DEFAULT_TICKERS_XLSX), help="Path to Tickers.xlsx.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output market_data directory.")
    parser.add_argument("--markets", default="all", help="Comma-separated markets or 'all'.")
    parser.add_argument("--start", default=DEFAULT_START_DATE, help="Start date, YYYY-MM-DD.")
    parser.add_argument("--end", default=default_end_date(), help="Exclusive end date, YYYY-MM-DD.")
    parser.add_argument("--validate-only", action="store_true", help="Validate Tickers.xlsx without downloading.")
    args = parser.parse_args()

    tickers_xlsx = Path(args.tickers).resolve()
    output_dir = Path(args.output_dir).resolve()
    markets = read_markets(tickers_xlsx)
    selected = select_markets(markets, args.markets)

    print(f"Tickers file: {tickers_xlsx}")
    print(f"Output dir: {output_dir}")
    print(f"Date range: {args.start} -> {args.end} (exclusive)")
    print(f"Markets selected: {len(selected)}")
    for market in selected:
        warnings = []
        if market["duplicate_tickers"]:
            warnings.append("duplicates=" + ",".join(market["duplicate_tickers"]))
        if market["benchmark_in_universe"]:
            warnings.append("benchmark repeated in universe")
        suffix = " | " + " | ".join(warnings) if warnings else ""
        print(
            f"- {market['market']} | benchmark={market['benchmark']} | "
            f"tickers={market['unique_ticker_count']}/{market['raw_ticker_count']}{suffix}"
        )

    if args.validate_only:
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "tickers_file": str(tickers_xlsx),
        "output_dir": str(output_dir),
        "start_date": args.start,
        "end_date_exclusive": args.end,
        "generated_at": datetime.now(ZoneInfo("Europe/Rome")).isoformat(timespec="seconds"),
        "markets": [],
    }

    for market in selected:
        print(f"\nDownloading {market['market']}...")
        try:
            prices, missing = download_market(market, args.start, args.end)
            metadata = write_market_data(output_dir, market, prices, missing, args.start, args.end)
            metadata["status"] = "OK"
            print(
                f"OK {market['market']}: rows={metadata['rows']} cols={metadata['columns']} "
                f"missing={len(missing)}"
            )
        except Exception as exc:
            metadata = {
                "market": market["market"],
                "benchmark": market["benchmark"],
                "status": "ERROR",
                "error": str(exc),
                "duplicate_tickers": market["duplicate_tickers"],
                "benchmark_in_universe": market["benchmark_in_universe"],
            }
            print(f"ERROR {market['market']}: {exc}")
        manifest["markets"].append(metadata)

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    ok_count = sum(1 for item in manifest["markets"] if item.get("status") == "OK")
    print(f"\nDone: {ok_count}/{len(selected)} markets OK")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
