@echo off
chcp 65001 >nul
title تشغيل متصفح السحب المفتوح وخادم بايثون NSW
echo ========================================================
echo  🚀 جاري تشغيل منظومة السحب وعالم سماء الروايات (NSW)
echo  1. خادم بايثون المحلي (Streamlit Port: 8501)
echo  2. متصفح Chrome بصمام أمان CDP (Port: 9222)
echo ========================================================

cd /d "C:\s"

:: 1. تشغيل خادم بايثون (Streamlit) إذا لم يكن نشطاً
netstat -ano | findstr /R /C:":8501 .*LISTENING" >nul
if %errorlevel% neq 0 (
    echo [1/2] ⏳ جاري تشغيل خادم بايثون ومحرك السحب (Port 8501)...
    start "NSW_Streamlit_Server" /min python -m streamlit run app.py --server.port 8501 --server.headless true
    timeout /t 3 /nobreak >nul
) else (
    echo [1/2] ✅ خادم بايثون نشط بالفعل على المنفذ 8501.
)

:: 2. تشغيل متصفح Chrome بجلسة الـ CDP وتوجيهه مباشرة للوحة التحكم
echo [2/2] 🌐 جاري تشغيل متصفح Chrome على المنفذ 9222...
set "CHROME_BIN=C:\Program Files\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME_BIN%" set "CHROME_BIN=chrome.exe"

start "" "%CHROME_BIN%" --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\Google\Chrome\ScraperProfile" "http://localhost:8501"

echo ========================================================
echo  🎉 تم التشغيل بنجاح!
echo  • الرابط: http://localhost:8501
echo  • منفذ الـ CDP: http://127.0.0.1:9222
echo ========================================================
timeout /t 2 /nobreak >nul
exit
