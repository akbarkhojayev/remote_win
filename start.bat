@echo off
chcp 65001 >nul
title Remote Bot - Ishga Tushirish
cd /d "%~dp0"

echo ================================================================
echo           💻 REMOTE BOT (WINDOWS) - ISHGA TUSHIRISH
echo ================================================================
echo.

:: 1. Python tekshirish
set "PYTHON_CMD="
py -3 --version >nul 2>&1
if %ERRORLEVEL% equ 0 set "PYTHON_CMD=py -3"
if "%PYTHON_CMD%"=="" python --version >nul 2>&1 && set "PYTHON_CMD=python"

if "%PYTHON_CMD%"=="" goto :no_python
goto :check_venv

:no_python
echo [XATOLIK] Kompyuterda Python topilmadi!
echo Iltimos, Python 3.10+ o'rnating: https://www.python.org/downloads/
pause
exit /b 1

:check_venv
:: 2. Virtual muhit (venv) tekshirish va yaratish
if exist "venv\Scripts\activate.bat" goto :venv_ready
echo [1/4] Python virtual muhiti yaratilmoqda...
%PYTHON_CMD% -m venv venv
call venv\Scripts\activate.bat
echo [2/4] Kerakli paketlar o'rnatilmoqda...
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt >nul 2>&1
goto :check_env

:venv_ready
echo [1/4] Muhit tekshirildi: Tayyor.

:check_env
:: 3. .env tekshirish
if exist ".env" goto :setup_autostart
if exist ".env.example" copy .env.example .env >nul
echo [DIQQAT] .env fayli yaratildi. Iltimos, BOT_TOKEN va ADMIN_ID ni to'ldiring!
notepad .env
pause
exit /b 1

:setup_autostart
:: 4. Windows Avtostartga ulash (Har doim avtomatik)
echo [2/4] Windows Avtostart sozlanmoqda...
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\RemoteBot.lnk"
set "OLD_VBS=%STARTUP_FOLDER%\start_hidden.vbs"
set "PYTHONW_EXE=%~dp0venv\Scripts\pythonw.exe"

if exist "%OLD_VBS%" del /f /q "%OLD_VBS%" >nul 2>&1
if exist "%SHORTCUT_PATH%" del /f /q "%SHORTCUT_PATH%" >nul 2>&1

powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath = '%PYTHONW_EXE%'; $s.Arguments = '\"%~dp0bot.py\"'; $s.WorkingDirectory = '%~dp0'; $s.Description = 'Remote Windows Bot'; $s.Save()" >nul 2>&1

:: 5. Ishlayotgan eski bot jarayonini to'xtatish
echo [3/4] Eski jarayonlar tekshirilmoqda...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.CommandLine -like '*bot.py*') -and ($_.Name -like 'python*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

:: 6. Botni fonda ishga tushirish
echo [4/4] Bot fonda silent ishga tushirilmoqda...
powershell -NoProfile -Command "Start-Process -FilePath '%PYTHONW_EXE%' -ArgumentList '\"%~dp0bot.py\"' -WorkingDirectory '%~dp0'" >nul 2>&1

echo.
echo ================================================================
echo  ✅ [MUVAFFAQIYATLI] Remote Bot fonda to'liq ishga tushdi!
echo ================================================================
echo   * Bot orqa fonda jimgina ishlayapti - qora oynasiz.
echo   * Kompyuter har safar yoqilganda o'zi avtomatik ishga tushadi.
echo   * Wi-Fi ulanganda Telegramingizga xabar yuboriladi.
echo.
echo Ushbu oyna 3 soniyada avtomatik yopiladi...
ping 127.0.0.1 -n 4 >nul
exit /b 0
