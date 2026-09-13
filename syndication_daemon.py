# -*- coding: utf-8 -*-
"""
syndication_daemon.py — المشغل الذاتي المجدول 24/7 (Autonomous Daemon)
المرحلة الرابعة: يعمل كخدمة خلفية على مدار الساعة:
- يمر بانتظام على كل الروايات المسجلة في syndicated_novels
- يفحص معدل النشر بالساعات (interval_hours) وموعد الفصل القادم
- يقوم بسحب الفصل وتجهيزه ونشره تلقائياً إلى نادي الروايات وواتباد
- يوثق كل حدث في السجل ويحدث العدادات دون أي تكرار
"""

import time
import threading
import logging
import syndication_db
import syndication_extractor
import rewayat_club_api
import wattpad_poster

logger = logging.getLogger("SyndicationDaemon")

_DAEMON_RUNNING = False
_DAEMON_THREAD = None

def process_scheduled_chapters_cycle(now: float):
    """
    فحص ونشر الفصول التي حان موعدها من جدول الجدولة المتقدمة في Google Sheet وقاعدة البيانات.
    """
    try:
        due_chapters = syndication_db.get_scheduled_chapters(status="PENDING", limit=20)
    except Exception as ex_db:
        logger.warning(f"Could not load scheduled chapters: {ex_db}")
        return

    if not due_chapters:
        return

    rc_token = syndication_db.get_synd_setting("rewayat_token", "")
    wp_token = syndication_db.get_synd_setting("wattpad_token", "")
    wp_user = syndication_db.get_synd_setting("wattpad_username", "")
    wp_pass = syndication_db.get_synd_setting("wattpad_password", "")

    for item in due_chapters:
        try:
            sch_ts = float(item.get("scheduled_timestamp") or 0.0)
            if sch_ts <= 0 or sch_ts > now:
                continue

            n_name = item["novel_name"]
            target_ch = item["chapter_num"]
            plat_target = item.get("platform", "all")

            all_novs = syndication_db.get_all_syndicated_novels()
            nov = next((n for n in all_novs if n["novel_name"] == n_name), None)
            if not nov:
                continue

            extracted = syndication_extractor.prepare_chapter_for_publishing(
                novel_name=n_name,
                chapter_num=target_ch,
                custom_cta=nov.get("custom_cta", ""),
                blogger_url=nov.get("blogger_url", "")
            )

            if not extracted.get("success"):
                logger.info(f"Scheduled Chapter {target_ch} for {n_name} not available in sheet yet.")
                continue

            success_rc = False
            success_wp = False
            rc_post_url = ""
            wp_post_url = ""
            err_messages = []

            # 1. نادي الروايات
            if plat_target in ("all", "rewayat_club") and nov.get("rewayat_enabled") and nov.get("rewayat_novel_id") and rc_token:
                try:
                    rc_client = rewayat_club_api.RewayatClubClient(token=rc_token)
                    rc_res = rc_client.publish_chapter(
                        novel_id=nov["rewayat_novel_id"],
                        chapter_num=target_ch,
                        title=extracted["title"],
                        content=extracted["content_for_publish"]
                    )
                    if rc_res.get("success"):
                        success_rc = True
                        rc_post_url = rc_res.get("post_url", "")
                        syndication_db.log_syndication_event(
                            novel_id=nov["id"], chapter_num=target_ch, platform="rewayat_club",
                            status="SUCCESS", post_url=rc_post_url
                        )
                    else:
                        err_msg = rc_res.get("error", "فشل نادي الروايات")
                        err_messages.append(err_msg)
                        syndication_db.log_syndication_event(
                            novel_id=nov["id"], chapter_num=target_ch, platform="rewayat_club",
                            status="FAILED", error_msg=err_msg
                        )
                except Exception as e_rc:
                    err_messages.append(str(e_rc))

            # 2. واتباد
            if plat_target in ("all", "wattpad") and nov.get("wattpad_enabled") and nov.get("wattpad_story_id"):
                if wp_token or (wp_user and wp_pass):
                    try:
                        wp_client = wattpad_poster.WattpadClient(token=wp_token, username=wp_user, password=wp_pass)
                        wp_res = wp_client.publish_chapter_to_story(
                            story_id=nov["wattpad_story_id"],
                            chapter_num=target_ch,
                            title=extracted["title"],
                            content=extracted["content_for_publish"]
                        )
                        if wp_res.get("success"):
                            success_wp = True
                            wp_post_url = wp_res.get("post_url", "")
                            syndication_db.log_syndication_event(
                                novel_id=nov["id"], chapter_num=target_ch, platform="wattpad",
                                status="SUCCESS", post_url=wp_post_url
                            )
                        else:
                            err_msg = wp_res.get("error", "فشل واتباد")
                            err_messages.append(err_msg)
                            syndication_db.log_syndication_event(
                                novel_id=nov["id"], chapter_num=target_ch, platform="wattpad",
                                status="FAILED", error_msg=err_msg
                            )
                    except Exception as e_wp:
                        err_messages.append(str(e_wp))

            if success_rc or success_wp:
                combined_url = " | ".join(filter(None, [rc_post_url, wp_post_url]))
                syndication_db.update_chapter_schedule_status(
                    novel_name=n_name,
                    chapter_num=target_ch,
                    status="PUBLISHED",
                    post_url=combined_url
                )
                if target_ch > (nov.get("last_synced_chapter") or 0):
                    nov["last_synced_chapter"] = target_ch
                    syndication_db.save_or_update_syndicated_novel(nov)

                logger.info(f"🚀 Published scheduled chapter {target_ch} for {n_name} successfully!")

                try:
                    from nsw_healer_engine import notify_admin
                    pub_links = []
                    if success_rc:
                        pub_links.append(f"• نادي الروايات: {rc_post_url or 'تم'}")
                    if success_wp:
                        pub_links.append(f"• واتباد: {wp_post_url or 'تم'}")
                    links_txt = "\n".join(pub_links)
                    msg = (
                        f"🚀 <b>[نشر مجدول بساعات محددة — ناجح]</b>\n\n"
                        f"📖 <b>الرواية:</b> {n_name}\n"
                        f"📑 <b>الفصل:</b> {target_ch}\n"
                        f"🏷️ <b>العنوان:</b> {extracted.get('title', '')}\n"
                        f"{links_txt}\n\n"
                        f"📊 <b>المصدر السحابي:</b> Google Sheet (SyndicationSchedule)"
                    )
                    notify_admin(msg)
                except Exception as ex_notif:
                    logger.warning(f"Could not send telegram notification: {ex_notif}")
            else:
                joined_err = " ; ".join(err_messages) or "تعذر النشر"
                syndication_db.update_chapter_schedule_status(
                    novel_name=n_name,
                    chapter_num=target_ch,
                    status="FAILED",
                    error_msg=joined_err
                )
        except Exception as ex_item:
            logger.error(f"Error in process_scheduled_chapters_cycle for item {item}: {ex_item}")

def run_syndication_cycle():
    """تنفيذ دورة فحص واحدة لكافة الروايات النشطة في النظام."""
    now = time.time()

    # أولاً: معالجة ونشر الفصول المجدولة بساعات محددة يدوياً من جدول Google Sheet
    try:
        process_scheduled_chapters_cycle(now)
    except Exception as ex_p:
        logger.error(f"Error in process_scheduled_chapters_cycle: {ex_p}")

    # ثانياً: معالجة الروايات بنظام الفترات الساعية الافتراضية (Legacy Interval Runner)
    novels = syndication_db.get_all_syndicated_novels(active_only=True)
    if not novels:
        return

    # جلب التوكنات العامة
    rc_token = syndication_db.get_synd_setting("rewayat_token", "")
    wp_token = syndication_db.get_synd_setting("wattpad_token", "")
    wp_user = syndication_db.get_synd_setting("wattpad_username", "")
    wp_pass = syndication_db.get_synd_setting("wattpad_password", "")

    for nov in novels:
        try:
            # إذا كانت الرواية تحتوي على فصول مجدولة معلقة بالجدول، نترك إدارتها لنظام الفصول لتفادي التكرار
            try:
                has_active_sched = syndication_db.get_scheduled_chapters(novel_name=nov["novel_name"], status="PENDING", limit=1)
                if has_active_sched:
                    continue
            except Exception:
                pass

            # 1. التحقق هل حان موعد النشر؟
            next_run = nov.get("next_run_timestamp", 0.0)
            # قاعدة صارمة: إذا لم يتم تحديد موعد جدولة صريح (> 0) أو لم يحن وقته بعد، نمنع النشر نهائياً
            if not next_run or next_run <= 0.0 or now < next_run:
                continue

            # مزامنة العداد تلقائياً مع الواقع الفعلي في نادي الروايات لتفادي التكرار
            if nov.get("rewayat_enabled") and nov.get("rewayat_novel_id") and rc_token:
                try:
                    rc_temp = rewayat_club_api.RewayatClubClient(token=rc_token)
                    live_num = rc_temp.get_latest_chapter_number(nov["rewayat_novel_id"])
                    if live_num and live_num > nov.get("last_synced_chapter", 0):
                        logger.info(f"Auto-synced last_synced_chapter for {nov['novel_name']}: {nov.get('last_synced_chapter')} -> {live_num}")
                        nov["last_synced_chapter"] = live_num
                        syndication_db.save_or_update_syndicated_novel(nov)
                except Exception as e_sync:
                    logger.warning(f"Could not auto-sync chapter count: {e_sync}")

            last_ch = nov.get("last_synced_chapter", 0)
            stop_ch = nov.get("stop_chapter", 9999)
            target_ch = last_ch + 1

            if target_ch > stop_ch:
                continue  # تم بلوغ آخر فصل محدد

            # 2. استخراج وتجهيز الفصل
            extracted = syndication_extractor.prepare_chapter_for_publishing(
                novel_name=nov["novel_name"],
                chapter_num=target_ch,
                custom_cta=nov.get("custom_cta", ""),
                blogger_url=nov.get("blogger_url", "")
            )

            if not extracted.get("success"):
                # تأجيل الفحص 30 دقيقة بدلاً من إرهاق السيرفر والشيت كل 60 ثانية إذا لم يتوفر الفصل بعد
                logger.info(f"Chapter {target_ch} for {nov['novel_name']} not available yet in sheet. Retrying in 30 min.")
                nov["next_run_timestamp"] = time.time() + 1800
                syndication_db.save_or_update_syndicated_novel(nov)
                continue

            success_rc = False
            success_wp = False

            # 3. النشر في نادي الروايات (إذا كان مفعلاً)
            if nov.get("rewayat_enabled") and nov.get("rewayat_novel_id") and rc_token:
                try:
                    rc_client = rewayat_club_api.RewayatClubClient(token=rc_token)
                    rc_res = rc_client.publish_chapter(
                        novel_id=nov["rewayat_novel_id"],
                        chapter_num=target_ch,
                        title=extracted["title"],
                        content=extracted["content_for_publish"]
                    )
                    if rc_res.get("success"):
                        success_rc = True
                        syndication_db.log_syndication_event(
                            novel_id=nov["id"],
                            chapter_num=target_ch,
                            platform="rewayat_club",
                            status="SUCCESS",
                            post_url=rc_res.get("post_url", "")
                        )
                    else:
                        syndication_db.log_syndication_event(
                            novel_id=nov["id"],
                            chapter_num=target_ch,
                            platform="rewayat_club",
                            status="FAILED",
                            error_msg=rc_res.get("error", "")
                        )
                except Exception as e:
                    logger.error(f"Error publishing RC for {nov['novel_name']}: {e}")

            # 4. النشر في واتباد (إذا كان مفعلاً)
            if nov.get("wattpad_enabled") and nov.get("wattpad_story_id"):
                if not wp_token and not (wp_user and wp_pass):
                    wp_res = {"success": False, "error": "لم يتم حفظ توكن أو بيانات حساب واتباد في إعدادات المنظومة"}
                    syndication_db.log_syndication_event(
                        novel_id=nov["id"],
                        chapter_num=target_ch,
                        platform="wattpad",
                        status="FAILED",
                        error_msg=wp_res["error"]
                    )
                else:
                    try:
                        wp_client = wattpad_poster.WattpadClient(token=wp_token, username=wp_user, password=wp_pass)
                        wp_res = wp_client.publish_chapter_to_story(
                            story_id=nov["wattpad_story_id"],
                            chapter_num=target_ch,
                            title=extracted["title"],
                            content=extracted["content_for_publish"]
                        )
                        if wp_res.get("success"):
                            success_wp = True
                            syndication_db.log_syndication_event(
                                novel_id=nov["id"],
                                chapter_num=target_ch,
                                platform="wattpad",
                                status="SUCCESS",
                                post_url=wp_res.get("post_url", "")
                            )
                        else:
                            syndication_db.log_syndication_event(
                                novel_id=nov["id"],
                                chapter_num=target_ch,
                                platform="wattpad",
                                status="FAILED",
                                error_msg=wp_res.get("error", "")
                            )
                    except Exception as e:
                        logger.error(f"Error publishing WP for {nov['novel_name']}: {e}")
                        wp_res = {"success": False, "error": str(e)}

            # 5. إذا تم النشر بنجاح على منصة واحدة على الأقل
            if success_rc or success_wp:
                nov["last_synced_chapter"] = target_ch
                interval_secs = max(0.1, float(nov.get("interval_hours", 1.0))) * 3600
                nov["next_run_timestamp"] = time.time() + interval_secs
                syndication_db.save_or_update_syndicated_novel(nov)
                logger.info(f"Published Ch.{target_ch} for {nov['novel_name']}. Next in {nov['interval_hours']}h")

                # إرسال إشعار تليجرام فوري للمشرف (إذا كان فصلاً جديداً)
                is_already = (success_rc and rc_res.get("already_exists")) or (success_wp and wp_res.get("already_exists"))
                if not is_already:
                    try:
                        from nsw_healer_engine import notify_admin
                        from ui_syndication_tabs import format_schedule_time_label
                        next_dt_label = format_schedule_time_label(nov["next_run_timestamp"])
                        pub_links = []
                        if success_rc:
                            pub_links.append(f"• نادي الروايات: {rc_res.get('post_url', 'تم')}")
                        if success_wp:
                            pub_links.append(f"• واتباد: {wp_res.get('post_url', 'تم')}")
                        links_txt = "\n".join(pub_links)
                        msg = (
                            f"🚀 <b>[نشر تلقائي مجدول — ناجح]</b>\n\n"
                            f"📖 <b>الرواية:</b> {nov['novel_name']}\n"
                            f"📑 <b>الفصل:</b> {target_ch}\n"
                            f"🏷️ <b>العنوان:</b> {extracted.get('title', '')}\n"
                            f"{links_txt}\n\n"
                            f"⏰ <b>موعد الفصل القادم ({target_ch + 1}):</b> {next_dt_label} (بعد {nov['interval_hours']} ساعة)"
                        )
                        notify_admin(msg)
                    except Exception as ex_notif:
                        logger.warning(f"Could not send telegram notification: {ex_notif}")
            else:
                # إذا كان سبب التعذر هو نقص التوكن، نوقف الرواية وننبه المشرف دون تكرار الإزعاج كل 15 دقيقة
                if "wp_res" in locals() and "توكن" in str(wp_res.get("error", "")):
                    nov["is_active"] = 0
                    nov["next_run_timestamp"] = 0.0
                    syndication_db.save_or_update_syndicated_novel(nov)
                    try:
                        from nsw_healer_engine import notify_admin
                        notify_admin(
                            f"⚠️ <b>[تنبيه منصة واتباد]:</b>\n"
                            f"تم إيقاف النشر التلقائي لرواية '{nov['novel_name']}' مؤقتاً.\n"
                            f"<b>السبب:</b> لم يتم إدخال رمز التوكن (Token) لحساب واتباد بعد.\n\n"
                            f"💡 <i>يرجى فتح صفحة السيرفر والدخول لتبويب واتباد وحفظ التوكن ثم استئناف الجدولة.</i>"
                        )
                    except Exception:
                        pass
                else:
                    # في حال فشل النشر الفعلي تأجيل المحاولة 15 دقيقة مع إشعار تحذيري
                    nov["next_run_timestamp"] = time.time() + 900
                    syndication_db.save_or_update_syndicated_novel(nov)
                    try:
                        from nsw_healer_engine import notify_admin
                        err_msg = ""
                        if "rc_res" in locals() and rc_res.get("error"):
                            err_msg += f"نادي الروايات: {rc_res.get('error')} "
                        if "wp_res" in locals() and wp_res.get("error"):
                            err_msg += f"واتباد: {wp_res.get('error')}"
                        notify_admin(f"⚠️ <b>[تنبيه النشر المجدول]:</b>\nتعذر نشر الفصل {target_ch} لرواية '{nov['novel_name']}'.\nالسبب: {err_msg or 'خطأ اتصال'}\n⏳ سيتم إعادة المحاولة تلقائياً بعد 15 دقيقة.")
                    except Exception:
                        pass
        except Exception as e_nov:
            logger.error(f"Error in syndication cycle for {nov.get('novel_name', '?')}: {e_nov}")

def _ping_render_keep_alive():
    """إرسال نبضة حياة هادئة كل 10 دقائق لمنع خمول وحظر سيرفر Render السحابي المجاني."""
    try:
        import os, urllib.request
        render_url = os.environ.get("RENDER_EXTERNAL_URL", "https://2-yqmt.onrender.com/")
        req = urllib.request.Request(render_url, headers={"User-Agent": "NSW-Daemon-KeepAlive/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            pass
    except Exception:
        pass

def daemon_worker_loop():
    """حلقة السيرفر الدائرية التي تعمل 24/7 في الخلفية."""
    global _DAEMON_RUNNING
    logger.info("Syndication Daemon worker loop started (24/7).")
    last_ping = 0.0
    while _DAEMON_RUNNING:
        try:
            # نبضة حياة دورية لمنع نوم حاوية Render
            if time.time() - last_ping > 600:
                last_ping = time.time()
                _ping_render_keep_alive()

            run_syndication_cycle()
        except Exception as ex:
            logger.error(f"Error in daemon loop: {ex}")
        # فحص كل 60 ثانية بهدوء وخفة دون استهلاك معالج
        time.sleep(60)

def start_syndication_daemon():
    """تشغيل خدمة النشر التلقائي في خيط خلفي مستقل."""
    global _DAEMON_RUNNING, _DAEMON_THREAD
    if _DAEMON_RUNNING:
        return
    _DAEMON_RUNNING = True
    _DAEMON_THREAD = threading.Thread(target=daemon_worker_loop, daemon=True, name="SyndicationDaemonThread")
    _DAEMON_THREAD.start()
    print("[Launcher] Syndication Daemon started (24/7 Background Scheduler).")

def stop_syndication_daemon():
    """إيقاف مؤقت للخدمة."""
    global _DAEMON_RUNNING
    _DAEMON_RUNNING = False
