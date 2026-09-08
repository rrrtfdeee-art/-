# -*- coding: utf-8 -*-
"""
==============================================================================
Smart Telegram Bot Interface - Novel Scraper & Media Downloader v1.0
==============================================================================
"""

import os
import sys
import time
import threading
from typing import Dict, Any, Optional

# ضبط ترميز الإخراج ليتوافق مع الرموز التعبيرية واللغة العربية في ويندوز
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

try:
    import telebot
    from telebot import types
except ImportError:
    telebot = None

import database
import scraper_engine
import media_engine
import cinema_engine
import nsw_healer_engine
from gemini_analyzer import DEFAULT_GAS_URL

# اسم مستخدم البوت الافتراضي وتوكن التحكم
DEFAULT_BOT_USERNAME = "@SmartNovelMediaBot"
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", database.get_setting("telegram_bot_token", "8914532697:AAFrBMD5o5rWWvXEfjXC0EXOEwPQad0fiy4"))
ADMIN_CHAT_ID = os.getenv("TELEGRAM_ALLOWED_USER", database.get_setting("telegram_allowed_user", "8883556949"))

# جلسات المستخدمين المؤقتة لاختيار الخيارات
USER_SESSIONS: Dict[int, Dict[str, Any]] = {}


def get_whitelisted_users() -> set:
    """جلب قائمة المستخدمين المسموح لهم من قاعدة البيانات."""
    raw = database.get_setting("telegram_whitelist", "")
    users = set()
    if ADMIN_CHAT_ID:
        users.add(str(ADMIN_CHAT_ID).strip())
    if raw:
        for u in raw.split(","):
            if u.strip():
                users.add(u.strip().lower().replace("@", ""))
    return users


def is_user_authorized(message_or_call) -> bool:
    """التحقق من أن المستخدم إما الأدمن أو موجود في القائمة البيضاء."""
    chat_id = str(message_or_call.from_user.id)
    username = (message_or_call.from_user.username or "").lower().strip()

    # إذا كان وضع البوت عاماً للجميع مؤقتاً
    if database.get_setting("telegram_public_mode", "false") == "true":
        return True

    allowed = get_whitelisted_users()
    if not allowed:
        return True  # متاح للجميع في حال لم يحدد الأدمن أحداً بعد

    return (chat_id in allowed) or (username in allowed)


def is_admin(user_id: int) -> bool:
    """التحقق مما إذا كان المستخدم هو المشرف الأساسي."""
    if not ADMIN_CHAT_ID:
        return True
    return str(user_id).strip() == str(ADMIN_CHAT_ID).strip()


def make_novel_selection_markup(prefix: str, include_all: bool = True) -> types.InlineKeyboardMarkup:
    """إنشاء لوحة مفاتيح تفاعلية لاختيار الرواية ديناميكياً من الدليل المركزي."""
    import nsw_healer_engine
    catalog = nsw_healer_engine.get_available_novels_catalog()
    markup = types.InlineKeyboardMarkup(row_width=1)
    for idx, n in enumerate(catalog):
        markup.add(types.InlineKeyboardButton(f"📖 {n['name']}", callback_data=f"{prefix}_{idx}"))
    if include_all:
        markup.add(types.InlineKeyboardButton("🌐 كافة الروايات المسجلة", callback_data=f"{prefix}_all"))
    markup.add(types.InlineKeyboardButton("❌ إلغاء", callback_data="CANCEL_ACTION"))
    return markup


def get_novel_from_catalog_idx(idx_str: str) -> Optional[str]:
    """استرجاع اسم الرواية الحقيقي بناءً على فهرس الاختيار."""
    if idx_str == "all":
        return None
    import nsw_healer_engine
    catalog = nsw_healer_engine.get_available_novels_catalog()
    try:
        idx = int(idx_str)
        if 0 <= idx < len(catalog):
            return catalog[idx]["name"]
    except Exception:
        pass
    return "After Severing Ties"


def create_bot_app():
    if not telebot or not BOT_TOKEN:
        return None

    from telebot import apihelper
    # زيادة مهلة الاتصال لـ 60 ثانية لحماية البوت من انقطاعات وتذبذب الشبكة
    apihelper.READ_TIMEOUT = 60
    apihelper.CONNECT_TIMEOUT = 30
    apihelper.RETRY_ON_ERROR = True

    bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

    # تسجيل قائمة الأوامر في زر Menu الرسمي بتطبيق تيليجرام
    try:
        bot.set_my_commands([
            types.BotCommand("menu", "📑 القائمة الرئيسية وأزرار التحكم"),
            types.BotCommand("repair", "🛡️ الإصلاح الشامل (فجوات + مبتورات + تنقل)"),
            types.BotCommand("fix_dates", "🗓️ إصلاح وتنسيق تواريخ نشر الفصول"),
            types.BotCommand("fix_titles", "🏷️ توحيد صيغة العناوين (الفصل X: العنوان)"),
            types.BotCommand("nav", "🔗 صيانة وربط أزرار التنقل (السابق/التالي/الفهرس)"),
            types.BotCommand("status", "📊 حالة المنظومة والمهام اللحظية"),
            types.BotCommand("gaps", "🧩 فحص وسد الفصول المفقودة والمسودات"),
            types.BotCommand("heal", "🩹 استصلاح الفصول المبتورة أو الناقصة"),
            types.BotCommand("stage", "🎭 تجهيز دفعة الـ 20 فصلاً لـ Claude Opus"),
            types.BotCommand("fix", "🎯 إصلاح أو ترجمة فصل فردي محدد"),
            types.BotCommand("publish", "🚀 نشر فصول مخصصة"),
            types.BotCommand("stop", "🛑 إيقاف فوري طارئ للمحرك"),
            types.BotCommand("help", "📋 عرض دليل الأوامر والمساعدة"),
        ])
    except Exception as cmd_err:
        print(f"[Telegram Bot] Warning setting commands menu: {cmd_err}")

    # ----------------------------------------------------
    # أوامر المشرف (Admin Control Commands)
    # ----------------------------------------------------
    @bot.message_handler(commands=['admin'])
    def admin_panel(message):
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر مخصص للمشرف فقط.")
            return

        mode = "🌐 عام (مفتوح للجميع)" if database.get_setting("telegram_public_mode", "false") == "true" else "🔒 خاص (للمصرح لهم فقط)"
        users_list = ", ".join(f"@{u}" for u in get_whitelisted_users()) or "لا يوجد غيرك"

        text = (
            "👑 <b>لوحة تحكم المشرف (Admin Panel)</b>\n\n"
            f"• <b>وضع البوت الحالي:</b> {mode}\n"
            f"• <b>المستخدمون المسموح لهم:</b> {users_list}\n\n"
            "<b>الأوامر الإدارية المتاحة:</b>\n"
            "➕ <code>/add @username</code> : لإضافة شخص مسموح له بالاستخدام.\n"
            "➖ <code>/remove @username</code> : لحذف شخص من القائمة.\n"
            "🌐 <code>/public</code> : لفتح البوت مؤقتاً للجميع (للاستعراض).\n"
            "🔒 <code>/private</code> : لقفل البوت وحصره عليك وعلى المضافين فقط.\n"
        )
        bot.reply_to(message, text)

    @bot.message_handler(commands=['add'])
    def add_user_cmd(message):
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ عذراً، هذا الأمر للمشرف فقط.")
            return

        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ يرجى كتابة اليوزر، مثلاً:\n<code>/add @username</code> أو <code>/add 12345678</code>")
            return

        new_user = parts[1].strip().lower().replace("@", "")
        current = get_whitelisted_users()
        current.add(new_user)
        database.save_setting("telegram_whitelist", ",".join(current))
        bot.reply_to(message, f"✅ <b>تم بنجاح إضافة (@{new_user}) إلى قائمة المسموح لهم!</b>\nيمكنه الآن استخدام البوت بكل مميزاته.")

    @bot.message_handler(commands=['remove'])
    def remove_user_cmd(message):
        if not is_admin(message.from_user.id):
            return

        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ يرجى كتابة اليوزر، مثلاً:\n<code>/remove @username</code>")
            return

        target_user = parts[1].strip().lower().replace("@", "")
        current = get_whitelisted_users()
        current.discard(target_user)
        database.save_setting("telegram_whitelist", ",".join(current))
        bot.reply_to(message, f"🗑️ <b>تم حذف (@{target_user}) من القائمة.</b>")

    @bot.message_handler(commands=['public'])
    def set_public_cmd(message):
        if not is_admin(message.from_user.id):
            return
        database.save_setting("telegram_public_mode", "true")
        bot.reply_to(message, "🌐 <b>تم تفعيل الوضع العام!</b> البوت الآن متاح لأي شخص للتجربة والاستعراض.")

    @bot.message_handler(commands=['private'])
    def set_private_cmd(message):
        if not is_admin(message.from_user.id):
            return
        database.save_setting("telegram_public_mode", "false")
        bot.reply_to(message, "🔒 <b>تم تفعيل الوضع الخاص!</b> البوت مقفل الآن ومتاح لك وللمستخدمين المصرح لهم فقط.")

    @bot.message_handler(commands=['start', 'help', 'menu'])
    @bot.message_handler(func=lambda msg: msg.text and msg.text.strip().lower() in ['ابدأ', 'ابدا', 'مرحبا', 'start', 'help', 'menu', 'قائمة', 'القائمة', 'الاوامر', 'الأوامر', 'القائمة الرئيسية', 'اوامر'])
    def send_welcome(message):
        if not is_user_authorized(message):
            bot.reply_to(message, "⛔ <b>عذراً، هذا البوت خاص وغير متاح للعامة.</b>\nتواصل مع مالك البوت للحصول على إذن الاستخدام.")
            return

        is_adm = is_admin(message.from_user.id)
        admin_hint = "\n👑 <b>أنت في وضع المشرف (Admin Mode).</b>" if is_adm else ""
        text = (
            "👋 <b>مرحباً بك في مركز تحكم Novelskyworld & Media AI!</b>\n\n"
            "هذا البوت مجهز لإدارة منظومة النشر والترجمة وسحب الوسائط بأعلى دقة:\n"
            "🛡️ <b>منظومة NSW:</b> فحص وسد الفجوات، واستصلاح المبتورات، وصيانة أزرار التنقل.\n"
            "📚 <b>سحب الروايات:</b> أرسل رابط فهرس أي رواية لسحب فصولها وتصديرها بملف TXT كامل.\n"
            "🎬 <b>تحميل الوسائط:</b> أرسل رابط فيديو (يوتيوب/تيك توك/تويتر) أو اطلب كشف الأفلام."
            f"{admin_hint}\n\n"
            "👇 <b>استخدم الأزرار التفاعلية أدناه للتحكم السريع:</b>"
        )
        markup = None
        if is_adm:
            markup = types.InlineKeyboardMarkup(row_width=2)
            btn_repair = types.InlineKeyboardButton("🛡️ الإصلاح الشامل الفائق", callback_data="cb_nsw_repair")
            btn_dates = types.InlineKeyboardButton("🗓️ إصلاح تواريخ النشر", callback_data="cb_fix_dates_start")
            btn_nav = types.InlineKeyboardButton("🔗 صيانة أزرار التنقل", callback_data="cb_nsw_nav")
            btn_sync = types.InlineKeyboardButton("🔄 مطابقة الشيت مع بلوجر", callback_data="cb_sync_blogger_start")
            btn_dups = types.InlineKeyboardButton("🧹 تطهير الفصول المكررة", callback_data="cb_purge_dups_start")
            btn_time = types.InlineKeyboardButton("⏱️ فحص تسلسل الجدولة", callback_data="cb_check_timeline_start")
            btn_gaps = types.InlineKeyboardButton("🧩 سد الفجوات الترقيمية", callback_data="cb_nsw_gaps")
            btn_heal = types.InlineKeyboardButton("🩹 استصلاح المبتورات", callback_data="cb_nsw_heal")
            btn_export = types.InlineKeyboardButton("📥 تصدير فصول TXT", callback_data="cb_export_chapters_start")
            btn_stage = types.InlineKeyboardButton("🎭 صقل أوبس (Opus)", callback_data="cb_nsw_stage")
            btn_status = types.InlineKeyboardButton("📊 حالة المنظومة", callback_data="cb_nsw_status")
            btn_stop = types.InlineKeyboardButton("🛑 إيقاف فوري", callback_data="cb_nsw_stop")
            btn_help = types.InlineKeyboardButton("📋 دليل الأوامر", callback_data="cb_nsw_help")
            markup.add(btn_repair)
            markup.add(btn_dates, btn_nav)
            markup.add(btn_sync, btn_dups)
            markup.add(btn_time)
            markup.add(btn_gaps, btn_heal)
            btn_titles = types.InlineKeyboardButton("🏷️ توحيد صيغة العناوين", callback_data="cb_fix_titles_start")
            markup.add(btn_export, btn_titles)
            markup.add(btn_stage, btn_status)
            markup.add(btn_help, btn_stop)

        bot.reply_to(message, text, reply_markup=markup)

    @bot.message_handler(content_types=['photo', 'video'])
    def handle_incoming_media(message):
        if not is_user_authorized(message):
            bot.reply_to(message, "⛔ <b>غير مصرح لك بالاستخدام.</b>")
            return

        chat_id = message.chat.id
        status_msg = bot.reply_to(message, "🔍 <b>جاري فحص المقطع/الصورة بالذكاء الاصطناعي والتعرف على الفيلم أو المسلسل...</b>")

        def _recognize_task():
            try:
                # تنزيل الصورة أو لقطة الفيديو
                file_id = message.photo[-1].file_id if message.photo else message.video.file_id
                file_info = bot.get_file(file_id)
                downloaded_file = bot.download_file(file_info.file_path)

                mime = "image/jpeg" if message.photo else "video/mp4"
                caption = message.caption or ""
                res = cinema_engine.analyze_cinema_content(query_text=caption, image_bytes=downloaded_file, image_mime_type=mime)
                _send_cinema_result(chat_id, res, status_msg.message_id)
            except Exception as e:
                bot.edit_message_text(f"❌ تعذر التعرف على المحتوى: {str(e)}", chat_id, status_msg.message_id)

        threading.Thread(target=_recognize_task, daemon=True).start()

    def _send_cinema_result(chat_id: int, res: dict, replace_msg_id: Optional[int] = None):
        recognized = res.get("recognized", False)
        title_ar = res.get("title_arabic", "غير معروف")
        title_orig = res.get("title_original", "")
        c_type = res.get("type", "unknown")
        story = res.get("story_arabic", "لا يتوفر وصف حالياً.")
        rating = res.get("rating", "N/A")
        year = res.get("release_year", "")
        duration = res.get("duration", "")
        seasons_cnt = res.get("seasons_count", 1)

        # إذا لم يتم التعرف على العمل بنجاح (مثلاً إرسال أمر /cinema فقط أو وصف فارغ)
        if not recognized or c_type == "unknown" or (title_ar in ["غير معروف", "N/A"] and not title_orig):
            text = (
                "ℹ️ <b>ميزة التعرف السينمائي الذكي:</b>\n\n"
                "لم يتم التعرف على العمل المطلوب بدقة.\n\n"
                "💡 <b>كيفية الاستخدام:</b>\n"
                "• أرسل <b>صورة</b> أو <b>لقطة شاشة</b> من الفيلم/المسلسل.\n"
                "• أو أرسل <b>اسم العمل أو وصف المشهد</b> كتابة (مثال: <code>Breaking Bad</code> أو <code>فيلم عن الأحلام لنولان</code>).\n"
                "• أو أرسل <b>رابط فيديو</b> (ريلز/يوتيوب) واضغط كشف بالذكاء الاصطناعي."
            )
            if replace_msg_id:
                try:
                    bot.edit_message_text(text, chat_id, replace_msg_id)
                    return
                except Exception:
                    pass
            bot.send_message(chat_id, text)
            return

        type_label = "🎬 فيلم" if c_type == "movie" else ("📺 مسلسل تلفزيوني" if c_type == "series" else "❓ عمل فني")

        text = (
            f"✨ <b>تم التعرف على العمل بنجاح!</b>\n\n"
            f"🏷️ <b>الاسم بالعربي:</b> {title_ar}\n"
            f"🌐 <b>الاسم الأصلي:</b> <code>{title_orig}</code>\n"
            f"🎭 <b>النوع:</b> {type_label} | {year}\n"
            f"⭐ <b>التقييم:</b> {rating} | ⏱️ {duration}\n\n"
            f"📖 <b>القصة:</b>\n{story}\n"
        )

        USER_SESSIONS[chat_id] = {
            "cinema_data": res,
            "title": title_orig or title_ar
        }

        markup = types.InlineKeyboardMarkup(row_width=2)
        if c_type == "series":
            btn_seasons = types.InlineKeyboardButton(f"📂 استعراض المواسم ({seasons_cnt})", callback_data="cin_seasons")
            markup.add(btn_seasons)
        else:
            btn_dl_sub = types.InlineKeyboardButton("📥 تنزيل الفيلم (مترجم)", callback_data="cin_dl_sub")
            btn_dl_raw = types.InlineKeyboardButton("📥 تنزيل الفيلم (أصلي)", callback_data="cin_dl_raw")
            markup.add(btn_dl_sub, btn_dl_raw)

        if replace_msg_id:
            try:
                bot.edit_message_text(text, chat_id, replace_msg_id, reply_markup=markup)
                return
            except Exception:
                pass
        bot.send_message(chat_id, text, reply_markup=markup)

    @bot.message_handler(commands=['cinema'])
    def handle_cinema_command(message):
        if not is_user_authorized(message):
            bot.reply_to(message, "⛔ <b>غير مصرح لك بالاستخدام.</b>")
            return
        args = message.text.replace("/cinema", "").strip()
        if args:
            status_msg = bot.reply_to(message, f"🔎 <b>جاري فحص والتعرف على:</b> <i>{args}</i>...")
            def _rec_arg():
                res = cinema_engine.analyze_cinema_content(query_text=args)
                _send_cinema_result(message.chat.id, res, status_msg.message_id)
            threading.Thread(target=_rec_arg, daemon=True).start()
        else:
            bot.reply_to(
                message,
                "🎬 <b>ميزة السينما والمسلسلات:</b>\n"
                "أرسل اسم الفيلم أو المسلسل مباشرة، أو أرسل صورة/لقطة شاشة للتعرف عليها فوراً واستعراض مواسمها وحلقاتها."
            )

    @bot.message_handler(commands=['media'])
    def handle_media_command(message):
        bot.reply_to(message, "🎬 <b>محرك تنزيل الفيديوهات والصوتيات:</b>\nفقط أرسل أي رابط من (يوتيوب، تيك توك، إنستغرام، أو تويتر) وسيتم تنزيله فوراً مع التجزئة التلقائية إذا لزم.")

    @bot.message_handler(commands=['novel'])
    def handle_novel_command(message):
        bot.reply_to(message, "📚 <b>محرك سحب الروايات:</b>\nأرسل رابط صفحة الرواية أو الفهرس لسحب كافة الفصول بدقة وتصديرها بملف TXT نظيف.")

    # ================================================================
    # أوامر إدارة NSW (نظام النشر والترجمة على Blogger)
    # ================================================================

    
    @bot.message_handler(commands=['fix_titles', 'clean_titles'])
    def nsw_fix_titles_cmd(message):
        """توحيد وتصحيح صيغة عناوين الفصول لتصبح 'الفصل X: العنوان' في بلوجر والشيت."""
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر مخصص للمشرف فقط.")
            return

        chat_id = message.chat.id
        parts = message.text.strip().split()
        dry_run = ("--dry-run" in parts or "معاينة" in parts)
        novel_name = ""
        for p in parts[1:]:
            if not p.startswith("--") and p != "معاينة":
                novel_name += (" " + p if novel_name else p)

        mode_str = "🔍 [معاينة تجريبية - Dry Run]" if dry_run else "⚡ [تنفيذ فعلي وتعديل في Blogger والشيت]"
        novel_str = novel_name if novel_name else "كافة الروايات"

        wait_msg = bot.reply_to(
            message,
            f"🏷️ <b>جاري تشغيل دالة توحيد وتصحيح عناوين الفصول...</b>\n"
            f"• <b>الوضع:</b> {mode_str}\n"
            f"• <b>الرواية المستهدفة:</b> <code>{novel_str}</code>\n"
            f"• <b>الصيغة الموحدة:</b> <code>الفصل X: العنوان</code>\n\n"
            f"⏳ يتم الآن فحص تدوينات Blogger (بما فيها المجدولة والمسودات) وتعديلها عبر محرك كود النشر..."
        )

        def _worker():
            try:
                import nsw_healer_engine
                total_updated_blogger = 0
                total_updated_sheets = 0
                total_scanned = 0
                total_matched = 0
                samples = []
                batch_round = 0
                max_rounds = 30  # أقصى حد للدفعات لحماية العملية

                while batch_round < max_rounds:
                    batch_round += 1
                    res = nsw_healer_engine.clean_and_unify_chapter_titles(novel_name, dry_run=dry_run, max_batch=35)
                    if not res.get("success"):
                        err_msg = res.get('message', res.get('error', 'تعذر إتمام المهمة'))
                        bot.edit_message_text(f"⚠️ تنبيه من كود النشر: {err_msg}", chat_id, wait_msg.message_id)
                        return

                    st = res.get("stats", {})
                    up_b = st.get("updatedBlogger", 0)
                    up_s = st.get("updatedSheets", 0)
                    total_scanned = max(total_scanned, st.get("totalScanned", 0))
                    total_matched = max(total_matched, st.get("matchedNovel", 0))
                    total_updated_blogger += up_b
                    total_updated_sheets += up_s

                    if not samples and st.get("samples"):
                        samples = st.get("samples")

                    # إذا لم يعد هناك فصول تحتاج للتعديل
                    if up_b == 0:
                        break

                    # تحديث رسالة التقدم اللحظي في تيليجرام
                    try:
                        bot.edit_message_text(
                            f"🏷️ <b>جاري توحيد وتصحيح العناوين عبر الدفعات الذكية...</b>\n"
                            f"• الوضع: {mode_str}\n"
                            f"• تم تعديل <b>{total_updated_blogger}</b> عنوناً حتى الآن (الدفعة #{batch_round})...\n"
                            f"⏳ جاري معالجة الدفعة التالية فوراً دون توقف...",
                            chat_id, wait_msg.message_id
                        )
                    except Exception:
                        pass

                    import time
                    time.sleep(1)

                out = (
                    f"✅ <b>[اكتمل فحص وتوحيد عناوين الفصول بنجاح تام]</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"• الوضع: <b>{mode_str}</b>\n"
                    f"• إجمالي الفصول المفحوصة في Blogger: <b>{total_scanned}</b>\n"
                    f"• إجمالي الفصول التي تم تصحيحها في Blogger: <b>{total_updated_blogger}</b>\n"
                    f"• إجمالي الفصول التي تم تصحيحها في الشيت: <b>{total_updated_sheets}</b>\n"
                    f"• النتيجة: أصبحت كافة العناوين بصيغة <code>الفصل X: العنوان</code> 🎯"
                )
                if samples:
                    out += "\n\n📋 <b>عينات من العناوين بعد التوحيد:</b>\n"
                    for s in samples[:5]:
                        out += f"• <code>{s.get('from','')[:40]}...</code>\n  ↳ <b>{s.get('to')}</b>\n"
                bot.edit_message_text(out, chat_id, wait_msg.message_id)
            except Exception as e:
                bot.edit_message_text(f"❌ خطأ أثناء تشغيل دالة تصحيح العناوين: {e}", chat_id, wait_msg.message_id)

        threading.Thread(target=_worker, daemon=True).start()

    @bot.message_handler(commands=['nsw_status', 'status'])
    def nsw_status_cmd(message):
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر مخصص للمشرف فقط.")
            return
        try:
            import nsw_healer_engine
            report = nsw_healer_engine.get_realtime_engine_report()
            bot.reply_to(message, report)
        except Exception as e:
            bot.reply_to(message, f"⚠️ تعذر جلب التقرير: {e}")

    def _run_nav_repair(chat_id: int, novel_filter: Optional[str], start_chap: int = 1):
        target_name = novel_filter or "كافة الروايات"
        bot.send_message(
            chat_id,
            f"🔗 <b>جاري بدء صيانة وربط أزرار التنقل ({target_name}) بدءاً من الفصل {start_chap}...</b>\n"
            "سيتم فحص جدول النشر وقراءة الروابط وربط كل فصل بالسابق واللاحق والفهرس بدقة متناهية."
        )
        def _task():
            try:
                import nsw_healer_engine
                res = nsw_healer_engine.repair_all_chapter_navigation(novel_filter, start_chapter=start_chap)
                if res.get("success"):
                    bot.send_message(chat_id, (
                        f"✅ <b>اكتملت صيانة أزرار التنقل بنجاح!</b> 🎉\n"
                        f"📖 <b>الرواية:</b> {target_name}\n"
                        f"🔗 <b>الفصول المربوطة:</b> {res.get('linksPatched', 0)} فصلاً\n"
                        f"🛡️ تم ربط أزرار السابق والتالي والفهرس بنجاح دون أي قفزات."
                    ))
                else:
                    bot.send_message(chat_id, f"⚠️ تنبيه: {res.get('error', 'تعذر إتمام صيانة التنقل')}")
            except Exception as e:
                bot.send_message(chat_id, f"❌ خطأ أثناء صيانة أزرار التنقل: {e}")
        threading.Thread(target=_task, daemon=True).start()

    def _run_full_repair(chat_id: int, novel_filter: Optional[str]):
        target_name = novel_filter or "After Severing Ties"
        bot.send_message(
            chat_id,
            f"🛡️ <b>تم إطلاق عملية الإصلاح والصيانة الشاملة لرواية '{target_name}'...</b>\n\n"
            "1️⃣ سد الفجوات المفقودة وترقية المسودات.\n"
            "2️⃣ استصلاح الفصول المبتورة في مكانها.\n"
            "3️⃣ ربط أزرار التنقل بالتسلسل التام.\n\n"
            "⏳ سيصلك تقرير مفصل عند اكتمال كل مرحلة."
        )
        def _task():
            try:
                import nsw_healer_engine
                nsw_healer_engine.run_comprehensive_full_repair(novel_filter)
            except Exception as e:
                bot.send_message(chat_id, f"❌ خطأ أثناء دورة الإصلاح الشامل: {e}")
        threading.Thread(target=_task, daemon=True).start()

    def _run_gaps_repair(chat_id: int, novel_filter: Optional[str]):
        target_name = novel_filter or "كافة الروايات"
        bot.send_message(
            chat_id,
            f"🧩 <b>جاري فحص الفصول المفقودة وملء الفجوات ({target_name})...</b>\n"
            "سيصلك تقرير عند الاكتمال."
        )
        def _task():
            try:
                import nsw_healer_engine
                nsw_healer_engine.run_auto_fill_all_gaps(novel_filter)
            except Exception as e:
                bot.send_message(chat_id, f"❌ خطأ أثناء ملء الفجوات: {e}")
        threading.Thread(target=_task, daemon=True).start()

    @bot.message_handler(commands=['nsw_gaps', 'gaps'])
    def nsw_gaps_cmd(message):
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر للمشرف فقط.")
            return
        parts = message.text.strip().split(None, 1)
        if len(parts) <= 1:
            markup = make_novel_selection_markup("cb_nvgap", include_all=True)
            bot.reply_to(
                message,
                "🧩 <b>[فحص وسد الفجوات الترقيمية]</b>\n\n"
                "أي رواية ترغب بفحص وسد فجواتها الترقيمية؟\n"
                "اختر إحدى الروايات أدناه:",
                reply_markup=markup
            )
            return
        novel_filter = parts[1].strip()
        _run_gaps_repair(message.chat.id, novel_filter)

    @bot.message_handler(commands=['nsw_repair', 'repair', 'full_repair', 'super_repair'])
    def nsw_repair_cmd(message):
        """أمر الإصلاح والصيانة الشامل: سد الفجوات + استصلاح المبتورات + صيانة أزرار التنقل دفعة واحدة."""
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر للمشرف فقط.")
            return
        parts = message.text.strip().split(None, 1)
        if len(parts) <= 1:
            markup = make_novel_selection_markup("cb_nvrep", include_all=True)
            bot.reply_to(
                message,
                "🛡️ <b>[الإصلاح الشامل الكامل]</b>\n\n"
                "أي رواية ترغب بإجراء دورة الإصلاح والصيانة الشاملة الكاملة لها؟\n"
                "اختر إحدى الروايات أدناه:",
                reply_markup=markup
            )
            return
        novel_filter = parts[1].strip()
        _run_full_repair(message.chat.id, novel_filter)

    @bot.message_handler(commands=['nsw_heal', 'heal', 'truncated'])
    def nsw_heal_cmd(message):
        """فحص واستصلاح الفصول المبتورة أو الناقصة على Blogger."""
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر للمشرف فقط.")
            return
        parts = message.text.strip().split(None, 1)
        novel_filter = parts[1].strip() if len(parts) > 1 else None
        
        target_name = novel_filter or "كافة الروايات"
        bot.reply_to(message, f"🩹 <b>جاري فحص واستصلاح الفصول المبتورة ({target_name})...</b>\nسيتم التحقق من المتن العربي واستصلاح أي فصل ناقص.")
        def _run():
            try:
                import nsw_healer_engine
                nsw_healer_engine.run_full_auto_heal(novel_filter)
            except Exception as e:
                bot.send_message(message.chat.id, f"❌ خطأ أثناء الاستصلاح: {e}")
        threading.Thread(target=_run, daemon=True).start()

    @bot.message_handler(commands=['nsw_fix', 'fix'])
    def nsw_fix_cmd(message):
        """مثال: /nsw_fix اسم الرواية 456"""
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر للمشرف فقط.")
            return
        parts = message.text.strip().split()
        cmd = parts[0]  # /nsw_fix أو /fix
        rest = parts[1:] if len(parts) > 1 else []

        if len(rest) >= 2 and rest[-1].isdigit():
            chap_num = int(rest[-1])
            novel_name = " ".join(rest[:-1])
        elif len(rest) == 1 and rest[0].isdigit():
            chap_num = int(rest[0])
            novel_name = "After Severing Ties"
        else:
            novel_name = " ".join(rest) if rest else "After Severing Ties"
            chap_num = 1
            bot.reply_to(message, (
                "⚠️ <b>مثال على استخدام الأمر:</b>\n"
                "<code>/nsw_fix اسم الرواية 456</code>\n"
                "أو: <code>/fix 456</code> (للرواية الافتراضية)"
            ))
            return

        bot.reply_to(message, f"🎯 <b>جاري إصلاح الفصل {chap_num} من رواية '{novel_name}'...</b>")
        def _run():
            try:
                import nsw_healer_engine
                nsw_healer_engine.fix_single_chapter_x(novel_name, chap_num)
            except Exception as e:
                bot.send_message(message.chat.id, f"❌ خطأ: {e}")
        threading.Thread(target=_run, daemon=True).start()

    @bot.message_handler(commands=['nsw_publish', 'publish'])
    def nsw_publish_cmd(message):
        """مثال: /nsw_publish اسم الرواية 1,5,10-20"""
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر للمشرف فقط.")
            return
        parts = message.text.strip().split(None, 2)
        if len(parts) < 3:
            bot.reply_to(message, (
                "⚠️ <b>الاستخدام:</b>\n"
                "<code>/nsw_publish اسم الرواية 1,5,10-20</code>\n"
                "لنشر فصول محددة أو نطاقات منفصلة."
            ))
            return
        novel_name = parts[1]
        chapters_str = parts[2]
        bot.reply_to(message, f"🚀 <b>جاري نشر الفصول المحددة لرواية '{novel_name}'...</b>\n📋 الفصول: <code>{chapters_str}</code>")
        def _run():
            try:
                import nsw_healer_engine
                nsw_healer_engine.publish_specific_chapters(novel_name, chapters_str)
            except AttributeError:
                bot.send_message(message.chat.id, "⚠️ دالة النشر المنفرد غير متاحة بعد في محرك NSW.")
            except Exception as e:
                bot.send_message(message.chat.id, f"❌ خطأ أثناء النشر: {e}")
        threading.Thread(target=_run, daemon=True).start()

    @bot.message_handler(commands=['export_chapters', 'export', 'get_chapters', 'dump_chapters'])
    def nsw_export_chapters_cmd(message):
        """تصدير فصول رواية من مدونة بلوجر بملف TXT نظيف."""
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر مخصص للمشرف فقط.")
            return

        # تحليل الأمر: /export [الرواية] [النطاق] أو /export [النطاق]
        raw_text = message.text.strip()
        parts = raw_text.split(None, 1)
        args_str = parts[1].strip() if len(parts) > 1 else ""

        if not args_str:
            markup = make_novel_selection_markup("cb_nvexport", include_all=False)
            bot.reply_to(
                message,
                "📥 <b>[تصدير فصول من مدونة بلوجر إلى ملف TXT]</b>\n\n"
                "اختر الرواية أدناه، أو أرسل الأمر مباشرة بالصيغة:\n"
                "<code>/export After Severing Ties 400-450</code>\n"
                "أو لتصدير الرواية الافتراضية:\n"
                "<code>/export 490-500</code>",
                reply_markup=markup
            )
            return

        # كشف إذا كان المعطى يحتوي على اسم رواية ونطاق
        import nsw_healer_engine
        tokens = args_str.rsplit(None, 1)
        if len(tokens) == 2 and (re.search(r'\d', tokens[1])):
            novel_name = tokens[0].strip()
            range_str = tokens[1].strip()
        elif len(tokens) == 1 and re.search(r'\d', tokens[0]):
            novel_name = "After Severing Ties"
            range_str = tokens[0].strip()
        else:
            novel_name = args_str
            range_str = "1-20"

        _run_export_chapters_task(message.chat.id, novel_name, range_str)

    def _run_export_chapters_task(chat_id: int, novel_name: str, range_str: str):
        status_msg = bot.send_message(
            chat_id,
            f"⏳ <b>جاري جلب الفصول ({range_str}) لرواية:</b> <code>{novel_name}</code> من مدونة بلوجر...\n"
            "يتم الآن استرجاع المنشورات وتجريد كود HTML وتجميع النص الصافي في ملف TXT."
        )

        def _task():
            try:
                import nsw_healer_engine
                res = nsw_healer_engine.export_chapters_from_blogger_to_txt(
                    novel_name=novel_name,
                    range_str=range_str
                )

                if not res.get("success"):
                    bot.edit_message_text(
                        f"❌ <b>تعذر التصدير:</b>\n{res.get('error', 'خطأ غير معروف')}",
                        chat_id,
                        status_msg.message_id
                    )
                    return

                file_path = res.get("file_path")
                filename = res.get("filename")
                exported_cnt = res.get("total_exported", 0)
                file_size_kb = res.get("file_size_kb", 0)
                missing = res.get("missing_chapters", [])

                caption = (
                    f"📚 <b>[تم بنجاح تصدير الفصول من المدونة!]</b> 🚀\n"
                    f"📖 <b>الرواية:</b> {novel_name}\n"
                    f"🔢 <b>النطاق:</b> {range_str}\n"
                    f"📄 <b>الفصول المصدرة:</b> <b>{exported_cnt}</b> فصلاً\n"
                    f"💾 <b>الحجم:</b> {file_size_kb} KB"
                )
                if missing:
                    caption += f"\n⚠️ <i>لم يتم العثور على {len(missing)} فصول بالمدونة: {missing[:10]}</i>"

                bot.delete_message(chat_id, status_msg.message_id)
                with open(file_path, "rb") as doc_file:
                    bot.send_document(
                        chat_id,
                        doc_file,
                        caption=caption
                    )
            except Exception as e:
                bot.edit_message_text(f"❌ خطأ أثناء معالجة التصدير: {e}", chat_id, status_msg.message_id)

        threading.Thread(target=_task, daemon=True).start()

    @bot.message_handler(commands=['nsw_stage', 'stage', 'opus_stage', 'opus'])
    def nsw_stage_cmd(message):
        """لوحة تحكم طابور Claude Opus مع زر بدء السحب الفوري."""
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر للمشرف فقط.")
            return
        parts = message.text.strip().split(None, 1)
        novel_filter = parts[1].strip() if len(parts) > 1 else "After Severing Ties"
        
        import sync_opus_queue
        p_cnt = len(list(sync_opus_queue.PENDING_DIR.glob("chapter_*.txt")))
        a_cnt = len(list(sync_opus_queue.APPROVED_DIR.glob("chapter_*.txt")))
        pub_cnt = len(list(sync_opus_queue.PUBLISHED_DIR.glob("chapter_*.txt")))

        text = (
            f"🎭 <b>[لوحة تحكم طابور صقل Claude Opus]:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📖 <b>الرواية:</b> {novel_filter}\n"
            f"⏳ <b>في الانتظار (Pending):</b> <b>{p_cnt}</b> فصلاً\n"
            f"✍️ <b>معتمدة للرفع (Approved):</b> <b>{a_cnt}</b> فصلاً\n"
            f"✅ <b>منشورة وموثقة (Published):</b> <b>{pub_cnt}</b> فصلاً\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👇 <b>اضغط الزر أدناه لبدء العملية فوراً:</b>"
        )
        markup = types.InlineKeyboardMarkup(row_width=1)
        btn_pull = types.InlineKeyboardButton("📥 ابدأ سحب 20 فصلاً الآن (Pull)", callback_data="cb_opus_pull_now")
        btn_auto_refine = types.InlineKeyboardButton("🤖 صقل الدفعة آلياً بالذكاء الاصطناعي", callback_data="cb_opus_auto_refine")
        btn_audit_full = types.InlineKeyboardButton("📚 تدقيق شامل لكامل الرواية (500+ فصل)", callback_data="cb_opus_audit_full_prompt")
        btn_approve_push = types.InlineKeyboardButton("🚀 اعتماد ونشر الكل إلى بلوجر (Push)", callback_data="cb_opus_push_all")
        btn_status = types.InlineKeyboardButton("📊 تحديث حالة مجلدات الاستقبال", callback_data="cb_opus_status")
        markup.add(btn_pull, btn_auto_refine, btn_audit_full, btn_approve_push, btn_status)
        bot.reply_to(message, text, reply_markup=markup)

    @bot.message_handler(commands=['audit_novel', 'audit_full', 'full_audit'])
    def nsw_audit_full_cmd(message):
        """بدء التدقيق الشامل لكامل فصول الرواية (500+ فصل) آلياً على دفعات متتالية."""
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر مخصص للمشرف فقط.")
            return
        parts = message.text.strip().split(None, 2)
        novel_name = parts[1].strip() if len(parts) > 1 else "After Severing Ties"
        start_c = int(parts[2].strip()) if len(parts) > 2 and parts[2].strip().isdigit() else 1

        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(f"▶️ تأكيد بدء التدقيق الشامل ({novel_name})", callback_data=f"cb_opus_start_full:{novel_name}:{start_c}"),
            types.InlineKeyboardButton("❌ إلغاء", callback_data="cb_opus_status")
        )
        bot.reply_to(
            message,
            f"📚 <b>[منظومة التدقيق الشامل لكامل الرواية - 500+ فصل]:</b>\n\n"
            f"📖 <b>الرواية:</b> {novel_name}\n"
            f"🔢 <b>البدء من الفصل:</b> {start_c}\n\n"
            f"⚙️ <b>كيف تعمل المنظومة ذاتياً؟</b>\n"
            f"• تسحب الفصول تباعاً على دفعات (20 فصلاً لكل دفعة).\n"
            f"• تطبق الصقل الأدبي الفصيح، والتحقق من القاموس وضبط وسوم BBCode الملكية.\n"
            f"• توثق الفصول في مجلد <code>approved/</code> وترسل لك نسبة الإنجاز بعد كل دفعة.\n"
            f"• يمكنك إيقاف العملية في أي لحظة بأمان عبر الأمر: <code>/stop_audit</code>\n\n"
            f"هل تود إطلاق عملية التدقيق الشامل الآن؟",
            reply_markup=markup
        )

    @bot.message_handler(commands=['stop_audit', 'audit_stop'])
    def nsw_stop_audit_cmd(message):
        """إيقاف التدقيق الشامل الجاري بأمان."""
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر مخصص للمشرف فقط.")
            return
        import sync_opus_queue
        sync_opus_queue.request_stop_full_audit()
        bot.reply_to(message, "🛑 <b>تم إرسال إشارة إيقاف التدقيق الشامل.</b>\nستتوقف العملية بأمان عند نهاية الدفعة الحالية دون ضياع أي فصول تم تدقيقها.")

    @bot.message_handler(commands=['fix_dates', 'dates', 'fix_date', 'date_fix'])
    def nsw_fix_dates_cmd(message):
        """إصلاح وتنسيق تواريخ نشر فصول الرواية وفق نمط زمني ذكي."""
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر مخصص للمشرف فقط.")
            return
        markup = make_novel_selection_markup("cb_nvdate", include_all=False)
        bot.reply_to(
            message,
            "🗓️ <b>[منظومة إصلاح وتنسيق تواريخ النشر المجدولة]</b>\n\n"
            "أي رواية ترغب بإصلاح تاريخ فصولها؟\n"
            "اختر إحدى الروايات المسجلة على الموقع أدناه:",
            reply_markup=markup
        )

    @bot.message_handler(commands=['sync_blogger', 'sync_sheet', 'match_blogger'])
    def nsw_sync_blogger_cmd(message):
        """مطابقة وإصلاح بيانات Google Sheets من Blogger مباشرة (أمر ➔ تقرير ➔ اتخاذ قرار)."""
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر مخصص للمشرف فقط.")
            return
        parts = message.text.strip().split(None, 1)
        novel_name = parts[1].strip() if len(parts) > 1 else "After Severing Ties"
        chat_id = message.chat.id
        wait_msg = bot.reply_to(message, f"🔄 <b>جاري فحص ومطابقة بيانات الشيت مع مدونة بلوجر لرواية:</b> <code>{novel_name}</code>...")

        def _worker():
            try:
                res = nsw_healer_engine.sync_and_repair_sheet_from_blogger(novel_name)
                missing_items = res.get("missing_items", [])
                missing_nums = res.get("missing_in_sheet", [])
                
                report = (
                    f"📊 <b>[تقرير مطابقة الشيت مع مدونة بلوجر]:</b>\n"
                    f"📖 الرواية: <b>{novel_name}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"• فصول بلوجر الإجمالية: <b>{res.get('total_blogger', 0)}</b> فصل\n"
                    f"• فصول الشيت المسجلة: <b>{res.get('total_sheet', 0)}</b> فصل\n"
                    f"• فصول على بلوجر غير مسجلة بالشيت: <b>{len(missing_nums)}</b> فصل\n"
                    f"• تعارض في معرف المنشور (PostID): <b>{len(res.get('id_mismatches', []))}</b> فصل\n"
                )
                markup = None
                if missing_nums:
                    USER_SESSIONS[chat_id] = USER_SESSIONS.get(chat_id, {})
                    USER_SESSIONS[chat_id]["pending_sync_sheet"] = {
                        "novel_name": novel_name,
                        "missing_items": missing_items
                    }
                    sample = [str(x) for x in missing_nums[:15]]
                    report += f"⚠️ <b>أرقام الفصول غير المسجلة بالشيت:</b> {', '.join(sample)}\n\n"
                    report += "💡 <i>هذه الفصول موجودة على بلوجر ولكن تنقص في الشيت. هل ترغب بإدراجها في جدول الشيت الآن؟</i>"
                    markup = types.InlineKeyboardMarkup(row_width=1)
                    markup.add(
                        types.InlineKeyboardButton(f"📥 تحديث وإدراج الـ {len(missing_nums)} فصلاً في الشيت الآن", callback_data=f"cb_exec_sync_sheet:{novel_name}"),
                        types.InlineKeyboardButton("❌ إلغاء", callback_data="CANCEL_ACTION")
                    )
                else:
                    report += "\n✅ كافة فصول بلوجر مسجلة في الشيت بتطابق تام 100%!"

                bot.edit_message_text(report, chat_id, wait_msg.message_id, reply_markup=markup)
            except Exception as e:
                bot.edit_message_text(f"❌ خطأ أثناء مطابقة الشيت: {e}", chat_id, wait_msg.message_id)

        threading.Thread(target=_worker, daemon=True).start()

    @bot.message_handler(commands=['check_timeline', 'timeline_anomalies', 'audit_timeline'])
    def nsw_check_timeline_cmd(message):
        """كشف الاضطراب الزمني والتضارب في ترتيب تواريخ النشر."""
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر مخصص للمشرف فقط.")
            return
        parts = message.text.strip().split(None, 1)
        novel_name = parts[1].strip() if len(parts) > 1 else "After Severing Ties"
        chat_id = message.chat.id
        wait_msg = bot.reply_to(message, f"⏱️ <b>جاري فحص التسلسل الزمني لرواية:</b> <code>{novel_name}</code>...")

        def _worker():
            try:
                res = nsw_healer_engine.detect_timeline_anomalies(novel_name)
                anomalies = res.get("anomalies", [])
                report = (
                    f"⏱️ <b>[تقرير رصد الاضطراب الزمني في الجدولة]:</b>\n"
                    f"📖 الرواية: <b>{novel_name}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"• إجمالي الفصول المفحوصة: <b>{res.get('total_chapters', 0)}</b> فصل\n"
                    f"• حالات الاضطراب المعكوسة: <b>{len(anomalies)}</b> حالة\n"
                )
                markup = None
                if anomalies:
                    report += "⚠️ <b>أبرز حالات التضارب المكتشفة:</b>\n"
                    for a in anomalies[:5]:
                        report += f"• الفصل <b>{a['next_chapter']}</b> يسبق الفصل <b>{a['prev_chapter']}</b> بفارق {a['time_difference_hours']} ساعة!\n"
                    report += "\n💡 <i>هل ترغب بإعادة تنسيق وضبط الجدولة وفق نمط زمني ذكي؟</i>"
                    markup = types.InlineKeyboardMarkup(row_width=1)
                    markup.add(
                        types.InlineKeyboardButton("🗓️ إصلاح وتنسيق الجدولة الآن (/fix_dates)", callback_data="cb_fix_dates_start"),
                        types.InlineKeyboardButton("❌ إغلاق", callback_data="CANCEL_ACTION")
                    )
                else:
                    report += "\n✅ الجدول الزمني متسق ومنتظم تصاعدياً بنسبة 100%!"

                bot.edit_message_text(report, chat_id, wait_msg.message_id, reply_markup=markup)
            except Exception as e:
                bot.edit_message_text(f"❌ خطأ أثناء فحص التسلسل الزمني: {e}", chat_id, wait_msg.message_id)

        threading.Thread(target=_worker, daemon=True).start()

    @bot.message_handler(commands=['purge_duplicates', 'check_duplicates', 'clean_duplicates'])
    def nsw_purge_duplicates_cmd(message):
        """كشف وتطهير الفصول المكررة على بلوجر والشيت (أمر ➔ تقرير ➔ اتخاذ قرار)."""
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر مخصص للمشرف فقط.")
            return
        parts = message.text.strip().split(None, 1)
        novel_name = parts[1].strip() if len(parts) > 1 else "After Severing Ties"
        chat_id = message.chat.id
        wait_msg = bot.reply_to(message, f"🧹 <b>جاري فحص ورصد الفصول المكررة لرواية:</b> <code>{novel_name}</code>...")

        def _worker():
            try:
                res = nsw_healer_engine.detect_and_purge_duplicate_posts(novel_name, dry_run=True)
                dups_cnt = res.get("duplicates_count", 0)
                to_purge = res.get("to_purge", [])
                
                report = (
                    f"🧹 <b>[تقرير رصد الفصول المكررة - معاينة]:</b>\n"
                    f"📖 الرواية: <b>{novel_name}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"• فصول تحتوي على تكرار: <b>{dups_cnt}</b> فصول\n"
                    f"• التدوينات الزائدة المستهدفة للحذف: <b>{len(to_purge)}</b> تدوينة\n"
                )
                markup = None
                if to_purge:
                    USER_SESSIONS[chat_id] = USER_SESSIONS.get(chat_id, {})
                    USER_SESSIONS[chat_id]["pending_purge_dups"] = {
                        "novel_name": novel_name,
                        "to_purge": to_purge
                    }
                    report += "📋 <b>تفاصيل التدوينات المكررة المرشحة للحذف:</b>\n"
                    for p in to_purge[:5]:
                        report += f"• الفصل <b>{p['chapter_number']}</b> [PostID: <code>{p['post_id']}</code>] بتاريخ ({p['date_raw'][:10]})\n"
                    report += "\n⚠️ <i>هل ترغب بتأكيد حذف وتطهير هذه التدوينات المكررة من مدونة بلوجر الآن؟</i>"
                    markup = types.InlineKeyboardMarkup(row_width=1)
                    markup.add(
                        types.InlineKeyboardButton(f"🗑️ تأكيد تطهير وحذف الـ {len(to_purge)} تدوينات المكررة الآن", callback_data=f"cb_exec_purge_dups:{novel_name}"),
                        types.InlineKeyboardButton("❌ إلغاء العملية", callback_data="CANCEL_ACTION")
                    )
                else:
                    report += "\n🛡️ لا توجد أي تدوينات مكررة على الإطلاق، النظام خلوٌ تام من أي تكرار!"

                bot.edit_message_text(report, chat_id, wait_msg.message_id, reply_markup=markup)
            except Exception as e:
                bot.edit_message_text(f"❌ خطأ أثناء فحص الفصول المكررة: {e}", chat_id, wait_msg.message_id)

        threading.Thread(target=_worker, daemon=True).start()

    @bot.message_handler(commands=['nsw_nav', 'nav', 'repair_nav', 'nav_repair'])
    def nsw_nav_cmd(message):
        """صيانة وربط أزرار التنقل (السابق/التالي/الفهرس) لكافة فصول الرواية المنشورة والمجدولة."""
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر للمشرف فقط.")
            return
        parts = message.text.strip().split(None, 2)
        if len(parts) <= 1:
            markup = make_novel_selection_markup("cb_nvnav", include_all=True)
            bot.reply_to(
                message,
                "🔗 <b>[صيانة وربط أزرار التنقل]</b>\n\n"
                "أي رواية ترغب بإصلاح روابط أزرار التنقل (السابق/التالي/الفهرس) لفصولها؟\n"
                "اختر إحدى الروايات أدناه:",
                reply_markup=markup
            )
            return
        novel_filter = parts[1].strip()
        start_chap = int(parts[2].strip()) if len(parts) > 2 and parts[2].strip().isdigit() else 1
        _run_nav_repair(message.chat.id, novel_filter, start_chap)

    @bot.message_handler(commands=['nsw_help', 'nsw'])
    def nsw_help_cmd(message):
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر للمشرف فقط.")
            return
        text = (
            "📋 <b>أوامر نظام NSW الشامل للنشر والترجمة:</b>\n\n"
            "🛡️ <code>/repair [رواية]</code> — <b>الإصلاح الشامل الكامل</b> (سد الفجوات + استصلاح المبتورات + صيانة أزرار التنقل)\n"
            "🗓️ <code>/fix_dates</code> — <b>إصلاح وتنسيق تواريخ النشر</b> المجدولة بذكاء وفق نمط زمني\n"
            "🔄 <code>/sync_blogger [رواية]</code> — <b>مطابقة فصول بلوجر وتحديث جدول الشيت</b>\n"
            "🧹 <code>/purge_duplicates [رواية]</code> — <b>كشف وتطهير الفصول المكررة</b> من بلوجر والشيت\n"
            "⏱️ <code>/check_timeline [رواية]</code> — <b>كشف الاضطراب والتضارب الزمني</b> في الجدولة\n"
            "📥 <code>/export [رواية] [نطاق]</code> — <b>تصدير فصول المدونة كملف TXT نظيف</b>\n"
            "🎭 <code>/stage [رواية]</code> — تجهيز دفعة الـ 20 فصلاً لصقل Claude Opus\n"
            "📖 <code>/audit_novel [رواية]</code> — تشغيل التدقيق الأدبي الشامل لرواية كاملة\n"
            "⏹️ <code>/stop_audit</code> — إيقاف التدقيق الشامل للرواية الجاري\n"
            "🔗 <code>/nav [رواية] [فصل_البداية]</code> — <b>صيانة وربط أزرار التنقل</b> (السابق/التالي/الفهرس)\n"
            "🧩 <code>/gaps [رواية]</code> — فحص وسد الفصول المفقودة والمسودات\n"
            "🩹 <code>/heal [رواية]</code> — استصلاح الفصول المبتورة أو الناقصة\n"
            "📊 <code>/status</code> — فحص حالة المنظومة والمهام اللحظية\n"
            "🎯 <code>/fix [رواية] [رقم]</code> — إصلاح أو ترجمة فصل فردي محدد\n"
            "🚀 <code>/publish [رواية] [فصول]</code> — نشر فصول مخصصة\n"
            "👑 <code>/admin</code> — لوحة تحكم المشرف وإدارة الوصول\n"
            "🛑 <code>/stop</code> — إيقاف فوري طارئ لكافة مهام المحرك\n\n"
            "💡 <i>جميع الأوامر متاحة أيضاً بأزرار تفاعلية مباشرة عبر: /menu</i>"
        )
        bot.reply_to(message, text)

    @bot.message_handler(commands=['nsw_audit', 'audit'])
    def nsw_audit_cmd(message):
        """طلب فحص شامل لمدونة بلوجر والجداول عند الطلب فقط مع تقرير تيليجرام."""
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر للمشرف فقط.")
            return
        parts = message.text.strip().split(None, 1)
        novel_filter = parts[1].strip() if len(parts) > 1 else "After Severing Ties"
        bot.reply_to(message, f"🔍 <b>جاري إجراء الفحص الشامل لمدونة Blogger والجداول لرواية '{novel_filter}' بناءً على طلبك...</b>\nسيصلك التقرير فور الاكتمال.")
        def _run():
            try:
                import requests
                from nsw_healer_engine import PUBLISH_WEBAPP_URL
                payload = {
                    "action": "runFullAudit",
                    "novelName": novel_filter,
                    "chatId": str(message.chat.id),
                    "sendTelegram": True
                }
                requests.post(PUBLISH_WEBAPP_URL, json=payload, timeout=90)
            except Exception as e:
                bot.send_message(message.chat.id, f"❌ خطأ أثناء الفحص: {e}")
        threading.Thread(target=_run, daemon=True).start()

    @bot.message_handler(commands=['nsw_weekly', 'weekly'])
    def nsw_weekly_cmd(message):
        """تفعيل الفحص الأسبوعي التلقائي (كل إثنين الساعة 09:00 ص)"""
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر للمشرف فقط.")
            return
        try:
            import requests
            from nsw_healer_engine import PUBLISH_WEBAPP_URL
            payload = {"action": "setupWeeklyAuditSchedule", "chatId": str(message.chat.id)}
            res = requests.post(PUBLISH_WEBAPP_URL, json=payload, timeout=30).json()
            if res.get("status") == "success":
                bot.reply_to(message, "🗓️ <b>تم تفعيل جدول الفحص الأسبوعي الدوري بنجاح!</b>\n⏰ <b>الموعد:</b> كل يوم إثنين الساعة 09:00 ص بتوقيت بغداد.\n🔍 سيتم فحص المدونة والجداول مرة واحدة أسبوعياً دون أي تشغيل تلقائي مزعج.")
            else:
                bot.reply_to(message, f"⚠️ تعذر تفعيل الجدول: {res.get('message')}")
        except Exception as e:
            bot.reply_to(message, f"❌ خطأ: {e}")

    @bot.message_handler(commands=['nsw_stop', 'stop'])
    def nsw_stop_cmd(message):
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر للمشرف فقط.")
            return
        try:
            import nsw_healer_engine
            nsw_healer_engine.request_stop()
            nsw_healer_engine.set_engine_state(
                "🛑 متوقف بأمر المشرف",
                "إيقاف فوري",
                "تم إيقاف كافة العمليات الجارية"
            )
            bot.reply_to(message, (
                "🛑 <b>تم تفعيل أمر الإيقاف الفوري بنجاح!</b>\n\n"
                "⚡ توقف المحرك فوراً وتم إلغاء أي سحب أو ترجمة أو نشر جاري.\n"
                "▶️ لاستئناف العمل يمكنك إرسال: <code>/nsw_gaps</code> أو <code>/nsw_fix</code> في أي وقت."
            ))
        except Exception as e:
            bot.reply_to(message, f"❌ خطأ: {e}")

    @bot.message_handler(func=lambda msg: True)
    def handle_incoming_link(message):
        if not is_user_authorized(message):
            bot.reply_to(message, "⛔ <b>غير مصرح لك بالاستخدام.</b>\nتواصل مع المشرف لإضافتك.")
            return

        user_text = message.text.strip()
        cleaned_text = user_text.lower().strip()

        # الكلمات العربية والإنجليزية الترحيبية والتشغيلية
        start_words = ['ابدأ', 'ابدا', 'بدء', 'تشغيل', 'مرحبا', 'أهلاً', 'اهلا', 'start', 'help', 'مساعده', 'مساعدة']
        if any(word == cleaned_text or cleaned_text.startswith(word) for word in start_words):
            send_welcome(message)
            return

        chat_id = message.chat.id

        session_state = USER_SESSIONS.get(chat_id, {}).get("state")
        if session_state and session_state.startswith("AWAITING_EXPORT_RANGE:"):
            target_novel = session_state.replace("AWAITING_EXPORT_RANGE:", "").strip() or "After Severing Ties"
            USER_SESSIONS.get(chat_id, {}).pop("state", None)
            _run_export_chapters_task(chat_id, target_novel, user_text.strip())
            return

        if session_state == "WAITING_FIX_DATE_PATTERN":
            novel_name = USER_SESSIONS.get(chat_id, {}).get("novel_name", "After Severing Ties")
            import nsw_healer_engine
            pattern = nsw_healer_engine.parse_schedule_pattern_input(user_text)
            if not pattern.get("success"):
                bot.reply_to(
                    message,
                    f"⚠️ <b>تعذر استنتاج نمط التاريخ:</b> {pattern.get('error')}\n\n"
                    "يرجى كتابة التاريخ بهذا الشكل مثلاً:\n"
                    "<code>الفصل 400 2027/1/30 الساعة 9:00\n"
                    "الفصل 401 2027/1/30 الساعة 16:00</code>\n\n"
                    "أو اضغط /menu للإلغاء والعودة للقائمة."
                )
                return

            wait_msg = bot.reply_to(message, f"⏳ <b>جاري فحص جدول فصول '{novel_name}' ومقارنة المواعيد (Dry Run)...</b>")

            def _preview_worker():
                try:
                    preview = nsw_healer_engine.preview_and_repair_novel_dates(novel_name, pattern, dry_run=True)
                    if not preview.get("success"):
                        bot.edit_message_text(f"⚠️ خطأ أثناء الفحص: {preview.get('error')}", chat_id, wait_msg.message_id)
                        USER_SESSIONS.get(chat_id, {}).pop("state", None)
                        return

                    USER_SESSIONS[chat_id]["pending_date_fix"] = {
                        "novel_name": novel_name,
                        "pattern": pattern
                    }
                    USER_SESSIONS[chat_id].pop("state", None)

                    total_scanned = preview.get("total_scanned", 0)
                    to_update_count = preview.get("to_update_count", 0)
                    skipped_count = preview.get("skipped_count", 0)
                    start_ch = pattern.get("start_chapter")
                    slots = ", ".join(pattern.get("time_slots", []))

                    samples_text = ""
                    if preview.get("to_update_sample"):
                        samples_text += "\n\n🔄 <b>أمثلة على الفصول التي سيتم تعديل موعدها:</b>\n"
                        for it in preview.get("to_update_sample")[:4]:
                            samples_text += f"• الفصل {it['chapter_number']}: <code>{it['current_date']}</code> ➔ <code>{it['target_date']}</code>\n"

                    if preview.get("skipped_sample"):
                        samples_text += "\n⭐ <b>أمثلة على فصول مطابقة مسبقاً (تم استثناؤها):</b>\n"
                        for it in preview.get("skipped_sample")[:3]:
                            samples_text += f"• الفصل {it['chapter_number']}: مطابق لموعد <code>{it['target_date']}</code>\n"

                    summary = (
                        f"📋 <b>[نتيجة المعاينة المسبقة لإصلاح تواريخ النشر]:</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"📖 <b>الرواية:</b> {novel_name}\n"
                        f"🔢 <b>الفصل البدائي:</b> {start_ch}\n"
                        f"⏰ <b>المواعيد اليومية:</b> {slots} ({pattern.get('slots_per_day')} فصول/يوم)\n"
                        f"📦 <b>إجمالي الفصول المشمولة:</b> {total_scanned} فصلاً\n"
                        f"⭐ <b>فصول مطابقة مسبقاً (مستثناة):</b> {skipped_count} فصلاً\n"
                        f"🔄 <b>فصول سيتم تعديل جدولتها:</b> {to_update_count} فصلاً"
                        f"{samples_text}\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                    )

                    if to_update_count == 0:
                        summary += "🎉 <b>كافة الفصول مطابقة بالفعل للنمط المطلوب! لا يوجد أي فصل بحاجة لتعديل.</b>"
                        markup = None
                    else:
                        summary += "⚠️ <b>هل ترغب باعتماد هذا النمط وتحديث الجداول وبلوجر الآن؟</b>"
                        markup = types.InlineKeyboardMarkup(row_width=2)
                        markup.add(
                            types.InlineKeyboardButton("✅ نعم، طبّق التعديل الآن", callback_data="cb_confirm_date_fix"),
                            types.InlineKeyboardButton("❌ إلغاء", callback_data="CANCEL_ACTION")
                        )

                    sent_ok = False
                    for attempt in range(3):
                        try:
                            bot.edit_message_text(summary, chat_id, wait_msg.message_id, reply_markup=markup)
                            sent_ok = True
                            break
                        except Exception as e_send:
                            time.sleep(2)
                    if not sent_ok:
                        bot.send_message(chat_id, summary, reply_markup=markup)
                except Exception as ex:
                    try:
                        bot.edit_message_text(f"❌ حدث خطأ أثناء المعاينة: {ex}", chat_id, wait_msg.message_id)
                    except Exception:
                        bot.send_message(chat_id, f"❌ حدث خطأ أثناء المعاينة: {ex}")
                    USER_SESSIONS.get(chat_id, {}).pop("state", None)

            threading.Thread(target=_preview_worker, daemon=True).start()
            return

        # فحص إذا كان المستخدم يكتب نصاً عادياً للبحث عن فيلم / مسلسل
        if not user_text.startswith("http://") and not user_text.startswith("https://"):
            status_msg = bot.reply_to(message, f"🔎 <b>جاري البحث والتعرف على:</b> <i>{user_text}</i>...")
            def _text_rec_task():
                res = cinema_engine.analyze_cinema_content(query_text=user_text)
                _send_cinema_result(chat_id, res, status_msg.message_id)
            threading.Thread(target=_text_rec_task, daemon=True).start()
            return

        USER_SESSIONS[chat_id] = {"url": user_text}

        # تحديد نوع الرابط تلقائياً
        if any(domain in user_text.lower() for domain in ["youtube.com", "youtu.be", "tiktok.com", "x.com", "twitter.com", "bilibili", "instagram"]):
            # رابط وسائط / فيديو
            markup = types.InlineKeyboardMarkup(row_width=2)
            btn_mp4 = types.InlineKeyboardButton("🎬 فيديو MP4 كامل", callback_data="media_mp4")
            btn_mp3 = types.InlineKeyboardButton("🎵 صوت فقط MP3", callback_data="media_mp3")
            btn_split = types.InlineKeyboardButton("✂️ تجزئة وتنزيل تلقائي", callback_data="media_split")
            btn_cinema = types.InlineKeyboardButton("🔍 كشف الفيلم بالذكاء الاصطناعي", callback_data="media_cinema_detect")
            markup.add(btn_mp4, btn_mp3)
            markup.add(btn_split, btn_cinema)
            
            bot.reply_to(
                message,
                f"🎬 <b>تم التعرف على رابط فيديو!</b>\nالرابط: <code>{user_text}</code>\n\nاختر الإجراء المطلوب:",
                reply_markup=markup
            )
        else:
            # رابط رواية وموقع ويب
            markup = types.InlineKeyboardMarkup(row_width=2)
            btn_ch_50 = types.InlineKeyboardButton("📚 سحب فصول (1 إلى 50)", callback_data="novel_1_50")
            btn_ch_100 = types.InlineKeyboardButton("📚 سحب فصول (1 إلى 100)", callback_data="novel_1_100")
            btn_ch_all = types.InlineKeyboardButton("🚀 سحب كل الفصول المتاحة", callback_data="novel_all")
            markup.add(btn_ch_50, btn_ch_100, btn_ch_all)

            bot.reply_to(
                message,
                f"📚 <b>تم التعرف على رابط رواية / فهرس!</b>\nالرابط: <code>{user_text}</code>\n\nاختر نطاق الفصول المطلوب سحبها في الخلفية:",
                reply_markup=markup
            )

    @bot.callback_query_handler(func=lambda call: True)
    def handle_callbacks(call):
        chat_id = call.message.chat.id
        if not is_user_authorized(call):
            bot.answer_callback_query(call.id, "غير مصرح.")
            return

        session_data = USER_SESSIONS.get(chat_id, {})
        target_url = session_data.get("url")
        data = call.data
        bot.answer_callback_query(call.id, "جاري المعالجة...")

        # ----------------------------------------------------
        # معالجة أزرار القائمة الرئيسية لمنظومة NSW
        # ----------------------------------------------------
        if data == "cb_fix_dates_start":
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            markup = make_novel_selection_markup("cb_nvdate", include_all=False)
            bot.send_message(
                chat_id,
                "🗓️ <b>[منظومة إصلاح وتنسيق تواريخ النشر المجدولة]</b>\n\n"
                "أي رواية ترغب بإصلاح تاريخ فصولها؟\n"
                "اختر إحدى الروايات المسجلة على الموقع أدناه:",
                reply_markup=markup
            )
            return

        elif data.startswith("cb_nvdate_"):
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            idx_str = data.replace("cb_nvdate_", "")
            novel_name = get_novel_from_catalog_idx(idx_str) or "After Severing Ties"
            USER_SESSIONS[chat_id] = {
                "state": "WAITING_FIX_DATE_PATTERN",
                "novel_name": novel_name
            }
            prompt_text = (
                f"📖 <b>الرواية المختارة:</b> <b>{novel_name}</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"من فضلك اكتب تاريخ أول فصل في أي تاريخ وبأي نمط ترغب به.\n\n"
                f"<b>مثال:</b>\n"
                f"<code>الفصل 400 2027/1/30 الساعة 9:00\n"
                f"الفصل 401 2027/1/30 الساعة 16:00</code>\n\n"
                f"💡 <i>المحرك سيستنتج أوقات النشر اليومية وسيطبقها على كافة الفصول التالية، مع استثناء أي فصل تاريخه مضبوط مسبقاً دون إرسال طلب تعديل له!</i>"
            )
            cancel_markup = types.InlineKeyboardMarkup()
            cancel_markup.add(types.InlineKeyboardButton("❌ إلغاء العملية", callback_data="CANCEL_ACTION"))
            bot.send_message(chat_id, prompt_text, reply_markup=cancel_markup)
            return

        elif data == "cb_confirm_date_fix":
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            pending = session_data.get("pending_date_fix")
            if not pending:
                bot.send_message(chat_id, "⚠️ انتهت صلاحية الجلسة أو تم إلغاؤها.")
                return
            n_name = pending["novel_name"]
            pat = pending["pattern"]
            bot.send_message(chat_id, f"🚀 <b>جاري تطبيق تعديل تواريخ النشر لرواية '{n_name}' على Google Sheet وبلوجر...</b>\nسيصلك تقرير تفصيلي فور الانتهاء.")
            def _run_date_fix():
                try:
                    import nsw_healer_engine
                    nsw_healer_engine.preview_and_repair_novel_dates(n_name, pat, dry_run=False)
                except Exception as ex:
                    bot.send_message(chat_id, f"❌ خطأ أثناء تطبيق تعديل التواريخ: {ex}")
            threading.Thread(target=_run_date_fix, daemon=True).start()
            USER_SESSIONS.get(chat_id, {}).pop("pending_date_fix", None)
            return

        elif data == "cb_nsw_repair":
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            markup = make_novel_selection_markup("cb_nvrep", include_all=True)
            bot.send_message(
                chat_id,
                "🛡️ <b>[الإصلاح الشامل الكامل]</b>\n\n"
                "أي رواية ترغب بإجراء دورة الإصلاح والصيانة الشاملة الكاملة لها؟\n"
                "اختر إحدى الروايات أدناه:",
                reply_markup=markup
            )
            return

        elif data.startswith("cb_nvrep_"):
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            idx_str = data.replace("cb_nvrep_", "")
            target_novel = get_novel_from_catalog_idx(idx_str)
            _run_full_repair(chat_id, target_novel)
            return

        elif data == "cb_nsw_status":
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            try:
                import nsw_healer_engine
                rep = nsw_healer_engine.get_realtime_engine_report()
                bot.send_message(chat_id, rep)
            except Exception as e:
                bot.send_message(chat_id, f"⚠️ تعذر جلب التقرير: {e}")
            return

        elif data == "cb_nsw_gaps":
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            markup = make_novel_selection_markup("cb_nvgap", include_all=True)
            bot.send_message(
                chat_id,
                "🧩 <b>[فحص وسد الفجوات الترقيمية]</b>\n\n"
                "أي رواية ترغب بفحص وسد فجواتها الترقيمية؟\n"
                "اختر إحدى الروايات أدناه:",
                reply_markup=markup
            )
            return

        elif data.startswith("cb_nvgap_"):
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            idx_str = data.replace("cb_nvgap_", "")
            target_novel = get_novel_from_catalog_idx(idx_str)
            _run_gaps_repair(chat_id, target_novel)
            return

        elif data == "cb_nsw_heal":
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            bot.send_message(chat_id, "🩹 <b>جاري فحص واستصلاح الفصول المبتورة على Blogger...</b>")
            def _run_heal():
                try:
                    import nsw_healer_engine
                    nsw_healer_engine.run_full_auto_heal("After Severing Ties")
                except Exception as e:
                    bot.send_message(chat_id, f"❌ خطأ أثناء الاستصلاح: {e}")
            threading.Thread(target=_run_heal, daemon=True).start()
            return

        elif data == "cb_nsw_nav":
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            markup = make_novel_selection_markup("cb_nvnav", include_all=True)
            bot.send_message(
                chat_id,
                "🔗 <b>[صيانة أزرار التنقل]</b>\n\n"
                "أي رواية ترغب بإصلاح روابط أزرار التنقل (السابق/التالي/الفهرس) لفصولها؟\n"
                "اختر إحدى الروايات أدناه:",
                reply_markup=markup
            )
            return

        elif data.startswith("cb_nvnav_"):
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            idx_str = data.replace("cb_nvnav_", "")
            target_novel = get_novel_from_catalog_idx(idx_str)
            _run_nav_repair(chat_id, target_novel, start_chap=1)
            return

        elif data == "cb_nsw_stage" or data == "cb_opus_status":
            try:
                import sync_opus_queue
                p_cnt = len(list(sync_opus_queue.PENDING_DIR.glob("chapter_*.txt")))
                a_cnt = len(list(sync_opus_queue.APPROVED_DIR.glob("chapter_*.txt")))
                pub_cnt = len(list(sync_opus_queue.PUBLISHED_DIR.glob("chapter_*.txt")))
                text = (
                    f"🎭 <b>[لوحة طابور صقل فصول Claude Opus]:</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"⏳ <b>في الانتظار (Pending):</b> <b>{p_cnt}</b> فصلاً\n"
                    f"✍️ <b>معتمدة للرفع (Approved):</b> <b>{a_cnt}</b> فصلاً\n"
                    f"✅ <b>منشورة وموثقة (Published):</b> <b>{pub_cnt}</b> فصلاً\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"👇 اضغط الزر أدناه لبدء السحب فوراً:"
                )
                m = types.InlineKeyboardMarkup(row_width=1)
                m.add(
                    types.InlineKeyboardButton("📥 ابدأ سحب 20 فصلاً الآن (Pull)", callback_data="cb_opus_pull_now"),
                    types.InlineKeyboardButton("🤖 صقل الدفعة آلياً بالذكاء الاصطناعي", callback_data="cb_opus_auto_refine"),
                    types.InlineKeyboardButton("📚 تدقيق شامل لكامل الرواية (500+ فصل)", callback_data="cb_opus_audit_full_prompt"),
                    types.InlineKeyboardButton("🚀 اعتماد ونشر الكل إلى بلوجر (Push)", callback_data="cb_opus_push_all")
                )
                bot.send_message(chat_id, text, reply_markup=m)
            except Exception as e:
                bot.send_message(chat_id, f"❌ خطأ: {e}")
            return

        elif data == "cb_opus_audit_full_prompt":
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            m = types.InlineKeyboardMarkup(row_width=1)
            m.add(
                types.InlineKeyboardButton("▶️ نعم، ابدأ تدقيق كامل الرواية (500+ فصل)", callback_data="cb_opus_start_full:After Severing Ties:1"),
                types.InlineKeyboardButton("❌ إلغاء", callback_data="cb_opus_status")
            )
            bot.send_message(
                chat_id,
                "📚 <b>[تأكيد إطلاق التدقيق الشامل لكامل الرواية]:</b>\n\n"
                "• الرواية: <b>After Severing Ties</b>\n"
                "• سيتم معالجة الفصول آلياً في الخلفية على دفعات (20 فصلاً في كل دفعة).\n"
                "• صقل أدبي فصيح + التحقق من القاموس وضبط وسوم BBCode.\n"
                "• سيصلك إشعار لحظي بعد كل دفعة مع نسبة التقدم.\n"
                "• يمكنك إيقاف العملية في أي وقت عبر <code>/stop_audit</code>.\n\n"
                "اضغط تأكيد للبدء فوراً:",
                reply_markup=m
            )
            return

        elif data.startswith("cb_opus_start_full"):
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            parts = data.split(":")
            novel_name = parts[1] if len(parts) > 1 else "After Severing Ties"
            start_c = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
            bot.send_message(chat_id, f"🚀 <b>تم إطلاق التدقيق الشامل لرواية '{novel_name}' بدءاً من الفصل {start_c}...</b>\nستعمل المنظومة في الخلفية وتوافيك بالتقدم بعد كل دفعة.")
            def _full_audit_thread():
                try:
                    import sync_opus_queue
                    sync_opus_queue.cmd_audit_full_novel(novel_name=novel_name, start_chapter=start_c)
                except Exception as e:
                    bot.send_message(chat_id, f"❌ خطأ أثناء التدقيق الشامل: {e}")
            threading.Thread(target=_full_audit_thread, daemon=True).start()
            return

        elif data == "cb_opus_auto_refine":
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            bot.send_message(chat_id, "🤖 <b>جاري بدء الصقل والتدقيق الأدبي الآلي للدفعة في الخلفية...</b>\nسيصلك إشعار فوري عند اكتمال التدقيق مع زر النشر المباشر.")
            def _refine_thread():
                try:
                    import sync_opus_queue
                    sync_opus_queue.cmd_auto_refine_and_notify(limit=20, novel_name="After Severing Ties")
                except Exception as e:
                    bot.send_message(chat_id, f"❌ خطأ أثناء الصقل الآلي: {e}")
            threading.Thread(target=_refine_thread, daemon=True).start()
            return

        elif data == "cb_opus_pull_now":
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            bot.send_message(chat_id, "⏳ <b>جاري سحب وتجهيز دفعة 20 فصلاً في مجلد pending...</b>")
            def _pull_thread():
                try:
                    import sync_opus_queue
                    sync_opus_queue.cmd_pull(limit=20, novel_name="After Severing Ties")
                    p_files = sorted(list(sync_opus_queue.PENDING_DIR.glob("chapter_*.txt")), key=lambda p: int(re.search(r'\d+', p.name).group(0)) if re.search(r'\d+', p.name) else 0)
                    ch_nums = [re.search(r'\d+', f.name).group(0) for f in p_files if re.search(r'\d+', f.name)]
                    msg = (
                        f"🎉 <b>[تم بنجاح سحب وتفريغ {len(p_files)} فصلاً في مجلد Pending!]</b> 🚀\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🔢 <b>الفصول الجاهزة:</b> {', '.join(ch_nums[:15])}{'...' if len(ch_nums) > 15 else ''}\n"
                        f"📂 <b>المجلد على حاسوبك:</b> <code>opus_staging/pending/</code>\n\n"
                        f"💬 <b>الخطوة التالية (اختر ما يناسبك):</b>\n"
                        f"1️⃣ إما أن تصقلها بنفسك عبر Claude في Antigravity.\n"
                        f"2️⃣ أو تضغط زر «صقل الدفعة آلياً» أدناه لتتولى المنظومة صقلها وإرسال إشعار الاعتماد.\n\n"
                        f"وبعد الانتهاء، اضغط الزر أدناه لاعتمادها ونشرها مباشرة في بلوجر والشيت:"
                    )
                    m = types.InlineKeyboardMarkup(row_width=1)
                    m.add(
                        types.InlineKeyboardButton("🤖 صقل الدفعة آلياً الآن", callback_data="cb_opus_auto_refine"),
                        types.InlineKeyboardButton("✍️ اعتماد كافة الفصول المصقولة", callback_data="cb_opus_approve_all"),
                        types.InlineKeyboardButton("🚀 رفع ونشر الكل إلى بلوجر والشيت (Push)", callback_data="cb_opus_push_all")
                    )
                    bot.send_message(chat_id, msg, reply_markup=m)
                except Exception as e:
                    bot.send_message(chat_id, f"❌ خطأ أثناء السحب: {e}")
            threading.Thread(target=_pull_thread, daemon=True).start()
            return

        elif data == "cb_opus_approve_all":
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            try:
                import sync_opus_queue
                cnt = sync_opus_queue.cmd_approve_all()
                msg = (
                    f"⭐ <b>تم اعتماد {cnt} فصول ونقلها إلى مجلد Approved بنجاح!</b>\n"
                    f"الفصول الآن جاهزة للرفع إلى مدونة بلوجر والتحديث في الشيت بضغطة زر واحدة:"
                )
                m = types.InlineKeyboardMarkup()
                m.add(types.InlineKeyboardButton("🚀 رفع ونشر الكل إلى بلوجر الآن (Push)", callback_data="cb_opus_push_all"))
                bot.send_message(chat_id, msg, reply_markup=m)
            except Exception as e:
                bot.send_message(chat_id, f"❌ خطأ: {e}")
            return

        elif data == "cb_opus_push_all":
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            bot.send_message(chat_id, "🚀 <b>جاري نشر ورفع الفصول المعتمدة إلى مدونة بلوجر وتحديث الجداول...</b>")
            def _push_thread():
                try:
                    import sync_opus_queue
                    sync_opus_queue.cmd_push(novel_name="After Severing Ties")
                    bot.send_message(chat_id, "🎉 <b>تم بنجاح رفع ونشر كافة الفصول المصقولة إلى Blogger ومزامنة قواعد البيانات!</b>")
                except Exception as e:
                    bot.send_message(chat_id, f"❌ خطأ أثناء النشر: {e}")
            threading.Thread(target=_push_thread, daemon=True).start()
            return

        elif data == "cb_nsw_stop":
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            try:
                import nsw_healer_engine
                nsw_healer_engine.request_stop()
                nsw_healer_engine.set_engine_state("🛑 متوقف بأمر المشرف", "إيقاف فوري", "تم إيقاف العمليات")
                bot.send_message(chat_id, "🛑 <b>تم تفعيل أمر الإيقاف الفوري بنجاح!</b>")
            except Exception as e:
                bot.send_message(chat_id, f"❌ خطأ: {e}")
            return

        elif data in ["TRIGGER_HEAL_GAPS", "heal_truncated_now"]:
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            conf_markup = types.InlineKeyboardMarkup(row_width=2)
            btn_yes = types.InlineKeyboardButton("✅ نعم، ابدأ الإصلاح الشامل", callback_data="CONFIRM_HEAL_GAPS")
            btn_no = types.InlineKeyboardButton("❌ إلغاء", callback_data="CANCEL_ACTION")
            conf_markup.add(btn_yes, btn_no)
            bot.send_message(
                chat_id,
                "⚠️ <b>تأكيد تشغيل الإصلاح الشامل:</b>\n"
                "سيقوم المحرك بسد الفجوات المفقودة بجدولة زمنية دقيقة، واستصلاح المبتورات، وصيانة أزرار التنقل.\n\n"
                "هل أنت متأكد من رغبتك بالبدء الآن؟",
                reply_markup=conf_markup
            )
            return

        elif data == "CONFIRM_HEAL_GAPS":
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            _run_full_repair(chat_id, None)
            return

        elif data == "cb_sync_blogger_start":
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            nsw_sync_blogger_cmd(call.message)
            return

        elif data == "cb_purge_dups_start":
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            nsw_purge_duplicates_cmd(call.message)
            return

        elif data == "cb_check_timeline_start":
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            nsw_check_timeline_cmd(call.message)
            return

        elif data == "cb_export_chapters_start":
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            markup = make_novel_selection_markup("cb_nvexport", include_all=False)
            bot.send_message(
                chat_id,
                "📥 <b>[تصدير فصول من مدونة بلوجر إلى ملف TXT]</b>\n\n"
                "اختر الرواية أدناه، أو أرسل الأمر مباشرة بالصيغة:\n"
                "<code>/export After Severing Ties 400-450</code>\n"
                "أو لتصدير الرواية الافتراضية:\n"
                "<code>/export 490-500</code>",
                reply_markup=markup
            )
            return

        elif data.startswith("cb_nvexport_"):
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            idx_str = data.replace("cb_nvexport_", "")
            target_novel = get_novel_from_catalog_idx(idx_str) or "After Severing Ties"
            USER_SESSIONS[chat_id] = USER_SESSIONS.get(chat_id, {})
            USER_SESSIONS[chat_id]["state"] = f"AWAITING_EXPORT_RANGE:{target_novel}"
            bot.send_message(
                chat_id,
                f"📖 <b>الرواية المختارة:</b> <code>{target_novel}</code>\n\n"
                "أرسل الآن نطاق الفصول المطلوب تصديرها (مثال: <code>400-450</code> أو <code>490, 492, 495</code>):"
            )
            return

        elif data.startswith("cb_exec_sync_sheet:"):
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            novel_name = data.replace("cb_exec_sync_sheet:", "").strip() or "After Severing Ties"
            pending = session_data.get("pending_sync_sheet", {})
            missing_items = pending.get("missing_items")
            bot.send_message(chat_id, f"🚀 <b>جاري إدراج وتوثيق الفصول في Google Sheet لرواية '{novel_name}'...</b>\nسيصلك تقرير تفصيلي فور الانتهاء.")
            def _exec_sync_thread():
                try:
                    import nsw_healer_engine
                    res = nsw_healer_engine.execute_sync_blogger_to_sheet(novel_name, missing_items)
                    if res.get("success"):
                        bot.send_message(chat_id, f"🎉 <b>تم بنجاح تحديث جدول الشيت وإدراج {res.get('added_count', 0)} فصلاً!</b>")
                    else:
                        bot.send_message(chat_id, f"⚠️ تنبيه أثناء تحديث الشيت: {res.get('error', 'تعذر الإدراج')}")
                except Exception as ex:
                    bot.send_message(chat_id, f"❌ خطأ أثناء مزامنة الشيت: {ex}")
            threading.Thread(target=_exec_sync_thread, daemon=True).start()
            USER_SESSIONS.get(chat_id, {}).pop("pending_sync_sheet", None)
            return

        elif data.startswith("cb_exec_purge_dups:"):
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            novel_name = data.replace("cb_exec_purge_dups:", "").strip() or "After Severing Ties"
            bot.send_message(chat_id, f"🧹 <b>جاري تنفيذ تطهير وحذف التدوينات المكررة من مدونة بلوجر لرواية '{novel_name}'...</b>\nسيصلك تقرير تفصيلي بعد المعالجة.")
            def _exec_purge_thread():
                try:
                    import nsw_healer_engine
                    res = nsw_healer_engine.detect_and_purge_duplicate_posts(novel_name, dry_run=False)
                    bot.send_message(chat_id, f"🎉 <b>اكتملت عملية التطهير بنجاح!</b> تم تنظيف التدوينات المكررة من بلوجر بنجاح.")
                except Exception as ex:
                    bot.send_message(chat_id, f"❌ خطأ أثناء تطهير المكررات: {ex}")
            threading.Thread(target=_exec_purge_thread, daemon=True).start()
            USER_SESSIONS.get(chat_id, {}).pop("pending_purge_dups", None)
            return

        elif data == "CANCEL_ACTION":
            USER_SESSIONS.get(chat_id, {}).pop("state", None)
            USER_SESSIONS.get(chat_id, {}).pop("pending_date_fix", None)
            USER_SESSIONS.get(chat_id, {}).pop("pending_sync_sheet", None)
            USER_SESSIONS.get(chat_id, {}).pop("pending_purge_dups", None)
            bot.send_message(chat_id, "🛑 تم إلغاء العملية بأمان. لن يتم إجراء أي تعديل أو نشر.")
            return


        elif data == "cb_nsw_help":
            try:
                nsw_help_cmd(call.message)
            except Exception as e:
                bot.send_message(chat_id, f"❌ خطأ: {e}")
            return

        # ----------------------------------------------------
        # معالجة استعراض سينما ومسلسلات (Cinema Callbacks)
        # ----------------------------------------------------
        if data == "media_cinema_detect":
            status_msg = bot.send_message(chat_id, "🔎 <b>جاري فحص المقطع والتعرف على المشهد والعمل الفني...</b>")
            def _detect_video():
                info = media_engine.get_video_info(target_url) if target_url else {}
                title = info.get("title", "")
                res = cinema_engine.analyze_cinema_content(query_text=f"رابط فيديو: {target_url}\nالعنوان: {title}")
                _send_cinema_result(chat_id, res, status_msg.message_id)
            threading.Thread(target=_detect_video, daemon=True).start()
            return

        elif data == "cin_seasons":
            cin_data = session_data.get("cinema_data", {})
            seasons_cnt = cin_data.get("seasons_count", 1)
            markup = types.InlineKeyboardMarkup(row_width=3)
            buttons = [
                types.InlineKeyboardButton(f"الموسم {s}", callback_data=f"cin_s_{s}")
                for s in range(1, min(seasons_cnt + 1, 15))
            ]
            markup.add(*buttons)
            bot.send_message(chat_id, f"📺 <b>مسلسل: {cin_data.get('title_arabic', '')}</b>\nاختر الموسم المطلوب استعراضه:", reply_markup=markup)
            return

        elif data.startswith("cin_s_"):
            season_num = int(data.split("_")[2])
            cin_data = session_data.get("cinema_data", {})
            ep_list = cin_data.get("episodes_per_season", [10])
            ep_count = ep_list[season_num - 1] if len(ep_list) >= season_num else 10

            markup = types.InlineKeyboardMarkup(row_width=4)
            buttons = [
                types.InlineKeyboardButton(f"حلقة {ep}", callback_data=f"cin_ep_{season_num}_{ep}")
                for ep in range(1, min(ep_count + 1, 25))
            ]
            markup.add(*buttons)
            bot.send_message(chat_id, f"🎬 <b>الموسم {season_num}</b>\nاختر رقم الحلقة لاستعراض تفاصيلها وتحميلها:", reply_markup=markup)
            return

        elif data.startswith("cin_ep_"):
            parts = data.split("_")
            s_num = int(parts[2])
            ep_num = int(parts[3])
            cin_data = session_data.get("cinema_data", {})
            s_name = cin_data.get("title_original") or cin_data.get("title_arabic", "مسلسل")

            status_msg = bot.send_message(chat_id, f"⏳ <b>جاري جلب تفاصيل الحلقة {ep_num} من الموسم {s_num}...</b>")
            def _ep_fetch():
                ep_info = cinema_engine.get_episode_details(s_name, s_num, ep_num)
                markup = types.InlineKeyboardMarkup(row_width=2)
                btn_dl_sub = types.InlineKeyboardButton("📥 تحميل الحلقة (مع الترجمة)", callback_data=f"cin_get_series_{s_num}_{ep_num}_sub")
                btn_dl_raw = types.InlineKeyboardButton("📥 تحميل الحلقة (بدون ترجمة)", callback_data=f"cin_get_series_{s_num}_{ep_num}_raw")
                markup.add(btn_dl_sub, btn_dl_raw)

                ep_text = (
                    f"🎬 <b>{s_name} - الموسم {s_num}</b>\n"
                    f"🏷️ <b>الحلقة {ep_num}:</b> {ep_info.get('title', '')}\n"
                    f"⏱️ <b>المدة:</b> {ep_info.get('duration', '45 دقيقة')}\n\n"
                    f"📝 <b>الملخص:</b>\n{ep_info.get('summary', '')}\n\n"
                    f"🚀 <i>اختر التحميل مع الترجمة أو بدونها وسيقوم الذكاء الاصطناعي بفحص المصادر وجلب المقطع فوراً:</i>"
                )
                bot.edit_message_text(ep_text, chat_id, status_msg.message_id, reply_markup=markup)
            threading.Thread(target=_ep_fetch, daemon=True).start()
            return

        elif data.startswith("cin_get_"):
            # مثال: cin_get_movie_sub أو cin_get_series_1_5_sub
            parts = data.split("_")
            c_type = parts[2]
            with_sub = (parts[-1] == "sub")
            cin_data = session_data.get("cinema_data", {})
            s_name = cin_data.get("title_original") or cin_data.get("title_arabic", "العمل الفني")
            
            s_num = int(parts[3]) if c_type == "series" else 1
            ep_num = int(parts[4]) if c_type == "series" else 1

            sub_str = "مع الترجمة العربية" if with_sub else "النسخة الأصلية بدون ترجمة"
            label = f"الحلقة {ep_num} من الموسم {s_num}" if c_type == "series" else "الفيلم"
            status_msg = bot.send_message(chat_id, f"🔍 <b>يقوم الذكاء الاصطناعي الآن بفحص المصادر السحابية لجلب {label} ({sub_str})...</b>\n<i>يرجى الانتظار ثوانٍ قليلة لتنزيل ومعالجة المقطع...</i>")

            def _resolve_and_send():
                res = cinema_engine.resolve_and_download_cinema_media(
                    title=s_name,
                    c_type=c_type,
                    season=s_num,
                    episode=ep_num,
                    with_subtitles=with_sub
                )
                if not res.get("success"):
                    bot.edit_message_text(f"⚠️ {res.get('error')}", chat_id, status_msg.message_id)
                    return

                fpath = res["filepath"]
                title = res["title"]
                size_mb = res["filesize_mb"]

                bot.edit_message_text(f"✅ تم سحب المقطع من الخوادم السحابية ({size_mb} MB)!\nجاري رفعه وإرساله لك الآن...", chat_id, status_msg.message_id)
                ok, send_info = media_engine.send_to_telegram(BOT_TOKEN, str(chat_id), fpath, caption=f"🎬 <b>{title}</b>\n✨ تم الجلب والتنزيل الآلي بواسطة الذكاء الاصطناعي.")
                if not ok:
                    bot.send_message(chat_id, f"⚠️ تنبيه الإرسال: {send_info}")
                bot.delete_message(chat_id, status_msg.message_id)

            threading.Thread(target=_resolve_and_send, daemon=True).start()
            return

        elif data.startswith("cin_dl_sub") or data.startswith("cin_dl_raw"):
            with_sub = ("sub" in data)
            cin_data = session_data.get("cinema_data", {})
            s_name = cin_data.get("title_original") or cin_data.get("title_arabic", "الفيلم")
            
            sub_str = "مع الترجمة العربية" if with_sub else "النسخة الأصلية بدون ترجمة"
            status_msg = bot.send_message(chat_id, f"🔍 <b>يقوم الذكاء الاصطناعي بفحص المصادر الخلفية لجلب الفيلم ({sub_str})...</b>")

            def _resolve_movie():
                res = cinema_engine.resolve_and_download_cinema_media(
                    title=s_name,
                    c_type="movie",
                    with_subtitles=with_sub
                )
                if not res.get("success"):
                    bot.edit_message_text(f"⚠️ {res.get('error')}", chat_id, status_msg.message_id)
                    return

                fpath = res["filepath"]
                title = res["title"]
                size_mb = res["filesize_mb"]

                bot.edit_message_text(f"✅ تم العثور على الفيلم وسحبه سحابياً ({size_mb} MB)!\nجاري تجهيزه وإرساله لك...", chat_id, status_msg.message_id)
                ok, send_info = media_engine.send_to_telegram(BOT_TOKEN, str(chat_id), fpath, caption=f"🎬 <b>{title}</b>\n✨ تم الجلب بواسطة الذكاء الاصطناعي.")
                if not ok:
                    bot.send_message(chat_id, f"⚠️ تنبيه الإرسال: {send_info}")
                bot.delete_message(chat_id, status_msg.message_id)

            threading.Thread(target=_resolve_movie, daemon=True).start()
            return

        if not target_url:
            bot.answer_callback_query(call.id, "انتهت صلاحية الجلسة، يرجى إعادة إرسال الرابط.")
            return

        # ----------------------------------------------------
        # معالجة طلبات الفيديوهات
        # ----------------------------------------------------
        if data.startswith("media_"):
            is_audio = (data == "media_mp3")
            should_split = (data == "media_split")

            status_msg = bot.send_message(chat_id, "⏳ <b>جاري فحص وتنزيل المقطع عبر السيرفر السحابي...</b>")

            def _download_task():
                res = media_engine.download_media_file(target_url, extract_audio=is_audio)
                if not res.get("success"):
                    bot.edit_message_text(f"❌ <b>فشل التحميل:</b> {res.get('error')}", chat_id, status_msg.message_id)
                    return

                fpath = res["filepath"]
                title = res["title"]
                size_mb = res["filesize_mb"]

                bot.edit_message_text(f"✅ تم اكتمال التحميل ({size_mb} MB)!\nجاري تجهيز وإرسال الملف (مع التجزئة التلقائية إذا لزم)...", chat_id, status_msg.message_id)

                ok, send_info = media_engine.send_to_telegram(BOT_TOKEN, str(chat_id), fpath, caption=f"🎬 {title}", auto_split_if_large=True)
                if not ok:
                    bot.send_message(chat_id, f"⚠️ تنبيه الإرسال: {send_info}")

                bot.delete_message(chat_id, status_msg.message_id)

            threading.Thread(target=_download_task, daemon=True).start()

        # ----------------------------------------------------
        # معالجة طلبات الروايات
        # ----------------------------------------------------
        elif data.startswith("novel_"):
            from_ch, to_ch = 1, 50
            if data == "novel_1_100":
                from_ch, to_ch = 1, 100
            elif data == "novel_all":
                from_ch, to_ch = 1, 9999

            status_msg = bot.send_message(chat_id, f"🚀 <b>تم بدء سحب الرواية في الخلفية (من {from_ch} إلى {to_ch})...</b>\nسيصلك ملف الـ TXT المكتمل فوراً!")

            def _novel_task():
                domain = scraper_engine.extract_clean_domain(target_url)
                cfg = database.get_domain_config(domain) or {
                    "toc_link_selector": "a[href*='/txt/'], a[href*='chapter'], a[href*='8095_']",
                    "chapter_title_selector": "h1",
                    "chapter_content_selector": ".txtnav, #chapter-content, #content, article",
                    "purge_selectors": ["h1", "script", "style", "nav"]
                }

                bot.edit_message_text("📑 <b>جاري زحف الفهرس واستخراج قائمة روابط الفصول تلقائياً...</b>", chat_id, status_msg.message_id)
                try:
                    chapters_list, detected_title = scraper_engine.crawl_toc_chapters(
                        target_url,
                        cfg.get("toc_link_selector") or "a[href*='chapter'], a[href*='/txt/']"
                    )
                except Exception as crawl_err:
                    bot.edit_message_text(f"❌ <b>فشل فحص الفهرس:</b> {crawl_err}", chat_id, status_msg.message_id)
                    return

                if not chapters_list:
                    bot.edit_message_text("⚠️ <b>تعذر استخراج روابط الفصول من صفحة الفهرس.</b> قد يحتاج الموقع إلى محددات خاصة أو به حماية.", chat_id, status_msg.message_id)
                    return

                novel = database.get_or_create_novel(target_url, title=detected_title or "رواية سحابية", domain=domain)
                database.sync_chapter_manifest(novel["id"], chapters_list)

                bot.edit_message_text(f"🚀 <b>تم العثور على {len(chapters_list)} فصلاً!</b>\nجاري الآن سحب وتجميع الفصول (من {from_ch} إلى {min(to_ch, len(chapters_list))}) في السيرفر...", chat_id, status_msg.message_id)

                # تشغيل السحب في الخلفية
                session = scraper_engine.start_background_scraping(
                    novel_id=novel["id"],
                    from_chapter=from_ch,
                    to_chapter=to_ch,
                    domain_config=cfg,
                    min_delay=0.3,
                    max_delay=0.8,
                    headless=True
                )

                # انتظار اكتمال السحب
                while novel["id"] in scraper_engine.ACTIVE_BACKGROUND_TASKS:
                    time.sleep(3.0)

                # تصدير الملف وإرساله
                full_text, count = database.export_novel_to_text(novel["id"], from_chapter=from_ch, to_chapter=to_ch)
                if count > 0:
                    bot.edit_message_text(f"✅ <b>اكتمل سحب {count} فصول بنجاح!</b>\nجاري إنشاء ملف الـ TXT ورفعه...", chat_id, status_msg.message_id)
                    temp_file = os.path.join(media_engine.DOWNLOAD_DIR, f"novel_{novel['id']}_chapters_{from_ch}_to_{to_ch}.txt")
                    with open(temp_file, "w", encoding="utf-8") as f_out:
                        f_out.write(full_text)

                    media_engine.send_to_telegram(BOT_TOKEN, str(chat_id), temp_file, caption=f"📚 <b>{novel['title']}</b>\nتم بنجاح سحب وتصدير {count} فصول كاملة بنص نظيف ومترابط!")
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                    bot.delete_message(chat_id, status_msg.message_id)
                else:
                    bot.edit_message_text("⚠️ لم يتم العثور على فصول مسحوبة بنجاح في هذا النطاق.", chat_id, status_msg.message_id)

            threading.Thread(target=_novel_task, daemon=True).start()

    return bot


import socket

_BOT_SOCKET_LOCK = None

def acquire_bot_lock() -> bool:
    """ضمان تشغيل نسخة واحدة فقط من البوت على مستوى الجهاز لمنع تكرار Polling وخطأ 409 Conflict."""
    global _BOT_SOCKET_LOCK
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('127.0.0.1', 58241))
        _BOT_SOCKET_LOCK = s
        return True
    except OSError as e:
        if getattr(e, 'winerror', None) == 10048 or getattr(e, 'errno', None) in (98, 10048):
            print("[Telegram Bot] ⚠️ هناك نسخة أخرى من البوت تعمل بالفعل. تم تخطي التشغيل لمنع خطأ 409 Conflict.")
            return False
        return True
    except Exception:
        return True


def run_telegram_bot_loop():
    """تشغيل حلقة استماع البوت السحابية المستمرة مع قفل تفادي الازدواجية."""
    if not acquire_bot_lock():
        return

    bot = create_bot_app()
    if not bot:
        print("[Telegram Bot] لم يتم تعيين TELEGRAM_BOT_TOKEN أو مكتبة telebot غير متوفرة.")
        return

    print("🤖 Telegram Bot is running and waiting for messages...")
    try:
        import local_nsw_api
        threading.Thread(target=local_nsw_api.start_server, daemon=True, name="NSWLocalAPI").start()
        print("⚡ [Local API] Web Bridge server active on http://127.0.0.1:58242")
    except Exception as e_api:
        print(f"⚠️ Could not start local web bridge: {e_api}")

    while True:
        try:
            bot.polling(none_stop=True, interval=1, timeout=30)
        except Exception as e:
            print(f"[Telegram Bot Error] {e}")
            time.sleep(5)


if __name__ == "__main__":
    run_telegram_bot_loop()
