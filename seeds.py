"""內建範例積木。

每個積木 = 一個 bash function 的「函式本體」(不含 name() { })。
內容針對 Linux 目標主機撰寫;產生器會自動包成 function 並依序呼叫。
誤刪可在 GUI 按「還原內建範例」補回(依名稱比對,不覆蓋使用者修改)。

說明與內容一律用英文,因為它們會被寫進產生的 .sh 腳本裡。
"""

SEED_FUNCTIONS = [
    {
        "name": "check_system_load",
        "description": "Check system load and memory; warn when load exceeds CPU cores",
        "content": """\
local cores load
cores=$(nproc 2>/dev/null || grep -c ^processor /proc/cpuinfo)
load=$(awk '{print $1}' /proc/loadavg)
echo "=== System load ==="
uptime
echo "CPU cores: ${cores}, 1-min load: ${load}"
awk -v l="$load" -v c="$cores" 'BEGIN { if (l+0 > c+0) print "[WARN] load exceeds core count!" }'
echo "=== Memory ==="
free -h""",
    },
    {
        "name": "check_sge_service",
        "description": "Check SGE daemons (qmaster/execd) and queue status",
        "content": """\
echo "=== SGE service check ==="
local ok=1 p
for p in sge_qmaster sge_execd; do
    if pgrep -x "$p" >/dev/null 2>&1; then
        echo "[OK] $p is running"
    else
        echo "[FAIL] $p is not running"
        ok=0
    fi
done
if command -v qstat >/dev/null 2>&1; then
    echo "--- queue summary (qstat -g c) ---"
    qstat -g c 2>&1 | head -20
else
    echo "[NOTE] qstat not found (SGE environment not sourced?)"
fi
[ "$ok" -eq 1 ]""",
    },
    {
        "name": "backup_system_config",
        "description": "Back up common system config files (override dest with BACKUP_DIR)",
        "content": """\
local dest="${BACKUP_DIR:-/tmp/config-backup}"
local stamp out
stamp=$(date +%Y%m%d-%H%M%S)
mkdir -p "$dest"
out="$dest/config-$stamp.tar.gz"
tar -czf "$out" \\
    /etc/hosts /etc/fstab /etc/passwd /etc/group /etc/crontab 2>/dev/null || true
echo "[OK] config backed up to $out"
ls -lh "$out\"""",
    },
    {
        "name": "check_disk_usage",
        "description": "Check disk usage per mount; warn when above threshold (default 85%)",
        "content": """\
local limit="${DISK_LIMIT:-85}"
echo "=== Disk usage (warn threshold ${limit}%) ==="
# Use NF-relative columns: a device path with spaces would shift fixed columns
df -hP | awk -v l="$limit" 'NR>1 {
    p=$(NF-1); gsub("%","",p)
    mark=(p+0>=l+0) ? "  <== WARNING" : ""
    printf "%-30s %4s%%%s\\n", $NF, p, mark
}'""",
    },
]
