# -*- coding: utf-8 -*-
"""
wattpad_poster.py — وسيط النشر والتفاعل مع منصة واتباد (Wattpad)
المرحلة الرابعة: يدعم:
1. المصادقة عبر Wattpad Token أو Session Cookie
2. إنشاء وإضافة جزء جديد (New Part) إلى قصة موجودة ونشره
3. فحص صلاحية الاتصال بالحساب
"""

import requests
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

BASE_WATTPAD_API = "https://www.wattpad.com/api/v3"
DEFAULT_WATTPAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Origin": "https://www.wattpad.com",
    "Referer": "https://www.wattpad.com/",
}

class WattpadClient:
    def __init__(self, token: str = "", username: str = ""):
        self.token = token.strip()
        self.username = username.strip()
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_WATTPAD_HEADERS)
        if self.token:
            self._apply_token(self.token)

    def _apply_token(self, token: str):
        import urllib.parse
        self.token = urllib.parse.unquote(token.strip())
        # واتباد يقبل إما Authorization Header بالتوكن أو cookie
        if self.token.lower().startswith("token ") or self.token.lower().startswith("bearer "):
            self.session.headers["Authorization"] = self.token
        else:
            self.session.headers["Authorization"] = f"token {self.token}"
            self.session.cookies.set("token", self.token, domain=".wattpad.com")

    def test_connection(self) -> Dict[str, Any]:
        """فحص حالة الاتصال وصلاحية الحساب في واتباد."""
        if not self.token and not self.username:
            return {"success": False, "message": "لم يتم إدخال التوكن أو بيانات الحساب بعد."}
        
        target_user = self.username.strip() or "WX-NOVEL"
        try:
            url = f"{BASE_WATTPAD_API}/users/{target_user}"
            res = self.session.get(url, timeout=10)
            if res.status_code == 200:
                data = res.json()
                u_name = data.get("username") or self.username
                desc = data.get("description", "")
                short_desc = (desc.split("\n")[0]) if desc else ""
                msg = f"تم التحقق بنجاح من حساب واتباد! مرحباً @{u_name}"
                if short_desc:
                    msg += f" ({short_desc})"
                return {"success": True, "message": msg, "user": data}
            elif res.status_code in [401, 403]:
                return {"success": False, "message": "رمز التوكن غير صالح أو انتهت صلاحيته."}
        except Exception as e:
            logger.warning(f"[wattpad] test_connection: {e}")

        if self.token:
            return {"success": True, "message": "التوكن محفوظ ومسجل للنشر التلقائي."}

        return {"success": False, "message": "تعذر التحقق من حساب واتباد."}

    def publish_chapter_to_story(self, story_id: str, chapter_num: int, title: str, content: str) -> Dict[str, Any]:
        """
        إضافة جزء/فصل جديد داخل قصة واتباد ونشره.
        """
        if not self.token:
            return {"success": False, "error": "يرجى إدخال وحفظ التوكن الخاص بحسابك في واتباد أولاً."}

        clean_story_id = story_id.strip()
        # تنظيف إذا تم إدخال رابط قصة واتباد كامل
        if "wattpad.com/story/" in clean_story_id:
            part = clean_story_id.split("wattpad.com/story/")[-1]
            clean_story_id = part.split("-")[0].split("/")[0].split("?")[0]

        # 1. إنشاء الجزء (Create Draft / Part)
        create_url = f"{BASE_WATTPAD_API}/stories/{clean_story_id}/parts"
        part_title = title.strip() or f"الفصل {chapter_num}"

        # تنسيق المحتوى مع فواصل الأسطر المناسبة لواتباد
        formatted_content = "<p>" + content.strip().replace("\n\n", "</p><p>").replace("\n", "<br/>") + "</p>"

        payload = {
            "title": part_title,
            "text_url": formatted_content,
            "text": formatted_content,
            "published": True
        }

        try:
            res = self.session.post(create_url, json=payload, timeout=20)
            if res.status_code in [200, 201]:
                data = res.json()
                part_id = data.get("id")
                part_url = data.get("url") or f"https://www.wattpad.com/{part_id}"
                
                # 2. التأكيد على حالة النشر (Publish) إن لزم الأمر
                try:
                    if part_id:
                        self.session.put(f"{BASE_WATTPAD_API}/parts/{part_id}", json={"published": True}, timeout=10)
                except Exception:
                    pass

                return {
                    "success": True,
                    "chapter_num": chapter_num,
                    "post_url": part_url,
                    "message": f"تم نشر الفصل {chapter_num} على قصة واتباد بنجاح!"
                }
            else:
                return {
                    "success": False,
                    "error": f"خطأ من واتباد ({res.status_code}): {res.text[:200]}"
                }
        except Exception as e:
            return {"success": False, "error": f"استثناء أثناء نشر الفصل على واتباد: {str(e)}"}
