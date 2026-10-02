-- ==============================================================================
-- NSW System v3.0 - Supabase PostgreSQL Database Schema
-- قم بلصق هذا الكود وتشغيله في SQL Editor داخل لوحة تحكم Supabase
-- ==============================================================================

-- 1. جدول الروايات (Novels)
CREATE TABLE IF NOT EXISTS novels (
    id BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    original_url TEXT,
    domain TEXT,
    total_chapters INT DEFAULT 0,
    config JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. جدول الفصول (Chapters)
CREATE TABLE IF NOT EXISTS chapters (
    id BIGSERIAL PRIMARY KEY,
    novel_id BIGINT REFERENCES novels(id) ON DELETE CASCADE,
    chapter_number INT NOT NULL,
    title TEXT,
    url TEXT,
    content TEXT,
    status TEXT DEFAULT 'مؤرشف', -- مؤرشف, pending, downloaded, translated, published, streamed
    source TEXT DEFAULT 'direct',
    downloaded_at TIMESTAMPTZ,
    translated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_novel_chapter UNIQUE(novel_id, chapter_number)
);

-- فهارس تسريع البحث عن الفصول والفجوات
CREATE INDEX IF NOT EXISTS idx_chapters_novel_num ON chapters(novel_id, chapter_number);
CREATE INDEX IF NOT EXISTS idx_chapters_status ON chapters(status);
CREATE INDEX IF NOT EXISTS idx_chapters_novel_status ON chapters(novel_id, status);

-- 3. جدول قواميس المصطلحات (Glossary)
CREATE TABLE IF NOT EXISTS glossaries (
    id BIGSERIAL PRIMARY KEY,
    novel_id BIGINT REFERENCES novels(id) ON DELETE CASCADE,
    term_source TEXT NOT NULL,
    term_target TEXT NOT NULL,
    category TEXT DEFAULT 'general',
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_novel_term UNIQUE(novel_id, term_source)
);

CREATE INDEX IF NOT EXISTS idx_glossary_novel ON glossaries(novel_id);

-- 4. جدول الروايات المربوطة بمنصات النشر (Syndicated Novels)
CREATE TABLE IF NOT EXISTS syndicated_novels (
    id BIGSERIAL PRIMARY KEY,
    novel_name TEXT UNIQUE NOT NULL,
    novel_id BIGINT,
    rewayat_novel_id INT,
    rewayat_enabled BOOLEAN DEFAULT FALSE,
    wattpad_story_id TEXT,
    wattpad_enabled BOOLEAN DEFAULT FALSE,
    blogger_url TEXT,
    blogger_enabled BOOLEAN DEFAULT FALSE,
    custom_cta TEXT,
    interval_hours INT DEFAULT 4,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. جدول طابور وجدولة نشر الفصول (Syndicated Chapter Schedules)
CREATE TABLE IF NOT EXISTS syndicated_chapter_schedules (
    id BIGSERIAL PRIMARY KEY,
    novel_name TEXT NOT NULL,
    chapter_num INT NOT NULL,
    platform TEXT DEFAULT 'all', -- all, wattpad, rewayat_club, blogger
    scheduled_time TIMESTAMPTZ NOT NULL,
    status TEXT DEFAULT 'PENDING', -- PENDING, PUBLISHED, FAILED, SKIPPED
    published_at TIMESTAMPTZ,
    published_url TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_schedule_item UNIQUE(novel_name, chapter_num, platform)
);

-- فهارس تسريع استعلام الحارس الليلي (Google Apps Script) وسيرفر النشر
CREATE INDEX IF NOT EXISTS idx_schedules_lookup ON syndicated_chapter_schedules(status, scheduled_time ASC);

-- 6. جدول سجلات وعمليات النشر (Syndication Logs)
CREATE TABLE IF NOT EXISTS syndication_logs (
    id BIGSERIAL PRIMARY KEY,
    level TEXT DEFAULT 'INFO',
    module TEXT,
    message TEXT NOT NULL,
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_logs_created_at ON syndication_logs(created_at DESC);

-- 7. جدول إعدادات النظام العامة (App Settings)
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    description TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- تمكين قراءة REST API العامة لجميع الجداول عبر مفتاح anon / service_role
COMMENT ON TABLE chapters IS 'فصول الروايات الكاملة مع المتون الأصلية والمترجمة';
COMMENT ON TABLE syndicated_chapter_schedules IS 'طابور النشر المجدول للمنصات الخارجية';
