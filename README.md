# Shell Script 功能積木組合器

把常用的 shell 功能做成「積木」(每塊 = 一個 bash function),在網頁 GUI 上
點選組合、即時預覽,輸出一支可直接在 Linux 執行的 `.sh` 腳本。

## 啟動

雙擊 `start.bat`(只需要 Python 3.10+,**不用安裝任何套件**),
或 `python run.py`。瀏覽器會自動開 http://127.0.0.1:8010(只綁本機)。

## 使用方式

1. **積木庫**(左):內建 4 個範例(檢查系統負載、檢查 SGE 服務、
   備份系統設定檔、檢查磁碟使用率)。點積木可編輯名稱/說明/內容,
   「➕ 新增積木」加自己的;內建範例誤刪可「↩ 還原」。
   - 積木內容 = function 本體(不用寫 `name() { }`,產生器會包)
2. **組合區**(右):按積木上的「加入 ➜」,可上下排序、移除;
   預覽即時更新。勾「任一積木失敗即中止」改變 main 的串接方式。
3. **輸出**:下載 .sh / 存到 `output/`(固定 LF 換行,拿到 Linux 直接
   `bash xxx.sh` 可跑)/ 複製 / 語法檢查(需 Git for Windows 的 bash)。

## 產出腳本結構

```bash
#!/usr/bin/env bash
set -u
check_system_load() { ... }   # 各積木 = 獨立 function,可單獨 source 取用
...
main() {                      # 依組合順序執行,結尾回報失敗清單
    check_system_load || failed+=("check_system_load")
    ...
}
main "$@"
```

## 資料

- 積木存 `data/functions.json`(僅本機)
- 產出腳本存 `output/`
