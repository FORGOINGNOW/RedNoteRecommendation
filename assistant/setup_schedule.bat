@echo off
cd /d "%~dp0"
schtasks /Create /F /TN "XHSNicheDailyUpdate" /TR "%~dp0daily_update.bat" /SC DAILY /ST 20:30 /RL LIMITED
if errorlevel 1 (
  echo [FAIL] Register failed, please run as administrator.
) else (
  echo [OK] Daily task registered: every day 20:30, with random delay 0-45min inside.
)
pause
