# -*- coding: utf-8 -*-
import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

with open(r"c:\Novelskyworld\نظام ترجمة ونشر الفصول\كود النشر.txt", "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

print("=== LAST 200 LINES OF FILE ===")
lines = text.splitlines()
for idx, l in enumerate(lines[-200:], start=len(lines)-199):
    print(f"{idx}: {l}")


