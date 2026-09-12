# -*- coding: utf-8 -*-
"""
ui_syndication_tabs.py — واجهة التبويبين لنادي الروايات وواتباد
تُستدعى في app.py لعرض الإعدادات والروايات المربوطة بدقة وأناقة دون لمس كود المنظومة الحساس.
"""

import streamlit as st
import syndication_db
import syndication_extractor

def render_rewayat_club_tab():
    st.subheader("🏛️ إدارة النشر التلقائي — نادي الروايات (Rewayat Club)")
    st.caption("أتمتة سحب الفصول من مدونة عالم سماء الروايات ونشرها دورياً على حسابك في منصة rewayat.club.")
    
    # 1. إعدادات حساب نادي الروايات
    with st.expander("🔐 بيانات حساب نادي الروايات (Authentication)", expanded=False):
        col_u, col_p = st.columns(2)
        stored_user = syndication_db.get_synd_setting("rewayat_username", "")
        stored_token = syndication_db.get_synd_setting("rewayat_token", "")
        
        with col_u:
            rewayat_user = st.text_input("اسم المستخدم / البريد:", value=stored_user, key="rc_user")
        with col_p:
            rewayat_token = st.text_input("رمز التوكن أو كلمة المرور (Bearer Token / Password):", value=stored_token, type="password", key="rc_token")
            
        if st.button("💾 حفظ بيانات الحساب", key="save_rc_creds"):
            syndication_db.save_synd_setting("rewayat_username", rewayat_user.strip())
            syndication_db.save_synd_setting("rewayat_token", rewayat_token.strip())
            st.success("تم حفظ بيانات الدخول لنادي الروايات بنجاح.")

    # 2. إضافة / تعديل رواية
    with st.expander("➕ إضافة رواية جديدة لنادي الروايات", expanded=True):
        with st.form("form_add_novel_rewayat"):
            col1, col2 = st.columns(2)
            with col1:
                n_name = st.text_input("🏷️ اسم الرواية (كما هو معتمد بالشيت/المدونة):", placeholder="مثال: Shadow Slave")
                n_blogger_url = st.text_input("🔗 رابط صفحة الرواية في مدونتك (Blogger):", placeholder="https://novelskyworld.blogspot.com/p/...")
                n_blogger_label = st.text_input("🏷️ تصنيف الرواية في بلوجر (Label / Novelname):", placeholder="Shadow Slave")
            with col2:
                n_rewayat_id = st.text_input("🆔 معرف / رابط الرواية في نادي الروايات:", placeholder="مثال: 5420 أو https://rewayat.club/novel/...")
                col_c1, col_c2, col_c3 = st.columns(3)
                with col_c1:
                    start_ch = st.number_input("الفصل الأول:", min_value=1, value=1, step=1)
                with col_c2:
                    last_ch = st.number_input("آخر فصل تم نشره:", min_value=0, value=0, step=1)
                with col_c3:
                    stop_ch = st.number_input("أقصى فصل للتوقف عنده:", min_value=1, value=5000, step=1)
                interval = st.number_input("⏱️ معدل النشر (ساعات بين كل فصل):", min_value=0.5, value=12.0, step=0.5)

            cta_default = "✨ استمتعتم بالفصل؟ لمتابعة الفصول الحصرية والمتقدمة فور صدورها زوروا موقعنا الأصلي: [رابط الرواية] ✨"
            custom_cta = st.text_area("💬 التعليق التحفيزي الثابت لنهاية كل فصل:", value=cta_default, height=70)
            
            submit_btn = st.form_submit_button("🚀 حفظ الرواية وبدء جدولتها", type="primary")
            if submit_btn:
                if not n_name.strip():
                    st.error("يرجى إدخال اسم الرواية على الأقل.")
                else:
                    syndication_db.save_or_update_syndicated_novel({
                        "novel_name": n_name.strip(),
                        "blogger_url": n_blogger_url.strip(),
                        "blogger_label": n_blogger_label.strip() or n_name.strip(),
                        "rewayat_enabled": 1,
                        "rewayat_novel_id": n_rewayat_id.strip(),
                        "rewayat_novel_url": n_rewayat_id.strip() if "rewayat.club" in n_rewayat_id else "",
                        "wattpad_enabled": 0,
                        "wattpad_story_id": "",
                        "wattpad_story_url": "",
                        "start_chapter": int(start_ch),
                        "last_synced_chapter": int(last_ch),
                        "stop_chapter": int(stop_ch),
                        "interval_hours": float(interval),
                        "custom_cta": custom_cta.strip(),
                        "is_active": 1
                    })
                    st.success(f"🎉 تم تسجيل الرواية '{n_name}' بنجاح في جدول النشر بنادي الروايات!")
                    st.rerun()

    # 3. عرض الروايات المسجلة
    st.markdown("### 📚 الروايات المربوطة حالياً بنادي الروايات")
    all_novels = [n for n in syndication_db.get_all_syndicated_novels() if n.get("rewayat_enabled") == 1]
    if not all_novels:
        st.info("لا توجد روايات مضافة لنادي الروايات حتى الآن. استخدم النموذج أعلاه لإضافة أول رواية.")
    else:
        for nov in all_novels:
            with st.container():
                col_info, col_status, col_actions = st.columns([3, 2, 1.5])
                with col_info:
                    st.markdown(f"**📖 {nov['novel_name']}**")
                    st.caption(f"معرف نادي الروايات: `{nov['rewayat_novel_id'] or 'غير محدد'}` | المصدر: `{nov['blogger_label']}`")
                with col_status:
                    st.markdown(f"📊 آخر فصل تم نشره: **{nov['last_synced_chapter']}** / التوقف عند: **{nov['stop_chapter']}**")
                    st.caption(f"⏱️ الوتيرة: فصل كل {nov['interval_hours']} ساعة | الحالة: {'🟢 نشط' if nov['is_active'] else '🔴 متوقف'}")
                with col_actions:
                    if st.button("🗑️ حذف", key=f"del_rc_nov_{nov['id']}"):
                        syndication_db.delete_syndicated_novel(nov["id"])
                        st.success(f"تم حذف {nov['novel_name']}")
                        st.rerun()
                st.markdown("---")

    # 4. قسم معاينة الفصل قبل نشره
    st.markdown("### 👁️ معاينة فصل وتجهيزه (اختبار المحرك)")
    with st.expander("🔍 معاينة فصل مجهّز جاهز للنشر", expanded=False):
        all_novels_names = [n["novel_name"] for n in syndication_db.get_all_syndicated_novels() if n.get("rewayat_enabled") == 1]
        if not all_novels_names:
            st.info("أضف رواية أولاً من النموذج أعلاه.")
        else:
            col_pv1, col_pv2 = st.columns([2, 1])
            with col_pv1:
                preview_novel = st.selectbox("📚 اختر الرواية:", all_novels_names, key="rc_preview_novel")
            with col_pv2:
                preview_chapter = st.number_input("رقم الفصل للمعاينة:", min_value=1, value=1, step=1, key="rc_preview_chap")

            if st.button("🔍 جلب ومعاينة الفصل", key="rc_preview_btn", use_container_width=True):
                # البحث عن إعدادات الرواية
                all_novs = syndication_db.get_all_syndicated_novels()
                nov_cfg = next((n for n in all_novs if n["novel_name"] == preview_novel), None)
                custom_cta = nov_cfg["custom_cta"] if nov_cfg else ""
                blogger_url = nov_cfg["blogger_url"] if nov_cfg else ""
                
                with st.spinner(f"⏳ جاري سحب الفصل {preview_chapter} من جداول الترجمة..."):
                    result = syndication_extractor.prepare_chapter_for_publishing(
                        novel_name=preview_novel,
                        chapter_num=int(preview_chapter),
                        custom_cta=custom_cta,
                        blogger_url=blogger_url
                    )
                
                if result["success"]:
                    st.success(f"✅ تم جلب الفصل من المصدر: `{result['source']}`")
                    st.markdown(f"**📌 عنوان الفصل:** {result['title']}")
                    st.markdown("**📄 معاينة أول 500 حرف من المتن:**")
                    st.text_area("المتن المُجهَّز:", value=result["content_for_publish"][:500] + "...", height=180, disabled=True, key="rc_preview_output")
                    
                    chars = len(result["content_for_publish"])
                    st.caption(f"📊 الطول الإجمالي: {chars:,} حرف | المصدر: `{result['source']}`")
                    
                    # عرض الفصول المتاحة
                    available = syndication_extractor.get_available_chapters_for_novel(preview_novel)
                    if available:
                        st.info(f"📚 إجمالي الفصول المتاحة لهذه الرواية في شيت الترجمة: **{len(available)}** فصل (من {min(available)} إلى {max(available)})")
                else:
                    st.error(f"❌ {result['error']}")

    # 5. سجل النشر الأخير
    st.markdown("### 📋 سجل النشر الأخير (نادي الروايات)")
    recent_logs = syndication_db.get_recent_syndication_logs(limit=20)
    rc_logs = [l for l in recent_logs if l.get("platform") == "rewayat_club"]
    if not rc_logs:
        st.info("لا توجد سجلات نشر بعد.")
    else:
        for log in rc_logs:
            icon = "✅" if log["status"] == "SUCCESS" else "❌"
            st.markdown(f"{icon} **{log.get('novel_name','؟')}** — الفصل `{log['chapter_num']}` — `{log['published_at']}`")
            if log.get("post_url"):
                st.caption(f"🔗 {log['post_url']}")
            if log.get("error_msg"):
                st.caption(f"⚠️ {log['error_msg']}")

def render_wattpad_tab():
    st.subheader("🟧 إدارة النشر التلقائي — واتباد (Wattpad)")
    st.caption("أتمتة سحب الفصول من مدونة عالم سماء الروايات ونشرها كأجزاء داخل قصص حسابك على Wattpad.")
    
    # 1. إعدادات حساب واتباد
    with st.expander("🔐 بيانات حساب واتباد (Wattpad Credentials)", expanded=False):
        col_u, col_p = st.columns(2)
        stored_w_user = syndication_db.get_synd_setting("wattpad_username", "")
        stored_w_token = syndication_db.get_synd_setting("wattpad_token", "")
        
        with col_u:
            wattpad_user = st.text_input("اسم المستخدم / الإيميل (Wattpad):", value=stored_w_user, key="wp_user")
        with col_p:
            wattpad_token = st.text_input("كلمة المرور أو الـ Session Token:", value=stored_w_token, type="password", key="wp_token")
            
        if st.button("💾 حفظ بيانات حساب واتباد", key="save_wp_creds"):
            syndication_db.save_synd_setting("wattpad_username", wattpad_user.strip())
            syndication_db.save_synd_setting("wattpad_token", wattpad_token.strip())
            st.success("تم حفظ بيانات الدخول لواتباد بنجاح.")

    # 2. إضافة رواية لواتباد
    with st.expander("➕ إضافة رواية جديدة لواتباد", expanded=True):
        with st.form("form_add_novel_wattpad"):
            col1, col2 = st.columns(2)
            with col1:
                w_name = st.text_input("🏷️ اسم الرواية:", placeholder="مثال: Shadow Slave")
                w_blogger_url = st.text_input("🔗 رابط صفحة الرواية في بلوجر:", placeholder="https://novelskyworld.blogspot.com/p/...")
                w_blogger_label = st.text_input("🏷️ تصنيف الرواية في بلوجر:", placeholder="Shadow Slave")
            with col2:
                w_story_id = st.text_input("🆔 معرف قصة واتباد (Story ID / URL):", placeholder="مثال: 987654321 أو رابط القصة")
                col_c1, col_c2, col_c3 = st.columns(3)
                with col_c1:
                    w_start_ch = st.number_input("الفصل الأول:", min_value=1, value=1, step=1, key="wp_start")
                with col_c2:
                    w_last_ch = st.number_input("آخر فصل تم نشره:", min_value=0, value=0, step=1, key="wp_last")
                with col_c3:
                    w_stop_ch = st.number_input("أقصى فصل للتوقف عنده:", min_value=1, value=5000, step=1, key="wp_stop")
                w_interval = st.number_input("⏱️ معدل النشر (ساعات):", min_value=0.5, value=12.0, step=0.5, key="wp_interval")

            w_cta_default = "✨ استمتعتم بالفصل؟ لمتابعة الفصول الحصرية والمتقدمة فور صدورها تفضلوا بزيارة موقعنا: [رابط الرواية] ✨"
            w_custom_cta = st.text_area("💬 التعليق التحفيزي لقصة واتباد:", value=w_cta_default, height=70, key="wp_cta")
            
            w_submit_btn = st.form_submit_button("🚀 حفظ الرواية وبدء جدولتها على واتباد", type="primary")
            if w_submit_btn:
                if not w_name.strip():
                    st.error("يرجى إدخال اسم الرواية على الأقل.")
                else:
                    syndication_db.save_or_update_syndicated_novel({
                        "novel_name": w_name.strip(),
                        "blogger_url": w_blogger_url.strip(),
                        "blogger_label": w_blogger_label.strip() or w_name.strip(),
                        "rewayat_enabled": 0,
                        "rewayat_novel_id": "",
                        "rewayat_novel_url": "",
                        "wattpad_enabled": 1,
                        "wattpad_story_id": w_story_id.strip(),
                        "wattpad_story_url": w_story_id.strip() if "wattpad.com" in w_story_id else "",
                        "start_chapter": int(w_start_ch),
                        "last_synced_chapter": int(w_last_ch),
                        "stop_chapter": int(w_stop_ch),
                        "interval_hours": float(w_interval),
                        "custom_cta": w_custom_cta.strip(),
                        "is_active": 1
                    })
                    st.success(f"🎉 تم تسجيل الرواية '{w_name}' بنجاح في جدول النشر بواتباد!")
                    st.rerun()

    # 3. عرض الروايات المسجلة في واتباد
    st.markdown("### 📚 الروايات المربوطة حالياً بواتباد")
    all_wp_novels = [n for n in syndication_db.get_all_syndicated_novels() if n.get("wattpad_enabled") == 1]
    if not all_wp_novels:
        st.info("لا توجد روايات مضافة لواتباد حتى الآن. استخدم النموذج أعلاه لإضافة قصة جديدة.")
    else:
        for nov in all_wp_novels:
            with st.container():
                col_info, col_status, col_actions = st.columns([3, 2, 1.5])
                with col_info:
                    st.markdown(f"**📖 {nov['novel_name']}**")
                    st.caption(f"معرف قصة واتباد: `{nov['wattpad_story_id'] or 'غير محدد'}` | المصدر: `{nov['blogger_label']}`")
                with col_status:
                    st.markdown(f"📊 آخر فصل تم نشره: **{nov['last_synced_chapter']}** / التوقف عند: **{nov['stop_chapter']}**")
                    st.caption(f"⏱️ الوتيرة: فصل كل {nov['interval_hours']} ساعة | الحالة: {'🟢 نشط' if nov['is_active'] else '🔴 متوقف'}")
                with col_actions:
                    if st.button("🗑️ حذف", key=f"del_wp_nov_{nov['id']}"):
                        syndication_db.delete_syndicated_novel(nov["id"])
                        st.success(f"تم حذف {nov['novel_name']}")
                        st.rerun()
                st.markdown("---")

    # 4. معاينة فصل في واتباد
    st.markdown("### 👁️ معاينة فصل (اختبار المحرك)")
    with st.expander("🔍 معاينة فصل جاهز للنشر على واتباد", expanded=False):
        all_wp_names = [n["novel_name"] for n in syndication_db.get_all_syndicated_novels() if n.get("wattpad_enabled") == 1]
        if not all_wp_names:
            st.info("أضف قصة أولاً من النموذج أعلاه.")
        else:
            col_pv1, col_pv2 = st.columns([2, 1])
            with col_pv1:
                wp_preview_novel = st.selectbox("📚 اختر الرواية:", all_wp_names, key="wp_preview_novel")
            with col_pv2:
                wp_preview_chapter = st.number_input("رقم الفصل:", min_value=1, value=1, step=1, key="wp_preview_chap")

            if st.button("🔍 جلب ومعاينة الفصل", key="wp_preview_btn", use_container_width=True):
                all_novs = syndication_db.get_all_syndicated_novels()
                nov_cfg = next((n for n in all_novs if n["novel_name"] == wp_preview_novel), None)
                custom_cta = nov_cfg["custom_cta"] if nov_cfg else ""
                blogger_url = nov_cfg["blogger_url"] if nov_cfg else ""

                with st.spinner(f"⏳ جاري سحب الفصل {wp_preview_chapter}..."):
                    result = syndication_extractor.prepare_chapter_for_publishing(
                        novel_name=wp_preview_novel,
                        chapter_num=int(wp_preview_chapter),
                        custom_cta=custom_cta,
                        blogger_url=blogger_url
                    )

                if result["success"]:
                    st.success(f"✅ تم جلب الفصل من المصدر: `{result['source']}`")
                    st.markdown(f"**📌 عنوان الفصل:** {result['title']}")
                    st.text_area("المتن المُجهَّز:", value=result["content_for_publish"][:500] + "...", height=180, disabled=True, key="wp_preview_output")
                    st.caption(f"📊 الطول: {len(result['content_for_publish']):,} حرف")
                    available = syndication_extractor.get_available_chapters_for_novel(wp_preview_novel)
                    if available:
                        st.info(f"📚 فصول متاحة: **{len(available)}** (من {min(available)} إلى {max(available)})")
                else:
                    st.error(f"❌ {result['error']}")

    # 5. سجل النشر الأخير (واتباد)
    st.markdown("### 📋 سجل النشر الأخير (واتباد)")
    recent_logs = syndication_db.get_recent_syndication_logs(limit=20)
    wp_logs = [l for l in recent_logs if l.get("platform") == "wattpad"]
    if not wp_logs:
        st.info("لا توجد سجلات نشر بعد.")
    else:
        for log in wp_logs:
            icon = "✅" if log["status"] == "SUCCESS" else "❌"
            st.markdown(f"{icon} **{log.get('novel_name','؟')}** — الفصل `{log['chapter_num']}` — `{log['published_at']}`")
            if log.get("post_url"):
                st.caption(f"🔗 {log['post_url']}")
            if log.get("error_msg"):
                st.caption(f"⚠️ {log['error_msg']}")
