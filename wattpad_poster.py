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
    def __init__(self, token: str = "", username: str = "", password: str = ""):
        self.token = token.strip()
        self.username = username.strip()
        self.password = password.strip()
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_WATTPAD_HEADERS)
        if self.token:
            self._apply_token(self.token)
        elif self.username and self.password:
            self.auto_login()

    def auto_login(self) -> Dict[str, Any]:
        """تسجيل الدخول التلقائي وسحب توكن جلسة نشط من خوادم واتباد."""
        user = self.username.strip() or "WX-NOVEL"
        pwd = self.password.strip()
        if not pwd:
            try:
                import syndication_db
                pwd = syndication_db.get_synd_setting("wattpad_password", "")
            except Exception:
                pass
        
        if not user or not pwd:
            return {"success": False, "message": "اسم المستخدم وكلمة المرور مطلوبان لتسجيل الدخول التلقائي."}
            
        url = "https://api.wattpad.com/v4/sessions"
        headers = {
            "User-Agent": "Wattpad/10.0 (Android; 13)",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json"
        }
        data = {
            "type": "wattpad",
            "username": user,
            "password": pwd,
            "fields": "token,user(username,email,name)"
        }
        try:
            res = requests.post(url, data=data, headers=headers, timeout=15)
            if res.status_code == 200:
                resp_data = res.json()
                new_token = resp_data.get("token")
                if new_token:
                    self.token = new_token
                    self._apply_token(new_token)
                    try:
                        import syndication_db
                        syndication_db.save_synd_setting("wattpad_token", new_token)
                        if user:
                            syndication_db.save_synd_setting("wattpad_username", user)
                        if pwd:
                            syndication_db.save_synd_setting("wattpad_password", pwd)
                    except Exception:
                        pass
                    return {"success": True, "token": new_token, "user": resp_data.get("user"), "message": "تم تسجيل الدخول وتجديد الجلسة بنجاح!"}
            return {"success": False, "message": f"فشل تسجيل الدخول ({res.status_code}): {res.text[:150]}"}
        except Exception as e:
            return {"success": False, "message": f"خطأ أثناء تسجيل الدخول: {e}"}

    def _apply_token(self, token: str):
        import urllib.parse
        self.token = urllib.parse.unquote(token.strip())
        # واتباد يقبل إما Authorization Header بالتوكن أو cookie
        if self.token.lower().startswith("token ") or self.token.lower().startswith("bearer "):
            self.session.headers["Authorization"] = self.token
        else:
            self.session.headers["Authorization"] = f"Bearer {self.token}"
            self.session.cookies.set("token", self.token, domain=".wattpad.com")
            self.session.cookies.set("wp_token", self.token, domain=".wattpad.com")

    def test_connection(self) -> Dict[str, Any]:
        """فحص حالة الاتصال وصلاحية الحساب في واتباد مع تجديد ذاتي إذا لزم."""
        if not self.token and (self.username or self.password):
            login_res = self.auto_login()
            if not login_res.get("success"):
                return login_res
                
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
            elif res.status_code in [401, 403, 500]:
                # محاولة تجديد الجلسة تلقائياً بكلمة المرور
                login_res = self.auto_login()
                if login_res.get("success"):
                    res = self.session.get(url, timeout=10)
                    if res.status_code == 200:
                        data = res.json()
                        u_name = data.get("username") or self.username
                        return {"success": True, "message": f"تم تجديد الجلسة والتحقق بنجاح من @{u_name}!", "user": data}
                return {"success": False, "message": "رمز التوكن غير صالح أو انتهت صلاحيته."}
        except Exception as e:
            logger.warning(f"[wattpad] test_connection: {e}")

        if self.token:
            return {"success": True, "message": "التوكن محفوظ ومسجل للنشر التلقائي."}

        return {"success": False, "message": "تعذر التحقق من حساب واتباد."}

    def publish_chapter_to_story(self, story_id: str, chapter_num: int, title: str, content: str) -> Dict[str, Any]:
        """
        إضافة جزء/فصل جديد داخل قصة واتباد ونشره عبر نقطة النهاية الرسمية apiv2/newstory.
        """
        if not self.token and (self.username or self.password):
            self.auto_login()

        if not self.token:
            return {"success": False, "error": "يرجى إدخال وحفظ التوكن أو بيانات الحساب في واتباد أولاً."}

        clean_story_id = story_id.strip()
        # تنظيف إذا تم إدخال رابط قصة واتباد كامل
        if "wattpad.com/story/" in clean_story_id:
            part = clean_story_id.split("wattpad.com/story/")[-1]
            clean_story_id = part.split("-")[0].split("/")[0].split("?")[0]

        part_title = title.strip() or f"الفصل {chapter_num}"
        formatted_content = "<p>" + content.strip().replace("\n\n", "</p><p>").replace("\n", "<br/>") + "</p>"

        def _do_post():
            url = "https://www.wattpad.com/apiv2/newstory"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Cookie": f"token={self.token}; wp_token={self.token};",
                "Authorization": f"token {self.token}",
                "X-Requested-With": "XMLHttpRequest"
            }
            data = {
                "groupid": clean_story_id,
                "title": part_title,
                "text": formatted_content,
                "draft": 0,
                "publish": 1,
                "language": 16,
                "copyright": 1,
                "category1": 4
            }
            return requests.post(url, data=data, headers=headers, timeout=25)

        try:
            res = _do_post()
            if res.status_code in [401, 403]:
                # محاولة تجديد الجلسة تلقائياً ببيانات الاعتماد وإعادة الطلب
                login_res = self.auto_login()
                if login_res.get("success"):
                    res = _do_post()

            if res.status_code in [200, 201]:
                data = res.json()
                if data.get("errors") and len(data.get("errors")) > 0:
                    return {
                        "success": False,
                        "error": f"أخطاء من واتباد: {data.get('errors')}"
                    }
                part_id = data.get("id")
                story_url = data.get("story_url", "")
                if story_url:
                    part_url = f"https://www.wattpad.com/{story_url}"
                elif part_id:
                    part_url = f"https://www.wattpad.com/{part_id}"
                else:
                    part_url = f"https://www.wattpad.com/story/{clean_story_id}"

                return {
                    "success": True,
                    "chapter_num": chapter_num,
                    "post_url": part_url,
                    "part_id": part_id,
                    "message": f"تم نشر الفصل {chapter_num} على قصة واتباد بنجاح!"
                }
            else:
                return {
                    "success": False,
                    "error": f"خطأ من واتباد ({res.status_code}): {res.text[:200]}"
                }
        except Exception as e:
            return {"success": False, "error": f"استثناء أثناء نشر الفصل على واتباد: {str(e)}"}
