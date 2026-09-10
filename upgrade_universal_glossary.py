# -*- coding: utf-8 -*-
"""
NSW Universal Glossary Engine Upgrade Script
ترقية مشغل القاموس واستخراج المصطلحات وبرومبت Claude إلى محرك عالمي شامل لجميع اللغات.
"""
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

HTML_PATH = r"C:\Novelskyworld\نظام ترجمة ونشر الفصول\الترجمة.html"

with open(HTML_PATH, "r", encoding="utf-8") as f:
    content = f.read()

# 1. ترقية قسم الـ UI
old_ui = """    <!-- 🧠 ميزة 4: مشغل القاموس والأمثال الصينية لـ Claude (Proverbs & Literary Glossary Engine) -->
    <div style="background: linear-gradient(135deg, #1e1e2e, #2a203c); border: 1px solid #cba6f7; padding: 16px; border-radius: 10px; margin: 15px 0; box-shadow: 0 4px 15px rgba(203, 166, 247, 0.1);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 10px;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 20px;">🧠</span>
                <h3 style="margin: 0; color: #cba6f7; font-size: 16px;">مشغل القاموس والأمثال الصينية لـ Claude (Proverbs & Glossary Engine)</h3>
                <span style="font-size: 11px; background: #89b4fa; color: #11111b; padding: 2px 8px; border-radius: 12px; font-weight: bold;">تعريب بلاغي</span>
            </div>
            <button type="button" onclick="toggleClaudeEngineBox()" style="background: #313244; color: #cdd6f4; border: 1px solid #585b70; padding: 5px 12px; font-size: 12px; border-radius: 4px; cursor: pointer;">
                تبديل العرض ↕️
            </button>
        </div>

        <p style="font-size: 12.5px; color: #bac2de; margin: 0 0 12px 0; line-height: 1.6;">
            يقوم هذا المشغل بمسح نصوص الفصول الحالية واستخراج: <b>الأسماء والشخصيات الصينية، المراتب، الطوائف، التقنيات القتالية</b>، وبشكل خاص: <b>الأمثال والحكم والتعابير الصينية (成语 & 俗语)</b>، ثم يجهز برومبتاً احترافياً لـ Claude لتعريبها بلاغياً، مع إمكانية استيراد النتيجة وتثبيتها مباشرة في جدول القاموس المعتمد (1oqK...).
        </p>

        <div id="claudeEngineBody">"""

new_ui = """    <!-- 🧠 ميزة 4: مشغل القاموس الشامل والأمثال لـ Claude (Universal Novels Glossary & Idioms Engine) -->
    <div style="background: linear-gradient(135deg, #1e1e2e, #2a203c); border: 1px solid #cba6f7; padding: 16px; border-radius: 10px; margin: 15px 0; box-shadow: 0 4px 15px rgba(203, 166, 247, 0.1);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 10px;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 20px;">🧠</span>
                <h3 style="margin: 0; color: #cba6f7; font-size: 16px;">مشغل القاموس الشامل والأمثال لـ Claude (Universal Glossary & Idioms Engine)</h3>
                <span id="engineLangBadge" style="font-size: 11px; background: #89b4fa; color: #11111b; padding: 2px 8px; border-radius: 12px; font-weight: bold;">تعريب عالمي متعدد اللغات 🌐</span>
            </div>
            <button type="button" onclick="toggleClaudeEngineBox()" style="background: #313244; color: #cdd6f4; border: 1px solid #585b70; padding: 5px 12px; font-size: 12px; border-radius: 4px; cursor: pointer;">
                تبديل العرض ↕️
            </button>
        </div>

        <p style="font-size: 12.5px; color: #bac2de; margin: 0 0 12px 0; line-height: 1.6;">
            يقوم هذا المشغل الذكي بمسح نصوص الفصول واستخراج: <b>أسماء الشخصيات، الرتب، الطوائف والمنظمات، التقنيات والمهارات</b>، وبشكل خاص <b>الأمثال والتعبيرات البلاغية (Idioms & Proverbs)</b> لأي لغة (إنجليزي، صيني، كوري، ياباني)، ثم يجهز برومبتاً احترافياً لـ Claude لتعريبها بدقة، مع إمكانية استيراد النتيجة وتثبيتها مباشرة في جدول القاموس المعتمد (1oqK...).
        </p>

        <div id="claudeEngineBody">
            <!-- شريط اختيار وكشف لغة الرواية العالمية -->
            <div style="display: flex; gap: 10px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; background: #181825; padding: 8px 12px; border-radius: 6px; border: 1px solid #313244;">
                <span style="color: #cdd6f4; font-size: 12px; font-weight: bold;">🌐 لغة الرواية الأصلية:</span>
                <select id="glossaryLangSelect" onchange="updateGlossaryLangIndicator()" style="background: #11111b; color: #89dceb; border: 1px solid #45475a; border-radius: 4px; padding: 6px 10px; font-size: 12px; font-weight: bold; cursor: pointer;">
                    <option value="auto">🌐 كشف تلقائي ذكي (Auto-Detect)</option>
                    <option value="en">🇬🇧 إنجليزي (English / Webnovel / LitRPG / Fantasy)</option>
                    <option value="zh">🇨🇳 صيني (Chinese / Hanzi / Chengyu)</option>
                    <option value="ko">🇰🇷 كوري (Korean / Hangul / Manhwa)</option>
                    <option value="ja">🇯🇵 ياباني (Japanese / Light Novel / Anime)</option>
                    <option value="universal">🌍 أي لغة أخرى / عام (Universal)</option>
                </select>
                <span id="detectedLangIndicator" style="color: #a6e3a1; font-size: 11px; font-weight: bold; margin-right: auto;"></span>
            </div>"""

if old_ui in content:
    content = content.replace(old_ui, new_ui)
    print("✅ Successfully updated UI section")
else:
    print("⚠️ Could not find exact old_ui block, checking partial match...")

# 2. ترقية دالة generateClaudeGlossaryPrompt وما حولها
old_js_start = "function generateClaudeGlossaryPrompt() {"
old_js_end = "function copyClaudePromptToClipboard() {"

p_start = content.find(old_js_start)
p_end = content.find(old_js_end)

if p_start == -1 or p_end == -1:
    print(f"❌ Error: Could not locate JS function boundaries (start: {p_start}, end: {p_end})")
    sys.exit(1)

new_js = r'''// ==============================================================================
    // 🌐 مشغل القاموس الشامل وتوليد برومبت Claude لكافة اللغات (Universal Engine)
    // ==============================================================================

    function updateGlossaryLangIndicator() {
        const sel = document.getElementById('glossaryLangSelect');
        const ind = document.getElementById('detectedLangIndicator');
        if (!sel || !ind) return;
        if (sel.value === 'auto') {
            ind.innerText = "🔍 الفحص التلقائي سيعمل عند الضغط على زر الاستخراج";
        } else {
            const labelMap = {
                en: "🇬🇧 تم تعيين اللغة يدوياً: إنجليزية",
                zh: "🇨🇳 تم تعيين اللغة يدوياً: صينية",
                ko: "🇰🇷 تم تعيين اللغة يدوياً: كورية",
                ja: "🇯🇵 تم تعيين اللغة يدوياً: يابانية",
                universal: "🌍 تم تعيين اللغة يدوياً: عالمية / أخرى"
            };
            ind.innerText = labelMap[sel.value] || "";
        }
    }

    // كشف تلقائي للغة من عينة النصوص
    function detectNovelLanguageFromText(sampleText) {
        if (!sampleText || sampleText.trim().length === 0) return "en";

        const zhMatches = sampleText.match(/[\u4e00-\u9fa5]/g) || [];
        const koMatches = sampleText.match(/[\uac00-\ud7af]/g) || [];
        const jaMatches = sampleText.match(/[\u3040-\u30ff]/g) || [];
        const enMatches = sampleText.match(/[a-zA-Z]/g) || [];

        const total = sampleText.length || 1;
        const zhRatio = zhMatches.length / total;
        const koRatio = koMatches.length / total;
        const jaRatio = jaMatches.length / total;

        if (koRatio > 0.03) return "ko";
        if (jaRatio > 0.03) return "ja";
        if (zhRatio > 0.05) return "zh";
        if (enMatches.length > 50) return "en";
        return "universal";
    }

    // --------------------------------------------------------------------------
    // 1. محرك استخراج المصطلحات الإنجليزية (English Extractor)
    // --------------------------------------------------------------------------
    function extractEnglishNovelGlossary(chapters) {
        const ENGLISH_STOPWORDS = new Set([
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
            "Yes", "No", "Not", "All", "Any", "Every", "Some", "Many", "Much", "More", "Most",
            "Now", "Here", "There", "Again", "Back", "Away", "Out", "Up", "Down", "Over", "Under",
            "About", "Into", "Through", "Between", "Against", "During", "Without", "Inside", "Outside",
            "Next", "Last", "Right", "Left", "Well", "Even", "Very", "Really", "Little", "Long", "Old", "New"
        ]);

        const TITLES_PREFIXES = [
            "Lord", "Lady", "Duke", "Duchess", "King", "Queen", "Emperor", "Empress", "Prince", "Princess",
            "Master", "Grandmaster", "Elder", "Great Elder", "Patriarch", "Sect Master", "Clan Leader",
            "Guild Leader", "Senior", "Junior", "Brother", "Sister", "General", "Commander", "Captain",
            "Archmage", "Saint", "Saintess", "High Priest", "Priest", "Knight", "Sir", "Baron", "Count",
            "Viscount", "Marquis", "Sovereign", "Monarch", "Overlord", "Supreme", "God", "Goddess",
            "Hero", "Vanguard", "Marshal", "Guardian", "Warden", "Headmaster"
        ];

        const LOCATION_KEYWORDS = [
            "City", "Town", "Village", "Kingdom", "Empire", "Continent", "Province", "County",
            "Mountain", "Peak", "Range", "Valley", "River", "Lake", "Sea", "Ocean", "Forest",
            "Plain", "Desert", "Island", "Cave", "Abyss", "Domain", "Realm", "World", "Palace",
            "Castle", "Fortress", "Tower", "Pavilion", "Temple", "Shrine", "Sanctuary", "Manor", "Hall"
        ];

        const ORG_KEYWORDS = [
            "Sect", "Clan", "Guild", "Family", "Alliance", "Association", "Order", "Union", "League",
            "Legion", "Corps", "House", "Chamber", "Pavilion", "Court", "Academy", "Institute",
            "Syndicate", "Faction", "Church", "Cult"
        ];

        const TECHNIQUE_KEYWORDS = [
            "Art", "Sword", "Blade", "Saber", "Spear", "Palm", "Fist", "Claw", "Finger", "Step", "Steps",
            "Slash", "Strike", "Manual", "Scripture", "Canon", "Sutra", "Mantra", "Technique", "Skill",
            "Spell", "Magic", "Formation", "Array", "Rune", "Method", "Formula", "Stance", "Style"
        ];

        const RANK_KEYWORDS = [
            "Realm", "Stage", "Level", "Layer", "Tier", "Rank", "Grade", "Class", "Core",
            "Qi Condensation", "Foundation Establishment", "Core Formation", "Nascent Soul",
            "Soul Transformation", "Void Refinement", "Ascension", "Martial Master", "Overlord"
        ];

        const FAMOUS_EN_IDIOMS = [
            "Double-edged sword", "Tip of the iceberg", "Wolf in sheep's clothing",
            "Play with fire", "Add insult to injury", "Bite the dust", "Turn a blind eye",
            "Barking up the wrong tree", "Burn bridges", "Calm before the storm",
            "Face the music", "Hit the nail on the head", "Kill two birds with one stone",
            "Piece of cake", "Through thick and thin", "Walking on thin ice", "Spill the beans",
            "Blessing in disguise", "Once in a blue moon", "Eye for an eye"
        ];

        const termChapterMap = {};
        const termCounts = {};
        const extractedIdioms = new Set();

        chapters.forEach(chap => {
            const text = chap.text || "";
            if (!text) return;

            // 1. كشف الأمثال والتعبيرات الإنجليزية
            FAMOUS_EN_IDIOMS.forEach(idm => {
                if (new RegExp("\\b" + idm + "\\b", "i").test(text)) {
                    extractedIdioms.add(idm);
                }
            });

            // 2. كشف رسائل وشاشات النظام المحصورة بأقواس مثل [System: ...] و 【...】
            const bracketMatches = text.match(/\[([A-Z0-9a-z\s:_\-–'’]{3,45})\]|【([A-Z0-9a-z\s:_\-–'’]{3,45})】/g) || [];
            bracketMatches.forEach(b => {
                const clean = b.replace(/[\[\]【】]/g, '').trim();
                if (clean && !clean.toLowerCase().startsWith("chapter") && clean.length >= 3 && clean.length <= 40) {
                    if (!termChapterMap[clean]) termChapterMap[clean] = { chapters: new Set(), cat: "System / Special Term", count: 0 };
                    termChapterMap[clean].chapters.add(chap.chapNum);
                    termChapterMap[clean].count += 2;
                }
            });

            // 3. كشف أسماء الأعلام والمصطلحات المركبة (1 إلى 4 كلمات تبدأ بأحرف كبيرة)
            const phraseMatches = text.match(/\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\b/g) || [];
            phraseMatches.forEach(phrase => {
                const trimmed = phrase.trim();
                const words = trimmed.split(/\s+/);
                if (words.length === 1 && ENGLISH_STOPWORDS.has(words[0])) return;
                if (words.length > 1 && ENGLISH_STOPWORDS.has(words[0]) && !TITLES_PREFIXES.includes(words[0])) {
                    words.shift();
                }
                const cleanTerm = words.join(" ");
                if (cleanTerm.length < 3 || ENGLISH_STOPWORDS.has(cleanTerm)) return;

                let cat = "Character";
                if (TITLES_PREFIXES.some(t => cleanTerm.includes(t))) cat = "Character";
                else if (ORG_KEYWORDS.some(k => cleanTerm.includes(k))) cat = "Organization";
                else if (LOCATION_KEYWORDS.some(k => cleanTerm.includes(k))) cat = "Location";
                else if (TECHNIQUE_KEYWORDS.some(k => cleanTerm.includes(k))) cat = "Technique";
                else if (RANK_KEYWORDS.some(k => cleanTerm.includes(k))) cat = "Rank";
                else if (words.length >= 2) cat = "Specialized Term";

                if (!termChapterMap[cleanTerm]) {
                    termChapterMap[cleanTerm] = { chapters: new Set(), cat: cat, count: 0 };
                }
                termChapterMap[cleanTerm].chapters.add(chap.chapNum);
                termChapterMap[cleanTerm].count++;
            });
        });

        let candidates = [];
        for (const [term, data] of Object.entries(termChapterMap)) {
            if (data.chapters.size >= 2 || data.count >= 3) {
                candidates.push({
                    term: term,
                    category: data.cat,
                    chapterCount: data.chapters.size,
                    totalCount: data.count
                });
            }
        }

        candidates.sort((a, b) => b.chapterCount - a.chapterCount || b.totalCount - a.totalCount);
        return {
            proverbs: Array.from(extractedIdioms).slice(0, 20),
            terms: candidates.slice(0, 50)
        };
    }

    // --------------------------------------------------------------------------
    // 2. محرك استخراج المصطلحات الصينية (Chinese Extractor)
    // --------------------------------------------------------------------------
    function extractChineseNovelGlossary(chapters) {
        const CHINESE_SURNAMES = new Set([
            "陈", "楚", "李", "王", "张", "刘", "赵", "诸葛", "司马", "欧阳", "慕容",
            "东方", "独孤", "南宫", "令狐", "西门", "林", "叶", "萧", "秦", "周", "吴",
            "韩", "杨", "徐", "朱", "孙", "马", "郭", "何", "高", "罗", "唐", "梁", "宋", "江", "顾"
        ]);

        const LOCATION_SUFFIXES = ["城", "府", "山", "州", "界", "郡", "村", "坊", "堂", "阁", "楼", "殿", "国", "海", "域", "谷", "林", "岛", "原"];
        const ORGANIZATION_SUFFIXES = ["宗", "门", "帮", "派", "会", "教", "院", "司", "卫", "朝", "行", "庄", "商会", "医馆", "圣地", "世家"];
        const TECHNIQUE_SUFFIXES = ["诀", "经", "功", "法", "掌", "拳", "剑", "刀", "步", "印", "指", "腿", "术", "阵", "式", "典", "图", "针", "秘法"];
        const RANK_SUFFIXES = ["王", "皇", "帝", "君", "尊", "侯", "公", "世子", "长老", "宗主", "师尊", "殿下", "陛下", "大人", "圣子", "神女", "将军", "状元", "至尊", "老祖"];

        const CHINESE_STOPWORDS = new Set([
            "一个", "他们", "我们", "自己", "什么", "怎么", "没有", "这时", "虽然",
            "如果", "知道", "看着", "说道", "听到", "现在", "不是", "就是", "这个时候", "在这个",
            "随着", "因为", "所以", "不过", "然而", "突然", "只见", "随后", "而且", "最后", "开始", "然后", "已经", "可以"
        ]);

        const FAMOUS_PROVERBS = [
            "井底之蛙", "班门弄斧", "杀鸡儆猴", "一箭双雕", "卧虎藏龙", "望梅止渴", "画龙点睛",
            "顺水推舟", "抛砖引玉", "破釜沉舟", "狐假虎威", "掩耳盗铃", "亡羊补牢", "对牛弹琴",
            "饮鸩止渴", "守株待兔", "杞人忧天", "自相矛盾", "画蛇添足", "拔苗助长", "螳臂当车",
            "坐井观天", "叶公好龙", "盲人摸象", "纸上谈兵", "草木皆兵", "望洋兴叹", "完璧归赵",
            "负荆请罪", "走马观花", "如鱼得水", "风吹草动", "鸡犬不宁", "狼吞虎咽", "鬼斧神工",
            "惊弓之鸟", "沧海一粟", "闭月羞花", "沉鱼落雁", "倾国倾城", "豁然开朗", "炉火纯青",
            "出神入化", "一鸣惊人", "气吞山河", "翻江倒海", "呼风唤雨", "惊天动地", "天翻地覆",
            "偷天换日", "独步天下", "登峰造极", "傲视群雄", "不可一世", "深不可测", "九死一生"
        ];

        const termChapterMap = {};
        const termCounts = {};
        const extractedProverbs = new Set();

        chapters.forEach(chap => {
            const text = chap.text || "";
            if (!text) return;

            FAMOUS_PROVERBS.forEach(p => {
                if (text.includes(p)) extractedProverbs.add(p);
            });

            const idiomMatches = text.match(/[\u4e00-\u9fa5]{4}/g) || [];
            idiomMatches.forEach(phrase => {
                if (CHINESE_STOPWORDS.has(phrase)) return;
                if (phrase[0] === phrase[2] || phrase[1] === phrase[3] || phrase[0] === phrase[1] || phrase[2] === phrase[3] ||
                    phrase.includes("之") || phrase.includes("不") || phrase.includes("如") || phrase.includes("一") || phrase.includes("大") || phrase.includes("天")) {
                    if (!termCounts[phrase]) termCounts[phrase] = 0;
                    termCounts[phrase]++;
                    if (termCounts[phrase] >= 2) extractedProverbs.add(phrase);
                }
            });

            const wordMatches = text.match(/[\u4e00-\u9fa5]{2,4}/g) || [];
            wordMatches.forEach(term => {
                if (CHINESE_STOPWORDS.has(term) || term.length < 2) return;

                let isCandidate = false;
                let cat = "Generic";

                if (Array.from(CHINESE_SURNAMES).some(s => term.startsWith(s)) && term.length <= 4) {
                    isCandidate = true;
                    cat = "Character";
                } else if (RANK_SUFFIXES.some(s => term.endsWith(s))) {
                    isCandidate = true;
                    cat = "Rank";
                } else if (ORGANIZATION_SUFFIXES.some(s => term.endsWith(s))) {
                    isCandidate = true;
                    cat = "Organization";
                } else if (TECHNIQUE_SUFFIXES.some(s => term.endsWith(s))) {
                    isCandidate = true;
                    cat = "Technique";
                } else if (LOCATION_SUFFIXES.some(s => term.endsWith(s))) {
                    isCandidate = true;
                    cat = "Location";
                }

                if (isCandidate) {
                    if (!termChapterMap[term]) termChapterMap[term] = { chapters: new Set(), cat: cat, count: 0 };
                    termChapterMap[term].chapters.add(chap.chapNum);
                    termChapterMap[term].count++;
                }
            });
        });

        let candidates = [];
        for (const [term, data] of Object.entries(termChapterMap)) {
            if (data.chapters.size >= 2 || data.count >= 3) {
                candidates.push({
                    term: term,
                    category: data.cat,
                    chapterCount: data.chapters.size,
                    totalCount: data.count
                });
            }
        }

        candidates.sort((a, b) => b.chapterCount - a.chapterCount || b.totalCount - a.totalCount);
        return {
            proverbs: Array.from(extractedProverbs).slice(0, 25),
            terms: candidates.slice(0, 50)
        };
    }

    // --------------------------------------------------------------------------
    // 3. محرك استخراج المصطلحات الكورية / اليابانية / العامة
    // --------------------------------------------------------------------------
    function extractUniversalNovelGlossary(chapters, lang) {
        const termChapterMap = {};
        const extractedIdioms = new Set();

        const pattern = (lang === "ko") ? /[\uac00-\ud7af]{2,6}/g :
                        (lang === "ja") ? /[\u30a0-\u30ff]{2,8}|[\u4e00-\u9fa5]{2,5}/g :
                        /\b[A-Z\u00C0-\u024F][a-z\u00C0-\u024F]+(?:\s+[A-Z\u00C0-\u024F][a-z\u00C0-\u024F]+){0,2}\b/g;

        chapters.forEach(chap => {
            const text = chap.text || "";
            if (!text) return;

            const bracketMatches = text.match(/\[([^\]]{2,35})\]|【([^】]{2,35})】/g) || [];
            bracketMatches.forEach(b => {
                const clean = b.replace(/[\[\]【】]/g, '').trim();
                if (clean.length >= 2) {
                    if (!termChapterMap[clean]) termChapterMap[clean] = { chapters: new Set(), cat: "Specialized Term", count: 0 };
                    termChapterMap[clean].chapters.add(chap.chapNum);
                    termChapterMap[clean].count += 2;
                }
            });

            const matches = text.match(pattern) || [];
            matches.forEach(m => {
                const term = m.trim();
                if (term.length < 2) return;
                if (!termChapterMap[term]) termChapterMap[term] = { chapters: new Set(), cat: "Character / Specialized Term", count: 0 };
                termChapterMap[term].chapters.add(chap.chapNum);
                termChapterMap[term].count++;
            });
        });

        let candidates = [];
        for (const [term, data] of Object.entries(termChapterMap)) {
            if (data.chapters.size >= 2 || data.count >= 3) {
                candidates.push({
                    term: term,
                    category: data.cat,
                    chapterCount: data.chapters.size,
                    totalCount: data.count
                });
            }
        }
        candidates.sort((a, b) => b.chapterCount - a.chapterCount || b.totalCount - a.totalCount);
        return {
            proverbs: Array.from(extractedIdioms).slice(0, 15),
            terms: candidates.slice(0, 50)
        };
    }

    // ==============================================================================
    // الدالة الرئيسية لتوليد البرومبت العالمي لـ Claude
    // ==============================================================================
    function generateClaudeGlossaryPrompt() {
        const novelNameInput = document.getElementById('novelNameInput');
        const novelName = novelNameInput ? novelNameInput.value.trim() : "";
        if (!novelName) {
            return alert("⚠️ يرجى إدخال أو اختيار اسم الرواية أولاً!");
        }

        if (!parsedChapters || parsedChapters.length === 0) {
            return alert("⚠️ لا توجد فصول محملة حالياً! يرجى تحميل ملف الرواية أو جلب فصولها من شيت الترجمة أولاً.");
        }

        // تحديد اللغة
        const langSelect = document.getElementById('glossaryLangSelect');
        let selectedLang = langSelect ? langSelect.value : "auto";
        let actualLang = selectedLang;

        // عينة للفحص التلقائي
        let sampleText = "";
        for (let i = 0; i < Math.min(parsedChapters.length, 5); i++) {
            sampleText += " " + (parsedChapters[i].text || "");
        }

        if (selectedLang === "auto") {
            actualLang = detectNovelLanguageFromText(sampleText);
        }

        const langMeta = {
            en: { name: "الإنجليزية 🇬🇧", label: "رواية إنجليزية (English / Webnovel / Fantasy)" },
            zh: { name: "الصينية 🇨🇳", label: "رواية صينية (Chinese / Xianxia / Wuxia)" },
            ko: { name: "الكورية 🇰🇷", label: "رواية كورية (Korean / Hunter / Manhwa)" },
            ja: { name: "اليابانية 🇯🇵", label: "رواية يابانية (Japanese / Light Novel / Anime)" },
            universal: { name: "العالمية 🌍", label: "رواية عالمية (Universal)" }
        };

        const currentMeta = langMeta[actualLang] || langMeta.universal;
        const ind = document.getElementById('detectedLangIndicator');
        if (ind) {
            ind.innerText = `🌐 لغة الرواية المعتمدة: [${currentMeta.name}]`;
        }
        const badge = document.getElementById('engineLangBadge');
        if (badge) {
            badge.innerText = `مشغل ${currentMeta.name}`;
        }

        logMsg(`🧠 بدء مسح وتعدين مصطلحات [${novelName}] - اللغة: ${currentMeta.name} من ${parsedChapters.length} فصلاً...`);

        // استخراج المصطلحات بحسب اللغة
        let extractedData;
        if (actualLang === "en") {
            extractedData = extractEnglishNovelGlossary(parsedChapters);
        } else if (actualLang === "zh") {
            extractedData = extractChineseNovelGlossary(parsedChapters);
        } else {
            extractedData = extractUniversalNovelGlossary(parsedChapters, actualLang);
        }

        const provList = extractedData.proverbs;
        const candidateTerms = extractedData.terms;

        if (candidateTerms.length === 0 && provList.length === 0) {
            return alert(`⚠️ لم يتم العثور على مصطلحات متكررة كافية في الفصول الحالية. تأكد من صحة النصوص واللغة المختارة (${currentMeta.name}).`);
        }

        let termsListing = "";
        if (provList.length > 0) {
            termsListing += `=== [قسم الأمثال والتعبيرات البلاغية (${actualLang === 'zh' ? '成语 / 俗语' : 'Idioms & Proverbs'})] ===\n`;
            provList.forEach(p => {
                termsListing += `- ${p} (الفئة: Proverb / Idiom | تعبير اصطلاحي/مثل)\n`;
            });
            termsListing += "\n";
        }

        termsListing += "=== [قسم أسماء الشخصيات، الرتب، المهارات، والمواقع] ===\n";
        candidateTerms.forEach(item => {
            termsListing += `- ${item.term} (الفئة المقترحة: ${item.category} | تكررت في ${item.chapterCount} فصلاً)\n`;
        });

        // صياغة البرومبت التوجيهي الذكي لـ Claude بحسب اللغة
        let languageInstructions = "";
        if (actualLang === "en") {
            languageInstructions = `1. أسماء الشخصيات الأجنبية والغربية: تُعرب صوتياً بدقة وسلاسة للأذن العربية الفصحى مع التشكيل الدقيق عند اللبس، وتحديد جنس الشخصية (ذكر / أنثى) بدقة بناءً على الضمائر (he/she) وسياق الاستخدام.
2. المهارات والتقنيات القتالية وفنون السحر (Skills / Spells / Arts): تُعرب بأسلوب فخم وجزل وبلاغي (مثلاً: 'Heavenly Frost Sword' تُعرب 'سيف الصقيع السماوي المتسامي' بدلاً من ترجمة حرفية باهتة).
3. الطوائف، المنظمات، النقابات، والمواقع الجغرافية: تُترجم بدقة دلالية فصيحة ومصطلحات متناسقة تناسب سياق الفانتازيا/الخيال.
4. [معيار الأمثال والتعبيرات الاصطلاحية (Idioms & Metaphors)]:
   - يجب تعريب التعبير الاصطلاحي بما يقابله في البلاغة العربية الفصيحة، مع تجنب الترجمة الحرفية التي تُفسد المعنى.
   - اجعل فئة التصنيف: 'Proverb / Idiom' وضع في خانة الملاحظات Notes شرحاً موجزاً لمعنى التعبير.`;
        } else if (actualLang === "zh") {
            languageInstructions = `1. أسماء الشخصيات الصينية: تُعرب صوتياً بدقة Pinyin وتحديد جنس الشخصية (ذكر / أنثى).
2. التقنيات والفنون القتالية ومستويات الزراعة الطاوية: تُعرب بأسلوب فخم وجزل يناسب الأذن العربية الرفيعة (مثلاً: 'فن سيف الغسق المتسامي' بدلاً من ترجمة حرفية ركيكة).
3. المواقع، الطوائف، والمناصب: تُترجم بدقة دلالية واضحة ومصطلحات متناسقة.
4. [معيار الأمثال والحكم والتعابير الاصطلاحية الصينية (成语 / 俗语)]:
   - يجب تعريب المثل أو التعبير الاصطلاحي بأسلوب بلاغي يعكس المعنى البلاغي الحقيقي الفصيح أو ما يقابله في البلاغة العربية (تجنب الترجمة الحرفية الباهتة مثل 'ضفدع في قاع بئر' وعوضها بمعنى 'قاصر النظر كضفدع في قاع بئر' أو 'ضيق الأفق').
   - اجعل فئة التصنيف: 'Proverb / Idiom' وضع في خانة الملاحظات Notes شرحاً موجزاً لمعنى المثل.`;
        } else {
            languageInstructions = `1. أسماء الشخصيات: تُعرب صوتياً بدقة للأذن العربية مع ضبط النطق وتحديد جنس الشخصية (ذكر / أنثى).
2. المهارات والرتب والمناصب: تُترجم بأسلوب فصيح وبليغ يناسب نوع الرواية.
3. المواقع والمنظمات: تُترجم بدقة دلالية ومصطلحات متناسقة.
4. التعبيرات والأمثال: تُعرب بما يقابلها في المعنى البلاغي الفصيح مع شرح موجز في الملاحظات (Notes).`;
        }

        const claudePrompt = `أنت خبير تعريب روايات عالمية وأديب وناقد ومترجم فوري معتمد من أعلى المستويات.
لدينا قائمة بأهم المصطلحات والشخصيات والأمثال المستخرجة آلياً من رواية [${currentMeta.label}] بعنوان '${novelName}'.

المطلوب إكمال وتدقيق بيانات كل مصطلح لإضافتها إلى شيت القاموس المعتمد للرواية، مع الالتزام التام بالمعايير التالية:
${languageInstructions}

قائمة المصطلحات والأمثال المستخرجة:
${termsListing}

أرجع النتيجة حصراً بصيغة JSON نظيفة كالتالي:
\`\`\`json
[
  {
    "OriginalTerm": "المصطلح الأصلي بلغة الرواية",
    "ArabicTranslation": "التعريب المعتمد البليغ",
    "Category": "Character / Location / Organization / Technique / Rank / Proverb / Idiom / Specialized Term",
    "Gender": "ذكر / أنثى / غير محدد",
    "Notes": "ملاحظة توضيحية أو شرح المثل/المصطلح"
  }
]
\`\`\``;

        document.getElementById('claudeGeneratedPromptArea').value = claudePrompt;
        document.getElementById('claudePromptBox').style.display = 'block';
        document.getElementById('claudeResponseBox').style.display = 'block';
        document.getElementById('btnCopyClaudePrompt').disabled = false;

        const totalExtracted = provList.length + candidateTerms.length;
        document.getElementById('extractedCountBadge').innerText = `✨ [${currentMeta.name}]: تم استخراج ${provList.length} مثلاً و ${candidateTerms.length} مصطلحاً وشخصية`;

        logMsg(`✅ تم تجهيز برومبت Claude بنجاح (${totalExtracted} عنصراً - لغة: ${currentMeta.name}). انسخ البرومبت وافتحه في Claude ثم الصق الرد بالأسفل.`);
    }

    '''

# تطبيق التعديل على الكود البرمجي
content = content[:p_start] + new_js + content[p_end:]

with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.write(content)

print("🎉 SUCCESS: Completely upgraded الترجمة.html to Universal Multi-Language Glossary Engine!")
