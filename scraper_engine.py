# -*- coding: utf-8 -*-
import os
import time
import random
import re
import html
import sys
import asyncio
import queue
import requests
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Any, Optional, Tuple, Callable
from bs4 import BeautifulSoup
import tldextract
import logging
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

logger = logging.getLogger("scraper_engine")
logging.basicConfig(level=logging.INFO)

import os
import requests

DEFAULT_GAS_URL = os.getenv("NSW_PUBLISH_WEBAPP_URL", "https://script.google.com/macros/s/AKfycbxqLaqJru1ag-am7G9Mrwy5Nb7HliZlK5vbIEQD9MeV3wOOquNUvz4d7vWEwZxkBI6zIw/exec")
DEFAULT_DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1546569711381254265/ZPrKjMA3tVj6kjWZzZeEOePb1I0PfopeYcpdYo7r8rFIXvlHk8m2HM1tIwM_HRRoTXv8")

def send_discord_scraper_alert(message: str, webhook_url: str = DEFAULT_DISCORD_WEBHOOK):
    """إرسال إشعار فوري لكونسول ديسكورد مع دعم تقليم الرسائل الطويلة."""
    if not webhook_url:
        return
    try:
        requests.post(webhook_url, json={"content": message[:1950]}, timeout=10)
    except Exception as e:
        print(f"⚠️ خطأ إرسال إشعار ديسكورد: {e}")

# حل مشكلة NotImplementedError على ويندوز في بيئات Streamlit
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

# استيراد مجمع وسائط Google Apps Script
from gemini_analyzer import DEFAULT_GAS_POOL, DEFAULT_GAS_URL

# شيت الأرشيف الخام المركزي لمنظومة NSW (1v1V4 - الورقة1)
RAW_ARCHIVE_SPREADSHEET_ID = "1v1V4_rQukDs3oCe8Z4Izvni3uCx91iKmSVNOm4A3mH0"

# استيراد طبقة قاعدة البيانات
from database import (
    get_domain_config,
    save_domain_config,
    get_or_create_novel,
    sync_chapter_manifest,
    save_chapter_content,
    get_chapters,
    get_novel_by_id,
    get_novel_by_title,
    get_novel_stats,
    compare_chapter_contents,
    compare_and_replace_chapter_content,
    get_truncated_chapters
)



def extract_clean_domain(url: str) -> str:
    """استخراج اسم النطاق الصافي من الرابط (مثل: example.com)."""
    try:
        ext = tldextract.extract(url)
        if ext.domain and ext.suffix:
            return f"{ext.domain}.{ext.suffix}".lower()
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except Exception:
        parsed = urlparse(url)
        return parsed.netloc.lower() or "unknown_domain"


def check_cdp_available(cdp_url: str = "http://localhost:9222") -> bool:
    """التحقق السريع مما إذا كان متصفح Chrome يعمل مع منفذ تصحيح الأخطاء CDP."""
    try:
        clean_url = cdp_url.rstrip("/")
        res = requests.get(f"{clean_url}/json/version", timeout=1.5)
        return res.status_code == 200
    except Exception:
        return False


class PlaywrightStealthBrowser:
    """إدارة جلسة متصفح Chromium مع إعدادات تخطي الكشف والـ Stealth المتقدمة."""

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    ]

    def __init__(self, headless: bool = True, timeout: int = 35000, cdp_url: Optional[str] = None):
        self.headless = headless
        self.timeout = timeout
        self.cdp_url = cdp_url
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def start(self):
        """تشغيل المتصفح وتجهيز بيئة الـ Stealth أو الاتصال بـ CDP."""
        if sys.platform == "win32":
            try:
                asyncio.set_event_loop(None)
            except Exception:
                pass

        self.playwright = sync_playwright().start()

        if self.cdp_url:
            # الاتصال بمتصفح Chrome البشري المفتوح عبر بروتوكول CDP
            self.browser = self.playwright.chromium.connect_over_cdp(self.cdp_url)
            self.context = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
            return
        
        # خيارات تشغيل متقدمة لإلغاء بصمة الروبوت
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--no-first-run",
            "--no-zygote",
            "--disable-gpu",
            "--window-size=1920,1080",
        ]

        self.browser = self.playwright.chromium.launch(
            headless=self.headless,
            args=launch_args
        )

        user_agent = random.choice(self.USER_AGENTS)
        self.context = self.browser.new_context(
            user_agent=user_agent,
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=1,
            has_touch=False,
            is_mobile=False,
            java_script_enabled=True,
            locale="en-US,en;q=0.9,ar;q=0.8",
            timezone_id="America/New_York",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Sec-Ch-Ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            }
        )

        # حقن سكربتات لتزييف البصمات وإلغاء متغير webdriver
        self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en', 'ar']
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            window.chrome = {
                runtime: {}
            };
        """)

        # محاولة تطبيق مكتبة playwright_stealth إذا كانت متوفرة
        try:
            from playwright_stealth import stealth_sync
            page = self.context.new_page()
            stealth_sync(page)
            page.close()
        except Exception:
            pass

    def get_page_html(self, url: str, wait_selector: Optional[str] = None) -> Tuple[str, str]:
        """
        فتح الرابط وجلب محتوى الـ HTML وعنوان الصفحة:
        يستخدم Fast HTTP Request أولاً لتوفير موارد السيرفر والسرعة الفائقة،
        ويتحول تلقائياً إلى متصفح Playwright الكامل في حال الحاجة لجافاسكربت.
        """
        parsed_u = urlparse(url)
        referer_val = f"{parsed_u.scheme or 'https'}://{parsed_u.netloc}/" if parsed_u.netloc else "https://www.google.com/"

        # 1. المسار فائق السرعة عبر requests (يوفر 100% من RAM المتصفح ويعمل خلال 0.5 ثانية)
        try:
            req_headers = {
                "User-Agent": random.choice(self.USER_AGENTS),
                "Referer": referer_val,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ar;q=0.6",
                "Sec-Ch-Ua": '"Not/A)Brand";v="8", "Chromium";v="126", "Google Chrome";v="126"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Upgrade-Insecure-Requests": "1"
            }
            resp = requests.get(url, headers=req_headers, timeout=12)
            if resp.status_code == 200 and len(resp.text) > 600:
                # التأكد من خلو الرد من صفحات تحدي Cloudflare
                low_text = resp.text[:1000].lower()
                if "just a moment" not in low_text and "attention required" not in low_text and "cloudflare" not in low_text:
                    soup = BeautifulSoup(resp.text[:3500], "html.parser")
                    pg_title = soup.title.get_text(strip=True) if soup.title else ""
                    return resp.text, pg_title
        except Exception:
            pass

        # 2. المسار الكامل عبر متصفح Playwright مع الـ Stealth
        if not self.context or not self.browser:
            self.start()

        page = self.context.new_page()
        try:
            try:
                page.set_extra_http_headers({
                    "Referer": referer_val,
                    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ar;q=0.6"
                })
            except Exception:
                pass

            # الانتقال إلى الصفحة مع معالجة الوقت المحدد
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
            
            # معالجة تلقائية لتحدي Cloudflare ("Just a moment...")
            for _ in range(8):
                current_title = page.title()
                if "Just a moment" in current_title or "Cloudflare" in current_title or "Attention Required" in current_title:
                    time.sleep(1.0)
                else:
                    break

            if wait_selector:
                try:
                    clean_wait = wait_selector.split(",")[0].strip()
                    if clean_wait:
                        page.wait_for_selector(clean_wait, timeout=3500)
                except Exception:
                    pass

            # تمرير خفيف لمحاكاة المستخدم وتحفيز الـ Lazy Loading
            try:
                page.evaluate("window.scrollBy(0, 500);")
                time.sleep(0.3)
            except Exception:
                pass

            content = page.content()
            title = page.title()
            return content, title
        finally:
            page.close()

    def close(self):
        """إغلاق المتصفح وتنظيف الموارد."""
        try:
            if self.cdp_url:
                # عند الاتصال عبر CDP، نفصل الاتصال فقط ولا نغلق متصفح المشرف الحقيقي
                if self.browser:
                    try:
                        self.browser.close()
                    except Exception:
                        pass
                if self.playwright:
                    try:
                        self.playwright.stop()
                    except Exception:
                        pass
            else:
                if self.context:
                    try:
                        self.context.close()
                    except Exception:
                        pass
                if self.browser:
                    try:
                        self.browser.close()
                    except Exception:
                        pass
                if self.playwright:
                    try:
                        self.playwright.stop()
                    except Exception:
                        pass
        except Exception:
            pass


# ==============================================================================
# معالجة وتنظيف نصوص الفصول (HTML Content Cleaning Pipeline)
# ==============================================================================

def clean_chapter_content(
    raw_html: str,
    content_selector: str,
    purge_selectors: List[str]
) -> str:
    """
    استخراج وتصفية نص الفصل:
    1. استهداف حاوية المحتوى المحددة بـ `content_selector`.
    2. حذف العناصر المحددة في `purge_selectors` والوسوم المزعجة.
    3. تحويل الفقرات وفواصل الأسطر إلى نص نظيف مفصول بأسطر مزدوجة.
    """
    if not raw_html:
        return ""

    try:
        soup = BeautifulSoup(raw_html, "lxml")
    except Exception:
        soup = BeautifulSoup(raw_html, "html.parser")
    
    # العثور على حاوية المحتوى الرئيسية
    container = None
    if content_selector and content_selector.strip():
        try:
            container = soup.select_one(content_selector)
        except Exception:
            container = None

    if not container:
        # كخيار احتياطي: محاولة البحث في وسوم عامة أو الاعتماد على الحاوية الجذرية
        container = (
            soup.select_one("article") or 
            soup.select_one(".entry-content") or 
            soup.select_one("#content") or 
            soup.body or 
            soup
        )

    if not container:
        return ""

    # حذف العناصر الشائعة المزعجة بشكل افتراضي
    default_purge = [
        "script", "style", "noscript", "iframe", "svg", "button", 
        "nav", "header", "footer", ".ad", ".ads", ".advertisement", 
        ".share", ".social", ".comments", ".pagination", ".pager"
    ]
    for tag_name in default_purge:
        for item in container.select(tag_name):
            item.decompose()

    # حذف العناصر المحددة من خلال Gemini / المستخدم
    for sel in purge_selectors:
        sel = sel.strip()
        if sel:
            try:
                for bad_item in container.select(sel):
                    bad_item.decompose()
            except Exception:
                pass

    # معالجة وسوم الفقرات وفواصل الأسطر <br>, <p>, <div>
    for br in container.find_all("br"):
        br.replace_with("\n")

    for p in container.find_all(["p", "div", "blockquote"]):
        p.insert_after("\n\n")

    # استخراج النص النظيف
    text = container.get_text()
    
    # فك تشفير كيانات HTML مثل &nbsp; و &amp;
    text = html.unescape(text)

    # تنظيف وتنسيق الأسطر والفقرات
    paragraphs = []
    for raw_para in text.split("\n"):
        clean_para = raw_para.strip()
        # تصفية الأسطر الفارغة وإعلانات الووترمارك الشائعة
        if clean_para:
            # إزالة المسافات المتعددة داخل السطر
            clean_para = re.sub(r"[ \t]+", " ", clean_para)
            paragraphs.append(clean_para)

    # دمج الفقرات بأسطر مزدوجة نظيفة
    formatted_content = "\n\n".join(paragraphs)
    return formatted_content


def extract_chapter_title(
    raw_html: str,
    title_selector: str,
    fallback_number: int = 1
) -> str:
    """استخراج عنوان الفصل الصافي مع دعم العناوين الرقمية وتوفير بديل ذكي."""
    if not raw_html:
        return f"الفصل {fallback_number}"

    soup = BeautifulSoup(raw_html, "lxml") if "lxml" in raw_html else BeautifulSoup(raw_html, "html.parser")
    title_elem = soup.select_one(title_selector) if title_selector else None

    if title_elem:
        raw_title = title_elem.get_text(strip=True)
        if raw_title:
            clean_title = re.sub(r"\s+", " ", raw_title).strip()
            # إذا كان العنوان رقماً بحتاً (مثل 1) نحوله إلى صيغة فصل واضحة
            if re.match(r"^\d+$", clean_title):
                return f"الفصل {clean_title}"
            return clean_title

    # محاولة استخراج العنوان من وسم <title>
    if soup.title and soup.title.string:
        page_title = soup.title.string.strip()
        # تنظيف لواحق المواقع مثل "- Read Novel Online"
        clean_title = re.split(r"[-–|—]", page_title)[0].strip()
        if clean_title:
            if re.match(r"^\d+$", clean_title):
                return f"الفصل {clean_title}"
            return clean_title

    return f"الفصل {fallback_number}"


# ==============================================================================
# زاحف الفهرس وقائمة الفصول (TOC Crawler)
# ==============================================================================

def normalize_toc_url(url: str) -> str:
    """تحويل روابط الفهارس الشائعة إلى الرابط الكامل للفصول (مثل 69shuba و novel543)."""
    # موقع 69shuba: تحويل /book/123.htm إلى /book/123/
    if "69shuba.com/book/" in url and url.endswith(".htm"):
        clean_id = re.search(r"/book/(\d+)\.htm", url)
        if clean_id:
            return f"https://www.69shuba.com/book/{clean_id.group(1)}/"
    # موقع novel543: التأكد أن الرابط ينتهي بـ /dir
    if "novel543.com" in url:
        url = url.rstrip("/")
        if not url.endswith("/dir"):
            m = re.search(r"novel543\.com/(\d+)$", url)
            if m:
                url = url + "/dir"
    return url


def crawl_toc_chapters(
    toc_url: str,
    toc_link_selector: str,
    browser_instance: Optional[PlaywrightStealthBrowser] = None,
    cdp_url: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], str]:
    """
    سحب صفحة الفهرس واستخراج كافة روابط الفصول وترتيبها تصاعدياً من الفصل الأول إلى الأخير:
    ترجع قائمة الفصول وعنوان الرواية. يدعم جسر متصفح المشرف المفتوح (CDP) لتجاوز حماية Cloudflare.
    """
    # 🌟 دعم مباشر لمنصة botitranslation.com عبر واجهة REST API
    if "botitranslation.com" in toc_url or "mystorywave.com" in toc_url:
        m_b = re.search(r"/(?:book|chapters)/(\d+)", toc_url)
        if m_b:
            b_id = m_b.group(1)
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Referer": "https://botitranslation.com/"}
                # جلب معلومات الرواية
                b_title = "رواية"
                try:
                    b_info = requests.get(f"https://api.mystorywave.com/story-wave-backend/api/v1/content/books/{b_id}", headers=headers, timeout=20).json()
                    b_title = (b_info.get("data") or {}).get("bookName") or "رواية"
                except Exception:
                    pass

                if b_title == "رواية":
                    m_slug = re.search(r"/book/\d+-([^/?#]+)", toc_url)
                    if m_slug:
                        b_title = m_slug.group(1).replace("-", " ").title()

                # جلب كافة الفصول عبر الصفحات بسرعة مع pageSize=100
                page_num = 1
                api_chaps = []
                while page_num <= 100:
                    api_url = f"https://api.mystorywave.com/story-wave-backend/api/v1/content/chapters/page?bookId={b_id}&pageNumber={page_num}&pageSize=100"
                    r_api = requests.get(api_url, headers=headers, timeout=20).json()
                    c_data = r_api.get("data", {})
                    c_list = c_data.get("list", [])
                    if not c_list:
                        break
                    api_chaps.extend(c_list)
                    total_pages = c_data.get("totalPages", 1)
                    if page_num >= total_pages:
                        break
                    page_num += 1

                # ترتيب الفصول تصاعدياً من 1 فصاعداً
                api_chaps.sort(key=lambda x: x.get("chapterOrder", 0))
                structured = []
                for item in api_chaps:
                    c_order = item.get("chapterOrder", 0)
                    c_id = item.get("id")
                    c_title = item.get("title", f"الفصل {c_order}").strip()
                    structured.append({
                        "chapter_number": c_order,
                        "title": c_title,
                        "url": f"https://api.mystorywave.com/story-wave-backend/api/v1/content/chapters/{c_id}"
                    })
                if structured:
                    logger.info(f"[botitranslation API] Extracted {len(structured)} chapters directly via API for book: {b_title}")
                    return structured, b_title
            except Exception as e_boti:
                logger.warning(f"Error fetching botitranslation API: {e_boti}")

    normalized_url = normalize_toc_url(toc_url)
    should_close_browser = False
    
    # تحديد المنفذ إن توفر جسر CDP
    target_cdp = cdp_url
    if not target_cdp and check_cdp_available("http://localhost:9222"):
        target_cdp = "http://localhost:9222"

    if browser_instance is None:
        browser_instance = PlaywrightStealthBrowser(headless=(target_cdp is None), cdp_url=target_cdp)
        browser_instance.start()
        should_close_browser = True

    try:
        html_content, page_title = browser_instance.get_page_html(normalized_url, wait_selector=toc_link_selector)
        
        # فحص وجود حماية Cloudflare ومحاولة التحويل التلقائي لجسر CDP إن كان متاحاً
        if ("Just a moment" in page_title or "challenge-platform" in html_content) and not target_cdp and check_cdp_available("http://localhost:9222"):
            if should_close_browser:
                browser_instance.close()
            target_cdp = "http://localhost:9222"
            browser_instance = PlaywrightStealthBrowser(headless=False, cdp_url=target_cdp)
            browser_instance.start()
            should_close_browser = True
            html_content, page_title = browser_instance.get_page_html(normalized_url, wait_selector=toc_link_selector)

        soup = BeautifulSoup(html_content, "lxml") if "lxml" in html_content else BeautifulSoup(html_content, "html.parser")

        links = soup.select(toc_link_selector) if toc_link_selector else []
        if not links:
            links = soup.find_all("a", href=re.compile(r"(chapter|ch-|\bch\d+|\bchap\b|/txt/)", re.IGNORECASE))

        # دعم ميزة التعرف على الفصول الرقمية البحتة (Pure Numeric Recognition):
        # 1. فحص إذا كان الرابط يحتوي على معرف الرواية الرقمي مثل /1010605889/dir أو novel543
        if not links:
            book_id_match = re.search(r"/(\d{5,})", normalized_url)
            if book_id_match:
                b_id = book_id_match.group(1)
                links = soup.find_all("a", href=re.compile(rf"/{b_id}/\d+"))

        # 2. البحث داخل حاويات الفهارس الشائعة
        if not links:
            for container_sel in [
                ".chaplist a", ".chaplist", ".dir-list", "#dir", ".chapter-list", ".list", "#list", 
                ".mulu", ".zjlist", "dl.chapterlist dd a", "dd a", 
                ".catalog", "ul.chapters", "#chapterlist", ".read-list"
            ]:
                candidate = soup.select(container_sel + " a" if " a" not in container_sel else container_sel)
                if candidate and len(candidate) > 2:
                    links = candidate
                    break

        # 3. البحث عن أي روابط تنتهي بمسارات رقمية (مثل /12345 أو 12345.html)
        if not links:
            links = soup.find_all("a", href=re.compile(r"/\d+(?:\.html)?(?:[?#].*)?$"))

        # 4. البحث عن روابط نصوصها أرقام فقط (مثال: <a>1</a>، <a>2</a>)
        if not links:
            all_a = soup.find_all("a", href=True)
            num_links = [a for a in all_a if re.match(r"^\s*\d+\s*$", a.get_text(strip=True))]
            if len(num_links) > 2:
                links = num_links

        raw_chapters = []
        seen_urls = set()

        for a_tag in links:
            href = a_tag.get("href")
            if not href:
                continue

            full_url = urljoin(normalized_url, href)
            # تجنب تكرار الروابط وتجنب روابط الرئيسية وصفحات الكتب
            if full_url in seen_urls or full_url.rstrip("/").endswith((".com", ".net", ".org", "book", "index")):
                continue
            # تجنب روابط صفحة الفهرس نفسها
            if full_url.rstrip("/").endswith("/dir"):
                continue
            seen_urls.add(full_url)

            link_text = a_tag.get_text(strip=True) or a_tag.get("title", "").strip()
            # تجاهل الروابط الفارغة أو التي تخص تسجيل الدخول
            if len(link_text) < 1 or "login" in link_text.lower() or "register" in link_text.lower():
                continue

            raw_chapters.append({
                "url": full_url,
                "title": link_text
            })

        # تنظيف عنوان الرواية من عنوان الصفحة
        novel_title = re.split(r"[-–|—]", page_title)[0].strip() or "رواية غير معنونة"

        # ترقيم الفصول تتابعياً مع التعرف الذكي على الفصول الرقمية (بدون كلمة فصل)
        structured_chapters = []
        for idx, item in enumerate(raw_chapters, start=1):
            raw_t = item["title"].strip()
            parsed_num = None
            clean_title = raw_t

            # النمط 1: الفصول الصينية 第1章 أو 第 1 节
            m_cn = re.search(r"第\s*(\d+)\s*[章节回]", raw_t)
            if m_cn:
                parsed_num = int(m_cn.group(1))
            else:
                # النمط 2: كلمة فصل أو Chapter متبوعة برقم
                m_word = re.search(r"(?:chapter|chap|ch\.?|الفصل|فصل)\s*(\d+)", raw_t, re.IGNORECASE)
                if m_word:
                    parsed_num = int(m_word.group(1))
                else:
                    m_url = re.search(r"_(\d+)\.html|\b(\d+)\.html|/chapter/(\d+)", item["url"])
                    if m_url:
                        parsed_num = int(m_url.group(1) or m_url.group(2) or m_url.group(3))

            # النمط 4: فحص نهاية الرابط لاستخراج رقم تسلسلي معقول (< 20000)
            if parsed_num is None:
                m_url_seq = re.search(r"/(\d{1,5})(?:\.html)?$", item["url"])
                if m_url_seq:
                    candidate_val = int(m_url_seq.group(1))
                    if 1 <= candidate_val <= 20000:
                        parsed_num = candidate_val
                        if not clean_title or clean_title == raw_t:
                            clean_title = f"الفصل {parsed_num}"

            # إذا لم يُستخرج أي رقم، نعتمد على ترتيب الرابط الفعلي idx
            chap_num = parsed_num if parsed_num is not None else idx
            if not clean_title:
                clean_title = f"الفصل {chap_num}"

            structured_chapters.append({
                "chapter_number": chap_num,
                "url": item["url"],
                "title": clean_title
            })

        # ترتيب الفصول تصاعدياً بشكل دقيق حسب رقم الفصل
        if len(structured_chapters) > 1:
            structured_chapters.sort(key=lambda x: x["chapter_number"])

        return structured_chapters, novel_title
    finally:
        if should_close_browser:
            browser_instance.close()


def fetch_samples_for_gemini_analysis(
    toc_url: str,
    browser_instance: Optional[PlaywrightStealthBrowser] = None,
    cdp_url: Optional[str] = None
) -> Tuple[str, str, str]:
    """
    جلب عينة HTML لصفحة الفهرس وعينة HTML لأول فصل لاكتشاف الـ Selectors عبر Gemini:
    يدعم المواقع ذات الروابط الرقمية كـ novel543.com.
    ترجع (toc_html, sample_chapter_html, novel_title).
    تدعم جسر متصفح المشرف المفتوح (CDP) لتجاوز حماية Cloudflare.
    """
    normalized_url = normalize_toc_url(toc_url)
    should_close_browser = False

    target_cdp = cdp_url
    if not target_cdp and check_cdp_available("http://localhost:9222"):
        target_cdp = "http://localhost:9222"

    if browser_instance is None:
        browser_instance = PlaywrightStealthBrowser(headless=(target_cdp is None), cdp_url=target_cdp)
        browser_instance.start()
        should_close_browser = True

    try:
        # 1. جلب صفحة الفهرس
        toc_html, page_title = browser_instance.get_page_html(normalized_url)

        # فحص وجود حماية Cloudflare ومحاولة التحويل التلقائي لجسر CDP إن كان متاحاً
        if ("Just a moment" in page_title or "challenge-platform" in toc_html) and not target_cdp and check_cdp_available("http://localhost:9222"):
            if should_close_browser:
                browser_instance.close()
            target_cdp = "http://localhost:9222"
            browser_instance = PlaywrightStealthBrowser(headless=False, cdp_url=target_cdp)
            browser_instance.start()
            should_close_browser = True
            toc_html, page_title = browser_instance.get_page_html(normalized_url)

        novel_title = re.split(r"[-–|—]", page_title)[0].strip() or "رواية جديدة"

        # محاولة ذكية للعثور على أول رابط فصل داخل صفحة الفهرس
        soup = BeautifulSoup(toc_html, "lxml") if "lxml" in toc_html else BeautifulSoup(toc_html, "html.parser")
        
        sample_chapter_url = None
        # البحث عن روابط مرشحة للفصول
        candidate_links = soup.find_all("a", href=re.compile(r"(chapter|ch-|\bch\d+|\bchap\b|read)", re.IGNORECASE))
        for a in candidate_links:
            href = a.get("href")
            if href and not href.startswith("#") and "javascript:" not in href:
                sample_chapter_url = urljoin(toc_url, href)
                break

        # Fallback للمواقع الرقمية و novel543.com
        if not sample_chapter_url:
            book_id_match = re.search(r"/(\d{5,})", normalized_url)
            if book_id_match:
                b_id = book_id_match.group(1)
                num_links = soup.find_all("a", href=re.compile(rf"/{b_id}/\d+"))
                for a in num_links:
                    href = a.get("href")
                    if href and not href.endswith("/dir"):
                        sample_chapter_url = urljoin(toc_url, href)
                        break

        # البحث داخل حاويات الفهارس الشائعة
        if not sample_chapter_url:
            for container_sel in [".dir-list a", ".chapter-list a", "#list a", "dd a", ".catalog a", ".mulu a"]:
                c_links = soup.select(container_sel)
                for a in c_links:
                    href = a.get("href")
                    if href and not href.endswith("/dir") and not href.startswith("#"):
                        sample_chapter_url = urljoin(toc_url, href)
                        break
                if sample_chapter_url:
                    break

        # إذا لم نجد رابطاً صريحاً، نأخذ أي رابط رقمي صالح
        if not sample_chapter_url:
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href and not href.startswith("#") and len(href) > 3 and "home" not in href.lower() and not href.endswith("/dir"):
                    sample_chapter_url = urljoin(toc_url, href)
                    break

        chapter_html = ""
        if sample_chapter_url:
            try:
                chapter_html, _ = browser_instance.get_page_html(sample_chapter_url)
            except Exception:
                chapter_html = ""

        return toc_html, chapter_html, novel_title
    finally:
        if should_close_browser:
            browser_instance.close()


# ==============================================================================
# تفريغ وضخ الفصول في شيت الأرشيف (Sheet 1v1V4 Streamer)
# ==============================================================================

def upload_single_chapter_to_sheet(
    novel_name: str,
    chapter_number: int,
    title: str,
    content: str,
    source_url: str = ""
) -> bool:
    """
    ضخ الفصل فورياً ومباشرة إلى جدول شيت الأرشيف الخام (1v1V4 - الورقة1).
    الأعمدة المعتمدة: [ChapterNum, RawContent, NovelName, CreatedAt, SourceUrl]
    """
    if not content or len(content.strip()) < 50:
        return False

    # توثيق التوقيت بتوقيت بغداد الصارم (UTC+3)
    tz_baghdad = timezone(timedelta(hours=3))
    created_at = datetime.now(tz_baghdad).strftime("%Y-%m-%d %H:%M:%S")

    payload = {
        "action": "pushToRawArchive",
        "spreadsheetId": RAW_ARCHIVE_SPREADSHEET_ID,
        "sheetName": "الورقة1",
        "novel_name": novel_name,
        "novelName": novel_name,
        "chapter_number": chapter_number,
        "chapterNumber": chapter_number,
        "title": title,
        "content": content,
        "rawText": content,
        "source_url": source_url,
        "sourceUrl": source_url,
        "createdAt": created_at,
        "row": [chapter_number, content, novel_name, created_at, source_url]
    }

    # المحاولة عبر مجمع وسائط Google Apps Script مع تجاوز الأخطاء تلقائياً
    endpoints = list(DEFAULT_GAS_POOL) if DEFAULT_GAS_POOL else [DEFAULT_GAS_URL]
    for url in endpoints:
        try:
            res = requests.post(url, json=payload, timeout=25)
            if res.status_code == 200:
                try:
                    data = res.json()
                    if data.get("status") == "success" or data.get("success") is True or data.get("chapter"):
                        return True
                except Exception:
                    if "success" in res.text.lower() or "ok" in res.text.lower():
                        return True
        except Exception:
            continue

    return False


def calculate_missing_gaps(existing_nums: List[Any], total_chapters: Optional[int] = None) -> Tuple[List[Dict[str, Any]], List[int]]:
    """
    اكتشاف الفجوات الترقيمية والفصول غير المنزلة واقتراح تنزيلها:
    مثال: إذا كانت الفصول الموجودة 4 و6 و8 و12 بإجمالي 20:
    تكتشف أن الفجوات هي: 1-3، 5، 7، 9-11، 13-20.
    """
    if not existing_nums:
        if total_chapters and total_chapters > 0:
            return [{"from": 1, "to": total_chapters, "label": f"1-{total_chapters}"}], list(range(1, total_chapters + 1))
        return [], []

    clean_nums = set()
    for n in existing_nums:
        try:
            m = re.search(r"(\d+(?:\.\d+)?)", str(n))
            if m:
                clean_nums.add(int(float(m.group(1))))
        except Exception:
            continue

    if not clean_nums:
        if total_chapters and total_chapters > 0:
            return [{"from": 1, "to": total_chapters, "label": f"1-{total_chapters}"}], list(range(1, total_chapters + 1))
        return [], []

    sorted_existing = sorted(list(clean_nums))
    max_ch = sorted_existing[-1]
    end_limit = max(max_ch, total_chapters or max_ch)

    all_possible = set(range(1, end_limit + 1))
    missing_set = sorted(list(all_possible - clean_nums))

    if not missing_set:
        return [], []

    ranges = []
    range_start = missing_set[0]
    prev = missing_set[0]

    for curr in missing_set[1:]:
        if curr == prev + 1:
            prev = curr
        else:
            label = f"{range_start}" if range_start == prev else f"{range_start}-{prev}"
            ranges.append({"from": range_start, "to": prev, "label": label})
            range_start = curr
            prev = curr

    label = f"{range_start}" if range_start == prev else f"{range_start}-{prev}"
    ranges.append({"from": range_start, "to": prev, "label": label})

    return ranges, missing_set


def trigger_cloud_sheet_sorting() -> Dict[str, Any]:
    """
    إرسال طلب فوري إلى وسيط Google Apps Script لتشغيل فرز وتنظيف وتصفية الجداول الثلاثة:
    (1v1V4 للأرشيف، 1Fceh للترجمة، 1HDj للنشر).
    """
    payload = {
        "action": "sortAndDeduplicateAllSheets"
    }
    endpoints = list(DEFAULT_GAS_POOL) if DEFAULT_GAS_POOL else [DEFAULT_GAS_URL]
    for url in endpoints:
        try:
            res = requests.post(url, json=payload, timeout=45)
            if res.status_code == 200:
                try:
                    return res.json()
                except Exception:
                    return {"status": "success", "raw_response": res.text[:200]}
        except Exception:
            continue
    return {"status": "failed", "error": "تعذر الاتصال بجميع روابط مجمع Google Apps Script"}


# ==============================================================================
# محرك السحب التتابعي والهجين للفصول (NSW Hybrid Scraper Engine)
# ==============================================================================

class NovelScrapingSession:
    """
    متحكم جلسة السحب الهجين (NSW Hybrid Scraper Engine):
    - يدير السحب المتوازي (3 خيوط متزامنة).
    - يدعم الاتصال المباشر بمتصفح المشرف المفتوح عبر بروتوكول CDP (منفذ 9222) لتخطي Cloudflare / Turnstile.
    - يدعم دورة الاستدراك التلقائية (Retry Pass) حتى 3 دورات للفصول المتعثرة.
    - يضخ الفصول فورياً في شيت الأرشيف الخام (1v1V4) مع ترتيب تسلسلي رياضي صارم.
    - يفرغ الذاكرة فور نجاح الضخ لحماية موارد السيرفر والحاسوب.
    """

    def __init__(
        self,
        novel_id: Optional[int] = None,
        novel_name: Optional[str] = None,
        domain_config: Optional[Dict[str, Any]] = None,
        min_delay: float = 1.0,
        max_delay: float = 2.5,
        headless: bool = True,
        cdp_url: Optional[str] = None,
        auto_stream_to_sheet: bool = True,
        workers_count: int = 3,
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ):
        self.novel_id = novel_id
        self.novel_name = novel_name
        self.domain_config = domain_config or {}
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.headless = headless
        self.cdp_url = cdp_url
        if not self.cdp_url and check_cdp_available("http://localhost:9222"):
            self.cdp_url = "http://localhost:9222"

        if self.cdp_url:
            self.headless = False
            self.workers_count = min(workers_count, 2)
        else:
            self.workers_count = workers_count

        self.auto_stream_to_sheet = auto_stream_to_sheet
        self.log_callback = log_callback or (lambda msg: None)
        self.progress_callback = progress_callback or (lambda current, total, status: None)
        
        self.is_paused = False
        self.is_stopped = False
        self.processed_count = 0
        self._lock = threading.Lock()

        # مزامنة اسم ومعرف الرواية وإعدادات الدومين تلقائياً
        if self.novel_id and not self.novel_name:
            db_nov = get_novel_by_id(self.novel_id)
            if db_nov:
                self.novel_name = db_nov.get("title", "")
                if not self.domain_config:
                    self.domain_config = get_domain_config(db_nov.get("domain", "")) or {}
        elif self.novel_name and not self.novel_id:
            db_nov = get_novel_by_title(self.novel_name)
            if db_nov:
                self.novel_id = db_nov["id"]
                if not self.domain_config:
                    self.domain_config = get_domain_config(db_nov.get("domain", "")) or {}

        if not self.novel_name:
            self.novel_name = "رواية عامة"

    def log(self, message: str):
        """تسجيل رسالة في كونسول السجلات بتوقيت بغداد."""
        tz_baghdad = timezone(timedelta(hours=3))
        now = datetime.now(tz_baghdad).strftime("%H:%M:%S")
        formatted = f"[{now}] {message}"
        self.log_callback(formatted)

    def pause(self):
        """إيقاف مؤقت للسحب."""
        self.is_paused = True
        self.log("⏸️ تم تفعيل الإيقاف المؤقت...")

    def resume(self):
        """استئناف السحب."""
        self.is_paused = False
        self.log("▶️ تم استئناف السحب...")

    def toggle_pause(self):
        """التبديل بين الإيقاف المؤقت والاستئناف."""
        if self.is_paused:
            self.resume()
        else:
            self.pause()

    def stop(self):
        """إلغاء وإيقاف السحب بالكامل."""
        self.is_stopped = True
        self.log("⏹️ تم طلب إيقاف عملية السحب.")

    def run_range(self, from_chapter: int = 1, to_chapter: int = 1, chapter_numbers: Optional[List[int]] = None):
        """
        تنفيذ عملية سحب الفصول في النطاق المحدد عبر مسار متوازي (3 Workers)،
        مع دورة استدراك تلقائية للفصول المتعثرة وضخ فوري في شيت 1v1V4 بالترتيب الرياضي الصارم.
        """
        if not self.novel_id:
            self.log("❌ خطأ: لم يتم العثور على معرف الرواية (novel_id).")
            return

        chapters_to_scrape = get_chapters(self.novel_id, from_chapter=from_chapter, to_chapter=to_chapter)
        total_in_range = len(chapters_to_scrape)

        if total_in_range == 0:
            self.log("⚠️ لم يتم العثور على أي فصول في هذا النطاق أو الأرقام المحددة.")
            return

        mode_desc = "جسر التصفح المفتوح (CDP Port 9222)" if self.cdp_url else f"السحب السحابي التلقائي ({self.workers_count} خيوط متوازية)"
        self.log(f"🚀 بدء سحب {total_in_range} فصلاً (من {from_chapter} إلى {to_chapter}) عبر {mode_desc}...")

        title_sel = self.domain_config.get("chapter_title_selector", "")
        content_sel = self.domain_config.get("chapter_content_selector", "")
        purge_sels = self.domain_config.get("purge_selectors", [])

        # قفل ومخزن الترتيب الرياضي الصارم للضخ في شيت 1v1V4
        stream_lock = threading.Lock()
        buffered_ready: Dict[int, Dict[str, Any]] = {}
        processed_count = 0
        next_to_stream = from_chapter

        def _flush_sequenced_buffer():
            nonlocal next_to_stream
            with stream_lock:
                while next_to_stream in buffered_ready:
                    item = buffered_ready.pop(next_to_stream)
                    ch_num = item["chapter_number"]
                    clean_content = item.get("content", "")
                    ch_title = item.get("title", f"الفصل {ch_num}")
                    ch_url = item.get("url", "")

                    if self.auto_stream_to_sheet and clean_content and len(clean_content) >= 50:
                        stream_ok = upload_single_chapter_to_sheet(
                            novel_name=self.novel_name,
                            chapter_number=ch_num,
                            title=ch_title,
                            content=clean_content,
                            source_url=ch_url
                        )
                        if stream_ok:
                            self.log(f"☁️ [ضخ سحابي]: تم ضخ الفصل {ch_num} بنجاح لشيت الأرشيف (1v1V4).")
                        else:
                            self.log(f"⚠️ تعذر ضخ الفصل {ch_num} لشيت الأرشيف.")

                    # تفريغ الذاكرة فور نجاح الضخ لحماية موارد السيرفر
                    del item
                    next_to_stream += 1

        def _worker_thread(worker_id: int):
            nonlocal processed_count
            if sys.platform == "win32":
                try:
                    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                except Exception:
                    pass

            try:
                with PlaywrightStealthBrowser(headless=self.headless, cdp_url=self.cdp_url) as browser:
                    while not task_queue.empty() and not self.is_stopped:
                        while self.is_paused and not self.is_stopped:
                            time.sleep(0.5)

                        try:
                            ch = task_queue.get_nowait()
                        except queue.Empty:
                            break

                        ch_num = ch["chapter_number"]
                        ch_url = ch["url"]
                        cached_status = ch.get("status")
                        cached_content = (ch.get("content") or "").strip()
                        is_suspiciously_short = (len(cached_content) < 3000)

                        # تخطي إذا كان محملاً مسبقاً ولديه محتوى كافٍ وغير مجتزأ
                        if cached_status == "downloaded" and cached_content and len(cached_content) >= 50 and not is_suspiciously_short:
                            self.log(f"⚡ الفصل {ch_num} مخزن مسبقاً وبحجم كامل ({len(cached_content)} حرف) - تم التخطي.")
                            with stream_lock:
                                processed_count += 1
                                buffered_ready[ch_num] = {
                                    "chapter_number": ch_num,
                                    "title": ch.get("title") or f"الفصل {ch_num}",
                                    "content": cached_content,
                                    "url": ch_url
                                }
                            self.progress_callback(processed_count, total_in_range, f"تم التخطي (مخزن كامل): فصل {ch_num}")
                            _flush_sequenced_buffer()
                            task_queue.task_done()
                            continue
                        elif cached_status == "downloaded" and is_suspiciously_short:
                            self.log(f"🔍 الفصل {ch_num} مخزن ولكن يبدو مقتطعاً ({len(cached_content)} حرف) - جاري إعادة سحبه ومقارنة المحتوى...")

                        self.log(f"📥 [خيط {worker_id}]: جاري سحب الفصل {ch_num} من: {ch_url}")
                        self.progress_callback(processed_count, total_in_range, f"جاري سحب فصل {ch_num}...")

                        try:
                            raw_html, _ = browser.get_page_html(ch_url, wait_selector=content_sel)

                            # رصد حظر Cloudflare
                            if any(k in raw_html for k in ["Just a moment...", "Attention Required", "Cloudflare to restrict access", "cf-browser-verification"]):
                                raise RuntimeError("حظر حماية Cloudflare (تحدي كابتشا أو 403)")

                            ch_title = extract_chapter_title(raw_html, title_sel, fallback_number=ch_num)
                            clean_content = clean_chapter_content(raw_html, content_sel, purge_sels)

                            if not clean_content or len(clean_content) < 50:
                                raise ValueError("لم يتم استخراج محتوى كافٍ من الصفحة (> 50 حرفاً).")

                            # مقارنة المحتوى مع المخزن مسبقاً واستبدال المجتزأ فوراً في SQLite
                            comp = compare_and_replace_chapter_content(
                                novel_id=self.novel_id,
                                chapter_number=ch_num,
                                original_content=clean_content,
                                original_title=ch_title,
                                original_url=ch_url
                            )

                            words_count = len(clean_content.split())
                            if comp.get("replaced") and comp.get("action") == "updated_replaced":
                                self.log(f"🔄 [استبدال المحتوى المجتزئ]: تم استبدال وتحديث الفصل {ch_num} بنجاح! ({comp.get('reason')})")
                            else:
                                self.log(f"✅ [خيط {worker_id}]: تم حفظ الفصل {ch_num}: '{ch_title}' بنجاح ({words_count} كلمة).")

                            with stream_lock:
                                processed_count += 1
                                buffered_ready[ch_num] = {
                                    "chapter_number": ch_num,
                                    "title": ch_title,
                                    "content": clean_content,
                                    "url": ch_url
                                }

                            # تفريغ الـ HTML المحلي فورياً لتوفير الذاكرة
                            del raw_html
                            _flush_sequenced_buffer()

                        except Exception as ex:
                            err_msg = str(ex)
                            self.log(f"❌ [خيط {worker_id}]: تعثر سحب الفصل {ch_num}: {err_msg}")
                            save_chapter_content(
                                novel_id=self.novel_id,
                                chapter_number=ch_num,
                                title=ch.get("title") or f"الفصل {ch_num}",
                                content="",
                                status="failed",
                                error_message=err_msg
                            )
                            with stream_lock:
                                processed_count += 1

                        finally:
                            task_queue.task_done()

                        # تأخير بشري خفيف بين الفصول
                        if not self.is_stopped:
                            delay = random.uniform(self.min_delay, self.max_delay)
                            time.sleep(delay)

            except Exception as b_err:
                self.log(f"❌ خطأ مشغل المتصفح [خيط {worker_id}]: {b_err}")

        # الدورة الأساسية: تعبئة الطابور وتشغيل الخيوط
        task_queue = queue.Queue()
        for ch in chapters_to_scrape:
            task_queue.put(ch)

        threads = []
        actual_workers = min(self.workers_count, total_in_range) if total_in_range > 0 else 1
        for w_id in range(1, actual_workers + 1):
            th = threading.Thread(target=_worker_thread, args=(w_id,), daemon=True)
            threads.append(th)
            th.start()

        for th in threads:
            th.join()

        # تفريغ ما تبقى في المخزن التسلسلي
        _flush_sequenced_buffer()

        # =====================================================================
        # دورة الاستدراك التلقائية (Retry Pass) - حتى 3 دورات للفصول المتعثرة
        # =====================================================================
        if not self.is_stopped:
            failed_chapters = [c for c in get_chapters(self.novel_id, from_chapter=from_chapter, to_chapter=to_chapter) if c.get("status") == "failed"]
            retry_pass = 0
            while failed_chapters and retry_pass < 3 and not self.is_stopped:
                retry_pass += 1
                self.log(f"🔄 [دورة الاستدراك {retry_pass}]: إعادة محاولة سحب {len(failed_chapters)} فصول متعثرة...")
                time.sleep(2.0)
                retry_queue = queue.Queue()
                for f_ch in failed_chapters:
                    retry_queue.put(f_ch)
                task_queue = retry_queue

                threads = []
                retry_workers = min(self.workers_count, len(failed_chapters))
                for w_id in range(1, retry_workers + 1):
                    th = threading.Thread(target=_worker_thread, args=(w_id,), daemon=True)
                    threads.append(th)
                    th.start()
                for th in threads:
                    th.join()

                _flush_sequenced_buffer()
                failed_chapters = [c for c in get_chapters(self.novel_id, from_chapter=from_chapter, to_chapter=to_chapter) if c.get("status") == "failed"]

        # =====================================================================
        # رصد التعثر المستمر وتنبيه صمام الأمان على تيليجرام (CDP Alert)
        # =====================================================================
        if not self.is_stopped:
            failed_chapters = [c for c in get_chapters(self.novel_id, from_chapter=from_chapter, to_chapter=to_chapter) if c.get("status") == "failed"]
            if failed_chapters and not self.cdp_url:
                sample_url = failed_chapters[0].get("url", "")
                self.log(f"🚨 تعذر السحب السحابي التلقائي لـ {len(failed_chapters)} فصول بسبب حماية الموقع. جاري تنبيه المشرف عبر تيليجرام لتفعيل جسر CDP...")
                try:
                    import telegram_bot
                    telegram_bot.notify_scraping_blocked(
                        novel_name=self.novel_name,
                        failed_count=len(failed_chapters),
                        source_url=sample_url
                    )
                except Exception as alert_err:
                    self.log(f"⚠️ تعذر إرسال تنبيه تيليجرام: {alert_err}")

        # تفريغ أخير لأي فصول متأخرة في المخزن بالترتيب
        with stream_lock:
            for rem_num in sorted(buffered_ready.keys()):
                item = buffered_ready[rem_num]
                clean_content = item.get("content", "")
                if self.auto_stream_to_sheet and clean_content and len(clean_content) >= 50:
                    upload_single_chapter_to_sheet(
                        novel_name=self.novel_name,
                        chapter_number=rem_num,
                        title=item.get("title", f"الفصل {rem_num}"),
                        content=clean_content,
                        source_url=item.get("url", "")
                    )
            buffered_ready.clear()

        stats = get_novel_stats(self.novel_id)
        self.log(f"🎉 اكتملت معالجة النطاق المطلوب! الفصول المنزلة: {stats.get('downloaded', 0)} | المتعثرة: {stats.get('failed', 0)}.")


# سجل مركزي للمهام الخلفية لتمكين استمرار السحب حتى عند مغادرة المستخدم للصفحة
ACTIVE_BACKGROUND_TASKS: Dict[int, NovelScrapingSession] = {}


def start_background_scraping(
    novel_id: int,
    from_chapter: int,
    to_chapter: int,
    domain_config: Dict[str, Any],
    novel_name: Optional[str] = None,
    chapter_numbers: Optional[List[int]] = None,
    min_delay: float = 0.5,
    max_delay: float = 1.0,
    headless: bool = True,
    cdp_url: Optional[str] = None,
    auto_stream_to_sheet: bool = True,
    workers_count: int = 3
) -> NovelScrapingSession:
    """
    تشغيل سحب الفصول في خيط مستقل بالخلفية (Background Daemon Thread).
    يستمر هذا الخيط في العمل وتخزين الفصول في SQLite وضخها في شيت 1v1V4 حتى لو أغلقت صفحة الويب تماماً.
    """
    if not novel_name:
        nov = get_novel_by_id(novel_id)
        novel_name = nov.get("title", f"رواية #{novel_id}") if nov else f"رواية #{novel_id}"

    session = NovelScrapingSession(
        novel_id=novel_id,
        novel_name=novel_name,
        domain_config=domain_config or {},
        min_delay=min_delay,
        max_delay=max_delay,
        headless=headless,
        cdp_url=cdp_url,
        auto_stream_to_sheet=auto_stream_to_sheet,
        workers_count=workers_count
    )

    ACTIVE_BACKGROUND_TASKS[novel_id] = session

    def _worker():
        if sys.platform == "win32":
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            except Exception:
                pass
        try:
            session.run_range(from_chapter, to_chapter, chapter_numbers=chapter_numbers)
        finally:
            ACTIVE_BACKGROUND_TASKS.pop(novel_id, None)

    th = threading.Thread(target=_worker, daemon=True)
    th.start()
    return session


def scan_and_repair_truncated_chapters(
    novel_id: int,
    from_chapter: Optional[int] = None,
    to_chapter: Optional[int] = None,
    threshold_length: int = 3000,
    cdp_url: Optional[str] = "http://127.0.0.1:9222",
    headless: bool = True,
    auto_stream_to_sheet: bool = True
) -> Dict[str, Any]:
    """
    فحص فصول الرواية واكتشاف أي فصول مجتزأة أو مبتورة وسحبها من المصدر ومقارنتها واستبدالها آلياً، ثم ضخها لشيت الأرشيف (1v1V4).
    """
    novel = get_novel_by_id(novel_id)
    if not novel:
        return {"success": False, "message": "الرواية غير موجودة"}

    cfg = get_domain_config(novel.get("domain", ""))
    novel_name = novel.get("title", f"رواية #{novel_id}")

    truncated_list = get_truncated_chapters(novel_id, threshold_length=threshold_length)
    if from_chapter is not None:
        truncated_list = [c for c in truncated_list if c["chapter_number"] >= from_chapter]
    if to_chapter is not None:
        truncated_list = [c for c in truncated_list if c["chapter_number"] <= to_chapter]

    if not truncated_list:
        return {
            "success": True,
            "repaired_count": 0,
            "message": "لا توجد فصول مقتطعة ضمن النطاق المحدد."
        }

    target_numbers = [c["chapter_number"] for c in truncated_list]
    session = NovelScrapingSession(
        novel_id=novel_id,
        novel_name=novel_name,
        domain_config=cfg,
        headless=headless,
        cdp_url=cdp_url,
        auto_stream_to_sheet=auto_stream_to_sheet,
        workers_count=1
    )
    session.run_range(min(target_numbers), max(target_numbers), chapter_numbers=target_numbers)

    return {
        "success": True,
        "scanned_count": len(target_numbers),
        "repaired_chapters": target_numbers,
        "message": f"تمت معالجة ومقارنة {len(target_numbers)} فصلاً مجتزأً بنجاح."
    }



