# -*- coding: utf-8 -*-
"""
syndication_db.py — إدارة إعدادات وقاعدة بيانات النشر التلقائي (نادي الروايات + واتباد)
مستقل تماماً ويحفظ إعدادات الروايات المتعددة وسجل الفصول المنشورة.
"""

import sqlite3
import json
import os
from typing import Dict, List, Optional, Any

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
    
    conn.commit()
    
    # 4. تهيئة البيانات الافتراضية تلقائياً لدعم السيرفر السحابي (Render Auto-Seeding)
    _seed_default_syndication_data(conn)

    conn.close()

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
        
        # 2. رواية After Severing Ties
        cur.execute("SELECT COUNT(*) FROM syndicated_novels WHERE novel_name = 'After Severing Ties'")
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
                1, 52, 5000,
                12.0, 0.0,
                '✨ استمتعتم بالفصل؟ لمتابعة الفصول الحصرية والمتقدمة فور صدورها زوروا موقعنا الأصلي: [رابط الرواية] ✨',
                1
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
            interval_hours, custom_cta, is_active
        ) VALUES (
            :novel_name, :blogger_url, :blogger_label,
            :rewayat_enabled, :rewayat_novel_id, :rewayat_novel_url,
            :wattpad_enabled, :wattpad_story_id, :wattpad_story_url,
            :start_chapter, :last_synced_chapter, :stop_chapter,
            :interval_hours, :custom_cta, :is_active
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
