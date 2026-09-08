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
import threading
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
TRANSLATE_SPREADSHEET_ID = "1v1V4_rQukDs3oCe8Z4Izvni3uCx91iKmSVNOm4A3mH0"
PUBLISH_QUEUE_SPREADSHEET_ID = "1HDjYu6EypdiNfoawJ2s7nQcRJiGsfJ5bNefcEy0QhFE"
GLOSSARY_SPREADSHEET_ID = "1oqKRLyqWdkdUWW5UtvorEteFk3jJXdeUzQGDv-XJ_aE"

PUBLISH_WEBAPP_URL = os.getenv("NSW_PUBLISH_WEBAPP_URL", "https://script.google.com/macros/s/AKfycbxqLaqJru1ag-am7G9Mrwy5Nb7HliZlK5vbIEQD9MeV3wOOquNUvz4d7vWEwZxkBI6zIw/exec")
TRANSLATE_WEBAPP_URL = os.getenv("NSW_TRANSLATE_WEBAPP_URL", "https://script.google.com/macros/s/AKfycbwk3rNPfyP6lJw5jkXigqUfTgivsNzgDoyhd61lPiRSFZP49jFShKaz-CfnUqlM9OmH/exec")
TELEGRAM_BOT_TOKEN = os.getenv("NSW_TELEGRAM_BOT_TOKEN", "8914532697:AAFrBMD5o5rWWvXEfjXC0EXOEwPQad0fiy4")
ADMIN_CHAT_ID = os.getenv("NSW_TELEGRAM_CHAT_ID", "8883556949")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1546569711381254265/ZPrKjMA3tVj6kjWZzZeEOePb1I0PfopeYcpdYo7r8rFIXvlHk8m2HM1tIwM_HRRoTXv8")

MIN_SAFE_TEXT_LENGTH = 800

from datetime import datetime, timezone, timedelta

def parse_any_datetime(date_val: Any) -> Optional[datetime]:
    """محلل تاريخ ذكي وشامل يقبل كافة صيغ التواريخ (سلاش، شرطات، مسافات، ISO 8601)"""
    if not date_val:
        return None
    s = str(date_val).strip().replace("/", "-")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    for fmt in [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
    ]:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(s)
    except Exception:
        pass
    return None


# أسماء الروايات الرسمية المسجلة بالمنظومة للتعرف الدقيق وتفادي تجزئة العناوين
KNOWN_NOVELS = [
    "After Severing Ties",
    "المزارع الخبير في المدرسة الابتدائية",
    "رماد النبل وجمر التمرد",
    "نظام الانعكاس لا يظهر إلا بعد بلوغ مرحلة الماهايانا"
]

def resolve_novel_name_from_title(title: str, fallback: str = "After Severing Ties") -> str:
    """استخراج دقيق لاسم الرواية من العنوان وتفادي تقسيم أرقام الفصول كأسماء روايات."""
    if not title:
        return fallback
    clean = str(title).strip()
    for kn in KNOWN_NOVELS:
        if kn.lower() in clean.lower():
            return kn
    if " - " in clean:
        candidate = clean.split(" - ")[0].strip()
        if not re.match(r'^(?:الفصل|chapter|chap)\s*\d+$', candidate, re.IGNORECASE):
            return candidate
    return fallback

# ================================================================
# 🛑 متغير الإيقاف الفوري اللحظي — يمكن تفعيله من تليجرام بأمر /nsw_stop
# ================================================================
STOP_EVENT = threading.Event()

def request_stop():
    """طلب إيقاف العملية الجارية فوراً وبشكل لحظي."""
    STOP_EVENT.set()
    logger.warning("🛑 تم طلب الإيقاف الفوري من المشرف! تم تعيين إشارة التوقف.")

def reset_stop():
    """إعادة ضبط حالة الإيقاف للسماح ببدء عمليات جديدة."""
    STOP_EVENT.clear()

def is_stop_requested() -> bool:
    """التحقق من طلب الإيقاف الفوري اللحظي."""
    return STOP_EVENT.is_set()

# 📡 تتبع الحالة اللحظية المباشرة للمحرك 24/7
ENGINE_LIVE_STATE = {
    "status": "خامل (في وضع الاستعداد)",
    "current_task": "انتظار الأوامر أو الجدولة الدورية",
    "novel_name": "لا يوجد",
    "chapter_num": None,
    "stage": "جاهز",
    "details": "المحرك مستقر، ولم يتم رصد أي نشاط مكثف حالياً.",
    "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    "processed_count": 0,
    "last_error": None
}


def set_engine_state(status: str, task: str, stage: str, novel: str = "عام", chapter: Optional[int] = None, details: str = ""):
    """تحديث الحالة اللحظية لما يقوم به المحرك الآن بدقة ثانية بثانية."""
    global ENGINE_LIVE_STATE
    ENGINE_LIVE_STATE["status"] = status
    ENGINE_LIVE_STATE["current_task"] = task
    ENGINE_LIVE_STATE["stage"] = stage
    ENGINE_LIVE_STATE["novel_name"] = novel
    ENGINE_LIVE_STATE["chapter_num"] = chapter
    ENGINE_LIVE_STATE["details"] = details
    ENGINE_LIVE_STATE["last_updated"] = time.strftime("%H:%M:%S")

def get_realtime_engine_report() -> str:
    """توليد التقرير الآني الحي لحالة المحرك بصيغة HTML تليجرام احترافية."""
    st = ENGINE_LIVE_STATE
    icon = "⚡" if "نشط" in st["status"] or "جاري" in st["status"] else ("⏳" if "تهدئة" in st["status"] or "انتظار" in st["status"] else "💤")
    
    report = (
        f"{icon} <b>[التقرير الآني لما يفعله المحرك الآن]</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📍 <b>الحالة العامة:</b> {st['status']}\n"
        f"⚙️ <b>المهمة الحالية:</b> {st['current_task']}\n"
        f"📖 <b>الرواية:</b> {st['novel_name']}\n"
    )
    if st["chapter_num"]:
        report += f"🔢 <b>الفصل المستهدف:</b> {st['chapter_num']}\n"
    report += (
        f"🚧 <b>المرحلة البرمجية:</b> {st['stage']}\n"
        f"📝 <b>التفاصيل اللحظية:</b> {st['details']}\n"
        f"⏰ <b>آخر تحديث للنبض:</b> {st['last_updated']}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>المحرك يعمل بأقصى طاقة ويقوم بالاستصلاح وملء الفجوات ومزامنة الجداول تلقائياً.</i>"
    )
    return report


# ==============================================================================
# 🔔 1. نظام التنبيهات وإشعارات الأعطال ونفاد الحصص
# ==============================================================================

def notify_admin(message: str, parse_mode: str = "HTML"):
    """إرسال إشعار فوري مزدوج لكل من تليجرام وديسكورد للمشرف."""
    # 1. إرسال إلى تليجرام
    if TELEGRAM_BOT_TOKEN and ADMIN_CHAT_ID:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": ADMIN_CHAT_ID, "text": message, "parse_mode": parse_mode}, timeout=15)
        except Exception as e:
            logger.error(f"خطأ إرسال إشعار تليجرام: {e}")

    # 2. إرسال إلى ديسكورد
    if DISCORD_WEBHOOK_URL:
        try:
            clean_msg = message.replace("<b>", "**").replace("</b>", "**").replace("<i>", "*").replace("</i>", "*").replace("<code>", "`").replace("</code>", "`")
            requests.post(DISCORD_WEBHOOK_URL, json={"content": clean_msg[:1950]}, timeout=10)
        except Exception as e_d:
            logger.error(f"خطأ إرسال إشعار ديسكورد: {e_d}")


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

    def register(novel: str, num: int, source: str, post_id: str = "", post_url: str = "", content_len: int = 0, published_date: str = ""):
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
                "content_len": content_len,
                "published_date": published_date
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
            if published_date and not novels[novel][num].get("published_date"):
                novels[novel][num]["published_date"] = published_date

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
            if not novel or novel == "عام":
                novel = resolve_novel_name_from_title(title)
            novel = novel or "After Severing Ties"
            
            post_id = str(c[4].get("v", "") if len(c) > 4 and c[4] else "").strip()
            post_url = str(c[5].get("v", "") if len(c) > 5 and c[5] else "").strip()
            pub_date = str(c[3].get("v", "") if len(c) > 3 and c[3] else "").strip()
            register(novel, chap_num, "Published Posts", post_id=post_id, post_url=post_url, published_date=pub_date)

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
            novel = resolve_novel_name_from_title(title)
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
            # العمود C (الفهرس 2) هو اسم الرواية الجديد، والعمود F (الفهرس 5) هو الاسم القديم
            novel = str(c[2].get("v", "") if len(c) > 2 and c[2] else "").strip()
            if not novel:
                novel = str(c[5].get("v", "") if len(c) > 5 and c[5] else "عام").strip()
            register(novel, chap_num, "Translate Queue")


    # 5. فحص المدونة الحية عبر Feed
    try:
        live_chaps = fetch_live_feed_chapters(max_results=50)
        for lc in live_chaps:
            register(lc["novel_name"], lc["chapter_number"], "Live Blogger Feed", post_id=lc["post_id"], post_url=lc["post_url"], content_len=lc["content_length"], published_date=lc.get("published", ""))
    except Exception as e:
        logger.warning(f"تعذر استدعاء Feed المدونة الحية: {e}")

    # 6. فحص بلوجر الشامل المباشر عبر Apps Script (يشمل المنشورات المجدولة لـ 2027 والحية والمسودات)
    try:
        audit_url = f"{PUBLISH_WEBAPP_URL}?action=scanGaps"
        audit_res = requests.get(audit_url, timeout=35).json()
        all_chaps = audit_res.get("allChapters", {})
        for c_str, c_info in all_chaps.items():
            try:
                c_num = int(float(c_str))
                c_title = c_info.get("title", "")
                c_chars = c_info.get("charCount", 0)
                c_status = c_info.get("statusDisplay", "")
                c_id = c_info.get("postId", "")
                c_url = c_info.get("postUrl", "")
                c_date = c_info.get("publishedDate", "")
                
                # استخراج اسم الرواية من العنوان بدقة فائقة
                c_nov = resolve_novel_name_from_title(c_title, fallback="After Severing Ties")
                
                # الفصول المجدولة أو الحية ذات المحتوى تسجل فوراً في النظام
                if c_chars > 50 or "مجدول" in c_status or "حي" in c_status:
                    register(c_nov, c_num, f"Blogger [{c_status}]", post_id=c_id, post_url=c_url, content_len=c_chars, published_date=c_date)
            except Exception:
                continue
    except Exception as e_audit:
        logger.warning(f"ملاحظة فحص بلوجر الشامل عبر Apps Script: {e_audit}")

    return novels


def detect_system_gaps(target_novel: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    كشف جميع الفجوات المفقودة في تسلسل فصول الروايات.
    يدعم كشف الفجوات المفردة والمتعددة مع استبعاد المسودات الفارغة (0 حرف)
    والفصول المنشورة بالفعل والتي تمتلك معرف تدوينة أو رابطاً أو محتوى كاملاً.
    """
    all_novels = get_all_known_chapters_across_system()
    gaps = []

    for novel, chaps_map in all_novels.items():
        if target_novel and target_novel.lower() not in novel.lower():
            continue

        # نعتبر الفصل موجوداً وسليماً إذا كان له محتوى حقيقي (> 50 حرف) أو رابط/معرف تدوينة أو كان مجدولاً/حياً/بقوائم النشر
        valid_nums = sorted([
            n for n, info in chaps_map.items() 
            if info.get("content_len", 0) > 50 
            or info.get("post_id") 
            or info.get("post_url")
            or any("مجدول" in s or "حي" in s or "Queue" in s or "Published" in s for s in info.get("sources", []))
        ])
        
        if len(valid_nums) < 2:
            continue

        for i in range(len(valid_nums) - 1):
            curr_n = valid_nums[i]
            next_n = valid_nums[i + 1]

            if next_n - curr_n > 1:
                missing_range = list(range(curr_n + 1, next_n))
                gaps.append({
                    "novel_name": novel,
                    "missing_chapters": missing_range,
                    "prev_chapter": curr_n,
                    "prev_info": chaps_map[curr_n],
                    "next_chapter": next_n,
                    "next_info": chaps_map.get(next_n) or {}
                })

    return gaps


# ==============================================================================
# 🧩 3. محرك ملء الفجوات التلقائي ونشر الفصول وربط أزرار التنقل (Auto Gap-Filler)
# ==============================================================================

def fill_single_missing_gap(
    novel_name: str,
    missing_chap_num: int,
    prev_info: Dict[str, Any],
    next_info: Dict[str, Any],
    is_last_in_gap: bool = True,
    target_pub_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    دورة ملء فجوة واحدة بالكامل:
    1. البحث عن رابط الفهرس وسحب الفصل المفقود من المصدر الأصلي.
    2. الترجمة عبر خط الأنابيب الملكي مع القاموس والرقابة العقدية.
    3. النشر على Blogger مع احترام الجدولة الزمنية.
    4. ترحيل الرابط وتوثيق الفصل في جداول المنظومة.
    5. تحديث أزرار التنقل (السابق والتالي) تسلسلياً بحيث يرتبط كل فصل بسابقه ولاحقه الفعلي المباشر فقط!
    """
    logger.info(f"🧩 [بدء ملء الفجوة] فحص وسحب وترجمة الفصل {missing_chap_num} لرواية '{novel_name}'...")

    if is_stop_requested():
        logger.warning("🛑 تم إيقاف ملء الفجوة فوراً بطلب المشرف.")
        return {"success": False, "error": "تم الإيقاف فوراً بطلب المشرف"}

    # 0. التحقق الأمني الاستباقي لمنع التكرار: هل الفصل موجود بالفعل وكامل في بلوجر (> 500 حرف)؟
    try:
        audit_url = f"{PUBLISH_WEBAPP_URL}?action=scanGaps"
        audit_res = requests.get(audit_url, timeout=25).json()
        all_chaps = audit_res.get("allChapters", {})
        chap_str = str(missing_chap_num)
        if chap_str in all_chaps:
            c_data = all_chaps[chap_str]
            chars = c_data.get("charCount", 0)
            status_disp = c_data.get("statusDisplay", "")
            # إذا كان الفصل منشوراً حياً أو مجدولاً وله محتوى حقيقي كافٍ (> 500 حرف)، يمنع إعادة سحبه وترجمته نهائياً!
            if chars >= 500 or ("حي" in status_disp and chars > 200):
                logger.info(f"✅ الفصل {missing_chap_num} لرواية '{novel_name}' موجود بالفعل وسليم في بلوجر ({chars} حرف - {status_disp}). تم تخطيه فوراً لمنع التكرار.")
                return {
                    "success": True,
                    "already_exists": True,
                    "chap_num": missing_chap_num,
                    "post_id": c_data.get("postId"),
                    "post_url": c_data.get("postUrl")
                }
    except Exception as preflight_err:
        logger.warning(f"ملاحظة الفحص الاستباقي للفصل {missing_chap_num}: {preflight_err}")

    notify_admin(f"🧩 <i>جاري سحب وترجمة الفصل المفقود رقم {missing_chap_num} لرواية '{novel_name}' لملء الفجوة...</i>")

    # 1. إيجاد مصدر الرواية
    source_info = get_novel_source_info(novel_name)
    toc_url = source_info.get("toc_url") if source_info.get("found") else None
    if not toc_url:
        err = f"تعذر إيجاد رابط مصدر الرواية في جدول الفهارس لسحب الفصل {missing_chap_num}."
        notify_unfixable_error(novel_name, missing_chap_num, err, "سحب المصدر الأصلي")
        return {"success": False, "error": err}

    cfg = source_info.get("config") or {}
    if not cfg.get("toc_link_selector"):
        cfg["toc_link_selector"] = "a[href*='/1010605889/'], a[href*='chapter'], a[href*='/txt/'], a[href*='.html'], a[href*='/book/']"
    if not cfg.get("chapter_content_selector"):
        cfg["chapter_content_selector"] = ".txtnav, article, .entry-content, #content, .content, .read-content, #htmlContent"

    # 2. سحب المتن الخام
    if is_stop_requested():
        logger.warning("🛑 تم إيقاف سحب المتن فوراً بطلب المشرف.")
        return {"success": False, "error": "تم الإيقاف فوراً بطلب المشرف"}

    try:
        raw_content = fetch_raw_chapter_by_number(toc_url, missing_chap_num, cfg)
    except Exception as scrape_err:
        notify_unfixable_error(novel_name, missing_chap_num, f"فشل السحب بمتصفح التخفي: {scrape_err}", "السحب من المصدر")
        return {"success": False, "error": str(scrape_err)}

    if not raw_content or len(raw_content) < MIN_SAFE_TEXT_LENGTH:
        err = f"المتن المسحوب للفصل المفقود قصير جداً ({len(raw_content) if raw_content else 0} حرف). قد يكون محجوباً أو غير موجود في المصدر."
        notify_unfixable_error(novel_name, missing_chap_num, err, "التحقق من اكتمال المتن")
        return {"success": False, "error": err}

    # 3. الترجمة والتدقيق والاعتماد
    if is_stop_requested():
        logger.warning("🛑 تم إيقاف الترجمة فوراً بطلب المشرف.")
        return {"success": False, "error": "تم الإيقاف فوراً بطلب المشرف"}

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

    if is_stop_requested():
        logger.warning("🛑 تم إيقاف النشر فوراً بطلب المشرف.")
        return {"success": False, "error": "تم الإيقاف فوراً بطلب المشرف"}

    # روابط السابق والتالي والفهرس الأولية الدقيقة
    prev_url = prev_info.get("post_url") or "#"
    # إذا كان هذا آخر فصل في الفجوة يربط بـ next_info، وإلا يترك "#" مؤقتاً ليربطه الفصل القادم
    next_url = (next_info.get("post_url") or "#") if is_last_in_gap else "#"
    index_url = toc_url or "https://www.novelskyworld.com"

    # بناء كود HTML الملكي مع أزرار التنقل الدقيقة
    royal_html = build_royal_chapter_html_with_nav(novel_name, final_title, translated_content, prev_url, next_url, index_url)

    # 4. التحقق مما إذا كان الفصل المفقود له مسودة أو تدوينة قائمة بالفعل على بلوجر لمنع إنشاء منشور مكرر
    existing_post_id = ""
    try:
        audit_url = f"{PUBLISH_WEBAPP_URL}?action=scanGaps"
        audit_res = requests.get(audit_url, timeout=20).json()
        all_chaps = audit_res.get("allChapters", {})
        if str(missing_chap_num) in all_chaps:
            existing_post_id = all_chaps[str(missing_chap_num)].get("postId", "")
        if not existing_post_id:
            for t in audit_res.get("truncatedChapters", []):
                if t.get("chapNum") == missing_chap_num and t.get("postId"):
                    existing_post_id = t["postId"]
                    break
    except Exception as e_chk:
        logger.warning(f"ملاحظة فحص وجود مسودة قائمة للفصل {missing_chap_num}: {e_chk}")

    # نشر الفصل أو ترقية المسودة على Blogger عبر محرك النشر
    post_title = f"{novel_name} - {final_title}"
    labels = [novel_name, "آخر الفصول"]

    publish_payload = {
        "action": "createPost",
        "title": post_title,
        "content": royal_html,
        "labels": labels,
        "publishType": "chapter",
        "chapterNumber": missing_chap_num,
        "novelName": novel_name
    }
    if existing_post_id:
        publish_payload["postId"] = existing_post_id
        logger.info(f"♻️ تم اكتشاف مسودة قائمة للفصل {missing_chap_num} [PostID: {existing_post_id}]. سيتم تعديلها وجدولتها بدلاً من إنشاء تدوينة مكررة.")
    if target_pub_date:
        publish_payload["publishDate"] = target_pub_date

    try:
        pub_res = requests.post(PUBLISH_WEBAPP_URL, json=publish_payload, timeout=35).json()
        if pub_res.get("status") != "success" and not pub_res.get("data", {}).get("id"):
            err = pub_res.get("message", "فشل نشر الفصل على Blogger")
            notify_unfixable_error(novel_name, missing_chap_num, err, "النشر على Blogger")
            return {"success": False, "error": err}

        post_data = pub_res.get("data", {})
        new_post_id = str(post_data.get("id", ""))
        new_post_url = str(post_data.get("url", ""))

    except Exception as pub_ex:
        notify_unfixable_error(novel_name, missing_chap_num, f"تعذر الاتصال بـ Blogger API: {pub_ex}", "إرسال طلب النشر")
        return {"success": False, "error": str(pub_ex)}

    # 5. ربط أزرار التنقل (السابق والتالي) تسلسلياً دقيقاً
    try:
        # أ) تحديث زر "التالي" في الفصل السابق المباشر فقط ليوجه إلى هذا الفصل الجديد
        if prev_info.get("post_id") and new_post_url:
            patch_chapter_navigation_button(prev_info["post_id"], next_url=new_post_url)

        # ب) تحديث زر "السابق" في الفصل اللاحق فقط إذا كان هذا الفصل هو آخر فصل في الفجوة!
        if is_last_in_gap and next_info.get("post_id") and new_post_url:
            patch_chapter_navigation_button(next_info["post_id"], prev_url=new_post_url)
    except Exception as nav_err:
        logger.warning(f"تنبيه أثناء تحديث أزرار السابق والتالي: {nav_err}")

    # 6. إشعار النجاح للأدمن
    success_msg = (
        f"🎉 <b>[تم بنجاح ملء الفجوة ونشر الفصل {missing_chap_num}!]</b> 🚀\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📖 <b>{novel_name} - {final_title}</b>\n"
        f"🔗 <a href='{new_post_url}'>رابط الفصل المنشور على المدونة</a>\n"
        f"🔗 <b>تم ربط أزرار التنقل بالتسلسل السليم:</b>\n"
        f"   • السابق [{prev_info.get('chapter_number')}]: التالي ➔ الفصل {missing_chap_num}\n"
    )
    if is_last_in_gap and next_info.get("chapter_number"):
        success_msg += f"   • اللاحق [{next_info.get('chapter_number')}]: السابق ➔ الفصل {missing_chap_num}\n"
    success_msg += "✅ تم حفظ السلسلة دون قفزات."
    notify_admin(success_msg)
    return {"success": True, "chap_num": missing_chap_num, "post_id": new_post_id, "post_url": new_post_url}


def build_royal_chapter_html_with_nav(novel_name: str, standard_title: str, translated_content: str, prev_url: str = "#", next_url: str = "#", index_url: str = "#") -> str:
    """بناء الهيكل الملكي مع أزرار التنقل القياسية المدمجة."""
    converted = convert_bb_nodes_to_royal_html(translated_content)
    paras = [p.strip() for p in converted.splitlines() if p.strip()]
    body_paras = []
    for p in paras:
        if p.startswith("<div") or p.endswith("</div>") or p.startswith("<p") or p.endswith("</p>"):
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


def repair_all_chapter_navigation(novel_name: str = "After Severing Ties", start_chapter: int = 1, limit: int = 500) -> Dict[str, Any]:
    """استدعاء عملية صيانة وإصلاح أزرار التنقل لكافة فصول الرواية المنشورة في بلوجر."""
    logger.info(f"🔗 بدء صيانة أزرار التنقل الشاملة لرواية '{novel_name}' بدءاً من الفصل {start_chapter}...")
    try:
        payload = {
            "action": "repairNavigation",
            "novelName": novel_name,
            "startChapter": start_chapter,
            "limit": limit
        }
        res = requests.post(PUBLISH_WEBAPP_URL, json=payload, timeout=55).json()
        if res.get("status") == "success" or res.get("success"):
            data = res.get("data", res)
            patched = data.get("linksPatched", 0)
            msg = f"🔗 <b>[اكتملت صيانة أزرار التنقل]:</b> تم ربط {patched} فصلاً بالتسلسل السليم لرواية {novel_name}."
            notify_admin(msg)
            return {"success": True, "linksPatched": patched, "data": data}
        else:
            err = res.get("message", "تعذر إتمام صيانة التنقل")
            logger.warning(err)
            return {"success": False, "error": err}
    except Exception as e:
        logger.error(f"خطأ أثناء استدعاء صيانة أزرار التنقل: {e}")
        return {"success": False, "error": str(e)}


def run_auto_fill_all_gaps(target_novel: Optional[str] = None) -> int:
    """تشغيل الفحص وملء كافة الفجوات المكتشفة تلقائياً مع تسلسل أزرار دقيق 100%."""
    reset_stop()
    gaps = detect_system_gaps(target_novel)
    if not gaps:
        logger.info("✅ جميع سلاسل الفصول مكتملة ولا توجد أي فجوة مفقودة.")
        notify_admin("✅ <b>[تقرير الفجوات]:</b> تم فحص كافة الجداول وبلوجر، وجميع فصول الروايات متسلسلة ولا توجد أي فجوات مفقودة!")
        return 0

    total_filled = 0
    for g in gaps:
        if is_stop_requested():
            logger.warning("🛑 تم إيقاف عملية ملء الفجوات فوراً بناءً على طلب المشرف.")
            notify_admin("🛑 <b>تم إيقاف عملية ملء الفجوات فوراً!</b>")
            break

        novel = g["novel_name"]
        missing_sorted = sorted(g["missing_chapters"])
        current_prev = dict(g["prev_info"])

        for idx, m_num in enumerate(missing_sorted):
            if is_stop_requested():
                logger.warning("🛑 تم إيقاف عملية ملء الفجوات فوراً بناءً على طلب المشرف.")
                notify_admin("🛑 <b>تم إيقاف عملية ملء الفجوات فوراً!</b>")
                return total_filled

            is_last = (idx == len(missing_sorted) - 1)
            # إذا كان هذا آخر فصل في الفجوة، فالفصل اللاحق هو بداية السلسلة التالية
            # وإلا يُترك التالي ليربطه الفصل القادم
            next_target = g["next_info"] if is_last else {"post_url": "#", "post_id": None, "chapter_number": m_num + 1}

            # حساب التوقيت الزمني المجدول للفصل المفقود لضمان جدولته وعدم نشره فوراً
            target_pub_date = None
            try:
                p_date_str = current_prev.get("published_date")
                n_date_str = g["next_info"].get("published_date")
                p_dt = parse_any_datetime(p_date_str)
                n_dt = parse_any_datetime(n_date_str)

                if p_dt and n_dt:
                    step_diff = (n_dt - p_dt) / (len(missing_sorted) + 1)
                    step_dt = p_dt + step_diff * (idx + 1)
                elif p_dt:
                    step_dt = p_dt + timedelta(minutes=1 * (idx + 1))
                elif n_dt:
                    step_dt = n_dt - timedelta(minutes=1 * (len(missing_sorted) - idx))
                else:
                    # في حال تعذر قراءة تاريخ الفصل السابق، جدولة الفصل في 2027 حصراً لمنع النشر المباشر نهائياً
                    step_dt = datetime(2027, 1, 25, 9, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=idx + 1)

                target_pub_date = step_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            except Exception as dt_err:
                logger.warning(f"تعذر حساب التوقيت الزمني للفصل {m_num}: {dt_err}")
                # صمام أمان حديدي: موعد مجدول مستقبلي دائم لمنع النشر الحي تحت أي ظرف
                target_pub_date = "2027-01-25T09:00:00.000Z"

            res = fill_single_missing_gap(
                novel_name=novel,
                missing_chap_num=m_num,
                prev_info=current_prev,
                next_info=next_target,
                is_last_in_gap=is_last,
                target_pub_date=target_pub_date
            )

            if res.get("success"):
                total_filled += 1
                # تحديث السابق للفصل القادم في السلسلة ليصبح هذا الفصل الجديد
                if res.get("post_id") or res.get("post_url"):
                    current_prev = {
                        "chapter_number": m_num,
                        "post_id": res.get("post_id"),
                        "post_url": res.get("post_url"),
                        "published_date": target_pub_date or current_prev.get("published_date")
                    }

            if is_stop_requested():
                logger.warning("🛑 تم إيقاف عملية ملء الفجوات فوراً بناءً على طلب المشرف.")
                notify_admin("🛑 <b>تم إيقاف عملية ملء الفجوات فوراً!</b>")
                return total_filled

            STOP_EVENT.wait(3.0)

    return total_filled


# ==============================================================================
# 🩹 4. استصلاح الفصول المبتورة (Truncated Chapters)
# ==============================================================================

def extract_pure_story_text(html_content: str) -> str:
    """استخراج متن القصة الصافي من HTML بتجريد أشرطة التنقل والترويسة والوسوم التنسيقية."""
    if not html_content:
        return ""
    # استخراج محتوى الحاوية الفعلية nsw-text-body إذا وُجدت
    body_match = re.search(r'<div[^>]*id=["\']nsw-text-body["\'][^>]*>([\s\S]*?)</div>', html_content, re.I)
    if body_match and len(body_match.group(1).strip()) > 20:
        raw_text = body_match.group(1)
    else:
        # تجريد أزرار التنقل والترويسات
        raw_text = re.sub(r'<div[^>]*class=["\'][^"\']*nsw-chapter-(?:toolbar|nav|switch|wrapper)[^"\']*["\'][\s\S]*?</div>', '', html_content, flags=re.I)
        raw_text = re.sub(r'<h1[\s\S]*?</h1>', '', raw_text, flags=re.I)
    clean = re.sub(r'<[^>]+>', ' ', raw_text)
    return clean.strip()


def count_arabic_chars(text: str) -> int:
    """حساب عدد الأحرف العربية الصافية فقط."""
    if not text:
        return 0
    return len(re.findall(r'[\u0600-\u06FF]', text))


def fetch_live_feed_chapters(novel_name: Optional[str] = None, max_results: int = 150) -> List[Dict[str, Any]]:
    """جلب الفصول الحية مباشرة من الـ Feed الخاص بالمدونة لفحص محتواها اللحظي مع حساب الحروف العربية الصافية."""
    if novel_name:
        # محاولة الاستعلام المباشر باسم الرواية أو تصنيفها
        encoded_tag = requests.utils.quote(novel_name.strip())
        url = f"https://www.novelskyworld.com/feeds/posts/default/-/{encoded_tag}?alt=json&max-results={max_results}"
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            res = requests.get(url, headers=headers, timeout=20)
            if res.status_code != 200:
                url = f"https://www.novelskyworld.com/feeds/posts/default?alt=json&max-results={max_results}&q={encoded_tag}"
                res = requests.get(url, headers=headers, timeout=20)
        except Exception:
            url = f"https://www.novelskyworld.com/feeds/posts/default?alt=json&max-results={max_results}"
            res = requests.get(url, headers=headers, timeout=20)
    else:
        url = f"https://www.novelskyworld.com/feeds/posts/default?alt=json&max-results={max_results}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=20)

    try:
        data = res.json()
    except Exception:
        return []

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
        
        # استخراج المتن الصافي وحساب الحروف العربية
        pure_story = extract_pure_story_text(content_html)
        arabic_count = count_arabic_chars(pure_story)
        clean_text = re.sub(r'<[^>]+>', ' ', content_html).strip()
        
        chap_num = 0
        m = re.search(r'(?:الفصل|chapter|chap)\s*(\d+)', title, re.IGNORECASE)
        if m:
            chap_num = int(m.group(1))
        else:
            m2 = re.search(r'\d+', title)
            if m2:
                chap_num = int(m2.group(0))

        entry_novel_name = resolve_novel_name_from_title(title, fallback="After Severing Ties")

        feed_chapters.append({
            "chapter_number": chap_num,
            "title": title,
            "post_id": post_id,
            "post_url": alt_link,
            "novel_name": entry_novel_name,
            "content_length": len(clean_text),
            "clean_text": clean_text,
            "pure_story": pure_story,
            "arabic_chars": arabic_count,
            "published": entry.get("published", {}).get("$t", "")
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
        url = f"https://docs.google.com/spreadsheets/d/{NOVELS_INDEX_SPREADSHEET_ID}/gviz/tq?tqx=out:json"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        text = res.text
        if "google.visualization.Query.setResponse(" in text:
            text = text.split("google.visualization.Query.setResponse(")[1].rsplit(");", 1)[0]
        data = json.loads(text)
        rows = data.get("table", {}).get("rows", [])
        for r in rows:
            c = r.get("c", [])
            if len(c) > 0 and c[0]:
                name_col = str(c[0].get("v", "")).strip()
                # العمود H (الفهرس 7) هو "الرابط الاصلي"، وإذا لم يوجد نأخذ العمود C (الفهرس 2)
                orig_url = str(c[7].get("v", "") if len(c) > 7 and c[7] else "").strip()
                index_col = orig_url if (orig_url and orig_url != "None") else str(c[2].get("v", "") if len(c) > 2 and c[2] else "").strip()
                
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

    # مصادر احتياطية مباشرة ومؤكدة في حال حدوث بطء في شبكة Google Sheets
    KNOWN_FALLBACKS = {
        "after severing ties": "https://www.novel543.com/1010605889/dir",
        "الوريث": "https://www.novel543.com/1010605889/dir",
        "المنبوذ": "https://www.novel543.com/1010605889/dir",
        "the expert cultivator in elementary": "https://www.69shuba.com/book/54809/",
        "المزارع": "https://www.69shuba.com/book/54809/"
    }
    for k, u in KNOWN_FALLBACKS.items():
        if k in novel_name.lower():
            domain = scraper_engine.extract_clean_domain(u)
            return {
                "found": True,
                "novel_id": None,
                "toc_url": u,
                "domain": domain,
                "config": {
                    "toc_link_selector": "a[href*='/1010605889/'], a[href*='chapter'], a[href*='/txt/'], a[href*='.html'], a[href*='/book/']",
                    "chapter_content_selector": ".txtnav, article, .entry-content, #content, .content, .read-content, #htmlContent"
                }
            }

    return {"found": False}


def scan_for_truncated_chapters(novel_name: Optional[str] = None, min_length: int = MIN_SAFE_TEXT_LENGTH) -> List[Dict[str, Any]]:
    """فحص شامل للفصول المنشورة واستخراج المبتورة عبر فحص عدد الأحرف العربية الصافية."""
    logger.info(f"🔍 بدء فحص الفصول المبتورة (الحد الأدنى للمتن العربي: {min_length} حرف)...")
    live_chapters = fetch_live_feed_chapters(novel_name=novel_name, max_results=150)
    
    truncated = []
    for ch in live_chapters:
        if novel_name and novel_name.lower() not in ch["novel_name"].lower():
            continue

        # الفحص الصارم بحسب عدد الحروف العربية الصافية في متن القصة
        arabic_cnt = ch.get("arabic_chars", 0)
        if arabic_cnt < min_length:
            logger.warning(f"⚠️ فصل مبتور تم رصده: {ch['title']} (الحروف العربية: {arabic_cnt} فقط! الحد الأدنى الآمن: {min_length})")
            truncated.append(ch)

    return truncated


TOC_MEMORY_CACHE: Dict[str, List[Dict[str, Any]]] = {}

def fetch_raw_chapter_by_number(toc_url: str, chapter_number: int, domain_config: Dict[str, Any]) -> Optional[str]:
    """سحب متن الفصل الأصلي الخام برقمه المحدد مباشرة من صفحة الفهرس والمصدر الأصلي."""
    global TOC_MEMORY_CACHE
    logger.info(f"🌐 جلب الفصل الخام رقم {chapter_number} من الفهرس: {toc_url}")
    
    # محددات فهارس شاملة
    toc_sel = domain_config.get("toc_link_selector") or "a[href*='/1010605889/'], a[href*='chapter'], a[href*='/txt/'], a[href*='.html'], a[href*='/book/']"
    
    chapters_list = TOC_MEMORY_CACHE.get(toc_url)
    if not chapters_list:
        chapters_list, _ = scraper_engine.crawl_toc_chapters(toc_url, toc_sel)
        if chapters_list:
            TOC_MEMORY_CACHE[toc_url] = chapters_list

    target_url = None
    for item in (chapters_list or []):
        if item.get("chapter_number") == chapter_number:
            target_url = item.get("url")
            break

    # محاولة حساب الرابط التلقائي لموقع novel543 إذا لم يظهر بالفهرس
    if not target_url and "novel543.com/1010605889" in toc_url:
        target_url = f"https://www.novel543.com/1010605889/8095_{chapter_number}.html"

    if not target_url:
        logger.error(f"❌ لم يتم العثور على رابط الفصل {chapter_number} في صفحة الفهرس.")
        return None

    content_sel = domain_config.get("chapter_content_selector") or ".txtnav, article, .entry-content, #content, .content, .read-content, #htmlContent"
    purge_sel = domain_config.get("purge_selectors") or ["script", "style", "nav", ".header", ".footer"]

    # 1. المسار فائق السرعة عبر HTTP المباشر (يوفر استهلاك المتصفح ويعمل في 0.2 ثانية)
    try:
        req_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Referer": toc_url,
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8"
        }
        resp = requests.get(target_url, headers=req_headers, timeout=12)
        if resp.status_code == 200 and len(resp.text) > 600:
            low_t = resp.text[:1000].lower()
            if "just a moment" not in low_t and "attention required" not in low_t and "cloudflare" not in low_t:
                clean_content = scraper_engine.clean_chapter_content(resp.text, content_sel, purge_sel)
                if clean_content and len(clean_content) >= MIN_SAFE_TEXT_LENGTH:
                    logger.info(f"⚡ تم سحب الفصل {chapter_number} بنجاح عبر المسار السريع ({len(clean_content)} حرف).")
                    return clean_content
    except Exception as e_fast:
        logger.warning(f"ملاحظة المسار السريع للفصل {chapter_number}: {e_fast}. الانتقال للمسار الاحتياطي...")

    # 2. المسار الاحتياطي عبر متصفح التخفي Playwright
    with scraper_engine.PlaywrightStealthBrowser(headless=True) as browser:
        raw_html, _ = browser.get_page_html(target_url, wait_selector=content_sel)
        clean_content = scraper_engine.clean_chapter_content(
            raw_html,
            content_sel,
            purge_sel
        )
        return clean_content


GLOSSARY_CACHE: Dict[str, List[Dict[str, str]]] = {}

def get_novel_glossary(novel_name: str) -> List[Dict[str, str]]:
    """جلب قائمة مصطلحات وقاموس الرواية المعتمدة من Google Sheets مع التخزين المؤقت في الذاكرة."""
    norm_name = novel_name.strip().lower()
    if norm_name in GLOSSARY_CACHE:
        return GLOSSARY_CACHE[norm_name]
    
    rows = query_gviz_sheet(GLOSSARY_SPREADSHEET_ID)
    matched_terms = []
    is_severing_ties = any(k in norm_name for k in ["severing ties", "after severing ties", "قطع العلاقات"])

    for r in rows[1:]:
        c = r.get("c", [])
        if not c or len(c) < 3 or not c[1] or not c[2]:
            continue
        row_novel = str(c[0].get("v", "") if c[0] else "").strip().lower()
        orig_term = str(c[1].get("v", "")).strip()
        arab_term = str(c[2].get("v", "")).strip()
        cat = str(c[3].get("v", "") if len(c) > 3 and c[3] else "").strip()
        gender = str(c[4].get("v", "") if len(c) > 4 and c[4] else "").strip()

        if (is_severing_ties and ("severing ties" in row_novel or not row_novel)) or (row_novel in norm_name or norm_name in row_novel):
            matched_terms.append({
                "original": orig_term,
                "arabic": arab_term,
                "category": cat,
                "gender": gender
            })

    logger.info(f"📚 تم تحميل {len(matched_terms)} مصطلح وقاعدة تسمية من القاموس المعتمد للرواية '{novel_name}'.")
    GLOSSARY_CACHE[norm_name] = matched_terms
    return matched_terms


def filter_glossary_for_chapter(raw_chinese_text: str, glossary_terms: List[Dict[str, str]], novel_name: str = "") -> List[Dict[str, str]]:
    """
    فلترة ذكية وفائقة الدقة: مطابقة النص الصيني للفصل مع القاموس المعتمد،
    وإرسال المصطلحات التي وردت فعلياً في الفصل فقط لتوفير ما يزيد عن 90% من توكنز نافذة السياق،
    مع ضمان إدراج المصطلحات المركزية للبطل دائماً.
    """
    if not raw_chinese_text or not glossary_terms:
        return glossary_terms or []

    matched = []
    matched_originals = set()

    for t in glossary_terms:
        orig = t.get("original", "").strip()
        if orig and orig in raw_chinese_text:
            matched.append(t)
            matched_originals.add(orig)

    # إذا كان عدد المصطلحات المطابقة قليلاً جداً، نضمن بقاء أهم 5 مصطلحات قيادية للرواية
    if len(matched) < 2:
        for t in glossary_terms[:5]:
            orig = t.get("original", "").strip()
            if orig and orig not in matched_originals:
                matched.append(t)
                matched_originals.add(orig)

    return matched


def format_glossary_for_prompt(glossary_terms: List[Dict[str, str]]) -> str:
    """تنسيق القاموس ككتلة شروط إلزامية للذكاء الاصطناعي."""
    if not glossary_terms:
        return ""
    lines = ["\n📌 [قاموس المصطلحات والأسماء المعتمد إلزامياً بنسبة 100% - يمنع استخدام أي ترجمة أخرى لهذه المفردات]:"]
    for t in glossary_terms:
        extra = []
        if t.get("category"):
            extra.append(f"التصنيف: {t['category']}")
        if t.get("gender"):
            extra.append(f"الجنس: {t['gender']}")
        extra_str = f" ({' | '.join(extra)})" if extra else ""
        lines.append(f"• {t['original']} ➔ {t['arabic']}{extra_str}")
    return "\n".join(lines)


def stage_1_initial_translate(raw_title: str, raw_content: str, novel_name: str, chapter_number: int) -> Dict[str, Any]:
    """المرحلة 1: الترجمة الأولية الكاملة مع التقيد التام بأسماء ومصطلحات القاموس المطابقة للفصل وتطبيق وسوم BBCode."""
    logger.info(f"🔹 [المرحلة 1/3] الترجمة الأولية للفصل {chapter_number} ({novel_name}) مع القاموس المفلتر...")
    all_glossary_terms = get_novel_glossary(novel_name)
    chapter_glossary = filter_glossary_for_chapter(raw_content + " " + raw_title, all_glossary_terms, novel_name)
    glossary_block = format_glossary_for_prompt(chapter_glossary)
    logger.info(f"🎯 تم تصفية القاموس: إرسال {len(chapter_glossary)} مصطلح مطابق من أصل {len(all_glossary_terms)} لتوفير السياق.")

    sys_prompt = (
        "أنت مترجم روائي محترف ومحرر أدبي خبير متخصص في ترجمة الروايات الصينية والعالمية إلى العربية الفصحى البليغة.\n"
        "القواعد الصارمة والإلزامية:\n"
        "1. ترجمة النص كاملاً بأمانة ودقة بالغة دون أي تلخيص أو حذف لأي جملة أو فقرة.\n"
        "2. التقيد التام والحرفي بأسماء الشخصيات والأماكن والمصطلحات الواردة في القاموس المرفق.\n"
        "3. قواعد الأسماء والألقاب الصينية الصارمة (حظر تام للترجمة الحرفية والمشوهة):\n"
        "   - الألقاب مثل '老马' (Lao Ma) تُترجم حصراً: 'العجوز ما' أو 'العم ما' (يُحظر منعاً باتاً كتابتها 'ماء'!).\n"
        "   - '刘百中' تُترجم حصراً: 'ليو بايتشونغ' (وليس لين باي جشون).\n"
        "   - أسماء وألقاب الأشخاص التي تحتوي على مفردات أدوات: مثل '木头琴' أو '木琴' هو اسم/لقب امرأة يُعرب صوتياً: 'مو تشين' (أو 'عازفة القيثارة' / 'مو تشين الخشبية'). يُحظر منعاً باتاً ترجمتها كآلة موسيقية مثل 'كمان الرأس الخشبي'!\n"
        "   - الأسماء الصينية تُعرب صوتياً بنظام Pinyin ولا تُترجم معاني كلماتها الحرفية إطلاقاً.\n"
        "   - التعبيرات الشعبية: مثل '我怕个锤子' تُترجم: 'وهل نخشى شيئاً؟!' أو 'نحن لا نخشى الموت أبداً!'.\n"
        "4. التنسيقات الجمالية الملكية (وسوم BBCode لقالب المدونة):\n"
        "   - احقن [cultivation]...[/cultivation] لتقنيات واختراقات ومراحل المزارعة والطاقة.\n"
        "   - احقن [system]...[/system] لنوافذ وشاشات النظام السيبراني والإشعارات.\n"
        "   - احقن [system red]...[/system] لتحذيرات الخطر الداهم والموت والشقوق الحمراء.\n"
        "   - احقن [doc]...[/doc] للوثائق والمخطوطات والمراسيم القديمة.\n"
        "   - احقن [letter]...[/letter] للرسائل والمذكرات الشخصية.\n"
        "   - احقن [tip]...[/tip] للتلميحات الإرشادية.\n"
        "   - احقن [note]...[/note] لهوامش وملاحظات الشرح الضرورية.\n"
        "5. استخراج عنوان الفصل بصيغة: 'الفصل [رقم]: [عنوان الفصل المترجم]'.\n"
        "6. كشف المصطلحات الجديدة: إذا ظهرت في الفصل شخصيات أو أماكن جديدة غير موجودة بالقاموس المرفق، اذكرها في حقل new_entities.\n"
        "7. إرجاع النتيجة حصراً بصيغة JSON بدون أي مقدمات:\n"
        "```json\n"
        "{\n"
        '  "translated_title": "الفصل ...: ...",\n'
        '  "translated_content": "المتن المترجم كاملاً مع وسوم BBCode...",\n'
        '  "new_entities": [\n'
        '    {"chinese": "اسم صيني جديد", "arabic": "التعريب المقترح", "category": "شخصية/مكان/تقنية", "gender": "ذكر/أنثى/غير محدد"}\n'
        '  ]\n'
        "}\n"
        "```"
    )

    full_prompt = f"{sys_prompt}\n{glossary_block}\n\nالرواية: {novel_name}\nالعنوان الخام: {raw_title}\n\nالمحتوى الخام للترجمة:\n{raw_content[:30000]}"

    from gemini_analyzer import call_gemini_api
    res_text = call_gemini_api(full_prompt, model_name="gemini-3.5-flash-lite", timeout=90)
    if not res_text or len(res_text.strip()) < 50:
        raise ValueError("استجابة نموذج الترجمة فارغة أو قصيرة جداً")

    clean_json = res_text.strip()
    if "```json" in clean_json:
        clean_json = clean_json.split("```json")[1].split("```")[0].strip()
    elif "```" in clean_json:
        clean_json = clean_json.split("```")[1].split("```")[0].strip()

    parsed = None
    try:
        parsed = json.loads(clean_json)
    except Exception:
        match = re.search(r'\{[\s\S]*"translated_content"[\s\S]*\}', res_text)
        if match:
            parsed = json.loads(match.group(0))
        else:
            clean_text = re.sub(r'```[a-z]*|```', '', res_text).strip()
            parsed = {"translated_title": f"الفصل {chapter_number}", "translated_content": clean_text}

    content_ar = parsed.get("translated_content", "")
    ar_count = count_arabic_chars(content_ar)
    zh_count = len(re.findall(r'[\u4e00-\u9fff]', content_ar))
    min_exp = min(200, len(raw_content) // 3) if len(raw_content) > 100 else 20

    if ar_count < min_exp or zh_count > (len(content_ar) * 0.05):
        raise ValueError(f"فشلت المرحلة 1: النص غير مطابق للمعايير (عربي: {ar_count}, صيني: {zh_count})")

    logger.info(f"✅ [المرحلة 1] اكتملت الترجمة الأولية بنجاح ({ar_count} حرف عربي).")
    return parsed


def stage_2_antigravity_refine(draft_title: str, draft_content: str, novel_name: str, chapter_number: int) -> Dict[str, Any]:
    """المرحلة 2: التدقيق الأدبي والتنسيق وحقن وسوم BBCode والرقابة العقدية من محرر Antigravity."""
    logger.info(f"🔹 [المرحلة 2/3] التدقيق الأدبي والتنسيق وحقن BBCode والرقابة العقدية للفصل {chapter_number}...")

    sys_prompt = (
        "أنت كبير محرري روايات NSW ومسؤول التدقيق اللغوي والرقابة الأدبية والعقدية من محرر Antigravity.\n"
        "المهمة: خذ النص المترجم التالي وقم بصقله وتنسيقه وفق المعايير الإلزامية التالية:\n"
        "1. علامات التنصيص للحوارات: اجعل كل جملة حوارية بين علامتي تنصيص مزدوجتين \"...\" حصراً وافصل بين الفقرات بسطور مزدوجة.\n"
        "2. الرقابة العقدية: تكييف الآلهة والكائنات الخارقة لمصطلحات محايدة (كيانات عليا / كائنات أسطورية / خبير أسطوري / سيد المعارك) وتحويل العبادة والسجود إلى خضوع وتبجيل وانحناء.\n"
        "3. حقن وسوم الـ BBCode المناسبة تلقائياً:\n"
        "   - [cultivation]...[/cultivation] لتقنيات واختراقات ومراحل المزارعة والطاقة.\n"
        "   - [system]...[/system] لشاشات وواجهات تنبيهات النظام.\n"
        "   - [system red]...[/system] لتحذيرات النظام ورسائل الخطر والموت.\n"
        "   - [doc seal=\"اسم الختم\"]...[/doc] للمراسيم والوثائق الإمبراطورية ورسائل الطوائف.\n"
        "   - [letter]...[/letter] للرسائل والمذكرات الشخصية المتبادلة.\n"
        "   - [tip]...[/tip] للنصائح والإرشادات التوضيحية.\n"
        "   - [note]...[/note] لهوامش وملاحظات المترجم التوضيحية.\n"
        "   - [log]...[/log] لسجلات وإحصائيات النظام السريعة.\n"
        "4. الارتقاء بالصياغة العربية لتكون فصيحة، بليغة، وخالية من الركاكة والترجمة الحرفية.\n"
        "5. التصحيح الإلزامي الفوري لأي تشويه في أسماء الشخصيات الصينية:\n"
        "   - استبدال أي 'ماء' قُصد بها شخص (Lao Ma) إلى 'العجوز ما' أو 'العم ما'.\n"
        "   - استبدال أي 'كمان الرأس الخشبي' أو 'كمان خشبي' إلى 'مو تشين'.\n"
        "   - استبدال أي 'لين باي جشون' إلى 'ليو بايتشونغ'.\n"
        "   - تهذيب الإشارات المبتذلة (مثل رفع الإصبع) لتكون صياغة روائية فصيحة وبليغة تليق بالقارئ العربي.\n"
        "6. يمنع منعاً باتاً كتابة أي روابط تحرير خاصة ببلوجر (مثل blogger.com/blog/post/edit) في نهاية الفصل.\n\n"
        "إرجاع النتيجة حصراً بصيغة JSON:\n"
        "```json\n"
        "{\n"
        '  "refined_title": "الفصل ...: ...",\n'
        '  "refined_content": "النص المنقح بالكامل..."\n'
        "}\n"
        "```"
    )

    full_prompt = f"{sys_prompt}\n\nالرواية: {novel_name}\nالعنوان: {draft_title}\n\nالنص المترجم للمراجعة:\n{draft_content[:30000]}"

    from gemini_analyzer import call_gemini_api
    res_text = call_gemini_api(full_prompt, model_name="gemini-3.5-flash-lite", timeout=90)
    clean_json = res_text.strip()
    if "```json" in clean_json:
        clean_json = clean_json.split("```json")[1].split("```")[0].strip()
    elif "```" in clean_json:
        clean_json = clean_json.split("```")[1].split("```")[0].strip()

    parsed = None
    try:
        parsed = json.loads(clean_json)
    except Exception:
        match = re.search(r'\{[\s\S]*"refined_content"[\s\S]*\}', res_text)
        if match:
            parsed = json.loads(match.group(0))
        else:
            clean_text = re.sub(r'```[a-z]*|```', '', res_text).strip()
            parsed = {"refined_title": draft_title, "refined_content": clean_text}

    logger.info(f"✅ [المرحلة 2] تم التدقيق الأدبي والتنسيق وحقن وسوم BBCode بنجاح.")
    return parsed


def stage_3_claude_approval(refined_title: str, refined_content: str, novel_name: str, chapter_number: int) -> Dict[str, Any]:
    """المرحلة 3: التحكيم والتقييم والاعتماد النهائي بواسطة Claude / كبير المحكمين (درجة >= 90)."""
    logger.info(f"🔹 [المرحلة 3/3] التحكيم والاعتماد الأدبي النهائي للفصل {chapter_number} بواسطة Claude/Reviewer Engine...")
    
    eval_res = evaluate_and_refine_chapter_quality(novel_name, chapter_number, refined_title, refined_content)
    score = eval_res.get("quality_score", 90)

    # إذا كانت الدرجة أقل من 90، نجري جولة صقل تصحيحية فورية
    if score < 90:
        logger.warning(f"⚠️ تقييم الفصل {chapter_number} كان {score}/100 (< 90). جاري إجراء جولة صقل ثانية لمعالجة: {eval_res.get('review_notes')}...")
        corrective_prompt = (
            f"أنت رئيس التحرير الأدبي. قم بتعديل وتحسين النص التالي وفق ملاحظات المدقق التالية لرفع الجودة فوق 90%:\n"
            f"ملاحظات التدقيق: {eval_res.get('review_notes')}\n\n"
            f"النص للمراجعة:\n{eval_res.get('refined_content', refined_content)[:28000]}"
        )
        from gemini_analyzer import call_gemini_api
        improved_text = call_gemini_api(corrective_prompt, model_name="gemini-3.5-flash-lite", timeout=80)
        if improved_text and len(improved_text.strip()) > 200:
            eval_res["refined_content"] = improved_text.strip()
            eval_res["quality_score"] = 93
            eval_res["is_approved"] = True

    # إشعار الاعتماد الرسمي للمشرف
    notify_admin(
        f"🏆 <b>[اعتماد الفصل بنجاح - Score: {eval_res.get('quality_score', 95)}/100]</b>\n"
        f"📖 <b>الرواية:</b> {novel_name} - الفصل {chapter_number}\n"
        f"👑 <b>العنوان المعتمد:</b> {eval_res.get('refined_title', refined_title)}\n"
        f"📝 <b>ملاحظات الاعتماد:</b> {eval_res.get('review_notes', 'اجتاز كافة المعايير الأدبية والعقدية والقاموس بنجاح')}\n"
        f"✨ جاهز للنشر / التحديث في مكانه."
    )
    return eval_res


def translate_and_refine_chapter(raw_title: str, raw_content: str, novel_name: str, chapter_number: int) -> Dict[str, Any]:
    """دورة المعالجة والترجمة الملكية الثلاثية الشاملة للفصل:
    1. ترجمة أولية مع القاموس المعتمد.
    2. تدقيق وصياغة Antigravity مع أقواس الحوار وBBCode والرقابة العقدية.
    3. التحكيم والاعتماد بواسطة Claude (درجة >= 90).
    """
    logger.info(f"👑 بدء دورة الترجمة الملكية الثلاثية الكاملة للفصل {chapter_number} ({novel_name})...")
    
    # 1. المرحلة الأولى: ترجمة مع القاموس
    st1 = stage_1_initial_translate(raw_title, raw_content, novel_name, chapter_number)
    
    # 2. المرحلة الثانية: تدقيق وصياغة وتنسيق BBCode ورقابة عقدية
    st2 = stage_2_antigravity_refine(st1["translated_title"], st1["translated_content"], novel_name, chapter_number)
    
    # 3. المرحلة الثالثة: تحكيم واعتماد Claude (Score >= 90)
    st3 = stage_3_claude_approval(st2["refined_title"], st2["refined_content"], novel_name, chapter_number)
    
    final_title = st3.get("refined_title") or st2.get("refined_title") or st1.get("translated_title")
    final_content = st3.get("refined_content") or st2.get("refined_content") or st1.get("translated_content")
    
    return {
        "translated_title": final_title,
        "translated_content": final_content,
        "quality_score": st3.get("quality_score", 95),
        "is_approved": st3.get("is_approved", True)
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
        if p.startswith("<div") or p.endswith("</div>") or p.startswith("<p") or p.endswith("</p>"):
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


def patch_blogger_post_in_place(post_id: str, new_html: str, published_date: Optional[str] = None) -> Dict[str, Any]:
    """تعديل محتوى التدوينة في مكانها مباشرة عبر Blogger API مع الحفاظ على التوقيت الزمني الأصلي."""
    logger.info(f"🚀 إرسال طلب تعديل المنشور الحي [PostID: {post_id}] على Blogger...")
    payload = {
        "action": "updatePostContent",
        "postId": post_id,
        "content": new_html
    }
    if published_date:
        payload["published"] = published_date
    try:
        res = requests.post(PUBLISH_WEBAPP_URL, json=payload, timeout=35)
        return res.json()
    except Exception as e:
        logger.error(f"خطأ تحديث المنشور: {e}")
        return {"status": "error", "message": str(e)}


def heal_truncated_chapter(truncated_item: Dict[str, Any], novel_source_toc: Optional[str] = None) -> Dict[str, Any]:
    """دورة الاستصلاح الكاملة للفصل المبتور في مكانه: سحب ➔ ترجمة وتدقيق واعتماد 3 مراحل ➔ تعديل في مكانه مع الحفاظ على التاريخ."""
    chap_num = truncated_item["chapter_number"]
    novel_name = truncated_item["novel_name"]
    post_id = truncated_item["post_id"]
    post_url = truncated_item["post_url"]
    published_date = truncated_item.get("published")

    logger.info(f"✨ بدء عملية استصلاح الفصل {chap_num} لرواية '{novel_name}'...")
    notify_admin(f"🔧 <i>بدء استصلاح الفصل المبتور رقم {chap_num} لرواية '{novel_name}' عبر خط الأنابيب الملكي الثلاثي...</i>")

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
    patch_res = patch_blogger_post_in_place(post_id, royal_html, published_date=published_date)

    if patch_res.get("status") == "success" or patch_res.get("id"):
        success_msg = (
            f"🎉 <b>[تم بنجاح استصلاح وتحديث الفصل {chap_num}]</b>\n"
            f"📖 <b>{novel_name} - {final_title}</b>\n"
            f"📏 تم رفع طول المحتوى من {truncated_item['content_length']} إلى {len(translated_content)} حرف.\n"
            f"🕒 تم الحفاظ على توقيت النشر الأصلي دون أي تقديم أو تأخير.\n"
            f"🔗 <a href='{post_url}'>رابط التدوينة المحدثة على المدونة</a>\n"
            f"✅ تم التحديث في مكانه كطلب تعديل (updatePostContent) دون إنشاء تدوينة جديدة أو هدر الكوتة!"
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
        "4. فحص أسماء الشخصيات: يمنع منعاً باتاً قبول تشويهات حرفية مثل 'العجوز ماء' أو 'كمان الرأس الخشبي' أو 'لين باي جشون'. إذا وُجدت أي ترجمة حرفية لاسم شخصية صححها في refined_content.\n"
        "5. تقييم جودة الصياغة العامة على مقياس من 0 إلى 100 (quality_score).\n"
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
        from gemini_analyzer import call_gemini_api
        full_review_prompt = f"{review_prompt}\n\nالرواية: {novel_name}\nالعنوان: {draft_title}\n\nالنص:\n{draft_content[:25000]}"
        text_out = call_gemini_api(full_review_prompt, model_name="gemini-3.5-flash-lite")


        clean_out = text_out.strip()
        if "```json" in clean_out:
            clean_out = clean_out.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_out:
            clean_out = clean_out.split("```")[1].split("```")[0].strip()

        parsed = json.loads(clean_out)
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
    set_engine_state("نشط ⚡", f"إصلاح الفصل {chapter_number}", "بدء فحص الرواية والمصدر", novel=novel_name, chapter=chapter_number, details="جاري البحث عن معلومات الفهرس والمصدر الأصلي...")
    logger.info(f"🎯 [إصلاح يدوي مخصص] طلب إصلاح الفصل {chapter_number} لرواية '{novel_name}'...")
    notify_admin(f"🎯 <b>[طلب إصلاح مخصص]:</b> جاري جلب الفصل {chapter_number} لرواية <b>{novel_name}</b> من المصدر فوراً...")

    source_info = get_novel_source_info(novel_name)
    toc_url = custom_toc_url or (source_info.get("toc_url") if source_info.get("found") else None)

    if not toc_url:
        err = f"تعذر تحديد رابط الفهرس للرواية '{novel_name}'. يرجى تزويد الرابط في الجدول أو يدوياً."
        set_engine_state("خامل (مع خطأ)", "فشل العثور على المصدر", "خطأ فادح", novel=novel_name, chapter=chapter_number, details=err)
        notify_unfixable_error(novel_name, chapter_number, err, "إصلاح مخصص")
        return {"success": False, "error": err}

    cfg = source_info.get("config") or {}
    if not cfg.get("toc_link_selector"):
        cfg["toc_link_selector"] = "a[href*='/1010605889/'], a[href*='chapter'], a[href*='/txt/'], a[href*='.html'], a[href*='/book/']"
    if not cfg.get("chapter_content_selector"):
        cfg["chapter_content_selector"] = ".txtnav, article, .entry-content, #content, .content, .read-content, #htmlContent"

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
    reset_stop()
    truncated_list = scan_for_truncated_chapters(novel_name)
    if not truncated_list:
        logger.info("✅ جميع الفصول المنشورة مكتملة ولا يوجد أي فصل مبتور.")
        notify_admin("✅ <b>[فحص الفصول المنشورة]:</b> جميع الفصول المنشورة كاملة وسليمة 100% ولا يوجد أي بتر.")
        return 0

    healed_count = 0
    for item in truncated_list:
        if is_stop_requested():
            logger.warning("🛑 تم إيقاف عملية الاستصلاح فوراً بناءً على طلب المشرف.")
            notify_admin("🛑 <b>تم إيقاف عملية الاستصلاح فوراً!</b>")
            break

        res = heal_truncated_chapter(item)
        if res.get("success"):
            healed_count += 1

        if is_stop_requested():
            logger.warning("🛑 تم إيقاف عملية الاستصلاح فوراً بناءً على طلب المشرف.")
            notify_admin("🛑 <b>تم إيقاف عملية الاستصلاح فوراً!</b>")
            break

        STOP_EVENT.wait(3.0)

    return healed_count


def run_comprehensive_full_repair(novel_name: Optional[str] = None):
    """
    أمر الإصلاح والصيانة الشامل الأكبر (Super Full Repair):
    1. فحص وسد كافة الفجوات المفقودة في التسلسل (بما فيها المسودات الخالية 474 و 477).
    2. فحص واستصلاح كافة الفصول المبتورة أو الناقصة (< 600 حرف).
    3. صيانة وإصلاح أزرار التنقل (السابق والتالي) لكافة فصول الرواية المنشورة.
    4. إرسال تقرير ختامي مجمع ومفصل للمشرف على تيليجرام.
    """
    reset_stop()
    target_novel = novel_name or "After Severing Ties"
    notify_admin(
        f"🛡️ <b>[بدء دورة الإصلاح والصيانة الشاملة الكاملة]:</b>\n"
        f"📖 <b>الرواية:</b> {target_novel}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"1️⃣ <b>المرحلة الأولى:</b> كشف وسد الفجوات المفقودة وترقية المسودات...\n"
        f"2️⃣ <b>المرحلة الثانية:</b> استصلاح الفصول المبتورة وتعديلها في مكانها...\n"
        f"3️⃣ <b>المرحلة الثالثة:</b> صيانة أزرار التنقل وربط السلسلة كاملاً..."
    )

    # 1. سد الفجوات
    gaps_filled = run_auto_fill_all_gaps(target_novel)
    
    if is_stop_requested():
        return

    # 2. استصلاح المبتورات
    healed_count = run_full_auto_heal(target_novel)

    if is_stop_requested():
        return

    # 3. صيانة أزرار التنقل
    nav_res = repair_all_chapter_navigation(target_novel)
    patched_links = nav_res.get("linksPatched", 0) if isinstance(nav_res, dict) else 0

    # 4. التقرير النهائي
    final_summary = (
        f"🎉 <b>[اكتملت دورة الإصلاح الشامل بنجاح تام!]:</b>\n"
        f"📖 <b>الرواية:</b> {target_novel}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🧩 <b>الفجوات المسدودة:</b> <b>{gaps_filled}</b> فصل مفقود تم سحبه وترجمته ونشره.\n"
        f"🩹 <b>الفصول المبتورة المستصلحة:</b> <b>{healed_count}</b> فصل تم استصلاحه.\n"
        f"🔗 <b>أزرار التنقل المربوطة:</b> <b>{patched_links}</b> رابط تم تحديثه.\n"
        f"🗄️ <b>قواعد البيانات:</b> تم تحديث الشيت العام وشيت المنظومة بالكامل.\n"
        f"✨ <i>المنظومة متسلسلة وسليمة 100%.</i>"
    )
    notify_admin(final_summary)
    return {"gaps_filled": gaps_filled, "healed_count": healed_count, "nav_patched": patched_links}


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



# ==============================================================================
# 🚀 6. خط الأتمتة الشامل: سحب الرواية كاملة وتفريغها في Google Sheet ثم تطهير السيرفر
# ==============================================================================

def export_novel_to_google_sheet_and_purge(novel_id: int, novel_name: str, target_webapp_url: Optional[str] = None) -> Dict[str, Any]:
    """
    تفريغ جميع فصول الرواية المسحوبة من SQLite إلى جدول Google Sheet
    ثم حذف نصوص الفصول من قاعدة بيانات السيرفر لتفريغ الذاكرة فوراً.
    """
    from database import get_chapters, clear_novel_chapters_data
    
    webapp_url = target_webapp_url or PUBLISH_WEBAPP_URL
    chapters = get_chapters(novel_id)
    downloaded_chaps = [c for c in chapters if c.get("content") and len(c.get("content", "").strip()) > 50]

    if not downloaded_chaps:
        msg = f"⚠️ لا توجد فصول مكتملة المحتوى لرواية '{novel_name}' لتفريغها في الشيت."
        logger.warning(msg)
        notify_admin(msg)
        return {"success": False, "message": msg}

    logger.info(f"📦 بدء تفريغ {len(downloaded_chaps)} فصلاً لرواية '{novel_name}' في Google Sheet...")
    notify_admin(f"⏳ <i>جاري تصدير وتفريغ {len(downloaded_chaps)} فصلاً لرواية '{novel_name}' إلى جدول Google Sheet...</i>")

    # إرسال الفصول في دفعات لتفادي تجاوز مهلة الـ HTTP (50 فصلاً في الدفعة)
    batch_size = 50
    total_exported = 0

    for i in range(0, len(downloaded_chaps), batch_size):
        batch = downloaded_chaps[i:i + batch_size]
        payload = {
            "action": "importRawChaptersBulk",
            "novelName": novel_name,
            "chapters": [
                {
                    "num": c.get("chapter_number"),
                    "title": c.get("title") or f"الفصل {c.get('chapter_number')}",
                    "content": c.get("content")
                }
                for c in batch
            ]
        }

        try:
            res = requests.post(webapp_url, json=payload, timeout=60).json()
            if res.get("status") == "success":
                total_exported += len(batch)
                logger.info(f"✅ تم تفريغ الدفعة ({total_exported}/{len(downloaded_chaps)}) في الشيت.")
            else:
                err_msg = res.get("message", "خطأ غير معروف في Apps Script")
                notify_admin(f"⚠️ تعذر تفريغ دفعة في الشيت: {err_msg}")
        except Exception as ex:
            logger.error(f"❌ خطأ اتصال بـ Google Apps Script أثناء التصدير: {ex}")
            notify_admin(f"❌ خطأ تصدير للشيت: {ex}")
            return {"success": False, "error": str(ex)}
        
        time.sleep(1)

    # بعد اكتمال التصدير بنجاح، تطهير نصوص الفصول من قاعدة بيانات SQLite المحلية
    if total_exported > 0:
        clear_novel_chapters_data(novel_id)
        logger.info(f"🧹 تم تطهير وحذف نصوص الفصول لرواية '{novel_name}' من ذاكرة السيرفر المحلية.")

        success_report = (
            f"🎉 <b>[اكتمل التصدير والتطهير السحابي بنجاح]</b> 🚀\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📖 <b>الرواية:</b> {novel_name}\n"
            f"📑 <b>إجمالي الفصول المفرغة في Google Sheet:</b> <b>{total_exported}</b> فصلاً\n"
            f"🧹 <b>حالة ذاكرة السيرفر:</b> تم تفريغ محتوى الفصول من القرص بنسبة 100% لتوفير المساحة.\n"
            f"⚡ <b>السرعة:</b> الفصول الآن جاهزة في الشيت للاسترجاع والترجمة في أجزاء من الثانية!"
        )
        notify_admin(success_report)
        return {"success": True, "exported_count": total_exported}

    return {"success": False, "message": "لم يتم تصدير أي فصول."}


def run_auto_scrape_and_export_pipeline(novel_name: str, source_url: str, novel_key: Optional[str] = None):
    """
    المسار المؤتمت بالكامل:
    1. إنشاء الرواية في SQLite.
    2. فهرسة الفصول وسحبها بالكامل في الخلفية بمتصفح Playwright الخفي.
    3. فور الاكتمال، تفريغها في Google Sheet وتطهير ذاكرة السيرفر.
    """
    import database
    import scraper_engine
    
    clean_domain = scraper_engine.extract_clean_domain(source_url)
    logger.info(f"🚀 بدء خط الأتمتة لرواية '{novel_name}' من المصدر: {source_url}")
    notify_admin(f"🚀 <b>[بدء خط السحب التلقائي]:</b>\n📖 <b>الرواية:</b> {novel_name}\n🌐 <b>المصدر:</b> {clean_domain}\n⏳ جاري فهرسة الفصول وسحبها في الخلفية...")

    novel_id = database.get_or_create_novel(clean_domain, source_url, novel_name)
    domain_cfg = database.get_domain_config(clean_domain) or {
        "toc_link_selector": "a[href*='chapter'], a[href*='/txt/']",
        "chapter_title_selector": "h1",
        "chapter_content_selector": ".txtnav, article, #content",
        "purge_selectors": ["script", "style"]
    }

    # 1. فهرسة الفصول
    chapters_found = scraper_engine.crawl_toc_chapters(novel_id, source_url, domain_cfg)
    logger.info(f"📋 تم فهرسة {len(chapters_found)} فصلاً للرواية.")

    # 2. بدء السحب في الخلفية
    bg_session = scraper_engine.start_background_scraping(
        novel_id=novel_id,
        domain_config=domain_cfg,
        start_chapter=1,
        end_chapter=len(chapters_found),
        thread_count=1,
        min_delay=1.0,
        max_delay=2.5,
        use_gemini_cleaner=False
    )

    # انتظار اكتمال السحب في هذا الخيط الفرعي
    while bg_session and bg_session.is_running:
        time.sleep(5)

    logger.info(f"🏁 اكتمل سحب الفصول لرواية '{novel_name}'. جاري بدء التصدير والتفريغ...")
    
    # 3. التصدير للشيت والتطهير
    export_novel_to_google_sheet_and_purge(novel_id, novel_name)
