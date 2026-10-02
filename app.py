# -*- coding: utf-8 -*-
"""
app.py — لوحة تحكم النشر الموحدة (NSW Cloud Publisher & Syndication UI)
مخصصة بالكامل لـ:
1. نشر وإدارة روايات نادي الروايات (Rewayat Club)
2. نشر وإدارة روايات واتباد (Wattpad)
3. مراقبة وإدارة جدول النشر الآلي بدون أي محركات سحب ثقيلة (<80MB RAM)
"""

import os
import sys
import time
import streamlit as st

import syndication_db
import ui_syndication_tabs
try:
    import supabase_db
except ImportError:
    supabase_db = None

# ==============================================================================
# إعداد الصفحة والمظهر البصري الداكن (RTL)
# ==============================================================================
st.set_page_config(
    page_title="NSW Publisher Studio",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&family=JetBrains+Mono:wght@400;600;700&display=swap');

    html, body {
        font-family: 'Cairo', sans-serif !important;
    }

    .stApp, .main, div[data-testid="stSidebarUserContent"], .scraper-card, .stMarkdown, div[data-testid="stVerticalBlock"] {
        font-family: 'Cairo', sans-serif !important;
        direction: rtl;
        text-align: right;
    }
    
    .stApp {
        background-color: #080c14;
        color: #f1f5f9;
    }

    section[data-testid="stSidebar"] {
        background-color: #0d131f !important;
        border-left: 1px solid #1e293b !important;
        overflow-x: hidden !important;
    }

    .scraper-card {
        background: linear-gradient(135deg, #0f172a 0%, #111827 100%);
        border: 1px solid #334155;
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 24px;
        box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.7);
    }
    
    .scraper-header {
        background: linear-gradient(90deg, #38bdf8, #818cf8, #a855f7);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 900;
        font-size: 2.2rem;
        margin-bottom: 8px;
    }
    
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

    div.stButton > button {
        background-color: #1e293b !important;
        color: #ffffff !important;
        border: 1px solid #475569 !important;
        border-radius: 10px !important;
        font-weight: 800 !important;
        font-size: 0.98rem !important;
        padding: 8px 18px !important;
        transition: all 0.25s ease !important;
    }
    div.stButton > button:hover {
        background-color: #334155 !important;
        color: #38bdf8 !important;
        border-color: #38bdf8 !important;
    }
    div.stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #0284c7 0%, #2563eb 100%) !important;
        color: #ffffff !important;
        border: 1px solid #60a5fa !important;
        font-weight: 900 !important;
    }

    div[data-baseweb="input"] input, div[data-baseweb="textarea"] textarea {
        background-color: #0f172a !important;
        color: #f8fafc !important;
        border: 1px solid #334155 !important;
        border-radius: 8px !important;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# الشريط الجانبي (Sidebar: System Status & Settings)
# ==============================================================================
with st.sidebar:
    st.markdown("## 🚀 خادم النشر الذكي")
    st.caption("NSW Cloud Publisher v3.0 | مخصص للنشر فقط")
    
    # حالة Supabase
    sb_ready = supabase_db.is_configured() if supabase_db else False
    if sb_ready:
        st.markdown('<span class="badge badge-success">✓ سحابي: Supabase متصل</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="badge badge-warning">⚠ وضع محلي: SQLite نشط</span>', unsafe_allow_html=True)
    
    st.markdown('<span class="badge badge-info">✓ محرك النشر الآلي: 24/7 نشط</span>', unsafe_allow_html=True)
    st.markdown('<span class="badge badge-info">✓ بوت تيليجرام: نشط</span>', unsafe_allow_html=True)
    st.markdown('<span class="badge badge-success">✓ استهلاك الذاكرة: خفيف جداً (&lt;80MB)</span>', unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown("### 🔑 مفاتيح المنصات السحابية")
    
    # توكن نادي الروايات
    current_rc = syndication_db.get_synd_setting("rewayat_token", "")
    rc_input = st.text_input("توكن نادي الروايات:", value=current_rc, type="password")
    if rc_input != current_rc:
        syndication_db.set_synd_setting("rewayat_token", rc_input.strip())
        st.success("تم تحديث توكن نادي الروايات!")

    # بيانات واتباد
    current_wp_user = syndication_db.get_synd_setting("wattpad_username", "")
    wp_user_input = st.text_input("اسم مستخدم واتباد:", value=current_wp_user)
    if wp_user_input != current_wp_user:
        syndication_db.set_synd_setting("wattpad_username", wp_user_input.strip())
        st.success("تم حفظ اسم المستخدم!")

    current_wp_pass = syndication_db.get_synd_setting("wattpad_password", "")
    wp_pass_input = st.text_input("كلمة مرور واتباد:", value=current_wp_pass, type="password")
    if wp_pass_input != current_wp_pass:
        syndication_db.set_synd_setting("wattpad_password", wp_pass_input.strip())
        st.success("تم حفظ كلمة المرور!")

# ==============================================================================
# الواجهة الرئيسية (Main Application View)
# ==============================================================================
st.markdown('<div class="scraper-header">🚀 NSW Cloud Publisher Studio</div>', unsafe_allow_html=True)
st.caption("نظام النشر السحابي الموحد والمستقل لروايات نادي الروايات وواتباد وجدولة الفصول.")

# محدد التبويبات الرئيسي
main_nav_tab = st.radio(
    "اختر منصة النشر:",
    ["🏛️ نادي الروايات (Rewayat Club)", "🟧 واتباد (Wattpad)"],
    index=0,
    horizontal=True,
    label_visibility="collapsed"
)

st.markdown("---")

if main_nav_tab == "🏛️ نادي الروايات (Rewayat Club)":
    ui_syndication_tabs.render_rewayat_club_tab()
elif main_nav_tab == "🟧 واتباد (Wattpad)":
    ui_syndication_tabs.render_wattpad_tab()
