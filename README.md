# 臺灣上市／上櫃官方開放資料每日快照

這個儲存庫每天把證交所與櫃買中心 **OpenAPI（政府開放資料）** 的最新回應原封不動存下來。OpenAPI 只提供最新一期，不能查歷史，所以要每天存。

- **非官方存檔**。內容是官方 API 回應的原始位元組，沒有修改、補值或重新排版；完整性與正確性以官方來源為準。
- 只存下表列出的開放資料端點。**不含**兩個網站報表頁或查詢介面的資料。
- 不是投資建議。

## 來源與授權

使用 [證交所 OpenAPI](https://openapi.twse.com.tw/) 和 [櫃買中心 OpenAPI](https://www.tpex.org.tw/openapi/)。下表各資料集刊載於政府資料開放平臺，依[政府資料開放授權條款－第 1 版](https://data.gov.tw/license)釋出。每份快照的旁檔記有提供機關、資料集名稱與授權網址。

| OpenAPI 端點 | 資料集 | 日期欄位及用途 |
| --- | --- | --- |
| 上市 `STOCK_DAY_ALL` | [11549](https://data.gov.tw/dataset/11549) | `Date` 是交易日 |
| 上櫃 `tpex_mainboard_quotes` | [11371](https://data.gov.tw/dataset/11371) | `Date` 是交易日 |
| 上市 `TWT48U_ALL` | [89748](https://data.gov.tw/dataset/89748) | `Date` 是預告的除權息日 |
| 上市 `TWT88U` | [11659](https://data.gov.tw/dataset/11659) | 首五日無漲跌幅的起訖日 |
| 上市 `TWTAWU` | [11677](https://data.gov.tw/dataset/11677) | 停牌與復牌日期 |
| 上市 `holidaySchedule` | [11761](https://data.gov.tw/dataset/11761) | 開休市行事曆 |
| 上櫃 `tpex_exright_prepost` | [11634](https://data.gov.tw/dataset/11634) | 預告的除權息日 |
| 上櫃 `tpex_exright_daily` | [11633](https://data.gov.tw/dataset/11633) | 除權息計算結果的生效日 |
| 上櫃 `tpex_3insti_daily_trading` | [11856](https://data.gov.tw/dataset/11856) | 三大法人買賣明細的交易日 |

## 檔案結構

- `snapshots/<交易日>/<來源>/<SHA-256>.json`：每日行情與法人交易。同一個交易日、同一份內容只存一次；來源若修訂，會多一個不同 SHA-256 的檔。
- `observations/<台灣採集日>/<來源>/<SHA-256>.json`：停復牌、除權息、首五日、行事曆。
- 每個 `.json` 旁邊有一個 `.meta.json`：來源網址、資料集、日期欄位、採集時間、HTTP 標頭、位元組數、筆數與 SHA-256。
- 檔名就是內容的 SHA-256。任何人都可以用 `sha256sum` 自行核對。

## 怎麼收

- `.github/workflows/capture.yml` 每天執行三次（台灣時間 20:40、23:40、隔天 07:40），也可以手動觸發。
- `python3 -I scripts/capture.py <空資料夾>` 只對上表的端點發 GET，不接受重導向或壓縮內容，單一回應上限 4 MiB。
- 新檔才加入，既有的檔不覆寫；同一路徑若出現不同位元組，流程會失敗而不是覆蓋。
- 任何一個端點失敗，該次執行會標示失敗，但已成功的檔仍然存檔。

## 已知限制

- GitHub 的排程可能延遲或漏跑。某個交易日若三次都沒收到，那一天就缺，補不回來。
- 上市 `TWT84U`（當日漲跌停價與開盤參考價）單檔約 12.7 MB，超過目前的大小上限，沒有收。
- 上市沒有個股三大法人的開放資料端點。
