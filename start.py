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
    """تشغيل بوت تليجرام في process مستقل مع إعادة التشغيل التلقائي عند أي توقف."""
    while True:
        try:
            print("[Launcher] Starting Telegram Bot loop...")
            subprocess.run(
                [sys.executable, "telegram_bot.py"],
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
        except Exception as e:
            print(f"[Launcher] Telegram Bot error: {e}")
        time.sleep(3)

def run_local_api():
    """تشغيل خادم الربط المحلي الفائق على بورت 58242."""
    print("[Launcher] Starting NSW Local Web Bridge API (Port 58242)...")
    subprocess.run(
        [sys.executable, "local_nsw_api.py"],
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

    # تشغيل البوت في خيط خلفي مع وسم منع الازدواجية
    os.environ["NSW_BOT_RUNNER"] = "start_py"
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True, name="TelegramBot")
    bot_thread.start()
    print("[Launcher] Telegram Bot thread started.")

    # تشغيل خادم الربط المحلي الفائق في خيط خلفي
    api_thread = threading.Thread(target=run_local_api, daemon=True, name="LocalWebBridge")
    api_thread.start()
    print("[Launcher] NSW Local Web Bridge API thread started on port 58242.")

    # تشغيل محرك النشر التلقائي الذاتي 24/7 (نادي الروايات + واتباد)
    try:
        import syndication_daemon
        syndication_daemon.start_syndication_daemon()
    except Exception as e_daemon:
        print(f"[Launcher] ⚠️ Could not start syndication daemon: {e_daemon}")

    # تم إلغاء إشعار الإقلاع التلقائي لمنع الإزعاج عند إعادة إقلاع سيرفر Render الدوري
    # Notification is disabled to ensure 100% silent startup

    # انتظار ثانيتين ثم تشغيل Streamlit
    time.sleep(2)
    run_streamlit()
