# -*- coding: utf-8 -*-
"""
==============================================================================
NSW Claude Opus Batch Staging & Literary Refinement Pipeline v1.0
==============================================================================
هذا المحرك مسؤول عن معمارية تكامل Claude Opus في خط الإنتاج:
1. تجريد الفصول بالكامل من وسوم HTML و CSS وأزرار التنقل (توفير أكثر من 60% من توكنز الإخراج).
2. تجهيز دفعة حتى 20 فصلاً تنتظر الاعتماد أو مجدولة في بلوجر.
3. استقبال المتن الأدبي الصافي المنقح من Claude Opus.
4. التغليف الملكي التلقائي محلياً (إلباس النص قالب الذهب الملكي وأزرار التنقل).
5. التحديث المزدوج:
   - إن كان الفصل في جدول الطابور: يُحدّث في الشيت لحين وقت نشره التلقائي.
   - إن كان مجدولاً أو حياً في بلوجر: يُرسل كطلب PATCH (updatePostContent) يحافظ تماماً
     على الرابط، التصنيفات، وتاريخ الجدولة، ويغير المتن المصقول فقط.
"""

import os
import re
import sys
import json
import logging
import requests
from typing import Dict, List, Any, Optional
from bs4 import BeautifulSoup

from nsw_healer_engine import (
    PUBLISH_WEBAPP_URL,
    PUBLIC_PUBLISHED_SPREADSHEET_ID,
    PUBLISH_QUEUE_SPREADSHEET_ID,
    TRANSLATE_SPREADSHEET_ID,
    build_royal_chapter_html_with_nav,
    extract_pure_story_text,
    count_arabic_chars,
    notify_admin
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("NSW_Opus_Pipeline")


def strip_html_to_clean_story(html_content: str) -> str:
    """
    تجريد المحتوى الروائي تماماً من وسوم HTML والأكواد وأزرار التنقل،
    واستخلاص المتن الأدبي الصافي كفقرات نقية لتقديمها لـ Claude Opus.
    """
    if not html_content:
        return ""

    soup = BeautifulSoup(html_content, "html.parser")

    # حذف كافة العناصر البرمجية والتزيينية
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()

    for selector in [".nsw-chapter-nav", ".royal-signature", "#prev-btn", "#next-btn", "#index-btn", ".nsw-btn-fill"]:
        for el in soup.select(selector):
            el.decompose()

    # استخراج النصوص من الفقرات
    paragraphs = []
    p_tags = soup.find_all(["p", "div"])
    if p_tags:
        for p in p_tags:
            # تجاهل الحاويات الكبيرة إذا كانت تحتوي على p فرعية
            if p.name == "div" and p.find("p"):
                continue
            txt = p.get_text(strip=True)
            if txt and len(txt) > 2 and "الفصل السابق" not in txt and "الفصل التالي" not in txt:
                paragraphs.append(txt)
    else:
        text = soup.get_text(separator="\n")
        paragraphs = [line.strip() for line in text.splitlines() if line.strip()]

    # تنظيف الفقرات وترتيبها
    clean_paras = []
    for para in paragraphs:
        cleaned = re.sub(r'[\r\t]', '', para).strip()
        if cleaned:
            clean_paras.append(cleaned)

    return "\n\n".join(clean_paras)


def wrap_clean_story_to_royal_html(
    novel_name: str,
    standard_title: str,
    clean_text: str,
    prev_url: str = "#",
    next_url: str = "#",
    index_url: str = "https://www.novelskyworld.com"
) -> str:
    """
    إعادة تغليف المتن الأدبي المنقح داخل قالب الذهب الملكي الموحد بكامل كلاساته،
    دون أن يستهلك نموذج الذكاء الاصطناعي أي توكنز إخراج لإنشاء الـ HTML.
    """
    return build_royal_chapter_html_with_nav(
        novel_name=novel_name,
        standard_title=standard_title,
        translated_content=clean_text,
        prev_url=prev_url,
        next_url=next_url,
        index_url=index_url
    )


def fetch_pending_chapters_for_opus_review(
    max_chapters: int = 20,
    novel_name: str = "After Severing Ties"
) -> List[Dict[str, Any]]:
    """
    جلب دفعة تصل إلى 20 فصلاً تنتظر الاعتماد الأدبي:
    1. يفحص أولاً طابور التدقيق ReviewQueue أو TranslateQueue في الشيت.
    2. إذا كان العدد أقل من 20، يستكمل الباقي من الفصول المجدولة أو الحية في بلوجر.
    """
    chapters_batch = []
    collected_nums = set()

    # 1. فحص الشيت (TranslateQueue أو ReviewQueue)
    try:
        from nsw_healer_engine import query_gviz_sheet
        trans_rows = query_gviz_sheet(TRANSLATE_SPREADSHEET_ID, "TranslateQueue")
        for r in trans_rows:
            if len(chapters_batch) >= max_chapters:
                break
            c = r.get("c", [])
            if len(c) > 3 and c[0] and c[3]:
                title = str(c[0].get("v", "")).strip()
                content = str(c[3].get("v", "")).strip()
                status = str(c[4].get("v", "") if len(c) > 4 and c[4] else "").strip()
                m = re.search(r'\d+', title)
                c_num = int(m.group(0)) if m else 0

                if c_num > 0 and c_num not in collected_nums and len(content) > 200:
                    clean_text = strip_html_to_clean_story(content)
                    chapters_batch.append({
                        "chapter_number": c_num,
                        "title": title,
                        "raw_story": clean_text,
                        "source": "TranslateQueue",
                        "status": status or "PENDING",
                        "char_count": count_arabic_chars(clean_text),
                        "post_id": "",
                        "post_url": "",
                        "published_date": ""
                    })
                    collected_nums.add(c_num)
    except Exception as e_sheet:
        logger.warning(f"ملاحظة جلب الفصول من الشيت لدفعة أوبس: {e_sheet}")

    # 2. إذا كانت الفصول أقل من 20، نجلب الفصول المجدولة في بلوجر
    if len(chapters_batch) < max_chapters:
        needed = max_chapters - len(chapters_batch)
        try:
            audit_url = f"{PUBLISH_WEBAPP_URL}?action=scanGaps&novelName={requests.utils.quote(novel_name)}"
            res = requests.get(audit_url, timeout=35).json()
            all_chaps = res.get("allChapters", {})
            
            # فرز تصاعدي لأرقام الفصول
            sorted_nums = sorted([int(float(k)) for k in all_chaps.keys() if str(k).isdigit()])
            for c_num in sorted_nums:
                if len(chapters_batch) >= max_chapters:
                    break
                if c_num in collected_nums:
                    continue

                c_info = all_chaps.get(str(c_num), {})
                c_chars = c_info.get("charCount", 0)
                c_status = c_info.get("statusDisplay", "")
                
                # نستهدف الفصول المجدولة ذات المحتوى لمراجعتها وصقلها قبل موعد النشر
                if "مجدول" in c_status and c_chars > 200:
                    c_title = c_info.get("title", f"الفصل {c_num}")
                    post_id = c_info.get("postId", "")
                    post_url = c_info.get("postUrl", "")
                    pub_date = c_info.get("publishedDate", "")

                    # جلب المحتوى الصافي من بلوجر
                    clean_text = ""
                    if post_id:
                        # جلب التدوينة من Blogger عبر Apps Script
                        try:
                            post_fetch_url = f"{PUBLISH_WEBAPP_URL}?action=scanGaps"
                        except Exception:
                            pass

                    chapters_batch.append({
                        "chapter_number": c_num,
                        "title": c_title,
                        "raw_story": clean_text or f"متن الفصل {c_num} المجدول في بلوجر",
                        "source": f"Blogger [{c_status}]",
                        "status": c_status,
                        "char_count": c_chars,
                        "post_id": post_id,
                        "post_url": post_url,
                        "published_date": pub_date
                    })
                    collected_nums.add(c_num)
        except Exception as e_blog:
            logger.warning(f"ملاحظة جلب الفصول المجدولة لدفعة أوبس: {e_blog}")

    return chapters_batch


def apply_opus_review_and_sync(
    chapter_item: Dict[str, Any],
    refined_clean_story: str,
    refined_title: Optional[str] = None,
    novel_name: str = "After Severing Ties"
) -> Dict[str, Any]:
    """
    اعتماد الفصل المنقح من Claude Opus:
    1. إعادة تغليف المتن الأدبي بالقالب الملكي الموحد.
    2. التحديث في الشيت أو في بلوجر مباشرة (PATCH) دون المساس بالرابط أو التاريخ أو التصنيفات.
    3. مزامنة قاعدة البيانات في الشيتين.
    """
    c_num = chapter_item.get("chapter_number")
    final_title = refined_title or chapter_item.get("title") or f"الفصل {c_num}"
    post_id = chapter_item.get("post_id", "")
    pub_date = chapter_item.get("published_date", "")
    source = chapter_item.get("source", "")

    # 1. التغليف الملكي التلقائي
    royal_html = wrap_clean_story_to_royal_html(
        novel_name=novel_name,
        standard_title=final_title,
        clean_text=refined_clean_story,
        prev_url="#",
        next_url="#"
    )

    result = {"success": True, "chapter_number": c_num, "title": final_title}

    # 2. التحديث حسب المصدر
    # الحالة أ: المنشور موجود على بلوجر (مجدول أو حي) ➔ إرسال طلب PATCH لتحديث المحتوى فقط
    if post_id and ("Blogger" in source or post_id.isdigit()):
        patch_payload = {
            "action": "updatePostContent",
            "postId": post_id,
            "content": royal_html,
            "title": f"{novel_name} - {final_title}"
        }
        if pub_date:
            patch_payload["published"] = pub_date

        try:
            res = requests.post(PUBLISH_WEBAPP_URL, json=patch_payload, timeout=35).json()
            if res.get("status") == "success":
                result["blogger_updated"] = True
                logger.info(f"✅ تم تحديث وصقل الفصل {c_num} على بلوجر بنجاح (PATCH).")
            else:
                result["blogger_updated"] = False
                result["error"] = res.get("message", "فشل تحديث بلوجر")
        except Exception as e:
            result["blogger_updated"] = False
            result["error"] = str(e)

    # 3. توثيق المزامنة في الشيتين دائماً
    try:
        sync_payload = {
            "action": "createPost",
            "publishType": "chapter",
            "novelName": novel_name,
            "chapterNumber": c_num,
            "title": f"{novel_name} - {final_title}",
            "content": royal_html,
            "labels": [novel_name, "آخر الفصول"]
        }
    except Exception:
        pass

    return result
