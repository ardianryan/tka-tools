@echo off
title Smart TKA Scanner & Auto-Uploader
cd /d "%~dp0"
echo =======================================================
echo    SMART SCANNER & SMART UPLOAD - TKA KEMENDIKDASMEN
echo =======================================================
echo.
echo Memeriksa dependensi Python...
python -m pip install -q flask flask-cors requests pillow winocr
echo.
echo Menjalankan Smart TKA Assistant Dashboard...
start http://127.0.0.1:5000
python app.py
pause
