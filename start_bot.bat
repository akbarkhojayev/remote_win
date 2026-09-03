@echo off
title Remote Bot Windows
cd /d "%~dp0"

if not exist venv (
    echo [INFO] Python virtual muhiti yaratilmoqda...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo [INFO] Kerakli paketlar o'rnatilmoqda...
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

if not exist .env (
    echo [DIQQAT] .env fayli topilmadi!
    echo .env.example faylidan nusxa olindi. Iltimos, .env faylini ochib BOT_TOKEN va ADMIN_ID ni kiriting.
    copy .env.example .env
    pause
    exit /b
)

echo [INFO] Remote Bot ishga tushmoqda...
python bot.py
pause
