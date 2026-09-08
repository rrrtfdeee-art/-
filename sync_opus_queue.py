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


def cmd_pull(limit: int = 20, novel_name: str = "After Severing Ties"):
    """سحب الفصول بانتظار المراجعة وتجريدها وتفريغها في pending/."""
    logger.info(f"🚀 بدء سحب دفعة حتى {limit} فصلاً لرواية '{novel_name}'...")
    import opus_staging_pipeline
    manifest = load_manifest()
    chapters_dict = manifest.setdefault("chapters", {})

    batch = opus_staging_pipeline.fetch_pending_chapters_for_opus_review(max_chapters=limit, novel_name=novel_name)
    if not batch:
        logger.info("ℹ️ لم يتم العثور على فصول تنتظر المراجعة حالياً.")
        return

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
            "char_count": len(raw_story),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        saved_count += 1

    save_manifest(manifest)
    logger.info(f"✅ تم سحب وتجهيز {saved_count} فصلاً ناصعاً بنجاح في مجلد: {PENDING_DIR}")


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
        title = meta.get("title", f"الفصل {c_num}")
        post_id = meta.get("post_id", "")
        pub_date = meta.get("published_date", "")
        source = meta.get("source", "")

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
    approve_parser = subparsers.add_parser("approve", help="اعتماد فصل ونقله إلى approved")
    approve_parser.add_argument("chapter", type=int, help="رقم الفصل")

    # أمر push
    push_parser = subparsers.add_parser("push", help="نشر وتحديث الفصول المعتمدة في بلوجر والشيت")
    push_parser.add_argument("--novel", type=str, default="After Severing Ties", help="اسم الرواية")

    args = parser.parse_args()

    if args.command == "status" or not args.command:
        cmd_status()
    elif args.command == "pull":
        cmd_pull(limit=args.limit, novel_name=args.novel)
    elif args.command == "approve":
        cmd_approve(chapter_num=args.chapter)
    elif args.command == "push":
        cmd_push(novel_name=args.novel)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
