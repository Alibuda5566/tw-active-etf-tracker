"""Build latest ETF premium/discount data from ETFInfo."""

from __future__ import annotations

import json
import html
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from http_client import fetch_text
from scrapers.etfinfo import fetch_etfinfo_market


BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_PATH = DATA_DIR / "premium_discount.json"
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Encoding": "identity",
}


def rebuild_etf_premium_discount(
    etf_config: dict[str, dict[str, Any]],
    tickers: list[str] | None = None,
    delay_sec: float = 0.2,
) -> Path:
    """Fetch latest market price, NAV, and premium/discount for tracked ETFs."""

    markets: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    target_tickers = tickers or list(etf_config.keys())

    for ticker in target_tickers:
        cfg = etf_config.get(ticker, {})
        ticker_errors = []
        try:
            market = fetch_etfinfo_market(ticker)
        except Exception as exc:
            ticker_errors.append(f"ETFInfo: {exc}")
            market = {}

        if not market:
            try:
                market = _fetch_moneydj_market(ticker, cfg)
            except Exception as exc:
                ticker_errors.append(f"MoneyDJ: {exc}")
                market = {}

        if market:
            market["name"] = cfg.get("name") or market.get("name") or ticker
            market["type"] = cfg.get("type", "")
            market["color"] = cfg.get("color", "")
            markets.append(market)
        else:
            error = "; ".join(ticker_errors) or "latest market data not found"
            errors.append({"ticker": ticker, "error": error})

        if delay_sec:
            time.sleep(delay_sec)

    payload = {
        "data_date": _latest_date(markets),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "etfinfo",
        "formula": "(market_price / nav - 1) * 100",
        "etfs": markets,
        "errors": errors,
    }

    _save_json(OUTPUT_PATH, payload)
    _update_etf_cards(markets)
    return OUTPUT_PATH


def _update_etf_cards(markets: list[dict[str, Any]]) -> None:
    cards_path = DATA_DIR / "etf_cards.json"
    if not cards_path.exists():
        return

    cards = _load_json(cards_path)
    if not isinstance(cards, list):
        return

    by_ticker = {item.get("ticker"): item for item in markets}
    updated = 0
    for card in cards:
        if not isinstance(card, dict):
            continue
        market = by_ticker.get(card.get("ticker"))
        if not market:
            continue
        card["market_price"] = market.get("price", 0)
        card["nav"] = market.get("nav", 0)
        card["premium_discount"] = market.get("premium_discount", 0)
        card["premium_discount_date"] = market.get("date", "")
        card["premium_discount_source"] = market.get("source", "etfinfo")
        updated += 1

    if updated:
        _save_json(cards_path, cards)


def _fetch_moneydj_market(ticker: str, cfg: dict[str, Any]) -> dict[str, Any]:
    url = f"https://www.moneydj.com/etf/x/basic/basic0003.xdjhtm?etfid={ticker.lower()}.tw"
    text = fetch_text(url, headers=_BROWSER_HEADERS, timeout=30).text
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S | re.I):
        cells = _html_cells(row)
        if len(cells) < 4:
            continue
        if not re.fullmatch(r"\d{4}/\d{2}/\d{2}", cells[0]):
            continue
        nav = _to_float(cells[1])
        price = _to_float(cells[2])
        premium = _to_float(cells[3])
        if nav <= 0 or price <= 0:
            continue
        if cells[3].upper() == "N/A":
            premium = (price / nav - 1) * 100
        return {
            "ticker": ticker,
            "name": cfg.get("name", ticker),
            "date": cells[0].replace("/", "-"),
            "price": round(price, 4),
            "nav": round(nav, 4),
            "premium_discount": round(premium, 4),
            "change": 0,
            "aum": 0,
            "beneficiaries": 0,
            "source": "moneydj",
        }
    return {}


def _html_cells(row: str) -> list[str]:
    cells = []
    for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I):
        text = re.sub(r"<[^>]+>", " ", cell)
        cells.append(html.unescape(re.sub(r"\s+", " ", text)).strip())
    return cells


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return default


def _latest_date(markets: list[dict[str, Any]]) -> str:
    dates = [str(item.get("date", "")) for item in markets if item.get("date")]
    return max(dates) if dates else ""


def _load_json(path: Path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
