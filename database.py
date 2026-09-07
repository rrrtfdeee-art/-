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

        # 4. جدول فصول الروايات مع دعم حالة التنزيل والمحتوى
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chapters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                novel_id INTEGER NOT NULL,
                chapter_number INTEGER NOT NULL,
                url TEXT NOT NULL,
                title TEXT,
                content TEXT,
                status TEXT DEFAULT 'pending', -- 'pending', 'downloaded', 'failed', 'streamed'
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
    """جلب قائمة بجميع الدومينات المحفوظة ومحدداتها."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM domains_config ORDER BY updated_at DESC")
        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["purge_selectors"] = json.loads(d["purge_selectors"])
            except Exception:
                d["purge_selectors"] = []
            result.append(d)
        return result


def delete_domain_config(domain: str, db_path: str = DB_FILE_PATH) -> bool:
    """حذف إعدادات دومين من قاعدة البيانات."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM domains_config WHERE domain = ?", (domain.lower(),))
        conn.commit()
        return cursor.rowcount > 0


# ==============================================================================
# إدارة إعدادات التطبيق العامة والمفاتيح (App Settings)
# ==============================================================================

def get_setting(key: str, default: str = "", db_path: str = DB_FILE_PATH) -> str:
    """جلب قيمة إعداد معين."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else default


def save_setting(key: str, value: str, db_path: str = DB_FILE_PATH) -> bool:
    """حفظ أو تحديث قيمة إعداد معين."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at;
        """, (key, str(value), now))
        conn.commit()
        return True


# ==============================================================================
# إدارة الروايات والفهارس (Novels & Chapters Management)
# ==============================================================================

def get_or_create_novel(domain: str, toc_url: str, title: str, db_path: str = DB_FILE_PATH) -> Dict[str, Any]:
    """جلب رواية موجودة أو إنشاء سجل جديد للرواية."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM novels WHERE toc_url = ?", (toc_url,))
        row = cursor.fetchone()
        if row:
            return dict(row)

        cursor.execute("""
            INSERT INTO novels (domain, toc_url, title)
            VALUES (?, ?, ?)
        """, (domain.lower(), toc_url, title))
        conn.commit()
        novel_id = cursor.lastrowid

        cursor.execute("SELECT * FROM novels WHERE id = ?", (novel_id,))
        return dict(cursor.fetchone())


def sync_chapter_manifest(novel_id: int, chapters_data: List[Dict[str, Any]], db_path: str = DB_FILE_PATH) -> int:
    """مزامنة وحفظ قائمة روابط وعناوين الفصول المكتشفة من صفحة الفهرس."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        inserted_count = 0
        for ch in chapters_data:
            cursor.execute("""
                INSERT INTO chapters (novel_id, chapter_number, url, title, status)
                VALUES (?, ?, ?, ?, 'pending')
                ON CONFLICT(novel_id, chapter_number) DO UPDATE SET
                    url = excluded.url,
                    title = COALESCE(excluded.title, chapters.title);
            """, (novel_id, ch["chapter_number"], ch["url"], ch.get("title", "")))
            inserted_count += 1

        cursor.execute("UPDATE novels SET total_chapters = (SELECT COUNT(*) FROM chapters WHERE novel_id = ?), updated_at = CURRENT_TIMESTAMP WHERE id = ?", (novel_id, novel_id))
        conn.commit()
        return inserted_count


def save_chapter_content(
    novel_id: int,
    chapter_number: int,
    title: str,
    content: Optional[str],
    status: str = "downloaded",
    error_message: Optional[str] = None,
    db_path: str = DB_FILE_PATH
) -> bool:
    """حفظ محتوى الفصل الذي تم سحبه وتحديث حالته وتاريخه."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE chapters
            SET title = ?,
                content = ?,
                status = ?,
                error_message = ?,
                downloaded_at = ?
            WHERE novel_id = ? AND chapter_number = ?
        """, (title, content, status, error_message, now if status == "downloaded" else None, novel_id, chapter_number))
        conn.commit()
        return cursor.rowcount > 0


def get_chapters(
    novel_id: int,
    from_chapter: Optional[int] = None,
    to_chapter: Optional[int] = None,
    status: Optional[str] = None,
    db_path: str = DB_FILE_PATH
) -> List[Dict[str, Any]]:
    """جلب فصول رواية مع إمكانية الفلترة بالنطاق أو الحالة."""
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

    query += " ORDER BY chapter_number ASC"

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def get_novel_stats(novel_id: int, db_path: str = DB_FILE_PATH) -> Dict[str, int]:
    """إرجاع إحصائيات سريعة عن فصول الرواية وحالاتها."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'downloaded' THEN 1 ELSE 0 END) as downloaded,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
            FROM chapters
            WHERE novel_id = ?
        """, (novel_id,))
        row = cursor.fetchone()
        return {
            "total": row["total"] or 0,
            "downloaded": row["downloaded"] or 0,
            "pending": row["pending"] or 0,
            "failed": row["failed"] or 0
        }


def clear_novel_chapters_data(novel_id: int, db_path: str = DB_FILE_PATH) -> bool:
    """تفريغ نصوص الفصول لرواية كاملة بعد التصدير لتوفير المساحة."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE chapters
            SET content = NULL, status = 'pending', downloaded_at = NULL, error_message = NULL
            WHERE novel_id = ?
        """, (novel_id,))
        conn.commit()
        return cursor.rowcount > 0


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


def delete_novel(novel_id: int, db_path: str = DB_FILE_PATH) -> bool:
    """حذف رواية وجميع فصولها بالكامل من قاعدة البيانات."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM novels WHERE id = ?", (novel_id,))
        conn.commit()
        return cursor.rowcount > 0


def export_novel_to_text(novel_id: int, from_chapter: int = 1, to_chapter: Optional[int] = None, db_path: str = DB_FILE_PATH) -> Tuple[str, int]:
    """توليد النص النهائي للرواية مجمعاً بالصيغة القياسية المحددة."""
    chapters = get_chapters(novel_id, from_chapter=from_chapter, to_chapter=to_chapter, status="downloaded", db_path=db_path)
    output_blocks = []
    
    for ch in chapters:
        if ch.get("content"):
            title = ch.get("title", f"الفصل {ch['chapter_number']}")
            content = ch["content"].strip()
            block = (
                "===CHAPTER_START===\n"
                f"TITLE: {title}\n"
                f"CONTENT:\n{content}\n"
                "===CHAPTER_END==="
            )
            output_blocks.append(block)

    full_text = "\n\n".join(output_blocks)
    return full_text, len(output_blocks)
