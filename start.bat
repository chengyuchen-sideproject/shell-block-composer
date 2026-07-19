@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [錯誤] 找不到 python，請先安裝 Python 3.10+ 並勾選 Add to PATH。
  pause
  exit /b 1
)

echo 啟動中… 瀏覽器會自動開啟 http://127.0.0.1:8010 （關閉請按 Ctrl+C）
python run.py

pause
