"""החלון הראשי: סיכום התראות, רשימת התראות וטבלת כל הרכבים."""
from __future__ import annotations

import csv
from datetime import date

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPushButton, QSplitter, QStatusBar, QTableWidget, QTableWidgetItem, QToolBar, QVBoxLayout, QWidget,
)

from . import APP_TITLE, __version__, calc
from .calc import fmt_date, fmt_km
from .db import Repo, format_plate
from .ui_dialogs import SettingsDialog, VehicleFormDialog
from .ui_vehicle import VehicleWindow
from .widgets import DateItem, NumItem, setup_table, status_colors, status_item

COLS = ["מס׳ רישוי", "רכב", "נהג", "ק״מ נוכחי", "ק״מ/חודש", "טיפול הבא", "נותרו לטיפול", "טסט", "ביטוח", "צפי שנתי", "מצב"]


class SummaryPill(QPushButton):
    def __init__(self, title: str, status: str, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        fg, _bg = status_colors(status)
        self.setObjectName("Pill")
        self._fg = fg
        self._title = title
        self.set_count(0)

    def set_count(self, n: int):
        self.setText(f"{n}\n{self._title}")
        self.setStyleSheet(
            f"QPushButton#Pill{{background:#fff;border:2px solid #e2e7ee;border-radius:10px;padding:8px 18px;font-size:13px;color:#1b2430;text-align:center}}"
            f"QPushButton#Pill:checked{{border-color:{self._fg};background:#f6f9ff}}"
            f"QPushButton#Pill:hover{{border-color:#b9c4d3}}")


class MainWindow(QMainWindow):
    def __init__(self, repo: Repo):
        super().__init__()
        self.repo = repo
        self.filter_level = None
        self.setWindowTitle(f"{APP_TITLE}  v{__version__}")
        self.resize(1280, 800)
        self._build()
        self.refresh()
        # רענון אוטומטי כל 10 דקות (לדוגמה כשהתוכנה פתוחה כל היום והתאריך מתחלף / קובץ משותף)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(10 * 60 * 1000)

    def _build(self):
        tb = QToolBar("ראשי")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(tb)

        act_new = QAction("➕ רכב חדש", self)
        act_new.setShortcut(QKeySequence.New)
        act_new.triggered.connect(self.new_vehicle)
        act_refresh = QAction("🔄 רענון", self)
        act_refresh.setShortcut(QKeySequence.Refresh)
        act_refresh.triggered.connect(self.refresh)
        act_export = QAction("📤 ייצוא לאקסל (CSV)", self)
        act_export.triggered.connect(self.export_csv)
        act_settings = QAction("⚙ הגדרות", self)
        act_settings.triggered.connect(self.open_settings)
        act_about = QAction("ℹ אודות", self)
        act_about.triggered.connect(self.about)
        for a in (act_new, act_refresh, act_export, act_settings):
            tb.addAction(a)
        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().horizontalPolicy().Expanding, spacer.sizePolicy().verticalPolicy())
        tb.addWidget(spacer)
        tb.addAction(act_about)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(10)

        # שורת סיכום
        pills = QHBoxLayout()
        self.pill_all = SummaryPill("רכבים פעילים", "neutral")
        self.pill_danger = SummaryPill("דחוף", "danger")
        self.pill_warn = SummaryPill("אזהרות", "warn")
        self.pill_ok = SummaryPill("תקינים", "ok")
        for p, lvl in ((self.pill_all, None), (self.pill_danger, "danger"), (self.pill_warn, "warn"), (self.pill_ok, "ok")):
            p.clicked.connect(lambda _c=False, l=lvl: self.set_filter(l))
            pills.addWidget(p)
        self.pill_all.setChecked(True)
        pills.addStretch(1)
        self.today_lbl = QLabel()
        self.today_lbl.setStyleSheet("color:#5f6b7a")
        pills.addWidget(self.today_lbl)
        root.addLayout(pills)

        split = QSplitter(Qt.Vertical)
        root.addWidget(split, 1)

        # התראות
        alerts_box = QFrame()
        al = QVBoxLayout(alerts_box)
        al.setContentsMargins(0, 0, 0, 0)
        hdr = QLabel("התראות")
        f = QFont(); f.setBold(True); f.setPointSize(11)
        hdr.setFont(f)
        al.addWidget(hdr)
        self.alerts = QListWidget()
        self.alerts.itemDoubleClicked.connect(lambda it: self.open_vehicle(it.data(Qt.UserRole)))
        self.alerts.setToolTip("לחיצה כפולה פותחת את הרכב")
        al.addWidget(self.alerts)
        split.addWidget(alerts_box)

        # טבלת רכבים
        table_box = QFrame()
        tl = QVBoxLayout(table_box)
        tl.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        hdr2 = QLabel("הרכבים בצי")
        hdr2.setFont(f)
        bar.addWidget(hdr2)
        self.search = QLineEdit()
        self.search.setPlaceholderText("חיפוש לפי מספר רישוי, דגם או נהג…")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(340)
        self.search.textChanged.connect(self.apply_filters)
        bar.addWidget(self.search)
        self.show_inactive = QCheckBox("הצג רכבים לא פעילים")
        self.show_inactive.toggled.connect(self.apply_filters)
        bar.addWidget(self.show_inactive)
        bar.addStretch(1)
        open_btn = QPushButton("פתיחת רכב")
        open_btn.clicked.connect(self.open_selected)
        bar.addWidget(open_btn)
        tl.addLayout(bar)
        self.table = QTableWidget()
        setup_table(self.table, COLS, stretch_col=1)
        self.table.doubleClicked.connect(lambda _i: self.open_selected())
        tl.addWidget(self.table)
        hint = QLabel("לחיצה כפולה על רכב פותחת את הכרטיס שלו להזנת קילומטראז׳, טיפולים ותיקונים.")
        hint.setStyleSheet("color:#5f6b7a;font-size:11px")
        tl.addWidget(hint)
        split.addWidget(table_box)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        split.setSizes([200, 520])

        self.setStatusBar(QStatusBar())

    # ---------- נתונים ----------
    def refresh(self):
        settings = self.repo.get_settings()
        hist = self.repo.history_all()
        self.rows = []
        for v in self.repo.list_vehicles(include_inactive=True):
            st = calc.compute_vehicle(v, hist["readings"].get(v["id"], []), hist["services"].get(v["id"], []), hist["repairs"].get(v["id"], []), settings)
            self.rows.append((v, st))
        active = [(v, st) for v, st in self.rows if v["active"]]
        self.pill_all.set_count(len(active))
        self.pill_danger.set_count(sum(1 for _v, st in active if st.worst_level == "danger"))
        self.pill_warn.set_count(sum(1 for _v, st in active if st.worst_level == "warn"))
        self.pill_ok.set_count(sum(1 for _v, st in active if st.worst_level in ("ok", "info")))
        self.today_lbl.setText(f"נכון ל-{fmt_date(date.today())}")

        self.alerts.clear()
        order = {"danger": 0, "warn": 1, "info": 2}
        items = []
        for v, st in active:
            for a in st.alerts:
                items.append((order[a.level], v, a))
        items.sort(key=lambda x: (x[0], x[1]["plate"]))
        for _o, v, a in items:
            name = " ".join(x for x in (v.get("make"), v.get("model")) if x)
            who = f"{format_plate(v['plate'])}  {name}" + (f"  ({v['driver']})" if v.get("driver") else "")
            icon = "⛔" if a.level == "danger" else "⚠" if a.level == "warn" else "ℹ"
            it = QListWidgetItem(f"{icon}  {who}   —   {a.text}")
            it.setData(Qt.UserRole, v["id"])
            fg, bg = status_colors(a.level)
            it.setBackground(QColor(bg))
            it.setForeground(QColor("#1b2430"))
            self.alerts.addItem(it)
        if not items:
            it = QListWidgetItem("✅ אין התראות פעילות")
            self.alerts.addItem(it)

        self.apply_filters()
        self.statusBar().showMessage(f"{len(self.rows)} רכבים במערכת  |  קובץ נתונים: {self.repo.path}")

    def set_filter(self, level):
        self.filter_level = level
        for p, lvl in ((self.pill_all, None), (self.pill_danger, "danger"), (self.pill_warn, "warn"), (self.pill_ok, "ok")):
            p.setChecked(lvl == level)
        self.apply_filters()

    def apply_filters(self):
        q = self.search.text().strip().lower().replace("-", "")
        show_inactive = self.show_inactive.isChecked()
        rows = []
        for v, st in self.rows:
            if not v["active"] and not show_inactive:
                continue
            if self.filter_level == "ok" and st.worst_level not in ("ok", "info"):
                continue
            if self.filter_level in ("danger", "warn") and st.worst_level != self.filter_level:
                continue
            hay = " ".join(str(x or "") for x in (v["plate"], v.get("make"), v.get("model"), v.get("driver"), v.get("year"))).lower()
            if q and q not in hay:
                continue
            rows.append((v, st))
        self._fill_table(rows)

    def _fill_table(self, rows):
        t = self.table
        t.setSortingEnabled(False)
        t.setRowCount(len(rows))
        for i, (v, st) in enumerate(rows):
            plate = QTableWidgetItem(format_plate(v["plate"]))
            plate.setData(Qt.UserRole, v["id"])
            plate.setTextAlignment(Qt.AlignCenter)
            pf = QFont("Consolas"); pf.setBold(True)
            plate.setFont(pf)
            t.setItem(i, 0, plate)
            name = " ".join(str(x) for x in (v.get("make"), v.get("model"), v.get("year")) if x)
            if not v["active"]:
                name += "  (לא פעיל)"
            t.setItem(i, 1, QTableWidgetItem(name))
            t.setItem(i, 2, QTableWidgetItem(v.get("driver") or ""))
            t.setItem(i, 3, NumItem(st.current_km))
            t.setItem(i, 4, NumItem(st.avg_monthly_km))
            s = st.service
            if s.status == "unknown":
                t.setItem(i, 5, status_item("unknown", "לא הוזן טיפול"))
                t.setItem(i, 6, NumItem(None, ""))
            else:
                txt = fmt_date(s.expected_date) + ("  (ק״מ)" if s.reason == "km" else "  (שנה)")
                it = status_item(s.status, txt)
                it.setData(Qt.UserRole, s.expected_date.toordinal())
                t.setItem(i, 5, it)
                t.setItem(i, 6, NumItem(s.km_remaining, "" if s.km_remaining is None else (f"{fmt_km(s.km_remaining)}" if s.km_remaining > 0 else f"חריגה {fmt_km(-s.km_remaining)}")))
            for col, ex in ((7, st.test), (8, st.insurance)):
                if ex.status == "unknown":
                    t.setItem(i, col, status_item("unknown", "לא הוזן"))
                else:
                    it = status_item(ex.status, fmt_date(ex.date))
                    it.setData(Qt.UserRole, ex.date.toordinal())
                    t.setItem(i, col, it)
            m = st.mileage
            if m.status == "unknown":
                t.setItem(i, 9, status_item("unknown", "—"))
            else:
                it = status_item(m.status, f"{fmt_km(m.projected_year_km)} ק״מ")
                it.setData(Qt.UserRole, m.projected_year_km)
                t.setItem(i, 9, it)
            lvl = st.worst_level
            t.setItem(i, 10, status_item(lvl, {"danger": "דחוף", "warn": "אזהרה", "info": "חסר מידע", "ok": "תקין"}[lvl]))
            if not v["active"]:
                for c in range(t.columnCount()):
                    t.item(i, c).setForeground(QColor("#9aa5b1"))
        t.setSortingEnabled(True)
        t.resizeColumnsToContents()
        t.horizontalHeader().setStretchLastSection(False)

    # ---------- פעולות ----------
    def _selected_vehicle_id(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.table.item(rows[0].row(), 0).data(Qt.UserRole)

    def open_selected(self):
        vid = self._selected_vehicle_id()
        if vid is None:
            QMessageBox.information(self, "בחירה", "יש לבחור רכב מהטבלה")
            return
        self.open_vehicle(vid)

    def open_vehicle(self, vid):
        if vid is None:
            return
        w = VehicleWindow(self.repo, vid, self)
        w.exec()
        self.refresh()

    def new_vehicle(self):
        d = VehicleFormDialog(self.repo, self)
        if d.exec():
            self.refresh()
            if d.result_id:
                self.open_vehicle(d.result_id)

    def open_settings(self):
        if SettingsDialog(self.repo, self).exec():
            self.refresh()

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "ייצוא רשימת הרכבים", f"צי רכב {date.today().isoformat()}.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh)
                w.writerow(["מספר רישוי", "יצרן", "דגם", "שנה", "נהג", "פעיל", "ק״מ נוכחי", "ק״מ/חודש", "טיפול אחרון", "ק״מ בטיפול האחרון",
                            "טיפול הבא (צפי)", "סיבה", "נותרו לטיפול (ק״מ)", "תוקף טסט", "ימים לטסט", "תוקף ביטוח", "ימים לביטוח",
                            "צפי נסועה שנתית", "מכסה", "מצב", "התראות"])
                for v, st in self.rows:
                    s, m = st.service, st.mileage
                    w.writerow([
                        format_plate(v["plate"]), v.get("make") or "", v.get("model") or "", v.get("year") or "", v.get("driver") or "",
                        "כן" if v["active"] else "לא", st.current_km or "", st.avg_monthly_km or "",
                        fmt_date(s.last_service_date) if s.last_service_date else "", s.last_service_km or "",
                        fmt_date(s.expected_date) if s.expected_date else "", {"km": "קילומטראז׳", "date": "זמן"}.get(s.reason, ""),
                        s.km_remaining if s.km_remaining is not None else "",
                        fmt_date(st.test.date) if st.test.date else "", st.test.days_left if st.test.days_left is not None else "",
                        fmt_date(st.insurance.date) if st.insurance.date else "", st.insurance.days_left if st.insurance.days_left is not None else "",
                        m.projected_year_km or "", m.limit, st.worst_level, " | ".join(a.text for a in st.alerts),
                    ])
        except OSError as e:
            QMessageBox.critical(self, "שגיאה", f"הייצוא נכשל: {e}")
            return
        QMessageBox.information(self, "ייצוא", f"הקובץ נשמר:\n{path}")

    def about(self):
        QMessageBox.about(self, "אודות", f"<b>{APP_TITLE}</b> גרסה {__version__}<br><br>"
                          "מעקב טסט, ביטוח, טיפולים, תיקונים וקילומטראז׳ לצי הרכב.<br>"
                          "טיפול כל 15,000 ק״מ או שנה (המוקדם מביניהם), התראה על חריגה מ-35,000 ק״מ בשנה - ניתן לשינוי בהגדרות.<br><br>"
                          f"קובץ הנתונים: <code>{self.repo.path}</code>")
