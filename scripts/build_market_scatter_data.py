import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# Disable SSL verification for curl_cffi (used by yfinance)
os.environ['CURL_CA_BUNDLE'] = ''
try:
    import curl_cffi.requests as _cffi
    _orig_init = _cffi.Session.__init__
    def _patched_init(self, *a, **kw):
        kw['verify'] = False
        _orig_init(self, *a, **kw)
    _cffi.Session.__init__ = _patched_init
except Exception:
    pass

import yfinance as yf


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "market_scatter_history.json"
LOOKBACK_WEEKS = 52
SNAPSHOT_COUNT = 52

MARKETS = [
    {"market": "USA100", "code": "US", "flag": "🇺🇸", "etf": "QQQ"},
    {"market": "Europe50", "code": "EU", "flag": "🇪🇺", "etf": "FEZ"},
    {"market": "Italy30", "code": "IT", "flag": "🇮🇹", "etf": "EWI"},
    {"market": "UK30", "code": "GB", "flag": "🇬🇧", "etf": "EWU"},
    {"market": "France40", "code": "FR", "flag": "🇫🇷", "etf": "EWQ"},
    {"market": "Germany30", "code": "DE", "flag": "🇩🇪", "etf": "EWG"},
    {"market": "Australia50", "code": "AU", "flag": "🇦🇺", "etf": "EWA"},
    {"market": "Japan50", "code": "JP", "flag": "🇯🇵", "etf": "EWJ"},
    {"market": "Canada50", "code": "CA", "flag": "🇨🇦", "etf": "EWC"},
    {"market": "Mexico30", "code": "MX", "flag": "🇲🇽", "etf": "EWW"},
    {"market": "South Korea30", "code": "KR", "flag": "🇰🇷", "etf": "EWY"},
    {"market": "South Africa30", "code": "ZA", "flag": "🇿🇦", "etf": "EZA"},
]


def regression_slope_r2(values):
    y = np.asarray(values, dtype=float)
    if len(y) < LOOKBACK_WEEKS or np.any(~np.isfinite(y)) or np.any(y <= 0):
        return np.nan, np.nan

    y = np.log(y)
    x = np.arange(len(y), dtype=float)
    x_mean = x.mean()
    y_mean = y.mean()
    denominator = np.sum((x - x_mean) ** 2)
    if denominator == 0:
        return np.nan, np.nan

    slope = np.sum((x - x_mean) * (y - y_mean)) / denominator
    intercept = y_mean - slope * x_mean
    fitted = intercept + slope * x
    residual = np.sum((y - fitted) ** 2)
    total = np.sum((y - y_mean) ** 2)
    r2 = 1.0 - residual / total if total > 0 else np.nan
    return slope, r2


def extract_close(downloaded):
    if downloaded.empty:
        return pd.DataFrame()
    if isinstance(downloaded.columns, pd.MultiIndex):
        for field in ("Adj Close", "Close"):
            if field in downloaded.columns.get_level_values(0):
                return downloaded[field].copy()
    for field in ("Adj Close", "Close"):
        if field in downloaded.columns:
            return downloaded[[field]]
    return pd.DataFrame()


def main():
    tickers = [item["etf"] for item in MARKETS]
    end = (datetime.now() + timedelta(days=1)).date().isoformat()
    start = (datetime.now() - timedelta(weeks=LOOKBACK_WEEKS + SNAPSHOT_COUNT + 12)).date().isoformat()
    downloaded = yf.download(
        tickers,
        start=start,
        end=end,
        auto_adjust=False,
        progress=False,
        group_by="column",
        threads=True,
    )
    closes = extract_close(downloaded)
    if closes.empty:
        raise RuntimeError("No price data downloaded from yfinance")

    weekly = closes.resample("W-FRI").last().ffill().dropna(how="all")
    snapshot_dates = weekly.index[-SNAPSHOT_COUNT:]
    snapshots = []

    for date in snapshot_dates:
        rows = []
        window_end = weekly.index.get_loc(date)
        for item in MARKETS:
            series = weekly[item["etf"]].iloc[: window_end + 1].dropna().tail(LOOKBACK_WEEKS)
            slope, r2 = regression_slope_r2(series)
            rows.append({**item, "slope": slope, "r2": r2, "last_price": float(series.iloc[-1])})

        slopes = pd.Series([row["slope"] for row in rows], dtype="float64")
        trend_scores = slopes.rank(pct=True).fillna(0) * 100

        points = []
        for index, row in enumerate(rows):
            stability = 0 if pd.isna(row["r2"]) else round(max(0, min(1, row["r2"])) * 100)
            trend = int(round(trend_scores.iloc[index]))
            points.append(
                {
                    "market": row["market"],
                    "code": row["code"],
                    "flag": row["flag"],
                    "etf": row["etf"],
                    "trend": trend,
                    "stability": int(stability),
                    "price": round(row["last_price"], 2),
                }
            )

        snapshots.append({"date": date.date().isoformat(), "points": points})

    OUT.write_text(
        json.dumps(
            {
                "source": "yfinance",
                "lookback_weeks": LOOKBACK_WEEKS,
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "snapshots": snapshots,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
