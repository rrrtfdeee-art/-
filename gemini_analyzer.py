"""
==============================================================================
Smart Novel Scraper - Gemini AI & Multi-GAS Distributed Pool v2.0
==============================================================================
هذا الملف مسؤول عن:
1. إدارة مجمع وسائط Google Apps Script المتعددة (Multi-GAS Pool) مع تدوير الحمل التلقائي (Round-Robin) وتجاوز الأخطاء (Failover).
2. إرسال طلبات الذكاء الاصطناعي مع دعم توزيع الحصص (Quota Distribution).
3. استخراج محددات CSS دقيقة بالاعتماد على Structured JSON Schema.
4. نظام الاستكشاف الهجين الذكي (Heuristic Fallback Engine).
5. فحص وتشخيص مجمع الوسائط بالكامل بالتوازي.
6. وكيل جلب الـ HTML السحابي عبر سيرفرات Google.
"""

import json
import re
import os
import itertools
import threading
import concurrent.futures
import requests
from typing import Dict, List, Any, Optional, Tuple
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
import database

DEFAULT_GAS_POOL = [
    "https://script.google.com/macros/s/AKfycbzqvNegOJvo1eHKNjUsaVwUnFn0-Apg5ouNuvuAGNSdMU32Kt0YuDKtpCQTDXPx_Mqd6Q/exec",
    "https://script.google.com/macros/s/AKfycbzg-zSivsMeJOtau8gGg8UdsrnCcVKsV1GLeee-1N4iear1mI-G5dAU1vDMrlCEPeXZ/exec",
    "https://script.google.com/macros/s/AKfycbxX2_Nm-13N06GfGP7fVWrfvGd1Gh7fYk7Z2KW4qsJdpY35eiBC5A-oc9yb4mVMBbPX/exec",
    "https://script.google.com/macros/s/AKfycbzbghSWICv5pebQ5RQtuf8KPnAN1qkPudtJeVw-zY-W3NTEZFe2RpwjnXmXRKv7vlZAbA/exec"
]
DEFAULT_GAS_URL = DEFAULT_GAS_POOL[0]


class DOMAnalysisResult(BaseModel):
    """النموذج الهيكلي المحدد لنتائج تحليل DOM من Gemini AI."""
    toc_link_selector: str = Field(
        ...,
        description="محدد CSS دقيق يستهدف جميع روابط الفصول داخل صفحة الفهرس TOC."
    )
    chapter_title_selector: str = Field(
        ...,
        description="محدد CSS دقيق يستهدف عنوان الفصل الرئيسي داخل صفحة القراءة."
    )
    chapter_content_selector: str = Field(
        ...,
        description="محدد CSS دقيق يستهدف الحاوية الرئيسية لنص الرواية."
    )
    purge_selectors: List[str] = Field(
        default_factory=list,
        description="قائمة بمحددات CSS للعناصر المزعجة المراد حذفها."
    )
    notes: Optional[str] = Field(
        default="",
        description="ملاحظات توضيحية حول بنية الموقع."
    )


# ==============================================================================
# مجمع وسائط Google Apps Script المتعددة (Distributed Multi-GAS Pool)
# ==============================================================================

class GoogleAppsScriptPool:
    """
    متحكم مجمع وسائط Google Apps Script:
    يدير تدوير الطلبات بين عدة روابط سحابية لتوزيع الحمل وتجاوز حدود الـ Rate Limits.
    """
    _instance = None
    _lock = threading.Lock()

    def __init__(self, endpoints: Optional[List[str]] = None):
        self.endpoints: List[str] = []
        self._counter = 0
        self.update_endpoints(endpoints)

    def update_endpoints(self, endpoints: Optional[List[str]] = None):
        with self._lock:
            if endpoints:
                clean = [e.strip() for e in endpoints if e and e.strip().startswith("http")]
                self.endpoints = clean if clean else list(DEFAULT_GAS_POOL)
            else:
                raw_saved = database.get_setting("gemini_gas_pool", "")
                if raw_saved:
                    clean = [e.strip() for e in raw_saved.split("\n") if e.strip().startswith("http")]
                    self.endpoints = clean if clean else list(DEFAULT_GAS_POOL)
                else:
                    self.endpoints = list(DEFAULT_GAS_POOL)

    def get_endpoints(self) -> List[str]:
        with self._lock:
            return list(self.endpoints)

    def get_next_endpoint(self) -> str:
        """الحصول على الرابط التالي في المجمع عبر Round-Robin."""
        with self._lock:
            if not self.endpoints:
                return DEFAULT_GAS_URL
            endpoint = self.endpoints[self._counter % len(self.endpoints)]
            self._counter += 1
            return endpoint


# كائن المجمع العام
gas_pool = GoogleAppsScriptPool()


def parse_gas_pool_string(raw_text: str) -> List[str]:
    """تحليل نص يحتوي على روابط متعددة (سطر لكل رابط أو مفصولة بفواصل)."""
    if not raw_text:
        return [DEFAULT_GAS_URL]
    
    lines = re.split(r"[\n,;]+", raw_text)
    clean_urls = []
    for line in lines:
        u = line.strip()
        if u.startswith("http") and "script.google.com" in u:
            clean_urls.append(u)
    return clean_urls if clean_urls else [DEFAULT_GAS_URL]


def clean_and_compress_dom_for_ai(html_content: str, max_length: int = 25000) -> str:
    """تنظيف وتلخيص شجرة HTML لتوفير مساحة الـ Tokens للذكاء الاصطناعي."""
    if not html_content:
        return ""

    try:
        soup = BeautifulSoup(html_content, "lxml")
    except Exception:
        soup = BeautifulSoup(html_content, "html.parser")

    for tag in soup(["script", "style", "svg", "noscript", "iframe", "link", "meta", "canvas", "picture"]):
        tag.decompose()

    allowed_attrs = {"class", "id", "href", "role", "itemprop"}
    for tag in soup.find_all(True):
        tag.attrs = {k: v for k, v in tag.attrs.items() if k in allowed_attrs}
        if tag.string and len(tag.string.strip()) > 80:
            tag.string = tag.string.strip()[:80] + "..."

    compressed_html = soup.prettify()
    compressed_html = re.sub(r"\n\s*\n", "\n", compressed_html)
    
    if len(compressed_html) > max_length:
        return compressed_html[:max_length] + "\n<!-- [Truncated for brevity] -->"
    
    return compressed_html


def auto_detect_selectors_heuristically(toc_html: str, chapter_html: str) -> Dict[str, Any]:
    """نظام استكشاف محلي سريع لمحددات CSS بدون استهلاك رصيد AI."""
    soup_toc = BeautifulSoup(toc_html, "lxml") if "lxml" in toc_html else BeautifulSoup(toc_html, "html.parser")
    soup_ch = BeautifulSoup(chapter_html, "lxml") if "lxml" in chapter_html else BeautifulSoup(chapter_html, "html.parser")

    toc_candidates = [
        "#catalog ul li a", ".catalog a", ".chapter-list a", "#chapters-list a",
        ".list-chapter a", ".wp-manga-chapter a", ".chapters-list li a", "ul.chapters a",
        "a[href*='/txt/']", "a[href*='chapter']", "a[href*='/ch-']", "a[href*='/read/']"
    ]
    best_toc_sel = "a[href*='/txt/'], a[href*='chapter']"
    max_toc_matches = 0

    for cand in toc_candidates:
        try:
            matches = soup_toc.select(cand)
            if len(matches) > max_toc_matches and len(matches) >= 2:
                max_toc_matches = len(matches)
                best_toc_sel = cand
        except Exception:
            pass

    title_candidates = [
        "h1.hide720", ".txtnav h1", "h1.chapter-title", "h1.entry-title", "h2.chap-name",
        ".chapter-heading", "h1.title", "h2.chapter-title", ".entry-title", "h1", "h2"
    ]
    best_title_sel = "h1.hide720, .txtnav h1, h1"
    for t_cand in title_candidates:
        try:
            el = soup_ch.select_one(t_cand)
            if el and len(el.get_text(strip=True)) > 2:
                best_title_sel = t_cand
                break
        except Exception:
            pass

    content_candidates = [
        ".txtnav", "#chapter-content", ".reading-content", ".entry-content", ".cha-content",
        "#article", ".chapter-body", ".novel-content", ".text-left", ".content-inner",
        "#content", "article", ".read-content"
    ]
    best_content_sel = ".txtnav, #chapter-content"
    max_content_len = 0

    for c_cand in content_candidates:
        try:
            c_el = soup_ch.select_one(c_cand)
            if c_el:
                c_len = len(c_el.get_text(strip=True))
                if c_len > max_content_len:
                    max_content_len = c_len
                    best_content_sel = c_cand
        except Exception:
            pass

    default_purges = [
        "h1", "script", "style", "noscript", "iframe", ".ad", ".ads",
        ".advertisement", ".navigation", ".pager", ".comments",
        ".social-share", ".watermark", "button"
    ]

    return {
        "toc_link_selector": best_toc_sel,
        "chapter_title_selector": best_title_sel,
        "chapter_content_selector": best_content_sel,
        "purge_selectors": default_purges,
        "notes": "تم الاكتشاف تلقائياً عبر المحرك الهجين السريع."
    }


def call_gemini_api(
    prompt: str,
    api_key: Optional[str] = None,
    model_name: str = "gemini-3.6-flash",
    gas_url: Optional[str] = None,
    timeout: int = 60
) -> str:
    """
    إرسال الطلب إلى Gemini مع دعم مجمع الوسائط المتعددة (Multi-GAS Pool & Automatic Failover).
    """
    clean_model = model_name.replace("models/", "").strip()
    stored_key = (api_key or "").strip() or database.get_setting("gemini_api_key", os.getenv("GEMINI_API_KEY", ""))

    # تجهيز قائمة الوسائط
    if gas_url and gas_url.strip().startswith("http"):
        endpoints_to_try = [gas_url.strip()]
    else:
        endpoints_to_try = gas_pool.get_endpoints()

    last_error = ""

    # تجربة وسائط المجمع بالترتيب مع التبديل التلقائي عند الخطأ
    for endpoint in endpoints_to_try:
        try:
            payload = {
                "apiKey": stored_key,
                "model": clean_model,
                "prompt": prompt
            }
            res = requests.post(endpoint, json=payload, timeout=timeout)
            if res.status_code != 200:
                last_error = f"وسيط {endpoint[:45]}... رد بكود {res.status_code}"
                continue
            
            data = res.json()
            if "error" in data:
                last_error = f"خطأ من الوسيط: {data['error']}"
                continue
            
            # نجاح الاستجابة
            return data.get("text", "")
        except Exception as e_endpoint:
            last_error = str(e_endpoint)
            continue

    # في حال تعثر كافة الوسائط في المجمع، محاولة الاتصال المباشر بـ REST API
    if stored_key:
        try:
            direct_url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={stored_key}"
            direct_payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}
            }
            direct_res = requests.post(direct_url, json=direct_payload, timeout=timeout)
            if direct_res.status_code == 200:
                res_json = direct_res.json()
                candidates = res_json.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    return "".join(p.get("text", "") for p in parts)
        except Exception as e_direct:
            last_error = f"فشل الاتصال المباشر أيضاً: {str(e_direct)}"

    raise RuntimeError(f"تعذر استلام الرد من جميع وسائط Google Apps Script المتاحة: {last_error}")


def fetch_html_via_gas_pool(target_url: str, timeout: int = 25) -> Tuple[bool, str]:
    """
    سحب كود صفحة ويب عبر مجمع وسائط Google Apps Script (Cloud Proxy).
    """
    endpoints = gas_pool.get_endpoints()
    endpoint = gas_pool.get_next_endpoint()

    for _ in range(len(endpoints)):
        try:
            payload = {
                "action": "fetch_html",
                "target_url": target_url
            }
            res = requests.post(endpoint, json=payload, timeout=timeout)
            if res.status_code == 200:
                data = res.json()
                if data.get("success") and data.get("html"):
                    return True, data["html"]
        except Exception:
            pass
        endpoint = gas_pool.get_next_endpoint()

    return False, ""


def test_gemini_connection(
    api_key: Optional[str] = None,
    model_name: str = "gemini-3.5-flash-lite",
    gas_url: Optional[str] = None
) -> Tuple[bool, str]:
    """فحص الاتصال السريع بمفتاح Gemini أو وسيط Google Apps Script."""
    test_prompt = 'أرجع كائن JSON بسيط: {"status": "ok", "service": "connected"}'
    try:
        result_text = call_gemini_api(
            prompt=test_prompt,
            api_key=api_key,
            model_name=model_name,
            gas_url=gas_url,
            timeout=35
        )
        if "ok" in result_text or "status" in result_text:
            return True, f"الاتصال ناجح بالنموذج ({model_name}) عبر خوادم Google!"
        return True, f"الاتصال ناجح! استجابة: {result_text[:80]}"
    except Exception as ex:
        return False, str(ex)


def run_pool_diagnostic(
    api_key: Optional[str] = None,
    endpoints: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    فحص شامل ومتوازي لكافة وسائط مجمع Google Apps Script.
    """
    target_endpoints = endpoints or gas_pool.get_endpoints()
    stored_key = (api_key or "").strip() or database.get_setting("gemini_api_key", os.getenv("GEMINI_API_KEY", ""))

    report = {
        "total_endpoints": len(target_endpoints),
        "online_count": 0,
        "results": []
    }

    def check_single(url, idx):
        item = {
            "id": idx + 1,
            "url": url,
            "display_url": f"{url[:35]}...{url[-15:]}" if len(url) > 55 else url,
            "ping_ok": False,
            "ai_ok": False,
            "message": ""
        }
        try:
            r = requests.get(url, timeout=8)
            item["ping_ok"] = (r.status_code == 200)
        except Exception as e_p:
            item["message"] = f"Ping Failed: {str(e_p)[:50]}"
            return item

        if item["ping_ok"]:
            ok, msg = test_gemini_connection(api_key=stored_key, model_name="gemini-3.5-flash-lite", gas_url=url)
            item["ai_ok"] = ok
            item["message"] = msg if ok else f"AI Error: {msg[:60]}"
        return item

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(target_endpoints))) as executor:
        futures = [executor.submit(check_single, url, i) for i, url in enumerate(target_endpoints)]
        for f in concurrent.futures.as_completed(futures):
            res_item = f.result()
            report["results"].append(res_item)
            if res_item["ai_ok"]:
                report["online_count"] += 1

    report["results"].sort(key=lambda x: x["id"])
    return report


def run_diagnostic_dict(
    api_key: Optional[str] = None,
    gas_url: Optional[str] = None
) -> Dict[str, Any]:
    """تشغيل فحص تشخيصي للنموذج الأساسي."""
    stored_key = (api_key or "").strip() or database.get_setting("gemini_api_key", os.getenv("GEMINI_API_KEY", ""))
    report = {
        "stored_key_found": bool(stored_key),
        "gas_online": True,
        "models_tested": {}
    }
    for model in ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.1-flash-lite", "gemini-2.0-flash", "gemini-1.5-flash"]:
        ok, msg = test_gemini_connection(api_key=stored_key, model_name=model, gas_url=gas_url)
        report["models_tested"][model] = {"success": ok, "message": msg}
    return report


def analyze_site_dom_with_gemini(
    toc_html: str,
    chapter_html: str,
    api_key: Optional[str] = None,
    model_name: str = "gemini-3.5-flash-lite",
    gas_url: Optional[str] = None
) -> Dict[str, Any]:
    """تحليل هيكل صفحة الفهرس والفصل واستخراج الـ CSS Selectors مع دعم المجمع والمحلل الهجين."""
    clean_toc = clean_and_compress_dom_for_ai(toc_html, max_length=20000)
    clean_chapter = clean_and_compress_dom_for_ai(chapter_html, max_length=25000)

    prompt = f"""
أنت خبير محترف في هندسة استخراج البيانات (Web Scraping & DOM Engineering).
المهمة: تحليل هيكل الـ HTML لموقع روايات واستخراج أفضل وأدق محددات CSS (CSS Selectors) لسحب الفصول تلقائياً.

لديك عينتان:
1. عينة من صفحة الفهرس (Table of Contents / Novel Index):
```html
{clean_toc}
```

2. عينة من صفحة قراءة الفصل (Chapter Reading Page):
```html
{clean_chapter}
```

المطلوب استخراجه بتنسيق JSON صارم وبدقة فائقة:
1. `toc_link_selector`: محدد CSS دقيق جداً يلتقط جميع وسوم الروابط `<a>` المؤدية للفصول داخل صفحة الفهرس (مثال: `.chapter-list a` أو `#catalog ul li a` أو `a[href*="chapter"]`).
2. `chapter_title_selector`: محدد CSS يستهدف عنوان الفصل الرئيسي داخل صفحة القراءة (مثال: `h1.chapter-title` أو `.entry-title` أو `h1.hide720` أو `h1`).
3. `chapter_content_selector`: محدد CSS يستهدف الحاوية الحاضنة لنص الرواية والفقرات فقط دون الرؤوس والتذييلات (مثال: `.txtnav` أو `#chapter-content` أو `.reading-content` أو `#article`).
4. `purge_selectors`: مصفوفة من محددات CSS للعناصر المزعجة المراد حذفها قبل استخراج النص (مثل الإعلانات، أزرار التنقل، التعليقات).
5. `notes`: ملخص موجز باللغة العربية حول البنية المكتشفة.

أرجع النتيجة بصيغة JSON فقط:
{{
  "toc_link_selector": "...",
  "chapter_title_selector": "...",
  "chapter_content_selector": "...",
  "purge_selectors": ["..."],
  "notes": "..."
}}
"""

    try:
        response_text = call_gemini_api(
            prompt=prompt,
            api_key=api_key,
            model_name=model_name,
            gas_url=gas_url
        )

        cleaned_json = response_text.strip()
        if cleaned_json.startswith("```"):
            cleaned_json = re.sub(r"^```(?:json)?\s*", "", cleaned_json)
            cleaned_json = re.sub(r"\s*```$", "", cleaned_json)
        
        match = re.search(r"\{.*\}", cleaned_json, re.DOTALL)
        if match:
            cleaned_json = match.group(0)

        parsed_data = json.loads(cleaned_json)
        validated = DOMAnalysisResult(**parsed_data)
        return validated.model_dump()

    except Exception as e_ai:
        heuristic_res = auto_detect_selectors_heuristically(toc_html, chapter_html)
        heuristic_res["notes"] += f" (ملاحظة: تعثر رد الذكاء الاصطناعي وتم تفعيل الاكتشاف الهجين الذكي: {str(e_ai)[:60]})"
        return heuristic_res


def validate_selectors_against_html(
    html: str,
    title_selector: str,
    content_selector: str,
    purge_selectors: List[str]
) -> Dict[str, Any]:
    """التحقق من صحة المحددات واختبارها محلياً على عينة الـ HTML."""
    soup = BeautifulSoup(html, "lxml") if "lxml" in html else BeautifulSoup(html, "html.parser")
    
    title_elem = soup.select_one(title_selector)
    title_found = bool(title_elem)
    sample_title = title_elem.get_text(strip=True) if title_elem else "لم يتم العثور عليه"

    content_elem = soup.select_one(content_selector)
    content_found = bool(content_elem)
    
    sample_length = 0
    paragraphs_count = 0
    if content_elem:
        for purge_sel in purge_selectors:
            if purge_sel.strip():
                try:
                    for bad in content_elem.select(purge_sel):
                        bad.decompose()
                except Exception:
                    pass
        
        sample_length = len(content_elem.get_text(strip=True))
        paragraphs_count = len(content_elem.find_all(["p", "div", "br"]))

    return {
        "title_found": title_found,
        "sample_title": sample_title,
        "content_found": content_found,
        "content_length": sample_length,
        "paragraphs_count": paragraphs_count,
        "is_valid": content_found and sample_length > 100
    }
