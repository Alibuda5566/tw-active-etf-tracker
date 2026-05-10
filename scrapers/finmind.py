"""FinMind Taiwan ETF price client.

Official API reference:
https://api.finmindtrade.com/api/v4/data with dataset=TaiwanStockPrice.
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any, Optional

from http_client import HttpClientError, fetch_json


FINMIND_DATA_URL = "https://api.finmindtrade.com/api/v4/data"


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    return int(_to_float(value, float(default)))


def _latest_row(rows: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    valid_rows = [row for row in rows if isinstance(row, dict) and row.get("date")]
    if not valid_rows:
        return None
    return max(valid_rows, key=lambda row: str(row.get("date", "")))


def fetch_etf_price(
    ticker: str,
    token: str = "",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    timeout: int = 20,
) -> dict[str, Any]:
    """Fetch the latest available daily price for one Taiwan ETF."""

    today = date.today()
    start = start_date or (today - timedelta(days=60)).isoformat()
    end = end_date or today.isoformat()
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": ticker,
        "start_date": start,
        "end_date": end,
        "token": token,
    }

    response = fetch_json(FINMIND_DATA_URL, params=params, timeout=timeout)
    payload = response.data
    if not isinstance(payload, dict):
        raise ValueError(f"FinMind returned an unexpected payload for {ticker}")

    status = payload.get("status")
    if status not in (None, 200, "200"):
        message = payload.get("msg") or payload.get("message") or payload
        raise ValueError(f"FinMind error for {ticker}: {message}")

    rows = payload.get("data") or []
    if not isinstance(rows, list):
        raise ValueError(f"FinMind data field is not a list for {ticker}")

    row = _latest_row(rows)
    if not row:
        raise ValueError(f"No TaiwanStockPrice rows returned for {ticker}")

    return {
        "ticker": ticker,
        "date": row.get("date", ""),
        "open": _to_float(row.get("open")),
        "max": _to_float(row.get("max")),
        "min": _to_float(row.get("min")),
        "close": _to_float(row.get("close")),
        "trading_volume": _to_int(row.get("Trading_Volume")),
        "trading_money": _to_int(row.get("Trading_money")),
    }


def fetch_etf_price_history(
    ticker: str,
    token: str = "",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    timeout: int = 30,
) -> list[dict[str, Any]]:
    """Fetch daily price history for one Taiwan ETF."""

    today = date.today()
    start = start_date or "2025-01-01"
    end = end_date or today.isoformat()
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": ticker,
        "start_date": start,
        "end_date": end,
        "token": token,
    }
    payload = fetch_json(FINMIND_DATA_URL, params=params, timeout=timeout).data
    if not isinstance(payload, dict):
        raise ValueError(f"FinMind returned an unexpected payload for {ticker}")
    status = payload.get("status")
    if status not in (None, 200, "200"):
        message = payload.get("msg") or payload.get("message") or payload
        raise ValueError(f"FinMind error for {ticker}: {message}")

    rows = payload.get("data") or []
    if not isinstance(rows, list):
        raise ValueError(f"FinMind data field is not a list for {ticker}")

    history = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("date"):
            continue
        close = _to_float(row.get("close"))
        if close <= 0:
            continue
        history.append({
            "date": row.get("date", ""),
            "open": _to_float(row.get("open")),
            "max": _to_float(row.get("max")),
            "min": _to_float(row.get("min")),
            "close": close,
            "trading_volume": _to_int(row.get("Trading_Volume")),
            "trading_money": _to_int(row.get("Trading_money")),
        })
    history.sort(key=lambda item: item["date"])
    return history


def fetch_etf_dividend_results(
    ticker: str,
    token: str = "",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    timeout: int = 30,
) -> list[dict[str, Any]]:
    """Fetch ex-dividend results for one Taiwan ETF."""

    today = date.today()
    start = start_date or "2025-01-01"
    end = end_date or today.isoformat()
    params = {
        "dataset": "TaiwanStockDividendResult",
        "data_id": ticker,
        "start_date": start,
        "end_date": end,
        "token": token,
    }
    payload = fetch_json(FINMIND_DATA_URL, params=params, timeout=timeout).data
    if not isinstance(payload, dict):
        raise ValueError(f"FinMind returned an unexpected dividend payload for {ticker}")
    status = payload.get("status")
    if status not in (None, 200, "200"):
        message = payload.get("msg") or payload.get("message") or payload
        raise ValueError(f"FinMind dividend error for {ticker}: {message}")

    rows = payload.get("data") or []
    if not isinstance(rows, list):
        raise ValueError(f"FinMind dividend data field is not a list for {ticker}")

    dividends = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("date"):
            continue
        cash_dividend = _to_float(row.get("stock_and_cache_dividend"))
        if cash_dividend <= 0:
            continue
        dividends.append({
            "date": row.get("date", ""),
            "cash_dividend": cash_dividend,
            "type": row.get("stock_or_cache_dividend", ""),
            "before_price": _to_float(row.get("before_price")),
            "after_price": _to_float(row.get("after_price")),
            "reference_price": _to_float(row.get("reference_price")),
        })
    dividends.sort(key=lambda item: item["date"])
    return dividends


def fetch_all_etf_prices(
    tickers: list[str],
    token: str = "",
    delay_sec: float = 0.5,
) -> dict[str, dict[str, Any]]:
    """Fetch latest prices for all requested ETF tickers.

    Individual failures are reported and skipped so the update script can still
    refresh whatever data is available.
    """

    prices: dict[str, dict[str, Any]] = {}
    for index, ticker in enumerate(tickers):
        try:
            price = fetch_etf_price(ticker, token=token)
        except (HttpClientError, ValueError) as exc:
            print(f"  [--] {ticker}: {exc}")
        else:
            prices[ticker] = price
            print(f"  [OK] {ticker}: {price['date']} close={price['close']}")

        if index < len(tickers) - 1 and delay_sec > 0:
            time.sleep(delay_sec)

    return prices
