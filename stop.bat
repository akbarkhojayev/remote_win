@echo off
chcp 65001 >nul
title Remote Bot - To'xtatish
cd /d "%~dp0"

echo ================================================================
echo           🛑 REMOTE BOT (WINDOWS) - TO'XTATISH
echo ================================================================
echo.

echo [1/2] Ishlayotgan bot jarayonlari to'xtatilmoqda...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.CommandLine -like '*bot.py*') -and ($_.Name -like 'python*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo [2/2] Windows Avtostartdan olib tashlanmoqda...
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\RemoteBot.lnk"
set "OLD_VBS=%STARTUP_FOLDER%\start_hidden.vbs"

if exist "%SHORTCUT_PATH%" del /f /q "%SHORTCUT_PATH%" >nul 2>&1
if exist "%OLD_VBS%" del /f /q "%OLD_VBS%" >nul 2>&1

echo.
echo ================================================================
echo  🛑 [MUVAFFAQIYATLI] Bot to'liq to'xtatildi va Avtostart o'chirildi!
echo ================================================================
echo   * Fondagi barcha bot jarayonlari yopildi.
echo   * Avtomatik ishga tushish o'chirildi.
echo.
echo Ushbu oyna 3 soniyada avtomatik yopiladi...
ping 127.0.0.1 -n 4 >nul
exit /b 0
