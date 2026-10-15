@echo off
chcp 65001 >nul
title 漫画翻译工作台
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
  echo 没有找到 venv 虚拟环境，请先按 README 安装依赖。
  pause
  exit /b 1
)
"venv\Scripts\python.exe" studio_launcher.py %*
if errorlevel 1 pause
