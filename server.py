"""HTTP 伺服器(純 stdlib):網頁 GUI + JSON API。

API:
  GET    /api/functions            積木清單
  POST   /api/functions            新增 {name, description, content}
  PUT    /api/functions/{id}       修改
  DELETE /api/functions/{id}       刪除
  POST   /api/functions/restore    補回被刪的內建範例
  POST   /api/compose              {ids, script_name, stop_on_error, save}
                                   → {script, warnings, saved_path?}
  POST   /api/lint                 {script} → bash -n 結果
只綁 127.0.0.1,不對外。
"""
from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import composer
import storage

STATIC_DIR = Path(__file__).resolve().parent / "static"
# 輸出檔名只允許安全字元,防路徑穿越
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


class Handler(BaseHTTPRequestHandler):

    # ---- 共用小工具 ----
    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _err(self, msg, status=400):
        self._json({"error": msg}, status)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def log_message(self, fmt, *args):  # 安靜一點,只留錯誤
        pass

    # ---- 路由 ----
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            page = (STATIC_DIR / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
        elif self.path == "/api/functions":
            self._json({"functions": storage.load_functions()})
        else:
            self._err("not found", 404)

    def do_POST(self):
        if self.path == "/api/functions":
            self._create()
        elif self.path == "/api/functions/restore":
            funcs, added = storage.restore_defaults()
            self._json({"functions": funcs, "added": added})
        elif self.path == "/api/compose":
            self._compose()
        elif self.path == "/api/lint":
            self._json(composer.lint_script(self._body().get("script") or ""))
        else:
            self._err("not found", 404)

    def do_PUT(self):
        m = re.match(r"^/api/functions/([0-9a-f]{8})$", self.path)
        if not m:
            return self._err("not found", 404)
        self._update(m.group(1))

    def do_DELETE(self):
        m = re.match(r"^/api/functions/([0-9a-f]{8})$", self.path)
        if not m:
            return self._err("not found", 404)
        funcs = storage.load_functions()
        remain = [f for f in funcs if f["id"] != m.group(1)]
        if len(remain) == len(funcs):
            return self._err("找不到此積木", 404)
        storage.save_functions(remain)
        self._json({"ok": True})

    # ---- 動作 ----
    def _validate(self, d: dict, funcs: list[dict],
                  skip_id: str | None = None) -> str | None:
        err = composer.validate_name(d.get("name") or "")
        if err:
            return err
        dup = next((f for f in funcs
                    if f["name"] == d["name"] and f["id"] != skip_id), None)
        if dup:
            return f"已有同名函式「{d['name']}」,請換個名稱"
        if not (d.get("content") or "").strip():
            return "函式內容不可空白"
        return None

    def _create(self):
        d = self._body()
        funcs = storage.load_functions()
        err = self._validate(d, funcs)
        if err:
            return self._err(err)
        item = {"id": storage._new_id(), "name": d["name"].strip(),
                "description": (d.get("description") or "").strip(),
                "content": d["content"], "builtin": False}
        funcs.append(item)
        storage.save_functions(funcs)
        self._json({"ok": True, "function": item})

    def _update(self, fid: str):
        d = self._body()
        funcs = storage.load_functions()
        item = next((f for f in funcs if f["id"] == fid), None)
        if item is None:
            return self._err("找不到此積木", 404)
        err = self._validate(d, funcs, skip_id=fid)
        if err:
            return self._err(err)
        item["name"] = d["name"].strip()
        item["description"] = (d.get("description") or "").strip()
        item["content"] = d["content"]
        storage.save_functions(funcs)
        self._json({"ok": True, "function": item})

    def _compose(self):
        d = self._body()
        ids = d.get("ids") or []
        if not ids:
            return self._err("尚未加入任何積木")
        by_id = {f["id"]: f for f in storage.load_functions()}
        missing = [i for i in ids if i not in by_id]
        if missing:
            return self._err("有積木已被刪除,請從組合區移除後重試")
        name = (d.get("script_name") or "composed").strip() or "composed"
        if not _SAFE_FILENAME.match(name):
            return self._err("腳本檔名只能用英文、數字、底線、減號(1-64字)")
        script, warnings = composer.generate_script(
            [by_id[i] for i in ids], name,
            stop_on_error=bool(d.get("stop_on_error")))
        resp = {"script": script, "warnings": warnings}
        if d.get("save"):
            path = storage.OUTPUT_DIR / f"{name}.sh"
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(script)  # 固定 LF,拿到 Linux 直接可跑
            resp["saved_path"] = str(path)
        self._json(resp)


def serve(host: str, port: int):
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.serve_forever()
