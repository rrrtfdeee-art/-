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
    """تحميل بيانات ورقة الجدول كقائمة صفوف."""
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={sheet_gid}"
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        reader = csv.reader(StringIO(resp.text))
        return list(reader)
    except Exception as e:
        logger.warning(f"[extractor] خطأ في تحميل الشيت {spreadsheet_id}: {e}")
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
        if novel_low not in row_novel and row_novel not in novel_low:
            continue
        
        try:
            row_chapter = int(str(row[COL_PUB_CHAPTER_NUM]).strip())
        except ValueError:
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
    # 1. محاولة عبر رابط المدونة مباشرة (أسرع وأدق كـ Fallback)
    if post_url:
        try:
            resp = requests.get(post_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                html = resp.text
                # استخراج محتوى التدوينة من الوسم الرئيسي للبلوجر
                m = re.search(r"<div[^>]*class=['\"][^'\"]*post-body[^'\"]*['\"][^>]*>(.*?)</div>\s*<div[^>]*class=['\"][^'\"]*post-footer", html, re.DOTALL | re.IGNORECASE)
                if not m:
                    m = re.search(r"<div[^>]*class=['\"][^'\"]*post-body[^'\"]*['\"][^>]*>(.*)", html, re.DOTALL | re.IGNORECASE)
                if m:
                    clean = _strip_blogger_html(m.group(1))
                    if len(clean) > 200:
                        return clean
        except Exception as e_direct:
            logger.warning(f"[extractor] تعذر الجلب المباشر من الرابط: {e_direct}")

    # 2. محاولة عبر Apps Script WebApp
    try:
        params = {"action": "getPostContent", "postId": post_id, "postUrl": post_url}
        resp = requests.get(GAS_WEBAPP_URL, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200 and resp.text.strip():
            try:
                data = resp.json()
                raw_html = data.get("content") or data.get("body") or ""
                if raw_html:
                    return _strip_blogger_html(raw_html)
            except Exception:
                pass
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
    clean_lines = []
    prev_empty = False
    for line in lines:
        if not line:
            if not prev_empty:
                clean_lines.append("")
            prev_empty = True
        else:
            clean_lines.append(line)
            prev_empty = False
    
    return "\n".join(clean_lines).strip()


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
      2. تنظيف المتن
      3. إضافة الخاتمة التحفيزية

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

    # === 3. تجهيز المتن ===
    content_clean = data["content"].strip()
    
    # === 4. دمج الخاتمة التحفيزية ===
    cta = _build_cta(custom_cta, novel_name, blogger_url)
    content_for_publish = f"{content_clean}\n\n{cta}" if cta else content_clean

    result.update({
        "success": True,
        "title": data["title"],
        "content_clean": content_clean,
        "content_for_publish": content_for_publish,
        "source": data["source"]
    })
    return result


def _build_cta(custom_cta: str, novel_name: str, blogger_url: str = "") -> str:
    """يبني نص الخاتمة التحفيزية مع استبدال المتغيرات الديناميكية."""
    if not custom_cta:
        return ""
    
    cta = custom_cta
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
