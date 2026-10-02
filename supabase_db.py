# -*- coding: utf-8 -*-
"""
supabase_db.py — الوسيط الموحد لإدارة قاعدة بيانات Supabase السحابية (PostgreSQL).
يعتمد على PostgREST REST API عبر مكتبة requests السريعة والخفيفة جداً (<5MB RAM).
يدعم القراءة والكتابة اللحظية مع الحفاظ على التوافق الخلفي التام.
"""

import os
import json
import logging
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

def _load_env():
    """تحميل المتغيرات البيئية من ملف .env تلقائياً إن وجد في مسار العمل."""
    env_paths = [
        ".env",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        r"C:\s\.env"
    ]
    for ep in env_paths:
        if os.path.exists(ep):
            try:
                with open(ep, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip().strip("'\"")
                            if k not in os.environ:
                                os.environ[k] = v
            except Exception:
                pass

_load_env()

# استخراج إعدادات Supabase من المتغيرات البيئية
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or os.getenv("SUPABASE_ANON_KEY", "")

def is_configured() -> bool:
    """التحقق من توفر رابط ومفتاح Supabase في المتغيرات البيئية."""
    global SUPABASE_URL, SUPABASE_KEY
    if not (SUPABASE_URL and SUPABASE_KEY):
        _load_env()
        SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
        SUPABASE_KEY = os.getenv("SUPABASE_KEY", "") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "") or os.getenv("SUPABASE_ANON_KEY", "")
    return bool(SUPABASE_URL and SUPABASE_KEY)

def _get_headers() -> Dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

def _request(method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, data: Optional[Any] = None) -> Optional[Any]:
    """تنفيذ طلب مباشر لـ PostgREST في Supabase."""
    if not is_configured():
        return None
    url = f"{SUPABASE_URL}/rest/v1/{endpoint}"
    try:
        resp = requests.request(
            method=method,
            url=url,
            headers=_get_headers(),
            params=params,
            json=data,
            timeout=15
        )
        if resp.status_code in (200, 201):
            return resp.json()
        elif resp.status_code == 204:
            return True
        else:
            logger.warning(f"[Supabase] {method} {endpoint} -> HTTP {resp.status_code}: {resp.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"[Supabase] Request failed: {e}")
        return None

# ==============================================================================
# 1. إدارة الروايات (Novels)
# ==============================================================================

def upsert_novel(novel_id: int, title: str, original_url: str = "", domain: str = "", total_chapters: int = 0, config: Optional[Dict] = None) -> bool:
    """إضافة أو تحديث بيانات رواية في Supabase."""
    payload = {
        "id": novel_id,
        "title": title,
        "original_url": original_url,
        "domain": domain,
        "total_chapters": total_chapters,
        "config": config or {},
        "updated_at": datetime.utcnow().isoformat()
    }
    headers = _get_headers()
    headers["Prefer"] = "resolution=merge-duplicates"
    try:
        resp = requests.post(f"{SUPABASE_URL}/rest/v1/novels", headers=headers, json=payload, timeout=12)
        return resp.status_code in (200, 201, 204)
    except Exception as e:
        logger.error(f"[Supabase] Error upserting novel: {e}")
        return False

def get_novel(novel_id: int) -> Optional[Dict[str, Any]]:
    """جلب بيانات رواية عبر المعرف."""
    res = _request("GET", "novels", params={"id": f"eq.{novel_id}", "limit": 1})
    return res[0] if res and len(res) > 0 else None

def get_all_novels() -> List[Dict[str, Any]]:
    """جلب كافة الروايات المسجلة."""
    res = _request("GET", "novels", params={"order": "id.asc"})
    return res or []

# ==============================================================================
# 2. إدارة الفصول (Chapters)
# ==============================================================================

def save_chapter(
    novel_id: int,
    chapter_number: int,
    title: str = "",
    url: str = "",
    content: str = "",
    status: str = "مؤرشف"
) -> bool:
    """حفظ أو تحديث متن فصل كامل في Supabase."""
    now_iso = datetime.utcnow().isoformat()
    payload = {
        "novel_id": novel_id,
        "chapter_number": chapter_number,
        "title": title or f"الفصل {chapter_number}",
        "url": url,
        "content": content,
        "status": status,
        "downloaded_at": now_iso,
        "updated_at": now_iso
    }
    headers = _get_headers()
    headers["Prefer"] = "resolution=merge-duplicates"
    try:
        resp = requests.post(f"{SUPABASE_URL}/rest/v1/chapters", headers=headers, json=payload, timeout=15)
        return resp.status_code in (200, 201, 204)
    except Exception as e:
        logger.error(f"[Supabase] Error saving chapter {chapter_number}: {e}")
        return False

def get_chapter(novel_id: int, chapter_number: int) -> Optional[Dict[str, Any]]:
    """جلب فصل محدد مع المتن الكامل."""
    res = _request("GET", "chapters", params={
        "novel_id": f"eq.{novel_id}",
        "chapter_number": f"eq.{chapter_number}",
        "limit": 1
    })
    return res[0] if res and len(res) > 0 else None

def get_chapter_by_novel_name(novel_name: str, chapter_number: int) -> Optional[Dict[str, Any]]:
    """جلب فصل بالاسم ورقم الفصل (عبر الربط مع جدول الروايات)."""
    if not is_configured():
        return None
    # أولاً البحث عن الرواية
    novs = _request("GET", "novels", params={"title": f"ilike.*{novel_name.strip()}*", "limit": 1})
    if not novs:
        return None
    nid = novs[0]["id"]
    return get_chapter(nid, chapter_number)

def get_novel_stats(novel_id: int) -> Dict[str, Any]:
    """إحصائيات سريعة للفصول المحملة والمفقودة من Supabase."""
    res = _request("GET", "chapters", params={
        "novel_id": f"eq.{novel_id}",
        "select": "chapter_number,status,content",
        "order": "chapter_number.asc"
    })
    if not res:
        return {"downloaded": 0, "total": 0, "max_chapter": 0}

    downloaded = sum(1 for c in res if c.get("status") in ("downloaded", "translated", "streamed"))
    nums = [c["chapter_number"] for c in res]
    max_ch = max(nums) if nums else 0
    return {
        "downloaded": downloaded,
        "total": len(res),
        "max_chapter": max_ch
    }

# ==============================================================================
# 3. إدارة الجدولة وطابور النشر (Syndication Schedules)
# ==============================================================================

def get_pending_schedules(limit: int = 15) -> List[Dict[str, Any]]:
    """جلب الفصول المجدولة المستحقة للنشر الآن أو سابقاً ولم تنشر بعد."""
    now_iso = datetime.utcnow().isoformat()
    res = _request("GET", "syndicated_chapter_schedules", params={
        "status": "eq.PENDING",
        "scheduled_time": f"lte.{now_iso}",
        "order": "scheduled_time.asc",
        "limit": limit
    })
    return res or []

def get_next_upcoming_schedule() -> Optional[Dict[str, Any]]:
    """جلب أقرب موعد نشر قادم في المستقبل للحارس الليلي (Google Apps Script)."""
    res = _request("GET", "syndicated_chapter_schedules", params={
        "status": "eq.PENDING",
        "order": "scheduled_time.asc",
        "limit": 1
    })
    return res[0] if res and len(res) > 0 else None

def add_schedule_item(novel_name: str, chapter_num: int, scheduled_time: str, platform: str = "all") -> bool:
    """إضافة موعد نشر مجدول جديد."""
    payload = {
        "novel_name": novel_name,
        "chapter_num": chapter_num,
        "platform": platform,
        "scheduled_time": scheduled_time,
        "status": "PENDING"
    }
    headers = _get_headers()
    headers["Prefer"] = "resolution=merge-duplicates"
    try:
        resp = requests.post(f"{SUPABASE_URL}/rest/v1/syndicated_chapter_schedules", headers=headers, json=payload, timeout=10)
        return resp.status_code in (200, 201, 204)
    except Exception as e:
        logger.error(f"[Supabase] Add schedule error: {e}")
        return False

def mark_schedule_published(schedule_id: int, post_url: str = "") -> bool:
    """تحديث حالة الفصل المجدول إلى منشور بنجاح."""
    headers = _get_headers()
    payload = {
        "status": "PUBLISHED",
        "published_at": datetime.utcnow().isoformat(),
        "published_url": post_url
    }
    try:
        resp = requests.patch(
            f"{SUPABASE_URL}/rest/v1/syndicated_chapter_schedules?id=eq.{schedule_id}",
            headers=headers,
            json=payload,
            timeout=10
        )
        return resp.status_code in (200, 204)
    except Exception as e:
        logger.error(f"[Supabase] Update schedule error: {e}")
        return False

def mark_schedule_failed(schedule_id: int, error_msg: str) -> bool:
    """تسجيل فشل نشر فصل مجدول."""
    headers = _get_headers()
    payload = {
        "status": "FAILED",
        "error_message": str(error_msg)[:500]
    }
    try:
        resp = requests.patch(
            f"{SUPABASE_URL}/rest/v1/syndicated_chapter_schedules?id=eq.{schedule_id}",
            headers=headers,
            json=payload,
            timeout=10
        )
        return resp.status_code in (200, 204)
    except Exception as e:
        logger.error(f"[Supabase] Fail schedule error: {e}")
        return False

# ==============================================================================
# 4. الروايات المربوطة والسجلات (Syndicated Novels & Logs)
# ==============================================================================

def get_all_syndicated_novels() -> List[Dict[str, Any]]:
    """جلب إعدادات نشر الروايات."""
    res = _request("GET", "syndicated_novels", params={"order": "id.asc"})
    return res or []

def upsert_syndicated_novel(data: Dict[str, Any]) -> bool:
    """إضافة أو تحديث إعدادات رواية للنشر."""
    headers = _get_headers()
    headers["Prefer"] = "resolution=merge-duplicates"
    data["updated_at"] = datetime.utcnow().isoformat()
    try:
        resp = requests.post(f"{SUPABASE_URL}/rest/v1/syndicated_novels", headers=headers, json=data, timeout=10)
        return resp.status_code in (200, 201, 204)
    except Exception as e:
        logger.error(f"[Supabase] Error upserting syndicated novel: {e}")
        return False

def log_syndication(level: str, module: str, message: str, details: Optional[Dict] = None):
    """حفظ سجل نشر في Supabase."""
    if not is_configured():
        return
    payload = {
        "level": level.upper(),
        "module": module,
        "message": message,
        "details": details or {}
    }
    try:
        headers = _get_headers()
        requests.post(f"{SUPABASE_URL}/rest/v1/syndication_logs", headers=headers, json=payload, timeout=5)
    except Exception:
        pass
