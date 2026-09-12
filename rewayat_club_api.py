# -*- coding: utf-8 -*-
"""
rewayat_club_api.py — وسيط النشر والتفاعل الرسمي مع منصة نادي الروايات (Rewayat Club)
مبني بدقة بناءً على الكود المصدري الأصلي لواجهة نادي الروايات:
- POST https://api.rewayat.club/api/chapters/{novel_slug}/create/
- Content-Type: multipart/form-data (FormData)
- Fields: number, title, content (و date إذا مجدول)
- Header: Authorization: Token {token_hex}
"""

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
        self.token = token.strip()
        self.username = username.strip()
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

    def publish_chapter(self, novel_id: str, chapter_num: int, title: str, content: str, schedule_date: Optional[str] = None) -> Dict[str, Any]:
        """
        نشر الفصل عبر الـ API الرسمي المطابق 100% لواجهة نادي الروايات:
        POST /api/chapters/{slug}/create/
        """
        if not self.token:
            return {"success": False, "error": "يرجى إدخال وحفظ التوكن (Token) أولاً."}

        # استخراج الـ slug النظيف للرواية
        clean_slug = novel_id.strip()
        if "rewayat.club/novel/" in clean_slug:
            clean_slug = clean_slug.split("rewayat.club/novel/")[-1].split("/")[0].split("?")[0]
        clean_slug = clean_slug.rstrip("/")

        endpoint = f"{BASE_API_URL}/chapters/{clean_slug}/create/"

        # التأكد من تغليف كل فقرة بـ <p>...</p> لضمان عرض الفقرات منفصلة ومريحة للقراءة في واجهة نادي الروايات
        raw_text = str(content).strip()
        if not raw_text.startswith("<p>"):
            paras = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
            formatted_content = "\n".join([f"<p>\n{p}\n</p>" for p in paras])
        else:
            formatted_content = raw_text

        # تجهيز FormData مطابق للـ Nuxt implementation
        form_data = {
            "number": str(chapter_num),
            "title": str(title).strip(),
            "content": formatted_content,
        }
        if schedule_date:
            form_data["date"] = schedule_date

        try:
            # نمرر data=form_data بدون تحديد يدوي للـ boundary ليتولى requests تجهيز multipart/form-data
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

    def get_latest_chapter_number(self, novel_id: str) -> Optional[int]:
        """استعلام أحدث رقم فصل منشور على نادي الروايات مباشرة عبر API."""
        clean_slug = novel_id.strip()
        if "rewayat.club/novel/" in clean_slug:
            clean_slug = clean_slug.split("rewayat.club/novel/")[-1].split("/")[0].split("?")[0]
        clean_slug = clean_slug.rstrip("/")

        endpoint = f"{BASE_API_URL}/chapters/{clean_slug}/"
        try:
            res = self.session.get(endpoint, timeout=10)
            if res.status_code == 200:
                data = res.json()
                results = data.get("results", [])
                if results and "number" in results[0]:
                    return int(results[0]["number"])
                if "count" in data:
                    return int(data["count"])
        except Exception as e:
            logger.warning(f"Error fetching latest chapter for {clean_slug}: {e}")
        return None
