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
echo.
echo ===== 算法契合度分析 =====
"%PY%" analyze_fit.py
echo.
echo ===== 帖子生命周期分析 =====
"%PY%" analyze_lifecycle.py
echo.
echo ===== 选题对比分析 =====
"%PY%" analyze_compare.py --data-dir "E:\数据分析\MediaCrawler\data\xhs\jsonl" --my-keywords "英文学习,AI" --out-dir "%~dp0report"
pause
