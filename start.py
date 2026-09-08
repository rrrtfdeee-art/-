# -*- coding: utf-8 -*-
"""
start.py — تشغيل موحد: بوت تليجرام + واجهة Streamlit
شغّله مرة واحدة بـ: python start.py
"""
import sys
import subprocess
import threading
import time
import os

def run_telegram_bot():
    """تشغيل بوت تليجرام في process مستقل."""
    print("[Launcher] Starting Telegram Bot...")
    subprocess.run(
        [sys.executable, "telegram_bot.py"],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )

def run_streamlit():
    """تشغيل واجهة Streamlit."""
    print("[Launcher] Starting Streamlit App on port 8501...")
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.port", "8501",
         "--server.address", "0.0.0.0",
         "--server.headless", "true"],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )

if __name__ == "__main__":
    print("=" * 50)
    print("  NSW System Launcher v2.0")
    print("  Telegram Bot + Streamlit UI")
    print("=" * 50)

    # تشغيل البوت في خيط خلفي
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True, name="TelegramBot")
    bot_thread.start()
    print("[Launcher] Telegram Bot thread started.")

    # إشعار الإقلاع التلقائي في الخلفية
    def _startup_notify():
        try:
            time.sleep(5)
            from nsw_healer_engine import notify_admin
            notify_admin("🖥️ <b>[إقلاع خط الإنتاج]:</b>\nتم تشغيل المنظومة بنجاح.\n• المزامنة المزدوجة للشيتين: <b>مفعلة</b>.\n• ربط أزرار التنقل التلقائي: <b>مفعل</b>.\n• كشف الفجوات المفردة: <b>مفعل</b>.\n• جاهز لاستقبال وصقل فصول <b>Claude Opus</b> (أمر: <code>/nsw_stage</code>).")
        except Exception:
            pass
    threading.Thread(target=_startup_notify, daemon=True).start()

    # انتظار ثانيتين ثم تشغيل Streamlit
    time.sleep(2)
    run_streamlit()
