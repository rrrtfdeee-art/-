# -*- coding: utf-8 -*-
import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from scraper_engine import PlaywrightStealthBrowser, crawl_toc_chapters, extract_chapter_title, clean_chapter_content
import database

database.init_db()
toc_url = "https://www.novel543.com/1010605889/dir"

print("==================================================")
print("1. فحص الفهرس وجلب الروابط")
print("==================================================")
chapters, novel_title = crawl_toc_chapters(toc_url, ".chaplist a")
print(f"اسم الرواية: {novel_title}")
print(f"عدد الفصول الإجمالي: {len(chapters)}")

ch1 = chapters[0]
ch2 = chapters[1]
print(f"رابط الفصل الأول: {ch1['url']}")
print(f"رابط الفصل الثاني: {ch2['url']}")

browser = PlaywrightStealthBrowser(headless=True)

print("\n==================================================")
print("2. تنزيل الفصل الأول")
print("==================================================")
html1, _ = browser.get_page_html(ch1["url"], wait_selector=".content")
title1 = extract_chapter_title(html1, "h1", fallback_number=1)
content1 = clean_chapter_content(html1, ".content", ["script", "style", ".ad", ".ads", "button"])
print(f"عنوان الفصل 1: {title1}")
print(f"طول المحتوى: {len(content1)} حرف / {len(content1.split())} كلمة")

out_file1 = os.path.join(os.getcwd(), "chapter_1_downloaded.txt")
with open(out_file1, "w", encoding="utf-8") as f:
    f.write(f"{title1}\n\n{content1}")
print(f"✅ تم حفظ الفصل الأول في: {out_file1}")

print("\n==================================================")
print("3. تنزيل الفصل الثاني")
print("==================================================")
html2, _ = browser.get_page_html(ch2["url"], wait_selector=".content")
title2 = extract_chapter_title(html2, "h1", fallback_number=2)
content2 = clean_chapter_content(html2, ".content", ["script", "style", ".ad", ".ads", "button"])
print(f"عنوان الفصل 2: {title2}")
print(f"طول المحتوى: {len(content2)} حرف / {len(content2.split())} كلمة")

out_file2 = os.path.join(os.getcwd(), "chapter_2_downloaded.txt")
with open(out_file2, "w", encoding="utf-8") as f:
    f.write(f"{title2}\n\n{content2}")
print(f"✅ تم حفظ الفصل الثاني في: {out_file2}")

print("\n==================================================")
print("4. مقتطفات نصية من بداية الفصلين للتأكد")
print("==================================================")
print("--- بداية الفصل الأول ---")
print(content1[:450])
print("\n--- بداية الفصل الثاني ---")
print(content2[:450])
