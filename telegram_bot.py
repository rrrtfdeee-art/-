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


def create_bot_app():
    if not telebot or not BOT_TOKEN:
        return None

    bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

    # تسجيل قائمة الأوامر في زر Menu الرسمي بتطبيق تيليجرام
    try:
        bot.set_my_commands([
            types.BotCommand("menu", "📑 القائمة الرئيسية وأزرار التحكم"),
            types.BotCommand("repair", "🛡️ الإصلاح الشامل (فجوات + مبتورات + تنقل)"),
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
            btn_nav = types.InlineKeyboardButton("🔗 صيانة أزرار التنقل", callback_data="cb_nsw_nav")
            btn_status = types.InlineKeyboardButton("📊 حالة المنظومة", callback_data="cb_nsw_status")
            btn_gaps = types.InlineKeyboardButton("🧩 سد الفجوات الترقيمية", callback_data="cb_nsw_gaps")
            btn_heal = types.InlineKeyboardButton("🩹 استصلاح المبتورات", callback_data="cb_nsw_heal")
            btn_stage = types.InlineKeyboardButton("🎭 صقل أوبس (Opus)", callback_data="cb_nsw_stage")
            btn_stop = types.InlineKeyboardButton("🛑 إيقاف فوري", callback_data="cb_nsw_stop")
            btn_help = types.InlineKeyboardButton("📋 دليل الأوامر", callback_data="cb_nsw_help")
            markup.add(btn_repair)
            markup.add(btn_nav, btn_status)
            markup.add(btn_gaps, btn_heal)
            markup.add(btn_stage, btn_stop)
            markup.add(btn_help)

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

    @bot.message_handler(commands=['nsw_gaps', 'gaps'])
    def nsw_gaps_cmd(message):
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر للمشرف فقط.")
            return
        bot.reply_to(message, "🧩 <b>جاري فحص الفصول المفقودة وملء الفجوات...</b>\nسيصلك تقرير عند الاكتمال.")
        def _run():
            try:
                import nsw_healer_engine
                nsw_healer_engine.run_auto_fill_all_gaps()
            except Exception as e:
                bot.send_message(message.chat.id, f"❌ خطأ أثناء ملء الفجوات: {e}")
        threading.Thread(target=_run, daemon=True).start()

    @bot.message_handler(commands=['nsw_repair', 'repair', 'full_repair', 'super_repair'])
    def nsw_repair_cmd(message):
        """أمر الإصلاح والصيانة الشامل: سد الفجوات + استصلاح المبتورات + صيانة أزرار التنقل دفعة واحدة."""
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر للمشرف فقط.")
            return
        parts = message.text.strip().split(None, 1)
        novel_filter = parts[1].strip() if len(parts) > 1 else "After Severing Ties"
        bot.reply_to(message, f"🛡️ <b>تم إطلاق عملية الإصلاح والصيانة الشاملة لرواية '{novel_filter}'...</b>\n\n1️⃣ سد الفجوات المفقودة وترقية المسودات.\n2️⃣ استصلاح الفصول المبتورة في مكانها.\n3️⃣ ربط أزرار التنقل بالتسلسل التام.\n\n⏳ سيصلك تقرير مفصل عند اكتمال كل مرحلة.")
        def _run():
            try:
                import nsw_healer_engine
                nsw_healer_engine.run_comprehensive_full_repair(novel_filter)
            except Exception as e:
                bot.send_message(message.chat.id, f"❌ خطأ أثناء دورة الإصلاح الشامل: {e}")
        threading.Thread(target=_run, daemon=True).start()

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

    @bot.message_handler(commands=['nsw_stage', 'stage', 'opus_stage', 'opus'])
    def nsw_stage_cmd(message):
        """تجهيز وجلب دفعة فصول (حتى 20 فصلاً) لصقلها واعتمادها عبر Claude Opus."""
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر للمشرف فقط.")
            return
        parts = message.text.strip().split(None, 1)
        novel_filter = parts[1].strip() if len(parts) > 1 else "After Severing Ties"
        bot.reply_to(message, f"🎭 <b>جاري تجهيز دفعة فصول Claude Opus (حتى 20 فصلاً) لرواية '{novel_filter}'...</b>\nسيتم تجريد النصوص برمجياً من الأكواد واستخراج المتن الصافي.")
        def _run():
            try:
                import opus_staging_pipeline
                batch = opus_staging_pipeline.fetch_pending_chapters_for_opus_review(max_chapters=20, novel_name=novel_filter)
                if not batch:
                    bot.send_message(message.chat.id, "ℹ️ لا توجد فصول حالياً بانتظار الاعتماد أو الجدولة لهذه الرواية.")
                    return
                report = f"✅ <b>تم تجهيز دفعة فصول ({len(batch)} فصل) للصقل الأدبي:</b>\n"
                for ch in batch:
                    report += f"• الفصل <b>{ch['chapter_number']}</b> ({ch['char_count']} حرف) ➔ مصدر: <code>{ch['source']}</code>\n"
                report += "\n💡 <i>المتون مجردة وجاهزة للصقل وإعادة التغليف الملكي التلقائي.</i>"
                bot.send_message(message.chat.id, report)
            except Exception as e:
                bot.send_message(message.chat.id, f"❌ خطأ أثناء تجهيز دفعة أوبس: {e}")
        threading.Thread(target=_run, daemon=True).start()

    @bot.message_handler(commands=['nsw_nav', 'nav', 'repair_nav', 'nav_repair'])
    def nsw_nav_cmd(message):
        """صيانة وربط أزرار التنقل (السابق/التالي/الفهرس) لكافة فصول الرواية المنشورة والمجدولة."""
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر للمشرف فقط.")
            return
        parts = message.text.strip().split(None, 2)
        novel_filter = parts[1].strip() if len(parts) > 1 else "After Severing Ties"
        start_chap = int(parts[2].strip()) if len(parts) > 2 and parts[2].strip().isdigit() else 1
        bot.reply_to(message, (
            f"🔗 <b>جاري بدء صيانة وربط أزرار التنقل لرواية '{novel_filter}' بدءاً من الفصل {start_chap}...</b>\n"
            "سيتم فحص جدول النشر وقراءة الروابط وربط كل فصل بالسابق واللاحق والفهرس بدقة متناهية."
        ))
        def _run():
            try:
                import nsw_healer_engine
                res = nsw_healer_engine.repair_all_chapter_navigation(novel_filter, start_chapter=start_chap)
                if res.get("success"):
                    bot.send_message(message.chat.id, (
                        f"✅ <b>اكتملت صيانة أزرار التنقل بنجاح!</b> 🎉\n"
                        f"📖 <b>الرواية:</b> {novel_filter}\n"
                        f"🔗 <b>الفصول المربوطة:</b> {res.get('linksPatched', 0)} فصلاً\n"
                        f"🛡️ تم ربط أزرار السابق والتالي والفهرس بنجاح دون أي قفزات."
                    ))
                else:
                    bot.send_message(message.chat.id, f"⚠️ تنبيه: {res.get('error', 'تعذر إتمام صيانة التنقل')}")
            except Exception as e:
                bot.send_message(message.chat.id, f"❌ خطأ أثناء صيانة أزرار التنقل: {e}")
        threading.Thread(target=_run, daemon=True).start()

    @bot.message_handler(commands=['nsw_help', 'nsw'])
    def nsw_help_cmd(message):
        if not is_admin(message.from_user.id):
            bot.reply_to(message, "⛔ هذا الأمر للمشرف فقط.")
            return
        text = (
            "📋 <b>أوامر نظام NSW الشامل للنشر والترجمة:</b>\n\n"
            "🛡️ <code>/nsw_repair [رواية]</code> — <b>الإصلاح الشامل الكامل</b> (سد الفجوات + استصلاح المبتورات + صيانة أزرار التنقل دفعة واحدة)\n"
            "🔗 <code>/nsw_nav [رواية] [فصل_البداية]</code> — <b>صيانة وربط أزرار التنقل</b> (السابق/التالي/الفهرس) من الشيت\n"
            "📊 <code>/nsw_status</code> — حالة المحرك والمهام الآنية\n"
            "🧩 <code>/nsw_gaps [رواية]</code> — فحص وسد الفصول المفقودة فقط\n"
            "🩹 <code>/nsw_heal [رواية]</code> — فحص واستصلاح الفصول المبتورة فقط\n"
            "🎭 <code>/nsw_stage [رواية]</code> — تجهيز دفعة الـ 20 فصلاً لـ Claude Opus\n"
            "🎯 <code>/nsw_fix [رواية] [رقم]</code> — إصلاح وترجمة فصل محدد\n"
            "🚀 <code>/nsw_publish [رواية] [فصول]</code> — نشر فصول بعينها\n"
            "🛑 <code>/nsw_stop</code> — إيقاف العملية الجارية فوراً\n\n"
            "💡 <b>اختصارات سريعة:</b>\n"
            "<code>/repair</code> · <code>/nav</code> · <code>/status</code> · <code>/gaps</code> · <code>/heal</code> · <code>/stage</code> · <code>/fix</code> · <code>/publish</code> · <code>/stop</code>"
        )
        bot.reply_to(message, text)

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
        if data == "cb_nsw_repair":
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            bot.send_message(chat_id, "🛡️ <b>تم إطلاق عملية الإصلاح والصيانة الشاملة...</b>\n\n1️⃣ سد الفجوات وترقية المسودات.\n2️⃣ استصلاح الفصول المبتورة مكانها.\n3️⃣ ربط أزرار التنقل بالتسلسل التام.\n\n⏳ سيصلك تقرير مفصل عند اكتمال كل مرحلة.")
            def _run_repair():
                try:
                    import nsw_healer_engine
                    nsw_healer_engine.run_comprehensive_full_repair("After Severing Ties")
                except Exception as e:
                    bot.send_message(chat_id, f"❌ خطأ أثناء الإصلاح الشامل: {e}")
            threading.Thread(target=_run_repair, daemon=True).start()
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
            bot.send_message(chat_id, "🧩 <b>جاري فحص الفصول المفقودة وسد الفجوات...</b>")
            def _run_gaps():
                try:
                    import nsw_healer_engine
                    nsw_healer_engine.run_auto_fill_all_gaps("After Severing Ties")
                except Exception as e:
                    bot.send_message(chat_id, f"❌ خطأ أثناء سد الفجوات: {e}")
            threading.Thread(target=_run_gaps, daemon=True).start()
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
            bot.send_message(chat_id, "🔗 <b>جاري بدء صيانة وربط أزرار التنقل لكافة الفصول...</b>\nسيتم قراءة الروابط من جدول النشر وربط زر السابق بالتالي والفهرس تسلسلياً.")
            def _run_nav():
                try:
                    import nsw_healer_engine
                    res = nsw_healer_engine.repair_all_chapter_navigation("After Severing Ties")
                    if res.get("success"):
                        bot.send_message(chat_id, (
                            f"✅ <b>اكتملت صيانة أزرار التنقل بنجاح!</b> 🎉\n"
                            f"🔗 <b>الفصول المربوطة:</b> {res.get('linksPatched', 0)} فصلاً\n"
                            f"🛡️ تم ربط أزرار السابق والتالي والفهرس بنجاح."
                        ))
                    else:
                        bot.send_message(chat_id, f"⚠️ تنبيه: {res.get('error', 'تعذر إتمام صيانة التنقل')}")
                except Exception as e:
                    bot.send_message(chat_id, f"❌ خطأ أثناء صيانة أزرار التنقل: {e}")
            threading.Thread(target=_run_nav, daemon=True).start()
            return

        elif data == "cb_nsw_stage":
            if not is_admin(chat_id):
                bot.send_message(chat_id, "⛔ هذا الأمر للمشرف فقط.")
                return
            bot.send_message(chat_id, "🎭 <b>جاري تجهيز دفعة الـ 20 فصلاً لـ Claude Opus...</b>")
            def _run_stage():
                try:
                    import opus_staging_pipeline
                    batch = opus_staging_pipeline.fetch_pending_chapters_for_opus_review(max_chapters=20, novel_name="After Severing Ties")
                    if not batch:
                        bot.send_message(chat_id, "ℹ️ لا توجد فصول حالياً بانتظار الاعتماد أو الجدولة لهذه الرواية.")
                        return
                    report = f"✅ <b>تم تجهيز دفعة فصول ({len(batch)} فصل) للصقل الأدبي:</b>\n"
                    for ch in batch:
                        report += f"• الفصل <b>{ch['chapter_number']}</b> ({ch['char_count']} حرف) ➔ مصدر: <code>{ch['source']}</code>\n"
                    report += "\n💡 <i>المتون مجردة وجاهزة للصقل وإعادة التغليف التلقائي.</i>"
                    bot.send_message(chat_id, report)
                except Exception as e:
                    bot.send_message(chat_id, f"❌ خطأ: {e}")
            threading.Thread(target=_run_stage, daemon=True).start()
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
    while True:
        try:
            bot.polling(none_stop=True, interval=1, timeout=30)
        except Exception as e:
            print(f"[Telegram Bot Error] {e}")
            time.sleep(5)


if __name__ == "__main__":
    run_telegram_bot_loop()
