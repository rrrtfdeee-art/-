# -*- coding: utf-8 -*-
"""
Enrich Proverbs, Idioms, and Figurative Metaphors in Translation System
توسيع وتعميق قاعدة بيانات ومحرك كشف الحكم والأمثال والعبارات المجازية
"""
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

HTML_PATH = r"C:\Novelskyworld\نظام ترجمة ونشر الفصول\الترجمة.html"
PY_PATH = r"C:\Users\Dell\.gemini\antigravity-ide\scratch\smart-media-bot\novel_glossary_miner.py"

# 1. قائمة موسعة وشاملة لأشهر الحكم والأمثال والتعبيرات المجازية في الروايات العالمية والمترجمة
EXPANDED_EN_IDIOMS_JS = """        const FAMOUS_EN_IDIOMS = [
            // أمثال فانتازية وروايات صينية/آسيوية مترجمة للإنجليزية (Webnovel & Cultivation Staples)
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
            
            // أمثال وتعبيرات إنجليزية مجازية شائعة (Classic Literary Idioms)
            "Double-edged sword", "Tip of the iceberg", "Wolf in sheep's clothing",
            "Play with fire", "Playing with fire", "Add insult to injury", "Bite the dust", "Turn a blind eye",
            "Barking up the wrong tree", "Burn bridges", "Burning bridges", "Calm before the storm",
            "Face the music", "Hit the nail on the head", "Kill two birds with one stone",
            "Piece of cake", "Through thick and thin", "Walking on thin ice", "Spill the beans",
            "Blessing in disguise", "Once in a blue moon", "Eye for an eye", "Bite the bullet",
            "Chew off more than you can chew", "Bite off more than you can chew", "Throw in the towel",
            "Cut corners", "Elephant in the room", "Storm in a teacup", "Water under the bridge",
            "A wild goose chase", "Biting the hand that feeds", "Walking on eggshells", "At death's door"
        ];"""

with open(HTML_PATH, "r", encoding="utf-8") as f:
    html = f.read()

# استبدال قائمة FAMOUS_EN_IDIOMS القديمة في الترجمة.html
p_idiom_start = html.find("const FAMOUS_EN_IDIOMS = [")
p_idiom_end = html.find("];", p_idiom_start)

if p_idiom_start != -1 and p_idiom_end != -1:
    old_idiom_block = html[p_idiom_start:p_idiom_end+2]
    html = html.replace(old_idiom_block, EXPANDED_EN_IDIOMS_JS.strip())
    print("✅ Successfully updated FAMOUS_EN_IDIOMS in الترجمة.html")
else:
    print("⚠️ Could not find FAMOUS_EN_IDIOMS block in الترجمة.html")

# ترقية توجيهات برومبت Claude لتعريب الأمثال والحكم
old_en_rule = """4. [معيار الأمثال والتعبيرات الاصطلاحية (Idioms & Metaphors)]:
   - يجب تعريب التعبير الاصطلاحي بما يقابله في البلاغة العربية الفصيحة، مع تجنب الترجمة الحرفية التي تُفسد المعنى.
   - اجعل فئة التصنيف: 'Proverb / Idiom' وضع في خانة الملاحظات Notes شرحاً موجزاً لمعنى التعبير."""

new_en_rule = """4. [معيار الحكم والأمثال والتعبيرات المجازية والبلاغية (Proverbs, Wisdoms, Idioms & Metaphors)]:
   - سواء كانت أمثالاً إنجليزية عامة أو حكماً وتعبيرات مجازية فانتازية/صينية مترجمة (مثل: 'Courting death' -> 'يستعجل حتفه / يلتمس الهلاك'، و 'Toad wanting swan meat' -> 'أمنية غراب في كبد السماء / يتطاول كضفدع يشتهي لحم البجع'، و 'Have eyes but fail to see Mount Tai' -> 'أعمى البصيرة لا يرى الطود الأشم'، و 'Mantis stalks the cicada, oriole behind' -> 'يغفل عما يتربص به كالجندب خلفه الصرد'، و 'Refusing a toast only to drink a forfeit' -> 'أبى الكرامة ورضي بالمهانة').
   - القاعدة الذهبية: يُمنع منعاً باتاً الترجمة الحرفية الجافة التي تُفسد المعنى، بل يجب صياغة بديل بلاغي فصيح من روح أمثال وفصاحة لسان العرب.
   - [صياد الحكم والأمثال الخفية]: إذا صادفت في سياق الفصول أي حكم، أمثال، أو استعارات مجازية أخرى لم تُرصد بالقائمة، قم باستخلاصها وإضافتها فوراً للنتيجة وصنفها كـ 'Proverb / Idiom' مع شرح معناها البلاغي وسياقها في خانة Notes."""

if old_en_rule in html:
    html = html.replace(old_en_rule, new_en_rule)
    print("✅ Successfully updated Claude prompt instructions for idioms in الترجمة.html")
else:
    print("⚠️ Could not find old_en_rule in الترجمة.html")

with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.write(html)

# 2. تحديث novel_glossary_miner.py
with open(PY_PATH, "r", encoding="utf-8") as f:
    py_code = f.read()

EXPANDED_EN_IDIOMS_PY = """FAMOUS_EN_IDIOMS = [
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
]"""

p_py_start = py_code.find("FAMOUS_EN_IDIOMS = [")
p_py_end = py_code.find("]", p_py_start)

if p_py_start != -1 and p_py_end != -1:
    old_py_block = py_code[p_py_start:p_py_end+1]
    py_code = py_code.replace(old_py_block, EXPANDED_EN_IDIOMS_PY.strip())
    print("✅ Successfully updated FAMOUS_EN_IDIOMS in novel_glossary_miner.py")

old_py_rule = "4. الأمثال والتعبيرات المجازية: تعريبها بما يقابلها في البلاغة العربية مع شرح موجز في الملاحظات (Notes)."
new_py_rule = """4. الحكم والأمثال والتعبيرات المجازية (Idioms, Proverbs & Metaphors):
   - سواء كانت أمثالاً إنجليزية عامة أو حكماً وتعبيرات فانتازية/صينية مترجمة (مثل: 'Courting death' -> 'يستعجل حتفه / يلتمس الهلاك'، و 'Toad wanting swan meat' -> 'أمنية غراب في كبد السماء'، و 'Mount Tai' -> 'الطود الأشم').
   - تجنب الترجمة الحرفية تماماً واستبدالها بما يماثلها في البلاغة وفصاحة لسان العرب.
   - [صياد الحكم والأمثال]: إذا رصدت في الفصول أي حكمة أو مثل أو تعبير مجازي إضافي، قم بإضافته للنتيجة مع شرح معناه في خانة Notes."""

if old_py_rule in py_code:
    py_code = py_code.replace(old_py_rule, new_py_rule)
    print("✅ Successfully updated Claude prompt instructions in novel_glossary_miner.py")

with open(PY_PATH, "w", encoding="utf-8") as f:
    f.write(py_code)

print("🎉 COMPLETED: Proverbs, Idioms, and Metaphor systems are now deeply enriched across the platform!")
