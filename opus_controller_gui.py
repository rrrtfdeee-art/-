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

        # إطار الأزرار
        btn_frame = tk.Frame(main_frame, bg="#1e1e2e")
        btn_frame.pack(fill=tk.X, pady=(0, 15))

        # زر 1: سحب 20 فصلاً
        self.btn_pull = tk.Button(
            btn_frame,
            text="📥 1. ابدأ سحب 20 فصلاً جديداً (Pull)",
            font=("Segoe UI", 11, "bold"),
            bg="#89b4fa",
            fg="#11111b",
            activebackground="#b4befe",
            cursor="hand2",
            pady=8,
            command=self.start_pull
        )
        self.btn_pull.pack(fill=tk.X, pady=4)

        # زر 2: فتح مجلد الفصول
        self.btn_open = tk.Button(
            btn_frame,
            text="📂 فتح مجلد الفصول على الحاسوب (Pending Folder)",
            font=("Segoe UI", 10),
            bg="#45475a",
            fg="#cdd6f4",
            activebackground="#585b70",
            cursor="hand2",
            pady=6,
            command=self.open_folder
        )
        self.btn_open.pack(fill=tk.X, pady=4)

        # زر 3: اعتماد الكل
        self.btn_approve = tk.Button(
            btn_frame,
            text="✍️ 2. اعتماد كافة الفصول المصقولة (Approve All)",
            font=("Segoe UI", 11, "bold"),
            bg="#a6e3a1",
            fg="#11111b",
            activebackground="#94e2d5",
            cursor="hand2",
            pady=8,
            command=self.start_approve_all
        )
        self.btn_approve.pack(fill=tk.X, pady=4)

        # زر 4: رفع ونشر لبلوجر
        self.btn_push = tk.Button(
            btn_frame,
            text="🚀 3. رفع ونشر الكل إلى بلوجر والشيت (Push to Blogger)",
            font=("Segoe UI", 11, "bold"),
            bg="#fab387",
            fg="#11111b",
            activebackground="#f9e2af",
            cursor="hand2",
            pady=8,
            command=self.start_push
        )
        self.btn_push.pack(fill=tk.X, pady=4)

        # زر تحديث الحالة
        self.btn_refresh = tk.Button(
            btn_frame,
            text="🔄 تحديث الأرقام والحالة",
            font=("Segoe UI", 9),
            bg="#313244",
            fg="#a6adc8",
            activebackground="#45475a",
            cursor="hand2",
            pady=4,
            command=self.update_status_display
        )
        self.btn_refresh.pack(fill=tk.X, pady=4)

        # صندوق السجلات والرسائل
        log_label = tk.Label(main_frame, text="📋 تقرير العمليات الآنية:", font=("Segoe UI", 9, "bold"), fg="#a6adc8", bg="#1e1e2e", anchor="w")
        log_label.pack(fill=tk.X, pady=(5, 2))

        self.log_text = tk.Text(main_frame, height=9, bg="#11111b", fg="#cdd6f4", font=("Consolas", 9), wrap=tk.WORD, bd=0, padx=8, pady=8)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.update_status_display()
        self.log("✅ لوحة تحكم أوبس جاهزة للعمل.")

    def log(self, message: str):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def set_buttons_state(self, enabled: bool):
        st = tk.NORMAL if enabled else tk.DISABLED
        self.btn_pull.config(state=st)
        self.btn_approve.config(state=st)
        self.btn_push.config(state=st)

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

    def start_pull(self):
        self.set_buttons_state(False)
        self.log("⏳ جاري سحب دفعة فصول جديدة لرواية 'After Severing Ties'...")
        def _run():
            try:
                sync_opus_queue.cmd_pull(limit=20, novel_name="After Severing Ties")
                self.root.after(0, lambda: self.log("🎉 اكتمل السحب بنجاح! الفصول موجودة في pending.\n💬 اطلب الآن من Claude في المحادثة صقلها."))
            except Exception as e:
                self.root.after(0, lambda: self.log(f"❌ خطأ أثناء السحب: {e}"))
            finally:
                self.root.after(0, lambda: (self.update_status_display(), self.set_buttons_state(True)))
        threading.Thread(target=_run, daemon=True).start()

    def start_approve_all(self):
        self.set_buttons_state(False)
        self.log("⏳ جاري نقل كافة الفصول المصقولة من pending إلى approved...")
        def _run():
            try:
                cnt = sync_opus_queue.cmd_approve_all()
                self.root.after(0, lambda: self.log(f"⭐ تم اعتماد {cnt} فصول ونقلها بنجاح إلى approved! جاهزة للنشر."))
            except Exception as e:
                self.root.after(0, lambda: self.log(f"❌ خطأ: {e}"))
            finally:
                self.root.after(0, lambda: (self.update_status_display(), self.set_buttons_state(True)))
        threading.Thread(target=_run, daemon=True).start()

    def start_push(self):
        self.set_buttons_state(False)
        self.log("🚀 جاري رفع ونشر الفصول المعتمدة إلى بلوجر وقواعد البيانات...")
        def _run():
            try:
                sync_opus_queue.cmd_push(novel_name="After Severing Ties")
                self.root.after(0, lambda: self.log("🎉 تم النشر والمزامنة بنجاح في بلوجر والجداول!"))
            except Exception as e:
                self.root.after(0, lambda: self.log(f"❌ خطأ أثناء النشر: {e}"))
            finally:
                self.root.after(0, lambda: (self.update_status_display(), self.set_buttons_state(True)))
        threading.Thread(target=_run, daemon=True).start()


def main():
    root = tk.Tk()
    app = OpusAppGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
