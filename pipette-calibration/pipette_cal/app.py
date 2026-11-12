"""Tkinter desktop application.

Layout (follows the Claude Design mock-up from the original project):

    +------------------------------------------------------------------+
    | logo  Pipette Calibration           [scale status] [theme] [cfg] |
    | Setup | Environment | Measurements | Results | History           |
    +--------------------------------------------+---------------------+
    |  tab content (cards)                       |  sidebar: progress, |
    |                                            |  certificate, scale |
    +--------------------------------------------+---------------------+
    | [New calibration]          [Email] [Print] [Save PDF] [Calculate]|
    +------------------------------------------------------------------+

All balance I/O happens on a worker thread (see scale.py); the GUI only
drains queues from the Tk event loop.
"""
from __future__ import annotations

import logging
import queue
import sys
import tempfile
import threading
import tkinter as tk
import tkinter.font as tkfont
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __app_name__, __version__
from .certificate import CertificateInfo, build_certificate, default_filename
from .models import (CATALOGUE, LEVELS, REPLICATES, Level, PipetteSpec, full_model_name,
                     resolve_catalogue_name)
from .physics import Environment, air_density, water_density, z_factor
from .report import email_file, open_file, print_file
from .scale import BaseScale, RadwagScale, Reading, ScaleError, SimulatedScale
from .stats import CalibrationResult, evaluate
from .storage import AppConfig, CalibrationRecord, History, now_iso

log = logging.getLogger(__name__)

TABS = ("Setup", "Environment", "Measurements", "Results", "History")
DEFAULT_OPERATOR = "LifeGene Technical Service"

# Automatic capture: a drop is saved when the balance reports a stable reading
# that has not moved for AUTO_STABLE_READINGS consecutive readings spanning at
# least AUTO_STABLE_SECONDS, and that is at least AUTO_MIN_FRACTION of the
# expected mass of the current test volume. After a capture the program tares
# and waits until the reading is back below AUTO_REARM_FRACTION before it will
# capture again, so one drop can never be recorded twice.
AUTO_STABLE_READINGS = 3
AUTO_STABLE_SECONDS = 0.8
AUTO_MIN_FRACTION = 0.30
AUTO_REARM_FRACTION = 0.15
AUTO_MIN_ABS_G = 0.00015          # never capture below 0.15 mg whatever the volume
DATE_FMT = "%d/%m/%Y"

PALETTES = {
    "dark": dict(bg="#0f172a", surface="#1e293b", surface2="#273449", border="#334155",
                 text="#e2e8f0", muted="#94a3b8", accent="#3b82f6", accent_text="#ffffff",
                 green="#22c55e", red="#ef4444", amber="#f59e0b", entry="#0b1220",
                 low="#3b82f6", mid="#06b6d4", high="#8b5cf6", header="#0b1220"),
    "light": dict(bg="#f1f5f9", surface="#ffffff", surface2="#f8fafc", border="#e2e8f0",
                  text="#0f172a", muted="#64748b", accent="#2563eb", accent_text="#ffffff",
                  green="#16a34a", red="#dc2626", amber="#d97706", entry="#ffffff",
                  low="#2563eb", mid="#0891b2", high="#7c3aed", header="#0f172a"),
}


def _parse_bool(text: str) -> bool:
    t = text.strip().lower()
    if t in ("yes", "y", "true", "1", "on", "כן"):
        return True
    if t in ("no", "n", "false", "0", "off", "לא"):
        return False
    raise ValueError(f"expected yes or no, got {text!r}")


def add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


def parse_date(text: str) -> date:
    text = text.strip()
    for fmt in (DATE_FMT, "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Date {text!r} must be in the form dd.mm.yyyy")


def pick_font(candidates: tuple[str, ...], fallback: str) -> str:
    families = set(tkfont.families())
    for name in candidates:
        if name in families:
            return name
    return fallback


# ---------------------------------------------------------------------------
# Small reusable widgets
# ---------------------------------------------------------------------------
class Card(tk.Frame):
    """White/dark card with a coloured accent bar on the left and a title."""

    def __init__(self, master, app: "App", title: str, accent: str | None = None, **kw):
        p = app.p
        super().__init__(master, bg=p["surface"], highlightbackground=p["border"],
                         highlightthickness=1, bd=0, **kw)
        bar = tk.Frame(self, bg=accent or p["accent"], width=4)
        bar.pack(side="left", fill="y")
        inner = tk.Frame(self, bg=p["surface"])
        inner.pack(side="left", fill="both", expand=True, padx=14, pady=10)
        if title:
            tk.Label(inner, text=title.upper(), bg=p["surface"], fg=p["muted"],
                     font=app.f_caption).pack(anchor="w", pady=(0, 6))
        self.body = tk.Frame(inner, bg=p["surface"])
        self.body.pack(fill="both", expand=True)


class Button(tk.Label):
    """Flat button with hover effect (tk.Button ignores colours on Windows)."""

    def __init__(self, master, app: "App", text: str, command, kind: str = "secondary",
                 width: int | None = None, **kw):
        p = app.p
        colours = {
            "primary": (p["accent"], p["accent_text"], "#1d4ed8"),
            "secondary": (p["surface2"], p["text"], p["border"]),
            "success": (p["green"], "#ffffff", "#15803d"),
            "danger": (p["red"], "#ffffff", "#b91c1c"),
            "ghost": (p["surface"], p["muted"], p["surface2"]),
        }[kind]
        self._bg, self._fg, self._hover = colours
        super().__init__(master, text=text, bg=self._bg, fg=self._fg, font=app.f_button,
                         padx=14, pady=7, cursor="hand2", width=width, **kw)
        self._command = command
        self._enabled = True
        self.bind("<Enter>", lambda e: self._enabled and self.config(bg=self._hover))
        self.bind("<Leave>", lambda e: self._enabled and self.config(bg=self._bg))
        self.bind("<Button-1>", self._click)

    def _click(self, _event=None):
        if self._enabled and self._command:
            self._command()

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        self.config(bg=self._bg if enabled else self._hover, cursor="hand2" if enabled else "arrow",
                    fg=self._fg if enabled else "#9ca3af")


class Pill(tk.Label):
    def __init__(self, master, app: "App", text: str, colour: str, **kw):
        super().__init__(master, text=text, bg=colour, fg="#ffffff", font=app.f_caption,
                         padx=10, pady=3, **kw)

    def set(self, text: str, colour: str):
        self.config(text=text, bg=colour)


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self, config: AppConfig | None = None, history: History | None = None):
        super().__init__()
        self.cfg = config or AppConfig.load()
        self.history = history or History()
        self.p = PALETTES[self.cfg.theme if self.cfg.theme in PALETTES else "dark"]

        self.title(f"{__app_name__} v{__version__}")
        self.minsize(1180, 740)
        icon = self._asset("app.ico")
        if icon and sys.platform.startswith("win"):
            try:
                self.iconbitmap(default=str(icon))
            except tk.TclError:
                pass
        try:
            self.state("zoomed")            # Windows: open maximised
        except tk.TclError:
            self.attributes("-zoomed", True) if self.tk.call("tk", "windowingsystem") == "x11" \
                else self.geometry("1280x800")

        ui = pick_font(("Segoe UI", "Helvetica Neue", "DejaVu Sans", "Liberation Sans"), "TkDefaultFont")
        mono = pick_font(("Consolas", "Cascadia Mono", "DejaVu Sans Mono", "Liberation Mono"), "TkFixedFont")
        self.f_title = tkfont.Font(family=ui, size=15, weight="bold")
        self.f_h = tkfont.Font(family=ui, size=11, weight="bold")
        self.f_body = tkfont.Font(family=ui, size=10)
        self.f_small = tkfont.Font(family=ui, size=9)
        self.f_caption = tkfont.Font(family=ui, size=8, weight="bold")
        self.f_button = tkfont.Font(family=ui, size=10, weight="bold")
        self.f_mono = tkfont.Font(family=mono, size=10)
        self.f_display = tkfont.Font(family=mono, size=38, weight="bold")
        self.f_verdict = tkfont.Font(family=ui, size=26, weight="bold")

        # ---- state -----------------------------------------------------
        self.scale: BaseScale | None = None
        self._connecting = False
        self.last_reading: Reading | None = None
        self._auto_armed = True            # False after a capture until the pan reads ~0 again
        self._auto_run: list[Reading] = []  # consecutive stable readings being evaluated
        self._auto_flash_after: str | None = None
        self.weights: dict[Level, list[float]] = {lv: [] for lv in LEVELS}
        self.result: CalibrationResult | None = None
        self.current_record: CalibrationRecord | None = None
        self.pdf_path: Path | None = None
        self._next_date_auto = True
        self.current_tab = tk.StringVar(value=TABS[0])

        # ---- form variables (survive theme rebuilds) --------------------
        self.v_model = tk.StringVar(value=CATALOGUE[4][0])      # PIPETMAN Classic P200
        self.v_tip = tk.StringVar(value=CATALOGUE[4][1].default_tip)
        self.v_serial = tk.StringVar()
        self.v_doc = tk.StringVar(value=self.history.next_document_number())
        today = date.today()
        self.v_date = tk.StringVar(value=today.strftime(DATE_FMT))
        self.v_next = tk.StringVar(value=add_months(today, self.cfg.next_calibration_months).strftime(DATE_FMT))
        self.v_comments = tk.StringVar()
        self.v_temp = tk.StringVar(value=f"{self.cfg.default_temperature_c:g}")
        self.v_air = tk.StringVar(value=f"{self.cfg.default_air_temperature_c:g}")
        self.v_hum = tk.StringVar(value=f"{self.cfg.default_humidity_pct:g}")
        self.v_press = tk.StringVar(value=f"{self.cfg.default_pressure_hpa:g}")
        self.v_balance = tk.StringVar(value=self.cfg.balance_id)
        self.v_ip = tk.StringVar(value=self.cfg.scale_ip)
        self.v_port = tk.StringVar(value=str(self.cfg.scale_port))
        self.v_demo = tk.BooleanVar(value=self.cfg.demo_mode)
        self.v_auto = tk.BooleanVar(value=self.cfg.auto_capture)
        self.v_auto.trace_add("write", lambda *_: self._on_auto_toggle())
        self.v_search = tk.StringVar()

        self.v_model.trace_add("write", lambda *_: self._on_model_change())
        self.v_serial.trace_add("write", lambda *_: self._on_serial_change())
        for v in (self.v_temp, self.v_air, self.v_hum, self.v_press):
            v.trace_add("write", lambda *_: self._update_env_readout())

        self._build()
        self.bind_all("<Return>", self._on_enter)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll_scale)
        if self.cfg.auto_connect:
            self.after(600, lambda: self._connect(silent=True))

    # ------------------------------------------------------------------
    # Building the UI
    # ------------------------------------------------------------------
    def _build(self):
        p = self.p
        self.configure(bg=p["bg"])
        self._style_ttk()
        for child in list(self.winfo_children()):
            child.destroy()
        self._build_header()
        self._build_tabbar()
        body = tk.Frame(self, bg=p["bg"])
        body.pack(fill="both", expand=True, padx=18, pady=(10, 6))
        # the sidebar is packed first so it always keeps its width; the
        # content area receives whatever is left.
        self.sidebar = tk.Frame(body, bg=p["bg"], width=290)
        self.sidebar.pack(side="right", fill="y", padx=(16, 0))
        self.sidebar.pack_propagate(False)
        self.content = tk.Frame(body, bg=p["bg"])
        self.content.pack(side="left", fill="both", expand=True)
        self._build_sidebar()
        self._build_footer()
        self.pages = {
            "Setup": self._page_setup(), "Environment": self._page_environment(),
            "Measurements": self._page_measurements(), "Results": self._page_results(),
            "History": self._page_history(),
        }
        self._show_tab(self.current_tab.get())
        self._on_model_change()
        self._update_env_readout()
        self._refresh_slots()
        self._refresh_sidebar()
        self._refresh_scale_widgets()
        self._refresh_auto_labels()
        self._refresh_history()

    def _style_ttk(self):
        p = self.p
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure("TCombobox", fieldbackground=p["entry"], background=p["surface2"],
                    foreground=p["text"], arrowcolor=p["muted"], bordercolor=p["border"],
                    lightcolor=p["border"], darkcolor=p["border"], padding=5)
        s.map("TCombobox", fieldbackground=[("readonly", p["entry"])],
              foreground=[("readonly", p["text"])])
        self.option_add("*TCombobox*Listbox.background", p["surface"])
        self.option_add("*TCombobox*Listbox.foreground", p["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", p["accent"])
        s.configure("Treeview", background=p["surface"], fieldbackground=p["surface"],
                    foreground=p["text"], bordercolor=p["border"], rowheight=26,
                    font=self.f_body)
        s.configure("Treeview.Heading", background=p["surface2"], foreground=p["muted"],
                    font=self.f_caption, relief="flat")
        s.map("Treeview", background=[("selected", p["accent"])],
              foreground=[("selected", "#ffffff")])
        s.configure("TCheckbutton", background=p["surface"], foreground=p["text"], font=self.f_body)
        s.map("TCheckbutton", background=[("active", p["surface"])])
        s.configure("Vertical.TScrollbar", background=p["surface2"], troughcolor=p["surface"],
                    bordercolor=p["border"], arrowcolor=p["muted"])

    def _build_header(self):
        p = self.p
        h = tk.Frame(self, bg=p["header"], height=64)
        h.pack(fill="x")
        h.pack_propagate(False)
        logo = tk.Frame(h, bg=p["header"])
        logo.pack(side="left", padx=18)
        logo_img = self._load_logo()
        if logo_img is not None:
            self._logo_img = logo_img
            tk.Label(logo, image=logo_img, bg=p["header"]).pack(side="left", padx=(0, 12))
        else:
            txt = tk.Frame(logo, bg=p["header"])
            txt.pack(side="left", padx=(0, 14))
            row = tk.Frame(txt, bg=p["header"])
            row.pack(anchor="w")
            tk.Label(row, text="LIFE", fg="#4a9be0", bg=p["header"],
                     font=(self.f_title.cget("family"), 17, "bold")).pack(side="left")
            tk.Label(row, text="GENE", fg="#8cd36a", bg=p["header"],
                     font=(self.f_title.cget("family"), 17, "bold")).pack(side="left")
            tk.Label(txt, text="Supporting Science", fg="#94a3b8", bg=p["header"],
                     font=(self.f_small.cget("family"), 8, "italic")).pack(anchor="w")
        tk.Frame(logo, bg="#334155", width=1, height=34).pack(side="left", padx=(0, 14))
        tk.Label(logo, text="Pipette Calibration", fg="#f8fafc", bg=p["header"],
                 font=self.f_title).pack(side="left")
        tk.Label(logo, text=f"v{__version__}", fg="#64748b", bg=p["header"],
                 font=self.f_small).pack(side="left", padx=8, pady=(6, 0))

        right = tk.Frame(h, bg=p["header"])
        right.pack(side="right", padx=18)
        Button(right, self, "Settings", self._open_settings, "ghost").pack(side="right", padx=(8, 0))
        Button(right, self, "Light mode" if self.cfg.theme == "dark" else "Dark mode",
               self._toggle_theme, "ghost").pack(side="right")
        self.scale_pill = Pill(right, self, "BALANCE: DISCONNECTED", "#475569", cursor="hand2")
        self.scale_pill.pack(side="right", padx=12)
        self.scale_pill.bind("<Button-1>", lambda e: self._show_tab("Measurements"))

    def _build_tabbar(self):
        p = self.p
        bar = tk.Frame(self, bg=p["surface"], highlightthickness=0)
        bar.pack(fill="x")
        tk.Frame(bar, bg=p["border"], height=1).pack(side="bottom", fill="x")
        self.tab_buttons: dict[str, tk.Label] = {}
        self.tab_underlines: dict[str, tk.Frame] = {}
        for name in TABS:
            cell = tk.Frame(bar, bg=p["surface"])
            cell.pack(side="left", padx=(18 if name == TABS[0] else 0, 6))
            lbl = tk.Label(cell, text=name, bg=p["surface"], fg=p["muted"], font=self.f_h,
                           padx=12, pady=10, cursor="hand2")
            lbl.pack()
            ul = tk.Frame(cell, bg=p["surface"], height=3)
            ul.pack(fill="x")
            lbl.bind("<Button-1>", lambda e, n=name: self._show_tab(n))
            self.tab_buttons[name] = lbl
            self.tab_underlines[name] = ul

    def _show_tab(self, name: str):
        p = self.p
        self.current_tab.set(name)
        for n, lbl in self.tab_buttons.items():
            active = n == name
            lbl.config(fg=p["text"] if active else p["muted"])
            self.tab_underlines[n].config(bg=p["green"] if active else p["surface"])
        for n, page in self.pages.items():
            page.pack_forget()
        self.pages[name].pack(fill="both", expand=True)
        if name == "History":
            self._refresh_history()

    def _build_sidebar(self):
        p = self.p
        prog = Card(self.sidebar, self, "Progress", p["green"])
        prog.pack(fill="x", pady=(0, 12))
        self.progress_label = tk.Label(prog.body, text="0 / 12 measurements", bg=p["surface"],
                                       fg=p["text"], font=self.f_h)
        self.progress_label.pack(anchor="w")
        self.progress_blocks: dict[tuple[Level, int], tk.Frame] = {}
        for lv in LEVELS:
            row = tk.Frame(prog.body, bg=p["surface"])
            row.pack(fill="x", pady=3)
            tk.Label(row, text=lv.value, width=5, anchor="w", bg=p["surface"],
                     fg=p[lv.value.lower()], font=self.f_caption).pack(side="left")
            for i in range(REPLICATES):
                b = tk.Frame(row, bg=p["border"], width=34, height=10)
                b.pack(side="left", padx=2)
                self.progress_blocks[(lv, i)] = b
        self.progress_hint = tk.Label(prog.body, text="", bg=p["surface"], fg=p["muted"],
                                      font=self.f_small, wraplength=230, justify="left")
        self.progress_hint.pack(anchor="w", pady=(6, 0))

        cert = Card(self.sidebar, self, "Certificate", p["accent"])
        cert.pack(fill="x", pady=(0, 12))
        self.side_labels: dict[str, tk.Label] = {}
        for key in ("Document", "Pipette", "Serial", "Date", "Result"):
            row = tk.Frame(cert.body, bg=p["surface"])
            row.pack(fill="x", pady=2)
            tk.Label(row, text=key, width=9, anchor="w", bg=p["surface"], fg=p["muted"],
                     font=self.f_small).pack(side="left")
            val = tk.Label(row, text="-", anchor="w", bg=p["surface"], fg=p["text"],
                           font=self.f_body)
            val.pack(side="left", fill="x", expand=True)
            self.side_labels[key] = val

        sc = Card(self.sidebar, self, "Balance", p["amber"])
        sc.pack(fill="x")
        self.side_scale_value = tk.Label(sc.body, text="---", bg=p["surface"], fg=p["text"],
                                         font=(self.f_mono.cget("family"), 16, "bold"))
        self.side_scale_value.pack(anchor="w")
        self.side_scale_status = tk.Label(sc.body, text="Not connected", bg=p["surface"],
                                          fg=p["muted"], font=self.f_small)
        self.side_scale_status.pack(anchor="w")
        self.side_connect_btn = Button(sc.body, self, "Connect", self._toggle_connect, "primary")
        self.side_connect_btn.pack(anchor="w", pady=(8, 2))
        self.side_scale_addr = tk.Label(sc.body, text="", bg=p["surface"], fg=p["muted"], font=self.f_small,
                                        cursor="hand2", anchor="w")
        self.side_scale_addr.pack(anchor="w")
        self.side_scale_addr.bind("<Button-1>", lambda e: self._show_tab("Measurements"))

    def _build_footer(self):
        p = self.p
        f = tk.Frame(self, bg=p["surface"], highlightbackground=p["border"], highlightthickness=1)
        f.pack(fill="x", side="bottom")
        inner = tk.Frame(f, bg=p["surface"])
        inner.pack(fill="x", padx=18, pady=10)
        Button(inner, self, "New calibration", self._new_calibration, "secondary").pack(side="left")
        self.btn_calc = Button(inner, self, "Calculate", self._calculate, "success")
        self.btn_calc.pack(side="right")
        self.btn_pdf = Button(inner, self, "Save PDF", self._save_pdf, "primary")
        self.btn_pdf.pack(side="right", padx=8)
        self.btn_print = Button(inner, self, "Print", self._print, "secondary")
        self.btn_print.pack(side="right", padx=(0, 0))
        self.btn_email = Button(inner, self, "Email", self._email, "secondary")
        self.btn_email.pack(side="right", padx=8)
        self._refresh_output_buttons()

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------
    def _entry(self, master, var, width=22, readonly=False, mono=False):
        p = self.p
        e = tk.Entry(master, textvariable=var, width=width, bg=p["entry"], fg=p["text"],
                     insertbackground=p["text"], relief="flat", font=self.f_mono if mono else self.f_body,
                     highlightthickness=1, highlightbackground=p["border"],
                     highlightcolor=p["accent"], disabledbackground=p["surface2"],
                     disabledforeground=p["muted"])
        if readonly:
            e.config(state="disabled")
        e.bind("<Return>", lambda ev: "break")     # Enter inside a field never saves a reading
        return e

    def _field(self, master, label, widget_factory, row, col, hint=""):
        p = self.p
        cell = tk.Frame(master, bg=p["surface"])
        cell.grid(row=row, column=col, sticky="new", padx=(0, 18), pady=6)
        tk.Label(cell, text=label, bg=p["surface"], fg=p["accent"], font=self.f_caption).pack(anchor="w")
        w = widget_factory(cell)
        w.pack(fill="x", ipady=4, pady=(3, 0))
        if hint:
            tk.Label(cell, text=hint, bg=p["surface"], fg=p["muted"], font=self.f_small).pack(anchor="w")
        return w

    def _page_setup(self):
        p = self.p
        page = tk.Frame(self.content, bg=p["bg"])
        card = Card(page, self, "Pipette")
        card.pack(fill="x", pady=(0, 12))
        g = card.body
        for c in range(3):
            g.columnconfigure(c, weight=1)
        self._field(g, "Model", lambda m: ttk.Combobox(
            m, textvariable=self.v_model, state="readonly",
            values=[name for name, _, _ in CATALOGUE], font=self.f_body), 0, 0)
        self._field(g, "Tip", lambda m: self._entry(m, self.v_tip), 0, 1,
                    "Suggested from the model - editable")
        self._field(g, "Serial number", lambda m: self._entry(m, self.v_serial), 0, 2)
        self.spec_info = tk.Label(g, text="", bg=p["surface"], fg=p["muted"], font=self.f_small,
                                  justify="left")
        self.spec_info.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self.serial_info = tk.Label(g, text="", bg=p["surface"], fg=p["amber"], font=self.f_small,
                                    justify="left")
        self.serial_info.grid(row=2, column=0, columnspan=3, sticky="w")

        card2 = Card(page, self, "Certificate")
        card2.pack(fill="x", pady=(0, 12))
        g2 = card2.body
        for c in range(3):
            g2.columnconfigure(c, weight=1)
        self._field(g2, "Document number", lambda m: self._entry(m, self.v_doc, mono=True), 0, 0,
                    "Generated automatically - editable")
        e_date = self._field(g2, "Calibration date", lambda m: self._entry(m, self.v_date), 0, 1,
                             "dd/mm/yyyy")
        e_date.bind("<FocusOut>", lambda e: self._on_date_change())
        e_next = self._field(g2, "Next calibration", lambda m: self._entry(m, self.v_next), 0, 2,
                             f"Default: {self.cfg.next_calibration_months} months after calibration")
        e_next.bind("<Key>", lambda e: setattr(self, "_next_date_auto", False))
        self._field(g2, "Place of calibration",
                    lambda m: tk.Label(m, text=self.cfg.place_of_calibration, anchor="w",
                                       bg=p["surface2"], fg=p["text"], font=self.f_body, padx=6), 1, 0)
        self._field(g2, "Calibrated by",
                    lambda m: tk.Label(m, text=self.operator(), anchor="w", bg=p["surface2"],
                                       fg=p["text"], font=self.f_body, padx=6), 1, 1)
        self._field(g2, "Comments", lambda m: self._entry(m, self.v_comments), 2, 0)
        g2.grid_slaves(row=2, column=0)[0].grid_configure(columnspan=3)
        return page

    def _page_environment(self):
        p = self.p
        page = tk.Frame(self.content, bg=p["bg"])
        card = Card(page, self, "Environmental conditions")
        card.pack(fill="x", pady=(0, 12))
        g = card.body
        for c in range(5):
            g.columnconfigure(c, weight=1)
        self._field(g, "Air temperature (°C)", lambda m: self._entry(m, self.v_air, mono=True), 0, 0)
        self._field(g, "Air pressure (hPa)", lambda m: self._entry(m, self.v_press, mono=True), 0, 1,
                    "1013.25 if unknown")
        self._field(g, "Relative humidity (%)", lambda m: self._entry(m, self.v_hum, mono=True), 0, 2)
        self._field(g, "Water temperature (°C)", lambda m: self._entry(m, self.v_temp, mono=True), 0, 3,
                    "Measured in the test water, 0 - 40 °C")
        self._field(g, "Balance ID", lambda m: self._entry(m, self.v_balance), 0, 4,
                    "Printed on the certificate")

        card2 = Card(page, self, "Derived conversion factors", p["amber"])
        card2.pack(fill="x")
        g2 = card2.body
        self.env_readout: dict[str, tk.Label] = {}
        for i, (key, unit) in enumerate((("Water density", "kg/m³"), ("Air density", "kg/m³"),
                                         ("Z factor", "µL/mg"))):
            cell = tk.Frame(g2, bg=p["surface"])
            cell.grid(row=0, column=i, padx=(0, 36), sticky="w")
            tk.Label(cell, text=key.upper(), bg=p["surface"], fg=p["muted"], font=self.f_caption).pack(anchor="w")
            val = tk.Label(cell, text="-", bg=p["surface"], fg=p["text"],
                           font=(self.f_mono.cget("family"), 16, "bold"))
            val.pack(anchor="w")
            tk.Label(cell, text=unit, bg=p["surface"], fg=p["muted"], font=self.f_small).pack(anchor="w")
            self.env_readout[key] = val
        tk.Label(g2, text=("Volume = mass × Z.  Z corrects for the density of water at the test "
                           "temperature and for air buoyancy (steel reference weights, 8000 kg/m³)."),
                 bg=p["surface"], fg=p["muted"], font=self.f_small, wraplength=760,
                 justify="left").grid(row=1, column=0, columnspan=3, sticky="w", pady=(10, 0))
        return page

    def _page_measurements(self):
        p = self.p
        page = tk.Frame(self.content, bg=p["bg"])

        conn = Card(page, self, "Balance connection", p["amber"])
        conn.pack(fill="x", pady=(0, 12))
        row = tk.Frame(conn.body, bg=p["surface"])
        row.pack(fill="x")
        tk.Label(row, text="IP", bg=p["surface"], fg=p["muted"], font=self.f_caption).pack(side="left")
        self._entry(row, self.v_ip, width=15, mono=True).pack(side="left", padx=(6, 14), ipady=3)
        tk.Label(row, text="PORT", bg=p["surface"], fg=p["muted"], font=self.f_caption).pack(side="left")
        self._entry(row, self.v_port, width=6, mono=True).pack(side="left", padx=(6, 14), ipady=3)
        ttk.Checkbutton(row, text="Demo mode (no balance)", variable=self.v_demo).pack(side="left", padx=(0, 14))
        ttk.Checkbutton(row, text="Auto-save when stable", variable=self.v_auto).pack(side="left", padx=(0, 14))
        self.btn_connect = Button(row, self, "Connect", self._toggle_connect, "primary")
        self.btn_connect.pack(side="left")
        self.btn_listen = Button(row, self, "Start listening", self._toggle_listen, "secondary")
        self.btn_listen.pack(side="left", padx=8)
        self.btn_zero = Button(row, self, "Zero", lambda: self._scale_cmd("zero"), "secondary")
        self.btn_zero.pack(side="left")
        self.btn_tare = Button(row, self, "Tare", lambda: self._scale_cmd("tare"), "secondary")
        self.btn_tare.pack(side="left", padx=8)
        self.btn_drop = Button(row, self, "Simulate drop", self._simulate_drop, "ghost")
        self.btn_drop.pack(side="left")

        live = tk.Frame(page, bg=p["surface"], highlightbackground=p["border"], highlightthickness=1)
        live.pack(fill="x", pady=(0, 12))
        left = tk.Frame(live, bg=p["surface"])
        left.pack(side="left", padx=18, pady=10)
        tk.Label(left, text="LIVE READING", bg=p["surface"], fg=p["muted"], font=self.f_caption).pack(anchor="w")
        self.live_value = tk.Label(left, text="--.------", bg=p["surface"], fg=p["text"], font=self.f_display)
        self.live_value.pack(anchor="w")
        self.live_raw = tk.Label(left, text="", bg=p["surface"], fg=p["muted"], font=self.f_mono)
        self.live_raw.pack(anchor="w")
        right = tk.Frame(live, bg=p["surface"])
        right.pack(side="right", padx=18, pady=10, fill="y")
        self.live_stable = Pill(right, self, "NO DATA", "#475569")
        self.live_stable.pack(anchor="e")
        self.live_target = tk.Label(right, text="", bg=p["surface"], fg=p["text"], font=self.f_h,
                                    justify="right")
        self.live_target.pack(anchor="e", pady=(10, 0))
        self.live_hint = tk.Label(right, text="", bg=p["surface"], fg=p["muted"], font=self.f_small)
        self.live_hint.pack(anchor="e", pady=(4, 0))
        self.auto_status = tk.Label(right, text="", bg=p["surface"], fg=p["amber"], font=self.f_caption)
        self.auto_status.pack(anchor="e", pady=(2, 0))
        btns = tk.Frame(right, bg=p["surface"])
        btns.pack(anchor="e", pady=(8, 0))
        Button(btns, self, "Undo last", self._undo_last, "ghost").pack(side="left", padx=(0, 6))
        self.btn_save = Button(btns, self, "Save reading  ⏎", self._save_reading, "success")
        self.btn_save.pack(side="left")

        grid = tk.Frame(page, bg=p["bg"])
        grid.pack(fill="both", expand=True)
        self.slot_rows: dict[tuple[Level, int], dict[str, tk.Label]] = {}
        self.level_headers: dict[Level, tk.Label] = {}
        for ci, lv in enumerate(LEVELS):
            grid.columnconfigure(ci, weight=1, uniform="lv")
            card = Card(grid, self, "", p[lv.value.lower()])
            card.grid(row=0, column=ci, sticky="nsew", padx=(0 if ci == 0 else 6, 0 if ci == 2 else 6))
            hdr = tk.Label(card.body, text=lv.value, bg=p["surface"], fg=p[lv.value.lower()], font=self.f_h)
            hdr.pack(anchor="w")
            self.level_headers[lv] = hdr
            head = tk.Frame(card.body, bg=p["surface"])
            head.pack(fill="x", pady=(6, 2))
            for text, w in (("#", 3), ("Weight (g)", 13), ("Volume (µL)", 12), ("", 3)):
                tk.Label(head, text=text, width=w, anchor="w", bg=p["surface"], fg=p["muted"],
                         font=self.f_caption).pack(side="left")
            for i in range(REPLICATES):
                r = tk.Frame(card.body, bg=p["surface"], highlightthickness=1, highlightbackground=p["surface"])
                r.pack(fill="x", pady=2)
                n = tk.Label(r, text=str(i + 1), width=3, anchor="w", bg=p["surface"], fg=p["muted"], font=self.f_body)
                n.pack(side="left")
                wv = tk.Label(r, text="", width=13, anchor="w", bg=p["surface"], fg=p["text"], font=self.f_mono)
                wv.pack(side="left")
                vol = tk.Label(r, text="", width=12, anchor="w", bg=p["surface"], fg=p["muted"], font=self.f_mono)
                vol.pack(side="left")
                x = tk.Label(r, text="✕", width=3, bg=p["surface"], fg=p["muted"], cursor="hand2", font=self.f_body)
                x.pack(side="left")
                x.bind("<Button-1>", lambda e, l=lv, k=i: self._clear_slot(l, k))
                self.slot_rows[(lv, i)] = {"frame": r, "n": n, "w": wv, "v": vol, "x": x}
        return page

    def _page_results(self):
        p = self.p
        page = tk.Frame(self.content, bg=p["bg"])
        self.verdict_frame = tk.Frame(page, bg=p["surface2"], highlightbackground=p["border"], highlightthickness=1)
        self.verdict_frame.pack(fill="x", pady=(0, 12))
        self.verdict_label = tk.Label(self.verdict_frame, text="No results yet", bg=p["surface2"],
                                      fg=p["muted"], font=self.f_verdict, pady=12)
        self.verdict_label.pack(side="left", padx=18)
        self.verdict_sub = tk.Label(self.verdict_frame, text="Complete 12 measurements or press Calculate.",
                                    bg=p["surface2"], fg=p["muted"], font=self.f_body, justify="left")
        self.verdict_sub.pack(side="left", padx=6)

        grid = tk.Frame(page, bg=p["bg"])
        grid.pack(fill="both", expand=True)
        self.result_cards: dict[Level, dict[str, tk.Label]] = {}
        rows = (("Average volume", "mean"), ("Systematic error", "sys"), ("Random error (SD)", "rnd"),
                ("Random error (%)", "cv"), ("Uncertainty (k=2)", "unc"), ("Accuracy", "acc"),
                ("Weights g → µL", "weights"))
        for ci, lv in enumerate(LEVELS):
            grid.columnconfigure(ci, weight=1, uniform="res")
            card = Card(grid, self, "", p[lv.value.lower()])
            card.grid(row=0, column=ci, sticky="nsew", padx=(0 if ci == 0 else 6, 0 if ci == 2 else 6))
            top = tk.Frame(card.body, bg=p["surface"])
            top.pack(fill="x")
            tk.Label(top, text=lv.value, bg=p["surface"], fg=p[lv.value.lower()], font=self.f_h).pack(side="left")
            labels: dict[str, tk.Label] = {}
            labels["nominal"] = tk.Label(top, text="", bg=p["surface"], fg=p["muted"], font=self.f_small)
            labels["nominal"].pack(side="left", padx=8)
            labels["pill"] = Pill(top, self, "-", "#475569")
            labels["pill"].pack(side="right")
            for text, key in rows:
                r = tk.Frame(card.body, bg=p["surface"])
                r.pack(fill="x", pady=3)
                tk.Label(r, text=text, width=16, anchor="w", bg=p["surface"], fg=p["muted"],
                         font=self.f_small).pack(side="left")
                val = tk.Label(r, text="-", anchor="w", bg=p["surface"], fg=p["text"], font=self.f_mono,
                               justify="left")
                val.pack(side="left", fill="x", expand=True)
                labels[key] = val
            self.result_cards[lv] = labels
        return page

    def _page_history(self):
        p = self.p
        page = tk.Frame(self.content, bg=p["bg"])
        card = Card(page, self, "Calibration history")
        card.pack(fill="both", expand=True)
        top = tk.Frame(card.body, bg=p["surface"])
        top.pack(fill="x", pady=(0, 8))
        tk.Label(top, text="SEARCH", bg=p["surface"], fg=p["muted"], font=self.f_caption).pack(side="left")
        e = self._entry(top, self.v_search, width=28)
        e.pack(side="left", padx=8, ipady=3)
        e.bind("<KeyRelease>", lambda ev: self._refresh_history())
        Button(top, self, "Re-create PDF", self._history_pdf, "primary").pack(side="right")
        Button(top, self, "Load into form", self._history_load, "secondary").pack(side="right", padx=8)
        cols = ("document", "date", "model", "serial", "tip", "verdict", "operator")
        self.history_tree = ttk.Treeview(card.body, columns=cols, show="headings", selectmode="browse")
        for c, w in zip(cols, (150, 140, 90, 130, 80, 80, 140)):
            self.history_tree.heading(c, text=c.upper())
            self.history_tree.column(c, width=w, anchor="w")
        sb = ttk.Scrollbar(card.body, orient="vertical", command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=sb.set)
        self.history_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.history_tree.tag_configure("PASS", foreground=p["green"])
        self.history_tree.tag_configure("FAIL", foreground=p["red"])
        return page

    # ------------------------------------------------------------------
    # Form logic
    # ------------------------------------------------------------------
    def spec(self) -> PipetteSpec:
        return resolve_catalogue_name(self.v_model.get())[0]

    def series(self) -> str:
        return resolve_catalogue_name(self.v_model.get())[1]

    def operator(self) -> str:
        return self.cfg.operator.strip() or DEFAULT_OPERATOR

    def _on_model_change(self):
        if not hasattr(self, "spec_info"):
            return
        s = self.spec()
        self.v_tip.set(s.default_tip)
        self.spec_info.config(text=(
            f"Range {s.range_label.replace('uL', 'µL')}  ·  {s.channels} channel{'s' if s.channels > 1 else ''}  ·  "
            f"Test volumes: {s.test_volumes[0]:g} / {s.test_volumes[1]:g} / {s.test_volumes[2]:g} µL      "
            f"Limits: systematic error ± {s.sys_limit_ul:g} µL,  random error ≤ {s.rnd_limit_ul:g} µL"))
        for lv in LEVELS:
            self.level_headers[lv].config(text=f"{lv.value}   {s.volume_for(lv):g} µL")
        self._refresh_sidebar()
        self._refresh_target()

    def _on_serial_change(self):
        if not hasattr(self, "serial_info"):
            return
        rec = self.history.last_for_serial(self.v_serial.get())
        if rec:
            self.serial_info.config(text=f"Previous calibration of this serial: {rec.document_no} "
                                         f"on {rec.calibrated_at[:10]}  ({rec.verdict})")
        else:
            self.serial_info.config(text="")
        self._refresh_sidebar()

    def _on_date_change(self):
        try:
            d = parse_date(self.v_date.get())
        except ValueError:
            return
        if self._next_date_auto:
            self.v_next.set(add_months(d, self.cfg.next_calibration_months).strftime(DATE_FMT))
        self._refresh_sidebar()

    def _environment(self) -> Environment:
        try:
            env = Environment(float(self.v_temp.get()), float(self.v_hum.get()), float(self.v_press.get()),
                              float(self.v_air.get()))
        except ValueError:
            raise ValueError("Temperatures, humidity and pressure must be numbers.") from None
        env.validate()
        return env

    def _update_env_readout(self):
        if not hasattr(self, "env_readout"):
            return
        try:
            env = self._environment()
        except ValueError:
            for lbl in self.env_readout.values():
                lbl.config(text="-")
            return
        self.env_readout["Water density"].config(text=f"{water_density(env.temperature_c):.3f}")
        self.env_readout["Air density"].config(
            text=f"{air_density(env.air_t, env.humidity_pct, env.pressure_hpa):.4f}")
        self.env_readout["Z factor"].config(text=f"{z_factor(env):.5f}")
        self._refresh_slots()

    # ------------------------------------------------------------------
    # Balance
    # ------------------------------------------------------------------
    def _toggle_connect(self):
        if self._connecting:
            return
        if self.scale and self.scale.connected:
            self.scale.disconnect()
            self.scale = None
            self._refresh_scale_widgets()
            return
        self._connect(silent=False)

    def _connect(self, silent: bool):
        """Open the balance connection on a worker thread; *silent* suppresses
        the error dialog (used for the automatic connection at start-up)."""
        try:
            if self.v_demo.get():
                scale: BaseScale = SimulatedScale(poll_interval=self.cfg.poll_interval_s)
            else:
                scale = RadwagScale(self.v_ip.get().strip(), int(self.v_port.get()), self.cfg.poll_interval_s)
        except ValueError:
            if not silent:
                messagebox.showerror("Balance", "The port must be a number.", parent=self)
            return
        self.cfg.scale_ip, self.cfg.demo_mode = self.v_ip.get().strip(), self.v_demo.get()
        self.cfg.scale_port = scale.port if isinstance(scale, RadwagScale) else self.cfg.scale_port
        self.cfg.save()
        self._connecting = True
        self._set_connecting_ui(True)

        def work():
            try:
                scale.connect()
                error = None
            except ScaleError as exc:
                error = str(exc)
            self.after(0, lambda: done(error))

        def done(error: str | None):
            self._connecting = False
            if error is None:
                self.scale = scale
                try:
                    self.scale.start_listening()
                except ScaleError as exc:
                    error = str(exc)
            if error is not None:
                log.warning("balance connection failed: %s", error)
                if not silent:
                    messagebox.showerror("Balance", error, parent=self)
            self._set_connecting_ui(False)
            self._refresh_scale_widgets()
            self._refresh_target()

        threading.Thread(target=work, name="balance-connect", daemon=True).start()

    def _set_connecting_ui(self, busy: bool):
        for b in (self.btn_connect, self.side_connect_btn):
            b.config(text="Connecting..." if busy else b.cget("text"))
            b.set_enabled(not busy)
        if busy:
            self.scale_pill.set("BALANCE: CONNECTING...", self.p["amber"])
            self.side_scale_status.config(text=f"Connecting to {self.v_ip.get().strip()}:{self.v_port.get()} ...")

    def _toggle_listen(self):
        if not self.scale or not self.scale.connected:
            return
        if self.scale.listening:
            self.scale.stop_listening()
        else:
            self.scale.start_listening()
        self._refresh_scale_widgets()

    def _scale_cmd(self, cmd: str):
        if not self.scale or not self.scale.connected:
            messagebox.showinfo("Balance", "Connect to the balance first.", parent=self)
            return
        try:
            getattr(self.scale, cmd)()
        except (ScaleError, OSError) as exc:
            messagebox.showerror("Balance", str(exc), parent=self)

    def _simulate_drop(self):
        if isinstance(self.scale, SimulatedScale):
            lv, _ = self._next_slot() or (Level.HIGH, 0)
            grams = self.spec().volume_for(lv) / 1000.0 / z_factor(self._safe_env())
            self.scale.add_drop(grams)

    def _safe_env(self) -> Environment:
        try:
            return self._environment()
        except ValueError:
            return Environment(self.cfg.default_temperature_c, self.cfg.default_humidity_pct,
                               self.cfg.default_pressure_hpa, self.cfg.default_air_temperature_c)

    def _poll_scale(self):
        if self.scale:
            reading = None
            try:
                while True:
                    reading = self.scale.readings.get_nowait()
                    if self.v_auto.get():
                        self._auto_capture(reading)
            except queue.Empty:
                pass
            if reading:
                self.last_reading = reading
                self._show_reading(reading)
            try:
                while True:
                    kind, msg = self.scale.events.get_nowait()
                    if kind == "error":
                        self._refresh_scale_widgets()
                        messagebox.showerror("Balance", msg, parent=self)
            except queue.Empty:
                pass
            if not self.scale.connected and self.scale_pill.cget("text") != "BALANCE: DISCONNECTED":
                self._refresh_scale_widgets()
        self.after(100, self._poll_scale)

    def _show_reading(self, r: Reading):
        p = self.p
        self.live_value.config(text=r.formatted(), fg=p["text"] if r.stable else p["amber"])
        self.live_raw.config(text=r.raw)
        self.live_stable.set("STABLE" if r.stable else "UNSTABLE", p["green"] if r.stable else p["amber"])
        self.side_scale_value.config(text=f"{r.formatted()} g")

    def _refresh_scale_widgets(self):
        p = self.p
        connected = bool(self.scale and self.scale.connected)
        listening = bool(connected and self.scale.listening)
        demo = isinstance(self.scale, SimulatedScale)
        self.btn_connect.config(text="Disconnect" if connected else "Connect")
        self.side_connect_btn.config(text="Disconnect" if connected else "Connect")
        self.side_scale_addr.config(text="Demo mode (simulator)" if self.v_demo.get() else
                                    f"{self.v_ip.get().strip()}:{self.v_port.get()}")
        self.btn_listen.config(text="Stop listening" if listening else "Start listening")
        for b in (self.btn_listen, self.btn_zero, self.btn_tare):
            b.set_enabled(connected)
        self.btn_drop.set_enabled(demo)
        if connected:
            label = "SIMULATOR" if demo else f"{self.scale.ip}:{self.scale.port}"
            self.scale_pill.set(f"BALANCE: {label}", p["green"] if listening else p["amber"])
            self.side_scale_status.config(text=("Listening" if listening else "Connected, paused") +
                                               (" (demo)" if demo else ""))
        else:
            self.scale_pill.set("BALANCE: DISCONNECTED", "#475569")
            self.side_scale_status.config(text="Not connected")
            self.side_scale_value.config(text="---")
            self.live_stable.set("NO DATA", "#475569")

    # ------------------------------------------------------------------
    # Measurements
    # ------------------------------------------------------------------
    def _next_slot(self) -> tuple[Level, int] | None:
        for lv in LEVELS:
            if len(self.weights[lv]) < REPLICATES:
                return lv, len(self.weights[lv])
        return None

    def _on_enter(self, _event=None):
        if self.current_tab.get() != "Measurements":
            return
        if isinstance(self.focus_get(), tk.Entry):
            return
        self._save_reading()

    def _expected_mass_g(self) -> float | None:
        slot = self._next_slot()
        if slot is None:
            return None
        return self.spec().volume_for(slot[0]) / 1000.0 / z_factor(self._safe_env())

    def _on_auto_toggle(self):
        self.cfg.auto_capture = self.v_auto.get()
        self.cfg.save()
        self._auto_run = []
        self._auto_armed = True
        if hasattr(self, "live_hint"):
            self._refresh_auto_labels()

    def _refresh_auto_labels(self, status: str = "", colour: str | None = None):
        p = self.p
        if self.v_auto.get():
            self.live_hint.config(text="Auto-save is on: dispense, wait for a stable reading.  Enter still saves manually.")
        else:
            self.live_hint.config(text="Press  Enter  to save the reading into the next slot")
        self.auto_status.config(text=status, fg=colour or p["amber"])

    def _auto_capture(self, r: Reading):
        """Called for every reading while auto-save is on."""
        if not hasattr(self, "auto_status"):
            return
        expected = self._expected_mass_g()
        if expected is None:                       # all slots full
            return
        min_capture = max(expected * AUTO_MIN_FRACTION, AUTO_MIN_ABS_G)
        rearm_below = max(expected * AUTO_REARM_FRACTION, AUTO_MIN_ABS_G * 0.5)
        value = r.value_g

        if not self._auto_armed:
            # wait for the tare to take effect / the pan to read ~0 again
            if abs(value) < rearm_below:
                self._auto_armed = True
                self._auto_run = []
                self._refresh_auto_labels("READY - waiting for the next drop")
            return

        if value < min_capture:
            self._auto_run = []
            self._refresh_auto_labels("READY - waiting for the next drop")
            return

        tolerance = max(expected * 0.002, 3e-6)
        if not r.stable or (self._auto_run and abs(value - self._auto_run[-1].value_g) > tolerance):
            self._auto_run = [r] if r.stable else []
            self._refresh_auto_labels("STABILISING ...")
            return
        self._auto_run.append(r)
        n = len(self._auto_run)
        span = self._auto_run[-1].timestamp - self._auto_run[0].timestamp
        if n >= AUTO_STABLE_READINGS and span >= AUTO_STABLE_SECONDS:
            self._auto_run = []
            self._auto_armed = False
            self._commit_reading(value, auto=True)
        else:
            self._refresh_auto_labels(f"STABLE {min(n, AUTO_STABLE_READINGS)}/{AUTO_STABLE_READINGS} ...")

    def _commit_reading(self, value: float, auto: bool):
        """Store *value* in the next slot, tare the balance, advance."""
        slot = self._next_slot()
        if slot is None:
            return
        lv, idx = slot
        self.weights[lv].append(value)
        try:
            if self.scale:
                self.scale.tare()                # ready for the next drop
        except (ScaleError, OSError) as exc:
            log.warning("tare failed: %s", exc)
        if isinstance(self.scale, SimulatedScale):
            self.scale.target_g = self.scale._offset_g = 0.0
        self.last_reading = None
        self._refresh_slots()
        self._refresh_auto_labels(f"SAVED {lv.value} #{idx + 1}:  {value:.6f} g" + ("  (auto)" if auto else ""),
                                  self.p["green"])
        if auto:
            self.bell()                      # audible confirmation, hands stay on the pipette
        if self._next_slot() is None:
            self.after(150, self._calculate)

    def _save_reading(self):
        if not self.last_reading or not self.scale or not self.scale.connected:
            messagebox.showinfo("Balance", "No reading from the balance yet.", parent=self)
            return
        slot = self._next_slot()
        if slot is None:
            messagebox.showinfo("Measurements", "All 12 measurements are recorded.", parent=self)
            return
        lv, _ = slot
        value = self.last_reading.value_g
        if value <= 0:
            if not messagebox.askyesno("Measurements", f"The reading is {value:+.6f} g. Save it anyway?",
                                       parent=self):
                return
        self._auto_armed = False
        self._auto_run = []
        self._commit_reading(value, auto=False)

    def _undo_last(self):
        for lv in reversed(LEVELS):
            if self.weights[lv]:
                self.weights[lv].pop()
                break
        self._refresh_slots()

    def _clear_slot(self, lv: Level, idx: int):
        if idx < len(self.weights[lv]):
            del self.weights[lv][idx]
            self._refresh_slots()

    def _refresh_slots(self):
        if not hasattr(self, "slot_rows"):
            return
        p = self.p
        nxt = self._next_slot()
        z = z_factor(self._safe_env())
        done = 0
        for lv in LEVELS:
            for i in range(REPLICATES):
                row = self.slot_rows[(lv, i)]
                block = self.progress_blocks[(lv, i)]
                if i < len(self.weights[lv]):
                    w = self.weights[lv][i]
                    row["w"].config(text=f"{w:.6f}")
                    row["v"].config(text=f"{w * 1000 * z:.3f}")
                    row["frame"].config(highlightbackground=p["surface"])
                    row["x"].config(fg=p["red"])
                    block.config(bg=p[lv.value.lower()])
                    done += 1
                else:
                    row["w"].config(text="")
                    row["v"].config(text="")
                    row["x"].config(fg=p["surface"])
                    active = nxt == (lv, i)
                    row["frame"].config(highlightbackground=p["accent"] if active else p["surface"])
                    block.config(bg=p["accent"] if active else p["border"])
        self.progress_label.config(text=f"{done} / {REPLICATES * 3} measurements")
        self.progress_hint.config(text=(
            "All measurements recorded - press Calculate." if nxt is None else
            f"Next: {nxt[0].value} #{nxt[1] + 1} - dispense {self.spec().volume_for(nxt[0]):g} µL and press Enter."))
        self._refresh_target()

    def _refresh_target(self):
        if not hasattr(self, "live_target"):
            return
        nxt = self._next_slot()
        if nxt is None:
            self.live_target.config(text="Done")
        else:
            lv, i = nxt
            self.live_target.config(text=f"{lv.value}  #{i + 1}  →  {self.spec().volume_for(lv):g} µL",
                                    fg=self.p[lv.value.lower()])

    # ------------------------------------------------------------------
    # Calculation & output
    # ------------------------------------------------------------------
    def _certificate_info(self) -> CertificateInfo:
        cal = parse_date(self.v_date.get())
        nxt = parse_date(self.v_next.get())
        if nxt <= cal:
            raise ValueError("Next calibration must be after the calibration date.")
        if not self.v_doc.get().strip():
            raise ValueError("Document number is required.")
        return CertificateInfo(
            document_no=self.v_doc.get().strip(), calibration_date=cal, next_calibration_date=nxt,
            serial_no=self.v_serial.get().strip(), tip=self.v_tip.get().strip(),
            operator=self.operator(), balance_id=self.v_balance.get().strip(),
            place=self.cfg.place_of_calibration, comments=self.v_comments.get(),
            series=self.series(), procedure=self.cfg.procedure, logo_path=self._logo_path())

    def _calculate(self):
        try:
            if not self.v_serial.get().strip():
                raise ValueError("Please enter the pipette serial number (Setup tab).")
            env = self._environment()
            info = self._certificate_info()
            result = evaluate(self.spec(), env, self.weights, self.cfg.balance_readability_mg)
        except ValueError as exc:
            messagebox.showwarning("Cannot calculate", str(exc), parent=self)
            return
        self.result, self.pdf_path = result, None
        self._show_results(result)
        self._store_record(info, result)
        self._refresh_sidebar()
        self._refresh_output_buttons()
        self._show_tab("Results")

    def _store_record(self, info: CertificateInfo, result: CalibrationResult):
        payload = {
            "model": result.spec.model, "series": info.series, "serial_no": info.serial_no, "tip": info.tip,
            "document_no": info.document_no, "calibration_date": info.calibration_date.isoformat(),
            "next_calibration_date": info.next_calibration_date.isoformat(),
            "operator": info.operator, "balance_id": info.balance_id, "place": info.place,
            "comments": info.comments, "procedure": info.procedure,
            "balance_readability_mg": result.balance_readability_mg,
            "environment": {"temperature_c": result.environment.temperature_c,
                            "humidity_pct": result.environment.humidity_pct,
                            "pressure_hpa": result.environment.pressure_hpa,
                            "air_temperature_c": result.environment.air_t},
            "weights_g": {lv.value: list(result.level(lv).weights_g) for lv in LEVELS},
            "z": result.z, "verdict": result.verdict,
        }
        rec = CalibrationRecord(info.document_no, now_iso(), result.spec.model, info.serial_no,
                                info.tip, result.verdict, info.operator, payload)
        try:
            self.history.add(rec)
            self.current_record = rec
        except Exception as exc:  # noqa: BLE001 - duplicate document number etc.
            log.warning("history: %s", exc)
            messagebox.showwarning("History", f"The calibration was not stored in the history:\n{exc}\n\n"
                                              "Use a different document number and calculate again "
                                              "if you want it recorded.", parent=self)

    def _show_results(self, result: CalibrationResult):
        p = self.p
        ok = result.passed
        colour = p["green"] if ok else p["red"]
        self.verdict_label.config(text=f"CALIBRATION {result.verdict}", fg=colour)
        failed = [lv.level.value for lv in result.levels if not lv.passed]
        self.verdict_sub.config(text=(
            f"Gilson {full_model_name(result.spec, self.series())}  ·  S/N {self.v_serial.get().strip()}  ·  "
            f"Z = {result.z:.5f} µL/mg\n"
            + ("All test volumes are within the acceptance limits." if ok else
               f"Out of limits at: {', '.join(failed)}.")), fg=p["text"])
        for lv in result.levels:
            c = self.result_cards[lv.level]
            c["nominal"].config(text=f"nominal {lv.nominal_ul:g} µL")
            c["pill"].set(lv.level.value and ("PASS" if lv.passed else "FAIL"), p["green"] if lv.passed else p["red"])
            c["mean"].config(text=f"{lv.mean_ul:.3f} µL")
            c["sys"].config(text=f"{lv.systematic_error_ul:+.3f} µL  ({lv.systematic_error_pct:+.2f} %)\n"
                                 f"limit ± {lv.sys_limit_ul:g} µL",
                            fg=p["green"] if lv.systematic_pass else p["red"])
            c["rnd"].config(text=f"{lv.random_error_ul:.3f} µL\nlimit ≤ {lv.rnd_limit_ul:g} µL",
                            fg=p["green"] if lv.random_pass else p["red"])
            c["cv"].config(text=f"{lv.random_error_pct:.2f} %   (CV {lv.cv_pct:.2f} %)")
            c["unc"].config(text=f"± {lv.uncertainty_ul:.3f} µL")
            c["acc"].config(text=f"{lv.accuracy_pct:.2f} %")
            c["weights"].config(text="\n".join(f"{w:.6f} → {v:.3f}" for w, v in zip(lv.weights_g, lv.volumes_ul)))

    def _ensure_pdf(self) -> Path | None:
        """Return a PDF path for print/e-mail, generating a temporary one if needed."""
        if not self.result:
            messagebox.showinfo("Certificate", "Calculate the results first.", parent=self)
            return None
        if self.pdf_path and self.pdf_path.exists():
            return self.pdf_path
        try:
            info = self._certificate_info()
            tmp = Path(tempfile.gettempdir()) / default_filename(info, self.result.spec.model)
            build_certificate(tmp, info, self.result)
            return tmp
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Certificate", f"Could not create the PDF:\n{exc}", parent=self)
            return None

    def _save_pdf(self):
        if not self.result:
            messagebox.showinfo("Certificate", "Calculate the results first.", parent=self)
            return
        try:
            info = self._certificate_info()
        except ValueError as exc:
            messagebox.showwarning("Certificate", str(exc), parent=self)
            return
        initial_dir = self.cfg.pdf_folder or str(Path.home() / "Documents")
        target = filedialog.asksaveasfilename(
            parent=self, title="Save calibration certificate", defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")], initialdir=initial_dir,
            initialfile=default_filename(info, self.result.spec.model))
        if not target:
            return
        try:
            self.pdf_path = build_certificate(target, info, self.result)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Certificate", f"Could not create the PDF:\n{exc}", parent=self)
            return
        self.cfg.pdf_folder = str(Path(target).parent)
        self.cfg.save()
        if messagebox.askyesno("Certificate", f"Saved:\n{target}\n\nOpen it now?", parent=self):
            open_file(self.pdf_path)

    def _print(self):
        path = self._ensure_pdf()
        if path:
            try:
                print_file(path)
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("Print", str(exc), parent=self)

    def _email(self):
        path = self._ensure_pdf()
        if not path or not self.result:
            return
        info = self._certificate_info()
        subject = f"Pipette calibration certificate {info.document_no} - Gilson {self.result.spec.model} S/N {info.serial_no}"
        body = (f"Please find attached the calibration certificate {info.document_no}.\n\n"
                f"Pipette: Gilson {self.result.spec.model}, S/N {info.serial_no}\n"
                f"Result: {self.result.verdict}\n"
                f"Calibration date: {info.calibration_date:%d/%m/%Y}\n"
                f"Next calibration: {info.next_calibration_date:%d/%m/%Y}\n\n"
                "LifeGene Ltd., Mevo Horon, Israel\n+972-(0)8-6444314 | info@lifegene.co.il\n")
        try:
            msg = email_file(path, self.cfg.email_to, subject, body)
            messagebox.showinfo("Email", msg, parent=self)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Email", str(exc), parent=self)

    def _refresh_output_buttons(self):
        have = self.result is not None
        for b in (self.btn_pdf, self.btn_print, self.btn_email):
            b.set_enabled(have)

    def _new_calibration(self):
        if any(self.weights.values()) and not messagebox.askyesno(
                "New calibration", "Discard the current measurements and start a new calibration?", parent=self):
            return
        self.weights = {lv: [] for lv in LEVELS}
        self.result, self.pdf_path, self.current_record = None, None, None
        self._auto_armed, self._auto_run = True, []
        self._refresh_auto_labels()
        self.v_serial.set("")
        self.v_comments.set("")
        self.v_doc.set(self.history.next_document_number())
        today = date.today()
        self.v_date.set(today.strftime(DATE_FMT))
        self._next_date_auto = True
        self._on_date_change()
        self.verdict_label.config(text="No results yet", fg=self.p["muted"])
        self.verdict_sub.config(text="Complete 12 measurements or press Calculate.", fg=self.p["muted"])
        self._refresh_slots()
        self._refresh_sidebar()
        self._refresh_output_buttons()
        self._show_tab("Setup")

    def _refresh_sidebar(self):
        if not hasattr(self, "side_labels"):
            return
        p = self.p
        self.side_labels["Document"].config(text=self.v_doc.get() or "-")
        self.side_labels["Pipette"].config(text=f"Gilson {self.spec().model}")
        self.side_labels["Serial"].config(text=self.v_serial.get().strip() or "-")
        self.side_labels["Date"].config(text=self.v_date.get())
        if self.result:
            self.side_labels["Result"].config(text=self.result.verdict,
                                              fg=p["green"] if self.result.passed else p["red"])
        else:
            self.side_labels["Result"].config(text="pending", fg=p["muted"])

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------
    def _refresh_history(self):
        if not hasattr(self, "history_tree"):
            return
        self.history_tree.delete(*self.history_tree.get_children())
        for rec in self.history.list(search=self.v_search.get()):
            self.history_tree.insert("", "end", iid=str(rec.id), tags=(rec.verdict,), values=(
                rec.document_no, rec.calibrated_at, rec.model, rec.serial_no, rec.tip, rec.verdict, rec.operator))

    def _selected_record(self) -> CalibrationRecord | None:
        sel = self.history_tree.selection()
        if not sel:
            messagebox.showinfo("History", "Select a calibration first.", parent=self)
            return None
        return self.history.get(int(sel[0]))

    @staticmethod
    def _rebuild_from_record(rec: CalibrationRecord) -> tuple[CertificateInfo, CalibrationResult]:
        pl = rec.payload
        env = Environment(**pl["environment"])
        weights = {lv: list(pl["weights_g"][lv.value]) for lv in LEVELS}
        spec, series = resolve_catalogue_name(pl["model"])
        series = pl.get("series", series)
        result = evaluate(spec, env, weights, pl.get("balance_readability_mg", 0.001))
        info = CertificateInfo(
            document_no=pl["document_no"], calibration_date=date.fromisoformat(pl["calibration_date"]),
            next_calibration_date=date.fromisoformat(pl["next_calibration_date"]),
            serial_no=pl["serial_no"], tip=pl["tip"], operator=pl.get("operator", ""),
            balance_id=pl.get("balance_id", ""), place=pl.get("place", ""), comments=pl.get("comments", ""),
            series=series, procedure=pl.get("procedure", ""))
        return info, result

    def _history_pdf(self):
        rec = self._selected_record()
        if not rec:
            return
        try:
            info, result = self._rebuild_from_record(rec)
        except (KeyError, ValueError) as exc:
            messagebox.showerror("History", f"This record cannot be rebuilt: {exc}", parent=self)
            return
        info.logo_path = self._logo_path()
        target = filedialog.asksaveasfilename(
            parent=self, title="Re-create certificate", defaultextension=".pdf", filetypes=[("PDF", "*.pdf")],
            initialdir=self.cfg.pdf_folder or str(Path.home() / "Documents"),
            initialfile=default_filename(info, result.spec.model))
        if target:
            build_certificate(target, info, result)
            if messagebox.askyesno("History", f"Saved:\n{target}\n\nOpen it now?", parent=self):
                open_file(Path(target))

    def _history_load(self):
        rec = self._selected_record()
        if not rec:
            return
        try:
            info, result = self._rebuild_from_record(rec)
        except (KeyError, ValueError) as exc:
            messagebox.showerror("History", f"This record cannot be loaded: {exc}", parent=self)
            return
        self.v_model.set(full_model_name(result.spec, info.series))
        self.v_tip.set(info.tip)
        self.v_serial.set(info.serial_no)
        self.v_doc.set(info.document_no)
        self.v_date.set(info.calibration_date.strftime(DATE_FMT))
        self.v_next.set(info.next_calibration_date.strftime(DATE_FMT))
        self.v_comments.set(info.comments)
        self.v_temp.set(f"{result.environment.temperature_c:g}")
        self.v_air.set(f"{result.environment.air_t:g}")
        self.v_hum.set(f"{result.environment.humidity_pct:g}")
        self.v_press.set(f"{result.environment.pressure_hpa:g}")
        self.v_balance.set(info.balance_id)
        self.weights = {lv: list(result.level(lv).weights_g) for lv in LEVELS}
        self.result, self.pdf_path, self.current_record = result, None, rec
        self._show_results(result)
        self._refresh_slots()
        self._refresh_sidebar()
        self._refresh_output_buttons()
        self._show_tab("Results")

    # ------------------------------------------------------------------
    # Settings / theme / misc
    # ------------------------------------------------------------------
    def _open_settings(self):
        p = self.p
        win = tk.Toplevel(self, bg=p["surface"])
        win.title("Settings")
        win.transient(self)
        win.grab_set()
        win.resizable(False, False)
        body = tk.Frame(win, bg=p["surface"])
        body.pack(padx=20, pady=16)
        fields = (
            ("Calibrated by (operator)", "operator", str),
            ("Default e-mail recipient", "email_to", str),
            ("Place of calibration", "place_of_calibration", str),
            ("Standard / procedure (on certificate)", "procedure", str),
            ("Next calibration after (months)", "next_calibration_months", int),
            ("Balance readability (mg)", "balance_readability_mg", float),
            ("Balance poll interval (s)", "poll_interval_s", float),
            ("Connect to the balance at start-up (yes/no)", "auto_connect", _parse_bool),
            ("Default water temperature (°C)", "default_temperature_c", float),
            ("Default air temperature (°C)", "default_air_temperature_c", float),
            ("Default humidity (%)", "default_humidity_pct", float),
            ("Default pressure (hPa)", "default_pressure_hpa", float),
            ("PDF folder", "pdf_folder", str),
        )
        vars_: dict[str, tk.StringVar] = {}
        for i, (label, key, _) in enumerate(fields):
            tk.Label(body, text=label, bg=p["surface"], fg=p["muted"], font=self.f_small,
                     anchor="w").grid(row=i, column=0, sticky="w", pady=4, padx=(0, 14))
            value = getattr(self.cfg, key)
            v = tk.StringVar(value=("yes" if value else "no") if isinstance(value, bool) else str(value))
            vars_[key] = v
            self._entry(body, v, width=38).grid(row=i, column=1, sticky="ew", ipady=3)
        msg = tk.Label(body, text="", bg=p["surface"], fg=p["red"], font=self.f_small)
        msg.grid(row=len(fields), column=0, columnspan=2, sticky="w")

        def save():
            try:
                for _, key, typ in fields:
                    setattr(self.cfg, key, typ(vars_[key].get().strip()))
            except ValueError as exc:
                msg.config(text=f"Invalid value: {exc}")
                return
            self.cfg.save()
            win.destroy()
            self._build()
        btns = tk.Frame(body, bg=p["surface"])
        btns.grid(row=len(fields) + 1, column=0, columnspan=2, sticky="e", pady=(12, 0))
        Button(btns, self, "Cancel", win.destroy, "secondary").pack(side="left", padx=(0, 8))
        Button(btns, self, "Save", save, "primary").pack(side="left")

    def _toggle_theme(self):
        self.cfg.theme = "light" if self.cfg.theme == "dark" else "dark"
        self.cfg.save()
        self.p = PALETTES[self.cfg.theme]
        self._build()
        if self.result:
            self._show_results(self.result)
        if self.last_reading:
            self._show_reading(self.last_reading)

    @staticmethod
    def _resource_dirs() -> list[Path]:
        """Folders searched for assets: next to the EXE / script first, then the
        bundled package folder (PyInstaller unpacks it to sys._MEIPASS)."""
        dirs: list[Path] = []
        if getattr(sys, "frozen", False):
            dirs.append(Path(sys.executable).resolve().parent)
            dirs.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)))
        dirs.append(Path(__file__).resolve().parent.parent)
        dirs.append(Path.cwd())
        return dirs

    @classmethod
    def _asset(cls, *names: str) -> Path | None:
        for base in cls._resource_dirs():
            for name in names:
                for folder in (base / "assets", base):
                    candidate = folder / name
                    if candidate.exists():
                        return candidate
        return None

    @classmethod
    def _logo_path(cls) -> Path | None:
        return cls._asset("logo.png", "logo.jpg", "logo.jpeg")

    def _load_logo(self):
        path = self._logo_path()
        if not path:
            return None
        try:
            from PIL import Image, ImageTk
            img = Image.open(path).convert("RGBA")
            ratio = 40 / img.height
            img = img.resize((max(1, round(img.width * ratio)), 40), Image.LANCZOS)
            return ImageTk.PhotoImage(img)
        except Exception as exc:  # noqa: BLE001 - PIL missing or unreadable file
            log.warning("logo not loaded: %s", exc)
            return None

    def _on_close(self):
        if self.scale:
            self.scale.disconnect()
        self.history.close()
        self.destroy()


def main() -> None:
    """Entry point. Logs to the console when there is one, otherwise (windowed
    EXE) to app.log in the per-user application-data folder."""
    from .storage import app_data_dir
    handlers: list[logging.Handler] = []
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    try:
        handlers.append(logging.FileHandler(app_data_dir() / "app.log", encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        App().mainloop()
    except Exception:  # noqa: BLE001 - last-resort report for the windowed build
        log.exception("fatal error")
        try:
            messagebox.showerror(__app_name__, "The program stopped because of an unexpected error.\n"
                                 f"Details were written to {app_data_dir() / 'app.log'}")
        except tk.TclError:
            pass
        raise
