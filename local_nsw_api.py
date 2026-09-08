# -*- coding: utf-8 -*-
"""
==============================================================================
NSW Local Web Bridge API Server v1.0
==============================================================================
خادم محلي خفيف جداً (Standard Library) يعمل على اللابتوب على المنفذ 58242.
يربط مباشرة بين صفحات الموقع والمحرر في المتصفح (الترجمة.html وصفحة النشر.html)
وبين خط إنتاج بايثون المحلي (Claude Opus Two-Click Workflow):
  - /api/status: جلب إحصائيات الفصول اللحظية.
  - /api/opus/stage: تنفيذ النقرة 1 (سحب، تجريد، فلترة القاموس، نسخ الأمر).
  - /api/opus/publish: تنفيذ النقرة 2 (اعتماد، إعادة التغليف الملكي، الرفع بمواعيد 2027).
  - /api/sync_dates: إطلاق المزامنة ثنائية الاتجاه لتواريخ النشر بين بلوجر وشيت 1IFT.
"""

import os
import sys
import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# المسارات
BASE_DIR = Path(__file__).resolve().parent
STAGING_DIR = BASE_DIR / "opus_staging"
PENDING_DIR = STAGING_DIR / "pending"
APPROVED_DIR = STAGING_DIR / "approved"
PUBLISHED_DIR = STAGING_DIR / "published"

for d in [PENDING_DIR, APPROVED_DIR, PUBLISHED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

import sync_opus_queue

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [Local-API] %(message)s")
logger = logging.getLogger("NSW_Local_API")

PORT = 58242

class NSWLocalAPIHandler(BaseHTTPRequestHandler):
    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/status" or self.path == "/":
            p_cnt = len(list(PENDING_DIR.glob("chapter_*.txt")))
            a_cnt = len(list(APPROVED_DIR.glob("chapter_*.txt")))
            pub_cnt = len(list(PUBLISHED_DIR.glob("chapter_*.txt")))
            
            prompt_file = STAGING_DIR / "CLAUDE_PROMPT_FOR_BATCH.txt"
            has_prompt = prompt_file.exists()
            prompt_snippet = ""
            if has_prompt:
                try:
                    prompt_snippet = prompt_file.read_text(encoding="utf-8")[:300] + "..."
                except Exception:
                    pass

            data = {
                "status": "online",
                "pending": p_cnt,
                "approved": a_cnt,
                "published": pub_cnt,
                "has_prompt": has_prompt,
                "prompt_snippet": prompt_snippet
            }
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
        elif self.path == "/api/opus/prompt":
            prompt_file = STAGING_DIR / "CLAUDE_PROMPT_FOR_BATCH.txt"
            content = prompt_file.read_text(encoding="utf-8") if prompt_file.exists() else "لم يتم توليد الأمر بعد."
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"prompt": content}, ensure_ascii=False).encode("utf-8"))
        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_len) if content_len > 0 else b"{}"
        try:
            body = json.loads(post_data.decode("utf-8")) if post_data else {}
        except Exception:
            body = {}

        if self.path == "/api/opus/stage":
            logger.info("📥 [Local API] استلام أمر النقرة 1: سحب وتجهيز الفصول والقاموس...")
            limit = int(body.get("limit", 20))
            novel_name = body.get("novel", "After Severing Ties")

            def _run_stage():
                try:
                    sync_opus_queue.cmd_pull(limit=limit, novel_name=novel_name)
                    # فتح المجلد في ويندوز
                    try:
                        os.startfile(str(PENDING_DIR))
                    except Exception:
                        pass
                except Exception as e:
                    logger.error(f"خطأ تنفيذ سحب الفصول: {e}")

            threading.Thread(target=_run_stage, daemon=True).start()

            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "message": f"تم إطلاق النقرة 1: سحب حتى {limit} فصلاً وتجريدها وتجهيز القاموس وفتح المجلد بنجاح."
            }, ensure_ascii=False).encode("utf-8"))

        elif self.path == "/api/opus/publish":
            logger.info("🚀 [Local API] استلام أمر النقرة 2: اعتماد ونشر الفصول بمواعيدها...")
            novel_name = body.get("novel", "After Severing Ties")

            def _run_publish():
                try:
                    cnt = sync_opus_queue.cmd_approve_all()
                    logger.info(f"✍️ تم اعتماد {cnt} فصول ونقلها.")
                    sync_opus_queue.cmd_push(novel_name=novel_name)
                    logger.info("🎉 اكتمل النشر والمزامنة بنجاح.")
                except Exception as e:
                    logger.error(f"خطأ تنفيذ النشر: {e}")

            threading.Thread(target=_run_publish, daemon=True).start()

            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "message": "تم إطلاق النقرة 2: جاري اعتماد الفصول وإعادة التغليف الملكي والرفع لبلوجر بمواعيدها المجدولة بدقة 100%."
            }, ensure_ascii=False).encode("utf-8"))

        elif self.path == "/api/sync_dates":
            logger.info("🔄 [Local API] استلام أمر مزامنة التواريخ ثنائياً بين بلوجر والشيت 1IFT...")
            def _run_sync():
                try:
                    from nsw_healer_engine import PUBLISH_WEBAPP_URL
                    import requests
                    r = requests.post(PUBLISH_WEBAPP_URL, json={"action": "syncBloggerDates"}, timeout=60).json()
                    logger.info(f"نتيجة مزامنة التواريخ من السيرفر: {r}")
                except Exception as e:
                    logger.error(f"خطأ مزامنة التواريخ: {e}")

            threading.Thread(target=_run_sync, daemon=True).start()

            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "message": "تم إطلاق المزامنة ثنائية الاتجاه لتواريخ النشر بنجاح."
            }, ensure_ascii=False).encode("utf-8"))
        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()

def start_server():
    server_address = ("127.0.0.1", PORT)
    try:
        httpd = HTTPServer(server_address, NSWLocalAPIHandler)
        logger.info(f"⚡ [NSW Local API] خادم الربط المحلي يعمل بنشاط على: http://127.0.0.1:{PORT}")
        httpd.serve_forever()
    except Exception as e:
        logger.warning(f"ملاحظة إقلاع خادم الربط المحلي: {e}")

if __name__ == "__main__":
    start_server()
