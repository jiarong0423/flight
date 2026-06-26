# GitHub Pages TDX Flight Board

純靜態 GitHub Pages 航班看板：

- `index.html`, `styles.css`, `app.js`: 前端航班看板。
- `data/flights.json`, `data/flights.csv`: 靜態航班快取。
- `scripts/crawler.py`: TDX 航空 FIDS crawler。
- `scripts/update_data.py`: 產生靜態 JSON / CSV。
- `scripts/local_scheduler.py`: 本地常駐排程，掃描資料、有變動才 commit/push。
- `scripts/push_update.ps1`: 單次更新並推送，適合 Windows 工作排程器。
- `scripts/install_windows_task.ps1`: 建立 Windows 工作排程器任務。
- `.github/workflows/update-flight-data.yml`: GitHub Actions 每 4 小時執行並推送更新。

## 資料來源

目前接的是交通部 TDX 運輸資料流通服務的航空 FIDS 機場出發/抵達資料。TDX 需要 API Key，所以不要把金鑰寫進 repo。

需要設定：

```text
TDX_CLIENT_ID
TDX_CLIENT_SECRET
```

本地 PowerShell：

```powershell
$env:TDX_CLIENT_ID="你的 Client ID"
$env:TDX_CLIENT_SECRET="你的 Client Secret"
python scripts\update_data.py
```

GitHub Actions：

1. 到 repo `Settings > Secrets and variables > Actions`。
2. 新增 repository secrets：
   - `TDX_CLIENT_ID`
   - `TDX_CLIENT_SECRET`
3. 到 `Actions` 手動執行 `Update flight static data`，或等排程每 4 小時更新。

如果沒有設定 TDX 金鑰，crawler 會使用 `mock-tdx-fallback`，讓 GitHub Pages 頁面和排程流程先保持可用。

## GitHub Pages 部署

到 repo `Settings > Pages`：

```text
Source: Deploy from a branch
Branch: main
Folder: /root
```

部署後網址：

```text
https://jiarong0423.github.io/flight/
```

## 本地排程推送

單次掃描、更新、有變動才推送：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\push_update.ps1
```

常駐每 4 小時掃描一次：

```powershell
python scripts\local_scheduler.py --interval-hours 4
```

或安裝成 Windows 工作排程器：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_windows_task.ps1
```

本地排程與 GitHub Actions 擇一即可。若兩邊都開，資料可能只是多產生幾次 commit，不會影響頁面，但通常不需要雙開。

## 調整機場

修改 `config/sources.json`：

```json
{
  "airports": ["TPE", "TSA", "KHH"],
  "directions": ["Departure", "Arrival"]
}
```
