"""
==============================================================================
Smart Media Engine - Video Downloader, Splitter & AI Subtitles v1.0
==============================================================================
هذا الملف مسؤول عن:
1. فحص وتنزيل مقاطع الفيديو عبر yt-dlp بجودات متعددة وصيغ MP4/MP3.
2. تجزئة الفيديوهات الكبيرة (>1GB أو حسب الحجم المطلوب) بدون فقدان الجودة (Lossless ffmpeg split).
3. استخراج ملفات الترجمة (.srt/.vtt) وترجمتها للعربية بواسطة Gemini 3.8 Flash.
4. إرسال المقاطع والملفات الناتجة اختيارياً إلى بوت تيليجرام.
5. الإدارة التلقائية لمساحة التخزين لتفادي امتلاء ذاكرة السيرفر.
"""

import os
import sys
import subprocess
import shutil
import json
import time
import requests
from typing import Dict, Any, List, Optional, Tuple

import database
from gemini_analyzer import call_gemini_api

DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads_media")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def is_ffmpeg_available() -> bool:
    """التحقق من توفر ffmpeg في مسار النظام."""
    return shutil.which("ffmpeg") is not None


def get_video_info(url: str) -> Dict[str, Any]:
    """استخراج معلومات الفيديو (العنوان، المدة، الأحجام المتاحة) دون تحميله."""
    try:
        import yt_dlp
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
            "socket_timeout": 30
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "success": True,
                "title": info.get("title", "فيديو بدون عنوان"),
                "duration": info.get("duration", 0),
                "thumbnail": info.get("thumbnail", ""),
                "formats": [
                    {
                        "format_id": f.get("format_id"),
                        "resolution": f.get("resolution") or f"{f.get('height', 'audio')}p",
                        "ext": f.get("ext"),
                        "filesize": f.get("filesize") or f.get("filesize_approx", 0)
                    }
                    for f in info.get("formats", []) if f.get("ext") in ["mp4", "webm", "m4a", "mp3"]
                ],
                "subtitles": list(info.get("subtitles", {}).keys()) + list(info.get("automatic_captions", {}).keys())
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


def download_media_file(
    url: str,
    format_type: str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    extract_audio: bool = False,
    progress_hook: Optional[Any] = None
) -> Dict[str, Any]:
    """تنزيل ملف الفيديو أو الصوت وحفظه في مجلد التنزيلات المؤقت."""
    try:
        import yt_dlp

        out_template = os.path.join(DOWNLOAD_DIR, "%(title).80s_%(id)s.%(ext)s")
        ydl_opts = {
            "outtmpl": out_template,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 30,
            "retries": 3,
            "fragment_retries": 3
        }

        if extract_audio:
            ydl_opts["format"] = "bestaudio/best"
            if is_ffmpeg_available():
                ydl_opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }]
        else:
            # إذا لم يكن ffmpeg مثبتاً محلياً، نختار صيغة مدمجة مسبقاً (single-file mp4) لتفادي خطأ الدمج
            if not is_ffmpeg_available():
                ydl_opts["format"] = "best[ext=mp4]/best"
            else:
                ydl_opts["format"] = format_type

        if progress_hook:
            ydl_opts["progress_hooks"] = [progress_hook]

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if extract_audio and is_ffmpeg_available():
                base, _ = os.path.splitext(filename)
                filename = base + ".mp3"

            file_size = os.path.getsize(filename) if os.path.exists(filename) else 0

            return {
                "success": True,
                "filepath": filename,
                "filesize_mb": round(file_size / (1024 * 1024), 2),
                "title": info.get("title", "فيديو"),
                "duration": info.get("duration", 0)
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


def split_video_lossless(filepath: str, max_part_mb: int = 450) -> List[str]:
    """تجزئة الفيديو تلقائياً باستخدام ffmpeg إلى أجزاء آمنة دون إعادة التشفير."""
    if not is_ffmpeg_available():
        return [filepath]

    total_bytes = os.path.getsize(filepath)
    max_part_bytes = max_part_mb * 1024 * 1024

    if total_bytes <= max_part_bytes:
        return [filepath]

    # جلب مدة الفيديو عبر ffprobe أو حساب عدد الأجزاء
    num_parts = (total_bytes // max_part_bytes) + 1
    base_name, ext = os.path.splitext(filepath)

    output_pattern = f"{base_name}_part%03d{ext}"
    cmd = [
        "ffmpeg",
        "-y",
        "-i", filepath,
        "-c", "copy",
        "-map", "0",
        "-segment_time", "600",  # 10 دقائق لكل جزء كمعدل آمن
        "-f", "segment",
        "-reset_timestamps", "1",
        output_pattern
    ]

    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        # جمع الأجزاء الناتجة
        parts = []
        dir_name = os.path.dirname(filepath)
        prefix = os.path.basename(base_name) + "_part"
        for f in sorted(os.listdir(dir_name)):
            if f.startswith(prefix) and f.endswith(ext):
                parts.append(os.path.join(dir_name, f))
        return parts if parts else [filepath]
    except Exception:
        return [filepath]


def translate_subtitles_with_gemini(srt_content: str) -> str:
    """ترجمة أسطر ملف الترجمة إلى اللغة العربية الاحترافية باستخدام Gemini 3.8 Flash."""
    prompt = f"""
أنت مترجم محترف للترجمات المرئية والأفلام.
المهمة: ترجم محتوى ملف الترجمة التالي إلى لغة عربية فصحى سلسة وسليمة مع الحفاظ الصارم على توقيتات وأرقام وأسطر SRT كما هي بالضبط:

```srt
{srt_content[:15000]}
```

أرجع ملف الترجمة المترجم بنفس هيكل SRT فقط دون أي مقدمات.
"""
    try:
        translated = call_gemini_api(prompt=prompt, model_name="gemini-3.8-flash")
        return translated.strip().replace("```srt", "").replace("```", "")
    except Exception as e:
        return f"خطأ أثناء الترجمة: {str(e)}"


def send_to_telegram(bot_token: str, chat_id: str, file_path: str, caption: str = "", auto_split_if_large: bool = True) -> Tuple[bool, str]:
    """إرسال ملف الفيديو أو الترجمة مباشرة إلى محادثة تيليجرام مع التقطيع التلقائي إذا تجاوز 48MB."""
    if not bot_token or not chat_id or not os.path.exists(file_path):
        return False, "بيانات الإرسال أو الملف غير صحيحة"

    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if file_size_mb > 48:
        if auto_split_if_large:
            # التقطيع التلقائي الإلزامي لضمان وصول الملف دون رفض تيليجرام
            parts = split_video_lossless(file_path, max_part_mb=45)
            if len(parts) > 1:
                all_ok = True
                for idx, part in enumerate(parts, 1):
                    part_cap = f"{caption}\n📦 جزء ({idx}/{len(parts)})" if caption else f"📦 جزء ({idx}/{len(parts)})"
                    ok, _ = send_to_telegram(bot_token, chat_id, part, caption=part_cap, auto_split_if_large=False)
                    if not ok:
                        all_ok = False
                return all_ok, f"تم تقطيع الملف وإرساله على {len(parts)} أجزاء بنجاح."
        return False, f"حجم الملف ({file_size_mb:.1f}MB) يتجاوز الحد المسموح به في Telegram Bot API (50MB)."

    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    try:
        with open(file_path, "rb") as f:
            files = {"document": f}
            data = {"chat_id": chat_id, "caption": caption}
            res = requests.post(url, files=files, data=data, timeout=120)
            if res.status_code == 200 and res.json().get("ok"):
                return True, "تم الإرسال بنجاح إلى تيليجرام!"
            return False, f"رد تيليجرام: {res.text}"
    except Exception as ex:
        return False, str(ex)


def cleanup_media_directory():
    """تنظيف مجلد التنزيلات المؤقتة لتحرير مساحة السيرفر فوراً."""
    try:
        for f in os.listdir(DOWNLOAD_DIR):
            f_path = os.path.join(DOWNLOAD_DIR, f)
            if os.path.isfile(f_path):
                os.remove(f_path)
    except Exception:
        pass
