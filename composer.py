"""腳本產生器:把選取的積木(function 本體)組成完整 bash 腳本。

輸出固定 LF 換行、UTF-8;結構:
  shebang / 產生資訊 → set -u → 各 function 定義 → main() 依序呼叫 → main "$@"
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

# bash 合法函式名稱(也擋掉空白/中文/減號,避免產出壞腳本)
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# 常見 shell 保留字/內建,不宜當函式名
_RESERVED = {"if", "then", "else", "elif", "fi", "for", "while", "until", "do",
             "done", "case", "esac", "function", "select", "time", "in",
             "main", "test", "echo", "cd", "read", "set", "local", "return"}


def validate_name(name: str) -> str | None:
    """名稱不合法時回傳錯誤訊息,合法回 None。"""
    if not name:
        return "函式名稱不可空白"
    if not NAME_RE.match(name):
        return "函式名稱只能用英文字母、數字、底線,且不能以數字開頭"
    if name in _RESERVED:
        return f"「{name}」是 shell 保留字/常用內建指令,請換個名稱"
    return None


def _indent(body: str) -> str:
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(("    " + ln) if ln.strip() else "" for ln in lines)


def _fanout_lines(f: dict, host_list: str, parallel: int) -> list[str]:
    """SSH 機器清單並行版:積木內容包成 <name>__task(),
    <name>() 用 xargs -P 對清單每台機器 ssh 執行 payload、逐台收斂結果。

    - declare -f 把 payload 原樣送到遠端 bash -s 執行,不必先佈腳本到各機
    - 每台輸出組成一塊、單次 printf,避免上千台同時列印交錯
    - 結果 tee 到暫存檔即時顯示,結束後統計 [FAIL] 數決定結束碼
    """
    name = f["name"]
    return [
        f"{name}__task() {{  # 會在清單中每台機器上執行的內容",
        _indent(f["content"]),
        "}",
        f"{name}() {{",
        f'    local hostfile="${{HOST_LIST:-{host_list}}}"',
        f'    local par="${{SSH_PARALLEL:-{parallel}}}"',
        '    if [ ! -r "$hostfile" ]; then',
        '        echo "[錯誤] 讀不到機器清單 $hostfile(一行一台,可 user@host;'
        'HOST_LIST=路徑 可覆寫)" >&2',
        "        return 1",
        "    fi",
        "    local total tmp fails",
        "    total=$(grep -cEv '^[[:space:]]*(#|$)' \"$hostfile\")",
        f'    echo "=== {name}:對 $total 台機器並行執行(同時上限 $par)==="',
        f'    export _FANOUT_CMD="$(declare -f {name}__task); {name}__task"',
        "    tmp=$(mktemp)",
        "    grep -Ev '^[[:space:]]*(#|$)' \"$hostfile\" \\",
        '        | xargs -r -P "$par" -n 1 -- bash -c \'',
        "            h=$1",
        '            out=$(ssh -o BatchMode=yes -o ConnectTimeout=5 "$h" bash -s \\',
        '                  <<<"$_FANOUT_CMD" 2>&1); rc=$?',
        '            if [ "$rc" -eq 0 ]; then tag="[OK]"; else tag="[FAIL rc=$rc]"; fi',
        '            printf "%s\\n" "───── $h $tag ─────',
        '$out"',
        "        ' _ | tee \"$tmp\"",
        '    fails=$(grep -c "^───── .* \\[FAIL" "$tmp"); rm -f "$tmp"',
        '    echo "[小結] '
        f'{name}: $((total - fails))/$total 成功, $fails 失敗"',
        '    [ "$fails" -eq 0 ]',
        "}",
    ]


def generate_script(funcs: list[dict], script_name: str = "composed",
                    mode: str = "sequential", host_list: str = "hosts.txt",
                    ssh_parallel: int = 50) -> tuple[str, list[str]]:
    """組出完整腳本。回傳(腳本文字, 警告清單)。

    funcs 每項可帶 "ssh_fanout": True → 該積木改為「SSH 機器清單並行版」:
    內容在清單中每台機器上執行(xargs -P 控併發),而非本機執行。
    host_list / ssh_parallel 是寫進腳本的預設值,執行時可用
    HOST_LIST / SSH_PARALLEL 環境變數覆寫。

    mode:
      sequential    依序執行,失敗不中斷,最後回報失敗清單(預設)
      stop_on_error 依序執行,任一積木失敗即中止
      parallel      並行執行:每塊丟背景(&)同時跑,輸出各自導暫存檔避免交錯,
                    再依啟動順序 wait 收斂、逐塊印出與收集結束碼。
                    注意:並行是子 shell,積木間不能共享變數、不保證先後。
    """
    warnings: list[str] = []
    seen: set[str] = set()
    for f in funcs:
        if f["name"] in seen:
            warnings.append(f"函式「{f['name']}」重複加入,後者定義會覆蓋前者")
        seen.add(f["name"])
    if mode == "parallel" and sum(1 for f in funcs if f.get("ssh_fanout")) > 1:
        warnings.append(
            "多個 SSH 並行積木又選整體並行模式:同時連線數最高可達"
            "「積木數×SSH_PARALLEL」,請留意本機與網路負載")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out = [
        "#!/usr/bin/env bash",
        f"# {script_name}.sh — 由 Shell Script 功能積木組合器產生({now})",
        ("# 各功能為獨立 function,可單獨取用;整支執行則「並行」全跑。"
         if mode == "parallel" else
         "# 各功能為獨立 function,可單獨取用;整支執行則依序全跑。"),
        "set -u",
        "",
    ]
    for f in funcs:
        desc = (f.get("description") or "").replace("\n", " ")
        if f.get("ssh_fanout"):
            out.append(f"# ── {f['name']}(SSH 機器清單並行):{desc}")
            out.extend(_fanout_lines(f, host_list, ssh_parallel))
        else:
            out.append(f"# ── {f['name']}:{desc}")
            out.append(f"{f['name']}() {{")
            out.append(_indent(f["content"]))
            out.append("}")
        out.append("")

    report = [  # 結尾共用:回報失敗清單(sequential / parallel 共用)
        '    echo ""',
        '    if [ "${#failed[@]}" -gt 0 ]; then',
        '        echo "[結果] 失敗項目: ${failed[*]}" >&2',
        "        return 1",
        "    fi",
        '    echo "[結果] 全部完成"',
    ]

    out.append('main() {')
    if mode == "stop_on_error":
        for f in funcs:
            out.append(f"    {f['name']} || {{ echo \"[中止] {f['name']} 失敗\" >&2; return 1; }}")
    elif mode == "parallel":
        out.append("    local tmpdir")
        out.append('    tmpdir=$(mktemp -d) || { echo "[錯誤] 無法建立暫存目錄" >&2; return 1; }')
        out.append("    local pids=() names=()")
        out.append("")
        out.append("    # 每塊丟背景同時跑;輸出導到各自的暫存檔,避免交錯")
        for i, f in enumerate(funcs):
            out.append(f'    {f["name"]} > "$tmpdir/{i:02d}.log" 2>&1 &')
            out.append(f'    pids+=($!); names+=("{f["name"]}")')
        out.append("")
        out.append("    # 依啟動順序等待,逐塊取回結束碼並印出輸出")
        out.append("    local failed=() i rc")
        out.append('    for i in "${!pids[@]}"; do')
        out.append('        rc=0; wait "${pids[$i]}" || rc=$?')
        out.append('        printf \'───── %s (exit=%s) ─────\\n\' "${names[$i]}" "$rc"')
        out.append('        cat "$(printf \'%s/%02d.log\' "$tmpdir" "$i")"')
        out.append('        if [ "$rc" -ne 0 ]; then failed+=("${names[$i]}"); fi')
        out.append("    done")
        out.append('    rm -rf "$tmpdir"')
        out.extend(report)
    else:
        out.append("    local failed=()")
        for f in funcs:
            out.append(f"    {f['name']} || failed+=(\"{f['name']}\")")
        out.extend(report)
    out.append("}")
    out.append("")
    out.append('main "$@"')
    return "\n".join(out) + "\n", warnings


def find_bash() -> str | None:
    """找可用的 bash(供語法檢查)。Windows 上優先 Git Bash。"""
    p = shutil.which("bash")
    if p:
        return p
    for cand in (r"C:\Program Files\Git\bin\bash.exe",
                 r"C:\Program Files\Git\usr\bin\bash.exe"):
        if Path(cand).exists():
            return cand
    return None


def lint_script(script: str) -> dict:
    """bash -n 語法檢查。回 {available, ok, output}。"""
    bash = find_bash()
    if not bash:
        return {"available": False, "ok": None,
                "output": "找不到 bash(裝 Git for Windows 即可用語法檢查)"}
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False,
                                     encoding="utf-8", newline="\n") as f:
        f.write(script)
        tmp = f.name
    try:
        r = subprocess.run([bash, "-n", tmp], capture_output=True,
                           text=True, timeout=15)
        return {"available": True, "ok": r.returncode == 0,
                "output": (r.stderr or r.stdout or "").replace(tmp, "script.sh").strip()
                          or "語法正確"}
    except Exception as e:  # noqa: BLE001
        return {"available": True, "ok": None, "output": f"檢查失敗:{e}"}
    finally:
        Path(tmp).unlink(missing_ok=True)
