@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=E:\数据分析\MediaCrawler\.venv\Scripts\python.exe
if not exist "%PY%" (
  echo 未找到 MediaCrawler 虚拟环境，请先安装：E:\数据分析\MediaCrawler
  pause
  exit /b 1
)
"%PY%" analyze_xhs.py
pause
