@echo off
title NSW Scraper Engine and Chrome CDP Launcher
echo ========================================================
echo  Starting NSW Novel System
echo  1. Checking and Launching Python Streamlit (Port: 8501)
echo  2. Launching Chrome with CDP Fail-Safe (Port: 9222)
echo ========================================================

cd /d "C:\s"

:: 1. Check if Streamlit port 8501 is listening
netstat -ano | findstr /R /C:":8501 .*LISTENING" >nul
if %errorlevel% neq 0 (
    echo [1/2] Starting Python Streamlit on Port 8501...
    start "NSW_Streamlit_Server" /min python -m streamlit run app.py --server.port 8501 --server.headless true
    timeout /t 3 /nobreak >nul
) else (
    echo [1/2] Streamlit is already running on Port 8501.
)

:: 2. Launch Chrome with CDP port 9222 and open localhost:8501
echo [2/2] Launching Chrome on CDP Port 9222...
set "CHROME_BIN=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME_BIN%" set "CHROME_BIN=chrome.exe"

start "" "%CHROME_BIN%" --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\Google\Chrome\ScraperProfile" "http://localhost:8501"

echo ========================================================
echo  System successfully launched!
echo  URL: http://localhost:8501
echo  CDP: http://127.0.0.1:9222
echo ========================================================
timeout /t 2 /nobreak >nul
exit
