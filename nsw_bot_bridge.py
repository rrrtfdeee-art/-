# -*- coding: utf-8 -*-
"""
==============================================================================
NSW Telegram Management Bot Cloud Bridge & Dispatcher v1.0
==============================================================================
هذا السكريبت يعمل كجسر سحابي متواصل 24/7 على السيرفر:
1. يستمع لأوامر المشرف عبر البوت @nsw_publisher_alert_bot (Token: 8527477822:AAG2dkvwdkkhHR_NyzAsfIWwlLBIdPk2Woc).
2. يمرر التحديثات والأوامر (/status, /publish_now, /claude, /scan_broken, /fix, /gaps) إلى Google Apps Script Web App.
3. يدير قفل التشغيل الأحادي التلقائي (Singleton Socket Lock) لمنع تعدد النسخ وتكرار الردود.
4. يتيح تشغيل فحص واستصلاح الفصول المبتورة مباشرة من السيرفر.
"""

import os
import sys
import time
import json
import socket
import logging
import collections
import threading
import requests

# ضبط ترميز الإخراج
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

TELEGRAM_BOT_TOKEN = os.getenv("NSW_TELEGRAM_BOT_TOKEN", "8527477822:AAG2dkvwdkkhHR_NyzAsfIWwlLBIdPk2Woc")
ADMIN_CHAT_ID = os.getenv("NSW_TELEGRAM_CHAT_ID", "1974483260")
GAS_WEBAPP_URL = os.getenv("NSW_GAS_WEBAPP_URL", "https://script.google.com/macros/s/AKfycbwk3rNPfyP6lJw5jkXigqUfTgivsNzgDoyhd61lPiRSFZP49jFShKaz-CfnUqlM9OmH/exec")
SINGLETON_PORT = 49282

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [NSW-Bridge] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("NSWBotBridge")

singleton_socket = None

def acquire_singleton_lock(port=SINGLETON_PORT):
    global singleton_socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(('127.0.0.1', port))
        singleton_socket = s
        logger.info(f"🔒 تم تأكيد قفل التشغيل الأحادي على المنفذ {port} (نسخة وحيدة نشطة).")
        return True
    except socket.error:
        logger.warning("⚠️ هناك نسخة أخرى من NSW bridge تعمل بالفعل في الخلفية! تم إنهاء هذه العملية فوراً لمنع تكرار الردود.")
        return False

def setup_polling():
    """حذف أي Webhook قديم عالق لتمكين استلام التحديثات بسلاسة دون أخطاء التوجيه 302."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getWebhookInfo"
    try:
        r = requests.get(url, timeout=10).json()
        if r.get("result", {}).get("url"):
            logger.info(f"حذف الـ Webhook القديم العالق: {r['result']['url']}")
            requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook?drop_pending_updates=false", timeout=10)
    except Exception as e:
        logger.warning(f"تعذر فحص الـ Webhook: {e}")

def send_instant_message(text: str, chat_id: str = ADMIN_CHAT_ID, parse_mode: str = "HTML"):
    """إرسال رسالة تليجرام فورية."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        requests.post(url, json=payload, timeout=15)
    except Exception as ex:
        logger.error(f"خطأ إرسال رسالة تليجرام: {ex}")

def _forward_worker(update):
    try:
        res = requests.post(GAS_WEBAPP_URL, json=update, timeout=90)
        logger.info(f"-> تم إرسال التحديث لـ Apps Script. الاستجابة: {res.status_code} {res.text[:80]}")
    except requests.exceptions.Timeout:
        logger.warning("⏳ انتهت مهلة الاتصال بـ Apps Script (Timeout 90s). المعالجة مستمرة في السحابة.")
    except Exception as e:
        logger.error(f"خطأ أثناء الاتصال بـ Apps Script: {e}")

def forward_to_gas(update):
    """تمرير غير متزامن في الخلفية لضمان استمرار حلقة استلام الرسائل دون أي تجميد."""
    t = threading.Thread(target=_forward_worker, args=(update,), daemon=True)
    t.start()

def run_bridge_loop(single_pass: bool = False):
    if not acquire_singleton_lock():
        return

    setup_polling()
    logger.info("🚀 بدء مراقبة رسائل تليجرام للبوت @nsw_publisher_alert_bot في السحابة...")
    
    seen_update_ids = collections.deque(maxlen=1000)
    offset = None
    last_heartbeat = time.time()

    while True:
        try:
            now = time.time()
            if now - last_heartbeat > 120:
                logger.info("💓 NSW Bridge نبض حي: المراقبة السحابية نشطة وجاهزة لاستقبال الأوامر...")
                last_heartbeat = now

            params = {"timeout": 20}
            if offset:
                params["offset"] = offset

            res = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates", params=params, timeout=25)
            data = res.json()

            if data.get("ok"):
                updates = data.get("result", [])
                for u in updates:
                    u_id = u["update_id"]
                    offset = u_id + 1

                    if u_id in seen_update_ids:
                        continue
                    seen_update_ids.append(u_id)

                    msg = u.get("message") or u.get("edited_message") or u.get("callback_query")
                    if msg:
                        user = msg.get("from", {}).get("first_name", "مجهول")
                        user_id = str(msg.get("from", {}).get("id", ""))
                        text = msg.get("text") or msg.get("data") or ""
                        text_clean = text.strip().lower()
                        # الأوامر السحابية المباشرة
                        if text_clean == "/fill_gaps" or text_clean == "ملء الفجوات":
                            send_instant_message("🧩 <i>جاري فحص كافة الجداول وبلوجر، وسحب وترجمة ونشر الفصول المفقودة تلقائياً...</i>", user_id)
                            threading.Thread(target=nsw_healer_engine.run_auto_fill_all_gaps, daemon=True).start()
                        elif text_clean == "/heal_now" or text_clean == "استصلاح":
                            send_instant_message("🩹 <i>جاري فحص الفصول المبتورة وسحبها من المصدر وتحديث Blogger فورياً...</i>", user_id)
                            threading.Thread(target=nsw_healer_engine.run_full_auto_heal, daemon=True).start()
                        else:
                            # تمرير التحديث فورياً إلى Google Apps Script
                            forward_to_gas(u)

            if single_pass:
                break

        except requests.exceptions.Timeout:
            if single_pass:
                break
            continue
        except Exception as e:
            logger.error(f"خطأ أثناء استلام التحديثات: {e}")
            time.sleep(3)

def start_bridge_thread():
    """تشغيل الجسر في خيط منفصل للاستخدام المدمج مع تطبيق Streamlit أو أي سيرفر."""
    t = threading.Thread(target=run_bridge_loop, daemon=True)
    t.start()
    return t

if __name__ == "__main__":
    is_daemon = "--daemon" in sys.argv
    run_bridge_loop(single_pass=not is_daemon)
