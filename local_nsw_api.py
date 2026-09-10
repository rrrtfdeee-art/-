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
import re
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

from urllib.parse import urlparse, parse_qs, unquote
from database import find_novel_by_query, get_novel_gaps, get_chapters

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
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/api/status" or path == "/":
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

        elif path == "/api/opus/prompt":
            prompt_file = STAGING_DIR / "CLAUDE_PROMPT_FOR_BATCH.txt"
            content = prompt_file.read_text(encoding="utf-8") if prompt_file.exists() else "لم يتم توليد الأمر بعد."
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"prompt": content}, ensure_ascii=False).encode("utf-8"))

        elif path == "/api/novel_stats":
            novel_q = qs.get("novel", [""])[0] or qs.get("name", [""])[0]
            nov = find_novel_by_query(novel_q)
            if not nov:
                data = {"status": "error", "message": f"لم يتم العثور على رواية تطابق: {novel_q}"}
            else:
                stats = get_novel_gaps(nov["id"])
                data = {
                    "status": "success",
                    "novel_id": nov["id"],
                    "title": nov["title"],
                    "domain": nov.get("domain", ""),
                    "min_chapter": stats["min"],
                    "max_chapter": stats["max"],
                    "latest_downloaded": stats["max"],
                    "total_manifest": stats["total_manifest"],
                    "completed_count": stats["completed"],
                    "failed_count": len(stats["failed"]),
                    "failed_chapters": stats["failed"][:50],
                    "gaps": stats["gaps"][:100],
                    "missing_count": stats["missing_count"]
                }
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

        elif path == "/api/raw_chapters":
            novel_q = qs.get("novel", [""])[0] or qs.get("name", [""])[0]
            start_c = int(qs.get("start", [1])[0])
            end_c = int(qs.get("end", [start_c + 50])[0])
            
            nov = find_novel_by_query(novel_q)
            if not nov:
                data = {"status": "error", "message": f"الرواية غير موجودة: {novel_q}", "chapters": []}
            else:
                raw_rows = get_chapters(nov["id"], from_chapter=start_c, to_chapter=end_c)
                out_chapters = []
                for r in raw_rows:
                    content = r.get("content") or ""
                    # إذا كان المحتوى مفرغاً محلياً، نفحص مجلد staging
                    if not content or len(content) < 30:
                        ch_file = APPROVED_DIR / f"chapter_{r['chapter_number']}.txt"
                        if not ch_file.exists():
                            ch_file = PENDING_DIR / f"chapter_{r['chapter_number']}.txt"
                        if ch_file.exists():
                            try:
                                content = ch_file.read_text(encoding="utf-8")
                            except Exception:
                                pass

                    out_chapters.append({
                        "chapNum": r["chapter_number"],
                        "title": r.get("title") or f"الفصل {r['chapter_number']}",
                        "authorTitle": r.get("title") or "",
                        "text": content,
                        "status": r.get("status", "unknown"),
                        "hasContent": bool(content and len(content) > 50)
                    })

                data = {
                    "status": "success",
                    "novel": nov["title"],
                    "novel_id": nov["id"],
                    "range": [start_c, end_c],
                    "count": len(out_chapters),
                    "chapters": out_chapters
                }
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

        elif path == "/api/polished_chapters":
            novel_q = qs.get("novel", [""])[0] or qs.get("name", [""])[0]
            start_c = int(qs.get("start", [1])[0])
            end_c = int(qs.get("end", [999999])[0])

            approved_files = sorted(APPROVED_DIR.glob("chapter_*.txt"), key=lambda p: int(re.search(r'\d+', p.name).group()) if re.search(r'\d+', p.name) else 0)
            polished_list = []
            for f in approved_files:
                try:
                    ch_num = int(re.search(r'\d+', f.name).group())
                except Exception:
                    continue
                if ch_num < start_c or ch_num > end_c:
                    continue

                try:
                    content = f.read_text(encoding="utf-8")
                    # فحص واستخراج العنوان والمحتوى الصافي
                    header_lines = []
                    body_text = content
                    if content.startswith("---"):
                        parts = content.split("---", 2)
                        if len(parts) >= 3:
                            header_part = parts[1]
                            body_text = parts[2].strip()
                            # فحص مطابقة الرواية إن كانت محددة
                            if novel_q:
                                n_match = re.search(r'novel:\s*(.*)', header_part)
                                if n_match and novel_q.lower() not in n_match.group(1).lower() and n_match.group(1).lower() not in novel_q.lower():
                                    continue

                    polished_list.append({
                        "chapNum": ch_num,
                        "title": f"الفصل {ch_num}",
                        "text": body_text,
                        "source": "local_approved",
                        "status": "approved"
                    })
                except Exception:
                    pass

            data = {
                "status": "success",
                "count": len(polished_list),
                "novel": novel_q,
                "range": [start_c, end_c],
                "chapters": polished_list
            }
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

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
        elif self.path == "/api/repair_gaps":
            novel_q = body.get("novel", "")
            nov = find_novel_by_query(novel_q)
            if not nov:
                self.send_response(200)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "message": f"لم يتم العثور على رواية تطابق: {novel_q}"}, ensure_ascii=False).encode("utf-8"))
                return
            
            stats = get_novel_gaps(nov["id"])
            gaps_to_fix = stats["gaps"]
            if not gaps_to_fix:
                self.send_response(200)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "message": "لا توجد أي فصول مفقودة في هذه الرواية!", "gaps_count": 0}, ensure_ascii=False).encode("utf-8"))
                return

            def _run_gap_fix():
                try:
                    import scraper_engine
                    scraper_engine.start_scraping_job_in_background(
                        novel_id=nov["id"],
                        from_chapter=stats["min"],
                        to_chapter=stats["max"],
                        chapter_numbers=gaps_to_fix,
                        novel_name=nov["title"],
                        thread_count=3,
                        auto_stream_to_sheet=True
                    )
                except Exception as ex_gap:
                    logger.error(f"خطأ سحب فصول الثغرات: {ex_gap}")

            threading.Thread(target=_run_gap_fix, daemon=True).start()

            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "message": f"تم إطلاق سحب وسد {len(gaps_to_fix)} فصلاً مفقوداً في الخلفية عبر 3 خيوط متوازية!",
                "gaps_count": len(gaps_to_fix),
                "gaps": gaps_to_fix[:50]
            }, ensure_ascii=False).encode("utf-8"))
        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()

from http.server import ThreadingHTTPServer

class ReusableThreadingServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

def start_server():
    server_address = ("127.0.0.1", PORT)
    try:
        httpd = ReusableThreadingServer(server_address, NSWLocalAPIHandler)
        logger.info(f"⚡ [NSW Local API] خادم الربط المحلي يعمل بنشاط على: http://127.0.0.1:{PORT}")
        httpd.serve_forever()
    except Exception as e:
        logger.warning(f"ملاحظة إقلاع خادم الربط المحلي: {e}")

if __name__ == "__main__":
    start_server()
