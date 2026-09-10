# -*- coding: utf-8 -*-
"""
==============================================================================
NSW Pre-Translation Universal Novel Glossary Miner & Batch Extractor v2.0
==============================================================================
محرك استخراج وتعدين قاموس الروايات الشامل والعالمي لكافة اللغات:
1. مسح نصوص الفصول الأصلية (إنجليزي، صيني، كوري، ياباني، أو عام) من SQLite أو الملفات.
2. كشف تلقائي ذكي للغة العمل (Auto-Detect).
3. استخراج المصطلحات وأسماء الأعلام (Capitalized Entities / Surnames) والرتب والمهارات والمواقع.
4. رصد رسائل وشاشات النظام والأمثال والتعبيرات البلاغية (Idioms & Proverbs).
5. صياغة برومبت مخصص فائق الذكاء لـ Claude Opus / Gemini للتعريب الدلالي الفصيح والصوتي.
6. تصدير CSV متوافق مع جدول القاموس المركزي (1oqK...).
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

# ----------------------------------------------------------------------
# القواعد الصينية (Chinese Rules)
# ----------------------------------------------------------------------
CHINESE_SURNAMES = {
    "陈", "楚", "李", "王", "张", "刘", "赵", "诸葛", "司马", "欧阳", "慕容",
    "东方", "独孤", "南宫", "令狐", "西门", "林", "叶", "萧", "秦", "周", "吴",
    "韩", "杨", "徐", "朱", "孙", "马", "郭", "何", "高", "罗", "唐", "梁", "宋", "江", "顾"
}

LOCATION_SUFFIXES = ("城", "府", "山", "州", "界", "郡", "村", "坊", "堂", "阁", "楼", "殿", "国", "海", "域", "谷", "林", "岛", "原")
ORGANIZATION_SUFFIXES = ("宗", "门", "帮", "派", "会", "教", "院", "司", "卫", "朝", "行", "庄", "商会", "医馆", "圣地", "世家")
TECHNIQUE_SUFFIXES = ("诀", "经", "功", "法", "掌", "拳", "剑", "刀", "步", "印", "指", "腿", "术", "阵", "式", "典", "图", "针", "秘法")
RANK_SUFFIXES = ("王", "皇", "帝", "君", "尊", "侯", "公", "世子", "长老", "宗主", "师尊", "殿下", "陛下", "大人", "圣子", "神女", "将军", "状元", "至尊", "老祖")

CHINESE_STOPWORDS = {
    "一个", "他们", "我们", "自己", "什么", "怎么", "没有", "这时", "虽然",
    "如果", "知道", "看着", "说道", "听到", "现在", "不是", "就是", "这个时候", "在这个",
    "随着", "因为", "所以", "不过", "然而", "突然", "只见", "随后", "而且", "最后", "开始", "然后", "已经", "可以"
}

# ----------------------------------------------------------------------
# القواعد الإنجليزية (English Rules)
# ----------------------------------------------------------------------
ENGLISH_STOPWORDS = {
    "The", "This", "That", "These", "Those", "Then", "After", "Before", "When", "While",
    "Where", "Why", "How", "What", "Who", "Whom", "Which", "However", "Therefore",
    "Although", "Suddenly", "Meanwhile", "Finally", "Actually", "First", "Second", "Third",
    "Because", "Since", "Unless", "Instead", "He", "She", "It", "They", "We", "You", "I",
    "His", "Her", "Their", "Our", "My", "Your", "Its", "And", "But", "Or", "So", "Yet",
    "For", "Nor", "As", "At", "By", "In", "Of", "On", "To", "With", "From", "Chapter",
    "Page", "Volume", "Book", "Part", "Prologue", "Epilogue", "Author", "Note", "One",
    "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Just", "Even",
    "Only", "Also", "Still", "Never", "Always", "Sometimes", "Often", "Come", "Go", "Look",
    "See", "Say", "Tell", "Think", "Know", "Feel", "Want", "Need", "Like", "Good", "Bad",
    "Yes", "No", "Not", "All", "Any", "Every", "Some", "Many", "Much", "More", "Most"
}

EN_TITLES = [
    "Lord", "Lady", "Duke", "Duchess", "King", "Queen", "Emperor", "Empress", "Prince", "Princess",
    "Master", "Grandmaster", "Elder", "Great Elder", "Patriarch", "Sect Master", "Clan Leader",
    "Guild Leader", "Senior", "Junior", "Brother", "Sister", "General", "Commander", "Captain",
    "Archmage", "Saint", "Saintess", "High Priest", "Priest", "Knight", "Sir", "Baron", "Count",
    "Viscount", "Marquis", "Sovereign", "Monarch", "Overlord", "Supreme", "God", "Goddess",
    "Hero", "Vanguard", "Marshal", "Guardian", "Warden"
]

EN_LOCATIONS = [
    "City", "Town", "Village", "Kingdom", "Empire", "Continent", "Province", "County",
    "Mountain", "Peak", "Range", "Valley", "River", "Lake", "Sea", "Ocean", "Forest",
    "Plain", "Desert", "Island", "Cave", "Abyss", "Domain", "Realm", "World", "Palace",
    "Castle", "Fortress", "Tower", "Pavilion", "Temple", "Shrine", "Sanctuary", "Manor", "Hall"
]

EN_ORGS = [
    "Sect", "Clan", "Guild", "Family", "Alliance", "Association", "Order", "Union", "League",
    "Legion", "Corps", "House", "Chamber", "Pavilion", "Court", "Academy", "Institute",
    "Syndicate", "Faction", "Church", "Cult"
]

EN_TECHNIQUES = [
    "Art", "Sword", "Blade", "Saber", "Spear", "Palm", "Fist", "Claw", "Finger", "Step", "Steps",
    "Slash", "Strike", "Manual", "Scripture", "Canon", "Sutra", "Mantra", "Technique", "Skill",
    "Spell", "Magic", "Formation", "Array", "Rune", "Method", "Formula", "Stance", "Style"
]

EN_RANKS = [
    "Realm", "Stage", "Level", "Layer", "Tier", "Rank", "Grade", "Class", "Core",
    "Qi Condensation", "Foundation Establishment", "Core Formation", "Nascent Soul",
    "Soul Transformation", "Void Refinement", "Ascension", "Martial Master", "Overlord"
]

FAMOUS_EN_IDIOMS = [
    # أمثال فانتازية وروايات صينية/آسيوية مترجمة للإنجليزية (Webnovel & Cultivation Staples)
    "Toad wanting to eat swan meat", "Toad lusting after swan meat", "Toad dreaming of swan meat",
    "Have eyes but fail to see Mount Tai", "Have eyes but cannot see Mount Tai", "Eyes but no pupils",
    "Courting death", "Seeking death",
    "Not knowing the immensity of heaven and earth", "Doesn't know the height of the sky and depth of the earth",
    "Mantis stalks the cicada", "Mantis catching the cicada", "Oriole behind",
    "Refusing a toast only to drink a forfeit", "Refusing a toast only to drink a penalty",
    "Strike a stone with an egg", "Throwing eggs against a rock", "Egg hitting a stone",
    "Draw a snake and add feet", "Adding legs to a snake",
    "Stealing a chicken only to lose the rice", "Steal a chicken and lose the rice",
    "Luring the tiger out of the mountain", "Lure the tiger off its mountain",
    "Borrowing a knife to kill", "Borrowing a dagger to slay",
    "Fish in troubled waters", "Fishing in muddy waters",
    "Hanging a sheep head to sell dog meat", "Selling dog meat while hanging sheep head",
    "Playing lute to a cow", "Playing the zither to a bull",
    "Vomiting blood in anger", "Spitting blood", "Spurting blood from fury",
    "Tiger entering a flock of sheep", "Like a wolf among sheep",
    "Paper tiger", "Toothless tiger",
    "Dragon among men", "Phoenix among women",
    "Golden scale in a shallow pool", "Dragon trapped in shallow waters",
    "Digging one's own grave", "Digging your own grave",
    "Reap what you sow", "You reap what you sow",
    "Drop in the ocean", "Drop in the bucket",
    "Pouring oil on the fire", "Adding fuel to the flames",
    "Between a rock and a hard place",
    
    # أمثال وتعبيرات إنجليزية مجازية شائعة (Classic Literary Idioms)
    "Double-edged sword", "Tip of the iceberg", "Wolf in sheep's clothing",
    "Play with fire", "Playing with fire", "Add insult to injury", "Bite the dust", "Turn a blind eye",
    "Barking up the wrong tree", "Burn bridges", "Burning bridges", "Calm before the storm",
    "Face the music", "Hit the nail on the head", "Kill two birds with one stone",
    "Piece of cake", "Through thick and thin", "Walking on thin ice", "Spill the beans",
    "Blessing in disguise", "Once in a blue moon", "Eye for an eye", "Bite the bullet",
    "Bite off more than you can chew", "Throw in the towel", "Elephant in the room",
    "Storm in a teacup", "Water under the bridge", "A wild goose chase", "Walking on eggshells"
]


def detect_novel_language(chapters_data: List[Tuple[int, str]]) -> str:
    """كشف تلقائي للغة الرواية بناء على عينة من الفصول."""
    sample = ""
    for _, text in chapters_data[:5]:
        sample += " " + (text or "")
    if not sample:
        return "en"

    total = len(sample) or 1
    zh_count = len(re.findall(r'[\u4e00-\u9fa5]', sample))
    ko_count = len(re.findall(r'[\uac00-\ud7af]', sample))
    ja_count = len(re.findall(r'[\u3040-\u30ff]', sample))
    en_count = len(re.findall(r'[a-zA-Z]', sample))

    if ko_count / total > 0.03:
        return "ko"
    if ja_count / total > 0.03:
        return "ja"
    if zh_count / total > 0.05:
        return "zh"
    if en_count > 50:
        return "en"
    return "universal"


def scan_novel_chapters_from_db(novel_name: str = "", limit_chapters: int = 100, db_path: str = "novel_scraper.db") -> List[Tuple[int, str]]:
    """قراءة نصوص الفصول المحفوظة في قاعدة البيانات المحلية."""
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



def fetch_central_glossary_terms(novel_name: str = None, sheet_id: str = "1oqKRLyqWdkdUWW5UtvorEteFk3jJXdeUzQGDv-XJ_aE") -> Set[str]:
    """جلب المصطلحات المسجلة مسبقاً لرواية معينة من جدول القاموس المركزي لاستبعادها."""
    import urllib.request
    existing = set()
    try:
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:json"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read().decode('utf-8')
            m = re.search(r'google\.visualization\.Query\.setResponse\((.*)\);', content, re.DOTALL)
            if m:
                data = json.loads(m.group(1))
                rows = data.get('table', {}).get('rows', [])
                clean_target = (novel_name or '').strip().lower()
                for r in rows:
                    cells = r.get('c', [])
                    c0 = str(cells[0].get('v', '') if len(cells) > 0 and cells[0] else '').strip().lower()
                    c1 = str(cells[1].get('v', '') if len(cells) > 1 and cells[1] else '').strip()
                    if c1:
                        if not clean_target or clean_target in c0 or c0 in clean_target:
                            existing.add(c1.lower())
    except Exception as e:
        print(f"⚠️ تعذر تحميل المصطلحات المسبقة من الشيت المركزي: {e}")
    return existing

def extract_potential_glossary_terms(chapters_data: List[Tuple[int, str]], lang: str = "auto", min_chapter_occurrences: int = 2, exclude_terms: Set[str] = None) -> Tuple[str, List[Dict[str, Any]], List[str]]:
    """
    استخراج الكلمات المرشحة لتكون أسماء أو مصطلحات أو أمثال متكررة عبر فصول متعددة.
    تدعم اللغات العالمية بذكاء.
    """
    if lang == "auto":
        actual_lang = detect_novel_language(chapters_data)
    else:
        actual_lang = lang

    term_chapter_map: Dict[str, Set[int]] = {}
    term_total_count: Counter = Counter()
    term_category_map: Dict[str, str] = {}
    extracted_idioms: List[str] = []

    if actual_lang == "zh":
        name_regex = re.compile(r'[\u4e00-\u9fa5]{2,4}')
        for ch_num, text in chapters_data:
            if not text: continue
            matches = name_regex.findall(text)
            seen_in_chapter = set()
            for term in matches:
                if term in CHINESE_STOPWORDS or len(term) < 2: continue
                is_candidate = False
                term_type = "Generic"

                if any(term.startswith(surname) for surname in CHINESE_SURNAMES) and len(term) in (2, 3, 4):
                    is_candidate = True; term_type = "Character"
                elif any(term.endswith(sfx) for sfx in RANK_SUFFIXES):
                    is_candidate = True; term_type = "Rank"
                elif any(term.endswith(sfx) for sfx in LOCATION_SUFFIXES):
                    is_candidate = True; term_type = "Location"
                elif any(term.endswith(sfx) for sfx in ORGANIZATION_SUFFIXES):
                    is_candidate = True; term_type = "Organization"
                elif any(term.endswith(sfx) for sfx in TECHNIQUE_SUFFIXES):
                    is_candidate = True; term_type = "Technique"

                if is_candidate:
                    seen_in_chapter.add(term)
                    term_total_count[term] += 1
                    term_category_map[term] = term_type
                    if term not in term_chapter_map: term_chapter_map[term] = set()
                    term_chapter_map[term].add(ch_num)

    elif actual_lang == "en":
        for _, text in chapters_data:
            if not text: continue
            for idm in FAMOUS_EN_IDIOMS:
                if re.search(r'\b' + re.escape(idm) + r'\b', text, re.I) and idm not in extracted_idioms:
                    extracted_idioms.append(idm)

        for ch_num, text in chapters_data:
            if not text: continue
            # رسائل النظام بين أقواس
            brackets = re.findall(r'\[([A-Z0-9a-z\s:_\-–\'’]{3,45})\]|【([A-Z0-9a-z\s:_\-–\'’]{3,45})】', text)
            for b in brackets:
                clean = (b[0] or b[1]).strip()
                if clean and not clean.lower().startswith("chapter") and len(clean) >= 3:
                    if clean not in term_chapter_map: term_chapter_map[clean] = set()
                    term_chapter_map[clean].add(ch_num)
                    term_total_count[clean] += 2
                    term_category_map[clean] = "System / Special Term"

            # أسماء الأعلام والعبارات المركبة (2 إلى 4 كلمات)
            phrases = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\b', text)
            for phrase in phrases:
                words = phrase.strip().split()
                if words[0] in ENGLISH_STOPWORDS and words[0] not in EN_TITLES:
                    words.pop(0)
                clean_term = " ".join(words)
                if len(clean_term) < 3 or clean_term in ENGLISH_STOPWORDS:
                    continue

                cat = "Specialized Term"
                if any(t in clean_term for t in EN_TITLES): cat = "Character"
                elif any(k in clean_term for k in EN_ORGS): cat = "Organization"
                elif any(k in clean_term for k in EN_LOCATIONS): cat = "Location"
                elif any(k in clean_term for k in EN_TECHNIQUES): cat = "Technique"
                elif any(k in clean_term for k in EN_RANKS): cat = "Rank"
                elif len(words) == 2 and any(w not in ENGLISH_STOPWORDS for w in words): cat = "Character"

                if clean_term not in term_chapter_map: term_chapter_map[clean_term] = set()
                term_chapter_map[clean_term].add(ch_num)
                term_total_count[clean_term] += 1
                term_category_map[clean_term] = cat

            # الكلمات المفردة المكتوبة بحرف كبير (شرط أن تأتي في منتصف الجملة مسبوقة بكلمة بحروف صغيرة)
            mid_words = re.findall(r'\b[a-z]{2,}\s+([A-Z][a-z]{2,})\b', text)
            for word in mid_words:
                if word in ENGLISH_STOPWORDS: continue
                if word in ["Dao", "Buddha", "Yin", "Demon", "Cultivator", "Cultivators", "Immortal", "Immortals"]:
                    if word not in term_chapter_map: term_chapter_map[word] = set()
                    term_chapter_map[word].add(ch_num)
                    term_total_count[word] += 1
                    term_category_map[word] = "Specialized Term"

    else:
        # لغة عامة / كوري / ياباني
        pattern = re.compile(r'[\uac00-\ud7af]{2,6}|[\u30a0-\u30ff]{2,8}|\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b')
        for ch_num, text in chapters_data:
            if not text: continue
            for match in pattern.findall(text):
                t = match.strip()
                if len(t) < 2: continue
                if t not in term_chapter_map: term_chapter_map[t] = set()
                term_chapter_map[t].add(ch_num)
                term_total_count[t] += 1
                term_category_map[t] = "Character / Specialized Term"

    # فلترة النتائج المتكررة
    mined_candidates = []
    for term, ch_set in term_chapter_map.items():
        if len(ch_set) >= min_chapter_occurrences or term_total_count[term] >= 3:
            mined_candidates.append({
                "term": term,
                "chapter_count": len(ch_set),
                "total_occurrences": term_total_count[term],
                "guessed_category": term_category_map.get(term, "Generic"),
                "first_seen_chapter": min(ch_set),
                "last_seen_chapter": max(ch_set)
            })

    mined_candidates.sort(key=lambda x: (x["chapter_count"], x["total_occurrences"]), reverse=True)
    return actual_lang, mined_candidates, extracted_idioms


def build_claude_enrichment_prompt(candidates: List[Dict[str, Any]], novel_name: str, idioms: List[str] = None, lang: str = "en", max_terms: int = 50) -> str:
    """
    بناء طلب فوري لكلاود (Claude Opus) لاستكمال وإثراء معلومات القاموس وفق لغة العمل.
    """
    terms_list = candidates[:max_terms]
    terms_str = "\n".join([f"- {item['term']} (الفئة المقترحة: {item['guessed_category']} | تكررت في {item['chapter_count']} فصلاً)" for item in terms_list])

    idioms_str = ""
    if idioms:
        idioms_str = "=== [قسم الأمثال والتعبيرات الاصطلاحية (Idioms & Proverbs)] ===\n"
        for idm in idioms[:15]:
            idioms_str += f"- {idm} (الفئة: Proverb / Idiom | تعبير اصطلاحي/مثل)\n"
        idioms_str += "\n"

    lang_desc = {
        "en": "الإنجليزية 🇬🇧",
        "zh": "الصينية 🇨🇳",
        "ko": "الكورية 🇰🇷",
        "ja": "اليابانية 🇯🇵",
        "universal": "العالمية 🌍"
    }.get(lang, "العالمية")

    if lang == "en":
        rules = """1. أسماء الشخصيات الأجنبية والغربية: تُعرب صوتياً بدقة وسلاسة للأذن العربية الفصحى مع التشكيل، وتحديد جنس الشخصية (ذكر / أنثى).
2. التقنيات والفنون والمهارات القتالية والسحرية: تُعرب بأسلوب فخم وجزل وبلاغي (مثلاً: 'فن سيف الصقيع السماوي' بدلاً من ترجمة حرفية ركيكة).
3. الطوائف والمنظمات والمواقع: تُترجم بدقة دلالية ومصطلحات متناسقة.
4. الحكم والأمثال والتعبيرات المجازية (Idioms, Proverbs & Metaphors):
   - سواء كانت أمثالاً إنجليزية عامة أو حكماً وتعبيرات فانتازية/صينية مترجمة (مثل: 'Courting death' -> 'يستعجل حتفه / يلتمس الهلاك'، و 'Toad wanting swan meat' -> 'أمنية غراب في كبد السماء'، و 'Mount Tai' -> 'الطود الأشم').
   - تجنب الترجمة الحرفية تماماً واستبدالها بما يماثلها في البلاغة وفصاحة لسان العرب.
   - [صياد الحكم والأمثال]: إذا رصدت في الفصول أي حكمة أو مثل أو تعبير مجازي إضافي، قم بإضافته للنتيجة مع شرح معناه في خانة Notes."""
    elif lang == "zh":
        rules = """1. الأسماء الصينية للشخصيات تُعرب صوتياً بدقة Pinyin وتحدد جنس الشخصية (ذكر / أنثى).
2. التقنيات والفنون القتالية ومستويات الزراعة تُعرب بطريقة فخمة وجزلة تناسب الأذن العربية.
3. الأماكن والطوائف والمناصب تُترجم بدقة دلالية واضحة ومصطلحات متناسقة.
4. الأمثال والحكم الصينية (成语 / 俗语): تُعرب بلاغياً بما يعكس معناها الفصيح مع شرح موجز في الملاحظات."""
    else:
        rules = """1. أسماء الشخصيات: تعريب صوتي دقيق مع ضبط النطق وتحديد الجنس.
2. المهارات والرتب والمناصب: ترجمة دلالية فصيحة ومصطلحات متناسقة.
3. المواقع والمنظمات: دقة دلالية واضحة.
4. الأمثال: ترجمة بلاغية لما يقابلها في العربية الفصحى."""

    prompt = f"""أنت خبير تعريب روايات عالمية وأديب ومترجم فوري معتمد من أعلى المستويات.
لدينا قائمة بأهم المصطلحات والشخصيات المستخرجة آلياً من رواية باللغة [{lang_desc}] بعنوان '{novel_name}'.

المطلوب إكمال وتدقيق بيانات كل مصطلح لإضافتها إلى شيت القاموس المعتمد للرواية، مع مراعاة القواعد التالية:
{rules}

قائمة المصطلحات:
{idioms_str}{terms_str}

أرجع النتيجة حصراً بصيغة JSON كالتالي:
```json
[
  {{
    "OriginalTerm": "المصطلح الأصلي",
    "ArabicTranslation": "التعريب المعتمد البليغ",
    "Category": "Character / Location / Organization / Technique / Rank / Proverb / Idiom / Specialized Term",
    "Gender": "ذكر / أنثى / غير محدد",
    "Notes": "ملاحظة توضيحية أو شرح المثل إن وجد"
  }}
]
```"""
    return prompt


def export_mined_terms_to_csv(terms: List[Dict[str, Any]], output_path: str, novel_name: str = "After Severing Ties"):
    """تصدير المصطلحات المستخرجة كملف CSV جاهز للشيت."""
    with open(output_path, "w", encoding="utf-8-sig") as f:
        f.write("NovelName,OriginalTerm,ArabicTranslation,Category,Gender,ChapterCount,TotalOccurrences\n")
        for item in terms:
            f.write(f'"{novel_name}","{item["term"]}","","{item["guessed_category"]}","", {item["chapter_count"]},{item["total_occurrences"]}\n')


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="NSW Universal Novel Glossary Miner v2.0")
    parser.add_argument("--novel", default="After Severing Ties", help="Novel name to mine")
    parser.add_argument("--lang", default="auto", choices=["auto", "en", "zh", "ko", "ja", "universal"], help="Source language")
    parser.add_argument("--chapters", type=int, default=50, help="Number of chapters to scan")
    parser.add_argument("--min_occurrences", type=int, default=2, help="Minimum chapter occurrences")
    parser.add_argument("--output", default="mined_glossary_candidates.csv", help="Output CSV path")
    parser.add_argument("--prompt", action="store_true", help="Print Claude enrichment prompt")

    args = parser.parse_args()

    print(f"🔍 فحص فصول الرواية [{args.novel}] من قاعدة البيانات...")
    chapters = scan_novel_chapters_from_db(args.novel, args.chapters)
    if not chapters:
        print("⚠️ لم يتم العثور على فصول للرواية في قاعدة البيانات.")
        sys.exit(0)

    detected_lang, candidates, idioms = extract_potential_glossary_terms(chapters, lang=args.lang, min_chapter_occurrences=args.min_occurrences)
    print(f"🌐 لغة الرواية: [{detected_lang}] | تم استخراج {len(candidates)} مصطلحاً و {len(idioms)} مثلاً.")

    if args.prompt:
        prompt_text = build_claude_enrichment_prompt(candidates, args.novel, idioms=idioms, lang=detected_lang)
        print("\n" + "=" * 60)
        print("--- [برومبت Claude المقترح] ---")
        print("=" * 60)
        print(prompt_text)

    if args.output:
        export_mined_terms_to_csv(candidates, args.output, args.novel)
        print(f"💾 تم حفظ النتائج في {args.output}")
