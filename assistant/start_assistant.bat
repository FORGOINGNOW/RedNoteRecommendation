@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动小红书赛道筛选 AI 助手 (http://localhost:8787) ...
python server.py
pause
