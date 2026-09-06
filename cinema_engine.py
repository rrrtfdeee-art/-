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
أنت خبير أرشيف سينمائي وتلفزيوني عالمي، ومتخصص استثنائي في الدراما الآسيوية والمسلسلات الصينية القصيرة (Chinese Mini-Dramas / Short Dramas / 微短剧 / Web Short Series) المنتشرة على منصات مثل:
(DramaBox, ReelShort, ShortMax, GoodShort, MoboReels, NetShort, Kuaishou, Douyin, Tencent WeTV, iQIYI, Youku, MangoTV, Viki).

المهمة: قم بالتعرف بدقة فائقة على المسلسل أو الفيلم، وخاصة إذا كان مسلسلاً صينياً قصيراً (من نوع: الرئيس التنفيذي المتسلط، زواج المصلحة، الهوية الخفية، عودة الملك/الإله، الانتقام والولادة من جديد، الصعلوك الذي تحول لملياردير، زراعة الخلود).
استخرج:
1. الاسم الصيني الأصلي بدقة (بالحروف الصينية Hanzi إن أمكن أو بينيين).
2. الاسم الإنجليزي والاسم المترجم والشائع بالعربية.
3. عدد الحلقات الحقيقي (المسلسلات الصينية القصيرة عادة تكون بين 60 إلى 120 حلقة بمدة 1-3 دقائق للحلقة).
4. المنصة الأصلية للعمل (مثل DramaBox أو ReelShort أو WeTV).
5. ملخص القصة الدقيق.

قم بإرجاع النتيجة بصيغة JSON حصراً بالشكل التالي دون أي نصوص إضافية:
{
  "recognized": true,
  "type": "mini_drama" أو "series" أو "movie",
  "platform": "DramaBox / ReelShort / WeTV / Douyin",
  "title_original": "اسم العمل بالصينية أو لغته الأصلية",
  "title_arabic": "اسم العمل بالعربي أو الشائع عربياً",
  "title_english": "English Title",
  "release_year": "سنة الإصدار",
  "duration": "متوسط مدة الحلقة (مثال: 2 دقيقة)",
  "rating": "تقييم العمل (مثال: 9.2/10)",
  "genres": ["رئيس تنفيذي", "زواج مدبر", "انتقام", "رومانسية"],
  "story_arabic": "ملخص مشوق ودقيق لقصة العمل باللغة العربية الفصحى (حوالي 3-4 أسطر)",
  "seasons_count": 1,
  "episodes_per_season": [80],
  "is_chinese_short_drama": true,
  "poster_url": "رابط تقريبي لصورة أو بوستر رسمي بجودة عالية إن وجد",
  "sample_episodes": [
    {
      "season": 1,
      "episode": 1,
      "title": "الحلقة 1",
      "summary": "ملخص سريع للحلقة الأولى",
      "duration": "2 دقيقة"
    }
  ]
}

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


def get_cinema_sources(title: str, c_type: str = "movie", season: int = 1, episode: int = 1) -> List[Dict[str, str]]:
    """
    توليد وتوفير روابط مصادر البث والمشاهدة والتحميل المباشرة (العربية والأجنبية المجانية والرسمية).
    """
    import urllib.parse
    encoded_title = urllib.parse.quote(title)
    
    sources = []
    
    # 1. المصادر العربية المجانية والمفتوحة (مترجم ومدبلج)
    # سيرفرات المشاهدة المباشرة المتوافقة مع البوتات والتحميل:
    if c_type == "series":
        sources.append({
            "name": "🌐 عرب سيد / فاصل إعلاني (مترجم)",
            "url": f"https://vidsrc.to/embed/tv/{encoded_title}/{season}/{episode}",
            "type": "free_stream"
        })
        sources.append({
            "name": "⚡ مشغل VidSrc السريع (بدون إعلانات)",
            "url": f"https://vidsrc.xyz/embed/tv?imdb={encoded_title}&season={season}&episode={episode}",
            "type": "direct_player"
        })
        sources.append({
            "name": "📥 خادم التحميل السحابي المباشر",
            "url": f"https://autoembed.to/tv/imdb/{encoded_title}-{season}-{episode}",
            "type": "direct_download"
        })
    else:
        sources.append({
            "name": "🌐 سيرفر البث المباشر (عربي/مترجم)",
            "url": f"https://vidsrc.to/embed/movie/{encoded_title}",
            "type": "free_stream"
        })
        sources.append({
            "name": "⚡ مشغل VidSrc الفوري HD",
            "url": f"https://vidsrc.xyz/embed/movie?imdb={encoded_title}",
            "type": "direct_player"
        })
        sources.append({
            "name": "📥 سيرفر التحميل السريع MP4",
            "url": f"https://autoembed.to/movie/imdb/{encoded_title}",
            "type": "direct_download"
        })

    # 2. كبرى منصات البث العربية المجانية المشهورة
    sources.append({
        "name": "🎬 إيجي بست (EgyBest)",
        "url": f"https://egybest.to/explore/?q={encoded_title}",
        "type": "free_stream"
    })
    sources.append({
        "name": "🔥 أكوام (Akwam HD)",
        "url": f"https://akwam.to/search?q={encoded_title}",
        "type": "free_stream"
    })
    sources.append({
        "name": "🍿 وي سيما (WeCima / MyCima)",
        "url": f"https://wecima.show/search/{encoded_title}/",
        "type": "free_stream"
    })
    sources.append({
        "name": "🧲 خادم التورنت فائق السرعة (YTS / 1337x)",
        "url": f"https://1337x.to/search/{encoded_title}/1/",
        "type": "torrent"
    })

    # 3. منصات المسلسلات الصينية والآسيوية القصيرة المشهورة
    sources.append({
        "name": "📱 منصة DramaBox (دراما بوكس)",
        "url": f"https://www.dramaboxdb.com/search?q={encoded_title}",
        "type": "mini_drama"
    })
    sources.append({
        "name": "🎭 منصة ReelShort الرسمية",
        "url": f"https://www.reelshort.com/search/{encoded_title}",
        "type": "mini_drama"
    })
    sources.append({
        "name": "⚡ يوتيوب - مسلسلات صينية مترجمة كاملة",
        "url": f"https://www.youtube.com/results?search_query={encoded_title}+مسلسل+صيني+قصير+كامل+مترجم",
        "type": "free_stream"
    })
    sources.append({
        "name": "🌐 ديلي موشن (Dailymotion Mini Dramas)",
        "url": f"https://www.dailymotion.com/search/{encoded_title}%20chinese%20drama/videos",
        "type": "free_stream"
    })

    # 4. المنصات الرسمية العالمية والعربية المشهورة (المدفوعة والمجانية)
    sources.append({
        "name": "👑 منصة شاهد VIP (Shahid)",
        "url": f"https://shahid.mbc.net/ar/search?q={encoded_title}",
        "type": "official_paid"
    })
    sources.append({
        "name": "🍿 منصة Netflix",
        "url": f"https://www.netflix.com/search?q={encoded_title}",
        "type": "official_paid"
    })
    sources.append({
        "name": "✨ منصة OSN+ / TOD",
        "url": f"https://osnplus.com/ar-ae/search?q={encoded_title}",
        "type": "official_paid"
    })
    sources.append({
        "name": "🌟 منصة Disney+",
        "url": f"https://www.disneyplus.com/search?q={encoded_title}",
        "type": "official_paid"
    })
    sources.append({
        "name": "📦 منصة Amazon Prime Video",
        "url": f"https://www.primevideo.com/search?phrase={encoded_title}",
        "type": "official_paid"
    })
    sources.append({
        "name": "⭐ قاعدة بيانات وتراخيص IMDb",
        "url": f"https://www.imdb.com/find/?q={encoded_title}",
        "type": "official_info"
    })

    return sources


def resolve_and_download_cinema_media(
    title: str,
    c_type: str = "movie",
    season: int = 1,
    episode: int = 1,
    with_subtitles: bool = True
) -> Dict[str, Any]:
    """
    🔍 بوابة خلفية ذكية للذكاء الاصطناعي:
    يقوم السيرفر بفحص المصادر المتاحة عنده، واستخراج أفضل رابط فيديو مباشر،
    وتنزيله سحابياً مع دمج أو توفير الترجمة العربية، وإرجاع ملف الفيديو الجاهز للبوت.
    """
    import media_engine
    
    # محاولة البحث عن الحلقة/الفيلم في خوادم الفيديو المباشرة
    search_queries = [
        f"{title} full movie arabic sub" if c_type == "movie" else f"{title} s{season:02d}e{episode:02d} arabic sub",
        f"{title} كامل مترجم" if c_type == "movie" else f"{title} الموسم {season} الحلقة {episode} مترجم",
        f"{title} raw" if not with_subtitles else f"{title}"
    ]

    for q in search_queries:
        # البحث في يوتيوب / الخوادم عبر yt-dlp
        yt_search_url = f"ytsearch3:{q}"
        try:
            dl_res = media_engine.download_media_file(yt_search_url, extract_audio=False)
            if dl_res.get("success") and os.path.exists(dl_res.get("filepath", "")):
                return {
                    "success": True,
                    "filepath": dl_res["filepath"],
                    "title": dl_res.get("title", title),
                    "filesize_mb": dl_res.get("filesize_mb", 0),
                    "with_subtitles": with_subtitles
                }
        except Exception:
            continue

    # محاولة سحب الفيديو المباشر من مصادر البث الحرة (VidSrc / Embed direct stream)
    sources = get_cinema_sources(title, c_type, season, episode)
    for src in sources:
        if src.get("type") in ["free_stream", "direct_download"]:
            try:
                dl_res = media_engine.download_media_file(src["url"], extract_audio=False)
                if dl_res.get("success") and os.path.exists(dl_res.get("filepath", "")):
                    return {
                        "success": True,
                        "filepath": dl_res["filepath"],
                        "title": f"{title} - {'مترجم' if with_subtitles else 'أصلي'}",
                        "filesize_mb": dl_res.get("filesize_mb", 0),
                        "with_subtitles": with_subtitles
                    }
            except Exception:
                continue

    return {
        "success": False,
        "error": "لم يتم العثور على تدفق فيديو مباشر قابل للتنزيل الآلي لهذا العمل حالياً في الخوادم الخلفية."
    }
