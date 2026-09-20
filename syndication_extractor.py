# -*- coding: utf-8 -*-
"""
syndication_extractor.py — محرك استخراج وتجهيز الفصول للنشر التلقائي (المرحلة الثانية)

يسحب الفصول من:
  1. (الأول والأسرع) شيت الترجمة الخاص بالمستخدم:
     https://docs.google.com/spreadsheets/d/1FcehVXh-GLlZGePTm2nm13N932qcFeT0uGuOsXRFXpI
     الأعمدة: [A]RawTitle, [B]RawText, [C]TransTitle, [D]TransContent, [E]NovelName, ..., [Z]Status
  2. (الاحتياطي) شيت المنشورات الحية العام 1IFT:
     عبر Apps Script WebApp للحصول على HTML منشور بلوجر
  3. (احتياطي أخير) قراءة URL التدوينة مباشرة من بلوجر (حين تُمرَّر الـ URL)
"""

import re
import csv
import time
import logging
import requests
from io import StringIO
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────
# معرفات الجداول والإعدادات (من خريطة_المنظومة.md)
# ─────────────────────────────────────────────────────────
TRANSLATE_SHEET_ID      = "1FcehVXh-GLlZGePTm2nm13N932qcFeT0uGuOsXRFXpI"  # شيت الترجمة الشخصي
PUBLIC_PUBLISHED_SHEET_ID = "1IFT9mKRFByiPhph-ZaSdUT7c6IPUWpLg6Gj2xa9g5mY"  # شيت المنشورات العام
GAS_WEBAPP_URL = "https://script.google.com/macros/s/AKfycbxqLaqJru1ag-am7G9Mrwy5Nb7HliZlK5vbIEQD9MeV3wOOquNUvz4d7vWEwZxkBI6zIw/exec"

# صفحة TranslateQueue هي الأولى (index 0) في الشيت الشخصي
# أعمدة شيت الترجمة الشخصي:
COL_RAW_TITLE   = 0  # A: RawTitle
COL_RAW_TEXT    = 1  # B: RawText
COL_TRANS_TITLE = 2  # C: TransTitle (رقم الفصل + العنوان العربي)
COL_TRANS_CONTENT = 3 # D: TransContent (المتن العربي)
COL_NOVEL_NAME  = 4  # E: NovelName
COL_STATUS      = -1 # Z: Status (آخر عمود)

# أعمدة شيت المنشورات العام 1IFT:
COL_PUB_CHAPTER_NUM = 0  # A: ChapterNum
COL_PUB_TITLE       = 1  # B: Title
COL_PUB_LABELS      = 2  # C: Labels
COL_PUB_DATE        = 3  # D: PublishDate
COL_PUB_POST_ID     = 4  # E: PostID
COL_PUB_POST_URL    = 5  # F: PostURL
COL_PUB_PUBLISHED_AT = 6 # G: PublishedAt
COL_PUB_NOVEL_NAME  = 7  # H: Novelname

REQUEST_TIMEOUT = 15  # ثانية


# ─────────────────────────────────────────────────────────
# دوال القراءة من الجداول (Google Sheets CSV)
# ─────────────────────────────────────────────────────────

def _fetch_sheet_csv(spreadsheet_id: str, sheet_gid: str = "0") -> list:
    """تحميل بيانات ورقة الجدول كقائمة صفوف مع مسارات احتياطية قوية."""
    urls = [
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={sheet_gid}",
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv",
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq?tqx=out:csv"
    ]
    for u in urls:
        try:
            resp = requests.get(u, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200 and resp.text.strip():
                reader = csv.reader(StringIO(resp.text))
                rows = list(reader)
                if rows:
                    return rows
        except Exception:
            continue
    logger.warning(f"[extractor] تعذر تحميل الشيت {spreadsheet_id} بكافة المسارات.")
    return []


# ─────────────────────────────────────────────────────────
# الطريقة الأولى: السحب من شيت الترجمة الشخصي
# ─────────────────────────────────────────────────────────

def fetch_chapter_from_translate_sheet(
    novel_name: str,
    chapter_num: int
) -> Optional[Dict[str, Any]]:
    """
    يسحب بيانات الفصل من شيت الترجمة الشخصي بالاعتماد على:
    - NovelName (مطابقة جزئية غير حساسة لحالة الأحرف)
    - رقم الفصل الموجود في TransTitle (الفصل NN أو Chapter NN)
    
    يُعيد:
      {"chapter_num": int, "title": str, "content": str, "source": "translate_sheet"}
    أو None إذا لم يُعثر عليه.
    """
    rows = _fetch_sheet_csv(TRANSLATE_SHEET_ID)
    if len(rows) < 2:
        return None

    novel_low = novel_name.strip().lower()
    
    for row in rows[1:]:  # تخطي السطر الأول (العناوين)
        if len(row) < 5:
            continue
        
        row_novel = str(row[COL_NOVEL_NAME]).strip().lower()
        if novel_low not in row_novel and row_novel not in novel_low:
            continue  # ليست نفس الرواية
        
        # استخراج رقم الفصل من TransTitle
        trans_title = str(row[COL_TRANS_TITLE]).strip()
        extracted_num = _extract_chapter_number(trans_title)
        
        if extracted_num == chapter_num:
            content = str(row[COL_TRANS_CONTENT]).strip()
            if not content:
                continue
            return {
                "chapter_num": chapter_num,
                "title": trans_title,
                "content": content,
                "source": "translate_sheet"
            }
    
    return None


def _extract_chapter_number(text: str) -> Optional[int]:
    """استخراج رقم الفصل من نص مثل 'الفصل 101: كذا' أو 'Chapter 101 - ...'"""
    patterns = [
        r"(?:الفصل|chapter|الجزء|part)\s*[:\-]?\s*(\d+)",
        r"(\d+)\s*[:\-]",
        r"^(\d+)$",
    ]
    text_clean = text.strip()
    for pat in patterns:
        m = re.search(pat, text_clean, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                continue
    return None


# ─────────────────────────────────────────────────────────
# الطريقة الثانية: السحب من شيت المنشورات العام 1IFT + Blogger URL
# ─────────────────────────────────────────────────────────

def fetch_chapter_from_published_sheet(
    novel_name: str,
    chapter_num: int
) -> Optional[Dict[str, Any]]:
    """
    يجد رابط تدوينة الفصل من شيت المنشورات العام (1IFT)
    ثم يجلب متن التدوينة من Blogger عبر GAS WebApp.
    """
    rows = _fetch_sheet_csv(PUBLIC_PUBLISHED_SHEET_ID)
    if len(rows) < 2:
        return None

    novel_low = novel_name.strip().lower()
    
    for row in rows[1:]:
        if len(row) < 6:
            continue
        
        row_novel = str(row[COL_PUB_NOVEL_NAME]).strip().lower()
        row_labels = str(row[COL_PUB_LABELS]).strip().lower() if len(row) > COL_PUB_LABELS else ""
        
        matches_novel = (
            novel_low in row_novel or 
            row_novel in novel_low or 
            novel_low in row_labels or 
            (len(novel_low) >= 6 and novel_low[:6] in row_novel)
        )
        if not matches_novel:
            continue
        
        try:
            ch_str = str(row[COL_PUB_CHAPTER_NUM]).strip()
            row_chapter = int(float(ch_str))
        except (ValueError, TypeError):
            continue
        
        if row_chapter == chapter_num:
            post_url = str(row[COL_PUB_POST_URL]).strip()
            post_id  = str(row[COL_PUB_POST_ID]).strip()
            title    = str(row[COL_PUB_TITLE]).strip()
            
            # جلب محتوى التدوينة عبر GAS
            content = _fetch_post_content_via_gas(post_id, post_url)
            if content:
                return {
                    "chapter_num": chapter_num,
                    "title": title,
                    "content": content,
                    "source": "blogger_gas"
                }
    return None


def _fetch_post_content_via_gas(post_id: str, post_url: str) -> Optional[str]:
    """يجلب محتوى المنشور من بلوجر عبر Apps Script WebApp أو مباشرة من رابط التدوينة."""
    # 1. محاولة عبر رابط المدونة مباشرة مع محاولات إعادة وترقية المهلة
    if post_url:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        for attempt in range(2):
            try:
                resp = requests.get(post_url, headers=headers, timeout=25)
                if resp.status_code == 200 and resp.text.strip():
                    html = resp.text
                    # استخراج محتوى التدوينة من الوسم الرئيسي للبلوجر
                    m = re.search(r"<div[^>]*class=['\"][^'\"]*post-body[^'\"]*['\"][^>]*>(.*?)</div>\s*<div[^>]*class=['\"][^'\"]*post-footer", html, re.DOTALL | re.IGNORECASE)
                    if not m:
                        m = re.search(r"<div[^>]*class=['\"][^'\"]*post-body[^'\"]*['\"][^>]*>(.*)", html, re.DOTALL | re.IGNORECASE)
                    if m:
                        clean = _strip_blogger_html(m.group(1))
                        if len(clean) > 200:
                            return clean
                break
            except Exception as e_direct:
                if attempt == 1:
                    logger.warning(f"[extractor] تعذر الجلب المباشر من الرابط: {e_direct}")
                time.sleep(1)

    # 2. محاولة عبر Apps Script WebApp
    try:
        params = {"action": "getPostContent", "postId": post_id, "postUrl": post_url}
        resp = requests.get(GAS_WEBAPP_URL, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200 and resp.text.strip():
            raw_text = resp.text.strip()
            if not raw_text.startswith("<"):
                data = resp.json()
                raw_html = data.get("content") or data.get("body") or ""
                if raw_html:
                    return _strip_blogger_html(raw_html)
    except Exception as e:
        logger.warning(f"[extractor] خطأ GAS لجلب postId={post_id}: {e}")
    return None


# ─────────────────────────────────────────────────────────
# تجريد HTML بلوجر وتنظيف المتن
# ─────────────────────────────────────────────────────────

# الأنماط التي تُحذف من الفصل (خاصة ببلوجر)
_BLOGGER_STRIP_PATTERNS = [
    # أزرار التنقل (السابق / التالي)
    r'<a[^>]*>(?:\s*(?:الفصل\s+(?:التالي|السابق)|&lt;&lt;|&gt;&gt;|[«»→←▶◀⏮⏭])[^<]*)</a>',
    # تعليقات HTML
    r'<!--.*?-->',
    # وسوم style المضمّنة
    r'<style[^>]*>.*?</style>',
    # الروابط الخارجية والأزرار
    r'<a\s+href=["\'][^"\']*["\'][^>]*>(?:[^<]{0,50})</a>',
    # divs خاصة بالتصميم / الإعلانات
    r'<div[^>]*class=["\'][^"\']*(?:nav|navigation|button|ad|banner|share)[^"\']*["\'][^>]*>.*?</div>',
]

def _strip_blogger_html(html: str) -> str:
    """تجريد HTML بلوجر المعقد وإخراج نص عربي نظيف بفقرات."""
    text = html
    
    # حذف الأنماط الخاصة ببلوجر
    for pat in _BLOGGER_STRIP_PATTERNS:
        text = re.sub(pat, " ", text, flags=re.IGNORECASE | re.DOTALL)

    # حذف صناديق الإعلانات الخاصة بـ Mondiad أو أي إعلانات ممولة
    text = re.sub(r'<div[^>]*class=["\'][^"\']*(?:sponsored|banner-ad|ad-box)[^"\']*["\'][^>]*>.*?</div>', ' ', text, flags=re.IGNORECASE | re.DOTALL)
    
    # حذف وسوم script و style و SVG و CSS تماماً بمحتواها
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<svg[^>]*>.*?</svg>', ' ', text, flags=re.IGNORECASE | re.DOTALL)

    # تحويل الوسوم الشائعة إلى أسطر جديدة
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(?:p|div|h[1-6]|li|blockquote)[^>]*>', '\n', text, flags=re.IGNORECASE)
    
    # حذف أي وسوم HTML أو CSS متبقية مثل <span style="..."> أو <font ...>
    text = re.sub(r'<[^>]+>', '', text)
    
    # فك تشفير كافة الرموز (HTML Entities) مثل &#1548; و &nbsp;
    import html as _html
    text = _html.unescape(text)
    
    # حذف أكواد الـ CSS الهاربة أو الشاذة إن وجدت مثل { color: ... }
    text = re.sub(r'\{[^{}]*(?:color|font|margin|padding|background|border)[^{}]*\}', '', text, flags=re.IGNORECASE)

    # 🧹 تطهير وسوم المنظومة والـ BBCode الخاصة بـ (System, Cultivation, Doc, Letter, Note, Tip, Log)
    # نحتفظ بالنص الداخلي ونحذف أقواس الوسوم المشوهة مثل:
    # [system]...[/system] أو [cultivation]...[/cultivation] أو [doc seal="..."]...[/doc]
    system_tags = [
        "system", "cultivation", "doc", "letter", "note", "tip", "log", "rift", "status", "panel"
    ]
    for tag in system_tags:
        # حذف وسم الفتح حتى لو احتوى على معلمات مثل [doc seal="..."] أو [system red]
        text = re.sub(rf'\[{tag}[^\]]*\]', '\n【 ', text, flags=re.IGNORECASE)
        # حذف وسم الإغلاق [/system]
        text = re.sub(rf'\[/{tag}\]', ' 】\n', text, flags=re.IGNORECASE)

    # تنظيف أي وسوم مربعة غير مغلقة شاذة مثل [color] أو [b] أو [/b]
    text = re.sub(r'\[/?(?:b|i|u|color|size|font|center|quote|align)[^\]]*\]', '', text, flags=re.IGNORECASE)

    # توحيد الأسطر الفارغة وتنظيف الفراغات
    lines = [l.strip() for l in text.splitlines()]
    clean_lines = [l for l in lines if l]
    return "\n\n".join(clean_lines).strip()


def format_standard_chapter_title(raw_title: str, chapter_num: int, novel_name: str = "") -> str:
    """
    توحيد صيغة عنوان الفصل بدقة متناهية لتصبح دائماً:
    'الفصل {chapter_num}: {العنوان_الفرعي}'
    أو 'الفصل {chapter_num}' إذا لم يتوفر عنوان فرعي.
    ينظف تكرار اسم الرواية وأي فواصل شاذة.
    """
    t = raw_title.strip()
    # 1. إزالة اسم الرواية إن وجد في البداية
    if novel_name:
        t = re.sub(r'^\s*' + re.escape(novel_name.strip()) + r'\s*[:\-—–|]*\s*', '', t, flags=re.IGNORECASE)
    
    # تنظيف أي تكرار لاسم الرواية الإنجليزية أو الفواصل
    t = re.sub(r'^[A-Za-z\s\']+\s*[:\-—–|]+\s*', '', t).strip()

    # 2. استخراج العنوان الفرعي
    m = re.search(r'(?:الفصل|chapter)\s*' + str(chapter_num) + r'\s*[:\-—–|]+\s*(.+)', t, re.IGNORECASE)
    if m:
        sub = m.group(1).strip()
        sub = re.sub(r'^[:\-—–|\s]+', '', sub).strip()
        if sub:
            return f"الفصل {chapter_num}: {sub}"
        return f"الفصل {chapter_num}"
    
    m = re.search(r'(?:الفصل|chapter)\s*' + str(chapter_num) + r'\s+(.+)', t, re.IGNORECASE)
    if m:
        sub = m.group(1).strip()
        sub = re.sub(r'^[:\-—–|\s]+', '', sub).strip()
        if sub:
            return f"الفصل {chapter_num}: {sub}"
        return f"الفصل {chapter_num}"

    # إذا كان فقط رقم أو كلمة الفصل/Chapter
    m_num_only = re.search(r'^(?:.*(?:الفصل|chapter)\s*)?' + str(chapter_num) + r'\s*$', t, re.IGNORECASE)
    if m_num_only:
        return f"الفصل {chapter_num}"

    # إذا كان هناك فاصل
    if any(sep in t for sep in [' - ', ' — ', ' : ', ':']):
        parts = re.split(r'[:\-—–|]', t)
        last_part = parts[-1].strip()
        if last_part and not re.search(r'^\d+$', last_part):
            return f"الفصل {chapter_num}: {last_part}"

    # تنظيف البقايا
    clean = re.sub(r'^(?:الفصل|chapter)\s*\d*\s*[:\-—–\s]*', '', t, flags=re.IGNORECASE).strip()
    if clean and clean != str(chapter_num):
        return f"الفصل {chapter_num}: {clean}"
    return f"الفصل {chapter_num}"


def clean_chapter_paragraphs(raw_text: str, novel_name: str = "", chapter_num: int = 0) -> str:
    """
    تنسيق وتنظيف فقرات الفصل:
    1. حذف تكرار اسم الرواية ورقم الفصل والإعلانات من صدر الفصل.
    2. تنظيم الأسطر كفقرات واضحة ومستقلة تفصل بينها أسطر فارغة.
    3. تطهير وسوم المنظومة والـ HTML.
    """
    text = raw_text.strip()
    
    # فك تشفير رموز HTML
    import html as _html
    text = _html.unescape(text)

    # تنظيف وسوم النظام
    system_tags = ["system", "cultivation", "doc", "letter", "note", "tip", "log", "rift", "status", "panel"]
    for tag in system_tags:
        text = re.sub(rf'\[{tag}[^\]]*\]', '\n【 ', text, flags=re.IGNORECASE)
        text = re.sub(rf'\[/{tag}\]', ' 】\n', text, flags=re.IGNORECASE)
    text = re.sub(r'\[/?(?:b|i|u|color|size|font|center|quote|align)[^\]]*\]', '', text, flags=re.IGNORECASE)

    # حذف أي وسوم html متبقية
    text = re.sub(r'<[^>]+>', '', text)

    # تقسيم إلى فقرات أولية
    raw_lines = [l.strip() for l in text.splitlines()]
    paras = [l for l in raw_lines if l]

    novel_clean = novel_name.strip().lower()

    # تنظيف مقدمة المحتوى من الترويسات والإعلانات
    while paras:
        first = paras[0]
        first_low = first.lower()

        # إعلانات أو فواصل
        if "إعلان مُموَّل" in first or "mondiad" in first_low or first in ["📢", "---", "***", "___"]:
            paras.pop(0)
            continue

        # اسم الرواية منفرداً
        if novel_clean and (first_low == novel_clean or first_low.startswith(novel_clean)):
            paras.pop(0)
            continue

        # سطر الفصل / العنوان المكرر في بداية المحتوى
        if chapter_num > 0 and (
            str(chapter_num) in first and any(k in first_low for k in ["فصل", "chapter", novel_clean])
        ) or first.startswith("الفصل") or first_low.startswith("chapter"):
            paras.pop(0)
            continue

        break

    # تنظيف ذيل المحتوى من أزرار التنقل الزائدة
    while paras:
        last = paras[-1].lower()
        if any(nav in last for nav in ["الفصل التالي", "الفصل السابق", "chapter next", "chapter prev"]):
            paras.pop()
            continue
        break

    return "\n\n".join(paras).strip()


# ─────────────────────────────────────────────────────────
# الدالة الرئيسية: اجلب الفصل المجهّز جاهزاً للنشر
# ─────────────────────────────────────────────────────────

def prepare_chapter_for_publishing(
    novel_name: str,
    chapter_num: int,
    custom_cta: str = "",
    blogger_url: str = ""
) -> Dict[str, Any]:
    """
    الدالة الرئيسية التي تجمع:
      1. سحب الفصل (translate_sheet أولاً، ثم published_sheet، ثم خطأ)
      2. تنظيف المتن وتنسيق الفقرات بدقة
      3. توحيد صيغة العنوان لتكون حصراً 'الفصل رقمه : العنوان'
      4. إضافة الخاتمة التحفيزية

    تُعيد:
      {
        "success": bool,
        "chapter_num": int,
        "title": str,
        "content_clean": str,       # النص النقي للمراجعة
        "content_for_publish": str,  # النص + الخاتمة التحفيزية
        "source": str,
        "error": str or None
      }
    """
    result = {
        "success": False,
        "chapter_num": chapter_num,
        "title": "",
        "content_clean": "",
        "content_for_publish": "",
        "source": "",
        "error": None
    }

    # === 1. حاول من شيت الترجمة الشخصي (الأسرع والأدق) ===
    data = fetch_chapter_from_translate_sheet(novel_name, chapter_num)

    # === 2. إن لم يُوجد، انتقل لشيت المنشورات العام ===
    if not data:
        logger.info(f"[extractor] {novel_name} ف{chapter_num}: لم يُوجد بشيت الترجمة، أجرب 1IFT...")
        data = fetch_chapter_from_published_sheet(novel_name, chapter_num)

    if not data:
        result["error"] = f"تعذّر إيجاد الفصل {chapter_num} لرواية '{novel_name}' في أي من الجداول المتاحة."
        return result

    # === 3. توحيد صيغة العنوان بدقة: الفصل رقمه : العنوان ===
    title_clean = format_standard_chapter_title(data["title"], chapter_num, novel_name)

    # === 4. تنظيف وتنسيق المتن وحذف الترويسات والإعلانات وفصل الفقرات ===
    content_clean = clean_chapter_paragraphs(data["content"], novel_name, chapter_num)
    
    # === 5. دمج الخاتمة التحفيزية الذكية المخصصة لكل منصة لمنع بصمة السبام ===
    cta_general = _build_cta(custom_cta, novel_name, blogger_url, platform="all")
    cta_rewayat = _build_cta(custom_cta, novel_name, blogger_url, platform="rewayat_club")
    cta_wattpad = _build_cta(custom_cta, novel_name, blogger_url, platform="wattpad")

    content_for_publish = f"{content_clean}\n\n{cta_general}" if cta_general else content_clean
    content_rewayat = f"{content_clean}\n\n{cta_rewayat}" if cta_rewayat else content_clean
    content_wattpad = f"{content_clean}\n\n{cta_wattpad}" if cta_wattpad else content_clean

    result.update({
        "success": True,
        "title": title_clean,
        "content_clean": content_clean,
        "content_for_publish": content_for_publish,
        "content_rewayat_club": content_rewayat,
        "content_wattpad": content_wattpad,
        "source": data["source"]
    })
    return result


REWAYAT_CTA_VARIANTS = [
    "✨ استمتعتم بالفصل؟ لدعم استمرار الترجمة ومتابعة الفصول المتقدمة فور صدورها، تفضلوا بزيارة موقعنا الأصلي عبر الرابط في خانة الدعم/بطاقة الرواية ✨",
    "🌟 لمتابعة الفصول المتقدمة والحصرية فور نزولها ودعم استمرار العمل، تفقدوا رابط الموقع في خانة الدعم والوصف 📖 ✨",
    "💫 قراءة ممتعة! لمتابعة الفصول الحصرية فور صدورها بجودة عالية، يمكنكم زيارة موقعنا عبر الرابط الموجود في بطاقة الرواية وخانة الدعم 🚀",
    "💎 دعمكم المستمر هو سر استمرارنا! لمتابعة الفصول الحصرية فور توفرها، زوروا موقعنا الأصلي عبر الرابط في خانة الدعم ✨"
]

WATTPAD_CTA_VARIANTS = [
    "✨ استمتعتم بالفصل؟ لمتابعة أحدث الفصول الحصرية والمتقدمة فور صدورها، تفضلوا بزيارة موقعنا الأصلي عبر الرابط في بايو الحساب (Bio) 🔗 ✨",
    "📚 لقراءة الفصول المتقدمة والحصرية فور نزولها، يمكنكم زيارة موقعنا عبر الرابط المباشر في بايو الملف الشخصي 🌟",
    "⚡ هل ترغبون بقراءة الفصول القادمة قبل الجميع؟ تفقدوا الرابط المباشر لموقعنا في بايو الحساب (Bio) 📖 ✨",
    "💫 لمتابعة بقية أحداث الرواية والفصول الحصرية بأعلى جودة، زوروا موقعنا الأصلي عبر الرابط في بايو الحساب 🚀"
]

def _build_cta(custom_cta: str, novel_name: str, blogger_url: str = "", platform: str = "all") -> str:
    """
    يبني نص الخاتمة التحفيزية مع التوجيه الذكي والآمن لكل منصة:
    - لواتباد: التوجيه لبايو الحساب (Bio) لتفادي حظر الروابط الخارجية وخوارزميات السبام.
    - لنادي الروايات: التوجيه لخانة الدعم وبطاقة الرواية.
    - يدعم التناوب العشوائي بين القوالب لكسر بصمة التكرار الآلي (Anti-Spam Fingerprint).
    """
    import random

    if platform == "wattpad":
        if custom_cta and ("بايو" in custom_cta or "bio" in custom_cta.lower()):
            cta = custom_cta
        else:
            cta = random.choice(WATTPAD_CTA_VARIANTS)
    elif platform == "rewayat_club":
        if custom_cta and ("الدعم" in custom_cta or "بطاقة" in custom_cta):
            cta = custom_cta
        else:
            cta = random.choice(REWAYAT_CTA_VARIANTS)
    else:
        if custom_cta:
            cta = custom_cta
        else:
            cta = random.choice(REWAYAT_CTA_VARIANTS)

    cta = cta.replace("{novel_name}", novel_name)
    cta = cta.replace("{novel_link}", blogger_url if blogger_url else "[رابط الرواية]")
    cta = cta.replace("[رابط الرواية]", blogger_url if blogger_url else "[رابط الرواية]")
    return cta


# ─────────────────────────────────────────────────────────
# دالة مساعدة: حصر الفصول المتاحة لرواية معينة
# ─────────────────────────────────────────────────────────

def get_available_chapters_for_novel(novel_name: str) -> list:
    """
    يُعيد قائمة مرتبة بأرقام الفصول المتاحة لرواية معينة في شيت الترجمة.
    مفيد لعرض تقدم المزامنة في الواجهة.
    """
    rows = _fetch_sheet_csv(TRANSLATE_SHEET_ID)
    if len(rows) < 2:
        return []

    novel_low = novel_name.strip().lower()
    chapters = []

    for row in rows[1:]:
        if len(row) < 5:
            continue
        row_novel = str(row[COL_NOVEL_NAME]).strip().lower()
        if novel_low not in row_novel and row_novel not in novel_low:
            continue

        trans_title = str(row[COL_TRANS_TITLE]).strip()
        num = _extract_chapter_number(trans_title)
        if num is not None and str(row[COL_TRANS_CONTENT]).strip():
            chapters.append(num)

    return sorted(set(chapters))


# ─────────────────────────────────────────────────────────
# دالة الاستخراج الذكي من الروابط (نادي الروايات / واتباد + موقع المدونة)
# ─────────────────────────────────────────────────────────

def inspect_novel_links(
    platform: str,
    platform_url: str,
    blogger_url: str = ""
) -> Dict[str, Any]:
    """
    فحص واستخراج بيانات الرواية تلقائياً من رابط المنصة ورابط الموقع.
    - يستخرج المعرف النظيف (slug أو story_id)
    - يجلب الاسم العربي والإنجليزي للرواية
    - يستخرج اسم الرواية والتصنيف من صفحة المدونة أو شيت الفهارس
    - يستعلم عن آخر فصل منشور في المنصة تلقائياً
    """
    res = {
        "success": False,
        "novel_name": "",
        "blogger_url": blogger_url.strip(),
        "blogger_label": "",
        "clean_id": "",
        "last_chapter": 0,
        "start_chapter": 1,
        "stop_chapter": 100,
        "error": None
    }

    clean_p_url = str(platform_url).strip()
    clean_b_url = str(blogger_url).strip()

    # 1. تحليل واستخراج بيانات الموقع الأصلي (المدونة / Novelskyworld)
    site_title = ""
    if clean_b_url:
        try:
            # محاولة قراءة الصفحة للحصول على العنوان
            resp_site = requests.get(
                clean_b_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                timeout=10
            )
            if resp_site.status_code == 200:
                m_title = re.search(r'<title>(.*?)</title>', resp_site.text, re.IGNORECASE)
                if m_title:
                    raw_t = m_title.group(1).strip()
                    # تنظيف العنوان من لاحقات المدونة الشائعة
                    for suffix in ["- عالم سماء الروايات", "| عالم سماء الروايات", "- Novelskyworld", "| Novelskyworld", "عالم سماء الروايات"]:
                        raw_t = raw_t.replace(suffix, "").strip()
                    site_title = raw_t.strip(" -|:")
        except Exception as e_site:
            logger.warning(f"[inspect_novel_links] تعذر جلب عنوان صفحة المدونة: {e_site}")

        # محاولة مطابقة الرابط مع شيت الفهارس (1s-yf1g...) للحصول على الاسم الرسمي
        try:
            idx_rows = _fetch_sheet_csv("1s-yf1gRHagPIeikEC9_aVIAst7oDaiwoNzLH-hd0Q24")
            for r in idx_rows[1:]:
                if len(r) >= 3:
                    sheet_name = str(r[0]).strip()
                    sheet_link = str(r[2]).strip()
                    if clean_b_url.rstrip("/?") in sheet_link or sheet_link.rstrip("/?") in clean_b_url:
                        if sheet_name:
                            site_title = sheet_name
                            break
        except Exception as e_idx:
            logger.warning(f"[inspect_novel_links] تعذر فحص شيت الفهارس: {e_idx}")

    # 2. معالجة منصة نادي الروايات (Rewayat Club)
    if platform == "rewayat_club":
        clean_slug = clean_p_url
        if "rewayat.club/novel/" in clean_slug:
            clean_slug = clean_slug.split("rewayat.club/novel/")[-1].split("/")[0].split("?")[0].strip()
        elif "novel/" in clean_slug:
            clean_slug = clean_slug.split("novel/")[-1].split("/")[0].split("?")[0].strip()
        else:
            clean_slug = clean_slug.strip().rstrip("/")

        res["clean_id"] = clean_slug

        # جلب بيانات الرواية من API نادي الروايات
        api_novel_name = ""
        if clean_slug:
            try:
                api_url = f"https://api.rewayat.club/api/novels/{clean_slug}/"
                api_resp = requests.get(api_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                if api_resp.status_code == 200:
                    nov_data = api_resp.json()
                    arabic_name = (nov_data.get("arabic") or "").strip()
                    english_name = (nov_data.get("english") or "").strip()
                    api_novel_name = arabic_name or english_name
            except Exception as e_api:
                logger.warning(f"[inspect_novel_links] تعذر جلب بيانات الرواية من API نادي الروايات: {e_api}")

        # اعتماد أفضل اسم متاح للرواية
        chosen_name = site_title or api_novel_name or clean_slug
        res["novel_name"] = chosen_name
        res["blogger_label"] = site_title or api_novel_name or chosen_name

        # فحص آخر فصل منشور على نادي الروايات
        try:
            import rewayat_club_api
            rc_client = rewayat_club_api.RewayatClubClient()
            latest_ch = rc_client.get_latest_chapter_number(clean_slug)
            if latest_ch and latest_ch > 0:
                res["last_chapter"] = latest_ch
                res["start_chapter"] = 1
                res["stop_chapter"] = max(latest_ch + 50, 100)
            else:
                res["last_chapter"] = 0
                res["start_chapter"] = 1
                res["stop_chapter"] = 50
        except Exception as e_rc:
            logger.warning(f"[inspect_novel_links] تعذر استعلام آخر فصل في نادي الروايات: {e_rc}")

        res["success"] = bool(clean_slug)

    # 3. معالجة منصة واتباد (Wattpad)
    elif platform == "wattpad":
        clean_story_id = clean_p_url
        story_slug = ""
        if "wattpad.com/story/" in clean_story_id:
            part = clean_story_id.split("wattpad.com/story/")[-1].split("?")[0].strip()
            # قد يكون الشكل: 365123456-shadow-slave-arabic
            m_wp = re.match(r"^(\d+)(?:-(.*))?", part)
            if m_wp:
                clean_story_id = m_wp.group(1)
                story_slug = (m_wp.group(2) or "").replace("-", " ").strip()
            else:
                clean_story_id = part.split("-")[0].split("/")[0].strip()
        else:
            # إذا أدخل المستخدم معرف رقمي أو نصي فقط
            m_num = re.search(r"(\d{6,})", clean_story_id)
            if m_num:
                clean_story_id = m_num.group(1)

        res["clean_id"] = clean_story_id

        chosen_name = site_title or story_slug or (f"قصة واتباد {clean_story_id}" if clean_story_id else "")
        res["novel_name"] = chosen_name
        res["blogger_label"] = site_title or story_slug or chosen_name

        # فحص آخر فصل منشور على قصة واتباد
        if clean_story_id:
            try:
                import wattpad_poster
                wp_client = wattpad_poster.WattpadClient()
                wp_latest = wp_client.get_latest_chapter_number(clean_story_id)
                if wp_latest and wp_latest > 0:
                    res["last_chapter"] = wp_latest
                    res["start_chapter"] = 1
                    res["stop_chapter"] = max(wp_latest + 30, 50)
                else:
                    res["last_chapter"] = 0
                    res["start_chapter"] = 1
                    res["stop_chapter"] = 30
            except Exception as e_wp:
                logger.warning(f"[inspect_novel_links] تعذر استعلام فصول واتباد: {e_wp}")

        res["success"] = bool(clean_story_id)

    return res

