#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import subprocess
import threading
import shutil
import ctypes
from tkinter import *
from tkinter import ttk, filedialog, messagebox, font as tkfont
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# ----------------------------- DPI Awareness -----------------------------
if sys.platform == "win32":
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except:
        pass

# ----------------------------- Helper to run adb with NO window -----------------------------
CREATE_NO_WINDOW = 0x08000000

def run_adb(cmd, timeout=90):
    try:
        proc = subprocess.run(
            [ADB_EXE] + cmd,
            capture_output=True,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        stdout = proc.stdout.decode('utf-8', errors='replace').strip()
        stderr = proc.stderr.decode('utf-8', errors='replace').strip()
        return stdout, stderr, proc.returncode
    except Exception as e:
        return "", str(e), -1

# ----------------------------- Resource path helper -----------------------------
def resource_path(relative_path):
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

# ----------------------------- Load custom font -----------------------------
def load_custom_font():
    if sys.platform != "win32":
        return None
    font_path = resource_path("Bellfast-gx9zY.otf")
    if not os.path.exists(font_path):
        font_path = resource_path("Bellfast-gx9zY.otf")
    if not os.path.exists(font_path):
        return None
    ctypes.windll.gdi32.AddFontResourceW(font_path)
    ctypes.windll.user32.SendMessageW(0xFFFF, 0x001D, 0, 0)
    return "Bellfast"

# ----------------------------- Path for ADB -----------------------------
def get_adb_path():
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(base_path, "adb.exe")
    if os.path.exists(candidate):
        return candidate
    return "adb"

ADB_EXE = get_adb_path()
CUSTOM_FONT = load_custom_font() or "Bellfast"

# ----------------------------- Configuration -----------------------------
EXCLUDED_DIRS = ["Android", "data", "obb", "cache", ".thumbnails", ".trash", "system", "vendor"]
CATEGORIES = {
    "photos": (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic"),
    "videos": (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".3gp", ".m4v"),
    "audio": (".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".wma"),
    "documents": (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".rtf", ".md"),
    "code": (".py", ".java", ".c", ".cpp", ".js", ".html", ".css", ".json", ".xml")
}
CUSTOM_EXTENSIONS = {".apk", ".zip"}
MAX_CONCURRENT_PULLS = 4

# ----------------------------- ADB logic (unchanged) -----------------------------
def device_connected():
    out, _, rc = run_adb(["devices"])
    lines = [l for l in out.splitlines() if l.strip() and not l.startswith("List")]
    return len(lines) == 1

def get_real_storage_path():
    out, _, rc = run_adb(["shell", "readlink -f /sdcard 2>/dev/null"])
    if rc == 0 and out and out != "/sdcard":
        return out
    for path in ["/storage/emulated/0", "/storage/self/primary", "/mnt/sdcard"]:
        out, _, rc = run_adb(["shell", f"[ -d {path} ] && echo ok"])
        if rc == 0 and out.strip() == "ok":
            return path
    return "/sdcard"

def android_path_exists(path):
    out, _, rc = run_adb(["shell", f"[ -d {path} ] && echo ok"])
    return rc == 0 and out.strip() == "ok"

def get_files_manually(root_dir, extensions, exclude_dirs, log_callback):
    results = []
    dirs_queue = [root_dir]
    processed = set()
    while dirs_queue:
        current = dirs_queue.pop(0)
        if current in processed:
            continue
        processed.add(current)
        if log_callback and len(processed) % 20 == 0:
            log_callback(f"Scanning: {current} (found {len(results)} files)")
        out, err, rc = run_adb(["shell", f"ls -la {current} 2>/dev/null"], timeout=15)
        if rc != 0 or not out:
            continue
        for line in out.splitlines():
            if not line or line.startswith("total"):
                continue
            parts = line.split()
            if len(parts) < 8:
                continue
            perm = parts[0]
            size_str = parts[4]
            if not size_str.isdigit():
                continue
            name = " ".join(parts[7:])
            if name in (".", ".."):
                continue
            full_path = f"{current}/{name}"
            if perm.startswith("d"):
                if any(ex in full_path for ex in exclude_dirs):
                    continue
                if full_path not in processed:
                    dirs_queue.append(full_path)
            else:
                ext = os.path.splitext(name)[1].lower()
                if ext in extensions:
                    results.append((full_path, int(size_str)))
    return results

def copy_files_parallel(file_list, dest_dir, progress_callback):
    total = len(file_list)
    completed = 0
    os.makedirs(dest_dir, exist_ok=True)
    base = get_real_storage_path()
    def pull_one(item):
        src, _ = item
        rel = os.path.relpath(src, base)
        dst = os.path.join(dest_dir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        _, _, rc = run_adb(["pull", src, dst], timeout=120)
        return rc == 0, src
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_PULLS) as ex:
        futures = {ex.submit(pull_one, item): item for item in file_list}
        for fut in as_completed(futures):
            ok, src = fut.result()
            completed += 1
            progress_callback(completed, total)
            if not ok:
                print(f"Failed: {src}")
    return completed

# ----------------------------- GUI -----------------------------
class CopyZenApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CopyZen v1.0 – Fast Android Transfer")
        self.root.geometry("800x750")
        self.root.minsize(750, 650)
        self.root.configure(bg="#E8E0D5")

        # Fonts: Bellfast (if available) else fallback to Segoe UI (not needed, but kept)
        font_list = ["Bellfast"]
        self.font_normal = self.get_font(font_list, 12, "normal")
        self.font_bold   = self.get_font(font_list, 12, "bold")
        self.font_title  = self.get_font(font_list, 16, "bold")

        self.dest_dir = StringVar()
        self.cat_vars = {}
        self.custom_exts = StringVar(value=",".join(CUSTOM_EXTENSIONS))
        self.found_items = []
        self.base_path = ""
        self.create_widgets()
        self.check_device()

    def get_font(self, families, size, weight):
        for family in families:
            try:
                tkfont.Font(family=family, size=size, weight=weight)
                return (family, size, weight)
            except:
                continue
        return ("Arial", size, weight)

    def create_widgets(self):
        main = Frame(self.root, bg="#E8E0D5")
        main.pack(fill=BOTH, expand=True, padx=15, pady=10)

        title = Label(main, text="CopyZen", font=self.font_title,
                      bg="#E8E0D5", fg="black")
        title.grid(row=0, column=0, columnspan=2, pady=10)

        f1 = LabelFrame(main, text="📱 Device", bg="#E8E0D5", fg="black",
                        font=self.font_bold, bd=2, relief=GROOVE)
        f1.grid(row=1, column=0, columnspan=2, sticky="ew", pady=5)
        self.dev_status = Label(f1, text="Checking...", font=self.font_normal,
                                bg="#E8E0D5", fg="black")
        self.dev_status.pack(anchor=W, padx=10, pady=5)
        Button(f1, text="⟳ Refresh", command=self.check_device, font=self.font_normal,
               bg="#E6D5B8", fg="black", relief=RAISED, bd=2, cursor="hand2").pack(anchor=W, padx=10, pady=5)

        f2 = LabelFrame(main, text="📂 File Types", bg="#E8E0D5", fg="black",
                        font=self.font_bold, bd=2, relief=GROOVE)
        f2.grid(row=2, column=0, columnspan=2, sticky="ew", pady=5)
        row, col = 0, 0
        for cat in CATEGORIES:
            var = BooleanVar(value=True)
            self.cat_vars[cat] = var
            cb = Checkbutton(f2, text=cat.capitalize(), variable=var,
                             font=self.font_normal, bg="#E8E0D5", fg="black",
                             selectcolor="#E8E0D5", activebackground="#E8E0D5",
                             cursor="hand2")
            cb.grid(row=row, column=col, sticky="w", padx=20, pady=2)
            col += 1
            if col > 2:
                col = 0
                row += 1
        ext_frame = Frame(f2, bg="#E8E0D5")
        ext_frame.grid(row=row+1, column=0, columnspan=3, sticky="w", pady=6, padx=20)
        Label(ext_frame, text="➕ Custom:", font=self.font_normal,
              bg="#E8E0D5", fg="black").pack(side=LEFT)
        Entry(ext_frame, textvariable=self.custom_exts, width=35,
              font=self.font_normal, bg="#FFF8E8", fg="black",
              relief=SUNKEN, bd=1).pack(side=LEFT, padx=5)

        f3 = LabelFrame(main, text="💾 Destination", bg="#E8E0D5", fg="black",
                        font=self.font_bold, bd=2, relief=GROOVE)
        f3.grid(row=3, column=0, columnspan=2, sticky="ew", pady=5)
        Entry(f3, textvariable=self.dest_dir, width=55,
              font=self.font_normal, bg="#FFF8E8", fg="black",
              relief=SUNKEN, bd=1).pack(side=LEFT, padx=8, pady=5, fill=X, expand=True)
        Button(f3, text="📁 Browse", command=self.browse, font=self.font_normal,
               bg="#E6D5B8", fg="black", relief=RAISED, bd=2, cursor="hand2").pack(side=LEFT, padx=8)

        btn_frame = Frame(main, bg="#E8E0D5")
        btn_frame.grid(row=4, column=0, columnspan=2, pady=12)
        for text, cmd in [("🔍 1. Find Files", self.find_files),
                          ("📊 2. Estimate Size", self.estimate_size),
                          ("🚀 3. Start Copy", self.start_copy)]:
            btn = Button(btn_frame, text=text, command=cmd, width=16,
                         font=self.font_bold, bg="#E6D5B8", fg="black",
                         relief=RAISED, bd=3, activebackground="#D4C0A0",
                         cursor="hand2")
            btn.pack(side=LEFT, padx=6)
            btn.bind("<ButtonPress-1>", lambda e, b=btn: self.on_button_press(b))
            btn.bind("<ButtonRelease-1>", lambda e, b=btn: self.on_button_release(b))

        self.progress = ttk.Progressbar(main, orient=HORIZONTAL, length=550, mode='determinate')
        self.progress.grid(row=5, column=0, columnspan=2, pady=10, sticky="ew")

        log_frame = LabelFrame(main, text="📜 Log", bg="#E8E0D5", fg="black",
                               font=self.font_bold, bd=2, relief=GROOVE)
        log_frame.grid(row=6, column=0, columnspan=2, sticky="nsew", pady=5)
        main.grid_rowconfigure(6, weight=1)
        main.grid_columnconfigure(0, weight=1)

        self.log_text = Text(log_frame, height=12, wrap=WORD, state=DISABLED,
                             font=self.font_normal, bg="#FFF8E8", fg="black",
                             relief=SUNKEN, bd=2)
        self.log_text.pack(side=LEFT, fill=BOTH, expand=True, padx=5, pady=5)
        scroll = Scrollbar(log_frame, command=self.log_text.yview,
                           bg="#E6D5B8", troughcolor="#D4C0A0")
        scroll.pack(side=RIGHT, fill=Y, padx=5, pady=5)
        self.log_text.config(yscrollcommand=scroll.set)

    def on_button_press(self, btn):
        btn.config(relief=SUNKEN, bg="#C0A880")
    def on_button_release(self, btn):
        btn.config(relief=RAISED, bg="#E6D5B8")

    def log(self, msg):
        self.log_text.config(state=NORMAL)
        self.log_text.insert(END, f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
        self.log_text.see(END)
        self.log_text.config(state=DISABLED)
        self.root.update_idletasks()

    def check_device(self):
        if not device_connected():
            self.dev_status.config(text="❌ No device (enable USB Debugging)", fg="red")
            return False
        self.base_path = get_real_storage_path()
        if not android_path_exists(self.base_path):
            self.dev_status.config(text=f"❌ Cannot access {self.base_path} (unlock device)", fg="red")
            return False
        self.dev_status.config(text=f"✅ Device ready – {self.base_path}", fg="green")
        return True

    def browse(self):
        d = filedialog.askdirectory()
        if d:
            self.dest_dir.set(d)

    def get_extensions(self):
        exts = set()
        for cat, var in self.cat_vars.items():
            if var.get():
                exts.update(CATEGORIES[cat])
        for e in self.custom_exts.get().split(","):
            e = e.strip().lower()
            if e:
                if not e.startswith("."):
                    e = "." + e
                exts.add(e)
        return exts

    def find_files(self):
        if not self.check_device():
            messagebox.showerror("Error", "Device not ready")
            return
        exts = self.get_extensions()
        if not exts:
            messagebox.showwarning("Warning", "No file types selected")
            return
        self.log(f"Scanning {self.base_path} for {len(exts)} extension(s)...")
        def task():
            items = get_files_manually(self.base_path, exts, EXCLUDED_DIRS, self.log)
            self.found_items = items
            self.root.after(0, self.show_found_result, len(items))
        threading.Thread(target=task, daemon=True).start()

    def show_found_result(self, count):
        self.log(f"✅ Found {count} file(s)")
        if count == 0:
            messagebox.showwarning("No files", "No files found.\nMake sure device is UNLOCKED and screen on.")
        else:
            messagebox.showinfo("Success", f"Found {count} files.\nNow click 'Estimate Size'.")

    def estimate_size(self):
        if not self.found_items:
            messagebox.showwarning("No files", "Run 'Find Files' first")
            return
        total = sum(s for _, s in self.found_items)
        mb = total / (1024*1024)
        gb = total / (1024**3)
        self.log(f"Total size: {mb:.2f} MB ({gb:.2f} GB)")
        dest = self.dest_dir.get()
        if dest and os.path.exists(dest):
            free = shutil.disk_usage(dest).free
            free_mb = free/(1024*1024)
            self.log(f"Destination free: {free_mb:.2f} MB")
            if total > free:
                self.log("⚠️ WARNING: Not enough disk space!")
                if not messagebox.askyesno("Low Space", f"Need {mb:.2f} MB, only {free_mb:.2f} MB free. Continue?"):
                    return
        messagebox.showinfo("Estimation done", f"Total size: {mb:.2f} MB\nClick 'Start Copy'.")

    def start_copy(self):
        if not self.found_items:
            messagebox.showwarning("No files", "Run 'Find Files' first")
            return
        dest = self.dest_dir.get()
        if not dest:
            messagebox.showerror("Error", "Select destination folder")
            return
        total = len(self.found_items)
        self.log(f"Copying {total} files to {dest} using {MAX_CONCURRENT_PULLS} parallel streams...")
        self.progress["maximum"] = total
        self.progress["value"] = 0
        def cb(curr, total):
            self.root.after(0, lambda: self.progress.configure(value=curr))
            if curr % 50 == 0 or curr == total:
                self.root.after(0, lambda: self.log(f"Progress: {curr}/{total}"))
        def task():
            success = copy_files_parallel(self.found_items, dest, cb)
            self.root.after(0, lambda: self.log(f"Copy finished. Copied {success} of {total} files."))
            messagebox.showinfo("Done", f"Copied {success} of {total} files.")
        threading.Thread(target=task, daemon=True).start()

# ----------------------------- ICON FIX: Three steps combined -----------------------------
def force_taskbar_icon(window):
    """Use Windows API to set taskbar icon (fallback for stubborn systems)."""
    ico_path = resource_path("copyzen.ico")
    if not os.path.exists(ico_path):
        return
    hicon = ctypes.windll.user32.LoadImageW(0, ico_path, 1, 0, 0, 0x0010 | 0x0002)
    if hicon:
        ctypes.windll.user32.SendMessageW(window.winfo_id(), 0x0080, 0, hicon)  # ICON_BIG
        ctypes.windll.user32.SendMessageW(window.winfo_id(), 0x0080, 1, hicon)  # ICON_SMALL
        ctypes.windll.user32.SetClassLongW(window.winfo_id(), -14, hicon)       # GCL_HICON

def main():
    # Check ADB first
    try:
        subprocess.run([ADB_EXE, "version"], capture_output=True, check=True,
                       creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0)
    except:
        root = Tk()
        root.withdraw()
        messagebox.showerror("Missing ADB", "ADB not found.\nMake sure adb.exe is in the same folder as CopyZen.")
        return

    # Create root window
    root = Tk()
    
    # Step 1 & 2: Call iconbitmap immediately with the bundled .ico file
    ico_path = resource_path("copyzen.ico")
    if os.path.exists(ico_path):
        root.iconbitmap(ico_path)          # sets title bar icon
        root.after(100, lambda: root.iconbitmap(ico_path))  # reapply after window appears
    
    # Step 3 (extra fallback): force taskbar icon using Windows API
    root.after(200, lambda: force_taskbar_icon(root))
    
    # Create the main application
    app = CopyZenApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()