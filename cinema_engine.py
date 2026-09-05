# -*- coding: utf-8 -*-
"""
==============================================================================
Smart Cinema & TV Series AI Engine v1.0
==============================================================================
هذا الملف مسؤول عن:
1. التعرف على الأفلام والمسلسلات عبر النصوص، الصور، أو لقطات الفيديو بالذكاء الاصطناعي.
2. استخراج بيانات العمل الكاملة (الاسم الأصلي والعربي، القصة، التقييم، المواسم والحلقات).
3. استخراج تفاصيل الحلقات (المدة، الملخص، صورة المعاينة).
4. البحث عن روابط التحميل والمشاهدة المباشرة مع خيارات الترجمة الفورية.
"""

import os
import sys
import json
import base64
import requests
from typing import Dict, Any, List, Optional

import database
from gemini_analyzer import call_gemini_api

def analyze_cinema_content(
    query_text: str = "",
    image_bytes: Optional[bytes] = None,
    image_mime_type: str = "image/jpeg"
) -> Dict[str, Any]:
    """
    تحليل المحتوى السينمائي (فيلم / مسلسل) بالذكاء الاصطناعي لاستخراج كافة التفاصيل.
    """
    prompt = """
أنت خبير أرشيف سينمائي وموسوعة أفلام ومسلسلات عالمية وعربية مدعومة بالذكاء الاصطناعي.
المهمة: قم بالتعرف بدقة على الفيلم أو المسلسل الموصوف أو الموجود في الصورة/النص التالي.

قم بإرجاع النتيجة بصيغة JSON حصراً بالشكل التالي دون أي نصوص إضافية:
{
  "recognized": true,
  "type": "movie" أو "series" أو "unknown",
  "title_original": "اسم العمل بلغته الأصلية",
  "title_arabic": "اسم العمل بالعربي أو الشائع عربياً",
  "release_year": "سنة الإصدار",
  "duration": "مدة العرض (مثال: ساعتان و15 دقيقة) للفيلم، أو متوسط مدة الحلقة للمسلسل",
  "rating": "تقييم العمل (مثال: 8.5/10)",
  "genres": ["أكشن", "غموض", "دراما"],
  "story_arabic": "ملخص مشوق ودقيق لقصة العمل باللغة العربية الفصحى (حوالي 3-4 أسطر)",
  "seasons_count": 1,
  "episodes_per_season": [10],
  "is_arabic_content": false,
  "poster_url": "رابط تقريبي لصورة أو بوستر رسمي بجودة عالية إن وجد",
  "sample_episodes": [
    {
      "season": 1,
      "episode": 1,
      "title": "عنوان الحلقة الأولى",
      "summary": "ملخص لأحداث هذه الحلقة",
      "duration": "45 دقيقة"
    }
  ]
}

إذا كان مسلسلاً، اذكر عدد المواسم بدقة (seasons_count) وعدد الحلقات التقديري لكل موسم.
إذا لم تستطع التعرف تماماً، ضع "recognized": false مع أفضل تخمين ممكن.
"""

    if query_text:
        prompt += f"\n\nالمحتوى أو الوصف المرسل من المستخدم:\n{query_text}\n"

    try:
        # إذا كانت هناك صورة مرفقة (Multimodal Gemini Vision)
        if image_bytes:
            b64_img = base64.b64encode(image_bytes).decode("utf-8")
            stored_key = database.get_setting("gemini_api_key", os.getenv("GEMINI_API_KEY", ""))
            clean_model = "gemini-2.5-flash"
            
            if stored_key:
                direct_url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={stored_key}"
                payload = {
                    "contents": [{
                        "parts": [
                            {"text": prompt},
                            {
                                "inline_data": {
                                    "mime_type": image_mime_type,
                                    "data": b64_img
                                }
                            }
                        ]
                    }],
                    "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}
                }
                res = requests.post(direct_url, json=payload, timeout=40)
                if res.status_code == 200:
                    cand = res.json().get("candidates", [])
                    if cand:
                        text_res = cand[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        return json.loads(text_res.strip().replace("```json", "").replace("```", ""))
        
        # تحليل نصي عادي عبر مجمع وسائط Gemini
        raw_result = call_gemini_api(prompt=prompt, model_name="gemini-3.6-flash")
        cleaned_json = raw_result.strip()
        if "```json" in cleaned_json:
            cleaned_json = cleaned_json.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned_json:
            cleaned_json = cleaned_json.split("```")[1].split("```")[0].strip()

        return json.loads(cleaned_json)
    except Exception as e:
        return {
            "recognized": False,
            "error": str(e),
            "type": "unknown",
            "title_original": query_text or "غير معروف",
            "title_arabic": query_text or "غير معروف",
            "story_arabic": "تعذر استخراج التفاصيل تلقائياً، يرجى المحاولة باسم أكثر وضوحاً."
        }


def get_episode_details(series_name: str, season: int, episode: int) -> Dict[str, Any]:
    """استخراج تفاصيل دقيقة لحلقة معينة من مسلسل."""
    prompt = f"""
أنت خبير في المسلسلات التلفزيونية.
المطلوب استخراج تفاصيل الحلقة {episode} من الموسم {season} للمسلسل التالي: "{series_name}".

أرجع النتيجة بصيغة JSON فقط:
{{
  "series_name": "{series_name}",
  "season": {season},
  "episode": {episode},
  "title": "عنوان الحلقة (عربي ومترجم)",
  "duration": "المدة المقدرة (مثال: 50 دقيقة)",
  "summary": "ملخص أحداث الحلقة باختصار بدون حرق مخل",
  "air_date": "تاريخ العرض إن وجد"
}}
"""
    try:
        raw_result = call_gemini_api(prompt=prompt, model_name="gemini-3.8-flash")
        cleaned = raw_result.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned)
    except Exception:
        return {
            "series_name": series_name,
            "season": season,
            "episode": episode,
            "title": f"الحلقة {episode}",
            "duration": "45 دقيقة",
            "summary": f"الحلقة رقم {episode} من الموسم {season} لمسلسل {series_name}."
        }
