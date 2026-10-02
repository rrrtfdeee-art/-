# -*- coding: utf-8 -*-
"""
start.py — المشغل فائق الخفة لخدمة النشر وتيليجرام على Render (NSW Publisher Service v3.0)
المميزات:
1. استهلاك ذاكرة ضئيل جداً (<80MB RAM) — خالي تماماً من متصفح Chromium وStreamlit وPlaywright.
2. يدعم السكون التلقائي (Sleep / Spin-down): لا يحتوي على Keep-Alive، مما يوفر ساعات باقة Render.
3. يوفر خادم HTTP مدمج لفحص الصحة في Render ولنبضات إيقاظ السيرفر.
4. يدير نشر الروايات وبوت تيليجرام بالتوازي في خيوط خلفية موحدة.
"""

import os
import sys
import time
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# إعداد السجلات
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("NSWPublisherLauncher")

# استيراد الوحدات الأساسية
import telegram_bot
import syndication_daemon
try:
    import supabase_db
except ImportError:
    supabase_db = None

PORT = int(os.getenv("PORT", "8000"))

class HealthAndWakeupHandler(BaseHTTPRequestHandler):
    """خادم HTTP مدمج وخفيف جداً لمعالجة فحص الصحة في Render."""

    def do_GET(self):
        if self.path in ("/", "/ping", "/health"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            status = {
                "status": "online",
                "service": "NSW-Publisher-Bot",
                "version": "3.0",
                "supabase_connected": supabase_db.is_configured() if supabase_db else False,
                "time": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            self.wfile.write(str(status).encode("utf-8"))
            logger.info(f"💓 [Wakeup Ping] Received GET {self.path} from {self.client_address[0]}")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass

def run_http_server():
    """تشغيل خادم الويب الخفيف على المنفذ المطلوب لـ Render."""
    server_address = ("0.0.0.0", PORT)
    httpd = HTTPServer(server_address, HealthAndWakeupHandler)
    logger.info(f"🌐 [HTTP Server] Listening on 0.0.0.0:{PORT} (Render Health Check Ready)")
    try:
        httpd.serve_forever()
    except Exception as e:
        logger.error(f"HTTP Server stopped: {e}")

def run_telegram_bot_thread():
    """تشغيل بوت تيليجرام مع إعادة المحاولة التلقائية عند أي انقطاع."""
    while True:
        try:
            logger.info("🤖 Starting Telegram Bot polling loop...")
            if hasattr(telegram_bot, 'run_telegram_bot_loop'):
                telegram_bot.run_telegram_bot_loop()
            elif hasattr(telegram_bot, 'bot') and telegram_bot.bot:
                telegram_bot.bot.infinity_polling(timeout=20, long_polling_timeout=15)
        except Exception as e:
            logger.error(f"Telegram Bot error: {e}")
        time.sleep(5)

if __name__ == "__main__":
    print("=" * 60)
    print("  🚀 NSW Publisher & Syndication Service v3.0")
    print("  Memory Footprint: <80MB RAM | Pure Publishing Engine")
    print("=" * 60)

    # 1. فحص إعدادات Supabase
    if supabase_db and supabase_db.is_configured():
        logger.info("✅ Supabase Cloud Database is configured and ready.")
    else:
        logger.warning("ℹ️ Supabase not configured in env, using standard pipeline.")

    # 2. تشغيل محرك النشر التلقائي (Syndication Daemon)
    try:
        syndication_daemon.start_syndication_daemon()
        logger.info("✅ Syndication Daemon started successfully.")
    except Exception as e_daemon:
        logger.error(f"⚠️ Could not start syndication daemon: {e_daemon}")

    # 3. تشغيل بوت تيليجرام في خيط مستقل
    tg_thread = threading.Thread(target=run_telegram_bot_thread, daemon=True, name="TelegramBotThread")
    tg_thread.start()
    logger.info("✅ Telegram Bot thread launched.")

    # 4. تشغيل خادم HTTP في الخيط الرئيسي لمنع إغلاق السيرفر ولتلبية فحص الصحة في Render
    run_http_server()
