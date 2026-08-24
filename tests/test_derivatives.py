import unittest

from scrapers.holdings import _parse_etfinfo_root_holdings, _parse_unitrust_assets
from update_history import _build_change_report


class HoldingsDerivativeTests(unittest.TestCase):
    def test_etfinfo_keeps_stocks_and_futures_only(self):
        stock = {
            "code": "TW0002330008",
            "name": "TAIWAN SEMICONDUCTOR",
            "weight": 20.0,
            "shares": 1000,
        }
        root = {
            "data": {
                "etf-detail-base-00404A": {
                    "holdings": {
                        "snapshotDate": "2026-08-21",
                        "stocks": [stock],
                        "holdings": [
                            stock,
                            {
                                "code": "202609TXF",
                                "name": "TAIEX FUTURES",
                                "weight": 12.5,
                                "shares": 61,
                            },
                            {
                                "code": "TXO51000",
                                "name": "TAIEX OPTION",
                                "weight": -0.1,
                                "shares": 2,
                            },
                            {
                                "code": "C_NTD",
                                "name": "CASH",
                                "weight": 5.0,
                                "shares": 50000,
                            },
                        ],
                    }
                }
            }
        }

        holdings = _parse_etfinfo_root_holdings(root, "00404A")

        self.assertEqual(["2330", "202609TXF"], [item["ticker"] for item in holdings])
        self.assertEqual(["stock", "future"], [item["asset_type"] for item in holdings])
        self.assertEqual(["股", "口"], [item["unit"] for item in holdings])

    def test_unitrust_keeps_stock_and_nominal_futures(self):
        assets = [
            {
                "AssetCode": "ST",
                "Details": [{
                    "DetailCode": "2330",
                    "DetailName": "台積電",
                    "NavRate": 10.0,
                    "Share": 1000,
                    "TranDate": "2026-08-21T00:00:00",
                }],
            },
            {
                "AssetCode": "GD",
                "Details": [{
                    "DetailCode": "TX",
                    "DetailName": "台指期貨",
                    "NavRate": 2.18,
                    "Share": 679,
                    "TranDate": "2026-08-21T00:00:00",
                }],
            },
            {
                "AssetCode": "CASH",
                "Details": [{"DetailCode": "TWD", "DetailName": "現金"}],
            },
        ]

        holdings = _parse_unitrust_assets(assets)

        self.assertEqual(["2330", "TX"], [item["ticker"] for item in holdings])
        self.assertEqual(["stock", "future"], [item["asset_type"] for item in holdings])

    def test_etfinfo_fallback_excludes_cash_and_options(self):
        root = {
            "data": {
                "etf-detail-base-00404A": {
                    "holdings": {
                        "snapshotDate": "2026-08-21",
                        "holdings": [
                            {"code": "TW0002330008", "name": "台積電", "weight": 10, "shares": 100},
                            {"code": "202609TXF", "name": "台股期貨09/26", "weight": 2, "shares": 5},
                            {"code": "TXO51000", "name": "臺指選擇權", "weight": -0.1, "shares": 2},
                            {"code": "C_NTD", "name": "現金", "weight": 5, "shares": 50000},
                        ],
                    }
                }
            }
        }

        holdings = _parse_etfinfo_root_holdings(root, "00404A")

        self.assertEqual(["2330", "202609TXF"], [item["ticker"] for item in holdings])
        self.assertEqual(["stock", "future"], [item["asset_type"] for item in holdings])

    def test_future_rollover_is_removed_and_added(self):
        previous = {
            "data_date": "2026-08-20",
            "etfs": {
                "00981A": [{
                    "ticker": "TX202608",
                    "name": "台指期202608",
                    "etf_name": "主動統一台股增長",
                    "weight": 2.0,
                    "shares": 600,
                    "asset_type": "future",
                    "unit": "口",
                }]
            },
        }
        current = {
            "data_date": "2026-08-21",
            "etfs": {
                "00981A": [{
                    "ticker": "TX202609",
                    "name": "台指期202609",
                    "etf_name": "主動統一台股增長",
                    "weight": 2.18,
                    "shares": 679,
                    "asset_type": "future",
                    "unit": "口",
                }]
            },
        }

        report = _build_change_report(previous, current)

        self.assertEqual(2, report["summary"]["future_changes"])
        self.assertEqual([], report["by_stock"])
        self.assertEqual(2, len(report["by_future"]))
        self.assertEqual({"added", "removed"}, {item["action"] for item in report["changes"]})
        self.assertEqual("TX202609", report["future_positions"][0]["ticker"])


if __name__ == "__main__":
    unittest.main()
