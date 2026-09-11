@echo off
title تشغيل متصفح السحب المفتوح NSW CDP
echo ========================================================
echo  جاري تشغيل متصفح Chrome بجلسة تصحيح مخصصة لسحب الفصول
echo  المنفذ النشط: 9222
echo ========================================================
start chrome.exe --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\Google\Chrome\ScraperProfile"
