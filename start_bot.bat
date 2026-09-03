@echo off
title Remote Bot Windows
cd /d "%~dp0"

:: Python buyrug'ini aniqlash
set PYTHON_CMD=
py -3 --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set PYTHON_CMD=py -3
) else (
    python --version >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        set PYTHON_CMD=python
    )
)

if "%PYTHON_CMD%"=="" (
    echo [XATOLIK] Kompyuteringizda Python topilmadi!
    echo Iltimos, Python 3.10+ o'rnating va PATH ga qo'shing: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Virtual muhitni tekshirish va yaratish
if not exist "venv\Scripts\activate.bat" (
    echo [INFO] Python virtual muhiti yaratilmoqda...
    %PYTHON_CMD% -m venv venv
    call venv\Scripts\activate.bat
    echo [INFO] Kerakli paketlar o'rnatilmoqda...
    python -m pip install --upgrade pip
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

:: .env faylini tekshirish
if not exist ".env" (
    echo [DIQQAT] .env fayli topilmadi!
    if exist ".env.example" (
        copy .env.example .env
        echo .env.example faylidan nusxa olindi.
    )
    echo Iltimos, .env faylini ochib BOT_TOKEN va ADMIN_ID ni to'ldiring!
    pause
    exit /b 1
)

echo [INFO] Remote Bot ishga tushmoqda...
python bot.py
if %ERRORLEVEL% neq 0 (
    echo [XATOLIK] Bot to'xtadi yoki xatolik yuz berdi.
    pause
)
