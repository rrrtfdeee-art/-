# -*- coding: utf-8 -*-
"""
==============================================================================
NSW Chapter Healing Engine & Truncation Auditor v1.0
==============================================================================
هذا المحرك مسؤول عن:
1. فحص فصول المدونة المنشورة والمجدولة لكشف الفصول المبتورة (أقل من 800 حرف أو ناقصة بنسبة كبيرة).
2. استخراج رابط المصدر الخام للرواية من جدول الفهارس المركزي (NOVELS_INDEX_SPREADSHEET_ID).
3. سحب متن الفصل الخام كاملاً عبر Playwright Stealth Engine.
4. الترجمة المتقدمة عبر Gemini مع الالتزام الصارم بالقاموس وتكييف المصطلحات والرقابة العقدية.
5. التدقيق اللغوي والصقل البلاغي والوسوم الملكية (Royal BBCode Tags).
6. إرسال طلب تحديث في مكانه (In-Place Update via updatePostContent) إلى سيرفر النشر على Blogger:
   - يحافظ على رابط الفصل الأصلي (SEO & Navigation Links).
   - لا ينشئ تدوينة جديدة (يوفر حصة النشر اليومية 50 مقال/يوم).
"""

import os
import sys
import time
import json
import re
import logging
from typing import Dict, List, Any, Optional, Tuple
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

# الحد الأدنى لعدد الحروف لاعتبار الفصل مكتملاً
MIN_SAFE_TEXT_LENGTH = 800


def notify_admin(message: str):
    """إرسال إشعار تليجرام للمشرف."""
    if not TELEGRAM_BOT_TOKEN or not ADMIN_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": ADMIN_CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=15)
    except Exception as e:
        logger.error(f"خطأ إرسال إشعار تليجرام: {e}")


def fetch_published_posts_from_sheet(novel_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """جلب سجل الفصول المنشورة من ورقة Published Posts المركزية."""
    url = f"https://docs.google.com/spreadsheets/d/{PUBLIC_PUBLISHED_SPREADSHEET_ID}/gviz/tq?tqx=out:json"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers, timeout=25)
    text = res.text
    json_str = text[text.find('{'):text.rfind('}') + 1]
    data = json.loads(json_str)

    posts = []
    rows = data.get("table", {}).get("rows", [])
    for r in rows:
        c = r.get("c", [])
        if not c:
            continue
        
        chap_num_raw = c[0].get("v") if len(c) > 0 and c[0] else 0
        title = str(c[1].get("v", "") if len(c) > 1 and c[1] else "").strip()
        labels_raw = str(c[2].get("v", "") if len(c) > 2 and c[2] else "")
        pub_date = str(c[3].get("v", "") if len(c) > 3 and c[3] else "")
        post_id = str(c[4].get("v", "") if len(c) > 4 and c[4] else "").strip()
        post_url = str(c[5].get("v", "") if len(c) > 5 and c[5] else "").strip()
        novel_name = str(c[7].get("v", "") if len(c) > 7 and c[7] else "").strip()

        if not novel_name and " - " in title:
            novel_name = title.split(" - ")[0].strip()

        if not post_id or not post_url:
            continue

        if novel_filter and novel_filter.lower() not in novel_name.lower():
            continue

        try:
            chap_num = float(chap_num_raw)
        except Exception:
            m = re.search(r'\d+', title)
            chap_num = float(m.group(0)) if m else 0

        posts.append({
            "chapter_number": int(chap_num),
            "title": title,
            "post_id": post_id,
            "post_url": post_url,
            "novel_name": novel_name,
            "publish_date": pub_date
        })

    return posts


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
        
        # استخراج رابط المنشور
        alt_link = "#"
        for l in entry.get("link", []):
            if l.get("rel") == "alternate":
                alt_link = l.get("href")
                break

        # استخراج Post ID من معرف الدخول
        entry_id = entry.get("id", {}).get("$t", "")
        post_id = entry_id.split("post-")[-1] if "post-" in entry_id else ""

        # استخراج المتن الصافي
        clean_text = re.sub(r'<[^>]+>', '', content_html).strip()
        
        # استخراج رقم الفصل واسم الرواية
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
    """
    جلب معلومات الرواية ورابط المصدر الخام ومحددات السحب:
    1. يبحث أولاً في قاعدة بيانات SQLite المحلية (`novels` & `domains_config`).
    2. يبحث في شيت الفهارس المركزي `NOVELS_INDEX_SPREADSHEET_ID`.
    """
    # 1. فحص SQLite المحلي
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

    # 2. فحص شيت الفهارس المركزي
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
    """
    فحص شامل لكافة الفصول واستخراج الفصول المبتورة التي يقل متنها عن الحد الآمن.
    """
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
    """
    سحب متن الفصل الأصلي الخام برقمه المحدد مباشرة من صفحة الفهرس والمصدر الأصلي.
    """
    logger.info(f"🌐 جلب الفصل الخام رقم {chapter_number} من الفهرس: {toc_url}")
    toc_sel = domain_config.get("toc_link_selector") or "a[href*='chapter'], a[href*='/txt/']"
    
    # 1. جلب قائمة فصول الرواية لاستهداف رابط هذا الفصل بدقة
    chapters_list, _ = scraper_engine.crawl_toc_chapters(toc_url, toc_sel)
    target_url = None
    for item in chapters_list:
        if item.get("chapter_number") == chapter_number:
            target_url = item.get("url")
            break

    if not target_url:
        logger.error(f"❌ لم يتم العثور على رابط الفصل {chapter_number} في صفحة الفهرس.")
        return None

    # 2. سحب صفحة الفصل واستخراج المحتوى المنظف
    with scraper_engine.PlaywrightStealthBrowser(headless=True) as browser:
        raw_html, _ = browser.get_page_html(target_url, wait_selector=domain_config.get("chapter_content_selector"))
        clean_content = scraper_engine.clean_chapter_content(
            raw_html,
            domain_config.get("chapter_content_selector") or "article, .entry-content, #content, .txtnav",
            domain_config.get("purge_selectors") or ["script", "style", "nav"]
        )
        return clean_content


def translate_and_refine_chapter(raw_title: str, raw_content: str, novel_name: str, chapter_number: int) -> Dict[str, Any]:
    """
    تمرير الفصل عبر خط أنابيب الترجمة الكامل بالذكاء الاصطناعي:
    1. ترجمة Gemini مع المعايير الملكية والرقابة العقدية.
    2. تحويل وسوم BBCode إلى HTML الملكي الكامل.
    """
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

    # الإرسال عبر مجمع وسائط Google Apps Script الموزع
    success, res = gas_pool.execute_request(action="gemini_proxy", payload=payload)
    if not success or not res:
        raise RuntimeError(f"فشل إرسال طلب الترجمة عبر مجمع الوسائط: {res}")

    try:
        if isinstance(res, str):
            res_obj = json.loads(res)
        else:
            res_obj = res

        # استخراج النص الناتج
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
    """تحويل وسوم BBCode إلى كود HTML الملكي المعتمد في NSW."""
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


def patch_blogger_post_in_place(post_id: str, new_html: str) -> Dict[str, Any]:
    """
    إرسال طلب تعديل محتوى التدوينة في مكانها مباشرة عبر نقطة Blogger WebApp.
    هذا يضمن الحفاظ على الرابط وعدم استهلاك كوتة النشر اليومية.
    """
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
    """
    دورة الاستصلاح الكاملة للفصل المبتور:
    1. استخراج المصدر.
    2. سحب النص الخام كاملاً.
    3. الترجمة والتدقيق.
    4. بناء الهيكل الملكي.
    5. التعديل المباشر على Blogger.
    """
    chap_num = truncated_item["chapter_number"]
    novel_name = truncated_item["novel_name"]
    post_id = truncated_item["post_id"]
    post_url = truncated_item["post_url"]

    logger.info(f"✨ بدء عملية استصلاح الفصل {chap_num} لرواية '{novel_name}'...")
    notify_admin(f"🔧 <i>بدء استصلاح الفصل المبتور رقم {chap_num} لرواية '{novel_name}'...</i>")

    # 1. جلب إعدادات الرواية
    source_info = get_novel_source_info(novel_name)
    toc_url = novel_source_toc or (source_info.get("toc_url") if source_info.get("found") else None)
    
    if not toc_url:
        err = f"تعذر إيجاد رابط فهرس المصدر الأصلي للرواية '{novel_name}'."
        logger.error(err)
        return {"success": False, "error": err}

    cfg = source_info.get("config") or {
        "toc_link_selector": "a[href*='chapter'], a[href*='/txt/']",
        "chapter_title_selector": "h1",
        "chapter_content_selector": ".txtnav, article, #content",
        "purge_selectors": ["script", "style"]
    }

    # 2. سحب المتن الخام كاملاً
    raw_content = fetch_raw_chapter_by_number(toc_url, chap_num, cfg)
    if not raw_content or len(raw_content) < MIN_SAFE_TEXT_LENGTH:
        err = f"المتن المسحوب من المصدر لا يزال صغيراً جداً أو غير متوفر ({len(raw_content) if raw_content else 0} حرف)."
        logger.error(err)
        return {"success": False, "error": err}

    # 3. الترجمة والتدقيق
    trans_res = translate_and_refine_chapter(truncated_item["title"], raw_content, novel_name, chap_num)
    sub_title = trans_res.get("translated_title", f"الفصل {chap_num}")
    clean_sub_title = re.sub(r'^(?:الفصل|chapter|chap)\s*\d+[:\s\-]*', '', sub_title, flags=re.I).strip()
    final_title = f"الفصل {chap_num}: {clean_sub_title}" if clean_sub_title else f"الفصل {chap_num}"
    translated_content = trans_res.get("translated_content", "")

    # 4. بناء الهيكل الملكي
    royal_html = build_royal_chapter_html(novel_name, final_title, translated_content)

    # 5. التحديث المباشر في Blogger في مكانه
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
        notify_admin(f"❌ فشل تحديث الفصل {chap_num} على Blogger: {err_msg}")
        return {"success": False, "error": err_msg}


def run_full_auto_heal(novel_name: Optional[str] = None):
    """تشغيل دورة الفحص والاستصلاح الشاملة لكافة الفصول المبتورة تلقائياً."""
    truncated_list = scan_for_truncated_chapters(novel_name)
    if not truncated_list:
        logger.info("✅ جميع الفصول المنشورة مكتملة ولا يوجد أي فصل مبتور.")
        notify_admin("✅ <b>[فحص الفصول المنشورة]:</b> جميع الفصول المنشورة كاملة وسليمة 100% ولا يوجد أي بتر.")
        return 0

    logger.info(f"⚠️ تم العثور على {len(truncated_list)} فصول مبتورة. جاري الاستصلاح...")
    healed_count = 0
    for item in truncated_list:
        res = heal_truncated_chapter(item)
        if res.get("success"):
            healed_count += 1
        time.sleep(3.0)

    logger.info(f"🎉 اكتملت الدورة: تم استصلاح {healed_count} من أصل {len(truncated_list)} فصول مبتورة.")
    return healed_count


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    run_full_auto_heal(target)
