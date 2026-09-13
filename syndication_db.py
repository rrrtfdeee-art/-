# -*- coding: utf-8 -*-
"""
syndication_db.py — إدارة إعدادات وقاعدة بيانات النشر التلقائي (نادي الروايات + واتباد)
مستقل تماماً ويحفظ إعدادات الروايات المتعددة وسجل الفصول المنشورة.
"""

import sqlite3
import json
import os
import time
import datetime
import logging
import threading
import requests
from typing import Dict, List, Optional, Any

logger = logging.getLogger("SyndicationDB")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "novel_scraper.db")

def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_syndication_tables():
    """تهيئة جداول النشر التلقائي إذا لم تكن موجودة."""
    conn = _get_conn()
    cur = conn.cursor()
    
    # 1. جدول الحسابات والإعدادات العامة
    cur.execute("""
    CREATE TABLE IF NOT EXISTS syndication_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    
    # 2. جدول الروايات المربوطة للنشر التلقائي
    cur.execute("""
    CREATE TABLE IF NOT EXISTS syndicated_novels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        novel_name TEXT NOT NULL,
        blogger_url TEXT,
        blogger_label TEXT,
        
        -- نادي الروايات
        rewayat_enabled INTEGER DEFAULT 1,
        rewayat_novel_id TEXT,
        rewayat_novel_url TEXT,
        
        -- واتباد
        wattpad_enabled INTEGER DEFAULT 1,
        wattpad_story_id TEXT,
        wattpad_story_url TEXT,
        
        -- قواعد النشر
        start_chapter INTEGER DEFAULT 1,
        last_synced_chapter INTEGER DEFAULT 0,
        stop_chapter INTEGER DEFAULT 9999,
        interval_hours REAL DEFAULT 12.0,
        next_run_timestamp REAL DEFAULT 0.0,
        
        -- التعليق التحفيزي
        custom_cta TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 3. سجل الفصول المنشورة لتفادي أي تكرار
    cur.execute("""
    CREATE TABLE IF NOT EXISTS syndication_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        novel_id INTEGER,
        chapter_num INTEGER,
        platform TEXT, -- 'rewayat_club' أو 'wattpad'
        status TEXT,   -- 'SUCCESS' أو 'FAILED'
        post_url TEXT,
        error_msg TEXT,
        published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(novel_id) REFERENCES syndicated_novels(id)
    )
    """)
    
    # 4. جدول مواعيد فصول الجدولة المتقدمة (مربوط ومتزامن مع Google Sheet)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS syndicated_chapter_schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        novel_name TEXT NOT NULL,
        chapter_num INTEGER NOT NULL,
        scheduled_time TEXT NOT NULL,
        scheduled_timestamp REAL NOT NULL,
        status TEXT DEFAULT 'PENDING',
        platform TEXT DEFAULT 'all',
        published_at TEXT DEFAULT '',
        post_url TEXT DEFAULT '',
        period_range TEXT DEFAULT '',
        last_error TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(novel_name, chapter_num)
    )
    """)

    # 5. جدول قواعد الفترات المخصصة
    cur.execute("""
    CREATE TABLE IF NOT EXISTS syndicated_period_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        novel_name TEXT NOT NULL,
        start_chapter INTEGER NOT NULL,
        end_chapter INTEGER NOT NULL,
        frequency_type TEXT DEFAULT 'daily',
        times_per_day INTEGER DEFAULT 1,
        selected_hours TEXT DEFAULT '[]',
        start_date TEXT DEFAULT '',
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    
    # 6. تهيئة البيانات الافتراضية تلقائياً لدعم السيرفر السحابي (Render Auto-Seeding)
    _seed_default_syndication_data(conn)

    conn.close()

    # مزامنة هادئة وفورية مع Google Sheet في خيط خلفي عند إقلاع السيرفر
    def _deferred_init_sync():
        try:
            time.sleep(1)
            sync_schedule_from_sheet()
        except Exception as ex_sync:
            logger.warning(f"Initial sheet sync notice: {ex_sync}")
    try:
        threading.Thread(target=_deferred_init_sync, daemon=True, name="InitSheetSync").start()
    except Exception as e_th:
        logger.warning(f"Could not launch initial sheet sync: {e_th}")

def _seed_default_syndication_data(conn):
    """تهيئة البيانات الافتراضية المعتمدة تلقائياً إذا كانت الجداول فارغة (مفيد لحاويات Render السحابية)."""
    try:
        cur = conn.cursor()
        # 1. إعدادات حساب نادي الروايات
        cur.execute("SELECT COUNT(*) FROM syndication_settings WHERE key = 'rewayat_token'")
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT OR REPLACE INTO syndication_settings (key, value) VALUES (?, ?)", 
                        ("rewayat_username", os.environ.get("REWAYAT_USERNAME", "wx")))
            cur.execute("INSERT OR REPLACE INTO syndication_settings (key, value) VALUES (?, ?)", 
                        ("rewayat_token", os.environ.get("REWAYAT_TOKEN", "4e3379691bd8dcf3025308a2c677318ed4383f31")))
        
        # 2. رواية After Severing Ties لنادي الروايات
        cur.execute("SELECT COUNT(*) FROM syndicated_novels WHERE rewayat_novel_id = 'after-severing-ties-the-prince-s-family-regrets-it-for-life'")
        if cur.fetchone()[0] == 0:
            cur.execute("""
            INSERT INTO syndicated_novels (
                novel_name, blogger_url, blogger_label,
                rewayat_enabled, rewayat_novel_id, rewayat_novel_url,
                wattpad_enabled, wattpad_story_id, wattpad_story_url,
                start_chapter, last_synced_chapter, stop_chapter,
                interval_hours, next_run_timestamp, custom_cta, is_active
            ) VALUES (
                'After Severing Ties',
                'https://www.novelskyworld.com/p/after-severing-ties.html',
                'After Severing Ties',
                1,
                'after-severing-ties-the-prince-s-family-regrets-it-for-life',
                'https://rewayat.club/novel/after-severing-ties-the-prince-s-family-regrets-it-for-life',
                0, '', '',
                1, 68, 5000,
                1.0, 0.0,
                '✨ استمتعتم بالفصل؟ لمتابعة الفصول الحصرية والمتقدمة فور صدورها زوروا موقعنا الأصلي: [رابط الرواية] ✨',
                0
            )
            """)

        # 3. إعدادات وقصة واتباد الافتراضية
        cur.execute("SELECT COUNT(*) FROM syndication_settings WHERE key = 'wattpad_username'")
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT OR REPLACE INTO syndication_settings (key, value) VALUES (?, ?)", 
                        ("wattpad_username", os.environ.get("WATTPAD_USERNAME", "WX-NOVEL")))
        cur.execute("SELECT COUNT(*) FROM syndication_settings WHERE key = 'wattpad_password'")
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT OR REPLACE INTO syndication_settings (key, value) VALUES (?, ?)", 
                        ("wattpad_password", os.environ.get("WATTPAD_PASSWORD", "F2#yy'=>@>4ZRp-")))
        cur.execute("SELECT COUNT(*) FROM syndication_settings WHERE key = 'wattpad_token'")
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT OR REPLACE INTO syndication_settings (key, value) VALUES (?, ?)", 
                        ("wattpad_token", os.environ.get("WATTPAD_TOKEN", "293131450:2:1789232081:JbbRew6HomsMHJe7_IWVS396lbmIiGoWt0KI6Iylhm17BKRDEv3_ZMem3En9jdrt")))

        cur.execute("SELECT COUNT(*) FROM syndicated_novels WHERE wattpad_story_id = '405774700'")
        if cur.fetchone()[0] == 0:
            cur.execute("""
            INSERT INTO syndicated_novels (
                novel_name, blogger_url, blogger_label,
                rewayat_enabled, rewayat_novel_id, rewayat_novel_url,
                wattpad_enabled, wattpad_story_id, wattpad_story_url,
                start_chapter, last_synced_chapter, stop_chapter,
                interval_hours, next_run_timestamp, custom_cta, is_active
            ) VALUES (
                'After Severing Ties',
                'https://www.novelskyworld.com/p/after-severing-ties.html',
                'After Severing Ties',
                0, '', '',
                1,
                '405774700',
                'https://wattpad.com/story/405774700',
                1, 13, 5000,
                1.0, 0.0,
                '✨ استمتعتم بالفصل؟ لمتابعة الفصول الحصرية والمتقدمة فور صدورها تفضلوا بزيارة موقعنا: [رابط الرواية] ✨',
                0
            )
            """)
        conn.commit()
    except Exception as e_seed:
        pass

# تهيئة الجداول فور الاستيراد
init_syndication_tables()

# ==================== دوال الإعدادات ====================

def get_synd_setting(key: str, default: str = "") -> str:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT value FROM syndication_settings WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    return row["value"] if row else default

def save_synd_setting(key: str, value: str):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO syndication_settings (key, value)
    VALUES (?, ?)
    ON CONFLICT(key) DO UPDATE SET value=excluded.value
    """, (key, value))
    conn.commit()
    conn.close()

# ==================== دوال الروايات ====================

def get_all_syndicated_novels(active_only: bool = False) -> List[Dict[str, Any]]:
    conn = _get_conn()
    cur = conn.cursor()
    query = "SELECT * FROM syndicated_novels"
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY id DESC"
    cur.execute(query)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def get_syndicated_novel_by_id(novel_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM syndicated_novels WHERE id = ?", (novel_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def save_or_update_syndicated_novel(data: Dict[str, Any]) -> int:
    conn = _get_conn()
    cur = conn.cursor()
    
    novel_id = data.get("id")
    data.setdefault("next_run_timestamp", 0.0)
    if novel_id:
        # تحديث
        cur.execute("""
        UPDATE syndicated_novels SET
            novel_name = :novel_name,
            blogger_url = :blogger_url,
            blogger_label = :blogger_label,
            rewayat_enabled = :rewayat_enabled,
            rewayat_novel_id = :rewayat_novel_id,
            rewayat_novel_url = :rewayat_novel_url,
            wattpad_enabled = :wattpad_enabled,
            wattpad_story_id = :wattpad_story_id,
            wattpad_story_url = :wattpad_story_url,
            start_chapter = :start_chapter,
            last_synced_chapter = :last_synced_chapter,
            stop_chapter = :stop_chapter,
            interval_hours = :interval_hours,
            next_run_timestamp = :next_run_timestamp,
            custom_cta = :custom_cta,
            is_active = :is_active
        WHERE id = :id
        """, data)
        res_id = novel_id
    else:
        # إضافة جديد
        cur.execute("""
        INSERT INTO syndicated_novels (
            novel_name, blogger_url, blogger_label,
            rewayat_enabled, rewayat_novel_id, rewayat_novel_url,
            wattpad_enabled, wattpad_story_id, wattpad_story_url,
            start_chapter, last_synced_chapter, stop_chapter,
            interval_hours, next_run_timestamp, custom_cta, is_active
        ) VALUES (
            :novel_name, :blogger_url, :blogger_label,
            :rewayat_enabled, :rewayat_novel_id, :rewayat_novel_url,
            :wattpad_enabled, :wattpad_story_id, :wattpad_story_url,
            :start_chapter, :last_synced_chapter, :stop_chapter,
            :interval_hours, :next_run_timestamp, :custom_cta, :is_active
        )
        """, data)
        res_id = cur.lastrowid
        
    conn.commit()
    conn.close()
    return res_id

def delete_syndicated_novel(novel_id: int):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM syndication_logs WHERE novel_id = ?", (novel_id,))
    cur.execute("DELETE FROM syndicated_novels WHERE id = ?", (novel_id,))
    conn.commit()
    conn.close()

# ==================== دوال السجلات (Logs) ====================

def log_syndication_event(novel_id: int, chapter_num: int, platform: str, status: str, post_url: str = "", error_msg: str = ""):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO syndication_logs (novel_id, chapter_num, platform, status, post_url, error_msg)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (novel_id, chapter_num, platform, status, post_url, error_msg))
    conn.commit()
    conn.close()

def get_recent_syndication_logs(novel_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
    conn = _get_conn()
    cur = conn.cursor()
    if novel_id:
        cur.execute("""
        SELECT l.*, n.novel_name 
        FROM syndication_logs l 
        LEFT JOIN syndicated_novels n ON l.novel_id = n.id
        WHERE l.novel_id = ? 
        ORDER BY l.id DESC LIMIT ?
        """, (novel_id, limit))
    else:
        cur.execute("""
        SELECT l.*, n.novel_name 
        FROM syndication_logs l 
        LEFT JOIN syndicated_novels n ON l.novel_id = n.id
        ORDER BY l.id DESC LIMIT ?
        """, (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

# ==================== إدارة ومزامنة شيت الجدولة السحابي وقواعد الفترات ====================

DEFAULT_SCHEDULE_SPREADSHEET_ID = "12_cNDWNVpyTK-VG1zLl0z6N3fDeO2qIVn5LYuDgRWD0"
SCHEDULE_TAB_NAME = "SyndicationSchedule"
TZ_ARABIA = datetime.timezone(datetime.timedelta(hours=3))
_CREDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ga_credentials.json")

def get_schedule_spreadsheet_id() -> str:
    """الحصول على معرف شيت الجدولة السحابي المعتمد من الإعدادات أو الافتراضي."""
    return get_synd_setting("schedule_spreadsheet_id", DEFAULT_SCHEDULE_SPREADSHEET_ID).strip() or DEFAULT_SCHEDULE_SPREADSHEET_ID

def set_schedule_spreadsheet_id(ssid: str):
    """تحديث معرف شيت الجدولة في الإعدادات."""
    save_synd_setting("schedule_spreadsheet_id", ssid.strip())

def _get_sheets_service():
    """الحصول على عميل Google Sheets API الرسمي الموثق."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        return None

    creds = None
    if os.path.exists(_CREDS_FILE):
        try:
            creds = service_account.Credentials.from_service_account_file(
                _CREDS_FILE,
                scopes=["https://www.googleapis.com/auth/spreadsheets"]
            )
        except Exception:
            pass
    elif os.getenv("GA_CREDENTIALS_JSON"):
        try:
            info = json.loads(os.getenv("GA_CREDENTIALS_JSON"))
            creds = service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/spreadsheets"]
            )
        except Exception:
            pass
    elif os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"):
        try:
            info = json.loads(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON"))
            creds = service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/spreadsheets"]
            )
        except Exception:
            pass

    if not creds:
        return None

    try:
        return build("sheets", "v4", credentials=creds, cache_discovery=False)
    except Exception as ex_b:
        logger.warning(f"Could not build Google Sheets service: {ex_b}")
        return None

def ensure_schedule_tab_exists(service=None, spreadsheet_id: Optional[str] = None) -> str:
    """التأكد من وجود ورقة الجدولة برؤوس الأعمدة المطلوبة وإرجاع اسم التبويب."""
    ssid = spreadsheet_id or get_schedule_spreadsheet_id()
    srv = service or _get_sheets_service()
    if not srv:
        return "الورقة1"
    try:
        meta = srv.spreadsheets().get(spreadsheetId=ssid).execute()
        existing_tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]
        target_tab = "الورقة1" if "الورقة1" in existing_tabs else (SCHEDULE_TAB_NAME if SCHEDULE_TAB_NAME in existing_tabs else (existing_tabs[0] if existing_tabs else "الورقة1"))
        if target_tab not in existing_tabs:
            body = {"requests": [{"addSheet": {"properties": {"title": target_tab}}}]}
            srv.spreadsheets().batchUpdate(spreadsheetId=ssid, body=body).execute()
        
        # التأكد من وجود رؤوس الأعمدة إذا كانت فارغة
        check_head = srv.spreadsheets().values().get(spreadsheetId=ssid, range=f"{target_tab}!A1:I1").execute().get("values", [])
        if not check_head or not check_head[0]:
            headers = [["novel_name", "chapter_num", "scheduled_time", "status", "platform", "published_at", "post_url", "period_range", "last_error"]]
            srv.spreadsheets().values().update(
                spreadsheetId=ssid,
                range=f"{target_tab}!A1:I1",
                valueInputOption="RAW",
                body={"values": headers}
            ).execute()
            logger.info(f"Initialized headers in tab '{target_tab}'")
        return target_tab
    except Exception as e_tab:
        logger.warning(f"ensure_schedule_tab_exists notice: {e_tab}")
        return "الورقة1"

def sync_schedule_from_sheet(spreadsheet_id: Optional[str] = None) -> Dict[str, Any]:
    """
    مزامنة كاملة وشاملة بين جدول Google Sheet وقاعدة البيانات المحلية.
    يضمن استعادة حالة الجدولة بالكامل عند كل إقلاع جديد لسيرفر Render.
    """
    ssid = spreadsheet_id or get_schedule_spreadsheet_id()
    service = _get_sheets_service()
    rows = []
    tab_name = "الورقة1"

    if service:
        try:
            tab_name = ensure_schedule_tab_exists(service, ssid)
            res = service.spreadsheets().values().get(
                spreadsheetId=ssid,
                range=f"{tab_name}!A2:I"
            ).execute()
            rows = res.get("values", [])
        except Exception as ex_api:
            logger.warning(f"Google Sheets API fetch error: {ex_api}, trying GViz fallback...")
            rows = []

    if not rows:
        try:
            for g_sheet in (tab_name, "الورقة1", SCHEDULE_TAB_NAME, None):
                try:
                    gviz_url = f"https://docs.google.com/spreadsheets/d/{ssid}/gviz/tq?tqx=out:json"
                    if g_sheet:
                        gviz_url += f"&sheet={requests.utils.quote(g_sheet)}"
                    resp = requests.get(gviz_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
                    text = resp.text
                    json_str = text[text.find('{'):text.rfind('}') + 1]
                    data = json.loads(json_str)
                    raw_rows = data.get("table", {}).get("rows", [])
                    if raw_rows:
                        for rr in raw_rows:
                            c_vals = []
                            for cell in rr.get("c", []):
                                c_vals.append(str(cell.get("v", "")) if cell and cell.get("v") is not None else "")
                            if any(c_vals):
                                rows.append(c_vals)
                        if rows:
                            break
                except Exception:
                    pass
        except Exception as ex_gv:
            logger.error(f"GViz fallback fetch error: {ex_gv}")

    if not rows:
        return {"success": False, "synced_count": 0, "message": "لا توجد فصول في الشيت أو تعذر الاتصال"}

    conn = _get_conn()
    cur = conn.cursor()
    synced_count = 0
    novel_stats = {}

    for r in rows:
        if len(r) < 3:
            continue
        n_name = str(r[0]).strip()
        try:
            ch_num = int(float(str(r[1]).strip()))
        except Exception:
            continue
        sch_time_str = str(r[2]).strip()
        stat = str(r[3]).strip().upper() if len(r) > 3 and str(r[3]).strip() else "PENDING"
        plat = str(r[4]).strip() if len(r) > 4 and str(r[4]).strip() else "all"
        pub_at = str(r[5]).strip() if len(r) > 5 else ""
        p_url = str(r[6]).strip() if len(r) > 6 else ""
        p_range = str(r[7]).strip() if len(r) > 7 else ""
        l_err = str(r[8]).strip() if len(r) > 8 else ""

        sch_ts = 0.0
        try:
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M"):
                try:
                    dt = datetime.datetime.strptime(sch_time_str, fmt).replace(tzinfo=TZ_ARABIA)
                    sch_ts = dt.timestamp()
                    break
                except Exception:
                    pass
        except Exception:
            sch_ts = 0.0

        cur.execute("""
        INSERT INTO syndicated_chapter_schedules (
            novel_name, chapter_num, scheduled_time, scheduled_timestamp,
            status, platform, published_at, post_url, period_range, last_error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(novel_name, chapter_num) DO UPDATE SET
            scheduled_time = excluded.scheduled_time,
            scheduled_timestamp = excluded.scheduled_timestamp,
            status = excluded.status,
            platform = excluded.platform,
            published_at = excluded.published_at,
            post_url = excluded.post_url,
            period_range = excluded.period_range,
            last_error = excluded.last_error
        """, (n_name, ch_num, sch_time_str, sch_ts, stat, plat, pub_at, p_url, p_range, l_err))
        synced_count += 1

        if n_name not in novel_stats:
            novel_stats[n_name] = {"max_published": 0, "earliest_pending": None, "pending_count": 0}

        if stat == "PUBLISHED":
            if ch_num > novel_stats[n_name]["max_published"]:
                novel_stats[n_name]["max_published"] = ch_num
        elif stat == "PENDING" and sch_ts > 0:
            novel_stats[n_name]["pending_count"] += 1
            if novel_stats[n_name]["earliest_pending"] is None or sch_ts < novel_stats[n_name]["earliest_pending"]:
                novel_stats[n_name]["earliest_pending"] = sch_ts

    conn.commit()

    # تحديث وتنشيط الروايات في syndicated_novels تلقائياً لدعم ريستارت سيرفر Render
    for n_name, st_info in novel_stats.items():
        cur.execute("SELECT * FROM syndicated_novels WHERE novel_name = ?", (n_name,))
        existing_nov = cur.fetchone()
        if existing_nov:
            updates = {}
            if st_info["max_published"] > (existing_nov["last_synced_chapter"] or 0):
                updates["last_synced_chapter"] = st_info["max_published"]
            if st_info["pending_count"] > 0:
                updates["is_active"] = 1
                if st_info["earliest_pending"]:
                    updates["next_run_timestamp"] = st_info["earliest_pending"]
            if updates:
                set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
                cur.execute(f"UPDATE syndicated_novels SET {set_clause} WHERE id = ?", list(updates.values()) + [existing_nov["id"]])
                conn.commit()

    conn.close()
    logger.info(f"Successfully synced {synced_count} schedule rows from Google Sheets.")
    return {"success": True, "synced_count": synced_count}

def save_chapter_schedules_batch(novel_name: str, rows: List[Dict[str, Any]], spreadsheet_id: Optional[str] = None) -> bool:
    """
    حفظ دفعة فصول مجدولة في قاعدة البيانات المحلية ومزامنتها فوراً مع Google Sheet.
    """
    if not rows:
        return True

    conn = _get_conn()
    cur = conn.cursor()
    for r in rows:
        cur.execute("""
        INSERT INTO syndicated_chapter_schedules (
            novel_name, chapter_num, scheduled_time, scheduled_timestamp,
            status, platform, published_at, post_url, period_range, last_error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(novel_name, chapter_num) DO UPDATE SET
            scheduled_time = excluded.scheduled_time,
            scheduled_timestamp = excluded.scheduled_timestamp,
            status = CASE WHEN syndicated_chapter_schedules.status = 'PUBLISHED' THEN 'PUBLISHED' ELSE excluded.status END,
            platform = excluded.platform,
            period_range = excluded.period_range
        """, (
            novel_name,
            r["chapter_num"],
            r["scheduled_time"],
            r["scheduled_timestamp"],
            r.get("status", "PENDING"),
            r.get("platform", "all"),
            r.get("published_at", ""),
            r.get("post_url", ""),
            r.get("period_range", ""),
            r.get("last_error", "")
        ))
    conn.commit()
    conn.close()

    # مزامنة فورية مع Google Sheet
    ssid = spreadsheet_id or get_schedule_spreadsheet_id()
    service = _get_sheets_service()
    if service:
        try:
            tab_name = ensure_schedule_tab_exists(service, ssid)
            res = service.spreadsheets().values().get(
                spreadsheetId=ssid,
                range=f"{tab_name}!A:B"
            ).execute()
            sheet_rows = res.get("values", [])
            row_map = {}
            for idx, sr in enumerate(sheet_rows, start=1):
                if idx == 1:
                    continue
                if len(sr) >= 2:
                    try:
                        row_map[(str(sr[0]).strip(), int(float(str(sr[1]).strip())))] = idx
                    except Exception:
                        pass

            append_rows = []
            update_data = []

            for r in rows:
                val_row = [
                    novel_name,
                    r["chapter_num"],
                    r["scheduled_time"],
                    r.get("status", "PENDING"),
                    r.get("platform", "all"),
                    r.get("published_at", ""),
                    r.get("post_url", ""),
                    r.get("period_range", ""),
                    r.get("last_error", "")
                ]
                key = (novel_name, r["chapter_num"])
                if key in row_map:
                    row_idx = row_map[key]
                    update_data.append({
                        "range": f"{tab_name}!A{row_idx}:I{row_idx}",
                        "values": [val_row]
                    })
                else:
                    append_rows.append(val_row)

            if update_data:
                service.spreadsheets().values().batchUpdate(
                    spreadsheetId=ssid,
                    body={"valueInputOption": "USER_ENTERED", "data": update_data}
                ).execute()

            if append_rows:
                service.spreadsheets().values().append(
                    spreadsheetId=ssid,
                    range=f"{tab_name}!A:I",
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body={"values": append_rows}
                ).execute()
        except Exception as ex_write:
            logger.error(f"Failed to write schedules to Google Sheet: {ex_write}")

    return True

def update_chapter_schedule_status(
    novel_name: str,
    chapter_num: int,
    status: str,
    post_url: str = "",
    error_msg: str = "",
    published_at: str = "",
    spreadsheet_id: Optional[str] = None
):
    """تحديث حالة الفصل المجدول في قاعدة البيانات المحلية وفي Google Sheet."""
    now_str = published_at or datetime.datetime.now(TZ_ARABIA).strftime("%Y-%m-%d %H:%M:%S")
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
    UPDATE syndicated_chapter_schedules SET
        status = ?,
        published_at = CASE WHEN ? = 'PUBLISHED' THEN ? ELSE published_at END,
        post_url = CASE WHEN ? != '' THEN ? ELSE post_url END,
        last_error = ?
    WHERE novel_name = ? AND chapter_num = ?
    """, (status, status, now_str, post_url, post_url, error_msg, novel_name, chapter_num))
    conn.commit()
    conn.close()

    ssid = spreadsheet_id or get_schedule_spreadsheet_id()
    service = _get_sheets_service()
    if service:
        try:
            tab_name = ensure_schedule_tab_exists(service, ssid)
            res = service.spreadsheets().values().get(
                spreadsheetId=ssid,
                range=f"{tab_name}!A:B"
            ).execute()
            sheet_rows = res.get("values", [])
            for idx, sr in enumerate(sheet_rows, start=1):
                if idx == 1:
                    continue
                if len(sr) >= 2 and str(sr[0]).strip() == novel_name and str(sr[1]).strip() == str(chapter_num):
                    service.spreadsheets().values().update(
                        spreadsheetId=ssid,
                        range=f"{tab_name}!D{idx}",
                        valueInputOption="USER_ENTERED",
                        body={"values": [[status]]}
                    ).execute()
                    if status == "PUBLISHED":
                        service.spreadsheets().values().update(
                            spreadsheetId=ssid,
                            range=f"{tab_name}!F{idx}:G{idx}",
                            valueInputOption="USER_ENTERED",
                            body={"values": [[now_str, post_url]]}
                        ).execute()
                    if error_msg:
                        service.spreadsheets().values().update(
                            spreadsheetId=ssid,
                            range=f"{tab_name}!I{idx}",
                            valueInputOption="USER_ENTERED",
                            body={"values": [[error_msg]]}
                        ).execute()
                    break
        except Exception as ex_up:
            logger.warning(f"Could not update chapter status in Google Sheet: {ex_up}")

def get_scheduled_chapters(novel_name: Optional[str] = None, status: Optional[str] = None, limit: int = 500) -> List[Dict[str, Any]]:
    """جلب قائمة الفصول المجدولة بحسب الرواية والحالة."""
    conn = _get_conn()
    cur = conn.cursor()
    query = "SELECT * FROM syndicated_chapter_schedules"
    params = []
    conds = []
    if novel_name:
        conds.append("novel_name = ?")
        params.append(novel_name)
    if status:
        conds.append("status = ?")
        params.append(status)
    if conds:
        query += " WHERE " + " AND ".join(conds)
    query += " ORDER BY chapter_num ASC, scheduled_timestamp ASC LIMIT ?"
    params.append(limit)
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def delete_chapter_schedule(novel_name: str, chapter_num: int, spreadsheet_id: Optional[str] = None) -> bool:
    """حذف أو إلغاء موعد فصل مجدول من قاعدة البيانات والشيت."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM syndicated_chapter_schedules WHERE novel_name = ? AND chapter_num = ?", (novel_name, chapter_num))
    conn.commit()
    conn.close()

    ssid = spreadsheet_id or get_schedule_spreadsheet_id()
    service = _get_sheets_service()
    if service:
        try:
            tab_name = ensure_schedule_tab_exists(service, ssid)
            res = service.spreadsheets().values().get(
                spreadsheetId=ssid,
                range=f"{tab_name}!A:B"
            ).execute()
            sheet_rows = res.get("values", [])
            for idx, sr in enumerate(sheet_rows, start=1):
                if idx == 1:
                    continue
                if len(sr) >= 2 and str(sr[0]).strip() == novel_name and str(sr[1]).strip() == str(chapter_num):
                    service.spreadsheets().values().update(
                        spreadsheetId=ssid,
                        range=f"{tab_name}!D{idx}",
                        valueInputOption="USER_ENTERED",
                        body={"values": [["CANCELLED"]]}
                    ).execute()
                    break
        except Exception as ex_d:
            logger.warning(f"Could not cancel chapter in Google Sheet: {ex_d}")
    return True

# ==================== قواعد الفترات المخصصة وحساب المواعيد ====================

def save_period_rule(rule_data: Dict[str, Any]) -> int:
    """حفظ قاعدة فترة جديدة للرواية."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO syndicated_period_rules (
        novel_name, start_chapter, end_chapter, frequency_type,
        times_per_day, selected_hours, start_date, is_active
    ) VALUES (:novel_name, :start_chapter, :end_chapter, :frequency_type,
              :times_per_day, :selected_hours, :start_date, :is_active)
    """, rule_data)
    res_id = cur.lastrowid
    conn.commit()
    conn.close()
    return res_id

def get_period_rules(novel_name: str) -> List[Dict[str, Any]]:
    """جلب كافة قواعد الفترات المسجلة للرواية."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM syndicated_period_rules WHERE novel_name = ? ORDER BY start_chapter ASC", (novel_name,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def delete_period_rule(rule_id: int):
    """حذف قاعدة فترة محددة."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM syndicated_period_rules WHERE id = ?", (rule_id,))
    conn.commit()
    conn.close()

def generate_schedule_from_period_rules(
    novel_name: str,
    start_ch: int,
    end_ch: int,
    freq_type: str,
    times_per_day: int,
    selected_hours: List[str],
    start_date_str: str,
    platform: str = "all"
) -> List[Dict[str, Any]]:
    """
    توليد جدول مواعيد الفصول بدقة استناداً إلى النطاق والتكرار والساعات المحددة يدوياً.
    """
    res = []
    ch = int(start_ch)
    end_val = int(end_ch)
    try:
        cur_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
    except Exception:
        cur_date = datetime.datetime.now(TZ_ARABIA).date()

    p_tag = f"{start_ch}-{end_ch}" if start_ch != end_ch else f"{start_ch}"

    valid_hours = []
    for h in (selected_hours or ["12:00"]):
        h_clean = str(h).strip()
        if ":" in h_clean:
            valid_hours.append(h_clean)
    if not valid_hours:
        valid_hours = ["12:00"]
    valid_hours = sorted(valid_hours)

    if freq_type == "daily":
        hour_idx = 0
        while ch <= end_val:
            h_str, m_str = valid_hours[hour_idx].split(":")
            dt = datetime.datetime.combine(cur_date, datetime.time(int(h_str), int(m_str)), tzinfo=TZ_ARABIA)
            res.append({
                "chapter_num": ch,
                "scheduled_time": dt.strftime("%Y-%m-%d %H:%M"),
                "scheduled_timestamp": dt.timestamp(),
                "status": "PENDING",
                "platform": platform,
                "period_range": p_tag
            })
            ch += 1
            hour_idx += 1
            if hour_idx >= len(valid_hours):
                hour_idx = 0
                cur_date += datetime.timedelta(days=1)

    elif freq_type == "weekly":
        h_str, m_str = valid_hours[0].split(":")
        while ch <= end_val:
            dt = datetime.datetime.combine(cur_date, datetime.time(int(h_str), int(m_str)), tzinfo=TZ_ARABIA)
            res.append({
                "chapter_num": ch,
                "scheduled_time": dt.strftime("%Y-%m-%d %H:%M"),
                "scheduled_timestamp": dt.timestamp(),
                "status": "PENDING",
                "platform": platform,
                "period_range": p_tag
            })
            ch += 1
            cur_date += datetime.timedelta(weeks=1)

    elif freq_type == "monthly":
        h_str, m_str = valid_hours[0].split(":")
        while ch <= end_val:
            dt = datetime.datetime.combine(cur_date, datetime.time(int(h_str), int(m_str)), tzinfo=TZ_ARABIA)
            res.append({
                "chapter_num": ch,
                "scheduled_time": dt.strftime("%Y-%m-%d %H:%M"),
                "scheduled_timestamp": dt.timestamp(),
                "status": "PENDING",
                "platform": platform,
                "period_range": p_tag
            })
            ch += 1
            cur_date += datetime.timedelta(days=30)

    elif freq_type == "interval":
        h_str, m_str = valid_hours[0].split(":")
        step_hours = float(times_per_day) if times_per_day and times_per_day > 0 else 1.0
        cur_dt = datetime.datetime.combine(cur_date, datetime.time(int(h_str), int(m_str)), tzinfo=TZ_ARABIA)
        while ch <= end_val:
            res.append({
                "chapter_num": ch,
                "scheduled_time": cur_dt.strftime("%Y-%m-%d %H:%M"),
                "scheduled_timestamp": cur_dt.timestamp(),
                "status": "PENDING",
                "platform": platform,
                "period_range": p_tag
            })
            ch += 1
            cur_dt += datetime.timedelta(hours=step_hours)

    elif freq_type == "once":
        h_str, m_str = valid_hours[0].split(":")
        dt = datetime.datetime.combine(cur_date, datetime.time(int(h_str), int(m_str)), tzinfo=TZ_ARABIA)
        while ch <= end_val:
            res.append({
                "chapter_num": ch,
                "scheduled_time": dt.strftime("%Y-%m-%d %H:%M"),
                "scheduled_timestamp": dt.timestamp(),
                "status": "PENDING",
                "platform": platform,
                "period_range": p_tag
            })
            ch += 1

    return res

