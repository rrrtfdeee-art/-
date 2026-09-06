"""
==============================================================================
Smart Novel Scraper - Playwright Anti-Bot Engine & Content Cleaner
==============================================================================
هذا الملف مسؤول عن:
1. إدارة متصفح Playwright مع تقنيات مكافحة الكشف والـ Stealth (Anti-Fingerprinting).
2. استخراج وفهرسة روابط الفصول من صفحة الفهرس (TOC Crawler).
3. سحب الفصول مع المحاكاة البشرية والتأخير الزمني العشوائي (Smart Throttling).
4. تنظيف الـ HTML وحذف العناصر المزعجة وتحويل النصوص إلى فقرات منظمة ومفصولة بأسطر مزدوجة.
5. التخزين اللحظي في SQLite ودعم ميزات الاستئناف (Resume) والتوقف المؤقت.
"""

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
        فتح الرابط وجلب محتوى الـ HTML النهائي وعنوان الصفحة.
        """
        if not self.context:
            self.start()

        page = self.context.new_page()
        try:
            # الانتقال إلى الصفحة مع معالجة الوقت المحدد
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
            
            # معالجة تلقائية لتحدي Cloudflare ("Just a moment...")
            for _ in range(12):
                current_title = page.title()
                if "Just a moment" in current_title or "Cloudflare" in current_title or "Attention Required" in current_title:
                    time.sleep(1.0)
                else:
                    break

            if wait_selector:
                try:
                    # أخذ أول محدد نظيف لتفادي أخطاء الفواصل المركبة في Playwright
                    clean_wait = wait_selector.split(",")[0].strip()
                    if clean_wait:
                        page.wait_for_selector(clean_wait, timeout=10000)
                except Exception:
                    pass

            # تمرير خفيف لمحاكاة المستخدم وتحفيز الـ Lazy Loading
            try:
                page.evaluate("window.scrollBy(0, 500);")
                time.sleep(0.5)
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
    """استخراج عنوان الفصل الصافي مع توفير بديل ذكي في حال عدم العثور عليه."""
    if not raw_html:
        return f"الفصل {fallback_number}"

    soup = BeautifulSoup(raw_html, "lxml") if "lxml" in raw_html else BeautifulSoup(raw_html, "html.parser")
    title_elem = soup.select_one(title_selector) if title_selector else None

    if title_elem:
        raw_title = title_elem.get_text(strip=True)
        if raw_title:
            # تنظيف أي فواصل أو مسافات غريبة
            clean_title = re.sub(r"\s+", " ", raw_title).strip()
            return clean_title

    # محاولة استخراج العنوان من وسم <title>
    if soup.title and soup.title.string:
        page_title = soup.title.string.strip()
        # تنظيف لواحق المواقع مثل "- Read Novel Online"
        clean_title = re.split(r"[-–|—]", page_title)[0].strip()
        if clean_title:
            return clean_title

    return f"الفصل {fallback_number}"


# ==============================================================================
# زاحف الفهرس وقائمة الفصول (TOC Crawler)
# ==============================================================================

def normalize_toc_url(url: str) -> str:
    """تحويل روابط الفهارس الشائعة إلى الرابط الكامل للفصول (مثل 69shuba)."""
    # موقع 69shuba: تحويل /book/123.htm إلى /book/123/
    if "69shuba.com/book/" in url and url.endswith(".htm"):
        clean_id = re.search(r"/book/(\d+)\.htm", url)
        if clean_id:
            return f"https://www.69shuba.com/book/{clean_id.group(1)}/"
    return url


def crawl_toc_chapters(
    toc_url: str,
    toc_link_selector: str,
    browser_instance: Optional[PlaywrightStealthBrowser] = None
) -> Tuple[List[Dict[str, Any]], str]:
    """
    سحب صفحة الفهرس واستخراج كافة روابط الفصول وترتيبها تصاعدياً من الفصل الأول إلى الأخير:
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

        links = soup.select(toc_link_selector)
        if not links:
            links = soup.find_all("a", href=re.compile(r"(chapter|ch-|\bch\d+|\bchap\b|/txt/)", re.IGNORECASE))

        raw_chapters = []
        seen_urls = set()

        for a_tag in links:
            href = a_tag.get("href")
            if not href:
                continue

            full_url = urljoin(normalized_url, href)
            # تجنب تكرار الروابط وتجنب روابط الرئيسية وصفحات الكتب
            if full_url in seen_urls or full_url.rstrip("/").endswith((".com", ".net", ".org", "book")):
                continue
            seen_urls.add(full_url)

            link_text = a_tag.get_text(strip=True) or a_tag.get("title", "").strip()
            # تجاهل الروابط الفارغة أو التي لا تخص الفصول
            if len(link_text) < 1 or "login" in link_text.lower() or "register" in link_text.lower():
                continue

            raw_chapters.append({
                "url": full_url,
                "title": link_text
            })

        # فحص ما إذا كانت القائمة مرتبة تنازلياً (من الأحدث للأقدم) وعكسها لتصبح من الفصل الأول للأخير
        if len(raw_chapters) > 3:
            first_title = raw_chapters[0]["title"]
            last_title = raw_chapters[-1]["title"]
            
            first_num_match = re.search(r"(\d+)", first_title)
            last_num_match = re.search(r"(\d+)", last_title)
            
            if first_num_match and last_num_match:
                f_num = int(first_num_match.group(1))
                l_num = int(last_num_match.group(1))
                # إذا كان الرقم الأول أكبر من الأخير (مثلاً 363 ثم 1)، نعكس القائمة
                if f_num > l_num:
                    raw_chapters.reverse()

        # تنظيف عنوان الرواية من عنوان الصفحة
        novel_title = re.split(r"[-–|—]", page_title)[0].strip() or "رواية غير معنونة"

        # ترقيم الفصول تتابعياً من 1 إلى N
        structured_chapters = []
        for idx, item in enumerate(raw_chapters, start=1):
            title = item["title"] if item["title"] else f"الفصل {idx}"
            # استخراج رقم الفصل الحقيقي من العنوان مثل 第477章 أو Chapter 477 أو 477.html
            parsed_num = None
            m_cn = re.search(r"第\s*(\d+)\s*章", title)
            if m_cn:
                parsed_num = int(m_cn.group(1))
            else:
                m_any = re.search(r"(?:chapter|chap|ch\.?|الفصل)?\s*(\d+)", title, re.IGNORECASE)
                if m_any:
                    parsed_num = int(m_any.group(1))
                else:
                    m_url = re.search(r"_(\d+)\.html|\b(\d+)\.html", item["url"])
                    if m_url:
                        parsed_num = int(m_url.group(1) or m_url.group(2))

            chap_num = parsed_num if parsed_num is not None else idx
            structured_chapters.append({
                "chapter_number": chap_num,
                "url": item["url"],
                "title": title
            })

        return structured_chapters, novel_title
    finally:
        if should_close_browser:
            browser_instance.close()


def fetch_samples_for_gemini_analysis(
    toc_url: str,
    browser_instance: Optional[PlaywrightStealthBrowser] = None
) -> Tuple[str, str, str]:
    """
    جلب عينة HTML لصفحة الفهرس وعينة HTML لأول فصل لاكتشاف الـ Selectors عبر Gemini.
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

        # إذا لم نجد رابطاً صريحاً، نأخذ أي رابط داخلي صالح
        if not sample_chapter_url:
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href and not href.startswith("#") and len(href) > 3 and "home" not in href.lower():
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
        domain_config: Optional[Dict[str, Any]] = None,
        min_delay: float = 2.0,
        max_delay: float = 4.0,
        headless: bool = True,
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ):
        self.novel_id = novel_id
        self.domain_config = domain_config or {}
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.headless = headless
        self.log_callback = log_callback or (lambda msg: None)
        self.progress_callback = progress_callback or (lambda current, total, status: None)
        
        self.is_paused = False
        self.is_stopped = False

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

    def run_range(self, from_chapter: int, to_chapter: int):
        """
        تنفيذ عملية سحب الفصول في النطاق المحدد مع حفظ كل فصل فورياً في SQLite.
        """
        chapters_to_scrape = get_chapters(self.novel_id, from_chapter=from_chapter, to_chapter=to_chapter)
        total_in_range = len(chapters_to_scrape)

        if total_in_range == 0:
            self.log("⚠️ لم يتم العثور على أي فصول في هذا النطاق.")
            return

        self.log(f"🚀 بدء سحب {total_in_range} فصلاً (من الفصل {from_chapter} إلى {to_chapter})...")

        title_sel = self.domain_config.get("chapter_title_selector", "")
        content_sel = self.domain_config.get("chapter_content_selector", "")
        purge_sels = self.domain_config.get("purge_selectors", [])

        with PlaywrightStealthBrowser(headless=self.headless) as browser:
            for idx, ch in enumerate(chapters_to_scrape, start=1):
                # التحقق من إشارات التوقف
                if self.is_stopped:
                    self.log("⏹️ توقفت عملية السحب بناءً على طلب المستخدم.")
                    break

                # التحقق من الإيقاف المؤقت
                while self.is_paused and not self.is_stopped:
                    time.sleep(0.5)

                ch_num = ch["chapter_number"]
                ch_url = ch["url"]
                cached_status = ch["status"]

                # إذا كان الفصل محملاً مسبقاً ولديه محتوى، يتم تخطيه تلقائياً
                if cached_status == "downloaded" and ch.get("content"):
                    self.log(f"⚡ الفصل {ch_num} موجود بالفعل في قاعدة البيانات - تم التخطي (Cached).")
                    self.progress_callback(idx, total_in_range, f"تم التخطي (مخزن): فصل {ch_num}")
                    continue

                self.log(f"📥 جاري سحب الفصل {ch_num} من: {ch_url}")
                self.progress_callback(idx, total_in_range, f"جاري سحب فصل {ch_num}...")

                try:
                    # جلب صفحة الفصل عبر Playwright مع إعدادات الـ Stealth
                    raw_html, _ = browser.get_page_html(ch_url, wait_selector=content_sel)

                    # استخراج العنوان والمحتوى المنظف
                    ch_title = extract_chapter_title(raw_html, title_sel, fallback_number=ch_num)
                    clean_content = clean_chapter_content(raw_html, content_sel, purge_sels)

                    if not clean_content or len(clean_content) < 50:
                        raise ValueError("لم يتم استخراج محتوى كافٍ من الصفحة. يرجى التحقق من صحة محدد المحتوى.")

                    # حفظ الفصل فورياً في SQLite
                    save_chapter_content(
                        novel_id=self.novel_id,
                        chapter_number=ch_num,
                        title=ch_title,
                        content=clean_content,
                        status="downloaded"
                    )

                    words_count = len(clean_content.split())
                    self.log(f"✅ تم حفظ الفصل {ch_num}: '{ch_title}' بنجاح ({words_count} كلمة).")

                except Exception as ex:
                    err_msg = str(ex)
                    self.log(f"❌ خطأ أثناء سحب الفصل {ch_num}: {err_msg}")
                    save_chapter_content(
                        novel_id=self.novel_id,
                        chapter_number=ch_num,
                        title=ch.get("title") or f"الفصل {ch_num}",
                        content="",
                        status="failed",
                        error_message=err_msg
                    )

                # تطبيق التأخير البشري العشوائي لمنع الحظر
                if idx < total_in_range and not self.is_stopped:
                    delay = random.uniform(self.min_delay, self.max_delay)
                    self.log(f"⏳ انتظار ذكي لمحاكاة التصفح البشري: {delay:.2f} ثانية...")
                    time.sleep(delay)

        self.log("🎉 اكتملت معالجة النطاق المطلوب بالكامل.")


# سجل مركزي للمهام الخلفية لتمكين استمرار السحب حتى عند مغادرة المستخدم للصفحة
ACTIVE_BACKGROUND_TASKS: Dict[int, NovelScrapingSession] = {}


def start_background_scraping(
    novel_id: int,
    from_chapter: int,
    to_chapter: int,
    domain_config: Dict[str, Any],
    min_delay: float = 0.5,
    max_delay: float = 1.0,
    headless: bool = True
) -> NovelScrapingSession:
    """
    تشغيل سحب الفصول في خيط مستقل بالخلفية (Background Daemon Thread).
    يستمر هذا الخيط في العمل وتخزين الفصول في SQLite حتى لو أغلقت صفحة الويب تماماً.
    """
    session = NovelScrapingSession(
        novel_id=novel_id,
        domain_config=domain_config,
        min_delay=min_delay,
        max_delay=max_delay,
        headless=headless
    )

    ACTIVE_BACKGROUND_TASKS[novel_id] = session

    def _worker():
        if sys.platform == "win32":
            try:
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            except Exception:
                pass
        try:
            session.run_range(from_chapter, to_chapter)
        finally:
            ACTIVE_BACKGROUND_TASKS.pop(novel_id, None)

    th = threading.Thread(target=_worker, daemon=True)
    th.start()
    return session

