# Taiwan Active ETF Tracker

台股主動式 ETF 追蹤看板。這個專案會整理主動式 ETF 的持股、每日增減、溢/折價與上市以來績效，並產出可下載的每日 Markdown 報告。

## Pages

預計 GitHub Pages 網址：

```text
https://alibuda5566.github.io/tw-active-etf-tracker/
```

## 頁面

- `index.html`：ETF 清單與成分股交集。
- `changes.html`：每日持股增減追蹤與每日報告下載。
- `performance.html`：主動式 ETF 上市以來績效與互動式走勢圖。

## 本機執行

```powershell
cd H:\data\fetch-findmind
python update_data.py
python -m http.server 8765
```

瀏覽：

```text
http://localhost:8765/index.html
```

## 每日更新

GitHub Actions 會在台北時間週一到週五晚上 7 點自動執行：

```bash
python update_data.py
```

更新完成後會 commit `data/` 內的 JSON、歷史快照與報告檔，GitHub Pages 會跟著重新部署。

## FinMind Token

目前專案沒有硬寫 FinMind token，預設會用免 token 模式呼叫 FinMind API。

如果之後需要 token，請在 GitHub repository secrets 新增：

```text
FINMIND_TOKEN
```

`update_data.py` 會自動讀取這個環境變數。

## 主要資料

- `data/etf_cards.json`：ETF 基本資料、價格、淨值與溢/折價。
- `data/cross_data.json`：股票與 ETF 持股交集。
- `data/holding_changes.json`：最新一次每日持股變動。
- `data/premium_discount.json`：各 ETF 市價、淨值與溢/折價。
- `data/performance/active_etf_performance.json`：主動式 ETF 績效。
- `data/reports/active_etf_daily_report_YYYY-MM-DD.md`：每日進出報告。
