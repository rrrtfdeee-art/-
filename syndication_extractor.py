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
import os
import json
import logging
import requests
import urllib.parse
import base64
from io import StringIO
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────
# إعدادات قواعد Supabase السحابية (بديل مستودعات الأرشيف القديمة)
# ─────────────────────────────────────────────────────────
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_BACKUP_REPO_AR = os.getenv("GITHUB_BACKUP_REPO_AR", os.getenv("GITHUB_BACKUP_REPO", "rrrtfdeee-art/back"))
GITHUB_BACKUP_REPO_EN = os.getenv("GITHUB_BACKUP_REPO_EN", "rrrtfdeee-art/back-en")
GITHUB_BACKUP_REPO = GITHUB_BACKUP_REPO_AR

# إعدادات Supabase العربية المركزية (novels & chapters)
SUPABASE_URL_AR = (os.getenv("SUPABASE_URL_AR") or os.getenv("SUPABASE_URL", "https://pyoxhjxdpvbqnacuihxi.supabase.co")).rstrip("/")
SUPABASE_KEY_AR = (
    os.getenv("SUPABASE_KEY_AR") or
    os.getenv("SUPABASE_KEY", "") or
    os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or
    os.getenv("SUPABASE_ANON_KEY", "")
)

# إعدادات Supabase الإنجليزية المركزية (novels_en & chapters_en)
SUPABASE_URL_EN = (os.getenv("SUPABASE_URL_EN") or "https://vsudtgopvcethxgxykpx.supabase.co").rstrip("/")
SUPABASE_KEY_EN = os.getenv("SUPABASE_KEY_EN", "")

# الحالات المعتمدة حصراً لسحب الفصول الجاهزة للنشر
APPROVED_CHAPTER_STATUSES = ("PUBLISHED", "SCHEDULED", "APPROVED", "STAGING_APPROVED", "READY")

NOVEL_NAME_MAPPINGS = {
    # 1. After Severing Ties
    "after severing ties": "After Severing Ties",
    "severing-ties": "After Severing Ties",
    "قطع العلاقات": "After Severing Ties",
    # 2. المزارع الخبير في المدرسة الابتدائية
    "المزارع الخبير في المدرسة الابتدائية": "المزارع الخبير في المدرسة الابتدائية",
    "expert-cultivator": "المزارع الخبير في المدرسة الابتدائية",
    "the-expert-cultivator-in-elementary": "المزارع الخبير في المدرسة الابتدائية",
    # 3. نظام الانعكاس لا يظهر إلا بعد بلوغ مرحلة الماهايانا
    "نظام الانعكاس لا يظهر إلا بعد بلوغ مرحلة الماهايانا": "نظام الانعكاس لا يظهر إلا بعد بلوغ مرحلة الماهايانا",
    "mahayana-reflection": "نظام الانعكاس لا يظهر إلا بعد بلوغ مرحلة الماهايانا",
    # 4. رماد النبل وجمر التمرد
    "رَمادُ النُّبل وجمرُ التمرد": "رَمادُ النُّبل وجمرُ التمرد",
    "رماد النبل وجمر التمرد": "رَمادُ النُّبل وجمرُ التمرد",
    "noble-ash": "رَمادُ النُّبل وجمرُ التمرد",
    # 5. المهندس الأعظم
    "المهندس الأعظم": "المهندس الأعظم",
    "greatest-estate-developer": "المهندس الأعظم",
    "the-greatest-estate-developer": "المهندس الأعظم",
    # 6. ناسخ أسلحة الأكاديمية
    "ناسخ أسلحة الأكاديمية": "ناسخ أسلحة الأكاديمية",
    "the-academys-weapon-replicator": "ناسخ أسلحة الأكاديمية",
    # 7. عندما قرأت الطائفة بأكملها أفكاري
    "when the entire sect read my thoughts": "When the Entire Sect Read My Thoughts, the Plot Went Off the Rails",
    "entire sect": "When the Entire Sect Read My Thoughts, the Plot Went Off the Rails",
    "عندما قرأت الطائفة بأكملها أفكاري، انهارت الحبكة حقاً": "When the Entire Sect Read My Thoughts, the Plot Went Off the Rails",
    "when-the-entire-sect-read-my-thoughts-the-plot-went-off-the-rails": "When the Entire Sect Read My Thoughts, the Plot Went Off the Rails",
    # 8. بينما يزرع الآخرون، أنا أنهب فرص بطل الرواية
    "بينما يزرع الآخرون، أنا أنهب فرص بطل الرواية": "بينما يزرع الآخرون، أنا أنهب فرص بطل الرواية",
    "while others cultivate i snatch male leads opportunities": "بينما يزرع الآخرون، أنا أنهب فرص بطل الرواية",
    "while-others-cultivate-i-snatch-male-leads-opportunities": "بينما يزرع الآخرون، أنا أنهب فرص بطل الرواية",
    # 9. تلاميذ الأشرار جميعهم متيمون؟ الشيزون المتكاسلة تصول وتجول
    "تلاميذ الأشرار جميعهم متيمون؟ الشيزون المتكاسلة تصول وتجول": "تلاميذ الأشرار جميعهم متيمون؟ الشيزون المتكاسلة تصول وتجول",
    "the villain disciples are all simps? the slacking shizun runs wild": "تلاميذ الأشرار جميعهم متيمون؟ الشيزون المتكاسلة تصول وتجول",
    "the-villain-disciples-are-all-simps": "تلاميذ الأشرار جميعهم متيمون؟ الشيزون المتكاسلة تصول وتجول",
    "shizun": "تلاميذ الأشرار جميعهم متيمون؟ الشيزون المتكاسلة تصول وتجول",
    # 10. قيدت نفسي في الأرض المحرمة لـ 500 عام
    "قيدت نفسي في الأرض المحرمة لـ 500 عام، لمَ تبكون الآن وقد أصبحت مزارعاً حراً؟": "قيدت نفسي في الأرض المحرمة لـ 500 عام، لمَ تبكون الآن وقد أصبحت مزارعاً حراً؟",
    "confined in the forbidden ground for 500 years": "قيدت نفسي في الأرض المحرمة لـ 500 عام، لمَ تبكون الآن وقد أصبحت مزارعاً حراً؟",
    "confined-in-forbidden-ground-for-500": "قيدت نفسي في الأرض المحرمة لـ 500 عام، لمَ تبكون الآن وقد أصبحت مزارعاً حراً؟",
    # 11. لورد الشياطين شرير لدرجة الاستقامة
    "انتقال سريع: لورد الشياطين شرير لدرجة الاستقامة": "انتقال سريع: لورد الشياطين شرير لدرجة الاستقامة",
    "quick transmigration: the demon venerable is righteously evil": "انتقال سريع: لورد الشياطين شرير لدرجة الاستقامة",
    "quick-transmigration-the-demon-venerable-is-righteously-evil": "انتقال سريع: لورد الشياطين شرير لدرجة الاستقامة",
}

def _normalize_title_text(text: str) -> str:
    """تجريد وتوحيد نصوص العناوين للمقارنة الذكية (إزالة التشكيل وتوحيد الحروف)."""
    if not text:
        return ""
    t = str(text).lower().strip()
    t = re.sub(r'[إأآا]', 'ا', t)
    t = re.sub(r'[ىي]', 'ي', t)
    t = re.sub(r'ة', 'ه', t)
    t = re.sub(r'[\u064B-\u065F\u0670]', '', t)  # إزالة التشكيل
    t = re.sub(r'[^a-z0-9\u0600-\u06FF]', '', t)
    return t

def resolve_archive_novel_folder(novel_name: str) -> str:
    """تحديد اسم مجلد/سلسلة الرواية المطابق."""
    clean = str(novel_name).strip().lower()
    for k, v in NOVEL_NAME_MAPPINGS.items():
        if k in clean or clean in k:
            return v
    return re.sub(r'[<>:"/\\|?*]', '_', str(novel_name)).strip()

# كاش مؤقت لقائمة الروايات لتجنب الاستعلامات المتكررة
_ARABIC_NOVELS_CACHE = {"timestamp": 0.0, "novels": []}
_ENGLISH_NOVELS_CACHE = {"timestamp": 0.0, "novels": []}

def resolve_supabase_arabic_novel(novel_identifier: Union[str, int]) -> Optional[Dict[str, Any]]:
    """
    مطابقة ذكية وشاملة للرواية في قاعدة Supabase العربية المركزية.
    يدعم:
    - رقم الرواية المباشر أو الترتيب (id / sort_order) مثل: 9, '9', 'الرواية 9', 'الرواية ال9', 'novel 9'
    - العنوان الإنجليزي من custom_rules.title_en (مثل: 'The Villain Disciples Are All Simps...')
    - المعرف اللطيف slug
    - الاسم العربي name_ar مع التجريد وإزالة التشكيل
    - الاسم الأصلي name_original
    - جدول NOVEL_NAME_MAPPINGS
    """
    if not (SUPABASE_URL_AR and SUPABASE_KEY_AR):
        return None

    global _ARABIC_NOVELS_CACHE
    now_ts = time.time()
    novels = _ARABIC_NOVELS_CACHE["novels"]
    if now_ts - _ARABIC_NOVELS_CACHE["timestamp"] > 300 or not novels:
        headers = {
            "apikey": SUPABASE_KEY_AR,
            "Authorization": f"Bearer {SUPABASE_KEY_AR}"
        }
        try:
            url = f"{SUPABASE_URL_AR}/rest/v1/novels?select=id,name_ar,name_original,slug,custom_rules,status&order=id.asc"
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                novels = r.json()
                _ARABIC_NOVELS_CACHE = {"timestamp": now_ts, "novels": novels}
        except Exception as e_fetch:
            logger.debug(f"[extractor] Error fetching Arabic novels cache: {e_fetch}")

    if not novels:
        return None

    raw_str = str(novel_identifier).strip().lower()
    clean_q = _normalize_title_text(raw_str)

    # 1. فحص هل الإدخال رقم مباشر أو 'الرواية 9' / 'novel 9'
    num_match = re.search(r'(?:الرواية|novel)?\s*(?:الـ|ال)?(\d+)', raw_str, re.IGNORECASE)
    extracted_num = None
    if num_match and (raw_str.startswith(("الرواية", "novel", "novels")) or raw_str == num_match.group(1)):
        extracted_num = int(num_match.group(1))

    # فحص جدول NOVEL_NAME_MAPPINGS
    mapped_target = resolve_archive_novel_folder(raw_str)
    mapped_clean = _normalize_title_text(mapped_target)

    for n in novels:
        n_id = n.get("id")
        cr = {}
        try:
            cr = json.loads(n.get("custom_rules") or "{}") if isinstance(n.get("custom_rules"), str) else (n.get("custom_rules") or {})
        except Exception:
            cr = {}
        title_en = cr.get("title_en", "")
        sort_order = cr.get("sort_order")

        # أ. مطابقة الرقم المباشر أو الترتيب
        if extracted_num is not None:
            if n_id == extracted_num or (sort_order is not None and int(sort_order) == extracted_num):
                return n

        # ب. مطابقة العنوان الإنجليزي في custom_rules
        if title_en:
            t_en_clean = _normalize_title_text(title_en)
            if clean_q == t_en_clean or raw_str in title_en.lower() or title_en.lower() in raw_str:
                return n
            if mapped_clean and (mapped_clean == t_en_clean or mapped_target.lower() in title_en.lower()):
                return n

        # ج. مطابقة الـ slug
        slug = (n.get("slug") or "").strip().lower()
        if slug:
            s_clean = _normalize_title_text(slug)
            if slug in raw_str or raw_str in slug or clean_q == s_clean or (s_clean and s_clean in clean_q):
                return n

        # د. مطابقة الاسم العربي
        name_ar = n.get("name_ar") or ""
        if name_ar:
            ar_clean = _normalize_title_text(name_ar)
            if clean_q and (clean_q in ar_clean or ar_clean in clean_q):
                return n
            if mapped_clean and (mapped_clean in ar_clean or ar_clean in mapped_clean):
                return n

        # هـ. مطابقة الاسم الأصلي (name_original)
        name_orig = (n.get("name_original") or "").strip().lower()
        if name_orig and (raw_str in name_orig or name_orig in raw_str):
            return n

    return None

def resolve_supabase_english_novel(novel_identifier: Union[str, int]) -> Optional[Dict[str, Any]]:
    """
    مطابقة ذكية وشاملة للرواية في قاعدة Supabase الإنجليزية المركزية (novels_en).
    """
    if not (SUPABASE_URL_EN and SUPABASE_KEY_EN):
        return None

    global _ENGLISH_NOVELS_CACHE
    now_ts = time.time()
    novels = _ENGLISH_NOVELS_CACHE["novels"]
    if now_ts - _ENGLISH_NOVELS_CACHE["timestamp"] > 300 or not novels:
        headers = {
            "apikey": SUPABASE_KEY_EN,
            "Authorization": f"Bearer {SUPABASE_KEY_EN}"
        }
        try:
            url = f"{SUPABASE_URL_EN}/rest/v1/novels_en?select=id,name_en,name_original,slug,custom_rules,status&order=id.asc"
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                novels = r.json()
                _ENGLISH_NOVELS_CACHE = {"timestamp": now_ts, "novels": novels}
        except Exception as e_fetch:
            logger.debug(f"[extractor] Error fetching English novels cache: {e_fetch}")

    if not novels:
        return None

    raw_str = str(novel_identifier).strip().lower()
    clean_q = _normalize_title_text(raw_str)

    num_match = re.search(r'(?:الرواية|novel)?\s*(?:الـ|ال)?(\d+)', raw_str, re.IGNORECASE)
    extracted_num = int(num_match.group(1)) if num_match and (raw_str.startswith(("الرواية", "novel", "novels")) or raw_str == num_match.group(1)) else None

    mapped_target = resolve_archive_novel_folder(raw_str)
    mapped_clean = _normalize_title_text(mapped_target)

    for n in novels:
        n_id = n.get("id")
        name_en = (n.get("name_en") or "").strip().lower()
        slug = (n.get("slug") or "").strip().lower()
        name_orig = (n.get("name_original") or "").strip().lower()

        cr = {}
        try:
            cr = json.loads(n.get("custom_rules") or "{}") if isinstance(n.get("custom_rules"), str) else (n.get("custom_rules") or {})
        except Exception:
            cr = {}
        sort_order = cr.get("sort_order")

        if extracted_num is not None:
            if n_id == extracted_num or (sort_order is not None and int(sort_order) == extracted_num):
                return n

        if name_en:
            n_clean = _normalize_title_text(name_en)
            if clean_q == n_clean or raw_str in name_en or name_en in raw_str:
                return n
            if mapped_clean and (mapped_clean == n_clean or mapped_target.lower() in name_en):
                return n

        if slug:
            s_clean = _normalize_title_text(slug)
            if slug in raw_str or raw_str in slug or clean_q == s_clean or (s_clean and s_clean in clean_q):
                return n

        if name_orig and (raw_str in name_orig or name_orig in raw_str):
            return n

    return None

def fetch_chapter_from_arabic_supabase(novel_name: str, chapter_num: int) -> Optional[Dict[str, Any]]:
    """
    سحب الفصل مباشرة من قاعدة بيانات Supabase العربية (جدولا novels و chapters عبر REST API).
    - يحدد معرف الرواية بدقة صارمة لمنع خلط الفصول بين الروايات نهائياً.
    - يسمح فقط بالفصول ذات الحالات المعتمدة: APPROVED_CHAPTER_STATUSES
    - استرجاع ذكي: إذا كان trans_content مفرغاً وكان له post_url أو blogger_post_id يسترجع المتن تلقائياً.
    """
    if not (SUPABASE_URL_AR and SUPABASE_KEY_AR):
        return None

    headers = {
        "apikey": SUPABASE_KEY_AR,
        "Authorization": f"Bearer {SUPABASE_KEY_AR}",
        "Content-Type": "application/json"
    }

    try:
        # 1. مطابقة معرف الرواية بدقة صارمة
        matched_novel = resolve_supabase_arabic_novel(novel_name)
        if not matched_novel:
            logger.warning(f"[extractor] Could not resolve novel '{novel_name}' in Arabic Supabase. Will NOT fetch without novel_id.")
            return None

        novel_id = matched_novel["id"]

        # 2. الاستعلام عن الفصل حصراً باستخدام novel_id المطابق
        ch_url = f"{SUPABASE_URL_AR}/rest/v1/chapters?novel_id=eq.{novel_id}&chapter_number=eq.{chapter_num}&select=*&limit=5"
        resp = requests.get(ch_url, headers=headers, timeout=15)
        if resp.status_code == 200:
            rows = resp.json()
            if rows:
                target_row = None
                for r_item in rows:
                    st = str(r_item.get("status") or "").strip().upper()
                    if st in APPROVED_CHAPTER_STATUSES:
                        target_row = r_item
                        break

                if not target_row and rows:
                    # فحص احتياطي إذا لم يتطابق status ولكن يوجد محتوى مترجم
                    for r_item in rows:
                        if r_item.get("trans_content") or r_item.get("content"):
                            target_row = r_item
                            break

                if target_row:
                    raw_title = str(target_row.get("trans_title") or target_row.get("title") or target_row.get("raw_title") or f"الفصل {chapter_num}").strip()
                    html_content = target_row.get("trans_content") or target_row.get("content") or ""

                    # معالجة ذكية: إذا كان المتن مفرغاً في Supabase وله رابط تدوينة منشور
                    post_url = str(target_row.get("post_url") or target_row.get("url") or "").strip()
                    post_id = str(target_row.get("blogger_post_id") or target_row.get("post_id") or "").strip()
                    if (not html_content or len(html_content.strip()) < 50) and (post_url or post_id):
                        logger.info(f"[extractor] trans_content empty for ch {chapter_num}. Fetching from blogger post: {post_url or post_id}")
                        fetched_body = _fetch_post_content_via_gas(post_id, post_url)
                        if fetched_body:
                            html_content = fetched_body

                    if html_content:
                        clean_text = _strip_blogger_html(html_content, novel_name=novel_name, chapter_num=chapter_num, title=raw_title, lang="ar")
                        return {
                            "chapter_num": chapter_num,
                            "title": raw_title,
                            "content": clean_text,
                            "source": "arabic_supabase",
                            "post_url": post_url
                        }
    except Exception as e_sb_ar:
        logger.warning(f"[extractor] Error fetching chapter {chapter_num} from Arabic Supabase: {e_sb_ar}")

    return None

def fetch_chapter_from_english_supabase(novel_name: str, chapter_num: int) -> Optional[Dict[str, Any]]:
    """
    سحب الفصل مباشرة من قاعدة بيانات Supabase الإنجليزية المركزية (جدولا novels_en و chapters_en).
    - يحدد معرف الرواية بدقة صارمة لمنع خلط الفصول نهائياً.
    - يسمح فقط بالفصول ذات الحالات المعتمدة: APPROVED_CHAPTER_STATUSES
    - استرجاع ذكي: إذا كان trans_content مفرغاً يسترجع المتن من post_url.
    """
    if not (SUPABASE_URL_EN and SUPABASE_KEY_EN):
        return None
    try:
        headers = {
            "apikey": SUPABASE_KEY_EN,
            "Authorization": f"Bearer {SUPABASE_KEY_EN}",
            "Content-Type": "application/json"
        }

        # 1. مطابقة معرف الرواية بدقة صارمة
        matched_novel = resolve_supabase_english_novel(novel_name)
        if not matched_novel:
            logger.warning(f"[extractor] Could not resolve novel '{novel_name}' in English Supabase. Will NOT fetch without novel_id.")
            return None

        novel_id = matched_novel["id"]

        # 2. الاستعلام عن الفصل حصراً باستخدام novel_id المطابق
        url = f"{SUPABASE_URL_EN}/rest/v1/chapters_en?novel_id=eq.{novel_id}&chapter_number=eq.{chapter_num}&select=*&limit=5"
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            rows = resp.json()
            if rows:
                target_row = None
                for r_item in rows:
                    st = str(r_item.get("status") or "").strip().upper()
                    if st in APPROVED_CHAPTER_STATUSES:
                        target_row = r_item
                        break

                if not target_row and rows:
                    for r_item in rows:
                        if r_item.get("trans_content") or r_item.get("content"):
                            target_row = r_item
                            break

                if target_row:
                    raw_title = str(target_row.get("trans_title") or target_row.get("title_en") or target_row.get("title") or f"Chapter {chapter_num}").strip()
                    html_c = target_row.get("trans_content") or target_row.get("content") or ""

                    post_url = str(target_row.get("post_url") or target_row.get("url") or "").strip()
                    post_id = str(target_row.get("blogger_post_id") or target_row.get("post_id") or "").strip()
                    if (not html_c or len(html_c.strip()) < 50) and (post_url or post_id):
                        fetched = _fetch_post_content_via_gas(post_id, post_url)
                        if fetched:
                            html_c = fetched

                    if html_c:
                        clean_text = _strip_blogger_html(html_c, novel_name=novel_name, chapter_num=chapter_num, title=raw_title, lang="en")
                        return {
                            "chapter_num": chapter_num,
                            "title": raw_title,
                            "content": clean_text,
                            "source": "english_supabase",
                            "post_url": post_url
                        }
    except Exception as e_sb_en:
        logger.warning(f"[extractor] Error fetching chapter {chapter_num} from English Supabase: {e_sb_en}")
    return None

def fetch_chapter_from_github_archive(
    novel_name: str,
    chapter_num: int,
    repo: Optional[str] = None,
    source_site: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    تحويل تلقائي ومباشر إلى Supabase (العربي أو الإنجليزي) للتوافق الخلفي التام
    دون الاعتماد على مستودعات GitHub القديمة.
    """
    if source_site == "en" or (repo and "en" in str(repo).lower()):
        data = fetch_chapter_from_english_supabase(novel_name, chapter_num)
        if data:
            return data
        return fetch_chapter_from_arabic_supabase(novel_name, chapter_num)
    else:
        data = fetch_chapter_from_arabic_supabase(novel_name, chapter_num)
        if data:
            return data
        return fetch_chapter_from_english_supabase(novel_name, chapter_num)

# ─────────────────────────────────────────────────────────
# معرفات الجداول والإعدادات (من خريطة_المنظومة.md)
# ─────────────────────────────────────────────────────────
TRANSLATE_SHEET_ID      = "1FcehVXh-GLlZGePTm2nm13N932qcFeT0uGuOsXRFXpI"  # شيت الترجمة الشخصي
PUBLIC_PUBLISHED_SHEET_ID = "1IFT9mKRFByiPhph-ZaSdUT7c6IPUWpLg6Gj2xa9g5mY"  # شيت المنشورات العام
GAS_WEBAPP_URL = os.getenv("NSW_GAS_WEBAPP_URL") or "https://script.google.com/macros/s/AKfycbxqLaqJru1ag-am7G9Mrwy5Nb7HliZlK5vbIEQD9MeV3wOOquNUvz4d7vWEwZxkBI6zIw/exec"

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
# تجريد HTML وتنظيف المتن السردي (معالجة Supabase وبلوجر الخاصة)
# ─────────────────────────────────────────────────────────

def _strip_blogger_html(
    html: str,
    novel_name: str = "",
    chapter_num: int = 0,
    title: str = "",
    lang: str = "ar"
) -> str:
    """
    تجريد وتطهير محتوى الفصول المخزنة في Supabase وبلوجر بالكامل:
    1. حذف أكواد السيو وJSON-LD وسكريبتات بلوجر وأنماط CSS وSVG تماماً بمحتواها.
    2. حذف العناصر المخفية مثل dynamic-novel-name وأي عنصر display:none.
    3. حذف أشرطة التنقل والإعلانات وكبسولات الجدولة بمحتواها.
    4. معالجة وسوم الاستوديو السردية (BBCode و HTML classes) وتحويلها لفواصل أنيقة 【 ... 】 مع الحفاظ على النص الداخلي.
    5. فك تشفير HTML Entities وتجريد كافة الوسوم الخام المتبقية.
    """
    if not html:
        return ""
    text = str(html)

    # 1. حذف كود JSON-LD وSchema.org والتعليقات بالكامل
    text = re.sub(r'<!--.*?-->', ' ', text, flags=re.DOTALL)
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<svg[^>]*>.*?</svg>', ' ', text, flags=re.IGNORECASE | re.DOTALL)

    # 2. حذف العناصر المخفية لاسم الرواية مثل dynamic-novel-name وأي display:none
    text = re.sub(r'<span[^>]*id=["\']dynamic-novel-name["\'][^>]*>.*?</span>', ' ', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<[^>]+style=["\'][^"\']*display\s*:\s*none[^"\']*["\'][^>]*>.*?</[^>]+>', ' ', text, flags=re.IGNORECASE | re.DOTALL)

    # 3. حذف أشرطة التنقل والإعلانات وكبسولات الجدولة بمحتواها بالكامل
    ad_nav_div_patterns = [
        r'<div[^>]*class=["\'][^"\']*(?:nsw-chapter-nav|nsw-nav-bar|nsw-sched-banner|sponsored|banner-ad|ad-box|navigation|button|share)[^"\']*["\'][^>]*>.*?</div>',
        r'<nav[^>]*>.*?</nav>',
        r'<a[^>]*>(?:\s*(?:الفصل\s+(?:التالي|السابق)|السابق|التالي|الفهرس|&lt;&lt;|&gt;&gt;|[«»→←▶◀⏮⏭])[^<]*)</a>',
        r'<div[^>]*id=["\'](?:ad-|banner|sponsored).*?["\'][^>]*>.*?</div>'
    ]
    for pat in ad_nav_div_patterns:
        text = re.sub(pat, ' ', text, flags=re.IGNORECASE | re.DOTALL)

    # 4. حذف أزرار الحواشي السفلية إن وجدت مثل <span class="nsw-note-trigger">[1]</span>
    text = re.sub(r'<span[^>]*class=["\'][^"\']*nsw-note-trigger[^"\']*["\'][^>]*>.*?</span>', '', text, flags=re.IGNORECASE | re.DOTALL)

    # 5. معالجة وسوم الاستوديو السردية BBCode (الحفاظ الكامل على النص بداخلها)
    bbcode_tags = [
        "mind-voice", "system", "cultivation", "doc", "letter",
        "note", "tip", "log", "rift", "status", "panel"
    ]
    for tag in bbcode_tags:
        text = re.sub(rf'\[{tag}[^\]]*\]', '\n\n【 ', text, flags=re.IGNORECASE)
        text = re.sub(rf'\[/{tag}\]', ' 】\n\n', text, flags=re.IGNORECASE)

    # معالجة حواشي [fn=...]...[/fn]
    text = re.sub(r'\[fn=[^\]]*\](.*?)\[/fn\]', r' (حاشية: \1) ', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'\[/?fn[^\]]*\]', '', text, flags=re.IGNORECASE)

    # 6. معالجة الحاويات وصناديق النظام السردية في HTML (تحويلها لفواصل سردية واضحة 【 ... 】)
    narrative_box_classes = [
        "system", "nsw-mind-voice", "nsw-trans-voice", "nsw-official-doc",
        "doc-title", "doc-body", "doc-seal", "nsw-rift",
        "nsw-system-log", "status-window", "nsw-en-status", "nsw-tip", "personal-letter"
    ]
    for nbc in narrative_box_classes:
        text = re.sub(rf'<div[^>]*class=["\'][^"\']*{nbc}[^"\']*["\'][^>]*>', '\n\n【 ', text, flags=re.IGNORECASE)

    # 7. حاويات التغليف السردية العادية (تحويلها لفواصل أسطر)
    wrapper_classes = [
        "nsw-chapter-wrapper", "reading-content", "actual-text",
        "nsw-text-body", "nsw-en-text-body", "nsw-paragraph", "nsw-en-paragraph"
    ]
    for wc in wrapper_classes:
        text = re.sub(rf'</?(?:div|p)[^>]*class=["\'][^"\']*{wc}[^"\']*["\'][^>]*>', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(rf'</?(?:div|p)[^>]*id=["\'][^"\']*{wc}[^"\']*["\'][^>]*>', '\n\n', text, flags=re.IGNORECASE)

    # 8. حذف أي بقايا CSS هاربة مثل { color: ...; font-size: ... }
    text = re.sub(r'\{[^{}]*(?:color|font|margin|padding|background|border|font-size)[^{}]*\}', '', text, flags=re.IGNORECASE)

    # 9. تحويل وسوم الفقرات والأسطر الشائعة
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</?(?:p|div|h[1-6]|li|blockquote)[^>]*>', '\n', text, flags=re.IGNORECASE)

    # 10. تجريد أي وسوم HTML متبقية
    text = re.sub(r'<[^>]+>', '', text)

    # 11. فك تشفير كافة رموز HTML Entities
    import html as _html
    text = _html.unescape(text)

    # 12. تجريد أي وسوم BBCode تنسيقية متبقية (مثل [b], [/b], [color], إلخ)
    text = re.sub(r'\[/?(?:b|i|u|color|size|font|center|quote|align)[^\]]*\]', '', text, flags=re.IGNORECASE)

    # 13. توحيد الأسطر وتطهير الفواصل المفرطة
    return clean_chapter_paragraphs(text, novel_name=novel_name, chapter_num=chapter_num, title=title)


def format_standard_chapter_title(raw_title: str, chapter_num: int, novel_name: str = "", lang: str = "ar") -> str:
    """
    توحيد صيغة عنوان الفصل بدقة متناهية:
    للعربي: 'الفصل {chapter_num}: {العنوان_الفرعي}' أو 'الفصل {chapter_num}'
    للإنجليزي: 'Chapter {chapter_num}: {Sub_Title}' أو 'Chapter {chapter_num}'
    """
    t = raw_title.strip()
    is_english = (lang == "en") or bool(re.search(r'^[A-Za-z0-9\s\':\-—–|,.]+$', t))
    prefix = "Chapter" if is_english else "الفصل"

    # 1. إزالة اسم الرواية إن وجد في البداية
    if novel_name:
        t = re.sub(r'^\s*' + re.escape(novel_name.strip()) + r'\s*[:\-—–|]*\s*', '', t, flags=re.IGNORECASE)

    # تنظيف أي تكرار لاسم الرواية الإنجليزية أو الفواصل
    if not is_english:
        t = re.sub(r'^[A-Za-z\s\']+\s*[:\-—–|]+\s*', '', t).strip()

    # 2. استخراج العنوان الفرعي
    m = re.search(r'(?:الفصل|chapter)\s*' + str(chapter_num) + r'\s*[:\-—–|]+\s*(.+)', t, re.IGNORECASE)
    if m:
        sub = m.group(1).strip()
        sub = re.sub(r'^[:\-—–|\s]+', '', sub).strip()
        if sub:
            return f"{prefix} {chapter_num}: {sub}"
        return f"{prefix} {chapter_num}"

    m = re.search(r'(?:الفصل|chapter)\s*' + str(chapter_num) + r'\s+(.+)', t, re.IGNORECASE)
    if m:
        sub = m.group(1).strip()
        sub = re.sub(r'^[:\-—–|\s]+', '', sub).strip()
        if sub:
            return f"{prefix} {chapter_num}: {sub}"
        return f"{prefix} {chapter_num}"

    # إذا كان فقط رقم أو كلمة الفصل/Chapter
    m_num_only = re.search(r'^(?:.*(?:الفصل|chapter)\s*)?' + str(chapter_num) + r'\s*$', t, re.IGNORECASE)
    if m_num_only:
        return f"{prefix} {chapter_num}"

    # إذا كان هناك فاصل
    if any(sep in t for sep in [' - ', ' — ', ' : ', ':']):
        parts = re.split(r'[:\-—–|]', t)
        last_part = parts[-1].strip()
        if last_part and not re.search(r'^\d+$', last_part):
            return f"{prefix} {chapter_num}: {last_part}"

    # تنظيف البقايا
    clean = re.sub(r'^(?:الفصل|chapter)\s*\d*\s*[:\-—–\s]*', '', t, flags=re.IGNORECASE).strip()
    if clean and clean != str(chapter_num):
        return f"{prefix} {chapter_num}: {clean}"
    return f"{prefix} {chapter_num}"


def clean_chapter_paragraphs(raw_text: str, novel_name: str = "", chapter_num: int = 0, title: str = "") -> str:
    """
    تنسيق وتنظيف فقرات الفصل:
    1. حذف تكرار العنوان ورقم الفصل واسم الرواية من بداية المتن لمنع تكرار العنوان مرتين.
    2. تنظيم الأسطر كفقرات مستقلة ومرتبة.
    3. إزالة ترويسات الإعلانات وأزرار التنقل السفلية.
    """
    text = raw_text.strip()
    raw_lines = [l.strip() for l in text.splitlines()]
    paras = [l for l in raw_lines if l]

    novel_clean = novel_name.strip().lower()
    title_clean = title.strip().lower()

    # تنظيف مقدمة المحتوى من الترويسات وتكرار العنوان
    while paras:
        first = paras[0]
        first_low = first.lower()

        # إعلانات أو فواصل
        if "إعلان مُموَّل" in first or "mondiad" in first_low or first in ["📢", "---", "***", "___", "===", "###"]:
            paras.pop(0)
            continue

        # اسم الرواية منفرداً
        if novel_clean and (first_low == novel_clean or first_low.startswith(novel_clean)):
            paras.pop(0)
            continue

        # العنوان المتطابق مع trans_title الممرر
        if title_clean and (first_low == title_clean or first_low in title_clean):
            paras.pop(0)
            continue

        # سطر الفصل / العنوان المكرر في بداية المحتوى (مثل 'الفصل 105: ...' أو 'Chapter 105')
        if chapter_num > 0 and (
            str(chapter_num) in first and any(k in first_low for k in ["فصل", "chapter", "ch.", "part", novel_clean])
        ) or first.startswith("الفصل") or first_low.startswith("chapter"):
            paras.pop(0)
            continue

        break

    # تنظيف ذيل المحتوى من أزرار التنقل الزائدة
    while paras:
        last = paras[-1].lower()
        if any(nav in last for nav in ["الفصل التالي", "الفصل السابق", "chapter next", "chapter prev", "فهرس الفصول"]):
            paras.pop()
            continue
        break

    # ضبط فواصل مربعات النظام المتتالية
    cleaned_result = "\n\n".join(paras).strip()
    cleaned_result = re.sub(r'【\s*】', '', cleaned_result)
    cleaned_result = re.sub(r'\n{3,}', '\n\n', cleaned_result)
    return cleaned_result


# ─────────────────────────────────────────────────────────
# الدالة الرئيسية: اجلب الفصل المجهّز جاهزاً للنشر
# ─────────────────────────────────────────────────────────

def prepare_chapter_for_publishing(
    novel_name: str,
    chapter_num: int,
    custom_cta: str = "",
    blogger_url: str = "",
    source_site: str = "ar",
    archive_repo: str = ""
) -> Dict[str, Any]:
    """
    الدالة الرئيسية التي تجمع:
      1. سحب الفصل من Supabase (العربية أو الإنجليزية بحسب مصدر الرواية مع توفر Fallback)
      2. تنظيف المتن وتنسيق الفقرات وفصل العنوان بدقة
      3. توحيد صيغة العنوان لتكون حصراً 'الفصل {num}: {title}' أو 'Chapter {num}: {title}'
      4. دمج الخاتمة التحفيزية المخصصة لكل منصة
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

    data = None
    if source_site == "en":
        # 1. سحب من قاعدة Supabase الإنجليزية المركزية (novels_en / chapters_en)
        data = fetch_chapter_from_english_supabase(novel_name, chapter_num)
        # 2. احتياطي: قاعدة Supabase العربية
        if not data:
            data = fetch_chapter_from_arabic_supabase(novel_name, chapter_num)
    else:
        # 1. سحب من قاعدة Supabase العربية المركزية (novels / chapters)
        data = fetch_chapter_from_arabic_supabase(novel_name, chapter_num)
        # 2. احتياطي: حاول من شيت الترجمة الشخصي
        if not data:
            data = fetch_chapter_from_translate_sheet(novel_name, chapter_num)
        # 3. احتياطي: شيت المنشورات العام 1IFT
        if not data:
            logger.info(f"[extractor] {novel_name} ف{chapter_num}: لم يُوجد بـ Supabase أو شيت الترجمة، أجرب 1IFT...")
            data = fetch_chapter_from_published_sheet(novel_name, chapter_num)
        # 4. احتياطي إنجليزي
        if not data:
            data = fetch_chapter_from_english_supabase(novel_name, chapter_num)

    if not data:
        result["error"] = f"تعذّر إيجاد الفصل {chapter_num} لرواية '{novel_name}' في Supabase أو الجداول المتاحة (المصدر: {source_site})."
        return result

    # === 3. توحيد صيغة العنوان بدقة بحسب اللغة ===
    title_clean = format_standard_chapter_title(data["title"], chapter_num, novel_name, lang=source_site)

    # === 4. تنظيف وتنسيق المتن وحذف الترويسات والإعلانات وفصل الفقرات ===
    content_clean = clean_chapter_paragraphs(data["content"], novel_name, chapter_num, title=title_clean)
    
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

    # 4. معالجة منصة Novel Updates
    elif platform == "novelupdates":
        import novelupdates_poster
        clean_nu = clean_p_url
        clean_site = clean_b_url

        # 1. استخراج المعرف واسم السلسلة من رابط Novel Updates أو الاسم المدخل
        series_slug = ""
        series_title_cand = ""
        if "novelupdates.com/series/" in clean_nu:
            part = clean_nu.split("novelupdates.com/series/")[-1].strip("/").split("/")[0].split("?")[0]
            series_slug = part.strip()
            series_title_cand = series_slug.replace("-", " ").title()
        elif clean_nu:
            series_slug = clean_nu.strip().rstrip("/")
            series_title_cand = series_slug.replace("-", " ").title()

        res["clean_id"] = series_slug
        res["series_url"] = clean_nu if clean_nu.startswith("http") else (f"https://www.novelupdates.com/series/{series_slug}/" if series_slug else "")

        # 2. استخراج وتطبيع الدومين المخصص من رابط الموقع
        custom_domain = ""
        if clean_site:
            try:
                p_site = urllib.parse.urlparse(clean_site)
                if p_site.netloc:
                    custom_domain = f"{p_site.scheme or 'https'}://{p_site.netloc}"
                else:
                    custom_domain = clean_site.split("/")[0]
            except Exception:
                custom_domain = clean_site
            if custom_domain:
                custom_domain = novelupdates_poster.normalize_custom_domain(custom_domain)
        res["custom_domain"] = custom_domain

        # 3. مطابقة الرواية مع latest_chapters.json لمعرفة الاسم الكامل وأحدث الفصول المنشورة
        matched_title = ""
        matched_link = ""
        max_ch = 0
        try:
            feed = novelupdates_poster.get_latest_chapters_feed()
            ref_str = f"{series_slug} {site_title} {clean_site}".lower()
            tokens = set(re.findall(r'[a-zA-Z]{3,}', ref_str))

            for item in feed:
                i_title = item.get("novelTitle", "")
                i_link = item.get("novelLink", "")
                try:
                    i_num = int(item.get("num", 0))
                except (ValueError, TypeError):
                    i_num = 0

                is_match = False
                if clean_site and (clean_site.rstrip("/?") in i_link or i_link.rstrip("/?") in clean_site):
                    is_match = True
                elif tokens:
                    t_title = set(re.findall(r'[a-zA-Z]{3,}', i_title.lower()))
                    if len(tokens.intersection(t_title)) >= 2:
                        is_match = True

                if is_match:
                    if not matched_title:
                        matched_title = i_title
                    if not matched_link:
                        matched_link = i_link
                    if i_num > max_ch:
                        max_ch = i_num
        except Exception as e_feed:
            logger.warning(f"[inspect_novel_links] Error checking latest_chapters.json: {e_feed}")

        chosen_name = matched_title or site_title or series_title_cand or (f"Series {series_slug}" if series_slug else "")
        res["novel_name"] = chosen_name
        res["blogger_label"] = chosen_name
        if not res["blogger_url"] and matched_link:
            res["blogger_url"] = matched_link
            if not res["custom_domain"]:
                res["custom_domain"] = novelupdates_poster.normalize_custom_domain(matched_link)

        res["start_chapter"] = 1
        res["last_chapter"] = 0
        res["stop_chapter"] = max_ch if max_ch > 0 else 50
        res["success"] = bool(clean_nu or clean_site or matched_title)

    return res


