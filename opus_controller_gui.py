# -*- coding: utf-8 -*-
"""
==============================================================================
NSW Claude Opus Desktop Control Panel - لوحة تحكم أوبس لسطح المكتب
==============================================================================
تطبيق مكتبي خفيف جداً يتيح لك إدارة دورة صقل الفصول بنقرة زر واحدة:
  1. سحب الفصول بضغطة زر.
  2. فتح المجلد لمراجعة وتعديل الفصول عبر Claude Opus.
  3. اعتماد الفصول المصقولة بضغطة زر.
  4. رفع ونشر الفصول مباشرة إلى بلوجر والشيت.
"""

import os
import sys
import threading
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

# المسارات
BASE_DIR = Path(__file__).resolve().parent
STAGING_DIR = BASE_DIR / "opus_staging"
PENDING_DIR = STAGING_DIR / "pending"
APPROVED_DIR = STAGING_DIR / "approved"
PUBLISHED_DIR = STAGING_DIR / "published"

for d in [PENDING_DIR, APPROVED_DIR, PUBLISHED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

import sync_opus_queue

class OpusAppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("NSW Claude Opus Manager - لوحة تحكم أوبس")
        self.root.geometry("580x620")
        self.root.resizable(False, False)
        self.root.configure(bg="#1e1e2e")

        # نمط مخصص
        style = ttk.Style()
        style.theme_use('clam')

        # الإطار الرئيسي
        main_frame = tk.Frame(root, bg="#1e1e2e", padx=20, pady=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # الترويسة
        header_lbl = tk.Label(
            main_frame,
            text="🎭 لوحة تحكم صقل الفصول الذاتية (Claude Opus)",
            font=("Segoe UI", 14, "bold"),
            fg="#cdd6f4",
            bg="#1e1e2e"
        )
        header_lbl.pack(pady=(0, 10))

        # بطاقة الحالة
        status_card = tk.Frame(main_frame, bg="#313244", padx=15, pady=10, relief=tk.RIDGE, bd=1)
        status_card.pack(fill=tk.X, pady=(0, 15))

        self.lbl_pending = tk.Label(status_card, text="⏳ في الانتظار (Pending): ...", font=("Segoe UI", 11), fg="#f9e2af", bg="#313244", anchor="w")
        self.lbl_pending.pack(fill=tk.X, pady=2)

        self.lbl_approved = tk.Label(status_card, text="✍️ المعتمدة (Approved): ...", font=("Segoe UI", 11), fg="#a6e3a1", bg="#313244", anchor="w")
        self.lbl_approved.pack(fill=tk.X, pady=2)

        self.lbl_published = tk.Label(status_card, text="✅ المنشورة (Published): ...", font=("Segoe UI", 11), fg="#89b4fa", bg="#313244", anchor="w")
        self.lbl_published.pack(fill=tk.X, pady=2)

        # إطار الأزرار بنظام النقرتين البسيط
        btn_frame = tk.Frame(main_frame, bg="#1e1e2e")
        btn_frame.pack(fill=tk.X, pady=(0, 15))

        # 🌟 النقرة الأولى: سحب وتجهيز مع القاموس
        self.btn_hero_click1 = tk.Button(
            btn_frame,
            text="📥 [النقرة 1]: اسحب 20 فصلاً وجهّز القاموس لكلاود أوبس",
            font=("Segoe UI", 11, "bold"),
            bg="#3b82f6",
            fg="#ffffff",
            activebackground="#60a5fa",
            cursor="hand2",
            pady=10,
            command=self.start_two_click_stage
        )
        self.btn_hero_click1.pack(fill=tk.X, pady=4)

        # 🌟 النقرة الثانية: اعتماد ونشر مباشر
        self.btn_hero_click2 = tk.Button(
            btn_frame,
            text="🚀 [النقرة 2]: اعتماد ورفع الكل إلى بلوجر بمواعيدها المجدولة",
            font=("Segoe UI", 11, "bold"),
            bg="#10b981",
            fg="#ffffff",
            activebackground="#34d399",
            cursor="hand2",
            pady=10,
            command=self.start_two_click_publish
        )
        self.btn_hero_click2.pack(fill=tk.X, pady=4)

        # أدوات مساعدة سريعة
        sub_btn_frame = tk.Frame(btn_frame, bg="#1e1e2e")
        sub_btn_frame.pack(fill=tk.X, pady=4)

        self.btn_copy_prompt = tk.Button(
            sub_btn_frame,
            text="📋 نسخ أمر كلاود مع القاموس للحافظة",
            font=("Segoe UI", 9, "bold"),
            bg="#4f46e5",
            fg="#ffffff",
            activebackground="#6366f1",
            cursor="hand2",
            pady=5,
            command=self.copy_claude_prompt_to_clipboard
        )
        self.btn_copy_prompt.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))

        self.btn_open = tk.Button(
            sub_btn_frame,
            text="📂 فتح مجلد الفصول",
            font=("Segoe UI", 9),
            bg="#374151",
            fg="#f3f4f6",
            activebackground="#4b5563",
            cursor="hand2",
            pady=5,
            command=self.open_folder
        )
        self.btn_open.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))

        # زر تحديث الحالة
        self.btn_refresh = tk.Button(
            btn_frame,
            text="🔄 تحديث الأرقام والحالة اللحظية",
            font=("Segoe UI", 8),
            bg="#1f2937",
            fg="#9ca3af",
            activebackground="#374151",
            cursor="hand2",
            pady=3,
            command=self.update_status_display
        )
        self.btn_refresh.pack(fill=tk.X, pady=(4, 0))

        # صندوق السجلات والرسائل
        log_label = tk.Label(main_frame, text="📋 تقرير العمليات الآنية:", font=("Segoe UI", 9, "bold"), fg="#a6adc8", bg="#1e1e2e", anchor="w")
        log_label.pack(fill=tk.X, pady=(5, 2))

        self.log_text = tk.Text(main_frame, height=9, bg="#11111b", fg="#cdd6f4", font=("Consolas", 9), wrap=tk.WORD, bd=0, padx=8, pady=8)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.update_status_display()
        self.log("✅ لوحة تحكم أوبس بنظام النقرتين السريع جاهزة.")

    def log(self, message: str):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def set_buttons_state(self, enabled: bool):
        st = tk.NORMAL if enabled else tk.DISABLED
        self.btn_hero_click1.config(state=st)
        self.btn_hero_click2.config(state=st)
        self.btn_copy_prompt.config(state=st)
        self.btn_open.config(state=st)

    def update_status_display(self):
        p_cnt = len(list(PENDING_DIR.glob("chapter_*.txt")))
        a_cnt = len(list(APPROVED_DIR.glob("chapter_*.txt")))
        pub_cnt = len(list(PUBLISHED_DIR.glob("chapter_*.txt")))

        self.lbl_pending.config(text=f"⏳ في الانتظار (Pending): {p_cnt} فصلاً (بانتظار الصقل)")
        self.lbl_approved.config(text=f"✍️ المعتمدة (Approved): {a_cnt} فصلاً (جاهزة للرفع)")
        self.lbl_published.config(text=f"✅ المنشورة (Published): {pub_cnt} فصلاً (تم النشر)")

    def open_folder(self):
        try:
            os.startfile(str(PENDING_DIR))
            self.log(f"📂 تم فتح مجلد: {PENDING_DIR}")
        except Exception as e:
            self.log(f"❌ خطأ فتح المجلد: {e}")

    def copy_claude_prompt_to_clipboard(self):
        prompt_file = STAGING_DIR / "CLAUDE_PROMPT_FOR_BATCH.txt"
        if not prompt_file.exists():
            self.log("⚠️ لم يتم العثور على ملف الأمر. اضغط على [النقرة 1] أولاً لتوليده.")
            return
        try:
            text = prompt_file.read_text(encoding="utf-8")
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.log("📋 تم نسخ أمر كلاود أوبس مع القاموس المفلتر إلى الحافظة بنجاح!\nالصقه الآن في محادثة Claude Opus.")
        except Exception as e:
            self.log(f"❌ تعذر نسخ النص: {e}")

    def start_two_click_stage(self):
        """النقرة الأولى: سحب وتجريد وتوليد القاموس المفلتر ونسخه للحافظة وفتح المجلد."""
        self.set_buttons_state(False)
        self.log("⏳ [النقرة 1]: جاري سحب 20 فصلاً وتجريدها من الأكواد وفلترة القاموس المعتمد...")
        def _run():
            try:
                sync_opus_queue.cmd_pull(limit=20, novel_name="After Severing Ties")
                self.root.after(0, self.copy_claude_prompt_to_clipboard)
                self.root.after(0, lambda: self.log(
                    "🎉 [اكتملت النقرة 1 بنجاح!]\n"
                    "1. تم سحب وتجريد الفصول في مجلد pending/ وحفظ وسوم BBCode.\n"
                    "2. تم استخلاص القاموس المفلتر بدقة (توفير 90%+ من توكنز نافذة السياق).\n"
                    "3. تم نسخ أمر كلاود أوبس مع القاموس المفلتر إلى الحافظة تلقائياً (Ctrl+V جاهز).\n"
                    "👉 الصقه في محادثة Claude Opus (أو اسحب ملفات الفصول من المجلد المفتوح وأفلتها).\n"
                    "👉 بعد انتهاء كلاود من صقل الفصول، اضغط مباشرة على [النقرة 2]."
                ))
                self.root.after(0, self.open_folder)
            except Exception as e:
                self.root.after(0, lambda: self.log(f"❌ خطأ في النقرة 1: {e}"))
            finally:
                self.root.after(0, lambda: (self.update_status_display(), self.set_buttons_state(True)))
        threading.Thread(target=_run, daemon=True).start()

    def start_two_click_publish(self):
        """النقرة الثانية: اعتماد الكل وإعادة التغليف الملكي والرفع لبلوجر بمواعيدها."""
        self.set_buttons_state(False)
        self.log("🚀 [النقرة 2]: جاري اعتماد كافة الفصول وإعادة التغليف الملكي والرفع لبلوجر بمواعيدها المجدولة...")
        def _run():
            try:
                cnt = sync_opus_queue.cmd_approve_all()
                self.root.after(0, lambda: self.log(f"✍️ تم اعتماد {cnt} فصول ونقلها للمزامنة..."))
                sync_opus_queue.cmd_push(novel_name="After Severing Ties")
                self.root.after(0, lambda: self.log("🎉 [اكتملت النقرة 2 بنجاح!] تم رفع ونشر كافة الفصول وصيانة مواعيدها بدقة 100%."))
            except Exception as e:
                self.root.after(0, lambda: self.log(f"❌ خطأ في النقرة 2: {e}"))
            finally:
                self.root.after(0, lambda: (self.update_status_display(), self.set_buttons_state(True)))
        threading.Thread(target=_run, daemon=True).start()


def main():
    root = tk.Tk()
    app = OpusAppGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
