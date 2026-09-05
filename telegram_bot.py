"""
==============================================================================
Smart Telegram Bot Interface - Novel Scraper & Media Downloader v1.0
==============================================================================
هذا البوت يعمل كواجهة تحكم متكاملة عبر تيليجرام:
1. يستقبل روابط الروايات، يفهرس الفصول، ويسحبها في الخلفية ويرسل ملف .TXT النهائي.
2. يستقبل روابط الفيديوهات، ويحملها بجودات متعددة أو صوت MP3 مع التجزئة التلقائية.
3. يدعم الأزرار التفاعلية (Inline Keyboards) وشاشات التقدم الحية.
4. نظام أمان متقدم يسمح للمالك فقط بالاستخدام لحماية السيرفر والمفاتيح.
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
from gemini_analyzer import DEFAULT_GAS_URL

# اسم مستخدم البوت الافتراضي وتوكن التحكم
DEFAULT_BOT_USERNAME = "@SmartNovelMediaBot"
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", database.get_setting("telegram_bot_token", ""))
ADMIN_CHAT_ID = os.getenv("TELEGRAM_ALLOWED_USER", database.get_setting("telegram_allowed_user", ""))

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

    @bot.message_handler(commands=['start', 'help'])
    def send_welcome(message):
        if not is_user_authorized(message):
            bot.reply_to(message, "⛔ <b>عذراً، هذا البوت خاص وغير متاح للعامة.</b>\nتواصل مع مالك البوت للحصول على إذن الاستخدام.")
            return

        admin_hint = "\n\n👑 <i>بصفتك المشرف، اكتب /admin للتحكم في الصلاحيات.</i>" if is_admin(message.from_user.id) else ""
        text = (
            "👋 <b>مرحباً بك في بوت Smart Scraper & Media AI!</b>\n\n"
            "هذا البوت مجهز لتنفيذ المهام التالية نيابة عنك وبأعلى سرعة:\n"
            "📚 <b>سحب الروايات:</b> أرسل رابط فهرس الرواية لسحب الفصول وتجميعها بملف TXT كامل.\n"
            "🎬 <b>تحميل الفيديوهات:</b> أرسل رابط يوتيوب، تيك توك، أو تويتر لتحميله MP4 أو تحويله لـ MP3 مع التجزئة التلقائية.\n"
            "🧠 <b>الذكاء الاصطناعي:</b> مدعوم بنموذج Google Gemini 3.8 Flash السحابي."
            f"{admin_hint}\n\n"
            "<i>فقط قم بمشاركة أو لصق أي رابط هنا للبدء مباشرة!</i>"
        )
        bot.reply_to(message, text)

    @bot.message_handler(func=lambda msg: True)
    def handle_incoming_link(message):
        if not is_user_authorized(message):
            bot.reply_to(message, "⛔ <b>غير مصرح لك بالاستخدام.</b>\nتواصل مع المشرف لإضافتك.")
            return

        user_text = message.text.strip()
        if not user_text.startswith("http://") and not user_text.startswith("https://"):
            bot.reply_to(message, "⚠️ يرجى إرسال رابط صالح يبدأ بـ http أو https.")
            return

        chat_id = message.chat.id
        USER_SESSIONS[chat_id] = {"url": user_text}

        # تحديد نوع الرابط تلقائياً
        if any(domain in user_text.lower() for domain in ["youtube.com", "youtu.be", "tiktok.com", "x.com", "twitter.com", "bilibili", "instagram"]):
            # رابط وسائط / فيديو
            markup = types.InlineKeyboardMarkup(row_width=2)
            btn_mp4 = types.InlineKeyboardButton("🎬 فيديو MP4 كامل", callback_data="media_mp4")
            btn_mp3 = types.InlineKeyboardButton("🎵 صوت فقط MP3", callback_data="media_mp3")
            btn_split = types.InlineKeyboardButton("✂️ تجزئة وتنزيل (<500MB)", callback_data="media_split")
            markup.add(btn_mp4, btn_mp3, btn_split)
            
            bot.reply_to(
                message,
                f"🎬 <b>تم التعرف على رابط فيديو!</b>\nالرابط: <code>{user_text}</code>\n\nاختر نوع التحميل المطلوب:",
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

        if not target_url:
            bot.answer_callback_query(call.id, "انتهت صلاحية الجلسة، يرجى إعادة إرسال الرابط.")
            return

        data = call.data
        bot.answer_callback_query(call.id, "جاري التنفيذ في الخلفية...")

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

                bot.edit_message_text(f"✅ تم اكتمال التحميل ({size_mb} MB)!\nجاري تجهيز الملف للإرسال...", chat_id, status_msg.message_id)

                if should_split and size_mb > 45:
                    parts = media_engine.split_video_lossless(fpath, max_part_mb=45)
                    for idx, p in enumerate(parts, 1):
                        bot.send_message(chat_id, f"📤 إرسال الجزء {idx} من {len(parts)}...")
                        media_engine.send_to_telegram(BOT_TOKEN, str(chat_id), p, caption=f"🎬 {title} (جزء {idx})")
                else:
                    media_engine.send_to_telegram(BOT_TOKEN, str(chat_id), fpath, caption=f"🎬 {title}")

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
                novel = database.get_or_create_novel(target_url, title="رواية سحابية", domain=domain)
                cfg = database.get_domain_config(domain) or {
                    "toc_link_selector": "a[href*='/txt/'], a[href*='chapter']",
                    "chapter_title_selector": "h1",
                    "chapter_content_selector": ".txtnav, #chapter-content",
                    "purge_selectors": ["h1", "script", "style"]
                }
                
                # تشغيل السحب في الخلفية
                session = scraper_engine.start_background_scraping(
                    novel_id=novel["id"],
                    from_chapter=from_ch,
                    to_chapter=to_ch,
                    domain_config=cfg,
                    min_delay=0.5,
                    max_delay=1.0,
                    headless=True
                )

                # انتظار اكتمال السحب
                while novel["id"] in scraper_engine.ACTIVE_BACKGROUND_TASKS:
                    time.sleep(3.0)

                # تصدير الملف وإرساله
                full_text, count = database.export_novel_to_text(novel["id"], from_chapter=from_ch, to_chapter=to_ch)
                if count > 0:
                    temp_file = os.path.join(media_engine.DOWNLOAD_DIR, f"novel_{novel['id']}_chapters_{from_ch}_to_{to_ch}.txt")
                    with open(temp_file, "w", encoding="utf-8") as f_out:
                        f_out.write(full_text)

                    media_engine.send_to_telegram(BOT_TOKEN, str(chat_id), temp_file, caption=f"📚 تم بنجاح سحب وتصدير {count} فصول كاملة بنص نظيف ومترابط!")
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                else:
                    bot.send_message(chat_id, "⚠️ لم يتم العثور على فصول مسحوبة في هذا النطاق.")

            threading.Thread(target=_novel_task, daemon=True).start()

    return bot


def run_telegram_bot_loop():
    """تشغيل حلقة استماع البوت السحابية المستمرة."""
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
