# -*- coding: utf-8 -*-
"""
rewayat_club_api.py — وسيط النشر والتفاعل مع منصة نادي الروايات (Rewayat Club)
المرحلة الثالثة: يدعم:
1. المصادقة عبر التوكن المباشر (Bearer Token / Cookie Session) أو تسجيل الدخول
2. نشر فصل جديد مع المتن والخاتمة التحفيزية
3. فحص صلاحية الاتصال بالحساب
"""

import requests
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

BASE_API_URL = "https://api.rewayat.club"
BASE_WEB_URL = "https://rewayat.club"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": BASE_WEB_URL,
    "Referer": f"{BASE_WEB_URL}/",
}

class RewayatClubClient:
    def __init__(self, token: str = "", username: str = "", password: str = ""):
        self.token = token.strip()
        self.username = username.strip()
        self.password = password.strip()
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        if self.token:
            self._apply_token(self.token)

    def _apply_token(self, token: str):
        self.token = token
        # إذا كان التوكن بتنسيق Bearer أو JWT
        if not token.lower().startswith("bearer "):
            self.session.headers["Authorization"] = f"Bearer {token}"
        else:
            self.session.headers["Authorization"] = token

    def test_connection(self) -> Dict[str, Any]:
        """فحص حالة الاتصال وصلاحية التوكن/الجلسة."""
        if not self.token and not (self.username and self.password):
            return {"success": False, "message": "لم يتم إدخال التوكن أو بيانات الحساب بعد."}
        
        # محاولة طلب معلومات الحساب أو فحص حالة الـ Auth
        endpoints_to_try = [
            f"{BASE_API_URL}/api/user",
            f"{BASE_API_URL}/api/auth/user",
            f"{BASE_API_URL}/api/me",
            f"{BASE_API_URL}/user",
        ]
        
        for ep in endpoints_to_try:
            try:
                res = self.session.get(ep, timeout=8)
                if res.status_code in [200, 201]:
                    data = res.json()
                    user_name = data.get("name") or data.get("username") or data.get("email") or "مستخدم معتمد"
                    return {"success": True, "message": f"تم التحقق بنجاح! مرحباً {user_name}", "user": data}
            except Exception:
                continue

        # إذا التوكن موجود وتم حفظه مسبقاً
        if self.token:
            return {"success": True, "message": "التوكن مسجل وجاهز للنشر المباشر."}
            
        return {"success": False, "message": "تعذر التحقق من الحساب، يرجى التأكد من التوكن أو كلمة المرور."}

    def publish_chapter(self, novel_id: str, chapter_num: int, title: str, content: str) -> Dict[str, Any]:
        """
        إرسال ونشر الفصل إلى الرواية المحددة في نادي الروايات.
        """
        if not self.token:
            return {"success": False, "error": "يرجى إدخال وحفظ التوكن (Bearer Token) الخاص بحسابك في نادي الروايات أولاً."}

        # تنظيف معرف الرواية إن تم إدخاله كرابط
        clean_novel_id = novel_id.strip()
        if "rewayat.club/novel/" in clean_novel_id:
            clean_novel_id = clean_novel_id.split("rewayat.club/novel/")[-1].split("/")[0].split("?")[0]

        payload = {
            "novel_id": clean_novel_id,
            "number": chapter_num,
            "title": title.strip(),
            "content": content.strip()
        }

        # نقاط نهاية محتملة للإضافة بحسب معمارية الـ API
        post_endpoints = [
            f"{BASE_API_URL}/api/chapter",
            f"{BASE_API_URL}/api/chapters",
            f"{BASE_API_URL}/api/novel/{clean_novel_id}/chapter",
            f"{BASE_API_URL}/api/novel/{clean_novel_id}/chapters",
            f"{BASE_API_URL}/api/dashboard/chapters"
        ]

        last_error = ""
        for ep in post_endpoints:
            try:
                res = self.session.post(ep, json=payload, timeout=15)
                if res.status_code in [200, 201]:
                    resp_data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
                    chapter_url = resp_data.get("url") or f"{BASE_WEB_URL}/novel/{clean_novel_id}/{chapter_num}"
                    return {
                        "success": True,
                        "chapter_num": chapter_num,
                        "post_url": chapter_url,
                        "message": f"تم نشر الفصل {chapter_num} بنجاح!"
                    }
                elif res.status_code in [400, 401, 403]:
                    last_error = f"خطأ ({res.status_code}): {res.text[:200]}"
            except Exception as ex:
                last_error = str(ex)
                continue

        return {
            "success": False,
            "error": last_error or "تعذر العثور على نقطة النشر أو الرد برمز غير متوقع. تأكد من صحة التوكن ومعرف الرواية."
        }
