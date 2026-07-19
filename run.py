"""本機啟動器:啟動伺服器並自動開啟瀏覽器(點 start.bat 即用)。

純 Python 標準庫,不需安裝任何套件。只綁 127.0.0.1 不對外。
"""
from __future__ import annotations

import threading
import time
import webbrowser

import server

HOST = "127.0.0.1"
PORT = 8010


def _open_browser():
    time.sleep(1.0)
    webbrowser.open(f"http://{HOST}:{PORT}")


if __name__ == "__main__":
    print(f"Shell Script 功能積木組合器 啟動中… http://{HOST}:{PORT}")
    print("關閉程式請在此視窗按 Ctrl+C。")
    threading.Thread(target=_open_browser, daemon=True).start()
    server.serve(HOST, PORT)
