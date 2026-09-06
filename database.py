"""
==============================================================================
Smart Novel Scraper - Database Management Layer (SQLite)
==============================================================================
هذا الملف مسؤول عن إدارة قاعدة بيانات SQLite بالكامل:
1. تخزين إعدادات الـ Selectors المستخرجة لكل دومين (domains_config).
2. حفظ بيانات الروايات والفهارس (novels).
3. حفظ وتتبع حالة ومحتوى كل فصل (chapters) لدعم الاستئناف (Resume) وتفادي التكرار.
4. توليد نص التصدير النهائي بالصيغة القياسية المحددة.
"""

import json
import sqlite3
import datetime
from typing import List, Dict, Optional, Any, Tuple
import os

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
        conn.commit()


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
    """إنشاء أو جلب سجل الرواية بناءً على رابط الفهرس TOC URL."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM novels WHERE toc_url = ?", (toc_url,))
        row = cursor.fetchone()
        if row:
            # إذا كان هناك تحديث للعنوان إذا لم يكن افتراضياً
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
    db_path: str = DB_FILE_PATH
) -> List[Dict[str, Any]]:
    """جلب قائمة الفصول لرواية معينة بناءً على النطاق والحالة."""
    query = "SELECT * FROM chapters WHERE novel_id = ?"
    params: List[Any] = [novel_id]

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


def get_all_novels(db_path: str = DB_FILE_PATH) -> List[Dict[str, Any]]:
    """جلب كل الروايات المخزنة على السيرفر مع إحصائيات تفصيلية لكل رواية."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                n.id, n.domain, n.toc_url, n.title, n.total_chapters,
                n.created_at, n.updated_at,
                COALESCE(SUM(CASE WHEN c.status = 'downloaded' THEN 1 ELSE 0 END), 0) AS downloaded,
                COALESCE(SUM(CASE WHEN c.status = 'pending' THEN 1 ELSE 0 END), 0) AS pending,
                COALESCE(SUM(CASE WHEN c.status = 'failed' THEN 1 ELSE 0 END), 0) AS failed
            FROM novels n
            LEFT JOIN chapters c ON n.id = c.novel_id
            GROUP BY n.id
            ORDER BY n.updated_at DESC;
        """)
        return [dict(r) for r in cursor.fetchall()]


def delete_novel(novel_id: int, db_path: str = DB_FILE_PATH) -> bool:
    """حذف الرواية وجميع فصولها بالكامل من قاعدة البيانات."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chapters WHERE novel_id = ?;", (novel_id,))
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
