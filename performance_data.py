"""Build active ETF performance JSON files."""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from http_client import HttpClientError
from scrapers.finmind import fetch_etf_dividend_results, fetch_etf_price_history


BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
PERFORMANCE_DIR = DATA_DIR / "performance"
PERFORMANCE_OUTPUT = PERFORMANCE_DIR / "active_etf_performance.json"


def rebuild_active_etf_performance(
    etf_config: dict[str, dict[str, Any]],
    token: str = "",
    start_date: str = "2025-01-01",
    delay_sec: float = 0.25,
) -> Path:
    """Fetch history and write active ETF performance data for the frontend."""

    active_items = [
        (ticker, config)
        for ticker, config in etf_config.items()
        if config.get("type") == "active"
    ]
    end_date = date.today().isoformat()
    etfs = []
    history_by_ticker = {}
    dividends_by_ticker = {}

    for index, (ticker, config) in enumerate(active_items):
        try:
            prices = fetch_etf_price_history(
                ticker,
                token=token,
                start_date=start_date,
                end_date=end_date,
            )
            dividends = fetch_etf_dividend_results(
                ticker,
                token=token,
                start_date=start_date,
                end_date=end_date,
            )
        except (HttpClientError, ValueError) as exc:
            print(f"  [--] {ticker}: performance update failed: {exc}")
            prices = []
            dividends = []

        series = _build_total_return_series(prices, dividends)
        metrics = _build_metrics(ticker, config, series, dividends)
        if metrics:
            etfs.append(metrics)
            history_by_ticker[ticker] = series
            dividends_by_ticker[ticker] = dividends
            print(f"  [OK] {ticker}: performance {metrics['latest_date']} close={metrics['latest_close']}")
        else:
            print(f"  [--] {ticker}: no performance rows")

        if index < len(active_items) - 1 and delay_sec > 0:
            time.sleep(delay_sec)

    etfs.sort(key=lambda item: item["ticker"])
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "data_date": max((item["latest_date"] for item in etfs), default=""),
        "start_date": start_date,
        "return_modes": [
            {
                "id": "price",
                "label": "價格報酬",
                "note": "以收盤價計算，未含配息。",
            },
            {
                "id": "total",
                "label": "含息總報酬",
                "note": "以除息結果現金股利於除息日收盤價再投入估算。",
            },
        ],
        "summary": _build_summary(etfs),
        "etfs": etfs,
        "history": history_by_ticker,
        "dividends": dividends_by_ticker,
    }

    PERFORMANCE_DIR.mkdir(parents=True, exist_ok=True)
    with open(PERFORMANCE_OUTPUT, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    return PERFORMANCE_OUTPUT


def _build_total_return_series(prices: list[dict], dividends: list[dict]) -> list[dict]:
    if not prices:
        return []

    dividend_by_date: dict[str, float] = {}
    for dividend in dividends:
        dividend_by_date[dividend["date"]] = dividend_by_date.get(dividend["date"], 0.0) + float(dividend["cash_dividend"])

    first_close = float(prices[0]["close"])
    shares = 1.0
    series = []
    for row in prices:
        close = float(row["close"])
        cash_dividend = dividend_by_date.get(row["date"], 0.0)
        if cash_dividend and close > 0:
            shares += shares * cash_dividend / close
        total_value = shares * close
        series.append({
            "date": row["date"],
            "close": round(close, 4),
            "price_index": round(close / first_close * 100, 4),
            "total_return_index": round(total_value / first_close * 100, 4),
            "cash_dividend": round(cash_dividend, 4),
            "trading_volume": row.get("trading_volume", 0),
        })
    return series


def _build_metrics(ticker: str, config: dict[str, Any], series: list[dict], dividends: list[dict]) -> dict:
    if not series:
        return {}

    first = series[0]
    latest = series[-1]
    first_close = float(first["close"])
    latest_close = float(latest["close"])
    days = max(1, (date.fromisoformat(latest["date"]) - date.fromisoformat(first["date"])).days)

    price_since = latest_close / first_close - 1
    total_since = latest["total_return_index"] / first["total_return_index"] - 1
    dividend_sum = sum(float(item.get("cash_dividend") or 0) for item in dividends)

    return {
        "ticker": ticker,
        "name": config.get("name", ticker),
        "color": config.get("color", "#0f766e"),
        "launch_date": first["date"],
        "latest_date": latest["date"],
        "first_close": round(first_close, 4),
        "latest_close": round(latest_close, 4),
        "trading_days": len(series),
        "calendar_days": days,
        "price_return_since_inception": _round_pct(price_since),
        "total_return_since_inception": _round_pct(total_since),
        "annualized_price_return": _round_pct(_annualized(price_since, days)),
        "annualized_total_return": _round_pct(_annualized(total_since, days)),
        "price_return_1m": _round_pct(_period_return(series, "price_index", days_back=30)),
        "total_return_1m": _round_pct(_period_return(series, "total_return_index", days_back=30)),
        "price_return_3m": _round_pct(_period_return(series, "price_index", days_back=90)),
        "total_return_3m": _round_pct(_period_return(series, "total_return_index", days_back=90)),
        "price_return_6m": _round_pct(_period_return(series, "price_index", days_back=180)),
        "total_return_6m": _round_pct(_period_return(series, "total_return_index", days_back=180)),
        "price_return_ytd": _round_pct(_period_return(series, "price_index", ytd=True)),
        "total_return_ytd": _round_pct(_period_return(series, "total_return_index", ytd=True)),
        "max_drawdown_price": _round_pct(_max_drawdown(series, "price_index")),
        "max_drawdown_total": _round_pct(_max_drawdown(series, "total_return_index")),
        "dividend_count": len(dividends),
        "dividend_sum": round(dividend_sum, 4),
        "last_dividend_date": dividends[-1]["date"] if dividends else "",
    }


def _period_return(series: list[dict], field: str, days_back: int = 0, ytd: bool = False) -> float:
    if len(series) < 2:
        return 0.0

    latest = series[-1]
    latest_date = date.fromisoformat(latest["date"])
    if ytd:
        target = date(latest_date.year, 1, 1)
    else:
        target = latest_date - timedelta(days=days_back)

    start = series[0]
    for row in series:
        if date.fromisoformat(row["date"]) >= target:
            start = row
            break

    start_value = float(start[field])
    latest_value = float(latest[field])
    return latest_value / start_value - 1 if start_value else 0.0


def _max_drawdown(series: list[dict], field: str) -> float:
    peak = 0.0
    max_drawdown = 0.0
    for row in series:
        value = float(row[field])
        if value > peak:
            peak = value
        if peak > 0:
            max_drawdown = min(max_drawdown, value / peak - 1)
    return max_drawdown


def _annualized(total_return: float, days: int) -> float:
    if days <= 0 or total_return <= -1:
        return 0.0
    return (1 + total_return) ** (365 / days) - 1


def _build_summary(etfs: list[dict]) -> dict:
    def best(metric: str) -> dict:
        rows = [item for item in etfs if item.get(metric) is not None]
        if not rows:
            return {}
        row = max(rows, key=lambda item: item.get(metric, 0))
        return {
            "ticker": row["ticker"],
            "name": row["name"],
            "value": row.get(metric, 0),
        }

    def mildest_drawdown(metric: str) -> dict:
        rows = [item for item in etfs if item.get(metric) is not None]
        if not rows:
            return {}
        row = max(rows, key=lambda item: item.get(metric, 0))
        return {
            "ticker": row["ticker"],
            "name": row["name"],
            "value": row.get(metric, 0),
        }

    return {
        "active_etf_count": len(etfs),
        "best_price_since_inception": best("price_return_since_inception"),
        "best_total_since_inception": best("total_return_since_inception"),
        "best_price_1m": best("price_return_1m"),
        "best_total_1m": best("total_return_1m"),
        "mildest_price_drawdown": mildest_drawdown("max_drawdown_price"),
        "mildest_total_drawdown": mildest_drawdown("max_drawdown_total"),
    }


def _round_pct(value: float) -> float:
    return round(value * 100, 4)
