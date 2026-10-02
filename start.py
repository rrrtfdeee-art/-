# -*- coding: utf-8 -*-
"""
start.py — المشغل الموحد لخدمة النشر وتيليجرام وواجهة Streamlit (NSW Publisher Service v3.0)
المميزات:
1. واجهة Streamlit كاملة وتفاعلية لإدارة نشر الروايات عبر المتصفح والموبايل.
2. خفيف جداً (<110MB RAM) — خالي تماماً من أي متصفحات ثقيلة (Chromium/Playwright).
3. يشغل بوت تيليجرام ومحرك النشر المجدول 24/7 بالتوازي في خيوط خلفية.
4. يربط Streamlit على المنفذ المطلوب بواسطة Render ($PORT).
"""

import os
import sys
import time
import logging
import threading
import subprocess

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("NSWPublisherLauncher")

PORT = os.getenv("PORT", "8501")

def run_telegram_bot_thread():
    """تشغيل بوت تيليجرام في خيط خلفي مع إعادة المحاولة التلقائية عند الانقطاع."""
    while True:
        try:
            logger.info("🤖 Starting Telegram Bot polling loop...")
            import telegram_bot
            if hasattr(telegram_bot, 'run_telegram_bot_loop'):
                telegram_bot.run_telegram_bot_loop()
            elif hasattr(telegram_bot, 'bot') and telegram_bot.bot:
                telegram_bot.bot.infinity_polling(timeout=20, long_polling_timeout=15)
        except Exception as e:
            logger.error(f"Telegram Bot error: {e}")
        time.sleep(5)

def run_syndication_daemon_thread():
    """تشغيل محرك النشر التلقائي الذاتي في خيط خلفي."""
    try:
        import syndication_daemon
        syndication_daemon.start_syndication_daemon()
        logger.info("✅ Syndication Daemon background thread active.")
    except Exception as e:
        logger.error(f"⚠️ Could not start syndication daemon: {e}")

def run_streamlit():
    """تشغيل واجهة Streamlit التفاعلية للنشر على منفذ Render."""
    logger.info(f"🌐 Launching Streamlit Publisher UI on port {PORT}...")
    cmd = [
        sys.executable, "-m", "streamlit", "run", "app.py",
        "--server.port", str(PORT),
        "--server.address", "0.0.0.0",
        "--server.headless", "true",
        "--server.enableCORS", "false",
        "--server.enableXsrfProtection", "false"
    ]
    subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    print("=" * 60)
    print("  🚀 NSW Cloud Publisher & Syndication Studio v3.0")
    print("  Telegram Bot + Autonomous Publisher + Streamlit UI")
    print("=" * 60)

    # 1. فحص إعدادات قاعدة البيانات Supabase
    try:
        import supabase_db
        if supabase_db.is_configured():
            logger.info("✅ Supabase Cloud Database is configured and ready.")
        else:
            logger.warning("ℹ️ Supabase not configured in env, using local SQLite fallback.")
    except Exception as e:
        logger.warning(f"Note on supabase: {e}")

    # 2. تشغيل بوت تيليجرام في خيط خلفي
    os.environ["NSW_BOT_RUNNER"] = "start_py"
    tg_thread = threading.Thread(target=run_telegram_bot_thread, daemon=True, name="TelegramBotThread")
    tg_thread.start()
    logger.info("✅ Telegram Bot thread launched.")

    # 3. تشغيل محرك النشر التلقائي في خيط خلفي
    synd_thread = threading.Thread(target=run_syndication_daemon_thread, daemon=True, name="SyndicationThread")
    synd_thread.start()
    logger.info("✅ Syndication Daemon thread launched.")

    # 4. تشغيل واجهة Streamlit في الخيط الرئيسي
    run_streamlit()
