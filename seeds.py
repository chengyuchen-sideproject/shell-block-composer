"""內建範例積木。

每個積木 = 一個 bash function 的「函式本體」(不含 name() { })。
內容針對 Linux 目標主機撰寫;產生器會自動包成 function 並依序呼叫。
誤刪可在 GUI 按「還原內建範例」補回(依名稱比對,不覆蓋使用者修改)。
"""

SEED_FUNCTIONS = [
    {
        "name": "check_system_load",
        "description": "檢查系統負載與記憶體,負載超過 CPU 核心數時警告",
        "content": """\
local cores load
cores=$(nproc 2>/dev/null || grep -c ^processor /proc/cpuinfo)
load=$(awk '{print $1}' /proc/loadavg)
echo "=== 系統負載 ==="
uptime
echo "CPU 核心數: ${cores}, 1 分鐘負載: ${load}"
awk -v l="$load" -v c="$cores" 'BEGIN { if (l+0 > c+0) print "[警告] 負載超過核心數!" }'
echo "=== 記憶體 ==="
free -h""",
    },
    {
        "name": "check_sge_service",
        "description": "檢查 SGE 服務程序(qmaster/execd)與佇列狀態",
        "content": """\
echo "=== SGE 服務檢查 ==="
local ok=1 p
for p in sge_qmaster sge_execd; do
    if pgrep -x "$p" >/dev/null 2>&1; then
        echo "[OK] $p 執行中"
    else
        echo "[異常] $p 未執行"
        ok=0
    fi
done
if command -v qstat >/dev/null 2>&1; then
    echo "--- 佇列摘要 (qstat -g c) ---"
    qstat -g c 2>&1 | head -20
else
    echo "[提示] 找不到 qstat 指令(SGE 環境變數未載入?)"
fi
[ "$ok" -eq 1 ]""",
    },
    {
        "name": "backup_system_config",
        "description": "備份常用系統設定檔(可用 BACKUP_DIR 覆寫目的地)",
        "content": """\
local dest="${BACKUP_DIR:-/tmp/config-backup}"
local stamp out
stamp=$(date +%Y%m%d-%H%M%S)
mkdir -p "$dest"
out="$dest/config-$stamp.tar.gz"
tar -czf "$out" \\
    /etc/hosts /etc/fstab /etc/passwd /etc/group /etc/crontab 2>/dev/null || true
echo "[OK] 設定檔已備份到 $out"
ls -lh "$out\"""",
    },
    {
        "name": "check_disk_usage",
        "description": "檢查各掛載點磁碟使用率,超過門檻(預設 85%)列警告",
        "content": """\
local limit="${DISK_LIMIT:-85}"
echo "=== 磁碟使用率(警告門檻 ${limit}%) ==="
# 用 NF 相對欄位:裝置路徑含空格時固定欄位會位移($(NF-1)=使用率, $NF=掛載點)
df -hP | awk -v l="$limit" 'NR>1 {
    p=$(NF-1); gsub("%","",p)
    mark=(p+0>=l+0) ? "  <== 警告" : ""
    printf "%-30s %4s%%%s\\n", $NF, p, mark
}'""",
    },
]
