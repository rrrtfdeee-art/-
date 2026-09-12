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

def run_syndication_cycle():
    """تنفيذ دورة فحص واحدة لكافة الروايات النشطة في النظام."""
    novels = syndication_db.get_all_syndicated_novels(active_only=True)
    if not novels:
        return

    now = time.time()
    
    # جلب التوكنات العامة
    rc_token = syndication_db.get_synd_setting("rewayat_token", "")
    wp_token = syndication_db.get_synd_setting("wattpad_token", "")

    for nov in novels:
        try:
            # 1. التحقق هل حان موعد النشر؟
            next_run = nov.get("next_run_timestamp", 0.0)
            if next_run and now < next_run:
                continue

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
                continue  # الفصل غير متوفر بعد في شيت الترجمة

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
            if nov.get("wattpad_enabled") and nov.get("wattpad_story_id") and wp_token:
                try:
                    wp_client = wattpad_poster.WattpadClient(token=wp_token)
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

            # 5. إذا تم النشر بنجاح على منصة واحدة على الأقل
            if success_rc or success_wp:
                nov["last_synced_chapter"] = target_ch
                interval_secs = max(0.5, float(nov.get("interval_hours", 12.0))) * 3600
                nov["next_run_timestamp"] = time.time() + interval_secs
                syndication_db.save_or_update_syndicated_novel(nov)
                logger.info(f"Published Ch.{target_ch} for {nov['novel_name']}. Next in {nov['interval_hours']}h")

        except Exception as e_nov:
            logger.error(f"Error in syndication daemon for novel {nov.get('novel_name')}: {e_nov}")

def daemon_worker_loop():
    """حلقة السيرفر الدائرية التي تعمل 24/7 في الخلفية."""
    global _DAEMON_RUNNING
    logger.info("Syndication Daemon worker loop started (24/7).")
    while _DAEMON_RUNNING:
        try:
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
