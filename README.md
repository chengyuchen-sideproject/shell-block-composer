# Shell Script Block Composer

**English** | [繁體中文](README.zh-TW.md)

Turn common shell tasks into reusable **blocks** (each block = one bash function),
then point-and-click to combine them in a web GUI and export a single `.sh`
script that runs as-is on Linux.

## Run

Double-click `start.bat` (only Python 3.10+ is required — **no packages to
install**), or run `python run.py`. Your browser opens
http://127.0.0.1:8010 automatically (bound to localhost only).

## How it works

1. **Block library** (left): ships with 4 examples (check system load, check
   SGE service, back up system config, check disk usage). Click a block to edit
   its name / description / content; "➕ New block" to add your own; deleted
   built-ins can be brought back with "↩ Restore defaults".
   - A block's content is the function *body* (no need to write `name() { }`,
     the generator wraps it). Generated script text is English.
2. **Composition area** (right): click "Add ➜" on a block; reorder / remove;
   the preview updates live. Pick one of three execution modes:
   - **Sequential (don't stop on error)**: run every block, report failures at the end
   - **Sequential (stop on error)**: stop at the first failing block
   - **Parallel**: launch each unit in the background (`&`) at the same time,
     each output redirected to its own temp file to avoid interleaving, then
     `wait` in order and collect exit codes. Parallel units are subshells:
     they can't share variables and order isn't guaranteed.
3. **SSH fan-out to a host list**: each block in the composition area has a
   "🖧 SSH list" checkbox — check it and the block's content is sent, via
   `xargs -P`, to **every machine in a host list at the same time** (great for
   hundreds/thousands of machines). The settings panel sets the list file and
   the concurrency.
   - Host list: one host per line (`user@host` allowed, `#` starts a comment).
     **Where to put it**: the default `hosts.txt` is resolved relative to the
     `.sh` file's own directory, so just put it in the same folder as the
     script; or use an absolute path. At run time you can override with
     `HOST_LIST=path SSH_PARALLEL=count bash xxx.sh`.
   - How: `declare -f` ships the block's function to the remote `bash -s`
     as-is (no need to pre-deploy a script), each host's output is printed as
     one block to avoid interleaving, and success/failure counts are tallied.
   - Prerequisite: SSH keys already set up on the targets (uses `BatchMode=yes`,
     never prompts for a password; unreachable hosts are recorded as failures).
4. **Block groups**: click "📦 New group" to create a container, drop several
   blocks in, and toggle SSH once for the **whole group**. Uses:
   - Do several things in a row on the same set of machines (e.g. "check disk →
     write log") without checking SSH on each block.
   - With SSH on, the group opens **one ssh connection per host and runs all
     member blocks sequentially on that host** (far fewer connections than
     fanning out each block separately when you have thousands of machines).
   - Without SSH, group members run sequentially **in the same shell**, so a
     variable a block `export`s can be read by a later block (e.g. a log block).
5. **Output**: download `.sh` / save to `output/` (fixed LF line endings, runs
   directly on Linux with `bash xxx.sh`) / copy / syntax check (needs the bash
   from Git for Windows).

## What an SSH fan-out script looks like

```bash
check_load() { uptime; free -h; }   # ← your block content = run on each host
__sbc_unit_0() {                    # the SSH fan-out runner for that block
    hostfile="$(__sbc_hostfile)"; par="${SSH_PARALLEL:-50}"
    export _SBC_FANOUT="$(declare -f check_load); check_load"
    grep -Ev '^\s*(#|$)' "$hostfile" \
      | xargs -r -P "$par" -n 1 -- bash -c '
          out=$(ssh -o BatchMode=yes -o ConnectTimeout=5 "$1" bash -s \
                <<<"$_SBC_FANOUT" 2>&1)
          printf "%s\n" "----- $1 -----\n$out"' _
    # …tally success/failure counts
}
```

For an SSH **group**, the exported payload is
`$(declare -f blockA blockB); blockA; blockB` — several functions in one ssh
session, run in order on each host.

## Data

- Blocks are stored in `data/functions.json` (local only)
- Generated scripts are saved under `output/`
