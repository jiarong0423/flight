# GitHub Pages Flight Calendar

純靜態 GitHub Pages 實作，可用 GitHub Actions 或本地排程定期推送更新：

- `index.html`, `styles.css`, `app.js`: 前端日曆介面。
- `data/flights.json`, `data/flights.csv`: 靜態資料快取。
- `scripts/update_data.py`: 定期更新資料的腳本。
- `scripts/local_scheduler.py`: 本地常駐排程，掃描資料、有變動才 commit/push。
- `scripts/push_update.ps1`: 單次更新並推送，適合 Windows 工作排程器。
- `scripts/install_windows_task.ps1`: 建立 Windows 工作排程器任務。
- `.github/workflows/update-flight-data.yml`: GitHub Actions 每 4 小時執行並推送更新。

目前 crawler 支援 JSON、CSV、HTML regex 三種來源，設定在 `config/sources.json`。正式資料源還沒填入前，會使用 `mock-fallback` 讓 GitHub Pages 和排程流程先跑通。

## 部署

1. 把這個資料夾內容推到 GitHub repo。
2. 到 repo `Settings > Pages`。
3. Source 選 `Deploy from a branch`。
4. Branch 選 `main`，資料夾選 `/root`。
5. 到 `Actions` 確認 `Update flight static data` 有執行權限。

## 本機產生資料

```powershell
python scripts\update_data.py
```

直接開 `index.html` 即可預覽。

## 本地排程推送

先確認這個資料夾已經是 Git repo，且 remote 可以 push：

```powershell
git remote -v
git push
```

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

