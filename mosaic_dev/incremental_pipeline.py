import json
from pathlib import Path

import pandas as pd


TIME_SERIES_FIELDS = (
    "Strategy_Returns",
    "Hedged_Strategy_Returns",
    "Benchmark_Returns",
)


def _market_key(row):
    return str(row.get("Market", "")).strip()


def _as_ordered_series(value):
    if isinstance(value, pd.Series):
        items = value.to_dict()
    elif isinstance(value, dict):
        items = value
    else:
        return {}

    normalized = {}
    for key, item in items.items():
        date_key = pd.to_datetime(key, errors="coerce")
        if pd.isna(date_key):
            continue
        normalized[date_key.strftime("%Y-%m-%d")] = item
    return dict(sorted(normalized.items()))


def _latest_date(series):
    dates = [pd.to_datetime(key, errors="coerce") for key in series.keys()]
    dates = [date for date in dates if not pd.isna(date)]
    return max(dates) if dates else None


def _merge_series(previous, current):
    previous_series = _as_ordered_series(previous)
    current_series = _as_ordered_series(current)
    previous_latest = _latest_date(previous_series)
    if previous_latest is None:
        return current_series, len(current_series)

    merged = dict(previous_series)
    appended = 0
    for key, value in current_series.items():
        date_key = pd.to_datetime(key, errors="coerce")
        if pd.isna(date_key) or date_key <= previous_latest:
            continue
        merged[key] = value
        appended += 1

    return dict(sorted(merged.items())), appended


def read_rows(path):
    path = Path(path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, list) else []


def latest_saved_dates_by_market(rows):
    latest_by_market = {}
    for row in rows:
        market = _market_key(row)
        if not market:
            continue
        latest_dates = []
        for field in TIME_SERIES_FIELDS:
            latest = _latest_date(_as_ordered_series(row.get(field)))
            if latest is not None:
                latest_dates.append(latest)
        if latest_dates:
            latest_by_market[market] = max(latest_dates)
    return latest_by_market


def latest_csv_date(market_data_dir, market):
    prices_path = Path(market_data_dir) / str(market).replace(" ", "_").replace("/", "_") / "prices_daily.csv"
    if not prices_path.exists():
        return None

    try:
        dates = pd.read_csv(prices_path, usecols=["Date"], parse_dates=["Date"])["Date"].dropna()
    except Exception:
        return None
    if dates.empty:
        return None
    return pd.Timestamp(dates.max()).normalize()


def markets_with_new_csv_data(markets, previous_json_path, market_data_dir):
    previous_rows = read_rows(previous_json_path)
    if not previous_rows:
        return [str(market).strip() for market in markets if str(market).strip()], {
            "mode": "full",
            "reason": "no_previous_output",
            "skipped": [],
            "pending": [str(market).strip() for market in markets if str(market).strip()],
        }

    saved_dates = latest_saved_dates_by_market(previous_rows)
    pending = []
    skipped = []
    for market in markets:
        market_name = str(market).strip()
        if not market_name:
            continue
        saved_date = saved_dates.get(market_name)
        available_date = latest_csv_date(market_data_dir, market_name)
        if saved_date is None or available_date is None or available_date > saved_date:
            pending.append(market_name)
        else:
            skipped.append(
                {
                    "market": market_name,
                    "saved_date": saved_date.strftime("%Y-%m-%d"),
                    "available_date": available_date.strftime("%Y-%m-%d"),
                }
            )

    return pending, {
        "mode": "incremental",
        "pending": pending,
        "skipped": skipped,
    }


def merge_with_existing_history(current_df, previous_json_path, active_markets=None):
    previous_rows = read_rows(previous_json_path)
    if not previous_rows:
        return current_df, {
            "previous_markets": 0,
            "current_markets": int(len(current_df)),
            "unchanged_markets": 0,
            "appended_points": 0,
        }

    active_market_set = None
    if active_markets is not None:
        active_market_set = {str(market).strip() for market in active_markets if str(market).strip()}

    previous_by_market = {
        _market_key(row): row
        for row in previous_rows
        if _market_key(row) and (active_market_set is None or _market_key(row) in active_market_set)
    }
    merged_rows = []
    appended_points = 0
    unchanged_markets = 0
    seen_markets = set()
    merged_markets = set()

    for current_row in current_df.to_dict(orient="records"):
        market = _market_key(current_row)
        if not market or market not in previous_by_market:
            merged_rows.append(current_row)
            continue

        seen_markets.add(market)
        previous_row = previous_by_market[market]
        merged_row = dict(current_row)
        row_appended = 0
        for field in TIME_SERIES_FIELDS:
            merged_series, appended = _merge_series(previous_row.get(field), current_row.get(field))
            merged_row[field] = merged_series
            row_appended += appended

        if row_appended == 0:
            merged_rows.append(previous_row)
            unchanged_markets += 1
        else:
            merged_rows.append(merged_row)
            appended_points += row_appended
        merged_markets.add(market)

    for market, previous_row in previous_by_market.items():
        if market not in seen_markets and market not in merged_markets:
            merged_rows.append(previous_row)

    summary = {
        "previous_markets": len(previous_by_market),
        "current_markets": int(len(current_df)),
        "unchanged_markets": unchanged_markets,
        "appended_points": appended_points,
    }
    return pd.DataFrame(merged_rows), summary
