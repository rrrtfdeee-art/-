# -*- coding: utf-8 -*-
"""
ui_syndication_tabs.py — واجهة التبويبين لنادي الروايات وواتباد
تُستدعى في app.py لعرض الإعدادات والروايات المربوطة بدقة وأناقة دون لمس كود المنظومة الحساس.
"""

import streamlit as st
import syndication_db
import syndication_extractor
import json
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
        st.markdown('<div style="background-color:#064e3b; border:1px solid #059669; border-radius:8px; padding:7px 14px; margin-bottom:12px; color:#6ee7b7; font-size:0.90rem; font-weight:bold;">🟢 <b>المجدول الذاتي وسحابة Google Sheet:</b> متصل بالجدول السحابي ونشط 24/7 — الفصول والمواعيد محفوظة سحابياً ضد انقطاع السيرفر.</div>', unsafe_allow_html=True)
    with col_stat2:
        if st.button("🔄 مزامنة وفحص الآن", key="rc_trigger_now", use_container_width=True):
            try:
                import syndication_daemon
                syndication_db.sync_novels_from_sheet()
                syndication_db.sync_schedule_from_sheet()
                syndication_daemon.run_syndication_cycle()
                st.success("تمت استعادة إعدادات الروايات والفصول من Google Sheet وتشغيل دورة الفحص!")
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

    # 2. إضافة رواية جديدة وجدولة فصولها (بالروابط فقط أو بالتخصيص الكامل)
    with st.expander("➕ إضافة رواية جديدة وجدولة فصولها في Google Sheet", expanded=True):
        st.markdown("##### 🔗 1️⃣ الإضافة السريعة بالروابط (رابط نادي الروايات + رابط الموقع):")
        st.caption("أدخل الرابطين فقط واضغط 'فحص وتعبئة البيانات' ليقوم السيرفر باستنتاج اسم الرواية، المعرف، والتصنيف، وآخر فصل منشور تلقائياً!")

        col_url1, col_url2 = st.columns(2)
        with col_url1:
            rc_quick_novel_url = st.text_input(
                "🆔 رابط أو معرّف الرواية في نادي الروايات:",
                placeholder="https://rewayat.club/novel/reverend-insanity أو المعرف فقط",
                key="rc_quick_novel_url"
            )
        with col_url2:
            rc_quick_blogger_url = st.text_input(
                "🌐 رابط صفحة الرواية في الموقع (المدونة / Novelskyworld):",
                placeholder="https://www.novelskyworld.com/p/... أو رابط بلوجر",
                key="rc_quick_blogger_url"
            )

        col_btn_auto, col_btn_direct = st.columns([2, 2])
        with col_btn_auto:
            if st.button("🔍 فحص واستيراد البيانات تلقائياً", key="rc_auto_fill_btn", use_container_width=True):
                if not rc_quick_novel_url.strip() and not rc_quick_blogger_url.strip():
                    st.error("❌ يرجى إدخال رابط نادي الروايات أو رابط الموقع أولاً.")
                else:
                    with st.spinner("⏳ جاري فحص الروابط واستخراج البيانات تلقائياً..."):
                        ins_res = syndication_extractor.inspect_novel_links(
                            platform="rewayat_club",
                            platform_url=rc_quick_novel_url.strip(),
                            blogger_url=rc_quick_blogger_url.strip()
                        )
                        if ins_res.get("novel_name"):
                            st.session_state["rc_uni_name"] = ins_res["novel_name"]
                        if ins_res.get("clean_id"):
                            st.session_state["rc_uni_id"] = ins_res["clean_id"]
                        if ins_res.get("blogger_url"):
                            st.session_state["rc_uni_burl"] = ins_res["blogger_url"]
                        if ins_res.get("blogger_label"):
                            st.session_state["rc_uni_blbl"] = ins_res["blogger_label"]
                        if "last_chapter" in ins_res:
                            st.session_state["rc_uni_last"] = int(ins_res["last_chapter"])
                            st.session_state["rc_uni_start"] = 1
                            st.session_state["rc_uni_stop"] = int(ins_res["stop_chapter"])
                        st.success(f"✅ تم بنجاح جلب بيانات '{ins_res.get('novel_name')}'! آخر فصل منشور: {ins_res.get('last_chapter')}")
                        st.rerun()

        st.markdown("---")
        st.markdown("##### ⚙️ 2️⃣ خيارات التخصيص والجدولة (يمكنك تعديل أي حقل بحرية):")
        rc_c1, rc_c2 = st.columns(2)
        with rc_c1:
            n_name = st.text_input("🏷️ اسم الرواية (مطلوب):", placeholder="مثال: Shadow Slave", key="rc_uni_name")
            n_rewayat_id = st.text_input("🆔 معرّف أو رابط الرواية في نادي الروايات (مطلوب):", placeholder="مثال: 5420 أو https://rewayat.club/novel/...", key="rc_uni_id")
        with rc_c2:
            rc_ch1, rc_ch2, rc_ch3 = st.columns(3)
            with rc_ch1:
                n_start_ch = st.number_input("من الفصل (بداية الترقيم):", min_value=1, value=1, step=1, help="رقم أول فصل تريد جدولته في الشيت (مثلاً 1)", key="rc_uni_start")
            with rc_ch2:
                n_stop_ch = st.number_input("إلى الفصل (نهاية الترقيم):", min_value=1, value=50, step=1, help="آخر فصل في الدفعة تتوقف عنده الجدولة (مثلاً 50 أو 100)", key="rc_uni_stop")
            with rc_ch3:
                n_last_ch = st.number_input("آخر فصل نُشر مسبقاً (تخطي تلقائي):", min_value=0, value=0, step=1, help="حدد هنا آخر فصل منشور لتخطيه تلقائياً! مثلاً إذا كتبت 23، سيبدأ السيرفر فوراً بنشر الفصل 24 وما بعده دون تكرار الفصول القديمة.", key="rc_uni_last")
        
        st.info("💡 **توضيح أرقام الفصول:** 'من الفصل' و 'إلى الفصل' يحددان نطاق الفصول المراد جدولتها في الشيت. أما **'آخر فصل نُشر مسبقاً'** فهو الأهم لتحديد نقطة انطلاق النشر الفعلي: إذا وضعت فيه `23`، سيتخطى السيرفر تلقائياً كافة الفصول حتى 23 ويبدأ فوراً بنشر الفصل **24**!")

        st.markdown("##### 3️⃣ معدل النشر التلقائي وموعد الانطلاق:")
        rc_c_rate1, rc_c_rate2 = st.columns(2)
        with rc_c_rate1:
            rc_interval_val = st.number_input("⏱️ معدل النشر (ساعات بين كل فصل):", min_value=0.25, max_value=168.0, value=24.0, step=0.5, help="مثال: 24 = فصل كل يوم، 12 = فصلين يومياً، 1 = فصل كل ساعة", key="rc_uni_int")
        with rc_c_rate2:
            rc_start_now = st.radio("⏰ موعد انطلاق أول فصل:", ["start_after_interval", "start_now"], format_func=lambda x: "⏳ بعد انتهاء المعدل الزمني المحدد" if x == "start_after_interval" else "⚡ النشر فوراً عند الحفظ", key="rc_uni_start_mode")

        with st.expander("⚙️ خيارات متقدمة إضافية (رابط الموقع، التصنيف، والتعليق التحفيزي)", expanded=False):
            rc_opt1, rc_opt2 = st.columns(2)
            with rc_opt1:
                n_blogger_url = st.text_input("🔗 رابط صفحة الرواية في المدونة (Blogger):", placeholder="https://novelskyworld.blogspot.com/p/...", key="rc_uni_burl")
            with rc_opt2:
                n_blogger_label = st.text_input("🏷️ تصنيف الرواية في بلوجر (Label):", placeholder="Shadow Slave", key="rc_uni_blbl")
            cta_default = "✨ استمتعتم بالفصل؟ لدعم استمرار الترجمة ومتابعة الفصول المتقدمة فور صدورها، تفضلوا بزيارة موقعنا الأصلي عبر الرابط في خانة الدعم/بطاقة الرواية ✨"
            custom_cta = st.text_area("💬 التعليق التحفيزي الثابت لنهاية كل فصل (التوجيه لخانة الدعم):", value=cta_default, height=70, key="rc_uni_cta")

        if st.button("🚀 حفظ الرواية وتفعيل النشر التلقائي", key="rc_uni_save_btn", type="primary", use_container_width=True):
            # إذا ضغط المستخدم حفظ مباشرة مع توفر الرابط السريع فقط دون ملء يدوي، نقوم بالاستنتاج التلقائي السريع فوراً
            target_name = n_name.strip()
            target_id = n_rewayat_id.strip()
            target_burl = n_blogger_url.strip()
            target_label = n_blogger_label.strip()
            target_last = int(n_last_ch)
            target_start = int(n_start_ch)
            target_stop = int(n_stop_ch)

            if not target_id and rc_quick_novel_url.strip():
                ins_res = syndication_extractor.inspect_novel_links(
                    platform="rewayat_club",
                    platform_url=rc_quick_novel_url.strip(),
                    blogger_url=rc_quick_blogger_url.strip() or target_burl
                )
                target_id = ins_res.get("clean_id", "")
                if not target_name:
                    target_name = ins_res.get("novel_name", "")
                if not target_burl:
                    target_burl = ins_res.get("blogger_url", "")
                if not target_label:
                    target_label = ins_res.get("blogger_label", "")
                if target_last == 0 and ins_res.get("last_chapter"):
                    target_last = int(ins_res["last_chapter"])
                    target_stop = int(ins_res["stop_chapter"])

            if not target_name:
                st.error("❌ يرجى إدخال اسم الرواية أو إدخال رابطها والضغط على 'فحص واستيراد البيانات تلقائياً'.")
            elif not target_id:
                st.error("❌ يرجى إدخال معرّف أو رابط الرواية في نادي الروايات.")
            elif target_start > target_stop:
                st.error("❌ رقم بداية الفصول يجب أن يكون أقل من أو يساوي رقم النهاية.")
            else:
                with st.spinner("⏳ جاري حفظ الرواية في المنظومة وGoogle Sheet..."):
                    clean_rc_id = target_id
                    if "novel/" in clean_rc_id:
                        clean_rc_id = clean_rc_id.split("novel/")[-1].split("/")[0].strip()

                    first_run_ts = time.time() if rc_start_now == "start_now" else (time.time() + float(rc_interval_val) * 3600.0)

                    syndication_db.save_or_update_syndicated_novel({
                        "novel_name": target_name,
                        "blogger_url": target_burl,
                        "blogger_label": target_label or target_name,
                        "rewayat_enabled": 1,
                        "rewayat_novel_id": clean_rc_id,
                        "rewayat_novel_url": rc_quick_novel_url.strip() if "rewayat.club" in rc_quick_novel_url else f"https://rewayat.club/novel/{clean_rc_id}",
                        "wattpad_enabled": 0,
                        "wattpad_story_id": "",
                        "wattpad_story_url": "",
                        "start_chapter": target_start,
                        "last_synced_chapter": target_last,
                        "stop_chapter": target_stop,
                        "interval_hours": float(rc_interval_val),
                        "next_run_timestamp": float(first_run_ts),
                        "custom_cta": custom_cta.strip(),
                        "is_active": 1
                    })

                    st.balloons()
                    st.success(f"🎉 تم بنجاح حفظ رواية '{target_name}' وتفعيل النشر التلقائي بمعدل فصل كل {rc_interval_val} ساعة!")
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

                # لوحة التحكم والإدارة الشاملة للرواية
                with st.expander(f"🎮 لوحة التحكم والإدارة الشاملة ({nov['novel_name']})", expanded=False):
                    st.markdown("##### ⚙️ إعدادات الرواية ومحرك النشر (تعديل مباشر وحفظ سحابي):")
                    st.caption("تعديل فوري لإعدادات هذه الرواية مع التثبيت السحابي في Google Sheet لمنع فقدان البيانات عند إعادة تشغيل السيرفر.")
                    c_cfg1, c_cfg2, c_cfg3 = st.columns([2, 2, 2])
                    with c_cfg1:
                        new_stop = st.number_input(
                            "🛑 التوقف عند الفصل (Stop Chapter):",
                            min_value=1,
                            value=int(nov.get("stop_chapter", 100)),
                            step=1,
                            key=f"rc_cfg_stop_{nov['id']}",
                            help="رقم الفصل الذي سيتوقف عنده المحرك نهائياً ولا ينشر بعده"
                        )
                    with c_cfg2:
                        new_interval = st.number_input(
                            "⏱️ معدل النشر (ساعات بين الفصول):",
                            min_value=0.5,
                            max_value=168.0,
                            value=float(nov.get("interval_hours", 12.0)),
                            step=0.5,
                            key=f"rc_cfg_interval_{nov['id']}",
                            help="الفارق الزمني بالساعات بين نشر كل فصل والفصل الذي يليه"
                        )
                    with c_cfg3:
                        new_active_val = st.selectbox(
                            "🚦 وضع النشر التلقائي:",
                            [1, 0],
                            index=0 if nov.get("is_active", 1) == 1 else 1,
                            format_func=lambda x: "🟢 نشط (يعمل تلقائياً)" if x == 1 else "🔴 متوقف مؤقتاً",
                            key=f"rc_cfg_active_{nov['id']}"
                        )
                    if st.button("💾 حفظ الإعدادات وتثبيتها سحابياً فوراً", key=f"rc_save_cfg_btn_{nov['id']}", type="primary", use_container_width=True):
                        nov["stop_chapter"] = int(new_stop)
                        nov["interval_hours"] = float(new_interval)
                        nov["is_active"] = int(new_active_val)
                        syndication_db.save_or_update_syndicated_novel(nov)
                        st.success("✅ تم حفظ الإعدادات بنجاح وتحديثها سحابياً في Google Sheet!")
                        st.rerun()

                    st.markdown("---")
                    st.markdown("##### 🚨 حذف الرواية بالكامل:")
                    col_del1, col_del2 = st.columns([2, 1])
                    with col_del1:
                        confirm_del = st.checkbox(f"أؤكد رغبتي بحذف '{nov['novel_name']}' نهائياً ومسح كافة فصولها من Google Sheet", key=f"rc_conf_del_{nov['id']}")
                    with col_del2:
                        if st.button("🗑️ حذف الرواية وفصولها نهائياً", key=f"rc_del_all_btn_{nov['id']}", type="secondary", use_container_width=True):
                            if confirm_del:
                                with st.spinner("⏳ جاري حذف الرواية ومسح كافة فصولها من Google Sheet..."):
                                    syndication_db.delete_syndicated_novel(nov["id"], delete_from_sheet=True)
                                    st.success(f"تم حذف الرواية '{nov['novel_name']}' نهائياً ومسح كافة فصولها من Google Sheet!")
                                    st.rerun()
                            else:
                                st.error("يرجى تفعيل مربع التأكيد أولاً لحذف الرواية.")
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
                all_novs = syndication_db.get_all_syndicated_novels()
                nov_cfg = next((n for n in all_novs if n["novel_name"] == preview_novel), None)
                custom_cta = nov_cfg["custom_cta"] if nov_cfg else ""
                blogger_url = nov_cfg["blogger_url"] if nov_cfg else ""
                
                with st.spinner(f"⏳ جاري سحب الفصل {preview_chapter} من جداول الترجمة..."):
                    res = syndication_extractor.prepare_chapter_for_publishing(
                        novel_name=preview_novel,
                        chapter_num=int(preview_chapter),
                        custom_cta=custom_cta,
                        blogger_url=blogger_url
                    )
                    st.session_state["rc_preview_data"] = res
                    st.session_state["rc_preview_meta"] = {
                        "novel": preview_novel,
                        "chapter": int(preview_chapter),
                        "nov_cfg": nov_cfg
                    }

            if "rc_preview_data" in st.session_state and st.session_state.get("rc_preview_meta", {}).get("novel") == preview_novel:
                result = st.session_state["rc_preview_data"]
                meta = st.session_state["rc_preview_meta"]
                p_chap = meta["chapter"]
                nov_cfg = meta["nov_cfg"]
                
                if result.get("success"):
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
                        elif not (nov_cfg and nov_cfg.get("rewayat_novel_id")):
                            st.error("❌ الرواية لا تحتوي على معرف (Novel ID) في نادي الروايات.")
                        else:
                            with st.spinner("⏳ جاري إرسال الفصل إلى منصة نادي الروايات..."):
                                client = rewayat_club_api.RewayatClubClient(token=user_token)
                                pub_res = client.publish_chapter(
                                    novel_id=nov_cfg["rewayat_novel_id"],
                                    chapter_num=int(p_chap),
                                    title=result["title"],
                                    content=result["content_for_publish"]
                                )
                                if pub_res.get("success"):
                                    st.balloons()
                                    st.success(f"🎉 {pub_res.get('message')}")
                                    # توثيق في السجل
                                    syndication_db.log_syndication_event(
                                        novel_id=nov_cfg["id"],
                                        chapter_num=int(p_chap),
                                        platform="rewayat_club",
                                        status="SUCCESS",
                                        post_url=pub_res.get("post_url", "")
                                    )
                                    # تحديث عداد آخر فصل تم نشره إذا كان هذا الفصل أحدث
                                    if int(p_chap) > nov_cfg.get("last_synced_chapter", 0):
                                        nov_cfg["last_synced_chapter"] = int(p_chap)
                                        syndication_db.save_or_update_syndicated_novel(nov_cfg)
                                    st.session_state.pop("rc_preview_data", None)
                                    st.rerun()
                                else:
                                    st.error(f"❌ {pub_res.get('error')}")
                                    syndication_db.log_syndication_event(
                                        novel_id=nov_cfg["id"],
                                        chapter_num=int(p_chap),
                                        platform="rewayat_club",
                                        status="FAILED",
                                        error_msg=pub_res.get("error", "")
                                    )
                else:
                    st.error(f"❌ {result.get('error', 'تعذر جلب الفصل')}")

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



def render_advanced_period_scheduler_section(default_platform="all"):
    st.markdown("---")
    st.subheader("📅 نظام الجدولة الدقيقة متعدد الفترات (Google Sheets Cloud Persistence)")
    st.caption("جدولة دفعات الفصول بنطاقات مخصصة وتحديد ساعات النشر يدوياً لكل فترة، مع المزامنة السحابية الدائمة 24/7 لحماية البيانات من انطفاء السيرفر.")

    # 1. شريط حالة الشيت والمزامنة السحابية
    with st.expander("☁️ إعدادات مستودع الجدولة السحابي (Google Sheet Cloud Settings)", expanded=False):
        cur_ssid = syndication_db.get_schedule_spreadsheet_id()
        c_ss1, c_ss2 = st.columns([3, 1])
        with c_ss1:
            inp_ssid = st.text_input("معرف جدول الجدولة في Google Sheet (Spreadsheet ID):", value=cur_ssid, key=f"ssid_inp_{default_platform}")
        with c_ss2:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if st.button("💾 حفظ المعرف", key=f"save_ssid_btn_{default_platform}", use_container_width=True):
                syndication_db.set_schedule_spreadsheet_id(inp_ssid.strip())
                st.success("تم تحديث وحفظ معرف الشيت!")
                st.rerun()

        st.caption(f"📌 اسم التبويب المعتمد تلقائياً في الشيت: `{syndication_db.SCHEDULE_TAB_NAME}`")
        if st.button("🔄 مزامنة فورية شاملة مع Google Sheet الآن", key=f"sync_sheet_btn_{default_platform}", use_container_width=True):
            with st.spinner("⏳ جاري قراءة ومزامنة الفصول من Google Sheet..."):
                sync_res = syndication_db.sync_schedule_from_sheet()
                if sync_res.get("success"):
                    st.success(f"🎉 تم مزامنة {sync_res.get('synced_count')} فصلاً بنجاح من الشيت السحابي!")
                else:
                    st.warning(f"⚠️ {sync_res.get('message')}")
                st.rerun()

    # 2. منشئ الفترات المخصصة والساعات اليدوية
    all_novels = syndication_db.get_all_syndicated_novels()
    if not all_novels:
        st.info("💡 أضف رواية واحدة على الأقل أولاً لتتمكن من إنشاء فترات الجدولة لها.")
        return

    novel_names = [n["novel_name"] for n in all_novels]

    with st.expander("🛠️ أداة جدولة دفعات إضافية مجمعة (نطاقات مخصصة - اختياري)", expanded=False):
        col_nov, col_plat = st.columns([2, 1])
        with col_nov:
            selected_novel = st.selectbox("📚 اختر الرواية:", novel_names, key=f"p_nov_sel_{default_platform}")
        with col_plat:
            plat_opts = ["all", "rewayat_club", "wattpad"]
            plat_labels = {"all": "كلاهما (نادي الروايات + واتباد)", "rewayat_club": "نادي الروايات فقط", "wattpad": "واتباد فقط"}
            def_idx = 0 if default_platform == "all" else (1 if default_platform == "rewayat_club" else 2)
            sel_plat = st.selectbox("🎯 المنصات المستهدفة:", plat_opts, index=def_idx, format_func=lambda x: plat_labels.get(x, x), key=f"p_plat_sel_{default_platform}")

        col_r1, col_r2, col_r3 = st.columns(3)
        with col_r1:
            p_start_ch = st.number_input("من الفصل:", min_value=1, value=1, step=1, key=f"p_start_ch_{default_platform}")
        with col_r2:
            p_end_ch = st.number_input("إلى الفصل:", min_value=int(p_start_ch), value=max(int(p_start_ch), 10), step=1, key=f"p_end_ch_{default_platform}")
        with col_r3:
            p_freq_type = st.selectbox(
                "🔁 وتيرة التكرار:",
                ["daily", "weekly", "monthly", "once"],
                format_func=lambda x: {
                    "daily": "يومي (ساعات محددة يدوياً)",
                    "weekly": "أسبوعي (مرة كل أسبوع)",
                    "monthly": "شهري (مرة كل شهر)",
                    "once": "مرة واحدة (فصل محدد)"
                }.get(x, x),
                key=f"p_freq_type_{default_platform}"
            )

        col_d1, col_d2 = st.columns([1, 2])
        with col_d1:
            p_start_date = st.date_input("📅 تاريخ بدء الفترة:", value=datetime.date.today(), key=f"p_start_d_{default_platform}")

        selected_hours = []
        if p_freq_type == "daily":
            with col_d2:
                p_times_count = st.number_input("🔢 كم مرة في اليوم؟", min_value=1, max_value=12, value=3, step=1, key=f"p_times_cnt_{default_platform}")

            st.markdown(f"**⏰ حدد ساعات النشر اليدوية ({p_times_count} أوقات يومياً بتوقيت مكة والعراق):**")
            cols_hours = st.columns(min(int(p_times_count), 4))
            def_hours = ["10:00", "14:00", "18:00", "21:30", "23:00", "01:00", "08:00", "12:00"]
            for i in range(int(p_times_count)):
                c_idx = i % len(cols_hours)
                with cols_hours[c_idx]:
                    def_t_str = def_hours[i] if i < len(def_hours) else "12:00"
                    dh_parts = def_t_str.split(":")
                    def_time_val = datetime.time(int(dh_parts[0]), int(dh_parts[1]))
                    t_val = st.time_input(f"الموعد {i+1}:", value=def_time_val, key=f"p_time_inp_{default_platform}_{i}")
                    selected_hours.append(t_val.strftime("%H:%M"))

        elif p_freq_type == "weekly":
            with col_d2:
                w_time = st.time_input("⏰ وقت النشر الأسبوعي:", value=datetime.time(20, 0), key=f"w_time_inp_{default_platform}")
                selected_hours.append(w_time.strftime("%H:%M"))

        elif p_freq_type == "monthly":
            with col_d2:
                m_time = st.time_input("⏰ وقت النشر الشهري:", value=datetime.time(20, 0), key=f"m_time_inp_{default_platform}")
                selected_hours.append(m_time.strftime("%H:%M"))

        elif p_freq_type == "once":
            with col_d2:
                o_time = st.time_input("⏰ وقت النشر:", value=datetime.datetime.now().time().replace(second=0, microsecond=0), key=f"o_time_inp_{default_platform}")
                selected_hours.append(o_time.strftime("%H:%M"))

        if st.button("⚡ توليد وتثبيت جدول الفصول في Google Sheet", key=f"btn_gen_sched_{default_platform}", type="primary", use_container_width=True):
            if int(p_start_ch) > int(p_end_ch):
                st.error("رقم بداية النطاق يجب أن يكون أقل من أو يساوي رقم النهاية.")
            else:
                with st.spinner("⏳ جاري حساب التواريخ وضخ الفصول في Google Sheet وقاعدة البيانات..."):
                    gen_rows = syndication_db.generate_schedule_from_period_rules(
                        novel_name=selected_novel,
                        start_ch=int(p_start_ch),
                        end_ch=int(p_end_ch),
                        freq_type=p_freq_type,
                        times_per_day=len(selected_hours),
                        selected_hours=selected_hours,
                        start_date_str=p_start_date.strftime("%Y-%m-%d"),
                        platform=sel_plat
                    )
                    syndication_db.save_chapter_schedules_batch(selected_novel, gen_rows)
                    syndication_db.save_period_rule({
                        "novel_name": selected_novel,
                        "start_chapter": int(p_start_ch),
                        "end_chapter": int(p_end_ch),
                        "frequency_type": p_freq_type,
                        "times_per_day": len(selected_hours),
                        "selected_hours": json.dumps(selected_hours),
                        "start_date": p_start_date.strftime("%Y-%m-%d"),
                        "is_active": 1
                    })
                    nov_obj = next((n for n in all_novels if n["novel_name"] == selected_novel), None)
                    if nov_obj:
                        nov_obj["is_active"] = 1
                        syndication_db.save_or_update_syndicated_novel(nov_obj)

                    st.balloons()
                    st.success(f"🎉 تم بنجاح توليد وجدولة {len(gen_rows)} فصلاً لرواية '{selected_novel}' وحفظها في Google Sheet!")
                    st.rerun()

    # 3. جدول مواعيد الفصول التفاعلي
    st.markdown("### 📋 جدول الفصول المجدولة في Google Sheet")
    st.caption("يعرض جميع الفصول المحسوبة والمثبتة سحابياً في Google Sheet. ينفذ السيرفر النشر تلقائياً فور حلول وقت كل فصل.")
    c_f1, c_f2 = st.columns([2, 1])
    with c_f1:
        tbl_novel = st.selectbox("🔍 تصفية حسب الرواية:", ["الكل"] + novel_names, key=f"tbl_nov_sel_{default_platform}")
    with c_f2:
        tbl_stat = st.selectbox("🔍 تصفية حسب الحالة:", ["الكل", "PENDING", "PUBLISHED", "FAILED"], format_func=lambda x: {"الكل": "الكل", "PENDING": "⏳ قيد الانتظار", "PUBLISHED": "🟢 تم النشر", "FAILED": "🔴 تعذر النشر"}.get(x, x), key=f"tbl_stat_sel_{default_platform}")

    filter_nov = None if tbl_novel == "الكل" else tbl_novel
    filter_st = None if tbl_stat == "الكل" else tbl_stat
    sched_items = syndication_db.get_scheduled_chapters(novel_name=filter_nov, status=filter_st, limit=100)

    if not sched_items:
        st.info("لا توجد فصول مجدولة مطابقة للشروط الحالية.")
    else:
        st.caption(f"تم العثور على {len(sched_items)} فصلاً مجدولاً.")
        for item in sched_items:
            with st.container():
                ci1, ci2, ci3, ci4 = st.columns([1.5, 2.5, 1.5, 1.5])
                with ci1:
                    st.markdown(f"**📖 {item['novel_name']}**")
                    st.caption(f"الفصل: **{item['chapter_num']}** | نطاق: `{item.get('period_range') or '-'}`")
                with ci2:
                    st.markdown(f"⏰ **الموعد:** `{item['scheduled_time']}`")
                    if item.get("post_url"):
                        st.caption(f"🔗 [رابط النشر]({item['post_url']})")
                    if item.get("last_error"):
                        st.caption(f"⚠️ `{item['last_error'][:60]}`")
                with ci3:
                    st_val = item.get("status", "PENDING")
                    if st_val == "PUBLISHED":
                        st.markdown("🟢 **تم النشر بنجاح**")
                        st.caption(f"نشر في: {item.get('published_at','')}")
                    elif st_val == "PENDING":
                        st.markdown("⏳ **مجدول بانتظار موعده**")
                        st.caption(f"المنصة: `{item.get('platform','all')}`")
                    else:
                        st.markdown("🔴 **تعذر النشر**")
                with ci4:
                    if st_val == "PENDING":
                        if st.button("⚡ نشر الآن", key=f"pub_now_btn_{item['novel_name']}_{item['chapter_num']}_{default_platform}"):
                            item["scheduled_timestamp"] = time.time() - 10
                            syndication_db.save_chapter_schedules_batch(item["novel_name"], [item])
                            try:
                                import syndication_daemon
                                syndication_daemon.run_syndication_cycle()
                                st.success("تم إطلاق النشر فوراً!")
                                st.rerun()
                            except Exception as ex_p:
                                st.error(f"خطأ: {ex_p}")
                    if st.button("🗑️ إلغاء", key=f"del_ch_btn_{item['novel_name']}_{item['chapter_num']}_{default_platform}"):
                        syndication_db.delete_chapter_schedule(item["novel_name"], item["chapter_num"])
                        st.success(f"تم إلغاء جدولة الفصل {item['chapter_num']}")
                        st.rerun()
                st.markdown("<hr style='margin:4px 0; border:0; border-top:1px solid #334155;'>", unsafe_allow_html=True)

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
        st.markdown('<div style="background-color:#064e3b; border:1px solid #059669; border-radius:8px; padding:7px 14px; margin-bottom:12px; color:#6ee7b7; font-size:0.90rem; font-weight:bold;">🟢 <b>المجدول الذاتي وسحابة Google Sheet:</b> متصل بالجدول السحابي ونشط 24/7 — الفصول والمواعيد محفوظة سحابياً ضد انقطاع السيرفر.</div>', unsafe_allow_html=True)
    with col_stat2:
        if st.button("🔄 مزامنة وفحص الآن", key="wp_trigger_now", use_container_width=True):
            try:
                import syndication_daemon
                syndication_db.sync_novels_from_sheet()
                syndication_db.sync_schedule_from_sheet()
                syndication_daemon.run_syndication_cycle()
                st.success("تمت استعادة إعدادات الروايات والفصول من Google Sheet وتشغيل دورة الفحص!")
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

    # 2. إضافة قصة جديدة لواتباد وجدولة فصولها في Google Sheet (بالروابط فقط أو بالتخصيص الكامل)
    with st.expander("➕ إضافة قصة جديدة وجدولة فصولها في Google Sheet", expanded=True):
        st.markdown("##### 🔗 1️⃣ الإضافة السريعة بالروابط (رابط قصة واتباد + رابط الموقع):")
        st.caption("أدخل رابط القصة في واتباد ورابطها في موقعك ليقوم السيرفر باستنتاج معرّف القصة واسم الرواية وتصنيف بلوجر وعدد الأجزاء المنشورة تلقائياً!")

        col_wurl1, col_wurl2 = st.columns(2)
        with col_wurl1:
            wp_quick_story_url = st.text_input(
                "🆔 رابط قصة واتباد أو المعرّف:",
                placeholder="https://www.wattpad.com/story/365123456-shadow-slave أو رقم القصة فقط",
                key="wp_quick_story_url"
            )
        with col_wurl2:
            wp_quick_blogger_url = st.text_input(
                "🌐 رابط صفحة الرواية في الموقع (المدونة / Novelskyworld):",
                placeholder="https://www.novelskyworld.com/p/... أو رابط بلوجر",
                key="wp_quick_blogger_url"
            )

        col_wbtn_auto, col_wbtn_direct = st.columns([2, 2])
        with col_wbtn_auto:
            if st.button("🔍 فحص واستيراد بيانات القصة تلقائياً", key="wp_auto_fill_btn", use_container_width=True):
                if not wp_quick_story_url.strip() and not wp_quick_blogger_url.strip():
                    st.error("❌ يرجى إدخال رابط قصة واتباد أو رابط الموقع أولاً.")
                else:
                    with st.spinner("⏳ جاري فحص الروابط واستخراج بيانات قصة واتباد تلقائياً..."):
                        ins_wp = syndication_extractor.inspect_novel_links(
                            platform="wattpad",
                            platform_url=wp_quick_story_url.strip(),
                            blogger_url=wp_quick_blogger_url.strip()
                        )
                        if ins_wp.get("novel_name"):
                            st.session_state["wp_uni_name"] = ins_wp["novel_name"]
                        if ins_wp.get("clean_id"):
                            st.session_state["wp_uni_id"] = ins_wp["clean_id"]
                        if ins_wp.get("blogger_url"):
                            st.session_state["wp_uni_burl"] = ins_wp["blogger_url"]
                        if ins_wp.get("blogger_label"):
                            st.session_state["wp_uni_blbl"] = ins_wp["blogger_label"]
                        if "last_chapter" in ins_wp:
                            st.session_state["wp_uni_last"] = int(ins_wp["last_chapter"])
                            st.session_state["wp_uni_start"] = 1
                            st.session_state["wp_uni_stop"] = int(ins_wp["stop_chapter"])
                        st.success(f"✅ تم بنجاح جلب بيانات قصة '{ins_wp.get('novel_name')}'! آخر جزء منشور: {ins_wp.get('last_chapter')}")
                        st.rerun()

        st.markdown("---")
        st.markdown("##### ⚙️ 2️⃣ خيارات التخصيص والجدولة (يمكنك تعديل أي حقل بحرية):")
        wp_c1, wp_c2 = st.columns(2)
        with wp_c1:
            w_name = st.text_input("🏷️ اسم الرواية (مطلوب):", placeholder="مثال: Shadow Slave", key="wp_uni_name")
            w_story_id = st.text_input("🆔 معرّف القصة أو رابطها في واتباد (مطلوب):", placeholder="مثال: 987654321 أو رابط القصة", key="wp_uni_id")
        with wp_c2:
            wp_ch1, wp_ch2, wp_ch3 = st.columns(3)
            with wp_ch1:
                w_start_ch = st.number_input("من الفصل:", min_value=1, value=1, step=1, key="wp_uni_start")
            with wp_ch2:
                w_stop_ch = st.number_input("إلى الفصل:", min_value=1, value=20, step=1, key="wp_uni_stop")
            with wp_ch3:
                w_last_ch = st.number_input("آخر فصل نُشر مسبقاً:", min_value=0, value=0, step=1, help="اتركه 0 إذا كانت رواية جديدة تماماً", key="wp_uni_last")

        st.markdown("##### 3️⃣ معدل النشر التلقائي وموعد الانطلاق:")
        wp_c_rate1, wp_c_rate2 = st.columns(2)
        with wp_c_rate1:
            wp_interval_val = st.number_input("⏱️ معدل النشر (ساعات بين كل فصل):", min_value=0.25, max_value=168.0, value=24.0, step=0.5, help="مثال: 24 = فصل كل يوم، 12 = فصلين يومياً، 1 = فصل كل ساعة", key="wp_uni_int")
        with wp_c_rate2:
            wp_start_now = st.radio("⏰ موعد انطلاق أول فصل:", ["start_after_interval", "start_now"], format_func=lambda x: "⏳ بعد انتهاء المعدل الزمني المحدد" if x == "start_after_interval" else "⚡ النشر فوراً عند الحفظ", key="wp_uni_start_mode")

        with st.expander("⚙️ خيارات متقدمة إضافية (رابط الموقع، التصنيف، والتعليق التحفيزي للبايو)", expanded=False):
            wp_opt1, wp_opt2 = st.columns(2)
            with wp_opt1:
                w_blogger_url = st.text_input("🔗 رابط صفحة الرواية في المدونة (Blogger):", placeholder="https://novelskyworld.blogspot.com/p/...", key="wp_uni_burl")
            with wp_opt2:
                w_blogger_label = st.text_input("🏷️ تصنيف الرواية في بلوجر (Label):", placeholder="Shadow Slave", key="wp_uni_blbl")
            w_cta_default = "✨ استمتعتم بالفصل؟ لمتابعة أحدث الفصول الحصرية والمتقدمة فور صدورها، تفضلوا بزيارة موقعنا الأصلي عبر الرابط في بايو الحساب (Bio) 🔗 ✨"
            w_custom_cta = st.text_area("💬 التعليق التحفيزي لنهاية كل فصل في واتباد (التوجيه للبايو):", value=w_cta_default, height=70, key="wp_uni_cta")

        if st.button("🚀 حفظ الرواية وتفعيل النشر التلقائي لواتباد", key="wp_uni_save_btn", type="primary", use_container_width=True):
            target_wname = w_name.strip()
            target_wid = w_story_id.strip()
            target_wburl = w_blogger_url.strip()
            target_wlabel = w_blogger_label.strip()
            target_wlast = int(w_last_ch)
            target_wstart = int(w_start_ch)
            target_wstop = int(w_stop_ch)

            # إذا توفر رابط واتباد السريع دون ملء يدوي، نقوم بالفحص والاستنتاج التلقائي مباشرة
            if not target_wid and wp_quick_story_url.strip():
                ins_wp = syndication_extractor.inspect_novel_links(
                    platform="wattpad",
                    platform_url=wp_quick_story_url.strip(),
                    blogger_url=wp_quick_blogger_url.strip() or target_wburl
                )
                target_wid = ins_wp.get("clean_id", "")
                if not target_wname:
                    target_wname = ins_wp.get("novel_name", "")
                if not target_wburl:
                    target_wburl = ins_wp.get("blogger_url", "")
                if not target_wlabel:
                    target_wlabel = ins_wp.get("blogger_label", "")
                if target_wlast == 0 and ins_wp.get("last_chapter"):
                    target_wlast = int(ins_wp["last_chapter"])
                    target_wstop = int(ins_wp["stop_chapter"])

            if not target_wname:
                st.error("❌ يرجى إدخال اسم الرواية أو إدخال رابط قصة واتباد والضغط على 'فحص واستيراد بيانات القصة تلقائياً'.")
            elif not target_wid:
                st.error("❌ يرجى إدخال معرّف قصة واتباد أو رابطها.")
            elif target_wstart > target_wstop:
                st.error("❌ رقم بداية الفصول يجب أن يكون أقل من أو يساوي رقم النهاية.")
            else:
                with st.spinner("⏳ جاري حفظ قصة واتباد في المنظومة وGoogle Sheet..."):
                    clean_story_id = target_wid
                    if "story/" in clean_story_id:
                        clean_story_id = clean_story_id.split("story/")[-1].split("-")[0].split("/")[0].strip()

                    first_run_ts = time.time() if wp_start_now == "start_now" else (time.time() + float(wp_interval_val) * 3600.0)

                    syndication_db.save_or_update_syndicated_novel({
                        "novel_name": target_wname,
                        "blogger_url": target_wburl,
                        "blogger_label": target_wlabel or target_wname,
                        "rewayat_enabled": 0,
                        "rewayat_novel_id": "",
                        "rewayat_novel_url": "",
                        "wattpad_enabled": 1,
                        "wattpad_story_id": clean_story_id,
                        "wattpad_story_url": wp_quick_story_url.strip() if "wattpad.com" in wp_quick_story_url else f"https://www.wattpad.com/story/{clean_story_id}",
                        "start_chapter": target_wstart,
                        "last_synced_chapter": target_wlast,
                        "stop_chapter": target_wstop,
                        "interval_hours": float(wp_interval_val),
                        "next_run_timestamp": float(first_run_ts),
                        "custom_cta": w_custom_cta.strip(),
                        "is_active": 1
                    })

                    st.balloons()
                    st.success(f"🎉 تم بنجاح حفظ قصة '{target_wname}' وتفعيل النشر التلقائي بمعدل فصل كل {wp_interval_val} ساعة!")
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

                # لوحة التحكم والإدارة الشاملة لقصة واتباد
                with st.expander(f"🎮 لوحة التحكم والإدارة الشاملة ({nov['novel_name']})", expanded=False):
                    st.markdown("##### ⚙️ إعدادات قصة واتباد ومحرك النشر (تعديل مباشر وحفظ سحابي):")
                    st.caption("تعديل فوري لإعدادات هذه القصة مع التثبيت السحابي في Google Sheet لمنع فقدان البيانات عند إعادة تشغيل السيرفر.")
                    c_wcfg1, c_wcfg2, c_wcfg3 = st.columns([2, 2, 2])
                    with c_wcfg1:
                        wnew_stop = st.number_input(
                            "🛑 التوقف عند الفصل (Stop Chapter):",
                            min_value=1,
                            value=int(nov.get("stop_chapter", 50)),
                            step=1,
                            key=f"wp_cfg_stop_{nov['id']}",
                            help="رقم الفصل الذي سيتوقف عنده المحرك نهائياً ولا ينشر بعده"
                        )
                    with c_wcfg2:
                        wnew_interval = st.number_input(
                            "⏱️ معدل النشر (ساعات بين الفصول):",
                            min_value=0.5,
                            max_value=168.0,
                            value=float(nov.get("interval_hours", 12.0)),
                            step=0.5,
                            key=f"wp_cfg_interval_{nov['id']}",
                            help="الفارق الزمني بالساعات بين نشر كل فصل والفصل الذي يليه"
                        )
                    with c_wcfg3:
                        wnew_active_val = st.selectbox(
                            "🚦 وضع النشر التلقائي:",
                            [1, 0],
                            index=0 if nov.get("is_active", 1) == 1 else 1,
                            format_func=lambda x: "🟢 نشط (يعمل تلقائياً)" if x == 1 else "🔴 متوقف مؤقتاً",
                            key=f"wp_cfg_active_{nov['id']}"
                        )
                    if st.button("💾 حفظ الإعدادات وتثبيتها سحابياً فوراً", key=f"wp_save_cfg_btn_{nov['id']}", type="primary", use_container_width=True):
                        nov["stop_chapter"] = int(wnew_stop)
                        nov["interval_hours"] = float(wnew_interval)
                        nov["is_active"] = int(wnew_active_val)
                        syndication_db.save_or_update_syndicated_novel(nov)
                        st.success("✅ تم حفظ الإعدادات بنجاح وتحديثها سحابياً في Google Sheet!")
                        st.rerun()

                    st.markdown("---")
                    st.markdown("##### 🚨 حذف الرواية بالكامل:")
                    col_wdel1, col_wdel2 = st.columns([2, 1])
                    with col_wdel1:
                        wconfirm_del = st.checkbox(f"أؤكد رغبتي بحذف '{nov['novel_name']}' نهائياً ومسح كافة فصولها من Google Sheet", key=f"wp_conf_del_{nov['id']}")
                    with col_wdel2:
                        if st.button("🗑️ حذف الرواية وفصولها نهائياً", key=f"wp_del_all_btn_{nov['id']}", type="secondary", use_container_width=True):
                            if wconfirm_del:
                                with st.spinner("⏳ جاري حذف الرواية ومسح كافة فصولها من Google Sheet..."):
                                    syndication_db.delete_syndicated_novel(nov["id"], delete_from_sheet=True)
                                    st.success(f"تم حذف الرواية '{nov['novel_name']}' نهائياً ومسح كافة فصولها من Google Sheet!")
                                    st.rerun()
                            else:
                                st.error("يرجى تفعيل مربع التأكيد أولاً لحذف الرواية.")
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
                    res = syndication_extractor.prepare_chapter_for_publishing(
                        novel_name=wp_preview_novel,
                        chapter_num=int(wp_preview_chapter),
                        custom_cta=custom_cta,
                        blogger_url=blogger_url
                    )
                    st.session_state["wp_preview_data"] = res
                    st.session_state["wp_preview_meta"] = {
                        "novel": wp_preview_novel,
                        "chapter": int(wp_preview_chapter),
                        "nov_cfg": nov_cfg
                    }

            if "wp_preview_data" in st.session_state and st.session_state.get("wp_preview_meta", {}).get("novel") == wp_preview_novel:
                result = st.session_state["wp_preview_data"]
                meta = st.session_state["wp_preview_meta"]
                wp_chap = meta["chapter"]
                nov_cfg = meta["nov_cfg"]

                if result.get("success"):
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
                        elif not (nov_cfg and nov_cfg.get("wattpad_story_id")):
                            st.error("❌ الرواية لا تحتوي على معرف قصة (Story ID) في واتباد.")
                        else:
                            with st.spinner("⏳ جاري إرسال الفصل كجزء جديد إلى قصة واتباد..."):
                                w_client = wattpad_poster.WattpadClient(token=w_user_token)
                                w_pub_res = w_client.publish_chapter_to_story(
                                    story_id=nov_cfg["wattpad_story_id"],
                                    chapter_num=int(wp_chap),
                                    title=result["title"],
                                    content=result["content_for_publish"]
                                )
                                if w_pub_res.get("success"):
                                    st.balloons()
                                    st.success(f"🎉 {w_pub_res.get('message')}")
                                    syndication_db.log_syndication_event(
                                        novel_id=nov_cfg["id"],
                                        chapter_num=int(wp_chap),
                                        platform="wattpad",
                                        status="SUCCESS",
                                        post_url=w_pub_res.get("post_url", "")
                                    )
                                    if int(wp_chap) > nov_cfg.get("last_synced_chapter", 0):
                                        nov_cfg["last_synced_chapter"] = int(wp_chap)
                                        syndication_db.save_or_update_syndicated_novel(nov_cfg)
                                    st.session_state.pop("wp_preview_data", None)
                                    st.rerun()
                                else:
                                    st.error(f"❌ {w_pub_res.get('error')}")
                                    syndication_db.log_syndication_event(
                                        novel_id=nov_cfg["id"],
                                        chapter_num=int(wp_chap),
                                        platform="wattpad",
                                        status="FAILED",
                                        error_msg=w_pub_res.get("error", "")
                                    )
                else:
                    st.error(f"❌ {result.get('error', 'تعذر جلب الفصل')}")

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


