#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude Usage Monitor - GUI (Windows / Linux / macOS)

Claude-styled Tkinter dashboard on top of claude_monitor.py.
- System tray via pystray + pillow (optional, graceful fallback)
- Bilingual UI (中文 / English), toggle button, persisted in config.json

Run:  python claude_monitor_gui.py   (or the packaged ClaudeUsageMonitor.exe)
"""

import json
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import claude_monitor
from claude_monitor import (
    Agg, blocks_of, data_dirs, fmt, load_entries, money, short_model,
)

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

REFRESH_MS = 30_000  # auto refresh interval
# frozen exe: config.json sits next to the .exe, not the PyInstaller temp dir
_APP_DIR = (Path(sys.executable).parent if getattr(sys, "frozen", False)
            else Path(__file__).parent)
CONFIG_PATH = _APP_DIR / "config.json"

# ------------------------------------------------------------ translations ---
L = {
    "zh": {
        "block_title":   "当前 5 小时窗口",
        "block_time":    "{s} - {e}    已用 {el:.0f} 分钟，剩余 {re:.0f} 分钟",
        "no_block":      "当前没有活跃窗口（最近无消息）",
        "blk_stats":     "tokens {t}    成本 {c}    消息 {n}",
        "blk_burn":      "in {i}  out {o}  缓存写 {w}  缓存读 {r}    燃烧 {b} tok/min",
        "usage_label":   "本窗口用量 / 限额（{src} {lim}）",
        "src_auto":      "自动估算",
        "src_custom":    "自定义",
        "usage_text":    "已用 {u}（{p:.0f}%）    余额 {r}",
        "today_title":   "今日用量  {d}",
        "today_stats":   "tokens {t}    消息 {n}\nin {i}  out {o}  缓存写 {w}  缓存读 {r}",
        "today_models":  "模型: {m}",
        "tab_daily":     " 按天 ",
        "tab_models":    " 按模型 ",
        "tab_projects":  " 按项目 ",
        "tab_blocks":    " 5小时窗口 ",
        "tab_monthly":   " 按月 ",
        "col_date":      "日期",
        "col_input":     "Input",
        "col_output":    "Output",
        "col_cachew":    "缓存写",
        "col_cacher":    "缓存读",
        "col_total":     "总计",
        "col_cost":      "成本",
        "col_models":    "模型",
        "col_msgs":      "消息数",
        "col_project":   "项目",
        "col_tokens":    "总 Token",
        "col_block":     "窗口",
        "col_status":    "状态",
        "col_month":     "月份",
        "row_total":     "总计",
        "row_active":    "进行中",
        "row_ended":     "已结束",
        "loading":       "加载中...",
        "loading_data":  "加载数据中...",
        "refreshing":    "刷新中...",
        "status_ok":     "最近刷新 {t} · 共 {n} 条记录",
        "status_err":    "加载失败: {m}",
        "countdown":     "下次刷新 {t}（{s} 秒后）",
        "btn_refresh":   "立即刷新",
        "btn_lang":      "English",
        "note":          "成本为等价 API 价值，订阅用户不按 token 付费",
        "note_tray":     " · 关闭窗口将最小化到托盘",
        "tray_showhide": "显示 / 隐藏",
        "tray_refresh":  "立即刷新",
        "tray_quit":     "退出",
        "tray_min_msg":  "已最小化到系统托盘，点击图标恢复窗口",
        "tray_today":    "今日",
        "no_data":       "未找到 Claude Code 数据目录 (~/.claude/projects)",
        "btn_settings":  "设置",
        "set_title":     "设置",
        "set_note":      ("本工具不需要 API Key。\n"
                          "用量数据直接读取本机 Claude Code 的本地记录文件，\n"
                          "不联网、不上传任何数据。"),
        "set_datadir":   "Claude 数据目录",
        "set_datadir_hint": "留空 = 自动检测：{p}",
        "set_none_found": "（未检测到，请手动选择）",
        "set_limit":     "5 小时窗口限额（美元）",
        "set_limit_hint": "留空 = 按历史最高窗口消耗自动估算",
        "btn_browse":    "浏览...",
        "btn_save":      "保存",
        "btn_cancel":    "取消",
        "set_invalid_limit": "限额必须是数字，例如 35",
    },
    "en": {
        "block_title":   "Current 5-hour Window",
        "block_time":    "{s} - {e}    elapsed {el:.0f} min, {re:.0f} min left",
        "no_block":      "No active window (no recent messages)",
        "blk_stats":     "tokens {t}    cost {c}    msgs {n}",
        "blk_burn":      "in {i}  out {o}  cacheW {w}  cacheR {r}    burn {b} tok/min",
        "usage_label":   "Window usage / limit ({src} {lim})",
        "src_auto":      "auto-estimated",
        "src_custom":    "custom",
        "usage_text":    "used {u} ({p:.0f}%)    remaining {r}",
        "today_title":   "Today  {d}",
        "today_stats":   "tokens {t}    msgs {n}\nin {i}  out {o}  cacheW {w}  cacheR {r}",
        "today_models":  "Models: {m}",
        "tab_daily":     " Daily ",
        "tab_models":    " Models ",
        "tab_projects":  " Projects ",
        "tab_blocks":    " 5h Blocks ",
        "tab_monthly":   " Monthly ",
        "col_date":      "Date",
        "col_input":     "Input",
        "col_output":    "Output",
        "col_cachew":    "CacheW",
        "col_cacher":    "CacheR",
        "col_total":     "Total",
        "col_cost":      "Cost",
        "col_models":    "Models",
        "col_msgs":      "Msgs",
        "col_project":   "Project",
        "col_tokens":    "Tokens",
        "col_block":     "Block",
        "col_status":    "Status",
        "col_month":     "Month",
        "row_total":     "TOTAL",
        "row_active":    "Active",
        "row_ended":     "Ended",
        "loading":       "Loading...",
        "loading_data":  "Loading data...",
        "refreshing":    "Refreshing...",
        "status_ok":     "Last refresh {t} · {n} records",
        "status_err":    "Load failed: {m}",
        "countdown":     "Next refresh {t} (in {s}s)",
        "btn_refresh":   "Refresh",
        "btn_lang":      "中文",
        "note":          "Cost = API-equivalent value; subscription users don't pay per token",
        "note_tray":     " · Closing the window minimizes to tray",
        "tray_showhide": "Show / Hide",
        "tray_refresh":  "Refresh now",
        "tray_quit":     "Quit",
        "tray_min_msg":  "Minimized to system tray; click the icon to restore",
        "tray_today":    "Today",
        "no_data":       "Claude Code data directory not found (~/.claude/projects)",
        "btn_settings":  "Settings",
        "set_title":     "Settings",
        "set_note":      ("No API key is required.\n"
                          "Usage data is read from Claude Code's local transcript\n"
                          "files on this machine — nothing is sent anywhere."),
        "set_datadir":   "Claude data directory",
        "set_datadir_hint": "Leave empty = auto-detect: {p}",
        "set_none_found": "(none found — please choose one)",
        "set_limit":     "5-hour window limit (USD)",
        "set_limit_hint": "Leave empty = auto-estimate from your highest window",
        "btn_browse":    "Browse...",
        "btn_save":      "Save",
        "btn_cancel":    "Cancel",
        "set_invalid_limit": "Limit must be a number, e.g. 35",
    },
}

# --------------------------------------------------------- Claude palette ---
BG       = "#F0EEE6"   # warm cream window background
BG_CARD  = "#FAF9F5"   # ivory card
BG_FIELD = "#FFFFFF"   # table field
BORDER   = "#E0DCD0"
TROUGH   = "#E5E1D6"
FG       = "#3D3929"   # warm dark text
FG_DIM   = "#87867F"
ACCENT   = "#D97757"   # Claude terracotta
ACCENT_D = "#C05F3C"
GREEN    = "#6F8F5E"
YELLOW   = "#C28A2D"
RED      = "#B3452F"
SELECT   = "#EBDDD3"

FONT_SERIF = ("Georgia", 12, "bold")     # Claude-style serif headings
FONT_UI    = ("Segoe UI", 9)
FONT_MONO  = ("Consolas", 10)


def local(ts):
    return ts.astimezone()


def group_by(entries, keyfn):
    groups = defaultdict(Agg)
    for e in entries:
        groups[keyfn(e)].add(e)
    return groups


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def make_tray_image(size=64):
    """Draw a Claude-style terracotta starburst icon."""
    import math
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((0, 0, size - 1, size - 1), fill=BG_CARD)
    cx = cy = size / 2
    r_out, r_in = size * 0.40, size * 0.10
    w = max(3, size // 12)
    for i in range(8):
        ang = math.radians(i * 45)
        x1 = cx + r_in * math.cos(ang)
        y1 = cy + r_in * math.sin(ang)
        x2 = cx + r_out * math.cos(ang)
        y2 = cy + r_out * math.sin(ang)
        d.line((x1, y1, x2, y2), fill=ACCENT, width=w)
    return img


class MonitorGUI:
    def __init__(self, root):
        self.root = root
        root.title("Claude Usage Monitor")
        root.geometry("980x720")
        root.configure(bg=BG)
        root.minsize(780, 560)

        self.config = load_config()
        self.lang = self.config.get("lang", "en")
        if self.lang not in L:
            self.lang = "en"
        self._apply_data_dir()

        self._setup_style()
        self._build_header()
        self._build_tabs()
        self._build_statusbar()

        self.loading = False
        self.tray = None
        self.today_cost_text = "$0.00"
        self.entries_cache = None
        self.next_refresh_at = None
        self._refresh_timer = None
        if TRAY_AVAILABLE:
            self._setup_tray()
            root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.refresh()
        self._tick()

    def tr(self, key):
        return L[self.lang][key]

    def _apply_data_dir(self):
        d = self.config.get("data_dir")
        claude_monitor.EXTRA_DATA_DIRS = [d] if d else []

    def _save_config(self):
        try:
            CONFIG_PATH.write_text(
                json.dumps(self.config, ensure_ascii=False, indent=2),
                encoding="utf-8")
        except OSError:
            pass

    # -------------------------------------------------------------- settings
    def open_settings(self):
        tr = self.tr
        win = tk.Toplevel(self.root)
        win.title(tr("set_title"))
        win.configure(bg=BG, padx=18, pady=14)
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text=tr("set_note"), bg=BG, fg=FG, font=FONT_UI,
                 justify="left", anchor="w").grid(row=0, column=0, columnspan=3,
                                                  sticky="w", pady=(0, 12))

        # data directory
        tk.Label(win, text=tr("set_datadir"), bg=BG, fg=FG,
                 font=("Segoe UI", 9, "bold"), anchor="w").grid(
            row=1, column=0, sticky="w")
        dir_var = tk.StringVar(value=self.config.get("data_dir", ""))
        ent_dir = tk.Entry(win, textvariable=dir_var, width=52, bg=BG_FIELD,
                           fg=FG, relief="flat", font=FONT_UI,
                           highlightthickness=1, highlightbackground=BORDER)
        ent_dir.grid(row=2, column=0, columnspan=2, sticky="we", ipady=3)

        def browse():
            d = filedialog.askdirectory(parent=win)
            if d:
                dir_var.set(d)
        tk.Button(win, text=tr("btn_browse"), command=browse, bg=BG_CARD, fg=FG,
                  relief="flat", padx=10, font=FONT_UI, cursor="hand2",
                  highlightbackground=BORDER, highlightthickness=1).grid(
            row=2, column=2, padx=(6, 0))

        detected = data_dirs()
        hint_p = str(detected[0]) if detected else tr("set_none_found")
        tk.Label(win, text=tr("set_datadir_hint").format(p=hint_p), bg=BG,
                 fg=FG_DIM, font=("Segoe UI", 8), anchor="w").grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(2, 10))

        # block limit
        tk.Label(win, text=tr("set_limit"), bg=BG, fg=FG,
                 font=("Segoe UI", 9, "bold"), anchor="w").grid(
            row=4, column=0, sticky="w")
        lim = self.config.get("block_limit_usd")
        lim_var = tk.StringVar(value="" if lim in (None, "") else str(lim))
        tk.Entry(win, textvariable=lim_var, width=14, bg=BG_FIELD, fg=FG,
                 relief="flat", font=FONT_UI, highlightthickness=1,
                 highlightbackground=BORDER).grid(row=5, column=0, sticky="w",
                                                  ipady=3)
        tk.Label(win, text=tr("set_limit_hint"), bg=BG, fg=FG_DIM,
                 font=("Segoe UI", 8), anchor="w").grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(2, 14))

        err = tk.Label(win, text="", bg=BG, fg=RED, font=("Segoe UI", 8),
                       anchor="w")
        err.grid(row=7, column=0, columnspan=3, sticky="w")

        def save():
            raw = lim_var.get().strip()
            if raw:
                try:
                    limit_val = float(raw)
                except ValueError:
                    err.config(text=tr("set_invalid_limit"))
                    return
                self.config["block_limit_usd"] = limit_val
            else:
                self.config.pop("block_limit_usd", None)
            d = dir_var.get().strip()
            if d:
                self.config["data_dir"] = d
            else:
                self.config.pop("data_dir", None)
            self._save_config()
            self._apply_data_dir()
            win.destroy()
            self.refresh()

        btns = tk.Frame(win, bg=BG)
        btns.grid(row=8, column=0, columnspan=3, sticky="e", pady=(8, 0))
        tk.Button(btns, text=tr("btn_cancel"), command=win.destroy, bg=BG_CARD,
                  fg=FG, relief="flat", padx=14, pady=3, font=FONT_UI,
                  cursor="hand2", highlightbackground=BORDER,
                  highlightthickness=1).pack(side="right", padx=(8, 0))
        tk.Button(btns, text=tr("btn_save"), command=save, bg=ACCENT,
                  fg="#FFFFFF", activebackground=ACCENT_D,
                  activeforeground="#FFFFFF", relief="flat", padx=16, pady=3,
                  font=FONT_UI, cursor="hand2", borderwidth=0).pack(side="right")

    # ------------------------------------------------------------- language
    def toggle_lang(self):
        self.lang = "en" if self.lang == "zh" else "zh"
        self.config["lang"] = self.lang
        self._save_config()
        self._apply_language()
        if self.entries_cache is not None:
            self._render(self.entries_cache)  # redraw dynamic texts

    def _apply_language(self):
        tr = self.tr
        self.blk_title.config(text=tr("block_title"))
        self.btn_refresh.config(text=tr("btn_refresh"))
        self.btn_lang.config(text=tr("btn_lang"))
        self.btn_settings.config(text=tr("btn_settings"))
        note = tr("note") + (tr("note_tray") if TRAY_AVAILABLE else "")
        self.note.config(text=note)
        for i, key in enumerate(self.tab_keys):
            self.nb.tab(i, text=tr(key))
        for tree, keys in self.trees:
            for col, key in zip(tree["columns"], keys):
                tree.heading(col, text=tr(key))
        if self.tray:
            self.tray.update_menu()
            self._update_tray_tooltip()

    # ------------------------------------------------------------------ tray
    def _setup_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem(lambda item: self.tr("tray_showhide"),
                             self._tray_toggle, default=True),
            pystray.MenuItem(lambda item: self.tr("tray_refresh"),
                             lambda: self.root.after(0, self.refresh)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda item: self.tr("tray_quit"), self._tray_quit),
        )
        self.tray = pystray.Icon("claude-monitor", make_tray_image(),
                                 "Claude Usage Monitor", menu)
        self.tray.run_detached()

    def _tray_toggle(self):
        self.root.after(0, self._toggle_window)

    def _toggle_window(self):
        if self.root.state() == "withdrawn":
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        else:
            self.root.withdraw()

    def hide_to_tray(self):
        self.root.withdraw()
        if self.tray:
            try:
                self.tray.notify(self.tr("tray_min_msg"), "Claude Usage Monitor")
            except Exception:
                pass  # notifications unsupported on some Linux backends

    def _tray_quit(self):
        if self.tray:
            self.tray.stop()
        self.root.after(0, self.root.destroy)

    def _update_tray_tooltip(self):
        if self.tray:
            self.tray.title = (f"Claude Usage Monitor · {self.tr('tray_today')} "
                               f"{self.today_cost_text}")

    # ---------------------------------------------------------------- style
    def _setup_style(self):
        s = ttk.Style(self.root)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure(".", background=BG, foreground=FG, fieldbackground=BG_FIELD,
                    bordercolor=BORDER, lightcolor=BG, darkcolor=BG)
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=BG, foreground=FG_DIM,
                    padding=(16, 7), borderwidth=0, font=FONT_UI)
        s.map("TNotebook.Tab",
              background=[("selected", BG_CARD)],
              foreground=[("selected", ACCENT_D)])
        s.configure("Treeview", background=BG_FIELD, foreground=FG,
                    fieldbackground=BG_FIELD, rowheight=26, borderwidth=0,
                    font=FONT_MONO)
        s.configure("Treeview.Heading", background=BG_CARD, foreground=ACCENT_D,
                    borderwidth=0, font=("Segoe UI", 9, "bold"))
        s.map("Treeview", background=[("selected", SELECT)],
              foreground=[("selected", FG)])
        s.configure("Vertical.TScrollbar", background=BG_CARD, troughcolor=BG,
                    bordercolor=BG, arrowcolor=FG_DIM)
        s.configure("Horizontal.TProgressbar", troughcolor=TROUGH,
                    background=ACCENT, borderwidth=0, thickness=14)
        s.configure("Usage.Horizontal.TProgressbar", troughcolor=TROUGH,
                    background=GREEN, borderwidth=0, thickness=14)

    # --------------------------------------------------------------- header
    def _card(self, parent):
        outer = tk.Frame(parent, bg=BORDER, padx=1, pady=1)  # hairline border
        inner = tk.Frame(outer, bg=BG_CARD, padx=14, pady=10)
        inner.pack(fill="both", expand=True)
        return outer, inner

    def _build_header(self):
        tr = self.tr
        top = tk.Frame(self.root, bg=BG, padx=12, pady=10)
        top.pack(fill="x")
        top.columnconfigure(0, weight=3)
        top.columnconfigure(1, weight=2)

        # -- current block card
        outer, blk = self._card(top)
        outer.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.blk_title = tk.Label(blk, text=tr("block_title"), bg=BG_CARD, fg=FG,
                                  font=FONT_SERIF, anchor="w")
        self.blk_title.pack(fill="x")
        self.blk_time = tk.Label(blk, text="-", bg=BG_CARD, fg=FG_DIM,
                                 font=FONT_UI, anchor="w")
        self.blk_time.pack(fill="x", pady=(2, 4))
        self.blk_bar = ttk.Progressbar(blk, style="Horizontal.TProgressbar",
                                       maximum=100)
        self.blk_bar.pack(fill="x", pady=(0, 6))
        self.blk_stats = tk.Label(blk, text="-", bg=BG_CARD, fg=FG,
                                  font=("Consolas", 11), anchor="w", justify="left")
        self.blk_stats.pack(fill="x")
        self.blk_burn = tk.Label(blk, text="", bg=BG_CARD, fg=FG_DIM,
                                 font=FONT_MONO, anchor="w")
        self.blk_burn.pack(fill="x")
        # usage vs limit bar
        self.usage_label = tk.Label(blk, text="-", bg=BG_CARD, fg=FG_DIM,
                                    font=FONT_UI, anchor="w")
        self.usage_label.pack(fill="x", pady=(8, 2))
        self.usage_bar = ttk.Progressbar(blk, style="Usage.Horizontal.TProgressbar",
                                         maximum=100)
        self.usage_bar.pack(fill="x", pady=(0, 4))
        self.usage_text = tk.Label(blk, text="-", bg=BG_CARD, fg=FG,
                                   font=FONT_MONO, anchor="w")
        self.usage_text.pack(fill="x")

        # -- today card
        outer, today = self._card(top)
        outer.grid(row=0, column=1, sticky="nsew")
        self.today_title = tk.Label(today, text="-", bg=BG_CARD, fg=FG,
                                    font=FONT_SERIF, anchor="w")
        self.today_title.pack(fill="x")
        self.today_cost = tk.Label(today, text="$0.00", bg=BG_CARD, fg=ACCENT,
                                   font=("Georgia", 26, "bold"), anchor="w")
        self.today_cost.pack(fill="x")
        self.today_stats = tk.Label(today, text="-", bg=BG_CARD, fg=FG,
                                    font=FONT_MONO, anchor="w", justify="left")
        self.today_stats.pack(fill="x")
        self.today_models = tk.Label(today, text="", bg=BG_CARD, fg=FG_DIM,
                                     font=("Consolas", 9), anchor="w")
        self.today_models.pack(fill="x")

    # ----------------------------------------------------------------- tabs
    def _make_tree(self, parent, keys, widths, anchors):
        frame = tk.Frame(parent, bg=BG_CARD)
        cols = [f"c{i}" for i in range(len(keys))]  # stable ascii column ids
        tree = ttk.Treeview(frame, columns=cols, show="headings")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        for col, key, w, a in zip(cols, keys, widths, anchors):
            tree.heading(col, text=self.tr(key))
            tree.column(col, width=w, anchor=a, stretch=(a == "w"))
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        tree.tag_configure("total", background=BG_CARD, foreground=ACCENT_D)
        tree.tag_configure("active", foreground=GREEN)
        self.trees.append((tree, keys))
        return frame, tree

    def _build_tabs(self):
        self.trees = []
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=12, pady=(0, 4))
        self.tab_keys = ["tab_daily", "tab_models", "tab_projects",
                         "tab_blocks", "tab_monthly"]

        f, self.tree_daily = self._make_tree(
            self.nb, ("col_date", "col_input", "col_output", "col_cachew",
                      "col_cacher", "col_total", "col_cost", "col_models"),
            (100, 90, 90, 90, 100, 100, 90, 220),
            ("w", "e", "e", "e", "e", "e", "e", "w"))
        self.nb.add(f, text=self.tr("tab_daily"))

        f, self.tree_models = self._make_tree(
            self.nb, ("col_models", "col_msgs", "col_input", "col_output",
                      "col_cachew", "col_cacher", "col_cost"),
            (220, 80, 90, 90, 100, 110, 100),
            ("w", "e", "e", "e", "e", "e", "e"))
        self.nb.add(f, text=self.tr("tab_models"))

        f, self.tree_projects = self._make_tree(
            self.nb, ("col_project", "col_msgs", "col_tokens", "col_cost"),
            (480, 90, 120, 100),
            ("w", "e", "e", "e"))
        self.nb.add(f, text=self.tr("tab_projects"))

        f, self.tree_blocks = self._make_tree(
            self.nb, ("col_block", "col_status", "col_msgs", "col_input",
                      "col_output", "col_total", "col_cost"),
            (180, 80, 80, 90, 90, 100, 90),
            ("w", "w", "e", "e", "e", "e", "e"))
        self.nb.add(f, text=self.tr("tab_blocks"))

        f, self.tree_monthly = self._make_tree(
            self.nb, ("col_month", "col_input", "col_output", "col_cachew",
                      "col_cacher", "col_total", "col_cost"),
            (100, 100, 100, 100, 110, 110, 100),
            ("w", "e", "e", "e", "e", "e", "e"))
        self.nb.add(f, text=self.tr("tab_monthly"))

    # ------------------------------------------------------------ statusbar
    def _build_statusbar(self):
        tr = self.tr
        bar = tk.Frame(self.root, bg=BG_CARD, padx=12, pady=5,
                       highlightbackground=BORDER, highlightthickness=1)
        bar.pack(fill="x", side="bottom")
        self.status = tk.Label(bar, text=tr("loading"), bg=BG_CARD, fg=FG_DIM,
                               font=FONT_UI, anchor="w")
        self.status.pack(side="left")
        self.countdown = tk.Label(bar, text="", bg=BG_CARD, fg=ACCENT_D,
                                  font=FONT_UI, anchor="w")
        self.countdown.pack(side="left", padx=(8, 0))
        self.btn_settings = tk.Button(bar, text=tr("btn_settings"),
                                      command=self.open_settings,
                                      bg=BG_CARD, fg=FG, activebackground=SELECT,
                                      activeforeground=FG, relief="flat",
                                      padx=10, pady=2, font=FONT_UI, cursor="hand2",
                                      borderwidth=1, highlightbackground=BORDER)
        self.btn_settings.pack(side="right", padx=(8, 0))
        self.btn_lang = tk.Button(bar, text=tr("btn_lang"), command=self.toggle_lang,
                                  bg=BG_CARD, fg=ACCENT_D, activebackground=SELECT,
                                  activeforeground=ACCENT_D, relief="flat",
                                  padx=10, pady=2, font=FONT_UI, cursor="hand2",
                                  borderwidth=1, highlightbackground=BORDER)
        self.btn_lang.pack(side="right", padx=(8, 0))
        self.btn_refresh = tk.Button(bar, text=tr("btn_refresh"), command=self.refresh,
                                     bg=ACCENT, fg="#FFFFFF", activebackground=ACCENT_D,
                                     activeforeground="#FFFFFF", relief="flat",
                                     padx=14, pady=2, font=FONT_UI, cursor="hand2",
                                     borderwidth=0)
        self.btn_refresh.pack(side="right")
        note = tr("note") + (tr("note_tray") if TRAY_AVAILABLE else "")
        self.note = tk.Label(bar, text=note, bg=BG_CARD, fg=FG_DIM,
                             font=("Segoe UI", 8))
        self.note.pack(side="right", padx=12)

    # -------------------------------------------------------------- refresh
    def _tick(self):
        """1s ticker: countdown to the next auto refresh."""
        if self.loading:
            self.countdown.config(text=self.tr("refreshing"))
        elif self.next_refresh_at:
            remain = max(0, int(self.next_refresh_at - time.time()))
            nxt = datetime.fromtimestamp(self.next_refresh_at).strftime("%H:%M:%S")
            self.countdown.config(text=self.tr("countdown").format(t=nxt, s=remain))
        self.root.after(1000, self._tick)

    def _schedule_refresh(self):
        if self._refresh_timer is not None:
            self.root.after_cancel(self._refresh_timer)
        self.next_refresh_at = time.time() + REFRESH_MS / 1000
        self._refresh_timer = self.root.after(REFRESH_MS, self.refresh)

    def refresh(self):
        if self.loading:
            return
        self.loading = True
        self.status.config(text=self.tr("loading_data"))
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        try:
            entries = load_entries()
        except Exception as exc:  # surface parse failures in the status bar
            self.root.after(0, self._on_error, str(exc))
            return
        self.root.after(0, self._on_loaded, entries)

    def _on_error(self, msg):
        self.loading = False
        self.status.config(text=self.tr("status_err").format(m=msg), fg=RED)
        self._schedule_refresh()

    def _on_loaded(self, entries):
        self.loading = False
        self.entries_cache = entries
        self._render(entries)
        self.status.config(
            text=self.tr("status_ok").format(
                t=datetime.now().strftime("%H:%M:%S"), n=len(entries)),
            fg=FG_DIM)
        self._schedule_refresh()

    # --------------------------------------------------------------- render
    def _render(self, entries):
        tr = self.tr
        now = datetime.now(timezone.utc)

        # ---- current block
        blocks = blocks_of(entries)
        cur = blocks[-1] if blocks and blocks[-1]["start"] <= now < blocks[-1]["end"] else None
        if cur:
            a = cur["agg"]
            elapsed = (now - cur["start"]).total_seconds() / 60
            span = (cur["end"] - cur["start"]).total_seconds() / 60
            remain = max(0, span - elapsed)
            rate = a.total / elapsed if elapsed > 0 else 0
            ratio = elapsed / span * 100
            self.blk_time.config(text=tr("block_time").format(
                s=local(cur["start"]).strftime("%H:%M"),
                e=local(cur["end"]).strftime("%H:%M"), el=elapsed, re=remain))
            self.blk_bar["value"] = ratio
            style = ttk.Style(self.root)
            color = ACCENT if ratio < 60 else (YELLOW if ratio < 85 else RED)
            style.configure("Horizontal.TProgressbar", background=color)
            self.blk_stats.config(text=tr("blk_stats").format(
                t=fmt(a.total), c=money(a.cost), n=a.count))
            self.blk_burn.config(text=tr("blk_burn").format(
                i=fmt(a.input), o=fmt(a.output), w=fmt(a.cache_w),
                r=fmt(a.cache_r), b=fmt(rate)))
        else:
            self.blk_time.config(text=tr("no_block"))
            self.blk_bar["value"] = 0
            self.blk_stats.config(text="-")
            self.blk_burn.config(text="")

        # ---- usage vs limit
        limit = self.config.get("block_limit_usd")
        limit_src = tr("src_custom") if limit else tr("src_auto")
        if not limit:
            past = [b["agg"].cost for b in blocks]
            limit = max(past) if past else 0
        used = cur["agg"].cost if cur else 0.0
        remain_usd = max(0.0, limit - used)
        pct = (used / limit * 100) if limit > 0 else 0
        self.usage_label.config(text=tr("usage_label").format(
            src=limit_src, lim=money(limit)))
        self.usage_bar["value"] = min(100, pct)
        style = ttk.Style(self.root)
        ucolor = GREEN if pct < 60 else (YELLOW if pct < 85 else RED)
        style.configure("Usage.Horizontal.TProgressbar", background=ucolor)
        self.usage_text.config(
            text=tr("usage_text").format(u=money(used), p=pct, r=money(remain_usd)),
            fg=ucolor if pct >= 85 else FG)

        # ---- today
        today_key = local(now).strftime("%Y-%m-%d")
        daily = group_by(entries, lambda e: local(e["ts"]).strftime("%Y-%m-%d"))
        t = daily.get(today_key, Agg())
        self.today_title.config(text=tr("today_title").format(d=today_key))
        self.today_cost_text = money(t.cost)
        self.today_cost.config(text=self.today_cost_text)
        self.today_stats.config(text=tr("today_stats").format(
            t=fmt(t.total), n=t.count, i=fmt(t.input), o=fmt(t.output),
            w=fmt(t.cache_w), r=fmt(t.cache_r)))
        self.today_models.config(text=tr("today_models").format(
            m=", ".join(sorted(short_model(m) for m in t.models)) or "-"))
        self._update_tray_tooltip()

        # ---- daily tab (last 14 days)
        self._fill(self.tree_daily, self._daily_rows(daily, days=14))
        # ---- models tab
        by_model = group_by(entries, lambda e: e["model"] or "?")
        rows = [(short_model(m), a.count, fmt(a.input), fmt(a.output),
                 fmt(a.cache_w), fmt(a.cache_r), money(a.cost))
                for m, a in sorted(by_model.items(), key=lambda kv: -kv[1].cost)]
        rows.append(self._total_row(by_model.values(),
                                    lambda tt: (tr("row_total"), tt.count, fmt(tt.input),
                                                fmt(tt.output), fmt(tt.cache_w),
                                                fmt(tt.cache_r), money(tt.cost))))
        self._fill(self.tree_models, rows)
        # ---- projects tab
        by_proj = group_by(entries, lambda e: e["project"])
        rows = [(p, a.count, fmt(a.total), money(a.cost))
                for p, a in sorted(by_proj.items(), key=lambda kv: -kv[1].cost)]
        rows.append(self._total_row(by_proj.values(),
                                    lambda tt: (tr("row_total"), tt.count,
                                                fmt(tt.total), money(tt.cost))))
        self._fill(self.tree_projects, rows)
        # ---- blocks tab (last 20)
        rows = []
        for b in blocks[-20:][::-1]:
            a = b["agg"]
            active = b["start"] <= now < b["end"]
            rows.append(((f"{local(b['start']).strftime('%m-%d %H:%M')} - "
                          f"{local(b['end']).strftime('%H:%M')}"),
                         tr("row_active") if active else tr("row_ended"), a.count,
                         fmt(a.input), fmt(a.output), fmt(a.total), money(a.cost),
                         "active" if active else ""))
        self._fill(self.tree_blocks, rows, tagged=True)
        # ---- monthly tab
        monthly = group_by(entries, lambda e: local(e["ts"]).strftime("%Y-%m"))
        rows = [(m, fmt(a.input), fmt(a.output), fmt(a.cache_w), fmt(a.cache_r),
                 fmt(a.total), money(a.cost)) for m, a in sorted(monthly.items())]
        rows.append(self._total_row(monthly.values(),
                                    lambda tt: (tr("row_total"), fmt(tt.input),
                                                fmt(tt.output), fmt(tt.cache_w),
                                                fmt(tt.cache_r), fmt(tt.total),
                                                money(tt.cost))))
        self._fill(self.tree_monthly, rows)

    def _daily_rows(self, daily, days):
        cutoff = (datetime.now().astimezone() - timedelta(days=days)).strftime("%Y-%m-%d")
        keys = sorted(k for k in daily if k >= cutoff)
        rows = []
        aggs = []
        for k in reversed(keys):
            a = daily[k]
            aggs.append(a)
            rows.append((k, fmt(a.input), fmt(a.output), fmt(a.cache_w),
                         fmt(a.cache_r), fmt(a.total), money(a.cost),
                         ",".join(sorted(short_model(m) for m in a.models))))
        rows.append(self._total_row(aggs,
                                    lambda tt: (self.tr("row_total"), fmt(tt.input),
                                                fmt(tt.output), fmt(tt.cache_w),
                                                fmt(tt.cache_r), fmt(tt.total),
                                                money(tt.cost), "")))
        return rows

    @staticmethod
    def _total_row(aggs, render):
        t = Agg()
        for a in aggs:
            t.input += a.input; t.output += a.output
            t.cache_w += a.cache_w; t.cache_r += a.cache_r
            t.cost += a.cost; t.count += a.count
        return tuple(render(t)) + ("total",)

    @staticmethod
    def _fill(tree, rows, tagged=False):
        tree.delete(*tree.get_children())
        ncols = len(tree["columns"])
        for row in rows:
            if len(row) > ncols:  # last element is a tag
                tree.insert("", "end", values=row[:ncols], tags=(row[ncols],))
            else:
                tree.insert("", "end", values=row)


def main():
    # No hard exit when the data dir is missing — the Settings dialog lets the
    # user point the tool at a custom Claude data directory.
    root = tk.Tk()
    app = MonitorGUI(root)
    try:
        root.mainloop()
    finally:
        if app.tray:
            app.tray.stop()


if __name__ == "__main__":
    main()
