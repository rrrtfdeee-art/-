"""
==============================================================================
Smart Novel Scraper - Production-Grade Streamlit Web Application
==============================================================================
تطبيق ويب متكامل واحترافي لسحب فصول الروايات بالذكاء الاصطناعي مع واجهة تفاعلية:
- تصميم Dark Modern فاخر مع تباين لوني فائق الوضوح ومريح للعين.
- نظام فهرسة هجين ذكي (خطوة 1: فحص تلقائي سريع، خطوة 2: تحليل متقدم بالذكاء الاصطناعي عند الحاجة).
- سحب فائق التخفي باستخدام Playwright Stealth وتجاوز حمايات Cloudflare.
- حفظ واستئناف تلقائي عبر SQLite.
- تصدير فوري لملف .TXT منظم بالصيغة المطلوبة.
"""

import os
import sys
import time
import json
import asyncio
import streamlit as st

# حل مشكلة NotImplementedError الخاصة بـ Playwright على ويندوز داخل Streamlit
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

# استيراد الوحدات المساعدة
from database import (
    init_db,
    get_domain_config,
    save_domain_config,
    get_all_domains_config,
    delete_domain_config,
    get_or_create_novel,
    get_all_novels,
    sync_chapter_manifest,
    save_chapter_content,
    get_chapters,
    get_novel_stats,
    clear_novel_chapters_data,
    delete_novel,
    export_novel_to_text,
    get_setting,
    save_setting
)
from gemini_analyzer import (
    analyze_site_dom_with_gemini,
    auto_detect_selectors_heuristically,
    validate_selectors_against_html,
    test_gemini_connection,
    run_diagnostic_dict,
    gas_pool,
    parse_gas_pool_string,
    run_pool_diagnostic,
    DEFAULT_GAS_POOL
)
from scraper_engine import (
    extract_clean_domain,
    PlaywrightStealthBrowser,
    crawl_toc_chapters,
    fetch_samples_for_gemini_analysis,
    NovelScrapingSession,
    extract_chapter_title,
    clean_chapter_content,
    start_background_scraping,
    ACTIVE_BACKGROUND_TASKS
)
from media_engine import (
    get_video_info,
    download_media_file,
    split_video_lossless,
    translate_subtitles_with_gemini,
    send_to_telegram,
    cleanup_media_directory,
    is_ffmpeg_available
)
import nsw_bot_bridge
import nsw_healer_engine

# إطلاق جسر بوت إدارة الموقع تلقائياً في الخلفية مرة واحدة فقط
if "nsw_bridge_started" not in st.session_state:
    try:
        nsw_bot_bridge.start_bridge_thread()
        st.session_state.nsw_bridge_started = True
    except Exception as _br_err:
        pass

# ==============================================================================
# تهيئة صفحة Streamlit والتنسيق البصري (High-Contrast Dark Theme)
# ==============================================================================

st.set_page_config(
    page_title="Smart Novel Scraper AI",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# تهيئة قاعدة البيانات المحلية
init_db()

# تطبيق أنماط CSS المتقدمة مع تباين عالي وواضح للنصوص والأزرار
st.markdown("""
<style>
    /* استيراد الخطوط */
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&family=JetBrains+Mono:wght@400;600;700&display=swap');

    html, body {
        font-family: 'Cairo', sans-serif !important;
    }

    /* تطبيق الاتجاه من اليمين لليسار على المحتوى الأساسي والبطاقات بدون كسر هيكل Streamlit */
    .stApp, .main, div[data-testid="stSidebarUserContent"], .scraper-card, .stMarkdown, div[data-testid="stVerticalBlock"] {
        font-family: 'Cairo', sans-serif !important;
        direction: rtl;
        text-align: right;
    }
    
    /* خلفية داكنة راقية وثابتة */
    .stApp {
        background-color: #080c14;
        color: #f1f5f9;
    }

    /* ---------------------------------------------------- */
    /* إصلاح تداخل الشريط الجانبي في الموبايل والـ RTL */
    /* ---------------------------------------------------- */
    section[data-testid="stSidebar"] {
        background-color: #0d131f !important;
        border-left: 1px solid #1e293b !important;
        overflow-x: hidden !important;
        transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1), width 0.3s ease !important;
    }

    /* إخفاء تام لأي نصوص متسربة عند إغلاق الشريط الجانبي */
    section[data-testid="stSidebar"][aria-expanded="false"] {
        display: none !important;
        visibility: hidden !important;
        width: 0 !important;
        min-width: 0 !important;
        margin: 0 !important;
        padding: 0 !important;
        overflow: hidden !important;
    }

    /* منع التفاف النصوص حرفاً بحرف عند تغيير الحجم */
    section[data-testid="stSidebar"] * {
        white-space: normal !important;
        word-break: break-word !important;
    }

    /* تحسين زر فتح وإغلاق القائمة على الجوال */
    [data-testid="collapsedControl"], [data-testid="stSidebarCollapseButton"] {
        z-index: 100000 !important;
        background-color: #1e293b !important;
        border-radius: 8px !important;
        border: 1px solid #334155 !important;
    }
    [data-testid="collapsedControl"] button, [data-testid="stSidebarCollapseButton"] button {
        color: #38bdf8 !important;
    }
    
    /* بطاقات المحتوى الرئيسية */
    .scraper-card {
        background: linear-gradient(135deg, #0f172a 0%, #111827 100%);
        border: 1px solid #334155;
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 24px;
        box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.7);
    }
    
    /* العناوين المضيئة */
    .scraper-header {
        background: linear-gradient(90deg, #38bdf8, #818cf8, #a855f7);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 900;
        font-size: 2.2rem;
        margin-bottom: 8px;
    }
    
    /* الشارات التوضيحية (Badges) مع تباين واضح */
    .badge {
        display: inline-block;
        padding: 5px 14px;
        border-radius: 9999px;
        font-size: 0.9rem;
        font-weight: 700;
        margin: 4px 6px;
    }
    .badge-success { background-color: #064e3b; color: #6ee7b7; border: 1px solid #059669; }
    .badge-info { background-color: #0c4a6e; color: #7dd3fc; border: 1px solid #0284c7; }
    .badge-warning { background-color: #78350f; color: #fde047; border: 1px solid #d97706; }
    .badge-danger { background-color: #7f1d1d; color: #fca5a5; border: 1px solid #dc2626; }

    /* كونسول السجلات المظلم Terminal */
    .terminal-console {
        background-color: #020617;
        border: 1px solid #1e293b;
        border-radius: 12px;
        padding: 18px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.92rem;
        color: #4ade80;
        max-height: 280px;
        overflow-y: auto;
        white-space: pre-wrap;
        line-height: 1.6;
        box-shadow: inset 0 2px 12px rgba(0,0,0,0.9);
    }

    /* ---------------------------------------------------- */
    /* تباين الأزرار البرمجية الفائق (High-Contrast Buttons) */
    /* ---------------------------------------------------- */
    div.stButton > button {
        background-color: #1e293b !important;
        color: #ffffff !important;
        border: 1px solid #475569 !important;
        border-radius: 10px !important;
        font-weight: 800 !important;
        font-size: 0.98rem !important;
        padding: 8px 18px !important;
        transition: all 0.25s ease !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4) !important;
    }
    div.stButton > button:hover {
        background-color: #334155 !important;
        color: #38bdf8 !important;
        border-color: #38bdf8 !important;
        transform: translateY(-2px);
        box-shadow: 0 6px 18px rgba(56, 189, 248, 0.3) !important;
    }

    div.stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #0284c7 0%, #2563eb 100%) !important;
        color: #ffffff !important;
        border: 1px solid #60a5fa !important;
        font-weight: 900 !important;
        font-size: 1.05rem !important;
        box-shadow: 0 4px 16px rgba(37, 99, 235, 0.5) !important;
    }
    div.stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #0369a1 0%, #1d4ed8 100%) !important;
        border-color: #93c5fd !important;
        box-shadow: 0 6px 22px rgba(37, 99, 235, 0.7) !important;
        transform: translateY(-2px);
    }

    /* حقول الإدخال والاختيار (Input Fields) */
    div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea {
        background-color: #0f172a !important;
        color: #f8fafc !important;
        border: 1px solid #334155 !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }
    div[data-baseweb="input"] input:focus, div[data-baseweb="textarea"] textarea:focus {
        border-color: #38bdf8 !important;
        box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.3) !important;
    }

    /* بطاقات الإحصائيات (Metrics) */
    div[data-testid="stMetric"] {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 14px;
    }
    div[data-testid="stMetricValue"] {
        font-weight: 900 !important;
        color: #38bdf8 !important;
    }

    /* تجاوب خاص ومخصص لشاشات الجوال */
    @media (max-width: 768px) {
        .main .block-container {
            padding: 1.5rem 0.8rem !important;
        }
        .scraper-header {
            font-size: 1.6rem !important;
        }
        .scraper-card {
            padding: 16px !important;
            border-radius: 12px !important;
        }
        section[data-testid="stSidebar"] {
            width: 88vw !important;
            max-width: 330px !important;
        }
    }
</style>
""", unsafe_allow_html=True)


# ==============================================================================
# إدارة الحالة (Session State Initialization)
# ==============================================================================

if "logs" not in st.session_state:
    st.session_state.logs = ["[النظام] مرحباً بك في Smart Novel Scraper. أدخل رابط الفهرس للبدء."]

if "active_novel" not in st.session_state:
    st.session_state.active_novel = None

if "domain_config" not in st.session_state:
    st.session_state.domain_config = None

if "chapters_cache" not in st.session_state:
    st.session_state.chapters_cache = []

if "is_scraping" not in st.session_state:
    st.session_state.is_scraping = False

if "session_controller" not in st.session_state:
    st.session_state.session_controller = None

if "last_preview_content" not in st.session_state:
    st.session_state.last_preview_content = ""

if "show_ai_fallback" not in st.session_state:
    st.session_state.show_ai_fallback = False


def add_log(message: str):
    """إضافة رسالة إلى سجل الأحداث الحي."""
    now = time.strftime("%H:%M:%S")
    formatted = f"[{now}] {message}"
    st.session_state.logs.append(formatted)
    if len(st.session_state.logs) > 100:
        st.session_state.logs.pop(0)


# ==============================================================================
# الشريط الجانبي (Sidebar: Configuration & Settings)
# ==============================================================================

with st.sidebar:
    st.markdown("## ⚙️ إعدادات النظام & AI")
    
    # 1. مجمع وسائط Google Apps Script الموزعة (Multi-GAS Pool)
    DEFAULT_POOL_STR = "\n".join(DEFAULT_GAS_POOL)
    stored_gas_pool = get_setting("gemini_gas_pool", DEFAULT_POOL_STR)
    
    with st.expander("🌐 مجمع وسائط غوغل (Multi-GAS Pool)", expanded=True):
        st.caption("الوسائط الثلاثة معتمدة وتعمل بنظام تدوير الحمل التلقائي:")
        gas_pool_input = st.text_area(
            "روابط الوسائط السحابية (رابط لكل سطر):",
            value=stored_gas_pool,
            height=110,
            placeholder="https://script.google.com/macros/s/.../exec",
            help="يتم توزيع طلبات الـ AI والـ Scraper بالتساوي على هذه السيرفرات."
        )
        if gas_pool_input != stored_gas_pool and gas_pool_input.strip():
            save_setting("gemini_gas_pool", gas_pool_input.strip())
            endpoints_list = parse_gas_pool_string(gas_pool_input)
            gas_pool.update_endpoints(endpoints_list)

        parsed_endpoints = parse_gas_pool_string(gas_pool_input)
        gas_pool.update_endpoints(parsed_endpoints)
        st.markdown(f'<span class="badge badge-success">✓ {len(parsed_endpoints)} وسائط نشطة في المجمع (Load Balancing)</span>', unsafe_allow_html=True)

    # 2. مفتاح Google Gemini API Key (اختياري - مدمج ومشفر تلقائياً في السحابة)
    stored_key = get_setting("gemini_api_key", os.getenv("GEMINI_API_KEY", ""))
    with st.expander("🔑 مفتاح Google Gemini API Key (اختياري)", expanded=False):
        api_key_input = st.text_input(
            "مفتاح API خاص بك:",
            value=stored_key,
            type="password",
            placeholder="اتركه فارغاً للاعتماد على وسيط غوغل السحابي التلقائي",
            help="إذا تركته فارغاً، سيتولى وسيط Google Apps Script السحابي تمرير المفتاح المشفر المدمج تلقائياً."
        )
        if api_key_input != stored_key:
            save_setting("gemini_api_key", api_key_input.strip())
            stored_key = api_key_input.strip()

    st.markdown('<span class="badge badge-success">✓ الذكاء الاصطناعي السحابي مفعل عبر Google Bridge</span>', unsafe_allow_html=True)

    # 3. اختيار نموذج Gemini
    ai_model = st.selectbox(
        "🧠 نموذج الذكاء الاصطناعي للتحليل الفوري",
        options=["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.6-flash"],
        index=0,
        help="نموذج Gemini 3.8 Flash هو الأحدث والأسرع عالمياً لمعالجة نصوص الـ HTML."
    )

    # أزرار الفحص والاختبار
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        test_single_btn = st.button("⚡ فحص النموذج", use_container_width=True)
    with col_t2:
        test_pool_btn = st.button("🩺 فحص المجمع", use_container_width=True)

    effective_key = api_key_input.strip() if 'api_key_input' in locals() and api_key_input.strip() else stored_key

    if test_single_btn:
        with st.spinner("جاري اختبار الاتصال بالمجمع وإرسال طلب تجريبي..."):
            ok, msg = test_gemini_connection(
                api_key=effective_key,
                model_name=ai_model
            )
            if ok:
                st.success(f"✅ {msg}")
            else:
                st.error(f"❌ فشل الاتصال:\n{msg}")

    if test_pool_btn:
        with st.spinner("جاري فحص جميع وسائط المجمع بالتوازي..."):
            pool_report = run_pool_diagnostic(api_key=effective_key, endpoints=parsed_endpoints)
            st.markdown(f"### 📊 نتائج فحص المجمع ({pool_report['online_count']}/{pool_report['total_endpoints']} متصل):")
            for item in pool_report["results"]:
                if item["ai_ok"]:
                    st.markdown(f"**خادم {item['id']}** (`{item['display_url']}`): :white_check_mark: متصل ويعمل")
                else:
                    st.markdown(f"**خادم {item['id']}** (`{item['display_url']}`): :x: {item['message']}")

    st.markdown("---")
    st.markdown("## 🛡️ إعدادات المتصفح & التخفي")
    
    headless_mode = st.toggle("تشغيل المتصفح في الخلفية (Headless)", value=True)
    
    speed_mode = st.selectbox(
        "⚡ نمط وسرعة السحب",
        options=["🚀 صاروخي (Turbo - 0.5s)", "⚡ سريع (Fast - 1.2s)", "🛡️ آمن ومتخفي (Stealth - 3.0s)", "⚙️ مخصص (Custom)"],
        index=0,
        help="النمط الصاروخي يستغل الجلسة المفتوحة لسحب الفصول في ثوانٍ معدودة."
    )

    if speed_mode.startswith("🚀"):
        default_min, default_max = 0.5, 1.0
    elif speed_mode.startswith("⚡"):
        default_min, default_max = 1.0, 2.0
    elif speed_mode.startswith("🛡️"):
        default_min, default_max = 2.5, 4.0
    else:
        default_min, default_max = 0.5, 2.0

    if speed_mode.startswith("⚙️"):
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            min_delay = st.number_input("الحد الأدنى للتأخير (ث)", min_value=0.1, max_value=15.0, value=default_min, step=0.2)
        with col_d2:
            max_delay = st.number_input("الحد الأقصى للتأخير (ث)", min_value=0.2, max_value=30.0, value=default_max, step=0.2)
    else:
        min_delay, max_delay = default_min, default_max
        st.caption(f"⏱️ التأخير النشط: {min_delay}s إلى {max_delay}s لكل فصل.")
        
    if min_delay > max_delay:
        max_delay = min_delay + 0.5

    st.markdown("---")
    with st.expander("🤖 إعدادات واجهة بوت تيليجرام (Telegram Bot)", expanded=False):
        st.markdown("**يوزر البوت المقترح:** `@SmartNovelMediaBot`")
        stored_tg_token = get_setting("telegram_bot_token", os.getenv("TELEGRAM_BOT_TOKEN", ""))
        stored_tg_user = get_setting("telegram_allowed_user", os.getenv("TELEGRAM_ALLOWED_USER", ""))
        
        tg_token_inp = st.text_input("توكن البوت (Bot Token):", value=stored_tg_token, type="password", placeholder="من @BotFather")
        tg_user_inp = st.text_input("معرف حسابك الحصري (Allowed Chat ID):", value=stored_tg_user, placeholder="اتركه فارغاً للسماح لك بالتجربة")

        if tg_token_inp != stored_tg_token:
            save_setting("telegram_bot_token", tg_token_inp.strip())
        if tg_user_inp != stored_tg_user:
            save_setting("telegram_allowed_user", tg_user_inp.strip())

        if tg_token_inp:
            st.markdown('<span class="badge badge-success">✓ تم حفظ توكن البوت بنجاح</span>', unsafe_allow_html=True)

    with st.expander("🗄️ إدارة الذاكرة المؤقتة للمواقع (Domains Cache)"):
        saved_domains = get_all_domains_config()
        if not saved_domains:
            st.info("لا توجد نطاقات محفوظة حالياً في قاعدة البيانات.")
        else:
            st.write(f"إجمالي النطاقات المسجلة: {len(saved_domains)}")
            for dom in saved_domains:
                col_d_name, col_d_del = st.columns([3, 1])
                with col_d_name:
                    st.markdown(f"**🌐 {dom['domain']}**")
                with col_d_del:
                    if st.button("🗑️", key=f"del_dom_{dom['domain']}"):
                        delete_domain_config(dom["domain"])
                        st.success(f"تم حذف {dom['domain']}")
                        st.rerun()


# ==============================================================================
# الواجهة الرئيسية (Main Application View)
# ==============================================================================

st.markdown('<div class="scraper-header">📚 Smart Novel Scraper AI</div>', unsafe_allow_html=True)
st.caption("نظام هجين ذكي لسحب فصول الروايات تلقائياً مع محرك استكشاف فوري وتحليل احتياطي بالذكاء الاصطناعي.")

# ------------------------------------------------------------------------------
# القسم 1: فحص الرواية وجلب الفهرس (نظام هجين من خطوتين)
# ------------------------------------------------------------------------------
st.markdown('<div class="scraper-card">', unsafe_allow_html=True)
st.subheader("1️⃣ فحص الرواية وجلب الفهرس")

col_url, col_btn_primary, col_btn_ai = st.columns([3, 1.4, 1.3])
with col_url:
    toc_url_input = st.text_input(
        "رابط صفحة الفهرس (Table of Contents URL)",
        placeholder="https://www.69shuba.com/book/54809.htm",
        key="toc_url"
    )
with col_btn_primary:
    st.write("")
    st.write("")
    fast_load_clicked = st.button("📑 جلب وفهرسة الفصول", use_container_width=True, type="primary")
with col_btn_ai:
    st.write("")
    st.write("")
    force_ai_clicked = st.button("🤖 تحليل متقدم بـ AI", use_container_width=True)

# معالجة استخراج الدومين والتحقق من التخزين المؤقت
if toc_url_input:
    domain_name = extract_clean_domain(toc_url_input)
    cached_config = get_domain_config(domain_name)
    if cached_config:
        st.session_state.domain_config = cached_config
        st.markdown(f'<span class="badge badge-success">✓ دومين مسجل ومعتمد: {domain_name}</span>', unsafe_allow_html=True)
    else:
        st.markdown(f'<span class="badge badge-info">ℹ️ دومين جديد: {domain_name} (سيتم فحصه تلقائياً بالخطوة 1 ثم الاستعانة بـ AI إذا تطلب الأمر)</span>', unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# معالجة الخطوة 1: الفحص والاستكشاف التلقائي السريع
# ------------------------------------------------------------------------------
if fast_load_clicked and toc_url_input:
    domain_name = extract_clean_domain(toc_url_input)
    with st.spinner("جاري فحص الموقع واستخراج قائمة الفصول تلقائياً..."):
        try:
            # 1. إذا كان الدومين محفوظاً مسبقاً، نستخدم محدداته فوراً
            current_config = get_domain_config(domain_name)
            
            if not current_config:
                add_log(f"🔍 دومين جديد [{domain_name}].. جاري الفحص والاستكشاف الهجين السريع...")
                toc_html, ch_html, detected_title = fetch_samples_for_gemini_analysis(toc_url_input)
                
                # تطبيق خوارزمية الاستكشاف الهجين المحلي السريع
                h_res = auto_detect_selectors_heuristically(toc_html, ch_html)
                save_domain_config(
                    domain=domain_name,
                    toc_link_selector=h_res["toc_link_selector"],
                    chapter_title_selector=h_res["chapter_title_selector"],
                    chapter_content_selector=h_res["chapter_content_selector"],
                    purge_selectors=h_res["purge_selectors"],
                    notes="تم الاكتشاف تلقائياً عبر المحرك الهجين السريع"
                )
                current_config = get_domain_config(domain_name)
                st.session_state.domain_config = current_config

            toc_sel = current_config["toc_link_selector"]
            add_log(f"جاري سحب قائمة الفصول باستخدام المحدد: {toc_sel}")
            chapters_list, novel_title = crawl_toc_chapters(toc_url_input, toc_sel)

            # إذا نجح السحب ووجد الفصول
            if chapters_list and len(chapters_list) > 0:
                novel = get_or_create_novel(toc_url=toc_url_input, title=novel_title, domain=domain_name)
                total_synced = sync_chapter_manifest(novel["id"], chapters_list)
                st.session_state.active_novel = novel
                st.session_state.chapters_cache = get_chapters(novel["id"])
                st.session_state.show_ai_fallback = False
                add_log(f"✅ تم بنجاح جلب وفهرسة {total_synced} فصلاً للرواية: '{novel_title}'")
                st.success(f"🎉 تم جلب {total_synced} فصلاً بنجاح!")
                st.rerun()
            else:
                # إذا تعثر الفحص التلقائي، نقترح تفعيل خطوة الذكاء الاصطناعي
                st.session_state.show_ai_fallback = True
                add_log("⚠️ لم يتم العثور على فصول بالمحدد الأولي. يمكنك الآن تفعيل الذكاء الاصطناعي لتحليل الصفحة.")
                st.warning("⚠️ تعذر اكتشاف قائمة الفصول بالنمط السريع. اضغط على 'تحليل متقدم بـ AI' لاستخراج الهيكل بدقة.")
        except Exception as ex:
            st.session_state.show_ai_fallback = True
            err_msg = str(ex) if str(ex).strip() else repr(ex)
            add_log(f"❌ تعثر الفحص التلقائي: {err_msg}")
            st.warning(f"تعثر الفحص التلقائي: {err_msg}\nيرجى تجربة 'تحليل متقدم بـ AI'.")

# ------------------------------------------------------------------------------
# معالجة الخطوة 2: التحليل المتقدم بالذكاء الاصطناعي (Gemini AI Fallback)
# ------------------------------------------------------------------------------
if (force_ai_clicked or st.session_state.show_ai_fallback) and toc_url_input:
    if force_ai_clicked:
        with st.spinner("جاري استخراج كود DOM وتحليله عبر Gemini AI لاستخراج أدق المحددات..."):
            try:
                add_log(f"🤖 جاري تشغيل تحليل الذكاء الاصطناعي ({ai_model}) لموقع {toc_url_input}...")
                toc_html, ch_html, detected_title = fetch_samples_for_gemini_analysis(toc_url_input)
                
                analysis_result = analyze_site_dom_with_gemini(
                    toc_html=toc_html,
                    chapter_html=ch_html,
                    api_key=effective_key,
                    model_name=ai_model,
                    gas_url=gas_url_input
                )

                domain_name = extract_clean_domain(toc_url_input)
                save_domain_config(
                    domain=domain_name,
                    toc_link_selector=analysis_result["toc_link_selector"],
                    chapter_title_selector=analysis_result["chapter_title_selector"],
                    chapter_content_selector=analysis_result["chapter_content_selector"],
                    purge_selectors=analysis_result.get("purge_selectors", []),
                    notes=analysis_result.get("notes", "")
                )
                
                st.session_state.domain_config = get_domain_config(domain_name)
                add_log(f"✅ تم تحليل وتخزين محددات الذكاء الاصطناعي للدومين {domain_name}.")
                
                # جلب الفصول بالمحددات الجديدة
                toc_sel = analysis_result["toc_link_selector"]
                chapters_list, novel_title = crawl_toc_chapters(toc_url_input, toc_sel)
                if chapters_list:
                    novel = get_or_create_novel(toc_url=toc_url_input, title=novel_title, domain=domain_name)
                    total_synced = sync_chapter_manifest(novel["id"], chapters_list)
                    st.session_state.active_novel = novel
                    st.session_state.chapters_cache = get_chapters(novel["id"])
                    st.session_state.show_ai_fallback = False
                    add_log(f"✅ تم استخراج {total_synced} فصلاً بنجاح عبر Gemini AI!")
                    st.success(f"🎉 تم تحليل الموقع وجلب {total_synced} فصلاً بنجاح!")
                    st.rerun()
                else:
                    st.error("تم تحليل الموقع ولكن لم يتم العثور على روابط فصول. يمكنك تعديل المحددات يدوياً أدناه.")
            except Exception as ex_ai:
                err_ai = str(ex_ai) if str(ex_ai).strip() else repr(ex_ai)
                st.error(f"خطأ أثناء تحليل AI: {err_ai}")
                add_log(f"❌ خطأ AI: {err_ai}")

# عرض وتعديل محددات الـ CSS المستخرجة
if st.session_state.domain_config:
    with st.expander("🛠️ مراجعة وتعديل محددات CSS يدوياً (DOM Selectors Config)"):
        c_sel = st.session_state.domain_config
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            t_link_sel = st.text_input("محدد روابط الفصول (TOC Link Selector)", value=c_sel.get("toc_link_selector", ""))
            c_title_sel = st.text_input("محدد عنوان الفصل (Chapter Title Selector)", value=c_sel.get("chapter_title_selector", ""))
        with col_s2:
            c_content_sel = st.text_input("محدد نص الفصل (Chapter Content Selector)", value=c_sel.get("chapter_content_selector", ""))
            p_sels = st.text_area("محددات عناصر الحذف (Purge Selectors - سطر لكل محدد)", value="\n".join(c_sel.get("purge_selectors", [])))
        
        if st.button("💾 حفظ التعديلات اليدوية للمحددات"):
            purge_list = [p.strip() for p in p_sels.split("\n") if p.strip()]
            save_domain_config(
                domain=c_sel["domain"],
                toc_link_selector=t_link_sel,
                chapter_title_selector=c_title_sel,
                chapter_content_selector=c_content_sel,
                purge_selectors=purge_list,
                notes="تم التعديل يدوياً من قبل المستخدم"
            )
            st.session_state.domain_config = get_domain_config(c_sel["domain"])
            st.success("تم تحديث المحددات بنجاح!")

st.markdown('</div>', unsafe_allow_html=True)


# ------------------------------------------------------------------------------
# القسم 1.5: ذاكرة الروايات المحفوظة على السيرفر (Server Novel Storage)
# ------------------------------------------------------------------------------
st.markdown('<div class="scraper-card">', unsafe_allow_html=True)
st.subheader("📦 ذاكرة الروايات المحفوظة على السيرفر")
st.caption("كل الروايات التي تم سحبها وحفظها مسبقاً في قاعدة بيانات السيرفر. يمكنك استعادة أو تصدير أو حذف أي رواية.")

all_novels = get_all_novels()
if not all_novels:
    st.info("🔍 لا توجد روايات محفوظة على السيرفر حالياً. ابدأ بسحب رواية جديدة!")
else:
    st.markdown(f'<span class="badge badge-info">📚 إجمالي الروايات المخزنة: {len(all_novels)}</span>', unsafe_allow_html=True)
    
    for novel_item in all_novels:
        n_id = novel_item["id"]
        n_title = novel_item["title"] or "بدون عنوان"
        n_domain = novel_item["domain"] or "غير محدد"
        n_total = novel_item["total_chapters"] or 0
        n_downloaded = novel_item["downloaded"] or 0
        n_pending = novel_item["pending"] or 0
        n_failed = novel_item["failed"] or 0
        n_date = novel_item.get("created_at", "")[:10] if novel_item.get("created_at") else "-"
        
        # تحديد لون الحالة
        if n_downloaded == n_total and n_total > 0:
            status_badge = '<span class="badge badge-success">✅ مكتملة</span>'
        elif n_downloaded > 0:
            status_badge = f'<span class="badge badge-warning">⏳ جزئي ({n_downloaded}/{n_total})</span>'
        else:
            status_badge = '<span class="badge badge-info">📝 معلقة</span>'
        
        with st.expander(f"📖 {n_title}  |  🌐 {n_domain}  |  📊 {n_downloaded}/{n_total} فصل", expanded=False):
            # معلومات الرواية
            info_col1, info_col2, info_col3, info_col4 = st.columns(4)
            info_col1.metric("الفصول الكلية", n_total)
            info_col2.metric("تم التنزيل", n_downloaded)
            info_col3.metric("معلقة", n_pending)
            info_col4.metric("فاشلة", n_failed)
            
            st.markdown(f'{status_badge} | 📅 تاريخ الإنشاء: **{n_date}** | 🔗 [{n_domain}]({novel_item.get("toc_url", "#")})', unsafe_allow_html=True)
            
            # أزرار التحكم
            btn_col1, btn_col2, btn_col3 = st.columns(3)
            
            with btn_col1:
                if st.button("📂 تحميل واستعادة", key=f"load_novel_{n_id}", use_container_width=True):
                    loaded_novel = {"id": n_id, "title": n_title, "domain": n_domain, "toc_url": novel_item.get("toc_url", ""), "total_chapters": n_total}
                    st.session_state.active_novel = loaded_novel
                    st.session_state.chapters_cache = get_chapters(n_id)
                    # تحميل إعدادات الدومين
                    domain_cfg = get_domain_config(n_domain)
                    if domain_cfg:
                        st.session_state.domain_config = domain_cfg
                    add_log(f"📂 تم تحميل الرواية '{n_title}' من ذاكرة السيرفر.")
                    st.success(f"✅ تم تحميل '{n_title}' بنجاح! يمكنك الآن متابعة السحب أو التصدير.")
                    st.rerun()
            
            with btn_col2:
                if n_downloaded > 0:
                    exported_txt, exp_count = export_novel_to_text(n_id)
                    if exp_count > 0:
                        file_name = f"{n_title.replace(' ', '_')}_full.txt"
                        st.download_button(
                            label=f"💾 تصدير TXT ({exp_count} فصل)",
                            data=exported_txt.encode("utf-8"),
                            file_name=file_name,
                            mime="text/plain; charset=utf-8",
                            use_container_width=True,
                            key=f"export_novel_{n_id}"
                        )
                else:
                    st.button("💾 لا توجد فصول للتصدير", key=f"export_novel_{n_id}", disabled=True, use_container_width=True)
            
            with btn_col3:
                if st.button("🗑️ حذف من السيرفر", key=f"delete_novel_{n_id}", use_container_width=True):
                    delete_novel(n_id)
                    add_log(f"🗑️ تم حذف الرواية '{n_title}' وجميع فصولها من السيرفر نهائياً.")
                    if st.session_state.active_novel and st.session_state.active_novel.get("id") == n_id:
                        st.session_state.active_novel = None
                        st.session_state.chapters_cache = []
                    st.success(f"🗑️ تم حذف '{n_title}' نهائياً من السيرفر!")
                    st.rerun()

st.markdown('</div>', unsafe_allow_html=True)


# ------------------------------------------------------------------------------
# القسم 2: لوحة تحكم السحب والإدارة
# ------------------------------------------------------------------------------
if st.session_state.active_novel:
    novel = st.session_state.active_novel
    novel_stats = get_novel_stats(novel["id"])
    total_ch = novel_stats["total"]
    
    st.markdown('<div class="scraper-card">', unsafe_allow_html=True)
    st.subheader(f"2️⃣ لوحة تحكم السحب: {novel['title']}")
    
    # مقاييس الرواية
    stat_c1, stat_c2, stat_c3, stat_c4 = st.columns(4)
    stat_c1.metric("إجمالي الفصول المكتشفة", total_ch)
    stat_c2.metric("فصول تم تنزيلها", novel_stats["downloaded"])
    stat_c3.metric("فصول معلقة", novel_stats["pending"])
    stat_c4.metric("فصول متعثرة", novel_stats["failed"])

    st.markdown("---")

    # تحديد نطاق الفصول المراد سحبها
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        from_chap = st.number_input("من الفصل رقم:", min_value=1, max_value=max(1, total_ch), value=1, key="from_chap_input")
    with col_r2:
        default_to_chap = max(from_chap, max(1, total_ch))
        to_chap = st.number_input("إلى الفصل رقم:", min_value=from_chap, max_value=max(1, total_ch), value=default_to_chap, key="to_chap_input")

    # أزرار التحكم في السحب
    col_ctrl1, col_ctrl2, col_ctrl3, col_ctrl4 = st.columns(4)
    with col_ctrl1:
        start_scrape = st.button("🚀 بدء سحب الفصول", use_container_width=True, type="primary", disabled=st.session_state.is_scraping)
    with col_ctrl2:
        pause_resume = st.button("⏸️ إيقاف مؤقت / استئناف", use_container_width=True)
    with col_ctrl3:
        stop_scrape = st.button("⏹️ إيقاف السحب", use_container_width=True)
    with col_ctrl4:
        clear_data_btn = st.button("🧹 تصفير بيانات الفصول", use_container_width=True)

    if clear_data_btn:
        clear_novel_chapters_data(novel["id"])
        st.session_state.chapters_cache = get_chapters(novel["id"])
        add_log("تم تصفير محتوى الفصول للبدء من جديد.")
        st.success("تم تصفير بيانات الفصول بنجاح!")
        st.rerun()

    # التحقق من وجود عملية سحب نشطة بالخلفية لهذه الرواية
    is_bg_running = novel["id"] in ACTIVE_BACKGROUND_TASKS
    bg_session = ACTIVE_BACKGROUND_TASKS.get(novel["id"])

    # معالجة زر الإيقاف المؤقت
    if pause_resume:
        active_ctrl = bg_session or st.session_state.session_controller
        if active_ctrl:
            active_ctrl.toggle_pause()
            status_word = "إيقاف مؤقت" if active_ctrl.is_paused else "استئناف"
            add_log(f"تم الضغط على: {status_word}")
            st.info(f"حالة السحب الآن: {status_word}")
            st.rerun()

    # معالجة زر الإيقاف التام
    if stop_scrape:
        active_ctrl = bg_session or st.session_state.session_controller
        if active_ctrl:
            active_ctrl.stop()
            ACTIVE_BACKGROUND_TASKS.pop(novel["id"], None)
            add_log("تم إيقاف عملية السحب بالكامل.")
            st.warning("تم إيقاف السحب بنجاح.")
            st.rerun()

    # بدء عملية السحب السحابية في الخلفية
    if start_scrape:
        all_chaps = get_chapters(novel["id"])
        target_chapters = [c for c in all_chaps if from_chap <= c["chapter_number"] <= to_chap]
        if len(target_chapters) == 0:
            st.warning("لا توجد فصول ضمن النطاق المحدد!")
        else:
            cfg = st.session_state.domain_config or get_domain_config(novel["domain"])
            add_log(f"🚀 بدء سحب {len(target_chapters)} فصلاً في خيط خلفي مستقل (حتى لو أغلقت الصفحة)...")
            bg_sess = start_background_scraping(
                novel_id=novel["id"],
                from_chapter=from_chap,
                to_chapter=to_chap,
                domain_config=cfg,
                min_delay=min_delay,
                max_delay=max_delay,
                headless=headless_mode
            )
            st.session_state.session_controller = bg_sess
            st.session_state.is_scraping = True
            st.rerun()

    # عرض حالة السحب الحية إذا كانت المهمة قيد التشغيل بالخلفية
    if is_bg_running and bg_session:
        st.markdown('<div class="badge badge-info">⚡ جاري السحب في الخلفية الآن (يمكنك إغلاق المتصفح بأمان)</div>', unsafe_allow_html=True)
        chaps_in_scope = [c for c in get_chapters(novel["id"]) if from_chap <= c["chapter_number"] <= to_chap]
        done_cnt = sum(1 for c in chaps_in_scope if c["status"] == "downloaded")
        tot_cnt = max(1, len(chaps_in_scope))
        progress_val = min(1.0, done_cnt / tot_cnt)
        st.progress(progress_val)
        st.caption(f"📊 المكتمل: {done_cnt} من أصل {tot_cnt} فصول ({int(progress_val * 100)}%)")
        time.sleep(2.0)
        st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)


# ------------------------------------------------------------------------------
# القسم 3: سجل الأحداث الحي وتصدير الملفات والمعاينة
# ------------------------------------------------------------------------------
st.markdown('<div class="scraper-card">', unsafe_allow_html=True)
st.subheader("3️⃣ سجل الأحداث المباشر & التصدير النهائي")

tab_logs, tab_export, tab_preview, tab_media, tab_nsw = st.tabs(["📟 Live Console Log", "📥 تصدير الرواية .TXT", "📖 معاينة الفصول", "🎬 محمل وتجزئة الوسائط", "🩹 استصلاح فصول المدونة"])

with tab_logs:
    st.markdown(f'<div class="terminal-console">{"\n".join(st.session_state.logs[-18:])}</div>', unsafe_allow_html=True)

with tab_export:
    if st.session_state.active_novel:
        novel_id = st.session_state.active_novel["id"]
        novel_title = st.session_state.active_novel["title"]
        
        col_exp1, col_exp2 = st.columns([2, 2])
        with col_exp1:
            export_from = st.number_input("تصدير من الفصل:", min_value=1, max_value=max(1, total_ch), value=1, key="exp_from")
        with col_exp2:
            default_export_to = max(export_from, max(1, total_ch))
            export_to = st.number_input("إلى الفصل:", min_value=export_from, max_value=max(1, total_ch), value=default_export_to, key="exp_to")

        exported_text, count_exported = export_novel_to_text(novel_id, from_chapter=export_from, to_chapter=export_to)
        
        if count_exported > 0:
            st.markdown(f'<span class="badge badge-success">جاهز للتنزيل: {count_exported} فصلاً مكتملاً</span>', unsafe_allow_html=True)
            
            with st.expander("👁️ معاينة هيكل التصدير القياسي"):
                preview_sample = exported_text[:1200] + ("\n\n... [بقية المحتوى المنظم]" if len(exported_text) > 1200 else "")
                st.code(preview_sample, language="text")

            file_name = f"{novel_title.replace(' ', '_')}_chapters_{export_from}_to_{export_to}.txt"
            st.download_button(
                label=f"💾 تحميل ملف الرواية (.TXT) - {count_exported} فصول",
                data=exported_text.encode("utf-8"),
                file_name=file_name,
                mime="text/plain; charset=utf-8",
                use_container_width=True,
                type="primary"
            )
        else:
            st.info("لا توجد فصول تم تنزيلها بعد في هذا النطاق. ابدأ السحب أولاً!")
    else:
        st.info("قم باختيار رواية وسحب فصولها لتتمكن من تصدير الملف النهائي.")

with tab_preview:
    if st.session_state.last_preview_content:
        st.markdown("#### 📄 عينة من آخر فصل تم سحبه:")
        st.text_area("محتوى الفصل المنظف:", value=st.session_state.last_preview_content, height=280)
    elif st.session_state.active_novel:
        chapters = get_chapters(st.session_state.active_novel["id"])
        downloaded_chaps = [c for c in chapters if c["status"] == "downloaded" and c["content"]]
        if downloaded_chaps:
            sample_ch = downloaded_chaps[-1]
            st.markdown(f"#### 📄 الفصل رقم {sample_ch['chapter_number']}: {sample_ch['title']}")
            st.text_area("محتوى الفصل المنظف:", value=sample_ch["content"], height=280)
        else:
            st.info("لم يتم تنزيل أي فصل بعد للمعاينة.")
    else:
        st.info("ابدأ بسحب الرواية لمشاهدة المعاينة الحية هنا.")

with tab_media:
    st.markdown("### 🎬 محمل الوسائط وتجزئة الفيديوهات الذكي")
    st.caption("تحميل الفيديوهات من يوتيوب ومنصات التواصل، مع دعم التجزئة التلقائية للفيديوهات الكبيرة (>1GB)، والترجمة الذكية عبر Gemini 3.8 Flash.")

    video_url_input = st.text_input("🔗 رابط الفيديو أو الوسائط:", placeholder="https://www.youtube.com/watch?v=... أو أي رابط فيديو")
    
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        media_mode = st.radio("نوع التحميل:", ["فيديو MP4", "صوت فقط MP3"], horizontal=True)
    with col_m2:
        auto_split = st.checkbox("تجزئة الفيديوهات الكبيرة تلقائياً (<500MB للأجزاء)", value=True)

    with st.expander("📲 إرسال تلقائي إلى تيليجرام (اختياري)"):
        st.caption("أدخل بيانات البوت الخاص بك ليصلك الفيديو في رسالة خاصة فور انتهاء التحميل:")
        tg_bot_token = st.text_input("توكن البوت (Bot Token):", placeholder="123456:ABC-DEF...", type="password")
        tg_chat_id = st.text_input("معرف المحادثة (Chat ID):", placeholder="123456789")

    if st.button("🚀 بدء فحص وتنزيل الفيديو", type="primary", use_container_width=True):
        if not video_url_input:
            st.warning("يرجى إدخال رابط الفيديو أولاً!")
        else:
            with st.spinner("جاري فحص وتنزيل الفيديو عبر المحرك السحابي..."):
                extract_audio = (media_mode == "صوت فقط MP3")
                res = download_media_file(video_url_input, extract_audio=extract_audio)
                if res.get("success"):
                    fpath = res["filepath"]
                    st.success(f"🎉 تم تحميل: '{res['title']}' بنجاح! (الحجم: {res['filesize_mb']} MB)")
                    
                    # تجزئة الفيديو إذا كان كبيراً وطلب المستخدم ذلك
                    if auto_split and res["filesize_mb"] > 450:
                        st.info("جاري تجزئة الملف لضمان سهولة التحميل وتجاوز قيود الذاكرة...")
                        parts = split_video_lossless(fpath, max_part_mb=450)
                        st.write(f"تم تقسيم الفيديو إلى {len(parts)} أجزاء:")
                        for p_idx, p_file in enumerate(parts, 1):
                            with open(p_file, "rb") as f_data:
                                p_name = os.path.basename(p_file)
                                st.download_button(f"📥 تحميل الجزء {p_idx} ({p_name})", data=f_data.read(), file_name=p_name, key=f"dl_part_{p_idx}")
                    else:
                        with open(fpath, "rb") as f_data:
                            v_name = os.path.basename(fpath)
                            st.download_button(f"📥 تحميل الملف المكتمل ({v_name})", data=f_data.read(), file_name=v_name, type="primary", use_container_width=True)

                    # إرسال اختياري إلى تيليجرام
                    if tg_bot_token and tg_chat_id:
                        with st.spinner("جاري الإرسال إلى محادثة تيليجرام..."):
                            ok_tg, msg_tg = send_to_telegram(tg_bot_token, tg_chat_id, fpath, caption=f"🎬 {res['title']}")
                            if ok_tg:
                                st.success("✅ " + msg_tg)
                            else:
                                st.warning("⚠️ تيليجرام: " + msg_tg)
                else:
                    st.error(f"❌ تعذر تحميل الفيديو: {res.get('error')}")

with tab_nsw:
    st.markdown("### 🩹 منظومة استصلاح وعلاج الفصول المبتورة (NSW Truncation Healer)")
    st.caption("يقوم هذا النظام بفحص فصول المدونة المنشورة، ورصد أي فصل ناقص أو مبتور، وسحبه من المصدر الأصلي، وترجمته وتدقيقه، وتحديث المنشور في مكانه على Blogger.")

    col_n1, col_n2 = st.columns([2, 1])
    with col_n1:
        target_novel_filter = st.text_input("اسم الرواية المراد فحصها (اتركه فارغاً لفحص الكل):", value="After Severing Ties")
    with col_n2:
        min_chars_thresh = st.number_input("الحد الأدنى لعدد الأحرف (أقل منه = مبتور):", min_value=100, max_value=5000, value=800, step=100)

    col_btn_scan, col_btn_heal = st.columns(2)
    with col_btn_scan:
        scan_clicked = st.button("🔍 فحص الفصول المبتورة الآن", use_container_width=True, type="primary")
    with col_btn_heal:
        heal_auto_clicked = st.button("🚀 استصلاح وتحديث الفصول المكتشفة", use_container_width=True)

    if scan_clicked:
        with st.spinner("جاري فحص فصول المدونة المنشورة عبر التغذية الحية..."):
            detected = nsw_healer_engine.scan_for_truncated_chapters(
                novel_name=target_novel_filter.strip() if target_novel_filter.strip() else None,
                min_length=min_chars_thresh
            )
            st.session_state["nsw_detected_broken"] = detected
            if detected:
                st.warning(f"⚠️ تم رصد {len(detected)} فصول مبتورة تعاني من نقص المحتوى!")
                for b in detected:
                    st.markdown(f"- 📖 **{b['title']}** (الحجم: `{b['content_length']}` حرف) ➔ [رابط التدوينة]({b['post_url']})")
            else:
                st.success("✅ جميع الفصول المنشورة كاملة وسليمة 100% ولا يوجد أي بتر!")

    if heal_auto_clicked:
        broken_items = st.session_state.get("nsw_detected_broken", [])
        if not broken_items:
            st.info("اضغط على 'فحص الفصول المبتورة الآن' أولاً لرصد الفصول المحتاجة للعلاج.")
        else:
            with st.spinner(f"جاري سحب وترجمة واستصلاح {len(broken_items)} فصول وتحديث Blogger..."):
                h_count = 0
                for item in broken_items:
                    res_h = nsw_healer_engine.heal_truncated_chapter(item)
                    if res_h.get("success"):
                        h_count += 1
                        st.success(f"✅ تم استصلاح: {res_h.get('title')}")
                    else:
                        st.error(f"❌ تعذر استصلاح {item.get('title')}: {res_h.get('error')}")
                st.balloons()
                st.success(f"🎉 اكتمل الاستصلاح: تم علاج وتحديث {h_count} فصول بنجاح على المدونة!")

    st.markdown("---")
    st.markdown("#### 🧩 كشف وسد فجوات الفصول المفقودة (Automatic Gap-Filler)")
    st.caption("يفحص كافة الجداول وبلوجر، وإذا وجد قفزة في الترقيم، يسحب الفصل المفقود ويترجمه وينشره ويربط أزرار السابق والتالي تلقائياً.")

    col_g1, col_g2 = st.columns(2)
    with col_g1:
        scan_gaps_clicked = st.button("🔍 فحص الفجوات المفقودة", use_container_width=True)
    with col_g2:
        fill_gaps_clicked = st.button("🚀 ملء الفجوات المفقودة ونشرها", use_container_width=True, type="primary")

    if scan_gaps_clicked:
        with st.spinner("جاري فحص كافة الجداول وبلوجر لكشف الفجوات..."):
            gaps_found = nsw_healer_engine.detect_system_gaps(target_novel_filter.strip() if target_novel_filter.strip() else None)
            st.session_state["nsw_gaps_found"] = gaps_found
            if gaps_found:
                st.warning(f"⚠️ تم رصد فجوات مفقودة في تسلسل الروايات!")
                for g in gaps_found:
                    st.markdown(f"- 📖 **{g['novel_name']}**: مفقود الفصول **{g['missing_chapters']}** (بين الفصل {g['prev_chapter']} والفصل {g['next_chapter']})")
            else:
                st.success("✅ جميع الفصول متسلسلة عبر كافة الجداول وبلوجر ولا توجد أي فجوة مفقودة!")

    if fill_gaps_clicked:
        with st.spinner("جاري سحب وترجمة ونشر الفصول المفقودة وربط أزرار التنقل..."):
            filled_cnt = nsw_healer_engine.run_auto_fill_all_gaps(target_novel_filter.strip() if target_novel_filter.strip() else None)
            if filled_cnt > 0:
                st.balloons()
                st.success(f"🎉 تم بنجاح ملء ونشر {filled_cnt} فصول مفقودة وتحديث أزرار التنقل!")
            else:
                st.info("لا توجد فجوات مفقودة لملئها حالياً.")

    st.markdown("---")
    st.markdown("#### 🎯 ميزة إصلاح الفصل المخصص X (Fix Specific Chapter)")
    st.caption("حدد اسم الرواية ورقم الفصل، ليقوم السيرفر بسحبه فورياً من المصدر، وترجمته وتدقيقه، وتحديثه في مكانه أو نشره.")

    col_fix_n, col_fix_num = st.columns([3, 1])
    with col_fix_n:
        fix_novel_inp = st.text_input("اسم الرواية للإصلاح المباشر:", value="After Severing Ties", key="fix_novel_inp")
    with col_fix_num:
        fix_chap_num_inp = st.number_input("رقم الفصل المستهدف (X):", min_value=1, max_value=99999, value=456, step=1, key="fix_chap_num_inp")

    fix_custom_toc = st.text_input("رابط الفهرس الأصلي (اختياري - يترك فارغاً للاستعلام التلقائي من الجدول):", value="", placeholder="https://www.69shuba.com/book/54809.htm")

    if st.button("🚀 سحب وإصلاح وتحديث هذا الفصل الآن", use_container_width=True, type="primary"):
        with st.spinner(f"جاري جلب الفصل {fix_chap_num_inp} لرواية '{fix_novel_inp}' من المصدر وترجمته وتحديثه..."):
            fix_res = nsw_healer_engine.fix_single_chapter_x(
                novel_name=fix_novel_inp.strip(),
                chapter_number=int(fix_chap_num_inp),
                custom_toc_url=fix_custom_toc.strip() if fix_custom_toc.strip() else None
            )
            if fix_res.get("success"):
                st.balloons()
                st.success(f"🎉 تم بنجاح إصلاح واعتماد الفصل {fix_chap_num_inp}: {fix_res.get('title')}")
            else:
                st.error(f"❌ تعذر إصلاح الفصل: {fix_res.get('error')}")

st.markdown('</div>', unsafe_allow_html=True)
