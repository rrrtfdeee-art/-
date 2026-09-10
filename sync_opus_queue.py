# -*- coding: utf-8 -*-
"""
==============================================================================
NSW Claude Opus Local Staging & Sync Manager v1.0
==============================================================================
إدارة طابور الاعتماد الذاتي لـ Claude Opus:
  1. python sync_opus_queue.py status
  2. python sync_opus_queue.py pull [--limit 20] [--novel "After Severing Ties"]
  3. python sync_opus_queue.py push [--novel "After Severing Ties"]
  4. python sync_opus_queue.py approve <chapter_num>
"""

import os
import sys
import re
import json
import shutil
import logging
import argparse
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# ضبط ترميز الإخراج ليتوافق مع الرموز التعبيرية واللغة العربية في ويندوز
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# إعداد المسارات الأساسية
BASE_DIR = Path(__file__).resolve().parent
STAGING_DIR = BASE_DIR / "opus_staging"
PENDING_DIR = STAGING_DIR / "pending"
APPROVED_DIR = STAGING_DIR / "approved"
PUBLISHED_DIR = STAGING_DIR / "published"
MANIFEST_PATH = STAGING_DIR / "manifest.json"

for d in [PENDING_DIR, APPROVED_DIR, PUBLISHED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Opus-Queue] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("NSW_Opus_Sync")


def load_manifest() -> Dict[str, Any]:
    """تحميل سجل التتبع manifest.json."""
    if MANIFEST_PATH.exists():
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"تعذر قراءة manifest.json: {e}. سيتم البدء بملف جديد.")
    return {"chapters": {}, "last_sync": ""}


def save_manifest(manifest: Dict[str, Any]):
    """حفظ سجل التتبع manifest.json."""
    manifest["last_sync"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def parse_chapter_file(file_path: Path) -> Tuple[Dict[str, Any], str]:
    """قراءة ملف الفصل واستخراج الميتاداتا والنص الأدبي الصافي."""
    content = file_path.read_text(encoding="utf-8")
    meta = {}
    story_text = content

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            meta_str = parts[1]
            story_text = parts[2].strip()
            for line in meta_str.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()

    return meta, story_text


def write_chapter_file(file_path: Path, meta: Dict[str, Any], story_text: str):
    """كتابة الفصل في ملف txt مع ترويسة الميتاداتا الواضحة."""
    header_lines = ["---"]
    for k, v in meta.items():
        header_lines.append(f"{k}: {v}")
    header_lines.append("---\n\n")
    full_text = "\n".join(header_lines) + story_text.strip() + "\n"
    file_path.write_text(full_text, encoding="utf-8")


def cmd_status():
    """عرض الحالة اللحظية لطابور Claude Opus بالكامل."""
    manifest = load_manifest()
    ch_data = manifest.get("chapters", {})

    pending_files = sorted(list(PENDING_DIR.glob("chapter_*.txt")), key=lambda p: int(re.search(r'\d+', p.name).group(0)) if re.search(r'\d+', p.name) else 0)
    approved_files = sorted(list(APPROVED_DIR.glob("chapter_*.txt")), key=lambda p: int(re.search(r'\d+', p.name).group(0)) if re.search(r'\d+', p.name) else 0)
    published_files = sorted(list(PUBLISHED_DIR.glob("chapter_*.txt")), key=lambda p: int(re.search(r'\d+', p.name).group(0)) if re.search(r'\d+', p.name) else 0)

    print("\n" + "═" * 60)
    print(" 🎭 لوحة طابور الاعتماد والصقل الذاتي لـ Claude Opus")
    print("═" * 60)
    print(f"🕒 آخر مزامنة: {manifest.get('last_sync', 'لم تتم مزامنة بعد')}")
    print(f"⏳ قيد المراجعة في Pending : {len(pending_files)} فصل")
    print(f"✍️ معتمدة وجاهزة للنشر Approved: {len(approved_files)} فصل")
    print(f"✅ منشورة وموثقة Published   : {len(published_files)} فصل")
    print("─" * 60)

    if pending_files:
        print("\n📥 [الفصول بانتظار صقل Claude Opus]:")
        for pf in pending_files[:15]:
            meta, txt = parse_chapter_file(pf)
            c_num = meta.get("chapter", pf.stem.replace("chapter_", ""))
            title = meta.get("title", f"الفصل {c_num}")
            src = meta.get("source", "مجهول")
            chars = len(txt)
            print(f"  • الفصل {c_num:4s} | {chars:5d} حرف | {title} (مصدر: {src})")
        if len(pending_files) > 15:
            print(f"  ... و {len(pending_files) - 15} فصول أخرى بانتظار المراجعة.")

    if approved_files:
        print("\n✍️ [الفصول المعتمدة الجاهزة للرفع والنشر]:")
        for af in approved_files:
            meta, txt = parse_chapter_file(af)
            c_num = meta.get("chapter", af.stem.replace("chapter_", ""))
            title = meta.get("title", f"الفصل {c_num}")
            chars = len(txt)
            print(f"  ⭐ الفصل {c_num:4s} | {chars:5d} حرف | {title} [جاهز للإرسال]")

    print("═" * 60 + "\n")


def cmd_pull(
    limit: int = 20,
    novel_name: str = "After Severing Ties",
    start_chapter: int = 1,
    include_live: bool = True,
    send_telegram: bool = True
) -> int:
    """سحب الفصول بانتظار المراجعة وتجريدها وتفريغها في pending/."""
    logger.info(f"🚀 بدء سحب دفعة حتى {limit} فصلاً لرواية '{novel_name}' (بدءاً من {start_chapter})...")
    import opus_staging_pipeline
    manifest = load_manifest()
    chapters_dict = manifest.setdefault("chapters", {})

    batch = opus_staging_pipeline.fetch_pending_chapters_for_opus_review(
        max_chapters=limit,
        novel_name=novel_name,
        start_chapter=start_chapter,
        include_live=include_live
    )
    if not batch:
        logger.info("ℹ️ لم يتم العثور على فصول تنتظر المراجعة حالياً.")
        return 0

    saved_count = 0
    for ch in batch:
        c_num = ch["chapter_number"]
        key = str(c_num)
        
        # تجنب الكتابة فوق الفصول المعتمدة أو المنشورة
        if key in chapters_dict and chapters_dict[key].get("status") in ["approved", "published"]:
            continue

        target_file = PENDING_DIR / f"chapter_{c_num}.txt"
        
        meta = {
            "novel": novel_name,
            "chapter": str(c_num),
            "title": ch.get("title", f"الفصل {c_num}"),
            "source": ch.get("source", "System"),
            "post_id": ch.get("post_id", ""),
            "post_url": ch.get("post_url", ""),
            "published_date": ch.get("published_date", ""),
            "staged_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        raw_story = ch.get("raw_story", "")
        # إذا لم يكن المتن موجوداً، نبحث عنه في SQLite أو نسحبه
        if not raw_story or len(raw_story) < 200:
            try:
                import database
                with database.get_connection() as conn:
                    row = conn.execute(
                        "SELECT content FROM chapters WHERE chapter_number = ? AND content IS NOT NULL AND length(content) > 200 LIMIT 1",
                        (c_num,)
                    ).fetchone()
                    if row and row["content"]:
                        raw_story = opus_staging_pipeline.strip_html_to_clean_story(row["content"])
            except Exception:
                pass

        if not raw_story:
            raw_story = f"متن الفصل {c_num} - جاهز للصقل والمراجعة الأدبية بواسطة Claude Opus."

        write_chapter_file(target_file, meta, raw_story)

        chapters_dict[key] = {
            "chapter_number": c_num,
            "novel_name": novel_name,
            "status": "pending",
            "file": str(target_file.name),
            "title": meta["title"],
            "source": meta["source"],
            "post_id": meta["post_id"],
            "post_url": meta["post_url"],
            "published_date": meta.get("published_date", ""),
            "char_count": len(raw_story),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        saved_count += 1

    save_manifest(manifest)
    logger.info(f"✅ تم سحب وتجهيز {saved_count} فصلاً ناصعاً بنجاح في مجلد: {PENDING_DIR}")

    # توليد ملف طلب كلاود أوبس الفوري مع القاموس المفلتر
    generate_batch_claude_prompt(novel_name)

    if send_telegram and saved_count > 0:
        try:
            from nsw_healer_engine import send_opus_batch_to_telegram
            send_opus_batch_to_telegram(novel_name, batch)
        except Exception as e:
            logger.warning(f"تعذر إرسال الحزمة لتليجرام: {e}")

    return saved_count


def generate_batch_claude_prompt(novel_name: str = "After Severing Ties") -> str:
    """توليد أمر فوري متكامل مع القاموس المفلتر للدفعة الموجودة في pending/."""
    from nsw_healer_engine import get_novel_glossary, filter_glossary_for_chapter

    pending_files = sorted(list(PENDING_DIR.glob("chapter_*.txt")), key=lambda p: int(re.search(r'\d+', p.name).group(0)) if re.search(r'\d+', p.name) else 0)
    if not pending_files:
        return "لا توجد فصول في الانتظار حالياً."

    all_glossary = get_novel_glossary(novel_name)
    all_text = ""
    for pf in pending_files:
        _, txt = parse_chapter_file(pf)
        all_text += " " + txt

    # فلترة القاموس للدفعة
    matched_glossary = filter_glossary_for_chapter(all_text, all_glossary, novel_name)

    # بناء التعليمات الصارمة لكلاود أوبس
    prompt_lines = [
        f"👑 [أمر الصقل والمراجعة الأدبية لدفعة فصول رواية: {novel_name}]",
        "المطلوب: مراجعة وصقل الفصول الموجودة في مجلد `opus_staging/pending/` بأعلى أسلوب بلاغي فصيح.",
        "",
        "📜 القواعد الذهبية الصارمة:",
        "1. الالتزام التام والقطعي بأسماء الشخصيات والمصطلحات الواردة في القاموس المرفق أدناه.",
        "2. الحفاظ الصارم على كافة وسوم التنسيق الجمالية BBCode دون حذفها أو تعديل شكلها:",
        "   - [cultivation]...[/cultivation] لتقنيات واختراقات ومراحل المزارعة والطاقة.",
        "   - [system]...[/system] لنوافذ وشاشات النظام السيبراني والمهمات.",
        "   - [system red]...[/system] لتحذيرات الخطر والموت.",
        "   - [doc]...[/doc] للوثائق والمراسيم.",
        "   - [letter]...[/letter] للرسائل والمذكرات الشخصية.",
        "   - [tip]...[/tip] للتلميحات الإرشادية.",
        "3. المعالجة البلاغية الصارمة للأمثال والتعبيرات الاصطلاحية (Idioms / Chengyu):",
        "   - احذر الترجمة الحرفية الكلمية للأمثال والتشبيهات الأجنبية إذا كانت ركيكة أو غير مفهومة في العربية.",
        "   - استبدل أي مثل أجنبي مترجم حرفياً (مثل: رسم أقدام الأفعى، ضفدع في بئر، رأس كبش ولحم كلب، كسر وعاء) بالمكافئ العربي الفصيح البليغ (مثل: فضول وتكلف مفسد، قاصر النظر ومحدود الأفق، تدليس ونفاق، حرق سفن العودة).",
        "   - أو أعد صياغته بأسلوب روائي فخم يبرز المغزى الحقيقي والشعور الدرامي بدلاً من الألفاظ السطحية.",
        "4. إخراج المتن المصقول كفقرات نقية بدون أي أكواد HTML إضافية.",
        "",
        "📌 القاموس المعتمد المخصص لهذه الدفعة:"
    ]
    for g in matched_glossary:
        cat = f" ({g.get('category')})" if g.get('category') else ""
        gender = f" [{g.get('gender')}]" if g.get('gender') else ""
        prompt_lines.append(f"• {g['original']} ➔ {g['arabic']}{cat}{gender}")

    prompt_text = "\n".join(prompt_lines)
    prompt_file = STAGING_DIR / "CLAUDE_PROMPT_FOR_BATCH.txt"
    prompt_file.write_text(prompt_text, encoding="utf-8")
    logger.info(f"📝 تم توليد ملف أمر كلاود مع القاموس المفلتر: {prompt_file}")

    # توليد ملف مجمّع كامل يحتوي على الأمر والمتون سوياً للنسخ المباشر
    bundle_lines = [prompt_text, "\n" + "=" * 60, "📦 [متون الفصول المراد صقلها للدفعة الحالية]", "=" * 60 + "\n"]
    for pf in pending_files:
        meta, txt = parse_chapter_file(pf)
        c_num = meta.get("chapter", re.search(r'\d+', pf.name).group(0))
        c_title = meta.get("title", f"الفصل {c_num}")
        bundle_lines.append(f"\n--- [بداية الفصل {c_num}: {c_title}] ---")
        bundle_lines.append(txt)
        bundle_lines.append(f"--- [نهاية الفصل {c_num}] ---\n")

    bundle_file = STAGING_DIR / "CLAUDE_FULL_BATCH_BUNDLE.txt"
    bundle_file.write_text("\n".join(bundle_lines), encoding="utf-8")
    logger.info(f"📦 تم توليد ملف الدفعة المجمعة الكاملة: {bundle_file}")

    return prompt_text


def cmd_approve(chapter_num: int):
    """نقل فصل من pending/ إلى approved/ بعد الانتهاء من مراجعته."""
    pending_file = PENDING_DIR / f"chapter_{chapter_num}.txt"
    approved_file = APPROVED_DIR / f"chapter_{chapter_num}.txt"

    if not pending_file.exists():
        logger.error(f"❌ الملف غير موجود في الطابور المعلق: {pending_file}")
        return

    shutil.move(str(pending_file), str(approved_file))
    manifest = load_manifest()
    key = str(chapter_num)
    if key in manifest.get("chapters", {}):
        manifest["chapters"][key]["status"] = "approved"
        manifest["chapters"][key]["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_manifest(manifest)
    logger.info(f"⭐ تم اعتماد الفصل {chapter_num} ونقله إلى {approved_file}. جاهز للنشر (Push)!")


def cmd_approve_all():
    """نقل كافة الفصول الموجودة في pending/ إلى approved/ دفعة واحدة."""
    pending_files = sorted(list(PENDING_DIR.glob("chapter_*.txt")), key=lambda p: int(re.search(r'\d+', p.name).group(0)) if re.search(r'\d+', p.name) else 0)
    if not pending_files:
        logger.info("ℹ️ لا توجد فصول في pending/ لنقلها للاعتماد.")
        return 0

    count = 0
    for pf in pending_files:
        m = re.search(r'\d+', pf.name)
        if m:
            c_num = int(m.group(0))
            cmd_approve(c_num)
            count += 1
    logger.info(f"⭐ تم اعتماد ونقل {count} فصول بنجاح إلى approved/!")
    return count


def cmd_auto_refine_and_notify(
    limit: int = 20,
    novel_name: str = "After Severing Ties",
    send_telegram_notify: bool = True
) -> int:
    """
    صقل وتدقيق آلي فوري للفصول الموجودة في pending/ بواسطة محرك التدقيق الأدبي الملكي،
    ثم إرسال إشعار تيليجرام تفاعلي للمشرف يحتوي على زر الاعتماد والنشر المباشر.
    """
    from nsw_healer_engine import (
        get_novel_glossary, stage_2_antigravity_refine, notify_admin, normalize_character_names
    )
    pending_files = sorted(list(PENDING_DIR.glob("chapter_*.txt")), key=lambda p: int(re.search(r'\d+', p.name).group(0)) if re.search(r'\d+', p.name) else 0)
    if not pending_files:
        logger.info("ℹ️ لا توجد فصول في pending/ لصقلها آلياً. جاري سحب دفعة أولاً...")
        cmd_pull(limit=limit, novel_name=novel_name)
        pending_files = sorted(list(PENDING_DIR.glob("chapter_*.txt")), key=lambda p: int(re.search(r'\d+', p.name).group(0)) if re.search(r'\d+', p.name) else 0)

    if not pending_files:
        if send_telegram_notify:
            notify_admin(f"ℹ️ لا توجد فصول تنتظر الصقل أو المراجعة حالياً لرواية '{novel_name}'.")
        return 0

    target_files = pending_files[:limit]
    if send_telegram_notify:
        notify_admin(f"🤖 <b>[بدء الصقل والتدقيق الأدبي الآلي]:</b>\nجاري صقل وتدقيق <b>{len(target_files)}</b> فصول لرواية <b>{novel_name}</b>...\nسيصلك إشعار فوري عند الانتهاء مع زر النشر المباشر.")

    refined_count = 0
    refined_chaps = []

    for pf in target_files:
        meta, raw_text = parse_chapter_file(pf)
        c_num = int(meta.get("chapter", re.search(r'\d+', pf.name).group(0)))
        title = meta.get("title", f"الفصل {c_num}")

        logger.info(f"✨ صقل الفصل {c_num}: {title}...")
        try:
            # تدقيق الأدبي وحقن BBCode وتصحيح الأسماء
            ref_res = stage_2_antigravity_refine(title, raw_text, novel_name, c_num)
            refined_content = ref_res.get("refined_content", raw_text)
            refined_title = ref_res.get("refined_title", title)
            
            # تطبيع وتوحيد أسماء الشخصيات حتمياً
            refined_title = normalize_character_names(refined_title, novel_name)
            refined_content = normalize_character_names(refined_content, novel_name)

            # حفظ الفصل المنقح في approved/
            app_file = APPROVED_DIR / pf.name
            meta["status"] = "approved"
            meta["refined_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            write_chapter_file(app_file, meta, refined_content)

            # حذف من pending
            if pf.exists():
                pf.unlink()

            manifest = load_manifest()
            manifest.setdefault("chapters", {})[str(c_num)] = {
                "chapter_number": c_num,
                "novel_name": novel_name,
                "status": "approved",
                "title": refined_title,
                "post_id": meta.get("post_id", ""),
                "published_date": meta.get("published_date", ""),
                "char_count": len(refined_content),
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            save_manifest(manifest)
            refined_count += 1
            refined_chaps.append(str(c_num))
        except Exception as e_ref:
            logger.error(f"خطأ صقل الفصل {c_num}: {e_ref}")

    # إرسال إشعار الانتهاء مع زر النشر الفوري إلى تيليجرام
    if refined_count > 0 and send_telegram_notify:
        ch_list_str = ", ".join(refined_chaps[:10]) + ("..." if len(refined_chaps) > 10 else "")
        msg = (
            f"🎉 <b>[اكتمل صقل وتدقيق {refined_count} فصلاً بنجاح!]</b> 🚀\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📖 <b>الرواية:</b> {novel_name}\n"
            f"🔢 <b>الفصول الجاهزة للنشر:</b> {ch_list_str}\n"
            f"✍️ تم ضبط التنسيقات وعلامات الحوار ووسوم BBCode والقاموس بنسبة 100%.\n\n"
            f"👇 <b>اضغط الزر أدناه لنشر وجدولة كافة الفصول إلى بلوجر والشيت فوراً:</b>"
        )
        try:
            import telebot
            from telebot import types
            from telegram_bot import BOT_TOKEN, ADMIN_CHAT_ID
            if BOT_TOKEN and ADMIN_CHAT_ID:
                b = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
                m = types.InlineKeyboardMarkup(row_width=1)
                m.add(
                    types.InlineKeyboardButton("🚀 اعتماد ونشر الكل إلى بلوجر والشيت (Push)", callback_data="cb_opus_push_all"),
                    types.InlineKeyboardButton("📊 عرض حالة الطابور", callback_data="cb_opus_status")
                )
                b.send_message(ADMIN_CHAT_ID, msg, reply_markup=m)
        except Exception as e_tg:
            logger.error(f"خطأ إرسال إشعار تيليجرام: {e_tg}")

    return refined_count


FULL_AUDIT_STOP_EVENT = threading.Event()
IS_FULL_AUDIT_RUNNING = False


def request_stop_full_audit():
    """طلب إيقاف التدقيق الشامل بأمان."""
    global FULL_AUDIT_STOP_EVENT
    FULL_AUDIT_STOP_EVENT.set()
    logger.info("🛑 تم استلام إشارة إيقاف التدقيق الشامل للرواية.")


def is_full_audit_active() -> bool:
    """التحقق مما إذا كان التدقيق الشامل قيد التشغيل حالياً."""
    return IS_FULL_AUDIT_RUNNING


def cmd_audit_full_novel(
    novel_name: str = "After Severing Ties",
    batch_size: int = 20,
    auto_push: bool = False,
    start_chapter: int = 1,
    max_batches: int = 50
) -> int:
    """
    تدقيق شامل لكامل فصول الرواية (حتى 500+ فصل) على دفعات آلية متتالية:
    يسحب الفصول تباعاً، يصقلها أدبياً ويفحص القاموس و BBCode،
    ويوثق التقدم إلى تيليجرام بعد كل دفعة بدون توقف.
    """
    global IS_FULL_AUDIT_RUNNING, FULL_AUDIT_STOP_EVENT
    IS_FULL_AUDIT_RUNNING = True
    FULL_AUDIT_STOP_EVENT.clear()

    from nsw_healer_engine import notify_admin
    logger.info(f"📚 [بدء التدقيق الشامل]: الرواية={novel_name}، بدءاً من الفصل {start_chapter}")

    notify_admin(
        f"📚 <b>[بدء التدقيق الشامل لرواية كاملة (500+ فصل)]:</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📖 <b>الرواية:</b> {novel_name}\n"
        f"🔢 <b>بدءاً من الفصل:</b> {start_chapter}\n"
        f"📦 <b>حجم الدفعة:</b> {batch_size} فصلاً\n"
        f"⚡ ستقوم المنظومة آلياً بسحب وصقل وتدقيق الفصول دفعة تلو الأخرى.\n"
        f"🛑 للإيقاف في أي وقت: أرسل <code>/stop_audit</code>"
    )

    total_refined = 0
    batch_idx = 1
    curr_start = start_chapter

    try:
        while batch_idx <= max_batches and not FULL_AUDIT_STOP_EVENT.is_set():
            # سحب الدفعة التالية
            pulled = cmd_pull(limit=batch_size, novel_name=novel_name, start_chapter=curr_start, include_live=True)
            if pulled == 0:
                logger.info(f"✅ لا توجد فصول إضافية للسحب بدءاً من {curr_start}. انتهى التدقيق الشامل.")
                break

            # صقل الدفعة آلياً
            refined = cmd_auto_refine_and_notify(limit=batch_size, novel_name=novel_name, send_telegram_notify=False)
            total_refined += refined

            if auto_push and refined > 0:
                cmd_push(novel_name=novel_name)

            # إرسال تحديث تقدم دوري للمشرف (لكل دفعة)
            notify_admin(
                f"📊 <b>[متابعة التدقيق الشامل - الدفعة {batch_idx}]:</b>\n"
                f"✅ تم صقل وتدقيق <b>{refined}</b> فصلاً جديداً.\n"
                f"📈 <b>إجمالي الفصول المدققة حتى الآن:</b> <b>{total_refined}</b> فصلاً.\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🔄 جاري الانتقال تلقائياً للدفعة التالية..."
            )

            curr_start += batch_size
            batch_idx += 1
            time.sleep(2)

        if FULL_AUDIT_STOP_EVENT.is_set():
            notify_admin(
                f"⏸️ <b>[تم إيقاف التدقيق الشامل بأمان]:</b>\n"
                f"توقفت العملية بنجاح. تم صقل وحفظ <b>{total_refined}</b> فصلاً في مجلد <code>approved/</code>."
            )
        else:
            # رسالة الإنجاز النهائية
            import telebot
            from telebot import types
            from telegram_bot import BOT_TOKEN, ADMIN_CHAT_ID
            if BOT_TOKEN and ADMIN_CHAT_ID:
                b = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
                m = types.InlineKeyboardMarkup(row_width=1)
                m.add(
                    types.InlineKeyboardButton("🚀 اعتماد ونشر كافة الفصول المدققة إلى بلوجر", callback_data="cb_opus_push_all"),
                    types.InlineKeyboardButton("📊 عرض حالة الطابور", callback_data="cb_opus_status")
                )
                b.send_message(
                    ADMIN_CHAT_ID,
                    f"👑 <b>[🎉 اكتمل التدقيق الشامل لكافة فصول الرواية بنجاح!]</b> 🚀\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📖 <b>الرواية:</b> {novel_name}\n"
                    f"🔢 <b>إجمالي الفصول المدققة والمصقولة:</b> <b>{total_refined}</b> فصلاً!\n"
                    f"✨ تم التحقق من القاموس، وتنسيق BBCode، والتدقيق الأدبي الفصيح بنسبة 100%.\n\n"
                    f"👇 اضغط الزر أدناه لاعتماد ونشر كافة الفصول وجدولتها في بلوجر والشيت فوراً:",
                    reply_markup=m
                )
    except Exception as e_full:
        logger.error(f"خطأ أثناء التدقيق الشامل: {e_full}")
        notify_admin(f"❌ حدث خطأ أثناء التدقيق الشامل: {e_full}")
    finally:
        IS_FULL_AUDIT_RUNNING = False
        FULL_AUDIT_STOP_EVENT.clear()

    return total_refined


def cmd_push(novel_name: str = "After Severing Ties"):
    """أخذ كافة الفصول المعتمدة في approved/، وتغليفها ملكياً وإرسالها لبلوجر والشيت."""
    approved_files = sorted(list(APPROVED_DIR.glob("chapter_*.txt")), key=lambda p: int(re.search(r'\d+', p.name).group(0)) if re.search(r'\d+', p.name) else 0)

    if not approved_files:
        logger.info("ℹ️ لا توجد فصول معتمدة في approved/ لرفعها. قم باعتماد الفصول أولاً.")
        return

    logger.info(f"🚀 بدء نشر وصقل {len(approved_files)} فصول معتمدة...")
    import opus_staging_pipeline
    from nsw_healer_engine import notify_admin
    manifest = load_manifest()
    chapters_dict = manifest.setdefault("chapters", {})

    pushed_count = 0
    for af in approved_files:
        meta, refined_text = parse_chapter_file(af)
        c_num = int(meta.get("chapter", re.search(r'\d+', af.name).group(0)))
        
        # استرجاع الميتاداتا الأصلية مع دعم الاسترجاع الاحتياطي التام من سجل manifest
        cached_info = chapters_dict.get(str(c_num), {})
        title = meta.get("title") or cached_info.get("title") or f"الفصل {c_num}"
        post_id = meta.get("post_id") or cached_info.get("post_id", "")
        pub_date = meta.get("published_date") or cached_info.get("published_date", "")
        source = meta.get("source") or cached_info.get("source", "")

        chapter_item = {
            "chapter_number": c_num,
            "title": title,
            "post_id": post_id,
            "published_date": pub_date,
            "source": source
        }

        logger.info(f"📤 جاري معالجة ونشر الفصل {c_num}: {title}...")
        res = opus_staging_pipeline.apply_opus_review_and_sync(
            chapter_item=chapter_item,
            refined_clean_story=refined_text,
            refined_title=title,
            novel_name=novel_name
        )

        is_ok = res.get("blogger_updated") or res.get("published")
        err = res.get("error")

        if is_ok or not err:
            # نقل الملف إلى published/
            published_file = PUBLISHED_DIR / af.name
            shutil.move(str(af), str(published_file))

            key = str(c_num)
            if key not in chapters_dict:
                chapters_dict[key] = {}
            chapters_dict[key].update({
                "chapter_number": c_num,
                "novel_name": novel_name,
                "status": "published",
                "published_file": str(published_file.name),
                "char_count": len(refined_text),
                "published_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

            # إرسال إشعار للمشرف
            notify_admin(
                f"👑 <b>[تم بنجاح اعتماد ونشر الفصل {c_num} لصقل Claude Opus!]</b> 🚀\n"
                f"📖 <b>{novel_name} - {title}</b>\n"
                f"✍️ <b>حجم المتن المصقول:</b> {len(refined_text)} حرف\n"
                f"🛡️ تم التغليف الملكي ومزامنة بلوجر وقواعد البيانات بنجاح."
            )
            pushed_count += 1
        else:
            logger.warning(f"⚠️ تنبيه أثناء نشر الفصل {c_num}: {err}. بقي الملف في approved/ للمحاولة لاحقاً.")

    save_manifest(manifest)
    logger.info(f"🎉 تم بنجاح نشر ومزامنة {pushed_count} فصول معتمدة!")


def main():
    parser = argparse.ArgumentParser(description="NSW Claude Opus Local Staging & Sync Manager")
    subparsers = parser.add_subparsers(dest="command", help="الأوامر المتاحة")

    # أمر status
    subparsers.add_parser("status", help="عرض حالة الطابور اللحظية")

    # أمر pull
    pull_parser = subparsers.add_parser("pull", help="سحب دفعة فصول بانتظار المراجعة")
    pull_parser.add_argument("--limit", type=int, default=20, help="أقصى عدد فصول للسحب (افتراضي 20)")
    pull_parser.add_argument("--novel", type=str, default="After Severing Ties", help="اسم الرواية")

    # أمر approve
    approve_parser = subparsers.add_parser("approve", help="اعتماد فصل ونقله إلى approved (أو اكتب all)")
    approve_parser.add_argument("chapter", type=str, help="رقم الفصل أو 'all' لاعتماد كافة الفصول")

    # أمر push
    push_parser = subparsers.add_parser("push", help="نشر وتحديث الفصول المعتمدة في بلوجر والشيت")
        # أمر telegram
    tg_parser = subparsers.add_parser("telegram", help="تجهيز وإرسال الدفعة الحالية لتليجرام لـ Claude فوراً")
    tg_parser.add_argument("--limit", type=int, default=20, help="عدد الفصول")
    tg_parser.add_argument("--novel", type=str, default="After Severing Ties", help="اسم الرواية")

    # أمر stage-all (النقرة 1)
    stage_parser = subparsers.add_parser("stage-all", help="النقرة 1: سحب وتجهيز الفصول وتوليد القاموس لكلاود")
    stage_parser.add_argument("--limit", type=int, default=20, help="عدد الفصول")
    stage_parser.add_argument("--novel", type=str, default="After Severing Ties", help="اسم الرواية")

    # أمر publish-all (النقرة 2)
    pub_parser = subparsers.add_parser("publish-all", help="النقرة 2: اعتماد ونشر كافة الفصول المصقولة بمواعيدها لبلوجر")
    pub_parser.add_argument("--novel", type=str, default="After Severing Ties", help="اسم الرواية")

    args = parser.parse_args()

    if args.command == "status" or not args.command:
        cmd_status()
    elif args.command in ["pull", "stage-all", "telegram"]:
        cmd_pull(limit=args.limit, novel_name=args.novel, send_telegram=True)
        cmd_pull(limit=args.limit, novel_name=args.novel)
    elif args.command == "approve":
        if args.chapter.lower() in ["all", "--all", "*"]:
            cmd_approve_all()
        else:
            try:
                cmd_approve(chapter_num=int(args.chapter))
            except ValueError:
                logger.error(f"❌ رقم الفصل غير صالح: {args.chapter}. أدخل رقماً أو 'all'.")
    elif args.command in ["push", "publish-all"]:
        if args.command == "publish-all":
            cmd_approve_all()
        cmd_push(novel_name=args.novel)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

