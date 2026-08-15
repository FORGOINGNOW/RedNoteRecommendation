@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动 Python 算法后端 (localhost:8765) ...
python server.py
pause
