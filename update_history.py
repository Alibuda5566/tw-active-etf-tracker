"""Minimal history helpers for the ETF JSON data files."""

from __future__ import annotations

import json
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Optional


BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
HISTORY_DIR = DATA_DIR / "history"
SNAPSHOT_DIR = HISTORY_DIR / "snapshots"
DAILY_HOLDINGS_DIR = HISTORY_DIR / "daily_holdings"
CHANGE_DIR = HISTORY_DIR / "changes"
CHANGE_OUTPUT = DATA_DIR / "holding_changes.json"
REPORT_DIR = DATA_DIR / "reports"
LATEST_REPORT = REPORT_DIR / "active_etf_daily_report_latest.md"


def _load_json(path: Path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def get_data_date() -> str:
    """Return a stable date label for snapshots."""

    cards_path = DATA_DIR / "etf_cards.json"
    if cards_path.exists():
        try:
            cards = _load_json(cards_path)
        except Exception:
            cards = []
        dates = []
        for card in cards:
            if isinstance(card, dict):
                value = card.get("date") or card.get("price_date")
                if value:
                    dates.append(str(value))
        if dates:
            return max(dates)
    return date.today().isoformat()


def save_snapshot(data_date: Optional[str] = None) -> Path:
    """Copy current JSON data files into data/history/snapshots."""

    label = data_date or get_data_date()
    timestamp = datetime.now().strftime("%H%M%S")
    snapshot_dir = SNAPSHOT_DIR / f"{label}_{timestamp}"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    for name in ("etf_cards.json", "cross_data.json"):
        source = DATA_DIR / name
        if source.exists():
            shutil.copy2(source, snapshot_dir / name)

    return snapshot_dir


def save_daily_holdings_snapshot(data_date: Optional[str] = None) -> Path:
    """Save one normalized holdings snapshot per data date."""

    cross_path = DATA_DIR / "cross_data.json"
    if not cross_path.exists():
        raise FileNotFoundError(cross_path)

    cross_rows = _load_json(cross_path)
    holdings = _holdings_from_cross_data(cross_rows)
    label = data_date or _holdings_data_date(holdings) or get_data_date()
    snapshot = {
        "data_date": label,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "etfs": holdings,
    }

    output = DAILY_HOLDINGS_DIR / f"{label}.json"
    _save_json(output, snapshot)
    return output


def rebuild_changes(data_date: Optional[str] = None) -> Path:
    """Compare the latest daily holdings snapshot with the prior date."""

    dates = _daily_snapshot_dates()
    if not dates:
        save_daily_holdings_snapshot(data_date)
        dates = _daily_snapshot_dates()
    if not dates:
        raise FileNotFoundError(DAILY_HOLDINGS_DIR)

    if data_date and data_date in dates:
        current_date = data_date
    else:
        current_date = dates[-1]

    current_snapshot = _load_daily_snapshot(current_date)
    previous_dates = [item for item in dates if item < current_date]
    previous_date = previous_dates[-1] if previous_dates else None
    previous_snapshot = _load_daily_snapshot(previous_date) if previous_date else None

    report = _build_change_report(previous_snapshot, current_snapshot)
    _save_json(CHANGE_OUTPUT, report)
    _save_json(CHANGE_DIR / f"{current_date}.json", report)
    return CHANGE_OUTPUT


def save_daily_report(data_date: Optional[str] = None) -> Path:
    """Write a Markdown report for active ETF daily holding changes."""

    if not CHANGE_OUTPUT.exists():
        rebuild_changes(data_date)

    report = _load_json(CHANGE_OUTPUT)
    current_date = report.get("current_date") or data_date or get_data_date()
    markdown = _render_active_etf_daily_report(report)

    output = REPORT_DIR / f"active_etf_daily_report_{current_date}.md"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    LATEST_REPORT.write_text(markdown, encoding="utf-8")
    return output


def rebuild_history() -> Path:
    """Create a compact manifest of available snapshots."""

    entries = []
    if SNAPSHOT_DIR.exists():
        for path in sorted(SNAPSHOT_DIR.iterdir()):
            if path.is_dir():
                entries.append({
                    "name": path.name,
                    "path": str(path.relative_to(DATA_DIR)).replace("\\", "/"),
                    "created_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
                    "files": sorted(child.name for child in path.iterdir() if child.is_file()),
                })

    daily_dates = _daily_snapshot_dates()
    manifest = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "latest_report": "reports/active_etf_daily_report_latest.md" if LATEST_REPORT.exists() else "",
        "snapshots": entries,
        "daily_holdings": [
            {
                "date": snapshot_date,
                "path": f"history/daily_holdings/{snapshot_date}.json",
            }
            for snapshot_date in daily_dates
        ],
    }
    output = HISTORY_DIR / "manifest.json"
    _save_json(output, manifest)
    return output


def _holdings_from_cross_data(cross_rows) -> dict[str, list[dict]]:
    holdings: dict[str, list[dict]] = {}
    for row in cross_rows:
        stock_ticker = str(row.get("ticker", "")).strip()
        stock_name = str(row.get("name", "")).strip()
        if not stock_ticker:
            continue
        for etf in row.get("etfs", []):
            etf_ticker = str(etf.get("etf_ticker", "")).strip()
            if not etf_ticker:
                continue
            holdings.setdefault(etf_ticker, []).append({
                "ticker": stock_ticker,
                "name": stock_name,
                "etf_name": etf.get("etf_name", etf_ticker),
                "weight": _to_float(etf.get("weight")),
                "shares": _to_int(etf.get("shares")),
                "date": etf.get("date", ""),
            })

    for etf_ticker in list(holdings):
        holdings[etf_ticker].sort(key=lambda item: item["ticker"])
    return dict(sorted(holdings.items()))


def _holdings_data_date(holdings: dict[str, list[dict]]) -> str:
    dates = []
    for etf_holdings in holdings.values():
        for item in etf_holdings:
            if item.get("date"):
                dates.append(str(item["date"]))
    return max(dates) if dates else ""


def _daily_snapshot_dates() -> list[str]:
    if not DAILY_HOLDINGS_DIR.exists():
        return []
    dates = []
    for path in DAILY_HOLDINGS_DIR.glob("*.json"):
        dates.append(path.stem)
    return sorted(dates)


def _load_daily_snapshot(snapshot_date: Optional[str]):
    if not snapshot_date:
        return None
    return _load_json(DAILY_HOLDINGS_DIR / f"{snapshot_date}.json")


def _build_change_report(previous_snapshot, current_snapshot) -> dict:
    current_date = current_snapshot.get("data_date", "")
    previous_date = previous_snapshot.get("data_date", "") if previous_snapshot else None
    previous_etfs = previous_snapshot.get("etfs", {}) if previous_snapshot else {}
    current_etfs = current_snapshot.get("etfs", {})

    if previous_snapshot is None:
        by_etf = {}
        for etf_ticker, holdings in sorted(current_etfs.items()):
            summary = _summarize_changes([])
            summary["holding_count"] = len(holdings)
            by_etf[etf_ticker] = summary

        summary = _summarize_changes([])
        summary["etf_count"] = len(current_etfs)
        summary["stock_count"] = _stock_count(current_etfs)
        summary["holding_links"] = sum(len(items) for items in current_etfs.values())
        return {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "current_date": current_date,
            "previous_date": None,
            "baseline": True,
            "summary": summary,
            "by_etf": by_etf,
            "by_stock": [],
            "changes": [],
            "top_increases": [],
            "top_decreases": [],
            "top_stock_buys": [],
            "top_stock_sells": [],
        }

    changes = []
    by_etf = {}
    for etf_ticker in sorted(set(previous_etfs) | set(current_etfs)):
        old_map = {item["ticker"]: item for item in previous_etfs.get(etf_ticker, [])}
        new_map = {item["ticker"]: item for item in current_etfs.get(etf_ticker, [])}
        etf_changes = []

        for stock_ticker in sorted(set(old_map) | set(new_map)):
            old = old_map.get(stock_ticker)
            new = new_map.get(stock_ticker)
            change = _compare_holding(etf_ticker, stock_ticker, old, new, previous_date, current_date)
            if change:
                changes.append(change)
                etf_changes.append(change)

        summary = _summarize_changes(etf_changes)
        summary["holding_count"] = len(new_map)
        by_etf[etf_ticker] = summary

    summary = _summarize_changes(changes)
    summary["etf_count"] = len(current_etfs)
    summary["stock_count"] = _stock_count(current_etfs)
    summary["holding_links"] = sum(len(items) for items in current_etfs.values())
    by_stock = _rollup_changes_by_stock(changes)

    return {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "current_date": current_date,
        "previous_date": previous_date,
        "baseline": previous_snapshot is None,
        "summary": summary,
        "by_etf": by_etf,
        "by_stock": by_stock,
        "changes": sorted(
            changes,
            key=lambda item: (
                _action_rank(item["action"]),
                -abs(item["weight_delta"]),
                item["etf_ticker"],
                item["stock_ticker"],
            ),
        ),
        "top_increases": _top_changes(changes, positive=True),
        "top_decreases": _top_changes(changes, positive=False),
        "top_stock_buys": _top_stock_rollups(by_stock, positive=True),
        "top_stock_sells": _top_stock_rollups(by_stock, positive=False),
    }


def _compare_holding(
    etf_ticker: str,
    stock_ticker: str,
    old,
    new,
    previous_date: Optional[str],
    current_date: str,
):
    old_weight = _to_float(old.get("weight")) if old else 0.0
    new_weight = _to_float(new.get("weight")) if new else 0.0
    old_shares = _to_int(old.get("shares")) if old else 0
    new_shares = _to_int(new.get("shares")) if new else 0
    weight_delta = round(new_weight - old_weight, 6)
    shares_delta = new_shares - old_shares

    if old is None:
        action = "added"
    elif new is None:
        action = "removed"
    elif abs(weight_delta) < 0.0001 and shares_delta == 0:
        return None
    elif weight_delta > 0 or (abs(weight_delta) < 0.0001 and shares_delta > 0):
        action = "increased"
    elif weight_delta < 0 or (abs(weight_delta) < 0.0001 and shares_delta < 0):
        action = "decreased"
    else:
        action = "changed"

    source = new or old or {}
    return {
        "action": action,
        "etf_ticker": etf_ticker,
        "etf_name": source.get("etf_name", etf_ticker),
        "stock_ticker": stock_ticker,
        "stock_name": source.get("name", ""),
        "old_weight": round(old_weight, 6),
        "new_weight": round(new_weight, 6),
        "weight_delta": weight_delta,
        "old_shares": old_shares,
        "new_shares": new_shares,
        "shares_delta": shares_delta,
        "previous_date": previous_date,
        "current_date": current_date,
    }


def _summarize_changes(changes: list[dict]) -> dict:
    summary = {
        "total_changes": len(changes),
        "added": 0,
        "removed": 0,
        "increased": 0,
        "decreased": 0,
        "changed": 0,
    }
    for change in changes:
        action = change.get("action", "changed")
        summary[action] = summary.get(action, 0) + 1
    return summary


def _stock_count(etfs: dict[str, list[dict]]) -> int:
    stocks = set()
    for holdings in etfs.values():
        for item in holdings:
            stocks.add(item.get("ticker"))
    return len(stocks)


def _top_changes(changes: list[dict], positive: bool) -> list[dict]:
    if positive:
        candidates = [item for item in changes if item["weight_delta"] > 0 or item["action"] == "added"]
        return sorted(candidates, key=lambda item: (-item["weight_delta"], item["etf_ticker"], item["stock_ticker"]))[:20]

    candidates = [item for item in changes if item["weight_delta"] < 0 or item["action"] == "removed"]
    return sorted(candidates, key=lambda item: (item["weight_delta"], item["etf_ticker"], item["stock_ticker"]))[:20]


def _rollup_changes_by_stock(changes: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for change in changes:
        stock_ticker = change.get("stock_ticker", "")
        if not stock_ticker:
            continue

        row = grouped.setdefault(stock_ticker, {
            "stock_ticker": stock_ticker,
            "stock_name": change.get("stock_name", ""),
            "net_weight_delta": 0.0,
            "net_shares_delta": 0,
            "affected_etfs": set(),
            "added": 0,
            "removed": 0,
            "increased": 0,
            "decreased": 0,
            "changed": 0,
            "changes": [],
        })
        action = change.get("action", "changed")
        row["stock_name"] = row["stock_name"] or change.get("stock_name", "")
        row["net_weight_delta"] += _to_float(change.get("weight_delta"))
        row["net_shares_delta"] += _to_int(change.get("shares_delta"))
        row["affected_etfs"].add(change.get("etf_ticker", ""))
        row[action] = row.get(action, 0) + 1
        row["changes"].append({
            "action": action,
            "etf_ticker": change.get("etf_ticker", ""),
            "etf_name": change.get("etf_name", ""),
            "old_weight": change.get("old_weight", 0),
            "new_weight": change.get("new_weight", 0),
            "weight_delta": change.get("weight_delta", 0),
            "old_shares": change.get("old_shares", 0),
            "new_shares": change.get("new_shares", 0),
            "shares_delta": change.get("shares_delta", 0),
        })

    result = []
    for row in grouped.values():
        affected = sorted(item for item in row.pop("affected_etfs") if item)
        row["affected_etf_count"] = len(affected)
        row["affected_etfs"] = affected
        row["buy_count"] = row["added"] + row["increased"]
        row["sell_count"] = row["removed"] + row["decreased"]
        row["net_weight_delta"] = round(row["net_weight_delta"], 6)
        row["changes"].sort(key=lambda item: (
            _action_rank(item["action"]),
            -abs(_to_float(item["weight_delta"])),
            item["etf_ticker"],
        ))
        result.append(row)

    return sorted(
        result,
        key=lambda item: (
            -abs(item["net_weight_delta"]),
            -item["affected_etf_count"],
            item["stock_ticker"],
        ),
    )


def _top_stock_rollups(rollups: list[dict], positive: bool) -> list[dict]:
    if positive:
        candidates = [item for item in rollups if item["net_weight_delta"] > 0 or item["buy_count"] > item["sell_count"]]
        return sorted(
            candidates,
            key=lambda item: (-item["net_weight_delta"], -item["buy_count"], item["stock_ticker"]),
        )[:20]

    candidates = [item for item in rollups if item["net_weight_delta"] < 0 or item["sell_count"] > item["buy_count"]]
    return sorted(
        candidates,
        key=lambda item: (item["net_weight_delta"], -item["sell_count"], item["stock_ticker"]),
    )[:20]


def _render_active_etf_daily_report(report: dict) -> str:
    cards = _load_etf_cards()
    active_cards = [card for card in cards if card.get("type") == "active"]
    active_tickers = {card["ticker"] for card in active_cards}
    active_changes = [
        change for change in report.get("changes", [])
        if change.get("etf_ticker") in active_tickers
    ]
    active_summary = _summarize_changes(active_changes)
    active_stock_rollups = _rollup_changes_by_stock(active_changes)
    top_buys = _top_stock_rollups(active_stock_rollups, positive=True)
    top_sells = _top_stock_rollups(active_stock_rollups, positive=False)

    current_date = report.get("current_date") or "-"
    previous_date = report.get("previous_date")
    period = f"{previous_date} -> {current_date}" if previous_date else f"{current_date} 基準日"

    lines = [
        f"# 主動式 ETF 每日進出報表",
        "",
        f"- 報表日期：{current_date}",
        f"- 比較區間：{period}",
        f"- 產生時間：{datetime.now().isoformat(timespec='seconds')}",
        f"- 統計範圍：{len(active_cards)} 檔主動式 ETF",
        "",
        "## 全體主動式 ETF 進出總結",
        "",
        _markdown_table(
            ["新增", "刪除", "增持", "減持", "其他變動", "合計"],
            [[
                active_summary["added"],
                active_summary["removed"],
                active_summary["increased"],
                active_summary["decreased"],
                active_summary["changed"],
                active_summary["total_changes"],
            ]],
        ),
        "",
        "### 主動式 ETF 溢/折價概覽",
        "",
        _premium_discount_markdown(active_cards),
        "",
    ]

    if report.get("baseline"):
        lines.extend([
            "目前只有基準日快照，尚無前一個交易日可比較。下一個不同持股日期更新後，這份報表會列出新增、刪除、增持與減持明細。",
            "",
        ])

    lines.extend([
        "### 整體加碼排行",
        "",
        _stock_rollup_markdown(top_buys),
        "",
        "### 整體減碼排行",
        "",
        _stock_rollup_markdown(top_sells),
        "",
        "### 各主動式 ETF 變動摘要",
        "",
        _etf_summary_markdown(active_cards, report.get("by_etf", {})),
        "",
        "## 各檔 ETF 進出明細",
        "",
    ])

    changes_by_etf: dict[str, list[dict]] = {}
    for change in active_changes:
        changes_by_etf.setdefault(change.get("etf_ticker", ""), []).append(change)

    for card in active_cards:
        ticker = card["ticker"]
        name = card.get("name", "")
        summary = report.get("by_etf", {}).get(ticker, {})
        etf_changes = changes_by_etf.get(ticker, [])
        lines.extend([
            f"### {ticker} {name}",
            "",
            f"- 持股檔數：{summary.get('holding_count', 0)}",
            f"- 市價 / 淨值 / 溢/折價：{_fmt_price(card.get('market_price') or card.get('price'))} / {_fmt_price(card.get('nav'))} / {_fmt_optional_percent(card.get('premium_discount'), signed=True)}",
            f"- 新增：{summary.get('added', 0)} / 刪除：{summary.get('removed', 0)} / 增持：{summary.get('increased', 0)} / 減持：{summary.get('decreased', 0)} / 合計：{summary.get('total_changes', 0)}",
            "",
        ])
        if etf_changes:
            rows = []
            for change in sorted(etf_changes, key=lambda item: (_action_rank(item["action"]), -abs(_to_float(item["weight_delta"])), item["stock_ticker"])):
                rows.append([
                    _action_text(change.get("action")),
                    change.get("stock_ticker", ""),
                    change.get("stock_name", ""),
                    _fmt_percent(change.get("old_weight"), signed=False),
                    _fmt_percent(change.get("new_weight"), signed=False),
                    _fmt_percent(change.get("weight_delta"), signed=True),
                    _fmt_signed_int(change.get("shares_delta")),
                ])
            lines.extend([
                _markdown_table(["狀態", "股票", "名稱", "前日權重", "今日權重", "權重差", "股數差"], rows),
                "",
            ])
        else:
            lines.extend(["本期沒有進出變動。", ""])

    return "\n".join(lines).rstrip() + "\n"


def _load_etf_cards() -> list[dict]:
    path = DATA_DIR / "etf_cards.json"
    if not path.exists():
        return []
    cards = _load_json(path)
    return cards if isinstance(cards, list) else []


def _stock_rollup_markdown(rows: list[dict]) -> str:
    if not rows:
        return "尚無資料。"
    return _markdown_table(
        ["股票", "名稱", "影響 ETF", "淨權重差", "淨股數差", "新增", "刪除", "增持", "減持"],
        [
            [
                row.get("stock_ticker", ""),
                row.get("stock_name", ""),
                row.get("affected_etf_count", 0),
                _fmt_percent(row.get("net_weight_delta"), signed=True),
                _fmt_signed_int(row.get("net_shares_delta")),
                row.get("added", 0),
                row.get("removed", 0),
                row.get("increased", 0),
                row.get("decreased", 0),
            ]
            for row in rows[:20]
        ],
    )


def _etf_summary_markdown(active_cards: list[dict], by_etf: dict) -> str:
    rows = []
    for card in active_cards:
        ticker = card["ticker"]
        summary = by_etf.get(ticker, {})
        rows.append([
            ticker,
            card.get("name", ""),
            _fmt_price(card.get("nav")),
            _fmt_optional_percent(card.get("premium_discount"), signed=True),
            summary.get("holding_count", 0),
            summary.get("added", 0),
            summary.get("removed", 0),
            summary.get("increased", 0),
            summary.get("decreased", 0),
            summary.get("total_changes", 0),
        ])
    return _markdown_table(["ETF", "名稱", "淨值", "溢/折價", "持股", "新增", "刪除", "增持", "減持", "合計"], rows)


def _premium_discount_markdown(active_cards: list[dict]) -> str:
    rows = []
    for card in active_cards:
        rows.append([
            card.get("ticker", ""),
            card.get("name", ""),
            card.get("premium_discount_date") or card.get("price_date") or "-",
            _fmt_price(card.get("market_price") or card.get("price")),
            _fmt_price(card.get("nav")),
            _fmt_optional_percent(card.get("premium_discount"), signed=True),
        ])
    return _markdown_table(["ETF", "名稱", "日期", "市價", "淨值", "溢/折價"], rows)


def _markdown_table(headers: list, rows: list[list]) -> str:
    escaped_headers = [_escape_md_cell(value) for value in headers]
    lines = [
        "| " + " | ".join(escaped_headers) + " |",
        "| " + " | ".join("---" for _ in escaped_headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_escape_md_cell(value) for value in row) + " |")
    return "\n".join(lines)


def _escape_md_cell(value) -> str:
    return str(value if value is not None else "").replace("\n", " ").replace("|", "\\|")


def _action_text(action: str) -> str:
    return {
        "added": "新增",
        "removed": "刪除",
        "increased": "增持",
        "decreased": "減持",
        "changed": "變動",
    }.get(action, "變動")


def _fmt_percent(value, signed: bool) -> str:
    number = _to_float(value)
    sign = "+" if signed and number > 0 else ""
    return f"{sign}{number:.2f}%"


def _fmt_optional_percent(value, signed: bool) -> str:
    if value is None or value == "":
        return "-"
    number = _to_float(value)
    sign = "+" if signed and number > 0 else ""
    return f"{sign}{number:.2f}%"


def _fmt_price(value) -> str:
    if value is None or value == "":
        return "-"
    return f"{_to_float(value):.2f}"


def _fmt_signed_int(value) -> str:
    number = _to_int(value)
    sign = "+" if number > 0 else ""
    return f"{sign}{number:,}"


def _action_rank(action: str) -> int:
    order = {
        "added": 0,
        "removed": 1,
        "increased": 2,
        "decreased": 3,
        "changed": 4,
    }
    return order.get(action, 9)


def _to_float(value, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return default


def _to_int(value, default: int = 0) -> int:
    return int(_to_float(value, float(default)))
