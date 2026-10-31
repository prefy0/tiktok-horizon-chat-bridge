@echo off
chcp 65001 > nul
cd /d "%~dp0"
set "TIKTOK_CREATOR="
set /p "TIKTOK_CREATOR=Введите TikTok username эфира, например @my_channel: "
py tiktok_horizon_bridge.py
echo.
pause