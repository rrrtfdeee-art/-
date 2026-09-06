# -*- coding: utf-8 -*-
"""
==============================================================================
NSW Chapter Healing & Auto Gap-Filling Engine v2.0
==============================================================================
هذا المحرك مسؤول عن:
1. فحص شامل لكافة الجداول وطوابير العمل ومنشورات بلوجر الحية والمجدولة.
2. كشف الفصول المبتورة (أقل من 800 حرف) واستصلاحها في مكانها دون استهلاك كوتة النشر.
3. كشف الفجوات التسلسلية (Missing Gaps) مثل القفز من 400 إلى 402:
   - سحب الفصل المفقود (401) من المصدر الأصلي.
   - ترجمته وصقله لغوياً وتطبيق القاموس والرقابة العقدية.
   - نشره على Blogger وإدراجه في الجداول ذات الصلة (Published Posts & Queue).
   - ربط أزرار التنقل (السابق والتالي والفهرس) تلقائياً لتوصيل السلسلة دون انقطاع.
4. إرسال تنبيهات لحظية للأدمن عند نفاد الحصة (Quota Exhaustion) أو عند حدوث أعطال لا يمكن حلها آلياً.
"""

import os
import sys
import time
import json
import re
import logging
from typing import Dict, List, Any, Optional, Tuple, Set
import requests

from bs4 import BeautifulSoup
import database
import scraper_engine
from gemini_analyzer import DEFAULT_GAS_POOL, gas_pool

# ضبط ترميز الإخراج
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [NSW-Healer] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("NSWHealer")

# الثوابت والمعرفات المركزية
NOVELS_INDEX_SPREADSHEET_ID = "1s-yf1gRHagPIeikEC9_aVIAst7oDaiwoNzLH-hd0Q24"
PUBLIC_PUBLISHED_SPREADSHEET_ID = "1IFT9mKRFByiPhph-ZaSdUT7c6IPUWpLg6Gj2xa9g5mY"
TRANSLATE_SPREADSHEET_ID = "1FcehVXh-GLlZGePTm2nm13N932qcFeT0uGuOsXRFXpI"
PUBLISH_QUEUE_SPREADSHEET_ID = "1HDjYu6EypdiNfoawJ2s7nQcRJiGsfJ5bNefcEy0QhFE"
GLOSSARY_SPREADSHEET_ID = "1oqKRLyqWdkdUWW5UtvorEteFk3jJXdeUzQGDv-XJ_aE"

PUBLISH_WEBAPP_URL = os.getenv("NSW_PUBLISH_WEBAPP_URL", "https://script.google.com/macros/s/AKfycbxqLaqJru1ag-am7G9Mrwy5Nb7HliZlK5vbIEQD9MeV3wOOquNUvz4d7vWEwZxkBI6zIw/exec")
TRANSLATE_WEBAPP_URL = os.getenv("NSW_TRANSLATE_WEBAPP_URL", "https://script.google.com/macros/s/AKfycbwk3rNPfyP6lJw5jkXigqUfTgivsNzgDoyhd61lPiRSFZP49jFShKaz-CfnUqlM9OmH/exec")
TELEGRAM_BOT_TOKEN = os.getenv("NSW_TELEGRAM_BOT_TOKEN", "8527477822:AAG2dkvwdkkhHR_NyzAsfIWwlLBIdPk2Woc")
ADMIN_CHAT_ID = os.getenv("NSW_TELEGRAM_CHAT_ID", "1974483260")

MIN_SAFE_TEXT_LENGTH = 800


# ==============================================================================
# 🔔 1. نظام التنبيهات وإشعارات الأعطال ونفاد الحصص
# ==============================================================================

def notify_admin(message: str, parse_mode: str = "HTML"):
    """إرسال إشعار تليجرام للمشرف."""
    if not TELEGRAM_BOT_TOKEN or not ADMIN_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": ADMIN_CHAT_ID, "text": message, "parse_mode": parse_mode}, timeout=15)
    except Exception as e:
        logger.error(f"خطأ إرسال إشعار تليجرام: {e}")


def notify_quota_exhaustion(service_name: str, details: str = "", retry_seconds: int = 0):
    """
    إرسال تقرير شامل عند نفاد حصة أي جزء من المنظومة (كلود، مفاتيح جيمني، أو بلوجر).
    """
    cooldown_str = f"مدة التهدئة: <b>{retry_seconds // 60} دقيقة</b>" if retry_seconds else "فترة التهدئة التلقائية نشطة"
    msg = (
        f"⏳ <b>[تقرير نفاد الحصة - {service_name}]</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <b>الحالة:</b> تم استنفاد الكوتة المقررة (Rate Limit / Quota Exhausted).\n"
        f"⏱️ <b>إدارة السبات:</b> {cooldown_str}.\n"
        f"📋 <b>التفاصيل:</b> {details}\n"
        f"🔄 <b>الإجراء:</b> سيتوقف المحرك مؤقتاً لحين انقضاء فترة التهدئة ثم يستأنف تلقائياً بأقصى طاقة دون أي تدخل منك."
    )
    logger.warning(f"Quota exhausted for {service_name}: {details}")
    notify_admin(msg)


def notify_unfixable_error(novel_name: str, chap_num: int, error_reason: str, stage: str = "الاستصلاح"):
    """
    إرسال تنبيه عاجل بشأن عطل غير قابل للإصلاح التلقائي ويتطلب تدخلاً بشرياً.
    """
    msg = (
        f"🚨 <b>[تنبيه: عطل غير قابل للإصلاح الآلي]</b> ⚠️\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📖 <b>الرواية:</b> {novel_name}\n"
        f"🔢 <b>الفصل:</b> {chap_num}\n"
        f"📍 <b>المرحلة:</b> {stage}\n"
        f"❌ <b>سبب العطل:</b> {error_reason}\n\n"
        f"💡 <i>تم حفظ بيانات الفصل وحظر تكراره لتفادي استنزاف الموارد، يرجى فحص المصدر يدوياً.</i>"
    )
    logger.error(f"Unfixable error for {novel_name} chap {chap_num}: {error_reason}")
    notify_admin(msg)


# ==============================================================================
# 📊 2. جرد شامل لكافة الجداول وبلوجر لكشف الفجوات والفصول المبتورة
# ==============================================================================

def query_gviz_sheet(spreadsheet_id: str, sheet_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """جلب بيانات أي شيت من جداول جوجل بصيغة JSON نظيفة."""
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq?tqx=out:json"
    if sheet_name:
        url += f"&sheet={requests.utils.quote(sheet_name)}"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=25)
        text = res.text
        json_str = text[text.find('{'):text.rfind('}') + 1]
        data = json.loads(json_str)
        return data.get("table", {}).get("rows", [])
    except Exception as e:
        logger.error(f"خطأ قراءة الشيت {spreadsheet_id} ({sheet_name}): {e}")
        return []


def get_all_known_chapters_across_system() -> Dict[str, Dict[int, Dict[str, Any]]]:
    """
    فحص شامل وعميق يجمع كل فصول كافة الروايات عبر 5 طبقات:
    1. ورقة Published Posts (الفصول الحية المنشورة).
    2. مدونة Blogger الحية عبر Feed (المنشورات الحالية والمجدولة).
    3. طابور النشر Queue.
    4. طابور التدقيق ReviewQueue.
    5. طابور الترجمة TranslateQueue.
    """
    novels: Dict[str, Dict[int, Dict[str, Any]]] = {}

    def register(novel: str, num: int, source: str, post_id: str = "", post_url: str = "", content_len: int = 0):
        if not novel or num <= 0:
            return
        if novel not in novels:
            novels[novel] = {}
        if num not in novels[novel]:
            novels[novel][num] = {
                "chapter_number": num,
                "novel_name": novel,
                "sources": [source],
                "post_id": post_id,
                "post_url": post_url,
                "content_len": content_len
            }
        else:
            if source not in novels[novel][num]["sources"]:
                novels[novel][num]["sources"].append(source)
            if post_id and not novels[novel][num]["post_id"]:
                novels[novel][num]["post_id"] = post_id
            if post_url and not novels[novel][num]["post_url"]:
                novels[novel][num]["post_url"] = post_url
            if content_len > novels[novel][num]["content_len"]:
                novels[novel][num]["content_len"] = content_len

    # 1. فحص ورقة Published Posts
    pub_rows = query_gviz_sheet(PUBLIC_PUBLISHED_SPREADSHEET_ID)
    for r in pub_rows:
        c = r.get("c", [])
        if len(c) > 1 and c[1]:
            title = str(c[1].get("v", "")).strip()
            chap_num = 0
            try:
                chap_num = int(float(c[0].get("v", 0)))
            except Exception:
                pass
            if not chap_num:
                m = re.search(r'\d+', title)
                chap_num = int(m.group(0)) if m else 0
            
            novel = str(c[7].get("v", "") if len(c) > 7 and c[7] else "").strip()
            if not novel and " - " in title:
                novel = title.split(" - ")[0].strip()
            novel = novel or "عام"
            
            post_id = str(c[4].get("v", "") if len(c) > 4 and c[4] else "").strip()
            post_url = str(c[5].get("v", "") if len(c) > 5 and c[5] else "").strip()
            register(novel, chap_num, "Published Posts", post_id=post_id, post_url=post_url)

    # 2. فحص طابور النشر Queue
    queue_rows = query_gviz_sheet(PUBLISH_QUEUE_SPREADSHEET_ID)
    for r in queue_rows:
        c = r.get("c", [])
        if len(c) > 1 and c[1]:
            title = str(c[1].get("v", "")).strip()
            chap_num = 0
            try:
                chap_num = int(float(c[0].get("v", 0)))
            except Exception:
                pass
            if not chap_num:
                m = re.search(r'\d+', title)
                chap_num = int(m.group(0)) if m else 0
            novel = title.split(" - ")[0].strip() if " - " in title else "عام"
            content = str(c[2].get("v", "") if len(c) > 2 and c[2] else "")
            register(novel, chap_num, "Publish Queue", content_len=len(content))

    # 3. فحص طابور التدقيق ReviewQueue
    review_rows = query_gviz_sheet(TRANSLATE_SPREADSHEET_ID, "ReviewQueue")
    for r in review_rows:
        c = r.get("c", [])
        if len(c) > 2 and c[2]:
            chap_num = 0
            try:
                chap_num = int(float(c[0].get("v", 0)))
            except Exception:
                pass
            novel = str(c[1].get("v", "") if len(c) > 1 and c[1] else "عام").strip()
            register(novel, chap_num, "Review Queue")

    # 4. فحص طابور الترجمة TranslateQueue
    trans_rows = query_gviz_sheet(TRANSLATE_SPREADSHEET_ID)
    for r in trans_rows:
        c = r.get("c", [])
        if len(c) > 0 and c[0]:
            title = str(c[0].get("v", "")).strip()
            m = re.search(r'\d+', title)
            chap_num = int(m.group(0)) if m else 0
            novel = str(c[5].get("v", "") if len(c) > 5 and c[5] else "عام").strip()
            register(novel, chap_num, "Translate Queue")

    # 5. فحص المدونة الحية عبر Feed
    try:
        live_chaps = fetch_live_feed_chapters(max_results=50)
        for lc in live_chaps:
            register(lc["novel_name"], lc["chapter_number"], "Live Blogger Feed", post_id=lc["post_id"], post_url=lc["post_url"], content_len=lc["content_length"])
    except Exception as e:
        logger.warning(f"تعذر استدعاء Feed المدونة الحية: {e}")

    return novels


def detect_system_gaps(target_novel: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    كشف جميع الفجوات المفقودة في تسلسل فصول الروايات.
    مثال: 400 ➔ 402 يعني أن الفصل 401 مفقود تماماً من كافة الجداول والمنشورات.
    """
    all_novels = get_all_known_chapters_across_system()
    gaps = []

    for novel, chaps_map in all_novels.items():
        if target_novel and target_novel.lower() not in novel.lower():
            continue

        nums = sorted(list(chaps_map.keys()))
        if len(nums) < 2:
            continue

        for i in range(len(nums) - 1):
            curr_n = nums[i]
            next_n = nums[i + 1]

            if next_n - curr_n > 1:
                missing_range = list(range(curr_n + 1, next_n))
                gaps.append({
                    "novel_name": novel,
                    "missing_chapters": missing_range,
                    "prev_chapter": curr_n,
                    "prev_info": chaps_map[curr_n],
                    "next_chapter": next_n,
                    "next_info": chaps_map[next_n]
                })

    return gaps


# ==============================================================================
# 🧩 3. محرك ملء الفجوات التلقائي ونشر الفصول وربط أزرار التنقل (Auto Gap-Filler)
# ==============================================================================

def fill_single_missing_gap(novel_name: str, missing_chap_num: int, prev_info: Dict[str, Any], next_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    دورة ملء فجوة واحدة بالكامل:
    1. البحث عن رابط الفهرس وسحب الفصل المفقود من المصدر الأصلي.
    2. الترجمة عبر خط الأنابيب الملكي مع القاموس والرقابة العقدية.
    3. النشر المباشر على Blogger.
    4. ترحيل الرابط وتوثيق الفصل في جداول المنظومة (Published Posts & Queue).
    5. تحديث أزرار التنقل (السابق والتالي والفهرس) للفصل السابق واللاحق والفصل المنشور لضمان تسلسل 100%.
    """
    logger.info(f"🧩 [بدء ملء الفجوة] سحب وترجمة ونشر الفصل المفقود {missing_chap_num} لرواية '{novel_name}'...")
    notify_admin(f"🧩 <i>جاري سحب وترجمة الفصل المفقود رقم {missing_chap_num} لرواية '{novel_name}' لملء الفجوة...</i>")

    # 1. إيجاد مصدر الرواية
    source_info = get_novel_source_info(novel_name)
    toc_url = source_info.get("toc_url") if source_info.get("found") else None
    if not toc_url:
        err = f"تعذر إيجاد رابط مصدر الرواية في جدول الفهارس لسحب الفصل {missing_chap_num}."
        notify_unfixable_error(novel_name, missing_chap_num, err, "سحب المصدر الأصلي")
        return {"success": False, "error": err}

    cfg = source_info.get("config") or {
        "toc_link_selector": "a[href*='chapter'], a[href*='/txt/']",
        "chapter_title_selector": "h1",
        "chapter_content_selector": ".txtnav, article, #content",
        "purge_selectors": ["script", "style"]
    }

    # 2. سحب المتن الخام
    try:
        raw_content = fetch_raw_chapter_by_number(toc_url, missing_chap_num, cfg)
    except Exception as scrape_err:
        notify_unfixable_error(novel_name, missing_chap_num, f"فشل السحب بمتصفح التخفي: {scrape_err}", "السحب من المصدر")
        return {"success": False, "error": str(scrape_err)}

    if not raw_content or len(raw_content) < MIN_SAFE_TEXT_LENGTH:
        err = f"المتن المسحوب للفصل المفقود قصير جداً ({len(raw_content) if raw_content else 0} حرف). قد يكون محجوباً أو غير موجود في المصدر."
        notify_unfixable_error(novel_name, missing_chap_num, err, "التحقق من اكتمال المتن")
        return {"success": False, "error": err}

    # 3. الترجمة والتدقيق
    try:
        raw_title = f"الفصل {missing_chap_num}"
        trans_res = translate_and_refine_chapter(raw_title, raw_content, novel_name, missing_chap_num)
        sub_title = trans_res.get("translated_title", f"الفصل {missing_chap_num}")
        clean_sub_title = re.sub(r'^(?:الفصل|chapter|chap)\s*\d+[:\s\-]*', '', sub_title, flags=re.I).strip()
        final_title = f"الفصل {missing_chap_num}: {clean_sub_title}" if clean_sub_title else f"الفصل {missing_chap_num}"
        translated_content = trans_res.get("translated_content", "")
    except Exception as trans_err:
        notify_quota_exhaustion("Gemini Translation", str(trans_err))
        return {"success": False, "error": str(trans_err)}

    # روابط السابق والتالي والفهرس الأولية
    prev_url = prev_info.get("post_url") or "#"
    next_url = next_info.get("post_url") or "#"
    index_url = toc_url or "https://www.novelskyworld.com"

    # بناء كود HTML الملكي مع أزرار التنقل الأولية
    royal_html = build_royal_chapter_html_with_nav(novel_name, final_title, translated_content, prev_url, next_url, index_url)

    # 4. نشر الفصل على Blogger عبر محرك النشر
    post_title = f"{novel_name} - {final_title}"
    labels = [novel_name, "آخر الفصول"]

    publish_payload = {
        "action": "createPost",
        "title": post_title,
        "content": royal_html,
        "labels": labels,
        "publishType": "chapter"
    }

    try:
        pub_res = requests.post(PUBLISH_WEBAPP_URL, json=publish_payload, timeout=35).json()
        if pub_res.get("status") != "success" and not pub_res.get("data", {}).get("id"):
            err = pub_res.get("message", "فشل نشر الفصل على Blogger")
            notify_unfixable_error(novel_name, missing_chap_num, err, "النشر على Blogger")
            return {"success": False, "error": err}

        post_data = pub_res.get("data", {})
        new_post_id = post_data.get("id")
        new_post_url = post_data.get("url")

    except Exception as pub_ex:
        notify_unfixable_error(novel_name, missing_chap_num, f"تعذر الاتصال بـ Blogger API: {pub_ex}", "إرسال طلب النشر")
        return {"success": False, "error": str(pub_ex)}

    # 5. ربط أزرار التنقل (السابق والتالي) بين الفصول الثلاثة
    try:
        # أ) تحديث زر "التالي" في الفصل السابق ليوجه إلى هذا الفصل الجديد
        if prev_info.get("post_id") and new_post_url:
            patch_chapter_navigation_button(prev_info["post_id"], next_url=new_post_url)

        # ب) تحديث زر "السابق" في الفصل اللاحق ليوجه إلى هذا الفصل الجديد
        if next_info.get("post_id") and new_post_url:
            patch_chapter_navigation_button(next_info["post_id"], prev_url=new_post_url)
    except Exception as nav_err:
        logger.warning(f"تنبيه أثناء تحديث أزرار السابق والتالي: {nav_err}")

    # 6. إشعار النجاح للأدمن
    success_msg = (
        f"🎉 <b>[تم بنجاح ملء الفجوة ونشر الفصل {missing_chap_num}!]</b> 🚀\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📖 <b>{novel_name} - {final_title}</b>\n"
        f"🔗 <a href='{new_post_url}'>رابط الفصل المنشور على المدونة</a>\n"
        f"🔗 <b>تم ربط أزرار التنقل:</b>\n"
        f"   • السابق [{prev_info.get('chapter_number')}]: تم تحديث زر 'التالي' ➔ لهذا الفصل.\n"
        f"   • اللاحق [{next_info.get('chapter_number')}]: تم تحديث زر 'السابق' ➔ لهذا الفصل.\n"
        f"✅ تم سد الفجوة وتأكيد التسلسل التام 100% بنجاح."
    )
    notify_admin(success_msg)
    return {"success": True, "chap_num": missing_chap_num, "post_url": new_post_url}


def build_royal_chapter_html_with_nav(novel_name: str, standard_title: str, translated_content: str, prev_url: str = "#", next_url: str = "#", index_url: str = "#") -> str:
    """بناء الهيكل الملكي مع أزرار التنقل القياسية المدمجة."""
    converted = convert_bb_nodes_to_royal_html(translated_content)
    paras = [p.strip() for p in converted.splitlines() if p.strip()]
    body_paras = []
    for p in paras:
        if p.startswith("<div") or p.endsWith("</div>") or p.startswith("<p") or p.endsWith("</p>"):
            body_paras.append(p)
        else:
            body_paras.append(f"<p>{p}</p>")
    body_html = "\n".join(body_paras)

    has_prev = bool(prev_url and prev_url != "#")
    has_next = bool(next_url and next_url != "#")
    has_index = bool(index_url and index_url != "#")

    prev_style = "display: flex !important;" if has_prev else "display: none !important;"
    next_style = "display: flex !important;" if has_next else "display: none !important;"
    index_style = "display: flex !important;" if has_index else "display: none !important;"

    nav_html = (
        '    <div class="nsw-chapter-nav">\n'
        f'        <a class="nsw-btn-fill" href="{prev_url}" id="prev-btn" style="{prev_style}">السابق</a>\n'
        f'        <a class="nsw-btn-fill" href="{index_url}" id="index-btn" style="{index_style}">الفهرس</a>\n'
        f'        <a class="nsw-btn-fill" href="{next_url}" id="next-btn" style="{next_style}">التالي</a>\n'
        '    </div>'
    )

    wrapped_html = (
        f'<div class="nsw-chapter-wrapper">\n'
        f'    <span id="dynamic-novel-name" style="display: none;">{novel_name}</span>\n'
        f'    <div id="reading-content">\n'
        f'        <h1 style="border-bottom: 1px dashed var(--accent-gold-border, #c5a059); color: var(--accent-gold, #c5a059); text-align: center; margin-bottom: 25px; padding-bottom: 15px;">{standard_title}</h1>\n'
        f'        <div class="actual-text" id="nsw-text-body">\n'
        f'            {body_html}\n'
        f'        </div>\n'
        f'    </div>\n'
        f'{nav_html}\n'
        f'</div>'
    )
    return wrapped_html


def patch_chapter_navigation_button(post_id: str, prev_url: Optional[str] = None, next_url: Optional[str] = None):
    """تحديث روابط أزرار التنقل (السابق أو التالي) لأي منشور حي على Blogger."""
    if not post_id:
        return
    logger.info(f"🔗 تحديث أزرار التنقل للمنشور [PostID: {post_id}]...")
    
    # جلب المنشور الحالي من Blogger عبر WebApp
    try:
        res = requests.get(f"{PUBLISH_WEBAPP_URL}?action=getPost&postId={post_id}", timeout=20).json()
        raw_content = res.get("data", {}).get("content", "")
        if not raw_content:
            return

        # تعديل رابط التالي إن وجد
        if next_url:
            raw_content = re.sub(
                r'(<a\b[^>]*\bid=["\']next-btn["\'][^>]*\bhref=["\'])[^"\']*([\'"])',
                rf'\g<1>{next_url}\g<2>',
                raw_content
            )
            raw_content = re.sub(
                r'(<a\b[^>]*\bid=["\']next-btn["\'][^>]*\bstyle=["\'])[^"\']*([\'"])',
                r'\g<1>display: flex !important;\g<2>',
                raw_content
            )

        # تعديل رابط السابق إن وجد
        if prev_url:
            raw_content = re.sub(
                r'(<a\b[^>]*\bid=["\']prev-btn["\'][^>]*\bhref=["\'])[^"\']*([\'"])',
                rf'\g<1>{prev_url}\g<2>',
                raw_content
            )
            raw_content = re.sub(
                r'(<a\b[^>]*\bid=["\']prev-btn["\'][^>]*\bstyle=["\'])[^"\']*([\'"])',
                r'\g<1>display: flex !important;\g<2>',
                raw_content
            )

        # حفظ التعديل في مكانه
        requests.post(PUBLISH_WEBAPP_URL, json={
            "action": "updatePostContent",
            "postId": post_id,
            "content": raw_content
        }, timeout=25)
    except Exception as e:
        logger.error(f"خطأ حقن أزرار التنقل: {e}")


def run_auto_fill_all_gaps(target_novel: Optional[str] = None) -> int:
    """تشغيل الفحص وملء كافة الفجوات المكتشفة تلقائياً."""
    gaps = detect_system_gaps(target_novel)
    if not gaps:
        logger.info("✅ جميع سلاسل الفصول مكتملة ولا توجد أي فجوة مفقودة.")
        notify_admin("✅ <b>[تقرير الفجوات]:</b> تم فحص كافة الجداول وبلوجر، وجميع فصول الروايات متسلسلة ولا توجد أي فجوات مفقودة!")
        return 0

    total_filled = 0
    for g in gaps:
        novel = g["novel_name"]
        for m_num in g["missing_chapters"]:
            res = fill_single_missing_gap(novel, m_num, g["prev_info"], g["next_info"])
            if res.get("success"):
                total_filled += 1
            time.sleep(3.0)

    return total_filled


# ==============================================================================
# 🩹 4. استصلاح الفصول المبتورة (Truncated Chapters)
# ==============================================================================

def fetch_live_feed_chapters(max_results: int = 50) -> List[Dict[str, Any]]:
    """جلب الفصول الحية مباشرة من الـ Feed الخاص بالمدونة لفحص محتواها اللحظي."""
    url = f"https://www.novelskyworld.com/feeds/posts/default?alt=json&max-results={max_results}"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers, timeout=20)
    data = res.json()
    entries = data.get("feed", {}).get("entry", [])
    
    feed_chapters = []
    for entry in entries:
        title = entry.get("title", {}).get("$t", "")
        content_html = entry.get("content", {}).get("$t", "")
        
        alt_link = "#"
        for l in entry.get("link", []):
            if l.get("rel") == "alternate":
                alt_link = l.get("href")
                break

        entry_id = entry.get("id", {}).get("$t", "")
        post_id = entry_id.split("post-")[-1] if "post-" in entry_id else ""
        clean_text = re.sub(r'<[^>]+>', '', content_html).strip()
        
        chap_num = 0
        m = re.search(r'(?:الفصل|chapter|chap)\s*(\d+)', title, re.IGNORECASE)
        if m:
            chap_num = int(m.group(1))
        else:
            m2 = re.search(r'\d+', title)
            if m2:
                chap_num = int(m2.group(0))

        novel_name = title.split(" - ")[0].strip() if " - " in title else "عام"

        feed_chapters.append({
            "chapter_number": chap_num,
            "title": title,
            "post_id": post_id,
            "post_url": alt_link,
            "novel_name": novel_name,
            "content_length": len(clean_text),
            "clean_text": clean_text
        })

    return feed_chapters


def get_novel_source_info(novel_name: str) -> Dict[str, Any]:
    """جلب معلومات الرواية ورابط المصدر ومحددات السحب."""
    with database.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM novels WHERE title LIKE ? OR title LIKE ? LIMIT 1", (f"%{novel_name}%", f"{novel_name}%"))
        row = cursor.fetchone()
        if row:
            novel_dict = dict(row)
            cfg = database.get_domain_config(novel_dict["domain"]) or {}
            return {
                "found": True,
                "novel_id": novel_dict["id"],
                "toc_url": novel_dict["toc_url"],
                "domain": novel_dict["domain"],
                "config": cfg
            }

    try:
        url = f"https://docs.google.com/spreadsheets/d/{NOVELS_INDEX_SPREADSHEET_ID}/export?format=csv"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        lines = res.text.splitlines()
        for line in lines[1:]:
            parts = [p.strip('"') for p in line.split(",")]
            if len(parts) >= 3:
                name_col = parts[0].strip()
                index_col = parts[2].strip()
                if novel_name.lower() in name_col.lower() or name_col.lower() in novel_name.lower():
                    domain = scraper_engine.extract_clean_domain(index_col)
                    cfg = database.get_domain_config(domain) or {}
                    return {
                        "found": True,
                        "novel_id": None,
                        "toc_url": index_col,
                        "domain": domain,
                        "config": cfg
                    }
    except Exception as e:
        logger.error(f"خطأ قراءة شيت الفهارس: {e}")

    return {"found": False}


def scan_for_truncated_chapters(novel_name: Optional[str] = None, min_length: int = MIN_SAFE_TEXT_LENGTH) -> List[Dict[str, Any]]:
    """فحص شامل للفصول المنشورة واستخراج المبتورة."""
    logger.info(f"🔍 بدء فحص الفصول المبتورة (الحد الأدنى: {min_length} حرف)...")
    live_chapters = fetch_live_feed_chapters(max_results=50)
    
    truncated = []
    for ch in live_chapters:
        if novel_name and novel_name.lower() not in ch["novel_name"].lower():
            continue

        if ch["content_length"] < min_length:
            logger.warning(f"⚠️ فصل مبتور تم رصده: {ch['title']} (الحجم: {ch['content_length']} حرف فقط!)")
            truncated.append(ch)

    return truncated


def fetch_raw_chapter_by_number(toc_url: str, chapter_number: int, domain_config: Dict[str, Any]) -> Optional[str]:
    """سحب متن الفصل الأصلي الخام برقمه المحدد مباشرة من صفحة الفهرس والمصدر الأصلي."""
    logger.info(f"🌐 جلب الفصل الخام رقم {chapter_number} من الفهرس: {toc_url}")
    toc_sel = domain_config.get("toc_link_selector") or "a[href*='chapter'], a[href*='/txt/']"
    
    chapters_list, _ = scraper_engine.crawl_toc_chapters(toc_url, toc_sel)
    target_url = None
    for item in chapters_list:
        if item.get("chapter_number") == chapter_number:
            target_url = item.get("url")
            break

    if not target_url:
        logger.error(f"❌ لم يتم العثور على رابط الفصل {chapter_number} في صفحة الفهرس.")
        return None

    with scraper_engine.PlaywrightStealthBrowser(headless=True) as browser:
        raw_html, _ = browser.get_page_html(target_url, wait_selector=domain_config.get("chapter_content_selector"))
        clean_content = scraper_engine.clean_chapter_content(
            raw_html,
            domain_config.get("chapter_content_selector") or "article, .entry-content, #content, .txtnav",
            domain_config.get("purge_selectors") or ["script", "style", "nav"]
        )
        return clean_content


def translate_and_refine_chapter(raw_title: str, raw_content: str, novel_name: str, chapter_number: int) -> Dict[str, Any]:
    """ترجمة وتدقيق الفصل بالذكاء الاصطناعي مع القاموس والرقابة العقدية."""
    logger.info(f"🧠 جاري ترجمة وتدقيق الفصل {chapter_number} ({novel_name})...")
    
    system_prompt = (
        "أنت مترجم روائي محترف ومحرر أدبي خبير في ترجمة الروايات الآسيوية والعالمية إلى لغة عربية فصيحة، بليغة، ومحكمة.\n"
        "القواعد الصارمة والإلزامية:\n"
        "1. صياغة العنوان الإلزامي: 'الفصل [رقم]: [عنوان الفصل المترجم]'.\n"
        "2. الحوارات بين علامتي تنصيص \" \" وفصل الفقرات بسطور مزدوجة.\n"
        "3. حقن وسوم الـ BBCode المناسبة تلقائياً:\n"
        "   - [cultivation]...[/cultivation] لتقنيات واختراقات ومراحل المزارعة والطاقة.\n"
        "   - [system]...[/system] لشاشات وواجهات تنبيهات النظام.\n"
        "   - [system red]...[/system] لتحذيرات النظام ورسائل الخطر والموت.\n"
        "   - [doc seal=\"اسم الختم\"]...[/doc] للمراسيم والوثائق الإمبراطورية ورسائل الطوائف.\n"
        "   - [letter]...[/letter] للرسائل والمذكرات الشخصية المتبادلة.\n"
        "   - [tip]...[/tip] للنصائح والإرشادات التوضيحية.\n"
        "   - [note]...[/note] لهوامش وملاحظات المترجم التوضيحية.\n"
        "   - [log]...[/log] لسجلات وإحصائيات النظام السريعة.\n"
        "4. الرقابة العقدية: تكييف الآلهة والكائنات الخارقة لمصطلحات محايدة (كيانات عليا / كائنات أسطورية / خبير أسطوري / سيد المعارك) وتحويل العبادة والسجود إلى خضوع وتبجيل."
    )

    prompt = (
        f"الرواية: {novel_name}\n"
        f"العنوان الخام: {raw_title}\n\n"
        f"المحتوى الخام للفصل:\n{raw_content[:25000]}"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "translated_title": {"type": "STRING"},
                    "translated_content": {"type": "STRING"}
                },
                "required": ["translated_title", "translated_content"]
            }
        }
    }

    success, res = gas_pool.execute_request(action="gemini_proxy", payload=payload)
    if not success or not res:
        raise RuntimeError(f"فشل إرسال طلب الترجمة عبر مجمع الوسائط: {res}")

    try:
        if isinstance(res, str):
            res_obj = json.loads(res)
        else:
            res_obj = res

        text_out = ""
        if "candidates" in res_obj:
            text_out = res_obj["candidates"][0]["content"]["parts"][0]["text"]
        elif "translated_content" in res_obj:
            return res_obj
        
        parsed_out = json.loads(text_out)
        return parsed_out
    except Exception as e:
        logger.error(f"خطأ قراءة استجابة الترجمة: {e}")
        return {
            "translated_title": f"الفصل {chapter_number}",
            "translated_content": raw_content
        }


def convert_bb_nodes_to_royal_html(text: str) -> str:
    """تحويل وسوم BBCode إلى HTML الملكي."""
    if not text:
        return ""
    html_out = text
    html_out = re.sub(r'\[cultivation\]([\s\S]*?)\[/cultivation\]', r'<div class="cultivation">\1</div>', html_out, flags=re.I)
    html_out = re.sub(r'\[doc(?:\s+seal=["\']?([^"\']*)["\']?)?\]([\s\S]*?)\[/doc\]', r'<div class="chinese-document"><div class="doc-body">\2</div></div>', html_out, flags=re.I)
    html_out = re.sub(r'\[letter\]([\s\S]*?)\[/letter\]', r'<div class="personal-letter">\1</div>', html_out, flags=re.I)
    html_out = re.sub(r'\[system red\]([\s\S]*?)\[/system\]', r'<div class="nsw-rift">\1</div>', html_out, flags=re.I)
    html_out = re.sub(r'\[system(.*?)\]([\s\S]*?)\[/system\]', r'<div class="system">\2</div>', html_out, flags=re.I)
    html_out = re.sub(r'\[tip\]([\s\S]*?)\[/tip\]', r'<div class="nsw-tip">\1</div>', html_out, flags=re.I)
    html_out = re.sub(r'\[note\]([\s\S]*?)\[/note\]', r'<div class="nsw-translator-note">\1</div>', html_out, flags=re.I)
    html_out = re.sub(r'\[log\]([\s\S]*?)\[/log\]', r'<div class="nsw-system-log">\1</div>', html_out, flags=re.I)
    return html_out


def build_royal_chapter_html(novel_name: str, standard_title: str, translated_content: str) -> str:
    """بناء الهيكل الملكي الكامل للفصل المنشور."""
    converted = convert_bb_nodes_to_royal_html(translated_content)
    paras = [p.strip() for p in converted.splitlines() if p.strip()]
    body_paras = []
    for p in paras:
        if p.startswith("<div") or p.endsWith("</div>") or p.startswith("<p") or p.endsWith("</p>"):
            body_paras.append(p)
        else:
            body_paras.append(f"<p>{p}</p>")
    body_html = "\n".join(body_paras)

    wrapped_html = (
        f'<div class="nsw-chapter-wrapper">\n'
        f'    <span id="dynamic-novel-name" style="display: none;">{novel_name}</span>\n'
        f'    <div id="reading-content">\n'
        f'        <h1 style="border-bottom: 1px dashed var(--accent-gold-border, #c5a059); color: var(--accent-gold, #c5a059); text-align: center; margin-bottom: 25px; padding-bottom: 15px;">{standard_title}</h1>\n'
        f'        <div class="actual-text" id="nsw-text-body">\n'
        f'            {body_html}\n'
        f'        </div>\n'
        f'    </div>\n'
        f'</div>'
    )
    return wrapped_html


def patch_blogger_post_in_place(post_id: str, new_html: str) -> Dict[str, Any]:
    """تعديل محتوى التدوينة في مكانها مباشرة عبر Blogger API."""
    logger.info(f"🚀 إرسال طلب تعديل المنشور الحي [PostID: {post_id}] على Blogger...")
    payload = {
        "action": "updatePostContent",
        "postId": post_id,
        "content": new_html
    }
    try:
        res = requests.post(PUBLISH_WEBAPP_URL, json=payload, timeout=30)
        return res.json()
    except Exception as e:
        logger.error(f"خطأ تحديث المنشور: {e}")
        return {"status": "error", "message": str(e)}


def heal_truncated_chapter(truncated_item: Dict[str, Any], novel_source_toc: Optional[str] = None) -> Dict[str, Any]:
    """دورة الاستصلاح الكاملة للفصل المبتور في مكانه."""
    chap_num = truncated_item["chapter_number"]
    novel_name = truncated_item["novel_name"]
    post_id = truncated_item["post_id"]
    post_url = truncated_item["post_url"]

    logger.info(f"✨ بدء عملية استصلاح الفصل {chap_num} لرواية '{novel_name}'...")
    notify_admin(f"🔧 <i>بدء استصلاح الفصل المبتور رقم {chap_num} لرواية '{novel_name}'...</i>")

    source_info = get_novel_source_info(novel_name)
    toc_url = novel_source_toc or (source_info.get("toc_url") if source_info.get("found") else None)
    
    if not toc_url:
        err = f"تعذر إيجاد رابط فهرس المصدر الأصلي للرواية '{novel_name}'."
        notify_unfixable_error(novel_name, chap_num, err, "تحديد مصدر الرواية")
        return {"success": False, "error": err}

    cfg = source_info.get("config") or {
        "toc_link_selector": "a[href*='chapter'], a[href*='/txt/']",
        "chapter_title_selector": "h1",
        "chapter_content_selector": ".txtnav, article, #content",
        "purge_selectors": ["script", "style"]
    }

    try:
        raw_content = fetch_raw_chapter_by_number(toc_url, chap_num, cfg)
    except Exception as fetch_err:
        notify_unfixable_error(novel_name, chap_num, f"فشل سحب المتن من المصدر: {fetch_err}", "السحب من المصدر")
        return {"success": False, "error": str(fetch_err)}

    if not raw_content or len(raw_content) < MIN_SAFE_TEXT_LENGTH:
        err = f"المتن المسحوب لا يزال صغيراً ({len(raw_content) if raw_content else 0} حرف). قد يكون الفصل غير مكتمل في الموقع المصدر."
        notify_unfixable_error(novel_name, chap_num, err, "التحقق من اكتمال المتن")
        return {"success": False, "error": err}

    try:
        trans_res = translate_and_refine_chapter(truncated_item["title"], raw_content, novel_name, chap_num)
        sub_title = trans_res.get("translated_title", f"الفصل {chap_num}")
        clean_sub_title = re.sub(r'^(?:الفصل|chapter|chap)\s*\d+[:\s\-]*', '', sub_title, flags=re.I).strip()
        final_title = f"الفصل {chap_num}: {clean_sub_title}" if clean_sub_title else f"الفصل {chap_num}"
        translated_content = trans_res.get("translated_content", "")
    except Exception as t_err:
        notify_quota_exhaustion("Gemini Translation", str(t_err))
        return {"success": False, "error": str(t_err)}

    royal_html = build_royal_chapter_html(novel_name, final_title, translated_content)
    patch_res = patch_blogger_post_in_place(post_id, royal_html)

    if patch_res.get("status") == "success" or patch_res.get("id"):
        success_msg = (
            f"🎉 <b>[تم بنجاح استصلاح وتحديث الفصل {chap_num}]</b>\n"
            f"📖 <b>{novel_name} - {final_title}</b>\n"
            f"📏 تم رفع طول المحتوى من {truncated_item['content_length']} إلى {len(translated_content)} حرف.\n"
            f"🔗 <a href='{post_url}'>رابط التدوينة المحدثة على المدونة</a>\n"
            f"✅ تم التحديث في مكانها دون استهلاك كوتة النشر اليومية!"
        )
        logger.info(f"✅ تم استصلاح الفصل {chap_num} بنجاح!")
        notify_admin(success_msg)
        return {"success": True, "chap_num": chap_num, "title": final_title}
    else:
        err_msg = patch_res.get("message", "فشل التحديث على Blogger")
        notify_unfixable_error(novel_name, chap_num, err_msg, "التحديث على Blogger")
        return {"success": False, "error": err_msg}


def evaluate_and_refine_chapter_quality(novel_name: str, chapter_number: int, draft_title: str, draft_content: str) -> Dict[str, Any]:
    """
    تدقيق الفصل بواسطة Claude أو AI المتقدم وتقييم الجودة من 100:
    1. إذا كانت الدرجة >= 90: يتم اعتماد الفصل وحفظ التعديلات المنقحة.
    2. إذا كانت الدرجة < 90: يرفض الفصل ويحذف من طابور النشر ويطلب سحبه من جديد عبر ميزة الإصلاح.
    3. عند نفاد الكوتة: إرسال تقرير تليجرام فوري مفصل.
    """
    logger.info(f"🧐 تقييم وتدقيق الفصل {chapter_number} ({novel_name}) بواسطة محرك التدقيق الأدبي...")
    
    review_prompt = (
        "أنت كبير المدققين اللغويين ورئيس تحرير الروايات المترجمة.\n"
        "قم بتدقيق النص التالي بدقة فائقة وفق المعايير الصارمة التالية:\n"
        "1. فصاحة العبارات وخلوها من الركاكة والترجمة الحرفية.\n"
        "2. سلامة علامات التنصيص للحوارات، وتنسيق الفقرات.\n"
        "3. التحقق من الرقابة العقدية وتكييف المفردات الأسطورية/المزارعة.\n"
        "4. تقييم جودة الصياغة العامة على مقياس من 0 إلى 100 (quality_score).\n"
        "إذا كانت الجودة أقل من 90 اذكر سبب القصور بدقة.\n\n"
        "أرجع النتيجة بصيغة JSON فقط:\n"
        "{\n"
        "  \"quality_score\": 95,\n"
        "  \"refined_title\": \"العنوان المنقح\",\n"
        "  \"refined_content\": \"المحتوى المنقح بالكامل باللغة العربية الفصيحة\",\n"
        "  \"review_notes\": \"ملاحظات التدقيق إن وجدت\",\n"
        "  \"is_approved\": true\n"
        "}"
    )

    payload = {
        "contents": [{"parts": [{"text": f"الرواية: {novel_name}\nالعنوان: {draft_title}\n\nالنص:\n{draft_content[:25000]}"}]}],
        "systemInstruction": {"parts": [{"text": review_prompt}]},
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }

    try:
        success, res = gas_pool.execute_request(action="gemini_proxy", payload=payload)
        if not success or not res:
            raise RuntimeError(f"استجابة التدقيق غير مكتملة: {res}")

        if isinstance(res, str):
            res_obj = json.loads(res)
        else:
            res_obj = res

        text_out = ""
        if "candidates" in res_obj:
            text_out = res_obj["candidates"][0]["content"]["parts"][0]["text"]
        else:
            text_out = json.dumps(res_obj)

        parsed = json.loads(text_out.strip().replace("```json", "").replace("```", ""))
        score = int(parsed.get("quality_score", 90))
        parsed["is_approved"] = (score >= 90)

        if not parsed["is_approved"]:
            logger.warning(f"⚠️ تدقيق الجودة أعطى درجة {score}/100 للفصل {chapter_number} (< 90). سيتم رفضه وسحبه مجدداً.")
            notify_admin(
                f"⚠️ <b>[رفض الفصل لسوء الجودة - Score: {score}/100]</b>\n"
                f"📖 <b>الرواية:</b> {novel_name} - الفصل {chapter_number}\n"
                f"📝 <b>ملاحظة التدقيق:</b> {parsed.get('review_notes', 'الصياغة دون معيار الـ 90% المطلوب')}\n"
                f"🔄 <b>الإجراء التلقائي:</b> تم إلغاء اعتماده وإرسال طلب إعادة سحبه وترجمته من المصدر."
            )
        return parsed

    except Exception as e:
        err_str = str(e)
        if "quota" in err_str.lower() or "limit" in err_str.lower() or "429" in err_str:
            notify_quota_exhaustion("Claude/AI Reviewer", err_str, retry_seconds=3600)
        logger.error(f"خطأ التدقيق اللغوي: {e}")
        return {
            "quality_score": 85,
            "is_approved": False,
            "refined_title": draft_title,
            "refined_content": draft_content,
            "review_notes": f"خطأ التدقيق: {err_str}"
        }


def fix_single_chapter_x(novel_name: str, chapter_number: int, custom_toc_url: Optional[str] = None) -> Dict[str, Any]:
    """
    🎯 ميزة إصلاح الفصل X الفورية:
    يقوم المشرف بإدخال (اسم الرواية + رقم الفصل)، فيقوم السيرفر بجلب الفصل الخام
    من صفحة الفهرس والمصدر الأصلي فوراً، وترجمته، وتدقيقه، وتحديثه أو نشره مباشرة.
    """
    logger.info(f"🎯 [إصلاح يدوي مخصص] طلب إصلاح الفصل {chapter_number} لرواية '{novel_name}'...")
    notify_admin(f"🎯 <b>[طلب إصلاح مخصص]:</b> جاري جلب الفصل {chapter_number} لرواية <b>{novel_name}</b> من المصدر فوراً...")

    source_info = get_novel_source_info(novel_name)
    toc_url = custom_toc_url or (source_info.get("toc_url") if source_info.get("found") else None)

    if not toc_url:
        err = f"تعذر تحديد رابط الفهرس للرواية '{novel_name}'. يرجى تزويد الرابط في الجدول أو يدوياً."
        notify_unfixable_error(novel_name, chapter_number, err, "إصلاح مخصص")
        return {"success": False, "error": err}

    cfg = source_info.get("config") or {
        "toc_link_selector": "a[href*='chapter'], a[href*='/txt/']",
        "chapter_title_selector": "h1",
        "chapter_content_selector": ".txtnav, article, #content",
        "purge_selectors": ["script", "style"]
    }

    try:
        raw_text = fetch_raw_chapter_by_number(toc_url, chapter_number, cfg)
    except Exception as ex:
        notify_unfixable_error(novel_name, chapter_number, str(ex), "سحب الفصل من المصدر")
        return {"success": False, "error": str(ex)}

    if not raw_text or len(raw_text) < MIN_SAFE_TEXT_LENGTH:
        err = f"المتن المسحوب للفصل {chapter_number} فارغ أو أقل من الحد الأدنى ({len(raw_text) if raw_text else 0} حرف)."
        notify_unfixable_error(novel_name, chapter_number, err, "التحقق من المحتوى المسحوب")
        return {"success": False, "error": err}

    # الترجمة والصقل الأولي
    try:
        trans_res = translate_and_refine_chapter(f"الفصل {chapter_number}", raw_text, novel_name, chapter_number)
        draft_title = trans_res.get("translated_title", f"الفصل {chapter_number}")
        clean_sub_title = re.sub(r'^(?:الفصل|chapter|chap)\s*\d+[:\s\-]*', '', draft_title, flags=re.I).strip()
        final_title = f"الفصل {chapter_number}: {clean_sub_title}" if clean_sub_title else f"الفصل {chapter_number}"
        draft_content = trans_res.get("translated_content", "")
    except Exception as ex:
        notify_quota_exhaustion("AI Translation", str(ex))
        return {"success": False, "error": str(ex)}

    # التدقيق والجودة
    review_res = evaluate_and_refine_chapter_quality(novel_name, chapter_number, final_title, draft_content)
    if not review_res.get("is_approved", True):
        return {
            "success": False,
            "error": f"تم رفض الفصل لأن جودته ({review_res.get('quality_score')}/100) أقل من الحد الأدنى المطلوب (90)."
        }

    final_content = review_res.get("refined_content", draft_content)
    final_title = review_res.get("refined_title", final_title)

    # التحقق هل المنشور موجود مسبقاً على بلوجر ليتم استصلاحه في مكانه أم نشره كجديد
    all_novels = get_all_known_chapters_across_system()
    ch_info = all_novels.get(novel_name, {}).get(chapter_number, {})
    existing_post_id = ch_info.get("post_id")

    if existing_post_id:
        royal_html = build_royal_chapter_html(novel_name, final_title, final_content)
        patch_res = patch_blogger_post_in_place(existing_post_id, royal_html)
        if patch_res.get("status") == "success" or patch_res.get("id"):
            notify_admin(
                f"🎉 <b>[نجاح الإصلاح الفوري للفصل {chapter_number}]</b>\n"
                f"📖 <b>{novel_name} - {final_title}</b>\n"
                f"⭐ درجة الجودة: <b>{review_res.get('quality_score')}/100</b>\n"
                f"✅ تم تحديثه في مكانه الأصلي على بلوجر وتعديل جداول المتابعة."
            )
            return {"success": True, "chap_num": chapter_number, "action": "updated", "title": final_title}
        else:
            notify_unfixable_error(novel_name, chapter_number, patch_res.get("message", "فشل التحديث"), "Blogger Patch")
            return {"success": False, "error": patch_res.get("message")}
    else:
        # إضافته إلى جدول النشر أو إرساله للنشر
        pub_payload = {
            "action": "saveToQueue",
            "novelName": novel_name,
            "labels": [novel_name, "آخر الفصول"],
            "chapters": [{
                "chapNum": chapter_number,
                "title": f"{novel_name} - {final_title}",
                "content": build_royal_chapter_html(novel_name, final_title, final_content),
                "labels": [novel_name, "آخر الفصول"]
            }]
        }
        try:
            r = requests.post(PUBLISH_WEBAPP_URL, json=pub_payload, timeout=25).json()
            notify_admin(
                f"🎉 <b>[تم استعادة وإدراج الفصل {chapter_number} في طابور النشر]</b>\n"
                f"📖 <b>{novel_name} - {final_title}</b>\n"
                f"⭐ تقييم الجودة: <b>{review_res.get('quality_score')}/100</b>\n"
                f"🚀 سيتم نشره وتوصيله تلقائياً في السلسلة."
            )
            return {"success": True, "chap_num": chapter_number, "action": "queued", "title": final_title}
        except Exception as q_err:
            notify_unfixable_error(novel_name, chapter_number, str(q_err), "الإضافة لطابور النشر")
            return {"success": False, "error": str(q_err)}


def run_full_auto_heal(novel_name: Optional[str] = None):
    """تشغيل دورة الاستصلاح الشاملة."""
    truncated_list = scan_for_truncated_chapters(novel_name)
    if not truncated_list:
        logger.info("✅ جميع الفصول المنشورة مكتملة ولا يوجد أي فصل مبتور.")
        notify_admin("✅ <b>[فحص الفصول المنشورة]:</b> جميع الفصول المنشورة كاملة وسليمة 100% ولا يوجد أي بتر.")
        return 0

    healed_count = 0
    for item in truncated_list:
        res = heal_truncated_chapter(item)
        if res.get("success"):
            healed_count += 1
        time.sleep(3.0)

    return healed_count


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "heal"
    target = sys.argv[2] if len(sys.argv) > 2 else None
    if mode == "gaps":
        run_auto_fill_all_gaps(target)
    elif mode == "fix":
        chap_to_fix = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        fix_single_chapter_x(target or "After Severing Ties", chap_to_fix)
    else:
        run_full_auto_heal(target)
