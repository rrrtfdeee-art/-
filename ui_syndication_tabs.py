# -*- coding: utf-8 -*-
"""
ui_syndication_tabs.py — واجهة التبويبين لنادي الروايات وواتباد
تُستدعى في app.py لعرض الإعدادات والروايات المربوطة بدقة وأناقة دون لمس كود المنظومة الحساس.
"""

import streamlit as st
import syndication_db
import syndication_extractor

import time
import datetime

TZ_ARABIA = datetime.timezone(datetime.timedelta(hours=3))

def format_schedule_time_label(ts: float) -> str:
    """تنسيق وقت وتاريخ الجدولة بأسلوب عربي ذكي وفق توقيت مكة المكرمة/العراق (UTC+3)"""
    if not ts or ts <= 0:
        return "غير مجدول (بانتظار التحديد)"
    dt = datetime.datetime.fromtimestamp(ts, tz=TZ_ARABIA)
    now = datetime.datetime.now(TZ_ARABIA)
    today = now.date()
    target_date = dt.date()
    time_str = dt.strftime('%I:%M %p').replace("AM", "صباحاً").replace("PM", "مساءً")
    if target_date == today:
        day_str = "اليوم"
    elif target_date == today + datetime.timedelta(days=1):
        day_str = "غداً"
    elif target_date == today + datetime.timedelta(days=2):
        day_str = "بعد غد"
    else:
        day_str = dt.strftime('%Y-%m-%d')
    return f"{day_str} الساعة {time_str}"

def render_rewayat_club_tab():
    # التأكد من تشغيل المشغل الذاتي المجدول 24/7 في الخلفية
    try:
        import syndication_daemon
        syndication_daemon.start_syndication_daemon()
    except Exception:
        pass

    st.subheader("🏛️ إدارة النشر التلقائي — نادي الروايات (Rewayat Club)")
    st.caption("أتمتة سحب الفصول من مدونة عالم سماء الروايات ونشرها دورياً على حسابك في منصة rewayat.club.")

    col_stat1, col_stat2 = st.columns([3, 1])
    with col_stat1:
        st.markdown('<div style="background-color:#064e3b; border:1px solid #059669; border-radius:8px; padding:7px 14px; margin-bottom:12px; color:#6ee7b7; font-size:0.90rem; font-weight:bold;">🟢 <b>المجدول التلقائي الذاتي (24/7 Background Scheduler):</b> نشط ويعمل في الخلفية لمراقبة مواعيد الفصول ونشرها بدقة.</div>', unsafe_allow_html=True)
    with col_stat2:
        if st.button("🔄 فحص وجدولة الآن", key="rc_trigger_now", use_container_width=True):
            try:
                import syndication_daemon
                syndication_daemon.run_syndication_cycle()
                st.success("تم تشغيل دورة الفحص!")
                st.rerun()
            except Exception as ex_trig:
                st.error(f"خطأ: {ex_trig}")
    
    # 1. إعدادات حساب نادي الروايات
    with st.expander("🔐 بيانات حساب نادي الروايات (Authentication)", expanded=False):
        col_u, col_p = st.columns(2)
        stored_user = syndication_db.get_synd_setting("rewayat_username", "")
        stored_token = syndication_db.get_synd_setting("rewayat_token", "")
        
        with col_u:
            rewayat_user = st.text_input("اسم المستخدم / البريد:", value=stored_user, key="rc_user")
        with col_p:
            rewayat_token = st.text_input("رمز التوكن أو كلمة المرور (Bearer Token / Password):", value=stored_token, type="password", key="rc_token")
            
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            if st.button("💾 حفظ بيانات الحساب", key="save_rc_creds", use_container_width=True):
                syndication_db.save_synd_setting("rewayat_username", rewayat_user.strip())
                syndication_db.save_synd_setting("rewayat_token", rewayat_token.strip())
                st.success("تم حفظ بيانات الدخول لنادي الروايات بنجاح.")
        with col_s2:
            if st.button("🔍 فحص الاتصال بالحساب", key="test_rc_conn", use_container_width=True):
                import rewayat_club_api
                client = rewayat_club_api.RewayatClubClient(
                    token=rewayat_token.strip() or stored_token,
                    username=rewayat_user.strip() or stored_user
                )
                chk = client.test_connection()
                if chk.get("success"):
                    st.success(f"✅ {chk.get('message')}")
                else:
                    st.warning(f"⚠️ {chk.get('message')}")

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
                interval = st.number_input("⏱️ معدل النشر (ساعات بين كل فصل):", min_value=0.25, value=1.0, step=0.25)

            col_ad1, col_ad2, col_ad3 = st.columns([1.5, 1.5, 1])
            with col_ad1:
                rc_add_date = st.date_input("📅 تاريخ بدء النشر:", value=datetime.date.today(), key="rc_add_d")
            with col_ad2:
                rc_add_time = st.time_input("⏰ وقت بدء النشر:", value=datetime.datetime.now().time().replace(second=0, microsecond=0), key="rc_add_t")
            with col_ad3:
                rc_add_now = st.checkbox("🚀 البدء فوراً (الآن)", value=True, key="rc_add_now_chk")

            cta_default = "✨ استمتعتم بالفصل؟ لمتابعة الفصول الحصرية والمتقدمة فور صدورها زوروا موقعنا الأصلي: [رابط الرواية] ✨"
            custom_cta = st.text_area("💬 التعليق التحفيزي الثابت لنهاية كل فصل:", value=cta_default, height=70)
            
            submit_btn = st.form_submit_button("🚀 حفظ الرواية وبدء جدولتها", type="primary")
            if submit_btn:
                if not n_name.strip():
                    st.error("يرجى إدخال اسم الرواية على الأقل.")
                else:
                    if rc_add_now:
                        init_next_run = 0.0
                    else:
                        init_next_run = datetime.datetime.combine(rc_add_date, rc_add_time).timestamp()
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
                        "next_run_timestamp": float(init_next_run),
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
                    target_ch = nov['last_synced_chapter'] + 1
                    st.markdown(f"📊 آخر فصل تم نشره: **{nov['last_synced_chapter']}** / التوقف عند: **{nov['stop_chapter']}**")
                    next_run = nov.get("next_run_timestamp", 0.0)
                    now_ts = time.time()
                    if not nov['is_active']:
                        st.caption(f"⏸️ **النشر متوقف:** اضغط 'استئناف' أو اختر موعداً للبدء.")
                    elif next_run and next_run > now_ts:
                        rem_hours = (next_run - now_ts) / 3600.0
                        dt_label = format_schedule_time_label(next_run)
                        st.caption(f"⏳ **موعد الفصل {target_ch}:** {dt_label} (بعد {rem_hours:.1f} ساعة)")
                    elif next_run and next_run <= now_ts:
                        st.caption(f"🟢 **الفصل {target_ch}:** حان موعده وجاهز للنشر في الدورة الحالية")
                    else:
                        st.caption(f"⏸️ **غير مجدول:** حدد موعد الانطلاق من الأسفل للبدء.")
                    st.caption(f"⏱️ الوتيرة: فصل كل {nov['interval_hours']} ساعة | الحالة: {'🟢 نشط' if nov['is_active'] else '🔴 متوقف'}")
                with col_actions:
                    if st.button("⚡ نشر فوراً", key=f"fast_pub_{nov['id']}", help="نشر الفصل القادم الآن دون انتظار المؤقت"):
                        nov["next_run_timestamp"] = time.time()
                        nov["is_active"] = 1
                        syndication_db.save_or_update_syndicated_novel(nov)
                        try:
                            import syndication_daemon
                            syndication_daemon.run_syndication_cycle()
                            st.success(f"تم إطلاق نشر الفصل {target_ch}!")
                            st.rerun()
                        except Exception as ex_f:
                            st.error(f"خطأ: {ex_f}")
                    if st.button("🗑️ حذف", key=f"del_rc_nov_{nov['id']}"):
                        syndication_db.delete_syndicated_novel(nov["id"])
                        st.success(f"تم حذف {nov['novel_name']}")
                        st.rerun()

                # قسم تعديل الإعدادات والجدولة السريعة لدفعة الفصول
                with st.expander(f"⚙️ تعديل الجدولة ووتيرة النشر ({nov['novel_name']})", expanded=False):
                    st.markdown("##### 🚀 الجدولة السريعة (وضع الدفعات — بتوقيت مكة والعراق):")
                    c_b1, c_b2, c_b3, c_b4 = st.columns(4)
                    now_ar = datetime.datetime.now(TZ_ARABIA)
                    today_ar = now_ar.date()
                    tmrw_ar = today_ar + datetime.timedelta(days=1)
                    t_10am = datetime.datetime.combine(tmrw_ar, datetime.time(10, 0), tzinfo=TZ_ARABIA).timestamp()
                    t_6pm = datetime.datetime.combine(tmrw_ar, datetime.time(18, 0), tzinfo=TZ_ARABIA).timestamp()
                    t_midnight = datetime.datetime.combine(tmrw_ar, datetime.time(0, 0), tzinfo=TZ_ARABIA).timestamp()

                    with c_b1:
                        if st.button("🚀 البدء الآن (20 فصل)", key=f"quick_now_{nov['id']}", use_container_width=True, help="نشر 20 فصلاً بمعدل فصل كل ساعة بدءاً من هذه اللحظة"):
                            nov["interval_hours"] = 1.0
                            nov["stop_chapter"] = nov["last_synced_chapter"] + 20
                            nov["next_run_timestamp"] = time.time()
                            nov["is_active"] = 1
                            syndication_db.save_or_update_syndicated_novel(nov)
                            st.success(f"تم الضبط! سينطلق النشر فوراً لـ 20 فصلاً (حتى الفصل {nov['stop_chapter']}) بمعدل فصل كل ساعة.")
                            st.rerun()
                    with c_b2:
                        if st.button("🌅 غداً 10:00 ص (20 فصل)", key=f"quick_tmrw10_{nov['id']}", use_container_width=True, help="بدء النشر غداً في تمام العاشرة صباحاً بتوقيت مكة/العراق"):
                            nov["interval_hours"] = 1.0
                            nov["stop_chapter"] = nov["last_synced_chapter"] + 20
                            nov["next_run_timestamp"] = t_10am
                            nov["is_active"] = 1
                            syndication_db.save_or_update_syndicated_novel(nov)
                            st.success(f"تمت الجدولة! سيبدأ أول فصل غداً في تمام 10:00 صباحاً (توقيت مكة)، ثم فصلاً كل ساعة حتى الفصل {nov['stop_chapter']}.")
                            st.rerun()
                    with c_b3:
                        if st.button("🌆 غداً 06:00 م (20 فصل)", key=f"quick_tmrw18_{nov['id']}", use_container_width=True, help="بدء النشر غداً في تمام السادسة مساءً بتوقيت مكة/العراق"):
                            nov["interval_hours"] = 1.0
                            nov["stop_chapter"] = nov["last_synced_chapter"] + 20
                            nov["next_run_timestamp"] = t_6pm
                            nov["is_active"] = 1
                            syndication_db.save_or_update_syndicated_novel(nov)
                            st.success(f"تمت الجدولة! سيبدأ أول فصل غداً في تمام 06:00 مساءً (توقيت مكة)، ثم فصلاً كل ساعة حتى الفصل {nov['stop_chapter']}.")
                            st.rerun()
                    with c_b4:
                        if st.button("🌙 غداً 12:00 ليلاً (20 فصل)", key=f"quick_tmrw00_{nov['id']}", use_container_width=True, help="بدء النشر غداً في منتصف الليل بتوقيت مكة/العراق"):
                            nov["interval_hours"] = 1.0
                            nov["stop_chapter"] = nov["last_synced_chapter"] + 20
                            nov["next_run_timestamp"] = t_midnight
                            nov["is_active"] = 1
                            syndication_db.save_or_update_syndicated_novel(nov)
                            st.success(f"تمت الجدولة! سيبدأ أول فصل غداً في تمام 12:00 منتصف الليل، ثم فصلاً كل ساعة حتى الفصل {nov['stop_chapter']}.")
                            st.rerun()

                    if st.button("⏸️ إيقاف / استئناف النشر التلقائي للرواية", key=f"toggle_act_{nov['id']}", use_container_width=True):
                        nov["is_active"] = 0 if nov["is_active"] else 1
                        syndication_db.save_or_update_syndicated_novel(nov)
                        st.info(f"تم تغيير الحالة إلى: {'🟢 نشط' if nov['is_active'] else '🔴 متوقف'}")
                        st.rerun()
                    
                    st.markdown("##### ✏️ ضبط يدوي مخصص (تحديد التاريخ والوقت بتوقيت مكة والعراق):")
                    with st.form(f"edit_novel_form_{nov['id']}"):
                        ce1, ce2, ce3 = st.columns(3)
                        with ce1:
                            new_interval = st.number_input("⏱️ الوتيرة (ساعات بين كل فصل):", min_value=0.25, value=float(nov['interval_hours']), step=0.25, key=f"int_{nov['id']}")
                        with ce2:
                            new_last_ch = st.number_input("آخر فصل تم نشره:", min_value=0, value=int(nov['last_synced_chapter']), step=1, key=f"last_{nov['id']}")
                        with ce3:
                            new_stop_ch = st.number_input("سقف التوقف (آخر فصل):", min_value=1, value=int(nov['stop_chapter']), step=1, key=f"stop_{nov['id']}")
                        
                        st.markdown("###### 📅 موعد انطلاق أول فصل قادم:")
                        cf1, cf2, cf3 = st.columns([1.5, 1.5, 1])
                        cur_nr = nov.get("next_run_timestamp", 0.0)
                        def_dt = datetime.datetime.fromtimestamp(cur_nr, tz=TZ_ARABIA) if cur_nr and cur_nr > time.time() else datetime.datetime.now(TZ_ARABIA)
                        with cf1:
                            edit_date = st.date_input("تاريخ الانطلاق:", value=def_dt.date(), key=f"ed_d_{nov['id']}")
                        with cf2:
                            edit_time = st.time_input("وقت الانطلاق:", value=def_dt.time().replace(second=0, microsecond=0), key=f"ed_t_{nov['id']}")
                        with cf3:
                            edit_now_chk = st.checkbox("🚀 فوراً (الآن)", value=False, key=f"ed_now_{nov['id']}")

                        btn_save_edit = st.form_submit_button("💾 حفظ الإعدادات وموعد الجدولة", type="primary")
                        if btn_save_edit:
                            nov["interval_hours"] = float(new_interval)
                            nov["last_synced_chapter"] = int(new_last_ch)
                            nov["stop_chapter"] = int(new_stop_ch)
                            if edit_now_chk:
                                nov["next_run_timestamp"] = time.time()
                                nov["is_active"] = 1
                            else:
                                combined_dt = datetime.datetime.combine(edit_date, edit_time, tzinfo=TZ_ARABIA)
                                nov["next_run_timestamp"] = combined_dt.timestamp()
                                nov["is_active"] = 1
                            syndication_db.save_or_update_syndicated_novel(nov)
                            st.success("تم تحديث إعدادات وموعد جدولة الرواية بنجاح!")
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

                    st.markdown("---")
                    st.markdown("##### 🚀 النشر التجريبي الفعلي (Live Publishing Test)")
                    if st.button("📤 نشر هذا الفصل الآن إلى نادي الروايات", key="rc_live_publish_btn", type="primary"):
                        import rewayat_club_api
                        user_token = syndication_db.get_synd_setting("rewayat_token", "")
                        if not user_token:
                            st.error("❌ يرجى إدخال وحفظ التوكن (Bearer Token) لحساب نادي الروايات أولاً.")
                        elif not nov_cfg.get("rewayat_novel_id"):
                            st.error("❌ الرواية لا تحتوي على معرف (Novel ID) في نادي الروايات.")
                        else:
                            with st.spinner("⏳ جاري إرسال الفصل إلى منصة نادي الروايات..."):
                                client = rewayat_club_api.RewayatClubClient(token=user_token)
                                pub_res = client.publish_chapter(
                                    novel_id=nov_cfg["rewayat_novel_id"],
                                    chapter_num=int(preview_chapter),
                                    title=result["title"],
                                    content=result["content_for_publish"]
                                )
                                if pub_res.get("success"):
                                    st.balloons()
                                    st.success(f"🎉 {pub_res.get('message')}")
                                    # توثيق في السجل
                                    syndication_db.log_syndication_event(
                                        novel_id=nov_cfg["id"],
                                        chapter_num=int(preview_chapter),
                                        platform="rewayat_club",
                                        status="SUCCESS",
                                        post_url=pub_res.get("post_url", "")
                                    )
                                    # تحديث عداد آخر فصل تم نشره إذا كان هذا الفصل أحدث
                                    if int(preview_chapter) > nov_cfg.get("last_synced_chapter", 0):
                                        nov_cfg["last_synced_chapter"] = int(preview_chapter)
                                        syndication_db.save_or_update_syndicated_novel(nov_cfg)
                                    st.rerun()
                                else:
                                    st.error(f"❌ {pub_res.get('error')}")
                                    syndication_db.log_syndication_event(
                                        novel_id=nov_cfg["id"],
                                        chapter_num=int(preview_chapter),
                                        platform="rewayat_club",
                                        status="FAILED",
                                        error_msg=pub_res.get("error", "")
                                    )
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
    # التأكد من تشغيل المشغل الذاتي المجدول 24/7 في الخلفية
    try:
        import syndication_daemon
        syndication_daemon.start_syndication_daemon()
    except Exception:
        pass

    st.subheader("🟧 إدارة النشر التلقائي — واتباد (Wattpad)")
    st.caption("أتمتة سحب الفصول من مدونة عالم سماء الروايات ونشرها كأجزاء داخل قصص حسابك على Wattpad.")

    col_stat1, col_stat2 = st.columns([3, 1])
    with col_stat1:
        st.markdown('<div style="background-color:#064e3b; border:1px solid #059669; border-radius:8px; padding:7px 14px; margin-bottom:12px; color:#6ee7b7; font-size:0.90rem; font-weight:bold;">🟢 <b>المجدول التلقائي الذاتي (24/7 Background Scheduler):</b> نشط ويعمل في الخلفية لمراقبة مواعيد الفصول ونشرها بدقة.</div>', unsafe_allow_html=True)
    with col_stat2:
        if st.button("🔄 فحص وجدولة الآن", key="wp_trigger_now", use_container_width=True):
            try:
                import syndication_daemon
                syndication_daemon.run_syndication_cycle()
                st.success("تم تشغيل دورة الفحص!")
                st.rerun()
            except Exception as ex_trig:
                st.error(f"خطأ: {ex_trig}")
    
    # 1. إعدادات حساب واتباد
    with st.expander("🔐 بيانات حساب واتباد والدخول التلقائي (Wattpad Auto-Login)", expanded=False):
        col_u, col_pwd, col_p = st.columns(3)
        stored_w_user = syndication_db.get_synd_setting("wattpad_username", "")
        stored_w_pass = syndication_db.get_synd_setting("wattpad_password", "")
        stored_w_token = syndication_db.get_synd_setting("wattpad_token", "")
        
        with col_u:
            wattpad_user = st.text_input("اسم المستخدم / الإيميل:", value=stored_w_user, key="wp_user")
        with col_pwd:
            wattpad_pass = st.text_input("كلمة المرور (للتسجيل الذاتي):", value=stored_w_pass, type="password", key="wp_pwd")
        with col_p:
            wattpad_token = st.text_input("رمز التوكن (يُجلب تلقائياً):", value=stored_w_token, type="password", key="wp_token")
        st.caption("💡 **الدخول التلقائي الذاتي:** عند إدخال اسم المستخدم وكلمة المرور، يقوم النظام بالدخول التلقائي وتجديد التوكن ذاتياً دون الحاجة لنسخه يدوياً في كل جلسة.")
            
        col_w1, col_w2, col_w3 = st.columns(3)
        with col_w1:
            if st.button("💾 حفظ البيانات", key="save_wp_creds", use_container_width=True):
                syndication_db.save_synd_setting("wattpad_username", wattpad_user.strip())
                syndication_db.save_synd_setting("wattpad_password", wattpad_pass.strip())
                syndication_db.save_synd_setting("wattpad_token", wattpad_token.strip())
                st.success("تم حفظ بيانات الدخول لواتباد بنجاح.")
        with col_w2:
            if st.button("🔄 تسجيل دخول وتجديد التوكن", key="wp_auto_login_btn", use_container_width=True):
                import wattpad_poster
                w_client = wattpad_poster.WattpadClient(
                    username=wattpad_user.strip() or stored_w_user,
                    password=wattpad_pass.strip() or stored_w_pass
                )
                login_res = w_client.auto_login()
                if login_res.get("success"):
                    st.success(f"✅ {login_res.get('message')}")
                    st.rerun()
                else:
                    st.error(f"❌ {login_res.get('message')}")
        with col_w3:
            if st.button("🔍 فحص الاتصال والحساب", key="test_wp_conn", use_container_width=True):
                import wattpad_poster
                w_client = wattpad_poster.WattpadClient(
                    token=wattpad_token.strip() or stored_w_token,
                    username=wattpad_user.strip() or stored_w_user,
                    password=wattpad_pass.strip() or stored_w_pass
                )
                w_chk = w_client.test_connection()
                if w_chk.get("success"):
                    st.success(f"✅ {w_chk.get('message')}")
                else:
                    st.warning(f"⚠️ {w_chk.get('message')}")

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
                w_interval = st.number_input("⏱️ معدل النشر (ساعات):", min_value=0.25, value=1.0, step=0.25, key="wp_interval")

            col_wad1, col_wad2, col_wad3 = st.columns([1.5, 1.5, 1])
            with col_wad1:
                wp_add_date = st.date_input("📅 تاريخ بدء النشر:", value=datetime.date.today(), key="wp_add_d")
            with col_wad2:
                wp_add_time = st.time_input("⏰ وقت بدء النشر:", value=datetime.datetime.now().time().replace(second=0, microsecond=0), key="wp_add_t")
            with col_wad3:
                wp_add_now = st.checkbox("🚀 البدء فوراً (الآن)", value=True, key="wp_add_now_chk")

            w_cta_default = "✨ استمتعتم بالفصل؟ لمتابعة الفصول الحصرية والمتقدمة فور صدورها تفضلوا بزيارة موقعنا: [رابط الرواية] ✨"
            w_custom_cta = st.text_area("💬 التعليق التحفيزي لقصة واتباد:", value=w_cta_default, height=70, key="wp_cta")
            
            w_submit_btn = st.form_submit_button("🚀 حفظ الرواية وبدء جدولتها على واتباد", type="primary")
            if w_submit_btn:
                if not w_name.strip():
                    st.error("يرجى إدخال اسم الرواية على الأقل.")
                else:
                    if wp_add_now:
                        init_wp_next_run = 0.0
                    else:
                        init_wp_next_run = datetime.datetime.combine(wp_add_date, wp_add_time).timestamp()
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
                        "next_run_timestamp": float(init_wp_next_run),
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
                    target_ch = nov['last_synced_chapter'] + 1
                    st.markdown(f"📊 آخر فصل تم نشره: **{nov['last_synced_chapter']}** / التوقف عند: **{nov['stop_chapter']}**")
                    next_run = nov.get("next_run_timestamp", 0.0)
                    now_ts = time.time()
                    if not nov['is_active']:
                        st.caption(f"⏸️ **النشر متوقف:** اضغط 'استئناف' أو اختر موعداً للبدء.")
                    elif next_run and next_run > now_ts:
                        rem_hours = (next_run - now_ts) / 3600.0
                        dt_label = format_schedule_time_label(next_run)
                        st.caption(f"⏳ **موعد الفصل {target_ch}:** {dt_label} (بعد {rem_hours:.1f} ساعة)")
                    elif next_run and next_run <= now_ts:
                        st.caption(f"🟢 **الفصل {target_ch}:** حان موعده وجاهز للنشر في الدورة الحالية")
                    else:
                        st.caption(f"⏸️ **غير مجدول:** حدد موعد الانطلاق من الأسفل للبدء.")
                    st.caption(f"⏱️ الوتيرة: فصل كل {nov['interval_hours']} ساعة | الحالة: {'🟢 نشط' if nov['is_active'] else '🔴 متوقف'}")
                with col_actions:
                    if st.button("⚡ نشر فوراً", key=f"fast_pub_wp_{nov['id']}", help="نشر الفصل القادم الآن دون انتظار المؤقت"):
                        nov["next_run_timestamp"] = time.time()
                        nov["is_active"] = 1
                        syndication_db.save_or_update_syndicated_novel(nov)
                        try:
                            import syndication_daemon
                            syndication_daemon.run_syndication_cycle()
                            st.success(f"تم إطلاق نشر الفصل {target_ch}!")
                            st.rerun()
                        except Exception as ex_f:
                            st.error(f"خطأ: {ex_f}")
                    if st.button("🗑️ حذف", key=f"del_wp_nov_{nov['id']}"):
                        syndication_db.delete_syndicated_novel(nov["id"])
                        st.success(f"تم حذف {nov['novel_name']}")
                        st.rerun()

                # قسم تعديل الإعدادات والجدولة السريعة لدفعة الفصول لواتباد
                with st.expander(f"⚙️ تعديل الجدولة ووتيرة النشر ({nov['novel_name']})", expanded=False):
                    st.markdown("##### 🚀 الجدولة السريعة (وضع الدفعات — بتوقيت مكة والعراق):")
                    c_wb1, c_wb2, c_wb3, c_wb4 = st.columns(4)
                    now_ar = datetime.datetime.now(TZ_ARABIA)
                    today_ar = now_ar.date()
                    tmrw_ar = today_ar + datetime.timedelta(days=1)
                    t_10am = datetime.datetime.combine(tmrw_ar, datetime.time(10, 0), tzinfo=TZ_ARABIA).timestamp()
                    t_6pm = datetime.datetime.combine(tmrw_ar, datetime.time(18, 0), tzinfo=TZ_ARABIA).timestamp()
                    t_midnight = datetime.datetime.combine(tmrw_ar, datetime.time(0, 0), tzinfo=TZ_ARABIA).timestamp()

                    with c_wb1:
                        if st.button("🚀 البدء الآن (20 فصل)", key=f"wp_quick_now_{nov['id']}", use_container_width=True, help="نشر 20 فصلاً بمعدل فصل كل ساعة بدءاً من هذه اللحظة"):
                            nov["interval_hours"] = 1.0
                            nov["stop_chapter"] = nov["last_synced_chapter"] + 20
                            nov["next_run_timestamp"] = time.time()
                            nov["is_active"] = 1
                            syndication_db.save_or_update_syndicated_novel(nov)
                            st.success(f"تم الضبط! سينطلق النشر فوراً لـ 20 فصلاً على واتباد (حتى الفصل {nov['stop_chapter']}) بمعدل فصل كل ساعة.")
                            st.rerun()
                    with c_wb2:
                        if st.button("🌅 غداً 10:00 ص (20 فصل)", key=f"wp_quick_tmrw10_{nov['id']}", use_container_width=True, help="بدء النشر على واتباد غداً في تمام العاشرة صباحاً بتوقيت مكة/العراق"):
                            nov["interval_hours"] = 1.0
                            nov["stop_chapter"] = nov["last_synced_chapter"] + 20
                            nov["next_run_timestamp"] = t_10am
                            nov["is_active"] = 1
                            syndication_db.save_or_update_syndicated_novel(nov)
                            st.success(f"تمت الجدولة! سيبدأ أول فصل على واتباد غداً في تمام 10:00 صباحاً (توقيت مكة)، ثم فصلاً كل ساعة حتى الفصل {nov['stop_chapter']}.")
                            st.rerun()
                    with c_wb3:
                        if st.button("🌆 غداً 06:00 م (20 فصل)", key=f"wp_quick_tmrw18_{nov['id']}", use_container_width=True, help="بدء النشر على واتباد غداً في تمام السادسة مساءً بتوقيت مكة/العراق"):
                            nov["interval_hours"] = 1.0
                            nov["stop_chapter"] = nov["last_synced_chapter"] + 20
                            nov["next_run_timestamp"] = t_6pm
                            nov["is_active"] = 1
                            syndication_db.save_or_update_syndicated_novel(nov)
                            st.success(f"تمت الجدولة! سيبدأ أول فصل على واتباد غداً في تمام 06:00 مساءً (توقيت مكة)، ثم فصلاً كل ساعة حتى الفصل {nov['stop_chapter']}.")
                            st.rerun()
                    with c_wb4:
                        if st.button("🌙 غداً 12:00 ليلاً (20 فصل)", key=f"wp_quick_tmrw00_{nov['id']}", use_container_width=True, help="بدء النشر على واتباد غداً في منتصف الليل بتوقيت مكة/العراق"):
                            nov["interval_hours"] = 1.0
                            nov["stop_chapter"] = nov["last_synced_chapter"] + 20
                            nov["next_run_timestamp"] = t_midnight
                            nov["is_active"] = 1
                            syndication_db.save_or_update_syndicated_novel(nov)
                            st.success(f"تمت الجدولة! سيبدأ أول فصل على واتباد غداً في تمام 12:00 منتصف الليل، ثم فصلاً كل ساعة حتى الفصل {nov['stop_chapter']}.")
                            st.rerun()

                    if st.button("⏸️ إيقاف / استئناف النشر التلقائي لواتباد", key=f"wp_toggle_act_{nov['id']}", use_container_width=True):
                        nov["is_active"] = 0 if nov["is_active"] else 1
                        syndication_db.save_or_update_syndicated_novel(nov)
                        st.info(f"تم تغيير الحالة إلى: {'🟢 نشط' if nov['is_active'] else '🔴 متوقف'}")
                        st.rerun()
                    
                    st.markdown("##### ✏️ ضبط يدوي مخصص (تحديد التاريخ والوقت بتوقيت مكة والعراق):")
                    with st.form(f"wp_edit_novel_form_{nov['id']}"):
                        ce1, ce2, ce3 = st.columns(3)
                        with ce1:
                            new_interval = st.number_input("⏱️ الوتيرة (ساعات بين كل فصل):", min_value=0.25, value=float(nov['interval_hours']), step=0.25, key=f"wp_int_{nov['id']}")
                        with ce2:
                            new_last_ch = st.number_input("آخر فصل تم نشره:", min_value=0, value=int(nov['last_synced_chapter']), step=1, key=f"wp_last_{nov['id']}")
                        with ce3:
                            new_stop_ch = st.number_input("سقف التوقف (آخر فصل):", min_value=1, value=int(nov['stop_chapter']), step=1, key=f"wp_stop_{nov['id']}")
                        
                        st.markdown("###### 📅 موعد انطلاق أول فصل قادم على واتباد:")
                        cf1, cf2, cf3 = st.columns([1.5, 1.5, 1])
                        cur_nr = nov.get("next_run_timestamp", 0.0)
                        def_dt = datetime.datetime.fromtimestamp(cur_nr, tz=TZ_ARABIA) if cur_nr and cur_nr > time.time() else datetime.datetime.now(TZ_ARABIA)
                        with cf1:
                            edit_date = st.date_input("تاريخ الانطلاق:", value=def_dt.date(), key=f"wp_ed_d_{nov['id']}")
                        with cf2:
                            edit_time = st.time_input("وقت الانطلاق:", value=def_dt.time().replace(second=0, microsecond=0), key=f"wp_ed_t_{nov['id']}")
                        with cf3:
                            edit_now_chk = st.checkbox("🚀 فوراً (الآن)", value=False, key=f"wp_ed_now_{nov['id']}")

                        btn_save_edit = st.form_submit_button("💾 حفظ الإعدادات وموعد الجدولة", type="primary")
                        if btn_save_edit:
                            nov["interval_hours"] = float(new_interval)
                            nov["last_synced_chapter"] = int(new_last_ch)
                            nov["stop_chapter"] = int(new_stop_ch)
                            if edit_now_chk:
                                nov["next_run_timestamp"] = time.time()
                                nov["is_active"] = 1
                            else:
                                combined_dt = datetime.datetime.combine(edit_date, edit_time, tzinfo=TZ_ARABIA)
                                nov["next_run_timestamp"] = combined_dt.timestamp()
                                nov["is_active"] = 1
                            syndication_db.save_or_update_syndicated_novel(nov)
                            st.success("تم تحديث إعدادات وموعد جدولة الرواية على واتباد بنجاح!")
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

                    st.markdown("---")
                    st.markdown("##### 🚀 النشر التجريبي الفعلي (Live Publishing to Wattpad)")
                    if st.button("📤 نشر هذا الفصل الآن إلى قصة واتباد", key="wp_live_publish_btn", type="primary"):
                        import wattpad_poster
                        w_user_token = syndication_db.get_synd_setting("wattpad_token", "")
                        if not w_user_token:
                            st.error("❌ يرجى إدخال وحفظ التوكن لحساب واتباد أولاً.")
                        elif not nov_cfg.get("wattpad_story_id"):
                            st.error("❌ الرواية لا تحتوي على معرف قصة (Story ID) في واتباد.")
                        else:
                            with st.spinner("⏳ جاري إرسال الفصل كجزء جديد إلى قصة واتباد..."):
                                w_client = wattpad_poster.WattpadClient(token=w_user_token)
                                w_pub_res = w_client.publish_chapter_to_story(
                                    story_id=nov_cfg["wattpad_story_id"],
                                    chapter_num=int(wp_preview_chapter),
                                    title=result["title"],
                                    content=result["content_for_publish"]
                                )
                                if w_pub_res.get("success"):
                                    st.balloons()
                                    st.success(f"🎉 {w_pub_res.get('message')}")
                                    syndication_db.log_syndication_event(
                                        novel_id=nov_cfg["id"],
                                        chapter_num=int(wp_preview_chapter),
                                        platform="wattpad",
                                        status="SUCCESS",
                                        post_url=w_pub_res.get("post_url", "")
                                    )
                                    if int(wp_preview_chapter) > nov_cfg.get("last_synced_chapter", 0):
                                        nov_cfg["last_synced_chapter"] = int(wp_preview_chapter)
                                        syndication_db.save_or_update_syndicated_novel(nov_cfg)
                                    st.rerun()
                                else:
                                    st.error(f"❌ {w_pub_res.get('error')}")
                                    syndication_db.log_syndication_event(
                                        novel_id=nov_cfg["id"],
                                        chapter_num=int(wp_preview_chapter),
                                        platform="wattpad",
                                        status="FAILED",
                                        error_msg=w_pub_res.get("error", "")
                                    )
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
