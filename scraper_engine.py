# -*- coding: utf-8 -*-
import os
import time
import random
import re
import html
import sys
import asyncio
import threading
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Any, Optional, Tuple, Callable
from bs4 import BeautifulSoup
import tldextract
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

import os
import requests

DEFAULT_GAS_URL = os.getenv("NSW_PUBLISH_WEBAPP_URL", "https://script.google.com/macros/s/AKfycbxqLaqJru1ag-am7G9Mrwy5Nb7HliZlK5vbIEQD9MeV3wOOquNUvz4d7vWEwZxkBI6zIw/exec")

def upload_single_chapter_to_sheet(novel_name: str, chapter_number: int, title: str, content: str, webapp_url: str = DEFAULT_GAS_URL) -> bool:
    """ضخ فصل واحد فورياً في جدول Google Sheet بمجرد سحبه (Streaming 0ms)."""
    payload = {
        "action": "importSingleRawChapter",
        "novelName": novel_name,
        "chapter": {
            "num": chapter_number,
            "title": title or f"الفصل {chapter_number}",
            "content": content
        }
    }
    try:
        res = requests.post(webapp_url, json=payload, timeout=25).json()
        return res.get("status") == "success"
    except Exception as ex:
        print(f"⚠️ خطأ أثناء تدفق الفصل {chapter_number} للشيت: {ex}")
        return False


# حل مشكلة NotImplementedError على ويندوز في بيئات Streamlit
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

# استيراد طبقة قاعدة البيانات
from database import (
    get_domain_config,
    save_domain_config,
    get_or_create_novel,
    sync_chapter_manifest,
    save_chapter_content,
    get_chapters
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


class PlaywrightStealthBrowser:
    """إدارة جلسة متصفح Chromium مع إعدادات تخطي الكشف والـ Stealth المتقدمة."""

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    ]

    def __init__(self, headless: bool = True, timeout: int = 35000):
        self.headless = headless
        self.timeout = timeout
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def start(self):
        """تشغيل المتصفح وتجهيز بيئة الـ Stealth."""
        if sys.platform == "win32":
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except Exception:
                pass

        self.playwright = sync_playwright().start()
        
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
        if not self.context:
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
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
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

    soup = BeautifulSoup(raw_html, "lxml") if "lxml" in raw_html else BeautifulSoup(raw_html, "html.parser")
    
    # العثور على حاوية المحتوى الرئيسية
    container = soup.select_one(content_selector)
    if not container:
        # كخيار احتياطي: محاولة البحث في وسوم عامة كـ article أو main
        container = soup.select_one("article") or soup.select_one(".entry-content") or soup.select_one("#content") or soup.body

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
    browser_instance: Optional[PlaywrightStealthBrowser] = None
) -> Tuple[List[Dict[str, Any]], str]:
    """
    سحب صفحة الفهرس واستخراج كافة روابط الفصول مع التعرف الذكي على الفصول الرقمية:
    يدعم المواقع التي تستخدم أرقاماً فقط بدون كلمة 'فصل' أو 'Chapter' وترتيبها تصاعدياً.
    ترجع قائمة الفصول وعنوان الرواية.
    """
    normalized_url = normalize_toc_url(toc_url)
    should_close_browser = False
    if browser_instance is None:
        browser_instance = PlaywrightStealthBrowser(headless=True)
        browser_instance.start()
        should_close_browser = True

    try:
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
                    # النمط 3: التعرف على الفصول الرقمية البحتة (Pure Numbers)
                    # العنوان عبارة عن رقم فقط مثل "1" أو "2"
                    m_pure_digit = re.match(r"^(\d+)$", raw_t)
                    if m_pure_digit:
                        parsed_num = int(m_pure_digit.group(1))
                        clean_title = f"الفصل {parsed_num}"
                    else:
                        # العنوان يبدأ برقم يليه فاصلة أو عنوان: "1. البداية" أو "001 البداية"
                        m_prefix_digit = re.match(r"^(\d+)[\.\s\:\-、](.*)$", raw_t)
                        if m_prefix_digit:
                            parsed_num = int(m_prefix_digit.group(1))
                            clean_title = f"الفصل {parsed_num}: {m_prefix_digit.group(2).strip()}"

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

        # إزالة التكرارات الناتجة عن مربعات 'أحدث الفصول' وفرز الفصول تصاعدياً من الفصل 1
        if structured_chapters:
            seen_nums = {}
            for ch in structured_chapters:
                num = ch["chapter_number"]
                if num not in seen_nums:
                    seen_nums[num] = ch

            structured_chapters = [seen_nums[k] for k in sorted(seen_nums.keys())]

        return structured_chapters, novel_title
    finally:
        if should_close_browser:
            browser_instance.close()


def fetch_samples_for_gemini_analysis(
    toc_url: str,
    browser_instance: Optional[PlaywrightStealthBrowser] = None
) -> Tuple[str, str, str]:
    """
    جلب عينة HTML لصفحة الفهرس وعينة HTML لأول فصل لاكتشاف الـ Selectors عبر Gemini:
    يدعم المواقع ذات الروابط الرقمية كـ novel543.com.
    ترجع (toc_html, sample_chapter_html, novel_title).
    """
    should_close_browser = False
    if browser_instance is None:
        browser_instance = PlaywrightStealthBrowser(headless=True)
        browser_instance.start()
        should_close_browser = True

    try:
        normalized_url = normalize_toc_url(toc_url)
        # 1. جلب صفحة الفهرس
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
# محرك السحب التتابعي للفصول (Batch Scraping Controller)
# ==============================================================================

class NovelScrapingSession:
    """
    متحكم جلسة السحب:
    يدير حلقة سحب الفصول مع التحديث اللحظي للواجهة، دعم الإيقاف المؤقت، وتخطي الفصول المحفوظة.
    """

    def __init__(
        self,
        novel_id: Optional[int] = None,
        novel_name: str = "رواية عامة",
        domain_config: Optional[Dict[str, Any]] = None,
        min_delay: float = 1.0,
        max_delay: float = 2.0,
        headless: bool = True,
        thread_count: int = 3,
        auto_stream_to_sheet: bool = True,
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ):
        self.novel_id = novel_id
        self.novel_name = novel_name
        self.domain_config = domain_config or {}
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.headless = headless
        self.thread_count = thread_count
        self.auto_stream_to_sheet = auto_stream_to_sheet
        self.log_callback = log_callback or (lambda msg: None)
        self.progress_callback = progress_callback or (lambda current, total, status: None)
        
        self.is_paused = False
        self.is_stopped = False
        self.processed_count = 0
        self._lock = threading.Lock()

    def log(self, message: str):
        """تسجيل رسالة في كونسول السجلات."""
        now = time.strftime("%H:%M:%S")
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

    def stop(self):
        """إلغاء وإيقاف السحب بالكامل."""
        self.is_stopped = True
        self.log("⏹️ تم طلب إيقاف عملية السحب.")

    def run_range(self, from_chapter: int = 1, to_chapter: int = 1, chapter_numbers: Optional[List[int]] = None):
        """
        تنفيذ عملية السحب عبر 3 خطوط متوازية (3 Parallel Workers)
        مع التدفق المباشر فصلاً بفصل إلى Google Sheet وتطهير ذاكرة السيرفر فوراً.
        """
        import queue
        from database import clear_single_chapter_content

        if chapter_numbers and len(chapter_numbers) > 0:
            chapters_to_scrape = get_chapters(self.novel_id, chapter_numbers=chapter_numbers)
        else:
            chapters_to_scrape = get_chapters(self.novel_id, from_chapter=from_chapter, to_chapter=to_chapter)

        total_in_range = len(chapters_to_scrape)

        if total_in_range == 0:
            self.log("⚠️ لم يتم العثور على أي فصول في هذا النطاق أو الأرقام المحددة.")
            return

        workers_count = max(1, min(self.thread_count, 3))
        self.log(f"🚀 [انطلاق 3 خطوط متوازية]: بدء سحب {total_in_range} فصلاً عبر {workers_count} عمال متوازيين مع التدفق الفوري للشيت...")

        title_sel = self.domain_config.get("chapter_title_selector", "")
        content_sel = self.domain_config.get("chapter_content_selector", "")
        purge_sels = self.domain_config.get("purge_selectors", [])

        task_queue = queue.Queue()
        for ch in chapters_to_scrape:
            task_queue.put(ch)

        def _worker_thread(worker_id: int):
            with PlaywrightStealthBrowser(headless=self.headless) as browser:
                while not task_queue.empty() and not self.is_stopped:
                    while self.is_paused and not self.is_stopped:
                        time.sleep(0.5)
                    if self.is_stopped:
                        break

                    try:
                        ch = task_queue.get_nowait()
                    except queue.Empty:
                        break

                    ch_num = ch["chapter_number"]
                    ch_url = ch["url"]
                    self.log(f"👷 [خيط {worker_id}] ➔ سحب الفصل {ch_num}...")

                    try:
                        raw_html, _ = browser.get_page_html(ch_url, wait_selector=content_sel)
                        ch_title = extract_chapter_title(raw_html, title_sel, fallback_number=ch_num)
                        clean_content = clean_chapter_content(raw_html, content_sel, purge_sels)

                        if not clean_content or len(clean_content) < 50:
                            raise ValueError("المحتوى المستخرج صغير جداً أو محجوب.")

                        # 1. حفظ أولي في SQLite للتأكيد
                        save_chapter_content(
                            novel_id=self.novel_id,
                            chapter_number=ch_num,
                            title=ch_title,
                            content=clean_content,
                            status="downloaded"
                        )

                        # 2. ⚡ التدفق الفوري فصلاً بفصل إلى Google Sheet مباشرة (Streaming)
                        if self.auto_stream_to_sheet:
                            stream_ok = upload_single_chapter_to_sheet(
                                novel_name=self.novel_name,
                                chapter_number=ch_num,
                                title=ch_title,
                                content=clean_content
                            )
                            if stream_ok:
                                try:
                                    clear_single_chapter_content(self.novel_id, ch_num)
                                except Exception:
                                    pass
                                self.log(f"⚡ [خيط {worker_id}] ✅ تم ضخ الفصل {ch_num} في Google Sheet وتطهير ذاكرته بنجاح!")
                            else:
                                self.log(f"ℹ️ [خيط {worker_id}] تم حفظ الفصل {ch_num} محلياً (سيتم رفعه بالدفعة التراكمية).")

                        with self._lock:
                            self.processed_count += 1
                            cnt = self.processed_count
                        self.progress_callback(cnt, total_in_range, f"اكتمل فصل {ch_num} ({cnt}/{total_in_range})")

                    except Exception as ex:
                        err_msg = str(ex)
                        self.log(f"❌ [خيط {worker_id}] تعذر سحب فصل {ch_num}: {err_msg[:60]}")
                        save_chapter_content(
                            novel_id=self.novel_id,
                            chapter_number=ch_num,
                            title=ch.get("title"),
                            content=None,
                            status="failed",
                            error_message=err_msg
                        )
                    finally:
                        task_queue.task_done()

                    delay = random.uniform(self.min_delay, self.max_delay)
                    time.sleep(delay)

        threads = []
        for w_id in range(1, workers_count + 1):
            th = threading.Thread(target=_worker_thread, args=(w_id,), daemon=True)
            threads.append(th)
            th.start()

        for th in threads:
            th.join()

        self.log(f"🎉 اكتملت معالجة كافة الفصول عبر الخطوط المتوازية بنجاح!")

def parse_custom_chapter_numbers(raw_input: str) -> List[int]:
    """تحليل سلسلة أرقام الفصول المفردة والمخصصة مثل '5, 9, 10, 78' أو '1, 3-6, 12'."""
    nums = set()
    if not raw_input:
        return []
    raw = str(raw_input).replace("،", ",").replace(" ", "")
    parts = raw.split(",")
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if "-" in p:
            try:
                start, end = p.split("-", 1)
                for i in range(int(start), int(end) + 1):
                    nums.add(i)
            except Exception:
                pass
        else:
            try:
                nums.add(int(p))
            except Exception:
                pass
    return sorted(list(nums))


# سجل مركزي للمهام الخلفية لتمكين استمرار السحب حتى عند مغادرة المستخدم للصفحة
ACTIVE_BACKGROUND_TASKS: Dict[int, NovelScrapingSession] = {}


def start_background_scraping(
    novel_id: int,
    from_chapter: int = 1,
    to_chapter: int = 1,
    domain_config: Dict[str, Any] = None,
    novel_name: str = "رواية عامة",
    thread_count: int = 3,
    auto_stream_to_sheet: bool = True,
    min_delay: float = 1.0,
    max_delay: float = 2.0,
    headless: bool = True,
    chapter_numbers: Optional[List[int]] = None
) -> NovelScrapingSession:
    """
    تشغيل سحب الفصول عبر 3 خطوط متوازية في الخلفية مع التدفق اللحظي فصلاً بفصل إلى Google Sheet.
    """
    session = NovelScrapingSession(
        novel_id=novel_id,
        novel_name=novel_name,
        domain_config=domain_config or {},
        min_delay=min_delay,
        max_delay=max_delay,
        headless=headless,
        thread_count=thread_count,
        auto_stream_to_sheet=auto_stream_to_sheet
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

