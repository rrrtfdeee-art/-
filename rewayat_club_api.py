# -*- coding: utf-8 -*-
"""
rewayat_club_api.py — وسيط النشر والتفاعل الرسمي مع منصة نادي الروايات (Rewayat Club)
مبني بدقة بناءً على الكود المصدري الأصلي لواجهة نادي الروايات:
- POST https://api.rewayat.club/api/chapters/{novel_slug}/create/
- Content-Type: multipart/form-data (FormData)
- Fields: number, title, content (و date إذا مجدول)
- Header: Authorization: Token {token_hex}
"""

import os
import requests
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

BASE_API_URL = "https://api.rewayat.club/api"
BASE_WEB_URL = "https://rewayat.club"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Origin": BASE_WEB_URL,
    "Referer": f"{BASE_WEB_URL}/create/chapter",
}

class RewayatClubClient:
    def __init__(self, token: str = "", username: str = "", password: str = ""):
        self.token = token.strip() or os.getenv("REWAYAT_TOKEN", "").strip() or os.getenv("REWAYAT_CLUB_TOKEN", "").strip()
        self.username = username.strip() or os.getenv("REWAYAT_USERNAME", "").strip()
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        if self.token:
            self._apply_token(self.token)

    def _apply_token(self, token: str):
        self.token = token
        # توكن نادي الروايات الأصلي هو Django REST Framework Token: "Token 4e3379..."
        if not token.lower().startswith("token ") and not token.lower().startswith("bearer "):
            self.session.headers["Authorization"] = f"Token {token}"
        else:
            self.session.headers["Authorization"] = token

    def test_connection(self) -> Dict[str, Any]:
        """فحص حالة الاتصال وصلاحية التوكن بالحساب."""
        if not self.token:
            return {"success": False, "message": "لم يتم إدخال التوكن الخاص بحسابك بعد."}
        
        try:
            url = f"{BASE_API_URL}/user/"
            res = self.session.get(url, timeout=10)
            if res.status_code == 200:
                data = res.json()
                u_name = data.get("username") or "مستخدم معتمد"
                return {
                    "success": True,
                    "message": f"تم التحقق بنجاح من حسابك في نادي الروايات! مرحباً @{u_name}",
                    "user": data
                }
            elif res.status_code in [401, 403]:
                return {"success": False, "message": "رمز التوكن غير صالح أو انتهت صلاحيته."}
            else:
                return {"success": False, "message": f"استجابة غير متوقعة: {res.status_code}"}
        except Exception as e:
            return {"success": False, "message": f"خطأ اتصال: {str(e)}"}

    def chapter_exists(self, novel_id: str, chapter_num: int) -> bool:
        """
        التحقق الصارم مما إذا كان الفصل موجوداً مسبقاً على نادي الروايات لتفادي التكرار.
        """
        clean_slug = str(novel_id).strip()
        if "rewayat.club/novel/" in clean_slug:
            clean_slug = clean_slug.split("rewayat.club/novel/")[-1].split("/")[0].split("?")[0]
        clean_slug = clean_slug.rstrip("/")

        # 1. فحص عبر API
        try:
            chk_url = f"{BASE_API_URL}/chapters/{clean_slug}/?number={chapter_num}"
            res = self.session.get(chk_url, timeout=8)
            if res.status_code == 200:
                data = res.json()
                results = data.get("results", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                for item in results:
                    try:
                        if int(item.get("number")) == int(chapter_num):
                            return True
                    except Exception:
                        pass
        except Exception:
            pass

        # 2. فحص عبر الويب المباشر
        try:
            web_url = f"{BASE_WEB_URL}/novel/{clean_slug}/{chapter_num}"
            res_web = self.session.get(web_url, timeout=8)
            if res_web.status_code == 200 and "404" not in res_web.text[:500]:
                return True
        except Exception:
            pass

        return False

    def publish_chapter(self, novel_id: str, chapter_num: int, title: str, content: str, schedule_date: Optional[str] = None) -> Dict[str, Any]:
        """
        نشر الفصل عبر الـ API الرسمي المطابق 100% لواجهة نادي الروايات:
        POST /api/chapters/{slug}/create/
        مع فحص استباقي لمنع التكرار (chapter_exists).
        """
        if not self.token:
            return {"success": False, "error": "يرجى إدخال وحفظ التوكن (Token) أولاً."}

        # استخراج الـ slug النظيف للرواية
        clean_slug = novel_id.strip()
        if "rewayat.club/novel/" in clean_slug:
            clean_slug = clean_slug.split("rewayat.club/novel/")[-1].split("/")[0].split("?")[0]
        clean_slug = clean_slug.rstrip("/")

        # 1. فحص مسبق: إذا كان الفصل موجوداً بالفعل لا نرسل طلب إنشاء
        if self.chapter_exists(clean_slug, chapter_num):
            live_url = f"{BASE_WEB_URL}/novel/{clean_slug}/{chapter_num}"
            logger.info(f"[rewayat] Chapter {chapter_num} already exists for {clean_slug}. Skipping POST.")
            return {
                "success": True,
                "chapter_num": chapter_num,
                "post_url": live_url,
                "already_exists": True,
                "message": f"الفصل {chapter_num} منشور مسبقاً على نادي الروايات."
            }

        endpoint = f"{BASE_API_URL}/chapters/{clean_slug}/create/"

        # التأكد من تغليف كل فقرة بـ <p>...</p> لضمان عرض الفقرات منفصلة ومريحة للقراءة في واجهة نادي الروايات
        raw_text = str(content).strip()
        if not raw_text.startswith("<p>"):
            paras = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
            formatted_content = "\n".join([f"<p>\n{p}\n</p>" for p in paras])
        else:
            formatted_content = raw_text

        form_data = {
            "number": str(chapter_num),
            "title": str(title).strip(),
            "content": formatted_content,
        }
        if schedule_date:
            form_data["date"] = schedule_date

        try:
            res = self.session.post(endpoint, data=form_data, timeout=25)
            
            if res.status_code in [200, 201]:
                resp_json = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
                actual_num = resp_json.get("number", chapter_num)
                live_url = f"{BASE_WEB_URL}/novel/{clean_slug}/{actual_num}"
                return {
                    "success": True,
                    "chapter_num": actual_num,
                    "post_url": live_url,
                    "message": f"تم نشر الفصل {actual_num} بنجاح على نادي الروايات!"
                }
            elif res.status_code == 400:
                err_text = res.text
                if "لقد قمت بإنشاء فصل بهذا الرقم" in err_text or "already created" in err_text.lower():
                    # الفصل موجود ومنشور بالفعل مسبقاً على نادي الروايات
                    live_url = f"{BASE_WEB_URL}/novel/{clean_slug}/{chapter_num}"
                    return {
                        "success": True,
                        "chapter_num": chapter_num,
                        "post_url": live_url,
                        "already_exists": True,
                        "message": f"الفصل {chapter_num} منشور مسبقاً على نادي الروايات."
                    }
                return {"success": False, "error": f"خطأ في بيانات النشر (400): {err_text[:250]}"}
            elif res.status_code in [401, 403]:
                return {"success": False, "error": f"غير مصرح بالنشر لهذه الرواية أو التوكن غير صالح ({res.status_code})."}
            elif res.status_code == 429:
                return {"success": False, "error": "لقد تخطيت العدد المسموح للطلبات (429 Rate Limit)."}
            else:
                return {"success": False, "error": f"خطأ غير متوقع من الموقع ({res.status_code}): {res.text[:200]}"}

        except Exception as e:
            return {"success": False, "error": f"استثناء أثناء محاولة النشر: {str(e)}"}

    def get_latest_chapter_number(self, novel_id: str, baseline_hint: int = 0) -> Optional[int]:
        """
        استعلام أحدث رقم فصل منشور على نادي الروايات:
        يدعم تصفح كل صفحات الفصول (Pagination حتى 2000+ فصل) لمنع تراجع رقم آخر فصل في الروايات الطويلة.
        """
        clean_slug = novel_id.strip()
        if "rewayat.club/novel/" in clean_slug:
            clean_slug = clean_slug.split("rewayat.club/novel/")[-1].split("/")[0].split("?")[0]
        clean_slug = clean_slug.rstrip("/")

        endpoint = f"{BASE_API_URL}/chapters/{clean_slug}/?limit=100"
        valid_nums = []
        page = 1
        max_pages = 25  # يدعم حتى 2500 فصل (25 * 100)

        while endpoint and page <= max_pages:
            try:
                res = self.session.get(endpoint, timeout=12)
                if res.status_code != 200:
                    break
                data = res.json()
                results = data.get("results", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                if results:
                    for item in results:
                        try:
                            n = int(item.get("number"))
                            if n > 0:
                                valid_nums.append(n)
                        except Exception:
                            pass
                endpoint = data.get("next") if isinstance(data, dict) else None
                page += 1
            except Exception as e:
                logger.warning(f"Error fetching page {page} for {clean_slug}: {e}")
                break

        if valid_nums:
            sorted_nums = sorted(set(valid_nums))
            valid_max = sorted_nums[0]
            for i in range(1, len(sorted_nums)):
                curr = sorted_nums[i]
                prev = sorted_nums[i-1]
                if curr - prev <= 5:
                    valid_max = curr
                else:
                    if baseline_hint > 0 and curr <= baseline_hint:
                        valid_max = curr
                        continue
                    break
            return valid_max
        return None
