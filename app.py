# -*- coding: utf-8 -*-
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
    sync_chapter_manifest,
    save_chapter_content,
    get_chapters,
    get_novel_stats,
    clear_novel_chapters_data,
    delete_novel,
    export_novel_to_text,
    get_setting,
    save_setting,
    update_novel_title,
    get_all_novels
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
import scraper_engine
from scraper_engine import (
    extract_clean_domain,
    PlaywrightStealthBrowser,
    crawl_toc_chapters,
    fetch_samples_for_gemini_analysis,
    NovelScrapingSession,
    extract_chapter_title,
    clean_chapter_content,
    start_background_scraping,
    ACTIVE_BACKGROUND_TASKS,
    check_cdp_available,
    calculate_missing_gaps,
    trigger_cloud_sheet_sorting,
    compare_and_heal_chapter,
    scan_sheet_extreme_outliers,
    heal_sheet_extreme_outliers
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
import telegram_bot as _tg_bot_module
import ui_syndication_tabs

# إطلاق بوت تليجرام الذكي (البوت الرئيسي) في الخلفية مرة واحدة فقط
# ملاحظة: nsw_bot_bridge معطل لتجنب التعارض مع البوت الرئيسي على نفس التوكن
if "tg_bot_started" not in st.session_state:
    try:
        import threading as _tg_threading
        _tg_thread = _tg_threading.Thread(
            target=_tg_bot_module.run_telegram_bot_loop,
            daemon=True,
            name="TelegramBotPolling"
        )
        _tg_thread.start()
        st.session_state.tg_bot_started = True
    except Exception as _tg_err:
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

# محاولة تحميل الرواية النشطة تلقائياً إذا وجدت في قاعدة البيانات
if st.session_state.active_novel is None:
    try:
        all_n = get_all_novels()
        for nov in all_n:
            st_info = get_novel_stats(nov["id"])
            if st_info.get("downloaded", 0) > 0:
                st.session_state.active_novel = nov
                st.session_state.chapters_cache = get_chapters(nov["id"])
                st.session_state.domain_config = get_domain_config(nov["domain"])
                break
    except Exception:
        pass

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
        # توفير أول رابط سحابي كافتراضي لاستخدامه عند الحاجة
        gas_url_input = parsed_endpoints[0] if parsed_endpoints else None
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
        options=["gemini-3.6-flash", "gemini-3.8-flash", "gemini-2.5-pro", "gemini-3.5-flash-lite"],
        index=0,
        help="اختر النموذج الأنسب لمعالجة نصوص الـ HTML واستخراج المحددات."
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

# محدد التبويبات الرئيسي
main_nav_tab = st.radio(
    "اختر لوحة العمل:",
    ["📚 محرك السحب والاستكشاف والترجمة (الرئيسي)", "🏛️ نادي الروايات (Rewayat Club)", "🟧 واتباد (Wattpad)"],
    index=0,
    horizontal=True,
    label_visibility="collapsed"
)

st.markdown("---")

if main_nav_tab == "🏛️ نادي الروايات (Rewayat Club)":
    ui_syndication_tabs.render_rewayat_club_tab()
    st.stop()
elif main_nav_tab == "🟧 واتباد (Wattpad)":
    ui_syndication_tabs.render_wattpad_tab()
    st.stop()

is_cdp_connected = check_cdp_available("http://localhost:9222")
cdp_param = "http://localhost:9222" if is_cdp_connected else None

if is_cdp_connected:
    st.markdown('<div style="background-color:#064e3b; border:1px solid #059669; border-radius:10px; padding:9px 16px; margin-bottom:16px; color:#6ee7b7; font-size:0.92rem; font-weight:bold;">🟢 <b>جسر متصفح المشرف (CDP Port 9222) متصل:</b> صمام تجاوز Cloudflare والتحميل الديناميكي نشط ويعمل تلقائياً.</div>', unsafe_allow_html=True)
else:
    st.markdown('<div style="background-color:#1e293b; border:1px solid #334155; border-radius:10px; padding:9px 16px; margin-bottom:16px; color:#94a3b8; font-size:0.90rem;">☁️ <b>النمط السحابي:</b> للمواقع المحمية بـ Cloudflare (مثل botitranslation)، شغّل ملف <code>تشغيل_المتصفح_المفتوح.bat</code> واستخدم التطبيق محلياً.</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# القسم 1: فحص الرواية وجلب الفهرس (نظام هجين من خطوتين)
# ------------------------------------------------------------------------------
st.markdown('<div class="scraper-card">', unsafe_allow_html=True)
st.subheader("1️⃣ فحص الرواية وجلب الفهرس")

# اختيار رواية سابقة للبدء فوراً دون إعادة إدخال الرابط
saved_novels = get_all_novels()
if saved_novels:
    novel_options = {}
    default_select_idx = 0
    for idx, n in enumerate(saved_novels):
        st_info = get_novel_stats(n["id"])
        label = f"📖 {n['title']} (معرف #{n['id']} | {st_info.get('downloaded', 0)}/{n.get('total_chapters', 0)} فصلاً)"
        novel_options[label] = n
        if st.session_state.active_novel and st.session_state.active_novel["id"] == n["id"]:
            default_select_idx = idx

    selected_label = st.selectbox(
        "📚 اختيار رواية سابقة للمتابعة فوراً دون إعادة إدخال الرابط:",
        options=list(novel_options.keys()),
        index=default_select_idx,
        key="novel_picker_select"
    )
    chosen_novel = novel_options[selected_label]
    if not st.session_state.active_novel or st.session_state.active_novel["id"] != chosen_novel["id"]:
        st.session_state.active_novel = chosen_novel
        st.session_state.chapters_cache = get_chapters(chosen_novel["id"])
        st.session_state.domain_config = get_domain_config(chosen_novel["domain"])
        st.rerun()

initial_toc_url = st.session_state.active_novel["toc_url"] if st.session_state.active_novel else ""
initial_novel_title = st.session_state.active_novel["title"] if st.session_state.active_novel else ""

col_url, col_novel_name = st.columns([2, 1.5])
with col_url:
    toc_url_input = st.text_input(
        "🔗 رابط صفحة الفهرس (Table of Contents URL):",
        value=initial_toc_url,
        placeholder="https://www.69shuba.com/book/54809.htm",
        key="toc_url"
    )
with col_novel_name:
    custom_novel_title_input = st.text_input(
        "🏷️ اسم الرواية (الذي سيوضع في العمود C بالشيت):",
        value=initial_novel_title,
        placeholder="مثال: After Severing Ties",
        key="custom_novel_title",
        help="اكتب اسم الرواية هنا ليتم اعتماده وتفريغ الفصول في Google Sheet بهذا الاسم بدلاً من العنوان التلقائي للموقع."
    )

col_btn_primary, col_btn_ai, col_btn_deep = st.columns([1.2, 1.1, 1.1])
with col_btn_primary:
    fast_load_clicked = st.button("📑 جلب وفهرسة الفصول", use_container_width=True, type="primary")
with col_btn_ai:
    force_ai_clicked = st.button("🤖 استكشاف هجين & AI", use_container_width=True, help="فحص سريع وتحليل بالذكاء الاصطناعي الخفيف")
with col_btn_deep:
    deep_ai_clicked = st.button("🧠 طلبك للتحليل المعماري العميق (Pro)", use_container_width=True, help="تحليل معماري شامل بكامل قدرة الذكاء الاصطناعي المتقدم والـ DOM الهندسي")

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
                toc_html, ch_html, detected_title = fetch_samples_for_gemini_analysis(toc_url_input, cdp_url=cdp_param)
                
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
            chapters_list, novel_title = crawl_toc_chapters(toc_url_input, toc_sel, cdp_url=cdp_param)

            # إذا نجح السحب ووجد الفصول
            if chapters_list and len(chapters_list) > 0:
                final_title = custom_novel_title_input.strip() if (custom_novel_title_input and custom_novel_title_input.strip()) else novel_title
                novel = get_or_create_novel(toc_url=toc_url_input, title=final_title, domain=domain_name)
                total_synced = sync_chapter_manifest(novel["id"], chapters_list)
                st.session_state.active_novel = novel
                st.session_state.chapters_cache = get_chapters(novel["id"])
                st.session_state.show_ai_fallback = False
                add_log(f"✅ تم بنجاح جلب وفهرسة {total_synced} فصلاً للرواية: '{final_title}'")
                st.success(f"🎉 تم جلب {total_synced} فصلاً بنجاح للرواية: '{final_title}'!")
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
# معالجة الخطوة 2: التحليل المتقدم بالذكاء الاصطناعي (Gemini AI Fallback & Deep Analysis)
# ------------------------------------------------------------------------------
if (force_ai_clicked or deep_ai_clicked or st.session_state.show_ai_fallback) and toc_url_input:
    if force_ai_clicked or deep_ai_clicked:
        target_model = "gemini-3.6-flash" if deep_ai_clicked else ai_model
        model_label = "Gemini 3.6 Flash / Pro (تحليل معماري فائق)" if deep_ai_clicked else ai_model
        with st.spinner(f"جاري استخراج كود DOM وتحليله عبر {model_label} لاستخراج أدق المحددات..."):
            try:
                add_log(f"🤖 جاري تشغيل تحليل الذكاء الاصطناعي ({ai_model}) لموقع {toc_url_input}...")
                toc_html, ch_html, detected_title = fetch_samples_for_gemini_analysis(toc_url_input, cdp_url=cdp_param)
                
                # استخدام رابط الوسيط النشط إذا وُجد
                active_gas = gas_url_input if 'gas_url_input' in locals() and gas_url_input else None
                analysis_result = analyze_site_dom_with_gemini(
                    toc_html=toc_html,
                    chapter_html=ch_html,
                    api_key=effective_key,
                    model_name=target_model,
                    gas_url=active_gas
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
                chapters_list, novel_title = crawl_toc_chapters(toc_url_input, toc_sel, cdp_url=cdp_param)
                if chapters_list:
                    final_title = custom_novel_title_input.strip() if (custom_novel_title_input and custom_novel_title_input.strip()) else novel_title
                    novel = get_or_create_novel(toc_url=toc_url_input, title=final_title, domain=domain_name)
                    total_synced = sync_chapter_manifest(novel["id"], chapters_list)
                    st.session_state.active_novel = novel
                    st.session_state.chapters_cache = get_chapters(novel["id"])
                    st.session_state.show_ai_fallback = False
                    add_log(f"✅ تم استخراج {total_synced} فصلاً بنجاح عبر Gemini AI للرواية: '{final_title}'!")
                    st.success(f"🎉 تم تحليل الموقع وجلب {total_synced} فصلاً بنجاح للرواية: '{final_title}'!")
                    st.rerun()
                else:
                    st.error("تم تحليل الموقع ولكن لم يتم العثور على روابط فصول. يمكنك تعديل المحددات يدوياً أدناه.")
            except Exception as ex_ai:
                err_ai = str(ex_ai) if str(ex_ai).strip() else repr(ex_ai)
                st.error(f"خطأ أثناء تحليل AI: {err_ai}")
                add_log(f"❌ خطأ AI: {err_ai}")

# عرض وتعديل محددات الـ CSS المستخرجة
if st.session_state.get("domain_config"):
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
# القسم 2: لوحة تحكم السحب والإدارة
# ------------------------------------------------------------------------------
if st.session_state.active_novel:
    novel = st.session_state.active_novel
    novel_stats = get_novel_stats(novel["id"])
    total_ch = novel_stats.get("total", 0)
    
    st.markdown('<div class="scraper-card">', unsafe_allow_html=True)
    st.subheader(f"2️⃣ لوحة تحكم السحب: {novel['title']}")
    
    # حقل اسم الرواية المعتمد في جدول Google Sheet (العمود C)
    col_name_input, col_name_btn = st.columns([3.5, 1])
    with col_name_input:
        novel_display_name = st.text_input(
            "🏷️ اسم الرواية المعتمد في جدول Google Sheet (يوضع في العمود C مع كل فصل):",
            value=novel.get("title", "رواية عامة"),
            key=f"novel_display_name_{novel['id']}",
            help="هذا الاسم سيُدرج في العمود C بجدول TranslateQueue مع كل فصل يتم تفريغه أو بثّه مباشرة."
        )
    with col_name_btn:
        st.write("")
        st.write("")
        save_name_btn = st.button("💾 تثبيت وحفظ الاسم", key=f"btn_save_name_{novel['id']}", use_container_width=True)

    if save_name_btn and novel_display_name:
        update_novel_title(novel["id"], novel_display_name)
        novel["title"] = novel_display_name
        st.session_state.active_novel = novel
        st.success(f"✓ تم حفظ وتثبيت اسم الرواية: '{novel_display_name}' بنجاح!")
        st.rerun()

    if novel_display_name and novel_display_name.strip() != novel.get("title"):
        update_novel_title(novel["id"], novel_display_name.strip())
        novel["title"] = novel_display_name.strip()
        st.session_state.active_novel = novel
    
    # مقاييس الرواية
    stat_c1, stat_c2, stat_c3, stat_c4 = st.columns(4)
    stat_c1.metric("إجمالي الفصول المكتشفة", total_ch)
    stat_c2.metric("فصول تم تنزيلها", novel_stats.get("downloaded", 0))
    stat_c3.metric("فصول معلقة", novel_stats.get("pending", 0))
    stat_c4.metric("فصول متعثرة", novel_stats.get("failed", 0))

    st.markdown("---")

    # 1. كشف الفجوات الترقيمية والفصول غير المنزلة واقتراحها
    all_local_chaps = get_chapters(novel["id"])
    downloaded_nums = [c["chapter_number"] for c in all_local_chaps if c.get("status") == "downloaded"]
    
    gap_ranges, all_missing = calculate_missing_gaps(downloaded_nums, total_chapters=total_ch)
    
    suggested_from = all_missing[0] if all_missing else 1
    suggested_to = all_missing[-1] if all_missing else max(1, total_ch)

    if gap_ranges and len(all_missing) > 0:
        gap_badges = " ".join([f'<span class="badge badge-warning">فجوة: {g["label"]}</span>' for g in gap_ranges[:8]])
        if len(gap_ranges) > 8:
            gap_badges += f' <span class="badge badge-info">+{len(gap_ranges)-8} فجوات أخرى</span>'
        
        st.markdown(f'''
        <div style="background-color: #1e1e2e; border: 1px solid #fab387; border-radius: 12px; padding: 14px 18px; margin-bottom: 16px;">
            <div style="color: #fab387; font-weight: bold; font-size: 1.05rem; margin-bottom: 6px;">
                🧩 <b>كاشف الفجوات والفصول غير المنزلة:</b> تم رصد {len(all_missing)} فصلاً ناقصاً عبر {len(gap_ranges)} فجوات ترقيمية.
            </div>
            <div style="margin-bottom: 8px;">{gap_badges}</div>
            <div style="color: #a6adc8; font-size: 0.88rem;">اختر إحدى الفجوات المقترحة أدناه لضبط نطاق السحب فورياً عليها:</div>
        </div>
        ''', unsafe_allow_html=True)

        # أزرار سريعة لاختيار أي فجوة فورياً
        cols_gap = st.columns(min(len(gap_ranges), 5))
        for idx, g in enumerate(gap_ranges[:5]):
            with cols_gap[idx]:
                if st.button(f"⚡ سحب فجوة ({g['label']})", key=f"gap_btn_{g['label']}_{idx}", use_container_width=True):
                    st.session_state.from_chap_input = g["from"]
                    st.session_state.to_chap_input = g["to"]
                    st.rerun()

    # 2. تعيين النطاق الافتراضي تلقائياً ليكون الفصول الناقصة فقط
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        from_chap = st.number_input("من الفصل رقم:", min_value=1, max_value=max(1, total_ch), value=suggested_from, key="from_chap_input")
    with col_r2:
        default_to_chap = max(from_chap, suggested_to)
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

    # أزرار التفريغ السحابي والفرز ومنع التكرار
    col_exp_sheet, col_sort_sheet = st.columns([1, 1])
    with col_exp_sheet:
        export_sheet_btn = st.button("📤 تفريغ الفصول في Google Sheet وتطهير ذاكرة السيرفر", key=f"export_sheet_{novel['id']}", use_container_width=True)
    with col_sort_sheet:
        sort_sheets_btn = st.button("🔄 فرز ومنع تكرار الجداول الثلاثة (1v1V4, 1Fceh, 1HDj)", key=f"sort_sheets_{novel['id']}", use_container_width=True)

    if export_sheet_btn:
        with st.spinner("⏳ جاري تفريغ الفصول في Google Sheet وحذفها من السيرفر..."):
            res = nsw_healer_engine.export_novel_to_google_sheet_and_purge(novel["id"], novel_display_name)
            if res.get("success"):
                st.success(f"🎉 تم تفريغ {res.get('exported_count')} فصلاً في Google Sheet وتطهير السيرفر بنجاح!")
                st.session_state.chapters_cache = get_chapters(novel["id"])
                st.rerun()
            else:
                st.error(f"❌ تعذر التفريغ: {res.get('message') or res.get('error')}")

    if sort_sheets_btn:
        with st.spinner("⏳ جاري الفرز الشامل، ترتيب الفصول 1..N، وحذف المكررات من جميع الجداول..."):
            sort_res = trigger_cloud_sheet_sorting()
            if sort_res.get("status") == "success":
                st.success("🎉 اكتمل فرز وترتيب وتطهير الجداول الثلاثة من التكرار بنجاح تام!")
                st.json(sort_res.get("results", sort_res))
            else:
                st.error(f"تعذر تنفيذ الفرز السحابي: {sort_res.get('error', 'خطأ غير معروف')}")

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
        custom_chaps_list = st.session_state.get("custom_chaps_list", None)
        if custom_chaps_list and len(custom_chaps_list) > 0:
            target_chapters = get_chapters(novel["id"], chapter_numbers=custom_chaps_list)
        else:
            all_chaps = get_chapters(novel["id"])
            target_chapters = [c for c in all_chaps if from_chap <= c["chapter_number"] <= to_chap]

        if len(target_chapters) == 0:
            st.warning("لا توجد فصول ضمن النطاق أو الأرقام المحددة!")
        else:
            cfg = st.session_state.domain_config or get_domain_config(novel["domain"])
            add_log(f"🚀 بدء سحب {len(target_chapters)} فصلاً في خيط خلفي مستقل (حتى لو أغلقت الصفحة)...")
            bg_sess = start_background_scraping(
                novel_id=novel["id"],
                from_chapter=from_chap,
                to_chapter=to_chap,
                domain_config=cfg,
                novel_name=novel_display_name,
                chapter_numbers=custom_chaps_list,
                min_delay=min_delay,
                max_delay=max_delay,
                headless=headless_mode,
                cdp_url=cdp_param,
                auto_stream_to_sheet=True
            )
            st.session_state.session_controller = bg_sess
            st.session_state.is_scraping = True
            st.rerun()

    # عرض حالة السحب الحية إذا كانت المهمة قيد التشغيل بالخلفية
    if is_bg_running and bg_session:
        st.markdown('<div class="badge badge-info">⚡ جاري السحب في الخلفية الآن (يمكنك إغلاق المتصفح بأمان)</div>', unsafe_allow_html=True)
        chaps_in_scope = [c for c in get_chapters(novel["id"]) if from_chap <= c["chapter_number"] <= to_chap]
        done_cnt = sum(1 for c in chaps_in_scope if c["status"] in ("downloaded", "streamed"))
        if hasattr(bg_session, "processed_count") and bg_session.processed_count > done_cnt:
            done_cnt = bg_session.processed_count
        tot_cnt = max(1, len(chaps_in_scope))
        progress_val = min(1.0, done_cnt / tot_cnt)
        st.progress(progress_val)
        st.caption(f"📊 المكتمل: {done_cnt} من أصل {tot_cnt} فصول ({int(progress_val * 100)}%)")
        time.sleep(2.0)
        st.rerun()

    # --------------------------------------------------------------------------
    # أداة المقارنة الفورية مع المصدر الأصلي واستبدال المحتوى المجتزأ (مباشرة في لوحة التحكم)
    # --------------------------------------------------------------------------
    st.markdown("---")
    with st.expander("⚖️ أداة فحص ومقارنة أي فصل مع المصدر الأصلي واستبداله فورياً (Live Chapter Comparator)", expanded=True):
        st.caption("قارن أي فصل محلياً أو في شيت الأرشيف مباشرة مع المصدر الأصلي الحي، وافحص هل هو مبتور أو ناقص، مع إمكانية الاستبدال الفوري بنقرة واحدة.")
        
        col_cmp_num, col_cmp_btn, col_cmp_scan = st.columns([1.5, 1.5, 1.5])
        with col_cmp_num:
            sec2_target_num = st.number_input("رقم الفصل للمقارنة المباشرة:", min_value=1, max_value=max(1, total_ch), value=102, step=1, key="sec2_compare_num")
        with col_cmp_btn:
            st.write("")
            st.write("")
            sec2_compare_clicked = st.button("🔍 مقارنة فورية مع الأصل", use_container_width=True, type="primary", key="sec2_cmp_btn")
        with col_cmp_scan:
            st.write("")
            st.write("")
            sec2_scan_range_clicked = st.button("🩺 فحص مقارنة (100-130)", use_container_width=True, help="فحص مقارنة سريع للفصول من 100 إلى 130 لكشف أي فصل مبتور", key="sec2_scan_rng_btn")

        if sec2_compare_clicked:
            with st.spinner(f"جاري جلب ومقارنة الفصل {sec2_target_num} مع المصدر الأصلي..."):
                c_res = compare_and_heal_chapter(
                    novel_id=novel["id"],
                    chapter_number=sec2_target_num,
                    cdp_url=cdp_param,
                    auto_replace=False,
                    auto_stream_to_sheet=True
                )
                st.session_state[f"sec2_comp_{sec2_target_num}"] = c_res

        active_c_res = st.session_state.get(f"sec2_comp_{sec2_target_num}")
        if active_c_res and active_c_res.get("success"):
            o_len = active_c_res["original_length"]
            d_len = active_c_res["downloaded_length"]
            d_diff = o_len - d_len
            
            c_m1, c_m2, c_m3 = st.columns(3)
            c_m1.metric("حجم النسخة المحلية/الشيت", f"{d_len:,} حرفاً")
            c_m2.metric("حجم المصدر الأصلي الحي", f"{o_len:,} حرفاً")
            c_m3.metric("الفارق", f"{d_diff:+,} حرفاً", delta_color="inverse" if d_diff > 400 else "normal")
            
            if active_c_res.get("is_truncated"):
                st.warning(f"⚠️ **تنبيه:** تم اكتشاف أن الفصل مجتزأ أو ناقص مقارنة بالأصل (فارق {d_diff:,} حرفاً)!")
            elif d_diff == 0:
                st.success("✅ النسخة المخزنة مطابقة تماماً للمصدر الأصلي 100%!")
            else:
                st.info("ℹ️ الفارق طفيف أو ضمن الحدود الطبيعية.")

            cp_col1, cp_col2 = st.columns(2)
            with cp_col1:
                st.markdown("**📄 محتوى النسخة المحلية / الشيت:**")
                st.text_area("المحلي:", value=active_c_res.get("downloaded_content", ""), height=220, key=f"sec2_txt_loc_{sec2_target_num}")
            with cp_col2:
                st.markdown("**🌐 محتوى المصدر الأصلي الحي:**")
                st.text_area("الأصلي:", value=active_c_res.get("original_content", ""), height=220, key=f"sec2_txt_orig_{sec2_target_num}")

            if st.button(f"⚡ استبدال النسخة المحلية بالأصل وتحديث شيت 1v1V4 فورياً", type="primary", key=f"sec2_btn_rep_{sec2_target_num}"):
                with st.spinner("جاري استبدال المحتوى في قاعدة البيانات والضخ لشيت الأرشيف..."):
                    r_res = compare_and_heal_chapter(
                        novel_id=novel["id"],
                        chapter_number=sec2_target_num,
                        cdp_url=cdp_param,
                        auto_replace=True,
                        auto_stream_to_sheet=True
                    )
                    if r_res.get("replaced"):
                        st.success(f"🎉 تم بنجاح استبدال الفصل {sec2_target_num} بالنسخة الكاملة ({o_len:,} حرفاً) وضخه لشيت 1v1V4!")
                        st.session_state.chapters_cache = get_chapters(novel["id"])
                        st.rerun()

        if sec2_scan_range_clicked:
            with st.spinner("جاري فحص مقارنة الفصول من 100 إلى 130..."):
                scan_results = []
                for sc_num in range(100, 131):
                    sc_res = compare_and_heal_chapter(novel["id"], sc_num, cdp_url=cdp_param, auto_replace=False)
                    if sc_res.get("success"):
                        scan_results.append({
                            "رقم الفصل": sc_num,
                            "الحجم المحلي": sc_res["downloaded_length"],
                            "حجم الأصل": sc_res["original_length"],
                            "الفارق": sc_res["diff_chars"],
                            "الحالة": "⚠️ مبتور / ناقص" if sc_res["is_truncated"] else "✅ كامل ومطابق"
                        })
                st.markdown("##### 📋 تقرير فحص المقارنة لنطاق الفصول (100 - 130):")
                st.dataframe(scan_results, use_container_width=True)

    st.markdown('</div>', unsafe_allow_html=True)


# ------------------------------------------------------------------------------
# القسم 3: سجل الأحداث الحي وتصدير الملفات والمعاينة
# ------------------------------------------------------------------------------
st.markdown('<div class="scraper-card">', unsafe_allow_html=True)
st.subheader("3️⃣ سجل الأحداث المباشر & التصدير النهائي")

tab_logs, tab_export, tab_outliers, tab_preview, tab_media, tab_nsw = st.tabs([
    "📟 Live Console Log",
    "📥 تصدير الرواية .TXT",
    "📊 كاشف القيم المتطرفة للشيت (1v1V4)",
    "⚖️ مقارنة الفصول واستبدال المجتزأ",
    "🎬 محمل وتجزئة الوسائط",
    "🩹 استصلاح فصول المدونة"
])

with tab_logs:
    logs_text = "\n".join(st.session_state.logs[-18:])
    st.markdown(f'<div class="terminal-console">{logs_text}</div>', unsafe_allow_html=True)

with tab_export:
    if st.session_state.active_novel:
        novel_id = st.session_state.active_novel["id"]
        novel_title = st.session_state.active_novel["title"]
        current_stats = get_novel_stats(novel_id)
        n_total = max(1, current_stats.get("total", 1))
        
        col_exp1, col_exp2 = st.columns([2, 2])
        with col_exp1:
            export_from = st.number_input("تصدير من الفصل:", min_value=1, max_value=n_total, value=1, key="exp_from")
        with col_exp2:
            min_exp_to = int(export_from)
            max_exp_to = max(min_exp_to, n_total)
            export_to = st.number_input("إلى الفصل:", min_value=min_exp_to, max_value=max_exp_to, value=max_exp_to, key="exp_to")

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

with tab_outliers:
    st.markdown("### 📊 المحلل الإحصائي للفصول وكاشف القيم المتطرفة الدنيا (شيت الأرشيف 1v1V4)")
    st.caption("مقارنة تلقائية ذكية تعتمد على حساب متوسط عدد أحرف الفصول واكتشاف القيم المتطرفة الدنيا (Lower Extreme Outliers) وفق معادلة المخطط الصندوقي (IQR) ونسبة الانحراف، مع إمكانية التعديل والاستبدال المباشر لنفس العمود B داخل شيت الأرشيف.")

    cur_novel_name = ""
    if st.session_state.active_novel:
        cur_novel_name = st.session_state.active_novel.get("title", "")
    if not cur_novel_name:
        cur_novel_name = "نظام الانعكاس لا يظهر إلا بعد بلوغ مرحلة الماهايانا"

    col_out_nov, col_out_sid = st.columns([2, 2])
    with col_out_nov:
        target_outlier_novel = st.text_input("اسم الرواية للفحص في الشيت:", value=cur_novel_name, key="outlier_nov_name_inp")
    with col_out_sid:
        target_outlier_ssid = st.text_input("معرف شيت الأرشيف (Spreadsheet ID):", value="1v1V4_rQukDs3oCe8Z4Izvni3uCx91iKmSVNOm4A3mH0", key="outlier_ssid_inp")

    col_btn_scan_out, col_btn_heal_out = st.columns([2, 2])
    with col_btn_scan_out:
        scan_outliers_clicked = st.button("🔍 فحص وتحليل القيم المتطرفة في الشيت", type="primary", use_container_width=True, key="btn_scan_sheet_outliers")
    with col_btn_heal_out:
        heal_outliers_clicked = st.button("⚡ تعديل واستبدال مباشر لكافة الفصول المتطرفة (العمود B)", type="secondary", use_container_width=True, key="btn_heal_sheet_outliers")

    if scan_outliers_clicked:
        with st.spinner("جاري تنزيل شيت الأرشيف وحساب المتوسط الإحصائي والربيعيات..."):
            out_res = scan_sheet_extreme_outliers(novel_name=target_outlier_novel, spreadsheet_id=target_outlier_ssid)
            st.session_state["last_outlier_scan"] = out_res

    last_scan = st.session_state.get("last_outlier_scan")
    if last_scan:
        if not last_scan.get("success"):
            st.error(last_scan.get("error") or last_scan.get("message") or "حدث خطأ أثناء فحص الشيت.")
        else:
            tot_chaps = last_scan.get("total_chapters", 0)
            mean_val = last_scan.get("mean", 0)
            med_val = last_scan.get("median", 0)
            thresh_val = last_scan.get("threshold", 0)
            out_list = last_scan.get("outliers", [])
            out_cnt = len(out_list)

            st.markdown("---")
            m_c1, m_c2, m_c3, m_c4, m_c5 = st.columns(5)
            m_c1.metric("إجمالي الفصول بالشيت", f"{tot_chaps:,}")
            m_c2.metric("المتوسط الحسابي (Mean)", f"{mean_val:,.1f} حرف")
            m_c3.metric("الوسيط (Median)", f"{med_val:,} حرف")
            m_c4.metric("عتبة القيمة المتطرفة", f"{thresh_val:,} حرف")
            m_c5.metric("الفصول المتطرفة المرصودة", f"{out_cnt:,}", delta=f"{round((out_cnt/max(1, tot_chaps))*100, 1)}%", delta_color="inverse")

            st.markdown(f"""
            <div style="background-color:#0f172a; border:1px solid #334155; border-radius:10px; padding:12px 18px; margin: 12px 0;">
                <span style="color:#38bdf8; font-weight:bold;">📐 المعادلة الإحصائية المطبقة:</span>
                <span style="color:#cbd5e1; font-size:0.92rem;">
                    الحد المتطرف = <code>min(Mean × 55%, Q1 - 2.5 × IQR)</code> مقيدة بنطاق الأمان [2,500 إلى 5,500 حرف].
                    <br>الربيع الأول (Q1): <b>{last_scan.get('q1')}</b> | الربيع الثالث (Q3): <b>{last_scan.get('q3')}</b> | المدى الربيعي (IQR): <b>{last_scan.get('iqr')}</b>
                </span>
            </div>
            """, unsafe_allow_html=True)

            if out_cnt == 0:
                st.success("🎉 ممتاز! لا توجد أي فصول تمثل قيمة متطرفة دنيا في الشيت. كافة الفصول مكتملة وتتجاوز عتبة الأمان.")
            else:
                st.warning(f"⚠️ تم اكتشاف **{out_cnt}** فصلاً يقل حجمها عن حد القيمة المتطرفة ({thresh_val:,} حرفاً) وتحتاج إلى استبدال المحتوى في العمود B:")
                
                table_rows = []
                for o in out_list:
                    table_rows.append({
                        "رقم الفصل": o.get("chapter_num"),
                        "رقم السطر بالشيت": o.get("row_number"),
                        "طول المحتوى (العمود B)": f"{o.get('content_length'):,} حرفاً",
                        "العجز عن العتبة": f"-{thresh_val - o.get('content_length'):,} حرفاً",
                        "النسبة من المتوسط": f"{o.get('ratio_to_mean')}%",
                        "معاينة البداية": o.get("content_preview")
                    })
                st.dataframe(table_rows, use_container_width=True)

    if heal_outliers_clicked:
        st.markdown("---")
        st.info("🚀 جاري إطلاق المعالجة والاستبدال المباشر لكافة الفصول المتطرفة في الشيت...")
        prog_bar = st.progress(0.0)
        status_txt = st.empty()

        def _streamlit_progress(idx, total, message):
            pct = min(1.0, idx / max(1, total))
            prog_bar.progress(pct)
            status_txt.markdown(f"**[{idx}/{total}]** {message}")

        with st.spinner("جاري سحب المحتوى الأصلي للفصول المتطرفة وتحديث نفس العمود B في الشيت..."):
            heal_result = heal_sheet_extreme_outliers(
                novel_name=target_outlier_novel,
                spreadsheet_id=target_outlier_ssid,
                cdp_url=cdp_param,
                progress_callback=_streamlit_progress
            )

        if heal_result.get("success"):
            rep_cnt = heal_result.get("repaired_count", 0)
            scanned_tot = heal_result.get("scanned_outliers", 0)
            st.success(f"🎉 {heal_result.get('message')}")
            
            det_rows = []
            for d in heal_result.get("details", []):
                det_rows.append({
                    "رقم الفصل": d.get("chapter_number"),
                    "الصف في الشيت": d.get("row_number"),
                    "الحجم السابق": f"{d.get('old_length'):,} حرفاً",
                    "الحجم الجديد": f"{d.get('new_length'):,} حرفاً",
                    "الحالة": "✅ تم الاستبدال بالعمود B" if d.get("replaced") else "تم التخطي"
                })
            st.dataframe(det_rows, use_container_width=True)
            st.session_state["last_outlier_scan"] = None
        else:
            st.error(heal_result.get("error") or heal_result.get("message") or "تعذر إكمال عملية الإصلاح.")

with tab_preview:
    st.markdown("#### 📖 قارئ ومقارن الفصول الحية (Chapter Inspector & Comparator)")
    st.caption("تصفح أي فصل من فصول الرواية، افحص حجم النص وسلامته، وقارنه مباشرة مع المصدر الأصلي مع خيار الاستبدال الفوري للمحتوى المجتزأ.")
    
    if st.session_state.active_novel:
        act_id = st.session_state.active_novel["id"]
        all_ch = get_chapters(act_id)
        if all_ch:
            tot_count = len(all_ch)
            col_sel_ch, col_btn_comp = st.columns([2, 1.5])
            with col_sel_ch:
                target_ch_num = st.number_input("اختر رقم الفصل للاستعراض والمقارنة:", min_value=1, max_value=tot_count, value=1, step=1, key="preview_ch_num_inp")
            
            # جلب الفصل المحدد
            curr_ch = next((c for c in all_ch if c["chapter_number"] == target_ch_num), None)
            
            if curr_ch:
                ch_status = curr_ch.get("status", "pending")
                ch_text = curr_ch.get("content") or ""
                ch_len = len(ch_text)
                
                status_color = "green" if ch_status == "downloaded" else "orange" if ch_status == "pending" else "red"
                st.markdown(f"**عنوان الفصل:** `{curr_ch.get('title', 'غير معروف')}` | **الحالة:** :{status_color}[{ch_status}] | **الحجم المخزن:** `{ch_len:,}` حرفاً | **رابط المصدر:** [زيارة الرابط]({curr_ch.get('url', '#')})")
                
                with col_btn_comp:
                    st.write("")
                    st.write("")
                    compare_clicked = st.button("🔍 مقارنة حية مع المصدر الأصلي", use_container_width=True, type="primary")

                if compare_clicked:
                    with st.spinner(f"جاري جلب الفصل {target_ch_num} من المصدر ومقارنة المحتوى..."):
                        comp_res = compare_and_heal_chapter(
                            novel_id=act_id,
                            chapter_number=target_ch_num,
                            cdp_url=cdp_param,
                            auto_replace=False,
                            auto_stream_to_sheet=True
                        )
                        st.session_state[f"comp_res_{target_ch_num}"] = comp_res

                # عرض تقرير المقارنة إذا توفر
                active_comp = st.session_state.get(f"comp_res_{target_ch_num}")
                if active_comp and active_comp.get("success"):
                    orig_len = active_comp["original_length"]
                    down_len = active_comp["downloaded_length"]
                    diff = orig_len - down_len
                    
                    st.markdown("---")
                    st.markdown(f"##### 📊 نتيجة المقارنة الحية للفصل {target_ch_num}:")
                    col_m1, col_m2, col_m3 = st.columns(3)
                    col_m1.metric("حجم النسخة المنزلة", f"{down_len:,} حرفاً")
                    col_m2.metric("حجم المصدر الأصلي", f"{orig_len:,} حرفاً")
                    col_m3.metric("الفارق", f"{diff:+,} حرفاً", delta_color="inverse" if diff > 500 else "normal")
                    
                    if active_comp.get("is_truncated"):
                        st.warning(f"⚠️ **تنبيه:** تم رصد نقص أو بتر في النسخة المخزنة مقارنة بالأصل (فارق {diff:,} حرفاً)!")
                    elif diff == 0:
                        st.success("✅ النسخة المخزنة مطابقة تماماً للمصدر الأصلي 100%!")
                    else:
                        st.info("ℹ️ الفارق طفيف أو ضمن الحدود الطبيعية للتنسيق.")

                    col_prev_local, col_prev_orig = st.columns(2)
                    with col_prev_local:
                        st.markdown("**📄 محتوى النسخة المخزنة محلياً:**")
                        st.text_area("المحلي:", value=active_comp.get("downloaded_content", ""), height=240, key=f"txt_local_{target_ch_num}")
                    with col_prev_orig:
                        st.markdown("**🌐 محتوى المصدر الأصلي الحي:**")
                        st.text_area("الأصلي:", value=active_comp.get("original_content", ""), height=240, key=f"txt_orig_{target_ch_num}")

                    col_act_rep, _ = st.columns([2, 2])
                    with col_act_rep:
                        if st.button(f"⚡ استبدال النسخة المحلية بالأصل وتحديث شيت الأرشيف (1v1V4)", type="primary", key=f"btn_replace_{target_ch_num}"):
                            with st.spinner("جاري استبدال المحتوى في قاعدة البيانات والضخ لشيت الأرشيف..."):
                                rep_res = compare_and_heal_chapter(
                                    novel_id=act_id,
                                    chapter_number=target_ch_num,
                                    cdp_url=cdp_param,
                                    auto_replace=True,
                                    auto_stream_to_sheet=True
                                )
                                if rep_res.get("replaced"):
                                    st.success(f"🎉 تم استبدال وتحديث الفصل {target_ch_num} بنجاح بالأصل ({orig_len:,} حرفاً) وضخه لشيت 1v1V4!")
                                    st.session_state.chapters_cache = get_chapters(act_id)
                                    st.rerun()
                                else:
                                    st.info("المحتوى الحالي مساوٍ أو أكبر من المصدر الأصلي بالفعل.")
                else:
                    st.text_area("📄 نص الفصل المخزن:", value=ch_text, height=300, key=f"ch_view_{target_ch_num}")
            else:
                st.warning(f"الفصل رقم {target_ch_num} غير مسجل في فهرس هذه الرواية.")
        else:
            st.info("لا توجد فصول مسجلة في فهرس هذه الرواية.")
    else:
        st.info("قم باختيار رواية لعرض ومقارنة فصولها.")

with tab_media:
    st.markdown("### 🎬 محمل الوسائط وتجزئة الفيديوهات الذكي")
    st.caption("تحميل الفيديوهات من يوتيوب ومنصات التواصل، مع دعم التجزئة التلقائية للفيديوهات الكبيرة (>1GB)، والترجمة الذكية.")

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

    col_g1, col_g2, col_g3 = st.columns([1.5, 2, 1.5])
    with col_g1:
        scan_gaps_clicked = st.button("🔍 فحص الفجوات المفقودة", use_container_width=True)
    with col_g2:
        fill_gaps_clicked = st.button("🚀 ملء الفجوات المفقودة ونشرها", use_container_width=True, type="primary")
    with col_g3:
        stop_gaps_clicked = st.button("🛑 إيقاف فوري للعملية", use_container_width=True)

    if stop_gaps_clicked:
        nsw_healer_engine.request_stop()
        st.error("🛑 تم إرسال أمر الإيقاف الفوري! سيتوقف محرك الفجوات لحظياً.")

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
                st.info("لا توجد فجوات مفقودة لملئها حالياً أو تم إيقاف العملية.")

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
