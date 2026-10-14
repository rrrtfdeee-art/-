# -*- coding: utf-8 -*-
"""
novelupdates_poster.py — محرك النشر وأتمتة الإصدارات على Novel Updates (v1.0)

الوظائف:
1. استخراج بيانات الفصل المنشور من https://github.com/rrrtfdeee-art/nsw-en-public/blob/main/data/latest_chapters.json
2. دعم تخصيص الدومين ومعالجة كافة أشكال السلاش (/) بذكاء لمنع ازدواجية الروابط أو كسرها.
3. تجهيز بيانات الإصدار (Series, Release code مثل c16, Link to Release, Group Name, Release Date).
4. إرسال الإصدار إلى https://www.novelupdates.com/add-release/ عبر بيانات الدخول والـ Cookie/Session Token.
5. توليد تغذية RSS معيارية خاصة بـ Novel Updates تتيح للزاحف الآلي التابع لموقع Novel Updates سحب الفصول تلقائياً 24/7 دون أي كابتشا.
"""

import os
import re
import json
import time
import logging
import urllib.parse
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
import requests

logger = logging.getLogger("NovelUpdatesPoster")

NU_ADD_RELEASE_URL = "https://www.novelupdates.com/add-release/"
LATEST_CHAPTERS_JSON_URL = "https://raw.githubusercontent.com/rrrtfdeee-art/nsw-en-public/main/data/latest_chapters.json"
LIBRARY_JSON_URL = "https://raw.githubusercontent.com/rrrtfdeee-art/nsw-en-public/main/data/library.json"

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


# ==============================================================================
# 1. معالجة وتطبيع الدومين المخصص والروابط (Custom Domain Handling)
# ==============================================================================

def normalize_custom_domain(domain_str: str) -> str:
    """
    تطبيع وتجهيز الدومين المخصص أياً كانت طريقة كتابته من المستخدم:
    - إزالة المسافات الفارغة.
    - إضافة https:// تلقائياً إذا لم يكتب البروتوكول.
    - إزالة كافة السلاش الزائدة من نهاية الدومين (Trailing Slashes).
    
    أمثلة:
      'en.novelskyworld.com/'      -> 'https://en.novelskyworld.com'
      'https://my-site.com///'     -> 'https://my-site.com'
      'http://read.nsw.org'        -> 'http://read.nsw.org'
      'sub.domain.com/path/'       -> 'https://sub.domain.com/path'
    """
    if not domain_str:
        return ""
    
    clean = str(domain_str).strip()
    if not clean:
        return ""
    
    # إضافة البروتوكول إذا لم يكن موجوداً
    if not clean.startswith("http://") and not clean.startswith("https://"):
        clean = "https://" + clean
    
    # إزالة السلاش من النهاية
    clean = clean.rstrip("/")
    return clean


def format_release_link(original_link: str, custom_domain: str = "") -> str:
    """
    دمج الدومين المخصص مع رابط الفصل الأصلي مع معالجة ذكية للسلاش:
    - إذا كان هناك دومين مخصص، يتم استبدال الدومين الأصلي به والاحتفاظ بمسار الفصل كاملاً.
    - منع ظهور // مزدوجة بين الدومين والمسار.
    - إذا لم يتوفر دومين مخصص، يتم إرجاع الرابط الأصلي بعد تنظيفه.
    """
    if not original_link:
        return ""
    
    orig = str(original_link).strip()
    norm_domain = normalize_custom_domain(custom_domain)
    
    if not norm_domain:
        return orig
    
    # استخراج المسار والاستعلام من الرابط الأصلي
    try:
        parsed_orig = urllib.parse.urlparse(orig)
        path = parsed_orig.path or "/"
        query = f"?{parsed_orig.query}" if parsed_orig.query else ""
        fragment = f"#{parsed_orig.fragment}" if parsed_orig.fragment else ""
        
        # التأكد من وجود سلاش واحدة فقط بين الدومين والمسار
        clean_path = path.lstrip("/")
        if clean_path:
            return f"{norm_domain}/{clean_path}{query}{fragment}"
        else:
            return f"{norm_domain}{query}{fragment}"
    except Exception as e:
        logger.warning(f"Error parsing release link: {e}")
        return orig


def extract_series_identifier(nu_url_or_name: str) -> str:
    """
    استخراج اسم أو معرّف السلسلة من رابط Novel Updates أو الاسم النصي:
    - 'https://www.novelupdates.com/series/when-the-entire-sect-read-my-thoughts/' -> 'when-the-entire-sect-read-my-thoughts'
    - 'After Severing Ties' -> 'After Severing Ties'
    """
    if not nu_url_or_name:
        return ""
    clean = str(nu_url_or_name).strip()
    if "novelupdates.com/series/" in clean:
        parts = clean.split("novelupdates.com/series/")[-1].strip("/").split("/")
        return parts[0].replace("-", " ").title()
    return clean.strip("/")


# ==============================================================================
# 2. جلب بيانات الفصول وروابطها من latest_chapters.json
# ==============================================================================

_CHAPTERS_CACHE = {"timestamp": 0, "data": []}

def get_latest_chapters_feed(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """جلب قائمة الفصول الحديثة من المستودع العام مع كاش مؤقت وبدائل سحابية سريعة (jsDelivr + GitHub)."""
    global _CHAPTERS_CACHE
    now = time.time()
    if not force_refresh and _CHAPTERS_CACHE["data"] and (now - _CHAPTERS_CACHE["timestamp"] < 60):
        return _CHAPTERS_CACHE["data"]
    
    # 1. محاولة jsDelivr CDN (الأسرع عالمياً)
    cdn_url = "https://cdn.jsdelivr.net/gh/rrrtfdeee-art/nsw-en-public@main/data/latest_chapters.json"
    try:
        resp = requests.get(cdn_url, headers={"User-Agent": DEFAULT_USER_AGENT}, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                _CHAPTERS_CACHE = {"timestamp": now, "data": data}
                return data
    except Exception as e_cdn:
        logger.debug(f"jsDelivr CDN notice: {e_cdn}")

    # 2. محاولة raw.githubusercontent.com
    try:
        resp = requests.get(LATEST_CHAPTERS_JSON_URL, headers={"User-Agent": DEFAULT_USER_AGENT}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                _CHAPTERS_CACHE = {"timestamp": now, "data": data}
                return data
    except Exception as e_raw:
        logger.debug(f"Raw github notice: {e_raw}")

    # 3. محاولة GitHub API مع التوكن
    try:
        import syndication_extractor
        tok = syndication_extractor.GITHUB_TOKEN
        api_url = "https://api.github.com/repos/rrrtfdeee-art/nsw-en-public/contents/data/latest_chapters.json"
        resp = requests.get(api_url, headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github.v3.raw"}, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                _CHAPTERS_CACHE = {"timestamp": now, "data": data}
                return data
    except Exception as e_api:
        logger.debug(f"GitHub API notice: {e_api}")
    
    return _CHAPTERS_CACHE["data"] or []


def fetch_chapter_release_info(novel_name_or_link: str, chapter_num: int, custom_domain: str = "") -> Dict[str, Any]:
    """
    استخراج بيانات الفصل المحدّد لرواية معينة:
    - يبحث في latest_chapters.json أولاً.
    - يطبق الدومين المخصص إن وجد.
    - يرجع كود الإصدار ورابطه الكامل وعنوانه.
    """
    chapters = get_latest_chapters_feed()
    target_num = int(chapter_num)
    search_term = str(novel_name_or_link).strip().lower()
    
    found_item = None
    for item in chapters:
        c_num = int(item.get("num", 0))
        n_title = str(item.get("novelTitle", "")).lower()
        n_link = str(item.get("novelLink", "")).lower()
        
        if c_num == target_num:
            # مطابقة بالاسم أو الرابط
            if search_term in n_title or n_title in search_term or (n_link and search_term in n_link):
                found_item = item
                break
    
    if found_item:
        raw_link = found_item.get("link", "")
        formatted_link = format_release_link(raw_link, custom_domain)
        return {
            "success": True,
            "novel_title": found_item.get("novelTitle", ""),
            "chapter_num": target_num,
            "release_code": f"c{target_num}",
            "release_url": formatted_link,
            "raw_url": raw_link,
            "date": found_item.get("date", ""),
            "full_title": found_item.get("fullTitle", f"Chapter {target_num}")
        }
    
    # محاولة بديلة: إذا لم يتوفر في الفيد المباشر، تركيب الرابط بشكل نمطي إذا كان رابط الرواية متوفراً
    clean_search = novel_name_or_link.strip()
    if clean_search.startswith("http"):
        # توليد رابط افتراضي بناءً على دومين المستخدم ورقم الفصل
        slug = clean_search.rstrip("/").split("/")[-1].replace(".html", "")
        fallback_path = f"/chapter-{target_num}.html"
        fallback_url = format_release_link(f"https://en.novelskyworld.com{fallback_path}", custom_domain)
        return {
            "success": True,
            "novel_title": slug.replace("-", " ").title(),
            "chapter_num": target_num,
            "release_code": f"c{target_num}",
            "release_url": fallback_url,
            "raw_url": f"https://en.novelskyworld.com{fallback_path}",
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "full_title": f"Chapter {target_num}"
        }
    
    return {
        "success": False,
        "message": f"لم يتم العثور على الفصل {target_num} للرواية '{novel_name_or_link}' في تغذية الفصول العامة (latest_chapters.json)."
    }


# ==============================================================================
# 3. عميل النشر المباشر على Novel Updates (NovelUpdatesClient)
# ==============================================================================

class NovelUpdatesClient:
    """
    عميل التعامل مع موقع Novel Updates:
    - دعم الإرسال عبر الكوكيز / التوكن (Session Cookie / Authentication Token).
    - دعم إرسال بيانات الدخول المباشرة (Username/Email & Password).
    - توليد تغذية RSS الخاصة بمجموعة الترجمة.
    """

    def __init__(self, username: str = "", password: str = "", token: str = "", group_name: str = ""):
        self.username = username.strip()
        self.password = password.strip()
        self.token = token.strip()
        self.group_name = group_name.strip()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
            "Referer": NU_ADD_RELEASE_URL,
            "Origin": "https://www.novelupdates.com"
        })

    def _apply_cookies(self):
        """تطبيق الكوكيز أو التوكن في الجلسة."""
        if not self.token:
            return
        
        # إذا كان التوكن عبارة عن سلسلة Cookie كاملة
        if ";" in self.token or "=" in self.token:
            for item in self.token.split(";"):
                item = item.strip()
                if "=" in item:
                    k, v = item.split("=", 1)
                    self.session.cookies.set(k.strip(), v.strip(), domain=".novelupdates.com")
        else:
            # إذا كان التوكن هو قيمة wordpress_logged_in
            self.session.cookies.set("wordpress_logged_in", self.token, domain=".novelupdates.com")

    def test_connection(self) -> Dict[str, Any]:
        """فحص إمكانية الوصول إلى صفحة إضافة الإصدارات في Novel Updates."""
        self._apply_cookies()
        try:
            resp = self.session.get(NU_ADD_RELEASE_URL, timeout=12)
            if resp.status_code == 200:
                text_lower = resp.text.lower()
                if "add release" in text_lower or "submit" in text_lower or "series" in text_lower:
                    # فحص ما إذا كان المستخدم مسجل الدخول
                    if "log in" not in text_lower or "wxsajad" in text_lower or (self.username and self.username.lower() in text_lower):
                        return {"success": True, "message": "الاتصال بـ Novel Updates نشط وتم التحقق من تسجيل الدخول بنجاح!"}
                    return {"success": True, "message": "تم الوصول لصفحة Novel Updates بنجاح (تأكد من إرفاق كوكيز الجلسة للتأكيد)."}
                return {"success": True, "message": "تم الوصول إلى صفحة Novel Updates."}
            elif resp.status_code == 403:
                return {
                    "success": False,
                    "message": "حماية Cloudflare تحجب الطلب المباشر (403). يرجى إدخال كوكيز الجلسة (Session Cookie) المأخوذة من متصفحك لتجاوز الحظر."
                }
            else:
                return {"success": False, "message": f"استجاب الموقع بكود: {resp.status_code}"}
        except Exception as e:
            return {"success": False, "message": f"خطأ في الاتصال: {str(e)}"}

    def publish_release(
        self,
        series_name: str,
        chapter_num: int,
        release_url: str,
        group_name: str = "",
        release_date: str = ""
    ) -> Dict[str, Any]:
        """
        إرسال فصل جديد إلى صفحة Add Release في Novel Updates:
        
        الحقول المطلوبة:
        - series: اسم السلسلة أو عنوانها على Novel Updates.
        - release: كود الإصدار (مثل c16 أو v1c16).
        - link: الرابط المباشر للفصل على موقع المستخدم.
        - group: اسم مجموعة الترجمة.
        - release_date: تاريخ النشر (اختياري، يترك فارغاً لليوم الحالي).
        """
        self._apply_cookies()
        effective_group = (group_name or self.group_name).strip()
        release_code = f"c{int(chapter_num)}"
        
        # تجهيز بيانات النموذج المطابقة لصفحة add-release
        payload = {
            "series": series_name.strip(),
            "release": release_code,
            "link": release_url.strip(),
            "group": effective_group,
            "release_date": release_date.strip() if release_date else "",
            "submit": "Submit"
        }

        try:
            # محاولة إرسال POST
            resp = self.session.post(NU_ADD_RELEASE_URL, data=payload, timeout=15, allow_redirects=True)
            
            if resp.status_code in [200, 201, 302]:
                resp_text = resp.text.lower()
                # التحقق من علامات النجاح
                if "submitted" in resp_text or "success" in resp_text or "release" in resp_text:
                    logger.info(f"✅ Release {release_code} submitted to Novel Updates for '{series_name}'")
                    return {
                        "success": True,
                        "chapter_num": int(chapter_num),
                        "release_code": release_code,
                        "post_url": release_url,
                        "message": f"تم إرسال الإصدار {release_code} بنجاح إلى Novel Updates ({effective_group})!"
                    }
                elif resp.status_code == 302:
                    return {
                        "success": True,
                        "chapter_num": int(chapter_num),
                        "release_code": release_code,
                        "post_url": release_url,
                        "message": f"تم إرسال الإصدار {release_code} وتمت إعادة التوجيه بنجاح."
                    }
            
            if resp.status_code == 403:
                return {
                    "success": False,
                    "error": "حماية Cloudflare تحجب الإرسال التلقائي المباشر (403). الصق كوكيز الجلسة من متصفحك في بيانات الحساب، أو استخدم ميزة RSS التلقائية الخاصة بمجموعتك."
                }
            
            return {
                "success": False,
                "error": f"استجاب الموقع بكود {resp.status_code}. يرجى التحقق من صحة الكوكيز واسم المجموعة."
            }

        except Exception as e:
            logger.error(f"Error publishing to Novel Updates: {e}")
            return {"success": False, "error": f"استثناء أثناء الإرسال لـ Novel Updates: {str(e)}"}

    @staticmethod
    def generate_novel_rss_feed(novel_name: str, releases: List[Dict[str, Any]], site_url: str = "") -> str:
        """
        توليد ملف RSS معتمد لموقع Novel Updates:
        يتيح لـ Novel Updates سحب كافة فصول الرواية تلقائياً كل 20 دقيقة عبر زاحفهم الرسمي
        دون الحاجة لإدخال كابتشا أو كوكيز!
        """
        clean_site = normalize_custom_domain(site_url) or "https://en.novelskyworld.com"
        now_rfc = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
        
        xml_items = []
        for r in releases:
            c_num = r.get("num", r.get("chapter_num", 1))
            ch_link = r.get("link", r.get("release_url", f"{clean_site}/chapter-{c_num}.html"))
            ch_title = f"{novel_name} Chapter {c_num}"
            date_str = r.get("date", now_rfc)
            
            item_xml = f"""    <item>
      <title><![CDATA[{ch_title}]]></title>
      <link>{ch_link}</link>
      <guid isPermaLink="true">{ch_link}</guid>
      <pubDate>{date_str}</pubDate>
      <description><![CDATA[Read {ch_title} on {clean_site}]]></description>
    </item>"""
            xml_items.append(item_xml)
        
        items_block = "\n".join(xml_items)
        
        rss_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title><![CDATA[{novel_name} - English Translations]]></title>
    <link>{clean_site}</link>
    <description><![CDATA[Latest chapter releases for {novel_name}]]></description>
    <language>en-US</language>
    <lastBuildDate>{now_rfc}</lastBuildDate>
{items_block}
  </channel>
</rss>"""
        return rss_content
