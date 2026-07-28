@echo off
chcp 65001 >nul
title 维权快速响应系统
echo ============================================
echo   维权快速响应系统 - 启动中...
echo   访问地址: http://127.0.0.1:5000
echo ============================================

cd /d "E:\WorkBuddy\2026-07-27-16-54-45\ip-protection-system"

REM 确保使用正确的 Python 环境
set PYTHON=C:\Users\LP0717\.workbuddy\binaries\python\envs\default\Scripts\python.exe

if not exist "%PYTHON%" (
    echo [错误] Python 环境未找到: %PYTHON%
    pause
    exit /b 1
)

echo [%date% %time%] 正在启动 Flask 服务...
"%PYTHON%" app.py

pause
