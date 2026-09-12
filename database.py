# -*- coding: utf-8 -*-
import json
import sqlite3
import datetime
from typing import List, Dict, Optional, Any, Tuple
import os
import re

DB_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "novel_scraper.db")


def get_connection(db_path: str = DB_FILE_PATH) -> sqlite3.Connection:
    """إنشاء اتصال مع قاعدة بيانات SQLite مع تمكين وضع WAL لدعم الخيوط المتوازية."""
    conn = sqlite3.connect(db_path, timeout=60.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 60000;")
    return conn


def init_db(db_path: str = DB_FILE_PATH):
    """تهيئة وإنشاء جداول قاعدة البيانات إذا لم تكن موجودة."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. جدول تخزين إعدادات ومحددات CSS لكل دومين
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS domains_config (
                domain TEXT PRIMARY KEY,
                toc_link_selector TEXT NOT NULL,
                chapter_title_selector TEXT NOT NULL,
                chapter_content_selector TEXT NOT NULL,
                purge_selectors TEXT NOT NULL, -- مخزن بتنسيق JSON List
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 2. جدول إعدادات التطبيق والمفاتيح
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 3. جدول الروايات
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS novels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                toc_url TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                total_chapters INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 3. جدول فصول الروايات مع دعم حالة التنزيل والمحتوى
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chapters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                novel_id INTEGER NOT NULL,
                chapter_number INTEGER NOT NULL,
                url TEXT NOT NULL,
                title TEXT,
                content TEXT,
                status TEXT DEFAULT 'pending', -- 'pending', 'downloaded', 'failed'
                error_message TEXT,
                downloaded_at TIMESTAMP,
                FOREIGN KEY (novel_id) REFERENCES novels (id) ON DELETE CASCADE,
                UNIQUE (novel_id, chapter_number)
            );
        """)

        # إنشاء فهارس لتحسين سرعة الاستعلام
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chapters_novel_status ON chapters(novel_id, status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_chapters_novel_num ON chapters(novel_id, chapter_number);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_novels_toc_url ON novels(toc_url);")

        # إدراج إعدادات مسبقة ومعتمدة لأشهر النطاقات (Preset Domains)
        presets = [
            (
                "botitranslation.com",
                "a[href*='/chapter/']",
                ".chapter-title, .title, title",
                ".chapter-content",
                json.dumps(["script", "style", "noscript", "button", ".ad", ".ads", "nav", "header", "footer", ".comments"], ensure_ascii=False),
                "موقع بوتي للترجمة (Cloudflare / SPA) - متوافق مع جسر CDP"
            ),
            (
                "69shuba.com",
                "div.catalog ul li a, .mybox ul li a, div.txtnav ul li a",
                "h1.hide720, h1",
                "div.txtnav, div.content",
                json.dumps(["script", "style", "noscript", ".ad", "div.bottom-ad"], ensure_ascii=False),
                "موقع 69شوبا الصيني الشهير"
            ),
            (
                "69shu.me",
                "div.catalog ul li a, .mybox ul li a, div.txtnav ul li a",
                "h1.hide720, h1",
                "div.txtnav, div.content",
                json.dumps(["script", "style", "noscript", ".ad", "div.bottom-ad"], ensure_ascii=False),
                "مرآة بديلة لموقع 69شوبا"
            )
        ]
        for p_dom, p_toc, p_title, p_cont, p_purge, p_notes in presets:
            cursor.execute("""
                INSERT OR IGNORE INTO domains_config (domain, toc_link_selector, chapter_title_selector, chapter_content_selector, purge_selectors, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (p_dom, p_toc, p_title, p_cont, p_purge, p_notes))

        conn.commit()


# ==============================================================================
# تنسيق وضبط رأس الفصل المعياري (Standard Chapter Header Formatting)
# ==============================================================================

def format_chapter_with_header(chapter_number: int, title: Optional[str], content: str) -> str:
    """
    وضع عنوان الفصل المستخرج من المصدر في بداية نص المحتوى بلغته الأصلية،
    مفصولاً بسطرين فارغين عن المتن، دون فرض أي بادئة عربية على النصوص الأجنبية.
    """
    raw_title = (title or "").strip()
    clean_body = (content or "").strip()

    # تنظيف أي بادئة عربية مصطنعة أضيفت سابقاً إذا كان العنوان الأصلي أجنبياً
    if raw_title and not re.search(r'[\u0600-\u06FF]', raw_title):
        clean_body = re.sub(r'^الفصل\s*\d+[\s:ـ\-]*.*?\n+', '', clean_body).strip()

    if not raw_title:
        # تحديد لغة المتن لاختيار بديل مناسب
        if re.search(r'[a-zA-Z]', clean_body):
            raw_title = f"Chapter {chapter_number}"
        elif re.search(r'[\u4e00-\u9fff]', clean_body):
            raw_title = f"第{chapter_number}章"
        else:
            raw_title = f"الفصل {chapter_number}"

    if not clean_body:
        return raw_title

    # إذا كان المتن يبدأ بالفعل بالعنوان الأصلي
    if clean_body.startswith(raw_title):
        return clean_body

    lines = clean_body.split('\n')
    first_line = lines[0].strip()
    if first_line.lower() == raw_title.lower():
        return clean_body

    # إذا كان السطر الأول تكراراً مشابهاً للعنوان
    if re.match(r'^(?:chapter|chap|ch\.?|第|الفصل)\s*' + str(chapter_number) + r'\b', first_line, re.IGNORECASE):
        clean_body = "\n".join(lines[1:]).strip()

    return f"{raw_title}\n\n{clean_body}"


# ==============================================================================
# إدارة إعدادات الدومينات (Domain Config Management)
# ==============================================================================

def get_domain_config(domain: str, db_path: str = DB_FILE_PATH) -> Optional[Dict[str, Any]]:
    """جلب إعدادات ومحددات موقع معين من قاعدة البيانات."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM domains_config WHERE domain = ?", (domain.lower(),))
        row = cursor.fetchone()
        if not row:
            return None
        
        config = dict(row)
        try:
            config["purge_selectors"] = json.loads(config["purge_selectors"])
        except Exception:
            config["purge_selectors"] = []
        return config


def save_domain_config(
    domain: str,
    toc_link_selector: str,
    chapter_title_selector: str,
    chapter_content_selector: str,
    purge_selectors: List[str],
    notes: Optional[str] = None,
    db_path: str = DB_FILE_PATH
) -> bool:
    """حفظ أو تحديث إعدادات ومحددات دومين في قاعدة البيانات."""
    purge_json = json.dumps(purge_selectors, ensure_ascii=False)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO domains_config (domain, toc_link_selector, chapter_title_selector, chapter_content_selector, purge_selectors, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(domain) DO UPDATE SET
                toc_link_selector = excluded.toc_link_selector,
                chapter_title_selector = excluded.chapter_title_selector,
                chapter_content_selector = excluded.chapter_content_selector,
                purge_selectors = excluded.purge_selectors,
                notes = excluded.notes,
                updated_at = excluded.updated_at;
        """, (domain.lower(), toc_link_selector, chapter_title_selector, chapter_content_selector, purge_json, notes, now))
        conn.commit()
    return True


def get_all_domains_config(db_path: str = DB_FILE_PATH) -> List[Dict[str, Any]]:
    """جلب قائمة بجميع الدومينات المخزنة في النظام."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM domains_config ORDER BY updated_at DESC;")
        rows = cursor.fetchall()
        result = []
        for r in rows:
            item = dict(r)
            try:
                item["purge_selectors"] = json.loads(item["purge_selectors"])
            except Exception:
                item["purge_selectors"] = []
            result.append(item)
        return result


def delete_domain_config(domain: str, db_path: str = DB_FILE_PATH) -> bool:
    """حذف إعدادات دومين معين من قاعدة البيانات."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM domains_config WHERE domain = ?", (domain.lower(),))
        conn.commit()
    return True


# ==============================================================================
# إدارة الروايات والفهارس (Novels & Chapters Management)
# ==============================================================================

def get_or_create_novel(
    toc_url: str,
    title: str = "رواية جديدة",
    domain: str = "",
    db_path: str = DB_FILE_PATH
) -> Dict[str, Any]:
    """إنشاء أو جلب سجل الرواية بناءً على رابط الفهرس TOC URL مع تطبيع الروابط ودعم www."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    clean_url = toc_url.strip().rstrip('/')
    alt_url = clean_url.replace("://www.", "://") if "://www." in clean_url else clean_url.replace("://", "://www.")
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM novels WHERE toc_url IN (?, ?, ?, ?) ORDER BY id ASC LIMIT 1",
            (toc_url, clean_url, alt_url, clean_url + "/")
        )
        row = cursor.fetchone()
        
        # إذا لم يُعثر على الرابط، ابحث بالعنوان الدقيق لتجنب تكرار الرواية
        if not row and title and title != "رواية جديدة":
            cursor.execute("SELECT * FROM novels WHERE LOWER(TRIM(title)) = LOWER(TRIM(?)) ORDER BY id ASC LIMIT 1", (title,))
            row = cursor.fetchone()

        if row:
            if title and title != "رواية جديدة" and row["title"] != title:
                cursor.execute("UPDATE novels SET title = ?, updated_at = ? WHERE id = ?", (title, now, row["id"]))
                conn.commit()
                cursor.execute("SELECT * FROM novels WHERE id = ?", (row["id"],))
                row = cursor.fetchone()
            return dict(row)
        
        # إنشاء سجل جديد
        cursor.execute("""
            INSERT INTO novels (domain, toc_url, title, total_chapters, created_at, updated_at)
            VALUES (?, ?, ?, 0, ?, ?);
        """, (domain.lower(), toc_url, title, now, now))
        novel_id = cursor.lastrowid
        conn.commit()
        
        cursor.execute("SELECT * FROM novels WHERE id = ?", (novel_id,))
        return dict(cursor.fetchone())


def get_novel_by_id(novel_id: int, db_path: str = DB_FILE_PATH) -> Optional[Dict[str, Any]]:
    """جلب بيانات الرواية بواسطة المعرف ID."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM novels WHERE id = ?", (novel_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_novel_by_title(title: str, db_path: str = DB_FILE_PATH) -> Optional[Dict[str, Any]]:
    """جلب بيانات الرواية بالبحث في العنوان (مطابقة دقيقة أو تقريبية)."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        # محاولة مطابقة دقيقة أولاً
        cursor.execute("SELECT * FROM novels WHERE LOWER(TRIM(title)) = LOWER(TRIM(?)) ORDER BY id DESC LIMIT 1;", (title,))
        row = cursor.fetchone()
        if not row:
            # مطابقة جزئية
            cursor.execute("SELECT * FROM novels WHERE LOWER(title) LIKE LOWER(?) ORDER BY id DESC LIMIT 1;", (f"%{title.strip()}%",))
            row = cursor.fetchone()
        return dict(row) if row else None


def get_all_novels(db_path: str = DB_FILE_PATH) -> List[Dict[str, Any]]:
    """جلب كافة الروايات المسجلة في النظام."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM novels ORDER BY updated_at DESC;")
        return [dict(r) for r in cursor.fetchall()]


def update_novel_title(novel_id: int, new_title: str, db_path: str = DB_FILE_PATH) -> bool:
    """تحديث عنوان الرواية في قاعدة البيانات."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE novels SET title = ?, updated_at = ? WHERE id = ?", (new_title.strip(), now, novel_id))
        conn.commit()
    return True


def sync_chapter_manifest(
    novel_id: int,
    chapter_list: List[Dict[str, Any]],
    db_path: str = DB_FILE_PATH
) -> int:
    """
    تحديث قائمة فصول الرواية المستخرجة من صفحة الفهرس.
    يتم الاحتفاظ بالفصول التي تم تنزيلها مسبقاً، وإضافة الفصول الجديدة بحالة 'pending'.
    """
    total = len(chapter_list)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        for idx, item in enumerate(chapter_list, start=1):
            ch_num = item.get("chapter_number", idx)
            ch_url = item.get("url", "")
            ch_title = item.get("title", f"الفصل {ch_num}")

            # إدخال الفصل إذا لم يكن موجوداً، أو تحديث الرابط والعنوان مع الحفاظ على المحتوى وحالة التنزيل
            cursor.execute("""
                INSERT INTO chapters (novel_id, chapter_number, url, title, status)
                VALUES (?, ?, ?, ?, 'pending')
                ON CONFLICT(novel_id, chapter_number) DO UPDATE SET
                    url = excluded.url,
                    title = CASE WHEN chapters.status = 'downloaded' AND chapters.title IS NOT NULL AND chapters.title != '' 
                                 THEN chapters.title 
                                 ELSE excluded.title END;
            """, (novel_id, ch_num, ch_url, ch_title))
        
        # تحديث إجمالي الفصول للرواية
        cursor.execute("UPDATE novels SET total_chapters = ?, updated_at = ? WHERE id = ?;", (total, now, novel_id))
        conn.commit()
        return total


def save_chapter_content(
    novel_id: int,
    chapter_number: int,
    title: str,
    content: str,
    status: str = "downloaded",
    error_message: Optional[str] = None,
    db_path: str = DB_FILE_PATH
) -> bool:
    """حفظ محتوى الفصل الذي تم سحبه وتحديث حالته فوراً في قاعدة البيانات."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") if status == "downloaded" else None
    
    # ضمان تطبيق صيغة (الفصل رقمه : العنوان ثم المحتوى) عند اكتمال تنزيل المحتوى
    if content and status == "downloaded":
        content = format_chapter_with_header(chapter_number, title, content)

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE chapters
            SET title = ?,
                content = ?,
                status = ?,
                error_message = ?,
                downloaded_at = ?
            WHERE novel_id = ? AND chapter_number = ?;
        """, (title, content, status, error_message, now, novel_id, chapter_number))
        conn.commit()
    return True


def get_chapters(
    novel_id: int,
    from_chapter: Optional[int] = None,
    to_chapter: Optional[int] = None,
    status: Optional[str] = None,
    chapter_numbers: Optional[List[int]] = None,
    db_path: str = DB_FILE_PATH
) -> List[Dict[str, Any]]:
    """جلب قائمة الفصول لرواية معينة بناءً على النطاق والحالة أو قائمة أرقام مخصصة."""
    query = "SELECT * FROM chapters WHERE novel_id = ?"
    params: List[Any] = [novel_id]

    if chapter_numbers:
        placeholders = ",".join(["?"] * len(chapter_numbers))
        query += f" AND chapter_number IN ({placeholders})"
        params.extend(chapter_numbers)
    else:
        if from_chapter is not None:
            query += " AND chapter_number >= ?"
            params.append(from_chapter)
        if to_chapter is not None:
            query += " AND chapter_number <= ?"
            params.append(to_chapter)

    if status is not None:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY chapter_number ASC;"

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(r) for r in cursor.fetchall()]


def get_novel_stats(novel_id: int, db_path: str = DB_FILE_PATH) -> Dict[str, int]:
    """حساب إحصائيات الفصول (إجمالي، تم التنزيل، معلق، فاشل)."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'downloaded' THEN 1 ELSE 0 END) AS downloaded,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed
            FROM chapters
            WHERE novel_id = ?;
        """, (novel_id,))
        row = cursor.fetchone()
        if not row:
            return {"total": 0, "downloaded": 0, "pending": 0, "failed": 0}
        
        return {
            "total": row["total"] or 0,
            "downloaded": row["downloaded"] or 0,
            "pending": row["pending"] or 0,
            "failed": row["failed"] or 0
        }


def clear_novel_chapters_data(novel_id: int, db_path: str = DB_FILE_PATH) -> bool:
    """إعادة تعيين محتوى الفصول وحالتها للرواية لجعلها معلقة (pending) لإعادة السحب."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE chapters
            SET content = NULL,
                status = 'pending',
                error_message = NULL,
                downloaded_at = NULL
            WHERE novel_id = ?;
        """, (novel_id,))
        conn.commit()
    return True


def delete_novel(novel_id: int, db_path: str = DB_FILE_PATH) -> bool:
    """حذف الرواية وجميع فصولها بالكامل من قاعدة البيانات."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM novels WHERE id = ?;", (novel_id,))
        conn.commit()
    return True


# ==============================================================================
# توليد ملف التصدير المنظم (Structured Export Generator)
# ==============================================================================

def export_novel_to_text(
    novel_id: int,
    from_chapter: Optional[int] = None,
    to_chapter: Optional[int] = None,
    db_path: str = DB_FILE_PATH
) -> Tuple[str, int]:
    """
    تجميع الفصول المنزلة بصيغة النص النظيف المطلوب بدقة:
    ===CHAPTER_START===
    TITLE: [Chapter Number] : [Chapter Title]
    CONTENT:
    [Clean text paragraphs separated by double newlines]
    ===CHAPTER_END===
    
    ترجع النص الكامل وعدد الفصول التي تم تصديرها.
    """
    chapters = get_chapters(novel_id, from_chapter=from_chapter, to_chapter=to_chapter, status="downloaded", db_path=db_path)
    
    if not chapters:
        return "", 0

    output_blocks = []
    for ch in chapters:
        ch_num = ch["chapter_number"]
        ch_title = (ch["title"] or f"الفصل {ch_num}").strip()
        ch_content = (ch["content"] or "").strip()
        ch_content = format_chapter_with_header(ch_num, ch_title, ch_content)
        
        block = (
            f"===CHAPTER_START===\n"
            f"TITLE: {ch_num} : {ch_title}\n"
            f"CONTENT:\n"
            f"{ch_content}\n"
            f"===CHAPTER_END==="
        )
        output_blocks.append(block)

    full_text = "\n\n".join(output_blocks)
    return full_text, len(chapters)


# ==============================================================================
# إدارة إعدادات التطبيق والمفاتيح (App Settings)
# ==============================================================================

def get_setting(key: str, default: str = "", db_path: str = DB_FILE_PATH) -> str:
    """استرجاع قيمة إعداد معين من قاعدة البيانات."""
    try:
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else default
    except Exception:
        return default


def save_setting(key: str, value: str, db_path: str = DB_FILE_PATH) -> bool:
    """حفظ أو تحديث إعداد في قاعدة البيانات."""
    try:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with get_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at;
            """, (key, value, now))
            conn.commit()
            return True
    except Exception:
        return False


# تهيئة الجداول تلقائياً عند استيراد الوحدة
init_db()


def clear_single_chapter_content(novel_id: int, chapter_number: int, db_path: str = DB_FILE_PATH) -> bool:
    """تفريغ نص فصل محدد من SQLite بعد تدفقه بنجاح إلى Google Sheet لتوفير المساحة."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE chapters 
            SET content = '', status = 'streamed'
            WHERE novel_id = ? AND chapter_number = ?
        """, (novel_id, chapter_number))
        conn.commit()
        return cursor.rowcount > 0


# ==============================================================================
# ⚡ دوال البحث الذكي وكشف الثغرات (Novel Query & Gap Detection)
# ==============================================================================

def find_novel_by_query(query_str: str, db_path: str = DB_FILE_PATH) -> Optional[Dict[str, Any]]:
    """البحث المرن عن الرواية بالاسم العربي أو الإنجليزي أو الصيني أو جزء من الرابط."""
    if not query_str:
        return None
    q = query_str.strip().lower()
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM novels;")
        rows = [dict(r) for r in cursor.fetchall()]
        
        # 1. تطابق مباشر
        for r in rows:
            t = (r.get("title") or "").lower()
            u = (r.get("toc_url") or "").lower()
            if q == t or q in t or t in q or q in u:
                return r
                
        # 2. تطابق الكلمات المفتاحية الشائعة
        if "severing" in q or "قطع" in q or "الروابط" in q or "ties" in q or "斷絕" in q:
            for r in rows:
                if "斷絕" in (r.get("title") or "") or "severing" in (r.get("toc_url") or "").lower():
                    return r
        if "mahayana" in q or "ماهايانا" in q or "reversal" in q or "انعكاس" in q:
            for r in rows:
                if "mahayana" in (r.get("title") or "").lower() or "mahayana" in (r.get("toc_url") or "").lower():
                    return r

        return rows[0] if len(rows) == 1 else None


def get_novel_gaps(novel_id: int, db_path: str = DB_FILE_PATH) -> Dict[str, Any]:
    """فحص واكتشاف ثغرات الفصول المفقودة أو المتعثرة للرواية بدقة."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT chapter_number, status, length(content) as content_len 
            FROM chapters 
            WHERE novel_id = ? 
            ORDER BY chapter_number ASC;
        """, (novel_id,))
        rows = cursor.fetchall()
        if not rows:
            return {"min": 0, "max": 0, "total_manifest": 0, "completed": 0, "failed": [], "gaps": [], "missing_count": 0}
            
        chap_nums = [r["chapter_number"] for r in rows]
        min_c = min(chap_nums)
        max_c = max(chap_nums)
        
        # الفصول التي تم سحبها بنجاح إما downloaded أو streamed
        completed_set = {
            r["chapter_number"] for r in rows 
            if r["status"] in ("downloaded", "streamed")
        }
        
        # الفصول الفاشلة
        failed_list = [r["chapter_number"] for r in rows if r["status"] == "failed"]
        
        # حساب الثغرات من min_c إلى max_c
        gaps = []
        for c in range(min_c, max_c + 1):
            if c not in completed_set:
                gaps.append(c)
                
        return {
            "min": min_c,
            "max": max_c,
            "total_manifest": len(rows),
            "completed": len(completed_set),
            "failed": failed_list,
            "gaps": gaps,
            "missing_count": len(gaps)
        }


# ==============================================================================
# 🔍 دوال مقارنة واستبدال الفصول المقتطعة (Truncation Comparison & Replacement)
# ==============================================================================

def compare_chapter_contents(
    original_content: str,
    downloaded_content: str,
    min_improvement_ratio: float = 1.15,
    min_valid_length: int = 3000
) -> Dict[str, Any]:
    """
    مقارنة دقيقة لمحتوى الفصلين بين الأصلي (المسحوب حديثاً) والمنزل (المخزن في قاعدة البيانات أو الشيت):
    - فحص نسبة الاختلاف وطول النصوص.
    - كشف الاقتطاع والتجزئة (Truncation Detection).
    - تقرير ما إذا كان يجب استبدال المحتوى المجتزئ بالنص الأكمل والأطول.
    """
    orig = (original_content or "").strip()
    down = (downloaded_content or "").strip()

    orig_len = len(orig)
    down_len = len(down)
    diff_len = orig_len - down_len
    ratio = (orig_len / down_len) if down_len > 0 else 999.0

    orig_words = len(orig.split())
    down_words = len(down.split())

    # حالة 1: المحتوى المنزّل فارغ أو شبه فارغ
    if down_len < 50:
        should_replace = orig_len >= 50
        reason = "المحتوى المنزّل فارغ أو غير صالح والأصلي يحتوي على نص"
        is_truncated = True

    # حالة 2: المحتوى المنزّل قصير ومقتطع بوضوح (أقل من الحد الآمن) بينما الأصلي سليم وكامل
    elif down_len < min_valid_length and orig_len >= min_valid_length:
        should_replace = True
        reason = f"المحتوى المنزّل مقتطع ومجتزأ ({down_len} حرفاً / {down_words} كلمة) بينما الأصلي كامل ({orig_len} حرفاً / {orig_words} كلمة)"
        is_truncated = True

    # حالة 3: المحتوى الأصلي أطول بشكل ملحوظ بنسبة تفوق معامل التحسين (مثلاً زيادة 15% أو أكثر)
    elif orig_len >= down_len * min_improvement_ratio and diff_len >= 300:
        should_replace = True
        percentage = round(((orig_len - down_len) / down_len) * 100, 1)
        reason = f"المحتوى الأصلي أطول بنسبة {percentage}% (زيادة {diff_len} حرفاً / {orig_words - down_words} كلمة)"
        is_truncated = True

    # حالة 4: المحتوى المنزّل أطول أو مساوٍ للأصلي
    else:
        should_replace = False
        reason = f"المحتوى المنزّل كافٍ ومتكامل ({down_len} حرفاً مقابل {orig_len} حرفاً للأصلي) - لا يتطلب استبدالاً"
        is_truncated = False

    return {
        "should_replace": should_replace,
        "is_truncated": is_truncated,
        "original_len": orig_len,
        "downloaded_len": down_len,
        "diff_len": diff_len,
        "ratio": round(ratio, 2),
        "original_words": orig_words,
        "downloaded_words": down_words,
        "reason": reason
    }


def compare_and_replace_chapter_content(
    novel_id: int,
    chapter_number: int,
    original_content: str,
    original_title: Optional[str] = None,
    original_url: Optional[str] = None,
    min_improvement_ratio: float = 1.15,
    min_valid_length: int = 3000,
    db_path: str = DB_FILE_PATH
) -> Dict[str, Any]:
    """
    مقارنة محتوى الفصل الأصلي مع الفصل المخزن في SQLite، واستبدال المحتوى القديم فوراً إذا كان مجتزأً أو إذا كان الجديد أكمل وأطول.
    """
    # ضمان تطبيق صيغة (الفصل رقمه : العنوان ثم المحتوى) على المحتوى المستخرج
    if original_content:
        original_content = format_chapter_with_header(chapter_number, original_title or "", original_content)

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, novel_id, chapter_number, title, content, status, url
            FROM chapters
            WHERE novel_id = ? AND chapter_number = ?;
        """, (novel_id, chapter_number))
        row = cursor.fetchone()

        if not row:
            # إذا لم يكن الفصل موجوداً، إنشاؤه وحفظه كفصل جديد
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            title = original_title or f"الفصل {chapter_number}"
            cursor.execute("""
                INSERT INTO chapters (novel_id, chapter_number, title, content, url, status, downloaded_at)
                VALUES (?, ?, ?, ?, ?, 'downloaded', ?);
            """, (novel_id, chapter_number, title, original_content, original_url or "", now))
            conn.commit()
            return {
                "replaced": True,
                "action": "inserted_new",
                "should_replace": True,
                "is_truncated": False,
                "original_len": len(original_content or ""),
                "downloaded_len": 0,
                "diff_len": len(original_content or ""),
                "ratio": 999.0,
                "reason": "تم إدراج الفصل لأول مرة في قاعدة البيانات"
            }

        existing_content = row["content"] or ""
        existing_title = row["title"] or f"الفصل {chapter_number}"

        comp = compare_chapter_contents(
            original_content=original_content,
            downloaded_content=existing_content,
            min_improvement_ratio=min_improvement_ratio,
            min_valid_length=min_valid_length
        )

        if comp["should_replace"]:
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            new_title = original_title.strip() if original_title and original_title.strip() else existing_title
            new_url = original_url if original_url else row["url"]

            cursor.execute("""
                UPDATE chapters
                SET title = ?,
                    content = ?,
                    url = COALESCE(?, url),
                    status = 'downloaded',
                    error_message = NULL,
                    downloaded_at = ?
                WHERE novel_id = ? AND chapter_number = ?;
            """, (new_title, original_content, new_url, now, novel_id, chapter_number))
            conn.commit()
            comp["replaced"] = True
            comp["action"] = "updated_replaced"
        else:
            comp["replaced"] = False
            comp["action"] = "kept_existing"

        return comp


def calculate_novel_length_stats(novel_id: int, db_path: str = DB_FILE_PATH) -> Dict[str, Any]:
    """
    حساب الإحصائيات الرياضية المتقدمة لأطوال فصول الرواية واكتشاف القيم المتطرفة الدنيا:
    - المتوسط الحسابي (Mean)
    - الانحراف المعياري (Std)
    - الوسيط (Median) والربيعيات (Q1, Q3, IQR)
    - حد القيمة المتطرفة الدنيا (Lower Extreme Outlier Threshold)
    """
    import math
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT length(content) as clen
            FROM chapters
            WHERE novel_id = ? 
              AND status IN ('downloaded', 'streamed')
              AND content IS NOT NULL 
              AND length(trim(content)) > 0
            ORDER BY clen ASC;
        """, (novel_id,))
        rows = cursor.fetchall()

    lens = [r["clen"] for r in rows if r["clen"]]
    n = len(lens)
    if n < 5:
        return {
            "count": n,
            "mean": 8000.0,
            "std": 1000.0,
            "median": 8000,
            "q1": 7000,
            "q3": 9000,
            "iqr": 2000,
            "lower_extreme_threshold": 3000,
            "is_dynamic": False
        }

    mean = sum(lens) / n
    variance = sum((x - mean) ** 2 for x in lens) / n
    std = math.sqrt(variance)
    median = lens[n // 2]
    q1 = lens[n // 4]
    q3 = lens[(3 * n) // 4]
    iqr = max(1, q3 - q1)

    # حساب حد القيمة المتطرفة الدنيا ديناميكياً:
    # يجمع بين قاعدة المخطط الصندوقي (Q1 - 2.5 * IQR) ونسبة 55% من المتوسط الحسابي
    box_threshold = q1 - 2.5 * iqr
    ratio_threshold = mean * 0.55
    raw_threshold = min(ratio_threshold, box_threshold) if box_threshold > 0 else ratio_threshold
    lower_threshold = int(max(2500, min(5500, raw_threshold)))

    return {
        "count": n,
        "mean": round(mean, 1),
        "std": round(std, 1),
        "median": median,
        "q1": q1,
        "q3": q3,
        "iqr": iqr,
        "lower_extreme_threshold": lower_threshold,
        "is_dynamic": True
    }


def get_extreme_outlier_chapters(
    novel_id: int,
    custom_threshold: Optional[int] = None,
    db_path: str = DB_FILE_PATH
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    استخراج كافة الفصول التي تمثل قيمة متطرفة دنيا (Lower Extreme Outliers)
    مقارنة بمتوسط أطوال فصول الرواية.
    """
    stats = calculate_novel_length_stats(novel_id, db_path=db_path)
    threshold = custom_threshold if custom_threshold is not None else stats["lower_extreme_threshold"]

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, novel_id, chapter_number, title, url, status, 
                   length(content) as content_len, downloaded_at
            FROM chapters
            WHERE novel_id = ? 
              AND status IN ('downloaded', 'streamed')
              AND (content IS NULL OR length(trim(content)) = 0 OR length(content) < ?)
            ORDER BY chapter_number ASC;
        """, (novel_id, threshold))
        rows = [dict(r) for r in cursor.fetchall()]

    for r in rows:
        clen = r.get("content_len") or 0
        r["is_extreme_outlier"] = clen < threshold
        r["threshold"] = threshold
        r["mean_length"] = stats["mean"]
        r["ratio_to_mean"] = round((clen / stats["mean"]) * 100, 1) if stats["mean"] > 0 else 0.0

    return rows, stats


def get_truncated_chapters(
    novel_id: int,
    threshold_length: Optional[int] = None,
    db_path: str = DB_FILE_PATH
) -> List[Dict[str, Any]]:
    """
    استخراج كافة الفصول المشتبه باقتطاعها أو صغر حجمها غير المعتاد لرواية معينة،
    مع اعتماد الحد الإحصائي الديناميكي تلقائياً في حال عدم تحديد حد ثابت.
    """
    if threshold_length is None:
        stats = calculate_novel_length_stats(novel_id, db_path=db_path)
        effective_threshold = stats["lower_extreme_threshold"]
    else:
        effective_threshold = threshold_length

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, novel_id, chapter_number, title, url, status, length(content) as content_len, downloaded_at
            FROM chapters
            WHERE novel_id = ? 
              AND status IN ('downloaded', 'streamed')
              AND (content IS NULL OR length(content) < ?)
            ORDER BY chapter_number ASC;
        """, (novel_id, effective_threshold))
        return [dict(r) for r in cursor.fetchall()]


# تهيئة الجداول تلقائياً عند استيراد الوحدة
try:
    init_db()
except Exception:
    pass

