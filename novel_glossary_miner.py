# -*- coding: utf-8 -*-
"""
==============================================================================
NSW Pre-Translation Novel Glossary Miner & Batch Extractor v1.0
==============================================================================
محرك استخراج وتعدين قاموس الرواية الشامل قبل بدء الترجمة:
1. مسح نصوص الفصول الصينية الأصلية (من SQLite أو الملفات).
2. كشف الأسماء والمصطلحات المتكررة عبر الفصول (2 إلى 4 أحرف صينية).
3. فلترة الكلمات الشائعة وحروف الجر الصينية.
4. تجهيز دفعة مصنفة ومعدة لـ Claude Opus / Gemini لتوليد:
   - التعريب البليغ للأذن العربية (Pinyin صوتي للشخصيات، وترجمة دلالية فخمة للتقنيات والمواقع).
   - التصنيف (Character, Location, Organization, Technique, Rank).
   - الجنس (ذكر / أنثى / غير محدد).
5. التصدير كـ CSV جاهز للرفع المباشر إلى جدول القاموس المعتمد (1oqK...).
"""

import os
import re
import sys
import json
import sqlite3
from typing import Dict, List, Any, Set, Tuple
from collections import Counter

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# قائمة المقاطع التوجيهية للأسماء والألقاب الصينية الأكثر شيوعاً
CHINESE_SURNAMES = {
    "陈", "楚", "李", "王", "张", "刘", "赵", "诸葛", "司马", "欧阳", "慕容",
    "东方", "独孤", "南宫", "令狐", "西门", "林", "叶", "萧", "秦", "周", "吴",
    "韩", "杨", "徐", "朱", "孙", "马", "郭", "何", "高", "罗", "唐", "梁", "宋"
}

# لواحق التصنيفات (أماكن، طوائف، تقنيات، رتب)
LOCATION_SUFFIXES = ("城", "府", "山", "州", "界", "郡", "村", "坊", "堂", "阁", "楼", "殿", "国", "海", "域", "谷", "林", "岛", "原")
ORGANIZATION_SUFFIXES = ("宗", "门", "帮", "派", "会", "教", "院", "司", "卫", "朝", "行", "庄", "商会", "医馆")
TECHNIQUE_SUFFIXES = ("诀", "经", "功", "法", "掌", "拳", "剑", "刀", "步", "印", "指", "腿", "术", "阵", "式", "典", "图", "针")
RANK_SUFFIXES = ("王", "皇", "帝", "君", "尊", "侯", "公", "世子", "长老", "宗主", "师尊", "殿下", "陛下", "大人", "圣子", "神女", "将军", "状元")

# كلمات التوقف الصينية المستبعدة
CHINESE_STOPWORDS = {
    "一个", "他们", "我们", "自己", "什么", "怎么", "没有", "这时", "虽然",
    "如果", "知道", "看着", "说道", "听到", "现在", "不是", "就是", "这个时候", "在这个",
    "随着", "因为", "所以", "不过", "然而", "突然", "只见", "随后", "而且", "最后"
}


def scan_novel_chapters_from_db(novel_name: str = "", limit_chapters: int = 100, db_path: str = "novel_scraper.db") -> List[Tuple[int, str]]:
    """قراءة نصوص الفصول الصينية المحفوظة في قاعدة البيانات المحلية."""
    if not os.path.exists(db_path):
        return []
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    if novel_name:
        c.execute("SELECT id FROM novels WHERE title LIKE ? LIMIT 1;", (f"%{novel_name}%",))
        nov_row = c.fetchone()
        novel_id = nov_row[0] if nov_row else 1
        c.execute("SELECT chapter_number, content FROM chapters WHERE novel_id=? ORDER BY chapter_number ASC LIMIT ?;", (novel_id, limit_chapters))
    else:
        c.execute("SELECT chapter_number, content FROM chapters ORDER BY chapter_number ASC LIMIT ?;", (limit_chapters,))
        
    rows = c.fetchall()
    conn.close()
    return rows


def extract_potential_glossary_terms(chapters_data: List[Tuple[int, str]], min_chapter_occurrences: int = 2) -> List[Dict[str, Any]]:
    """
    استخراج الكلمات المرشحة لتكون أسماء أو مصطلحات تكررت عبر فصول متعددة.
    """
    term_chapter_map: Dict[str, Set[int]] = {}
    term_total_count: Counter = Counter()

    name_regex = re.compile(r'[\u4e00-\u9fa5]{2,4}')

    for ch_num, text in chapters_data:
        if not text:
            continue

        matches = name_regex.findall(text)
        seen_in_chapter = set()

        for term in matches:
            if term in CHINESE_STOPWORDS or len(term) < 2:
                continue

            # التحقق من مؤشرات الأسماء أو المصطلحات
            is_candidate = False
            term_type = "Generic"

            # أ) يبدأ بلقب عائلة معروف
            if any(term.startswith(surname) for surname in CHINESE_SURNAMES) and len(term) in (2, 3, 4):
                is_candidate = True
                term_type = "Character"

            # ب) ينتهي بلاحقة رتبة أو منصب
            elif any(term.endswith(sfx) for sfx in RANK_SUFFIXES):
                is_candidate = True
                term_type = "Rank"

            # ج) ينتهي بلاحقة مكان
            elif any(term.endswith(sfx) for sfx in LOCATION_SUFFIXES):
                is_candidate = True
                term_type = "Location"

            # د) ينتهي بلاحقة طائفة أو منظمة
            elif any(term.endswith(sfx) for sfx in ORGANIZATION_SUFFIXES):
                is_candidate = True
                term_type = "Organization"

            # هـ) ينتهي بلاحقة فن قتالي أو تقنية
            elif any(term.endswith(sfx) for sfx in TECHNIQUE_SUFFIXES):
                is_candidate = True
                term_type = "Technique"

            if is_candidate:
                seen_in_chapter.add(term)
                term_total_count[term] += 1
                if term not in term_chapter_map:
                    term_chapter_map[term] = set()
                term_chapter_map[term].add(ch_num)

    # فلترة الكلمات التي ظهرت في فصول متعددة
    mined_candidates = []
    for term, ch_set in term_chapter_map.items():
        if len(ch_set) >= min_chapter_occurrences:
            # تخمين نوع أولي
            guessed_category = "Character"
            if any(term.endswith(sfx) for sfx in RANK_SUFFIXES): guessed_category = "Rank"
            elif any(term.endswith(sfx) for sfx in LOCATION_SUFFIXES): guessed_category = "Location"
            elif any(term.endswith(sfx) for sfx in ORGANIZATION_SUFFIXES): guessed_category = "Organization"
            elif any(term.endswith(sfx) for sfx in TECHNIQUE_SUFFIXES): guessed_category = "Technique"

            mined_candidates.append({
                "term": term,
                "chapter_count": len(ch_set),
                "total_occurrences": term_total_count[term],
                "guessed_category": guessed_category,
                "first_seen_chapter": min(ch_set),
                "last_seen_chapter": max(ch_set)
            })

    # ترتيب النتائج بالأكثر تكراراً عبر الفصول
    mined_candidates.sort(key=lambda x: (x["chapter_count"], x["total_occurrences"]), reverse=True)
    return mined_candidates


def build_claude_enrichment_prompt(candidates: List[Dict[str, Any]], novel_name: str, max_terms: int = 50) -> str:
    """
    بناء طلب فوري لكلاود (Claude Opus) لاستكمال وإثراء معلومات القاموس.
    """
    terms_list = candidates[:max_terms]
    terms_str = "\n".join([f"- {item['term']} (الفئة المقترحة: {item['guessed_category']} | تكررت في {item['chapter_count']} فصلاً)" for item in terms_list])

    prompt = f"""أنت خبير تعريب روايات صينية وناقد أدبي رفيع. 
لدينا قائمة بالمصطلحات الصينية الأكثر تكراراً المستخرجة آلياً من رواية '{novel_name}'.
المطلوب إكمال وتدقيق بيانات كل مصطلح لإضافتها إلى شيت القاموس الرسمي، مع مراعاة القواعد التالية:
1. الأسماء الصينية للشخصيات تُعرب صوتياً بدقة Pinyin وتحدد جنس الشخصية (ذكر / أنثى).
2. التقنيات والفنون القتالية تُعرب بطريقة فخمة وجزلة تناسب الأذن العربية (مثل: 'فن سيف الغسق' بدلاً من ترجمة حرفية ركيكة).
3. الأماكن والطوائف والمناصب تُترجم بدقة دلالية واضحة.

قائمة المصطلحات:
{terms_str}

أرجع النتيجة حصراً بصيغة JSON كالتالي:
```json
[
  {{
    "OriginalTerm": "المصطلح الصيني",
    "ArabicTranslation": "التعريب المعتمد",
    "Category": "Character / Location / Organization / Technique / Rank / Specialized Term",
    "Gender": "ذكر / أنثى / غير محدد",
    "Notes": "ملاحظة توضيحية مختصرة إن وجدت"
  }}
]
```"""
    return prompt


def export_mined_terms_to_csv(terms: List[Dict[str, Any]], output_path: str, novel_name: str = "After Severing Ties"):
    """تصدير المصطلحات المستخرجة كملف CSV جاهز."""
    with open(output_path, "w", encoding="utf-8-sig") as f:
        f.write("NovelName,OriginalTerm,ArabicTranslation,Category,Gender,ChapterCount,TotalOccurrences\n")
        for item in terms:
            f.write(f'"{novel_name}","{item["term"]}","","{item["guessed_category"]}","", {item["chapter_count"]},{item["total_occurrences"]}\n')


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="NSW Novel Glossary Miner")
    parser.add_argument("--novel", default="After Severing Ties", help="Novel name to mine")
    parser.add_argument("--chapters", type=int, default=50, help="Number of chapters to scan")
    parser.add_argument("--min_occurrences", type=int, default=2, help="Minimum chapter occurrences")
    parser.add_argument("--output", default="mined_glossary_candidates.csv", help="Output CSV path")
    parser.add_argument("--prompt", action="store_true", help="Print Claude enrichment prompt")

    args = parser.parse_args()

    print(f"🔍 جاري فحص الفصول الصينية لرواية '{args.novel}' (حتى {args.chapters} فصلاً)...")
    chapters = scan_novel_chapters_from_db(args.novel, args.chapters)
    print(f"📖 تم جلب {len(chapters)} فصلاً من قاعدة البيانات.")

    candidates = extract_potential_glossary_terms(chapters, args.min_occurrences)
    print(f"✨ تم اكتشاف {len(candidates)} مصطلحاً واسماً متكرراً.")

    export_mined_terms_to_csv(candidates, args.output, args.novel)
    print(f"💾 تم حفظ النتائج في: {args.output}")

    if args.prompt or len(candidates) > 0:
        p_path = "claude_glossary_prompt.txt"
        with open(p_path, "w", encoding="utf-8") as pf:
            pf.write(build_claude_enrichment_prompt(candidates, args.novel, 40))
        print(f"📝 تم تجهيز أمر التوليد لكلاود في: {p_path}")
