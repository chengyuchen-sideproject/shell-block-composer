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


def _hostfile_helper(host_list: str) -> list[str]:
    """共用:解析機器清單路徑。相對路徑以「腳本所在目錄」為基準
    (放在 .sh 同資料夾即可),絕對路徑或 HOST_LIST 覆寫則照用。"""
    return [
        "# Resolve host list path: relative paths are based on this script's directory",
        "__sbc_hostfile() {",
        f'    local hf="${{HOST_LIST:-{host_list}}}"',
        '    if [[ "$hf" != /* ]]; then',
        '        local d; d="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"',
        '        hf="$d/$hf"',
        "    fi",
        "    printf '%s' \"$hf\"",
        "}",
        "",
    ]


def _fanout_runner(runner: str, label: str, member_names: list[str],
                   parallel: int) -> list[str]:
    """產生一個 fan-out 執行函式:把 member_names 這些 function 用 declare -f
    送到清單每台機器,在遠端依序執行(rc 任一失敗即為失敗),xargs -P 控併發。

    - 單一積木:member_names 只有一個
    - 群組:member_names 為組內多個積木,遠端同一條 ssh 內依序跑完
    """
    declare_names = " ".join(member_names)
    calls = ("rc=0; " + "; ".join(f"{n} || rc=1" for n in member_names)
             + "; exit \\$rc")
    return [
        f"{runner}() {{",
        "    local hostfile par total tmp fails",
        '    hostfile="$(__sbc_hostfile)"',
        f'    par="${{SSH_PARALLEL:-{parallel}}}"',
        '    if [ ! -r "$hostfile" ]; then',
        '        echo "[ERROR] cannot read host list $hostfile (one host per line, '
        'user@host allowed; put it next to the script or override with HOST_LIST=path)" >&2',
        "        return 1",
        "    fi",
        "    total=$(grep -cEv '^[[:space:]]*(#|$)' \"$hostfile\")",
        f'    echo "=== {label}: running on $total host(s) in parallel '
        '(max concurrency $par) ==="',
        f'    export _SBC_FANOUT="$(declare -f {declare_names}); {calls}"',
        "    tmp=$(mktemp)",
        "    grep -Ev '^[[:space:]]*(#|$)' \"$hostfile\" \\",
        '        | xargs -r -P "$par" -n 1 -- bash -c \'',
        "            h=$1",
        '            out=$(ssh -o BatchMode=yes -o ConnectTimeout=5 "$h" bash -s \\',
        '                  <<<"$_SBC_FANOUT" 2>&1); rc=$?',
        '            if [ "$rc" -eq 0 ]; then tag="[OK]"; else tag="[FAIL rc=$rc]"; fi',
        '            printf "%s\\n" "───── $h $tag ─────',
        '$out"',
        "        ' _ | tee \"$tmp\"",
        '    fails=$(grep -c "^───── .* \\[FAIL" "$tmp"); rm -f "$tmp"',
        f'    echo "[SUMMARY] {label}: $((total - fails))/$total OK, $fails failed"',
        '    [ "$fails" -eq 0 ]',
        "}",
    ]


def _local_group(gname: str, member_names: list[str]) -> list[str]:
    """本機群組:組內積木在同一個 shell 依序執行(可共享 export 的變數),
    任一失敗整組視為失敗但仍跑完其餘。"""
    lines = [
        f"{gname}() {{",
        "    local __grc=0",
        f'    echo "=== group {gname}: running {len(member_names)} block(s) '
        'in sequence ==="',
    ]
    for n in member_names:
        lines.append(f"    {n} || __grc=1")
    lines += ["    return $__grc", "}"]
    return lines


def _normalize_units(items: list[dict]) -> list[dict]:
    """把輸入正規化成 units。相容舊格式(純 func dict,帶 ssh_fanout)。"""
    units = []
    for it in items:
        if it.get("kind") in ("block", "group"):
            units.append(it)
        else:  # 舊格式:一個 func dict = 一個 block unit
            units.append({"kind": "block", "func": it,
                          "ssh": bool(it.get("ssh_fanout"))})
    return units


def generate_script(items: list[dict], script_name: str = "composed",
                    mode: str = "sequential", host_list: str = "hosts.txt",
                    ssh_parallel: int = 50) -> tuple[str, list[str]]:
    """組出完整腳本。回傳(腳本文字, 警告清單)。

    items 每項為一個「單元」:
      block:{"kind":"block","func":{name,description,content},"ssh":bool}
      group:{"kind":"group","name","ssh":bool,
             "members":[{name,description,content}...]}
    也相容舊格式(純 func dict,帶 ssh_fanout)。
    ssh=True 的單元(積木或群組)改用 SSH fan-out:內容送到機器清單每台執行;
    群組 SSH 時整組在遠端同一條 ssh 內依序跑完。
    host_list / ssh_parallel 是寫進腳本的預設值,可用 HOST_LIST / SSH_PARALLEL 覆寫。

    mode:sequential(失敗不中斷)/ stop_on_error(失敗即中止)/ parallel(單元間並行)。
    """
    units = _normalize_units(items)
    warnings: list[str] = []

    # 蒐集所有要定義的積木(標準積木 + 群組成員),依名稱去重(名稱在庫中唯一)
    block_defs: dict[str, dict] = {}
    invoke_count: dict[str, int] = {}
    for u in units:
        members = ([u["func"]] if u["kind"] == "block" else u["members"])
        for f in members:
            block_defs.setdefault(f["name"], f)
            invoke_count[f["name"]] = invoke_count.get(f["name"], 0) + 1
    for name, c in invoke_count.items():
        if c > 1:
            warnings.append(f"積木「{name}」被多個單元使用,執行時會各跑一次")

    any_ssh = any(u["ssh"] for u in units)
    ssh_unit_count = sum(1 for u in units if u["ssh"])
    if mode == "parallel" and ssh_unit_count > 1:
        warnings.append(
            "多個 SSH 單元又選整體並行:同時連線數最高可達"
            "「SSH 單元數×SSH_PARALLEL」,請留意本機與網路負載")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out = [
        "#!/usr/bin/env bash",
        f"# {script_name}.sh — generated by Shell Script Block Composer ({now})",
        "# Each feature is a standalone function and can be reused individually.",
        "set -u",
        "",
    ]
    if any_ssh:
        out.extend(_hostfile_helper(host_list))

    # 1) 所有積木函式定義(每個唯一名稱定義一次)
    for name, f in block_defs.items():
        desc = (f.get("description") or "").replace("\n", " ")
        out.append(f"# -- {name}: {desc}")
        out.append(f"{name}() {{")
        out.append(_indent(f["content"]))
        out.append("}")
        out.append("")

    # 2) 各單元的執行函式(fan-out runner / 本機群組),並記錄 main 要呼叫的 (call,label)
    calls: list[tuple[str, str]] = []
    for i, u in enumerate(units):
        if u["kind"] == "block":
            name = u["func"]["name"]
            if u["ssh"]:
                runner = f"__sbc_unit_{i}"
                out.append(f"# -- {name} (SSH fan-out to host list)")
                out.extend(_fanout_runner(runner, name, [name], ssh_parallel))
                out.append("")
                calls.append((runner, name))
            else:
                calls.append((name, name))  # 直接呼叫已定義的積木
        else:  # group
            gname = u["name"]
            member_names = [m["name"] for m in u["members"]]
            if u["ssh"]:
                out.append(f"# == group {gname} (SSH fan-out; run member blocks "
                           "sequentially on each host)")
                out.extend(_fanout_runner(gname, gname, member_names, ssh_parallel))
            else:
                out.append(f"# == group {gname} (run member blocks sequentially, "
                           "locally)")
                out.extend(_local_group(gname, member_names))
            out.append("")
            calls.append((gname, gname))

    report = [
        '    echo ""',
        '    if [ "${#failed[@]}" -gt 0 ]; then',
        '        echo "[RESULT] failed: ${failed[*]}" >&2',
        "        return 1",
        "    fi",
        '    echo "[RESULT] all done"',
    ]

    out.append('main() {')
    if mode == "stop_on_error":
        for call, label in calls:
            out.append(f"    {call} || {{ echo \"[ABORT] {label} failed\" >&2; return 1; }}")
    elif mode == "parallel":
        out.append("    local tmpdir")
        out.append('    tmpdir=$(mktemp -d) || { echo "[ERROR] failed to create temp dir" >&2; return 1; }')
        out.append("    local pids=() names=()")
        out.append("")
        out.append("    # Launch each unit in background; redirect output to its own temp file to avoid interleaving")
        for i, (call, label) in enumerate(calls):
            out.append(f'    {call} > "$tmpdir/{i:02d}.log" 2>&1 &')
            out.append(f'    pids+=($!); names+=("{label}")')
        out.append("")
        out.append("    # Wait in launch order, collect each exit code and print its output")
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
        for call, label in calls:
            out.append(f"    {call} || failed+=(\"{label}\")")
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
