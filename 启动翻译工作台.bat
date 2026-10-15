@echo off
chcp 65001 >nul
title 漫画翻译工作台
cd /d "%~dp0"
set "PY=venv\Scripts\python.exe"
if not exist "%PY%" if exist ".venv-path" set /p VENVDIR=<".venv-path"
if not exist "%PY%" if defined VENVDIR set "PY=%VENVDIR%\Scripts\python.exe"
if not exist "%PY%" (
  echo 没有找到 Python 运行环境。
  echo 请把虚拟环境放在项目的 venv 文件夹，或在 .venv-path 文件里写上它的路径。
  pause
  exit /b 1
)
"%PY%" studio_launcher.py %*
if errorlevel 1 pause
