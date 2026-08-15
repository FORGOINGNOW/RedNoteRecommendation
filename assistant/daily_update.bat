@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 手动运行每日更新（含随机延迟 0-45 分钟）
echo 测试可运行: python daily_update.py --now
python daily_update.py
pause
