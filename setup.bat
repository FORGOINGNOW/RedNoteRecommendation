@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 小红书赛道筛选 AI 助手 - 一键安装

echo ==============================================
echo   小红书赛道筛选 AI 助手 · 首次安装
echo ==============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [错误] 未检测到 Python，请先安装 Python 3.10 或更高版本：
  echo   1. 打开 https://www.python.org/downloads/
  echo   2. 下载安装时务必勾选 "Add Python to PATH"
  echo.
  pause
  exit /b 1
)

set MC=%~dp0..\MediaCrawler

if not exist "%MC%" (
  echo [1/3] 正在下载开源采集器 MediaCrawler（首次约 1-3 分钟）...
  git clone --depth 1 https://github.com/NanmiCoder/MediaCrawler.git "%MC%"
  if errorlevel 1 (
    echo [错误] 下载失败。若未安装 git，请到 https://git-scm.com/downloads 安装，
    echo        或手动下载 https://github.com/NanmiCoder/MediaCrawler 并解压到本目录的上一级。
    pause
    exit /b 1
  )
) else (
  echo [1/3] MediaCrawler 已存在，跳过下载
)

if not exist "%MC%\.venv\Scripts\python.exe" (
  echo [2/3] 正在创建虚拟环境并安装依赖（约 3-10 分钟，请耐心等待）...
  python -m venv "%MC%\.venv"
  "%MC%\.venv\Scripts\python.exe" -m pip install -r "%MC%\requirements.txt" --quiet
  if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
  )
) else (
  echo [2/3] 虚拟环境已存在，跳过安装
)

echo [3/3] 环境就绪，启动助手...
echo.
cd "%~dp0assistant"
python server.py
pause
