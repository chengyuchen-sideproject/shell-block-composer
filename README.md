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
   預覽即時更新。執行方式三選一:
   - **依序執行(失敗不中斷)**:逐塊跑完,結尾回報失敗清單
   - **依序執行(失敗即中止)**:任一積木失敗就停
   - **並行執行**:每塊丟背景(`&`)同時跑、輸出各自導暫存檔避免交錯,
     再依序 `wait` 收斂、逐塊印出與收集結束碼。適合互不相依的檢查類積木;
     並行是子 shell,積木間不能共享變數、不保證先後順序。
3. **SSH 機器清單並行**:組合區每塊積木可勾「🖧 SSH清單」——勾了之後,
   該積木的內容會透過 `xargs -P` **同時 SSH 到機器清單上的每一台機器執行**
   (適合幾百~幾千台批次巡檢/操作)。設定區可指定清單檔與同時連線數。
   - 機器清單:一行一台(可 `user@host`,`#` 開頭是註解),
     執行時可用 `HOST_LIST=路徑 SSH_PARALLEL=數量 bash xxx.sh` 覆寫預設
   - 原理:`declare -f` 把積木內容原樣送到遠端 `bash -s` 執行(免先佈腳本),
     每台輸出各自成塊避免交錯,結束後統計成功/失敗台數
   - 前提:目標機已佈好 SSH 金鑰(用 `BatchMode=yes` 不問密碼,連不上記失敗)
4. **輸出**:下載 .sh / 存到 `output/`(固定 LF 換行,拿到 Linux 直接
   `bash xxx.sh` 可跑)/ 複製 / 語法檢查(需 Git for Windows 的 bash)。

## SSH fan-out 產生的腳本長怎樣

```bash
check_load__task() { uptime; free -h; }   # ← 你的積木內容 = 送到每台機器執行
check_load() {
    hostfile="${HOST_LIST:-hosts.txt}"; par="${SSH_PARALLEL:-50}"
    export _FANOUT_CMD="$(declare -f check_load__task); check_load__task"
    grep -Ev '^\s*(#|$)' "$hostfile" \
      | xargs -r -P "$par" -n 1 -- bash -c '
          out=$(ssh -o BatchMode=yes -o ConnectTimeout=5 "$1" bash -s \
                <<<"$_FANOUT_CMD" 2>&1)
          printf "%s\n" "───── $1 ─────\n$out"' _
    # …統計成功/失敗台數
}
```

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
