"""ETFInfo helpers for ETF market and payload data."""

from __future__ import annotations

import html
import json
import re
from typing import Any

from http_client import fetch_json, fetch_text


ETFINFO_BASE_URL = "https://www.etfinfo.tw"

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "identity",
}


def fetch_etfinfo_payload(ticker: str, page: str = "holdings") -> dict[str, Any]:
    """Fetch and hydrate ETFInfo Nuxt payload for one ETF page."""

    html_text = fetch_text(
        f"{ETFINFO_BASE_URL}/etf/{ticker}/{page}",
        headers=_BROWSER_HEADERS,
        timeout=30,
    ).text

    root = _payload_from_nuxt_data(html_text)
    if isinstance(root.get("data"), dict):
        return root

    payload_match = re.search(r'href="(?P<url>/[^"]+_payload\.json[^"]*)"', html_text)
    if not payload_match:
        return root

    payload_url = ETFINFO_BASE_URL + html.unescape(payload_match.group("url"))
    payload = fetch_json(payload_url, headers={"User-Agent": _BROWSER_HEADERS["User-Agent"]}, timeout=30).data
    if not isinstance(payload, list):
        return {}
    hydrated = hydrate_nuxt_payload(payload)
    return hydrated if isinstance(hydrated, dict) else {}


def fetch_etfinfo_market(ticker: str) -> dict[str, Any]:
    """Return latest price, NAV, and premium/discount from ETFInfo."""

    root = fetch_etfinfo_payload(ticker, "holdings")
    data = root.get("data") if isinstance(root, dict) else {}
    base = data.get(f"etf-detail-base-{ticker}") if isinstance(data, dict) else {}
    latest = base.get("latestMarket") if isinstance(base, dict) else {}
    info = base.get("info") if isinstance(base, dict) else {}
    if not isinstance(latest, dict) or not latest:
        return {}

    price = _to_float(latest.get("price"))
    nav = _to_float(latest.get("nav"))
    premium = _to_float(latest.get("premium"))
    if nav and price and "premium" not in latest:
        premium = (price / nav - 1) * 100

    return {
        "ticker": ticker,
        "name": _clean_text(info.get("name")) or ticker,
        "date": _clean_text(latest.get("date")),
        "price": round(price, 4),
        "nav": round(nav, 4),
        "premium_discount": round(premium, 4),
        "change": round(_to_float(latest.get("change")), 4),
        "aum": _to_float(latest.get("aum")),
        "beneficiaries": int(_to_float(latest.get("beneficiaries"))),
        "source": "etfinfo",
    }


def _payload_from_nuxt_data(text: str) -> dict[str, Any]:
    match = re.search(
        r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>',
        text,
        re.S,
    )
    if not match:
        return {}
    try:
        payload = json.loads(html.unescape(match.group(1)))
        hydrated = hydrate_nuxt_payload(payload)
    except (TypeError, ValueError, json.JSONDecodeError, KeyError, IndexError):
        return {}
    return hydrated if isinstance(hydrated, dict) else {}


def hydrate_nuxt_payload(payload: list[Any]) -> Any:
    def hydrate(index: Any, memo: dict[int, Any]) -> Any:
        if not isinstance(index, int):
            return index
        if index < 0:
            return None
        if index in memo:
            return memo[index]

        value = payload[index]
        if isinstance(value, dict):
            obj: dict[str, Any] = {}
            memo[index] = obj
            for key, child in value.items():
                obj[key] = hydrate(child, memo)
            return obj

        if isinstance(value, list):
            if value and value[0] in {"Reactive", "ShallowReactive", "Ref", "ShallowRef"} and len(value) >= 2:
                return hydrate(value[1], memo)
            if value and value[0] in {"Date", "Set"} and len(value) >= 2:
                return hydrate(value[1], memo)
            arr: list[Any] = []
            memo[index] = arr
            arr.extend(hydrate(child, memo) for child in value)
            return arr

        return value

    return hydrate(0, {})


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return default
