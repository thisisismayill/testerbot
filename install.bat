@echo off
REM TesterBot qurasdirma (Windows)
cd /d "%~dp0"
echo Python paketleri qurasdirilir...
python -m pip install -r requirements.txt
echo Chromium brauzeri yuklenir (bir defelik, ~150 MB)...
python -m playwright install chromium
echo.
echo Hazirdir. Istifade:
echo    python tester_bot.py https://sizin-sayt.az
pause
