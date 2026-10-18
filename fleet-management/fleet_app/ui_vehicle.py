"""חלון רכב בודד: פרטים, כרטיסי מצב, היסטוריית קילומטראז׳/טיפולים/תיקונים."""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QTabWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QPlainTextEdit,
)

from . import calc
from .calc import fmt_date, fmt_km
from .db import Repo, format_plate
from .ui_dialogs import ReadingDialog, RepairDialog, ServiceDialog, VehicleFormDialog
from .widgets import DateItem, NumItem, StatCard, confirm, setup_table, show_error, status_colors

REASON_TEXT = {"km": "לפי קילומטראז׳", "date": "לפי זמן (שנה מהטיפול)"}


class VehicleWindow(QDialog):
    def __init__(self, repo: Repo, vehicle_id: int, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.vid = vehicle_id
        self.changed = False
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        self.resize(1050, 720)
        self._build()
        self.refresh()

    # ---------- בנייה ----------
    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        head = QFrame()
        head.setObjectName("Header")
        hl = QHBoxLayout(head)
        self.plate_lbl = QLabel()
        self.plate_lbl.setObjectName("Plate")
        self.title_lbl = QLabel()
        f = QFont(); f.setPointSize(14); f.setBold(True)
        self.title_lbl.setFont(f)
        self.sub_lbl = QLabel()
        self.sub_lbl.setStyleSheet("color:#5f6b7a")
        tbox = QVBoxLayout()
        tbox.setSpacing(0)
        tbox.addWidget(self.title_lbl)
        tbox.addWidget(self.sub_lbl)
        hl.addWidget(self.plate_lbl)
        hl.addSpacing(8)
        hl.addLayout(tbox)
        hl.addStretch(1)
        self.edit_btn = QPushButton("✏ עריכת פרטים")
        self.edit_btn.clicked.connect(self.edit_vehicle)
        self.delete_btn = QPushButton("🗑 מחיקת רכב")
        self.delete_btn.setObjectName("danger")
        self.delete_btn.clicked.connect(self.delete_vehicle)
        hl.addWidget(self.edit_btn)
        hl.addWidget(self.delete_btn)
        root.addWidget(head)

        self.alerts = QListWidget()
        self.alerts.setObjectName("Alerts")
        self.alerts.setFixedHeight(0)
        self.alerts.setFocusPolicy(Qt.NoFocus)
        self.alerts.setSelectionMode(QListWidget.NoSelection)
        root.addWidget(self.alerts)

        cards = QGridLayout()
        cards.setSpacing(10)
        self.card_service = StatCard("טיפול הבא")
        self.card_mileage = StatCard("צפי נסועה שנתית")
        self.card_avg = StatCard("ממוצע נסועה")
        self.card_test = StatCard("טסט")
        self.card_insurance = StatCard("ביטוח")
        cards.addWidget(self.card_service, 0, 0)
        cards.addWidget(self.card_mileage, 0, 1)
        cards.addWidget(self.card_avg, 0, 2)
        cards.addWidget(self.card_test, 0, 3)
        cards.addWidget(self.card_insurance, 0, 4)
        root.addLayout(cards)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        # --- קילומטראז׳ ---
        self.readings_tab, self.readings_table = self._history_tab(
            ["תאריך", "קילומטראז׳", "הערה"], add_text="➕ הזנת קילומטראז׳",
            on_add=self.add_reading, on_delete=self.delete_reading)
        self.tabs.addTab(self.readings_tab, "קילומטראז׳")

        # --- טיפולים ---
        self.services_tab, self.services_table = self._history_tab(
            ["תאריך", "קילומטראז׳", "מוסך", "מה נעשה", "עלות (₪)"], add_text="➕ הזנת טיפול",
            on_add=self.add_service, on_delete=self.delete_service, on_edit=self.edit_service, stretch_col=3)
        self.tabs.addTab(self.services_tab, "טיפולים")

        # --- תיקונים ---
        self.repairs_tab, self.repairs_table = self._history_tab(
            ["תאריך", "קילומטראז׳", "מוסך", "תיאור התיקון", "עלות (₪)"], add_text="➕ הזנת תיקון",
            on_add=self.add_repair, on_delete=self.delete_repair, on_edit=self.edit_repair, stretch_col=3)
        self.tabs.addTab(self.repairs_tab, "תיקונים")

        # --- הערות ---
        notes_w = QWidget()
        nl = QVBoxLayout(notes_w)
        self.notes_view = QPlainTextEdit()
        self.notes_view.setReadOnly(True)
        nl.addWidget(self.notes_view)
        self.tabs.addTab(notes_w, "הערות")

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        close = QPushButton("סגירה")
        close.clicked.connect(self.accept)
        bottom.addWidget(close)
        root.addLayout(bottom)

    def _history_tab(self, headers, add_text, on_add, on_delete, on_edit=None, stretch_col=None):
        w = QWidget()
        lay = QVBoxLayout(w)
        bar = QHBoxLayout()
        add = QPushButton(add_text)
        add.clicked.connect(on_add)
        bar.addWidget(add)
        if on_edit:
            edit = QPushButton("✏ עריכה")
            edit.setObjectName("secondary")
            edit.clicked.connect(on_edit)
            bar.addWidget(edit)
        delete = QPushButton("🗑 מחיקה")
        delete.setObjectName("danger")
        delete.clicked.connect(on_delete)
        bar.addWidget(delete)
        bar.addStretch(1)
        total = QLabel("")
        total.setStyleSheet("color:#5f6b7a")
        bar.addWidget(total)
        lay.addLayout(bar)
        table = QTableWidget()
        setup_table(table, headers, stretch_col)
        table.total_label = total
        if on_edit:
            table.doubleClicked.connect(lambda _i: on_edit())
        lay.addWidget(table)
        return w, table

    # ---------- רענון ----------
    def refresh(self):
        self.vehicle = v = self.repo.get_vehicle(self.vid)
        readings, services, repairs = self.repo.readings(self.vid), self.repo.services(self.vid), self.repo.repairs(self.vid)
        settings = self.repo.get_settings()
        st = self.status = calc.compute_vehicle(v, readings, services, repairs, settings)

        self.setWindowTitle(f"רכב {format_plate(v['plate'])} - {' '.join(x for x in (v.get('make'), v.get('model')) if x)}")
        self.plate_lbl.setText(format_plate(v["plate"]))
        title = " ".join(str(x) for x in (v.get("make"), v.get("model"), v.get("year")) if x) or "רכב"
        if not v.get("active"):
            title += "  (לא פעיל)"
        self.title_lbl.setText(title)
        parts = []
        if v.get("driver"):
            parts.append(f"נהג: {v['driver']}")
        parts.append(f"ק״מ נוכחי (משוער): {fmt_km(st.current_km)}")
        if st.last_point:
            parts.append(f"קריאה אחרונה: {fmt_km(st.last_point.km)} ב-{fmt_date(st.last_point.date)}")
        self.sub_lbl.setText("   |   ".join(parts))
        self.notes_view.setPlainText(v.get("notes") or "")

        # התראות
        self.alerts.clear()
        for a in st.alerts:
            it = QListWidgetItem(("⛔ " if a.level == "danger" else "⚠ " if a.level == "warn" else "ℹ ") + a.text)
            _fg, bg = status_colors(a.level)
            it.setForeground(QColor("#1b2430"))
            it.setBackground(QColor(bg))
            self.alerts.addItem(it)
        self.alerts.setFixedHeight(min(4, len(st.alerts)) * 26 + 6 if st.alerts else 0)

        # כרטיסים
        s = st.service
        c = self.card_service
        if s.status == "unknown":
            c.value.setText("לא ידוע")
            c.sub.setText("יש להזין טיפול אחרון כדי לחשב")
            c.set_progress(None)
        else:
            c.value.setText(fmt_date(s.expected_date))
            lines = [f"{REASON_TEXT.get(s.reason, '')}"]
            if s.km_remaining is not None:
                lines.append(f"נותרו {fmt_km(s.km_remaining)} ק״מ (יעד {fmt_km(s.due_km)})" if s.km_remaining > 0 else f"חריגה של {fmt_km(-s.km_remaining)} ק״מ מעל היעד {fmt_km(s.due_km)}")
            lines.append(f"לכל המאוחר {fmt_date(s.due_date)}\nטיפול אחרון {fmt_date(s.last_service_date)}" + (f" ב-{fmt_km(s.last_service_km)} ק״מ" if s.last_service_km is not None else ""))
            c.sub.setText("\n".join(lines))
            if s.km_remaining is not None and settings.service_interval_km:
                c.set_progress((settings.service_interval_km - s.km_remaining) / settings.service_interval_km)
            else:
                c.set_progress(None)
        c.set_status(s.status)

        m = st.mileage
        c = self.card_mileage
        if m.status == "unknown":
            c.value.setText("לא ידוע")
            c.sub.setText("יש להזין לפחות שתי קריאות קילומטראז׳")
            c.set_progress(None)
        else:
            c.value.setText(f"{fmt_km(m.projected_year_km)} ק״מ")
            txt = f"מכסה {fmt_km(m.limit)} | נסעו עד כה {fmt_km(m.driven_so_far)}\nשנת נסועה {fmt_date(m.year_start)} עד {fmt_date(m.year_end - timedelta(days=1))}"
            if m.partial_year:
                txt += f"\nמעקב החל מ-{fmt_date(m.tracked_from)}; קצב שנתי {fmt_km(m.annualized_km)}"
            elif m.annualized_km is not None:
                txt += f"\nקצב שנתי לפי הממוצע {fmt_km(m.annualized_km)} ק״מ"
            c.sub.setText(txt)
            c.set_progress(m.projected_year_km / m.limit if m.limit else None)
        c.set_status(m.status)

        c = self.card_avg
        if st.avg_daily_km is None:
            c.value.setText("—")
            c.sub.setText("נדרשות לפחות שתי קריאות בתאריכים שונים")
            c.set_status("unknown", "")
        else:
            c.value.setText(f"{fmt_km(st.avg_monthly_km)} ק״מ/חודש")
            c.sub.setText(f"{st.avg_daily_km:g} ק״מ ליום בממוצע (לפי השנה האחרונה)\nמבוסס על {len(st.timeline)} נקודות מדידה")
            c.set_status("neutral", "")

        for card, ex, name in ((self.card_test, st.test, "הטסט"), (self.card_insurance, st.insurance, "הביטוח")):
            if ex.status == "unknown":
                card.value.setText("לא הוזן")
                card.sub.setText("")
            else:
                card.value.setText(fmt_date(ex.date))
                card.sub.setText(f"{name} פג לפני {-ex.days_left} ימים" if ex.days_left < 0 else f"נותרו {ex.days_left} ימים")
            card.set_status(ex.status)

        # טבלאות
        self._fill_readings(readings)
        self._fill_services(services)
        self._fill_repairs(repairs)

    def _fill_readings(self, rows):
        t = self.readings_table
        t.setSortingEnabled(False)
        t.setRowCount(len(rows))
        for i, r in enumerate(rows):
            t.setItem(i, 0, DateItem(r["reading_date"]))
            t.setItem(i, 1, NumItem(r["km"]))
            t.setItem(i, 2, QTableWidgetItem(r.get("note") or ""))
            t.item(i, 0).setData(Qt.UserRole + 1, r["id"])
        t.setSortingEnabled(True)
        t.total_label.setText(f"{len(rows)} קריאות")

    def _fill_services(self, rows):
        t = self.services_table
        t.setSortingEnabled(False)
        t.setRowCount(len(rows))
        total = 0.0
        for i, r in enumerate(rows):
            t.setItem(i, 0, DateItem(r["service_date"]))
            t.setItem(i, 1, NumItem(r.get("odometer_km")))
            t.setItem(i, 2, QTableWidgetItem(r.get("garage") or ""))
            t.setItem(i, 3, QTableWidgetItem(r.get("description") or ""))
            t.setItem(i, 4, NumItem(r.get("cost"), "" if r.get("cost") is None else f"{r['cost']:,.0f}"))
            t.item(i, 0).setData(Qt.UserRole + 1, r["id"])
            total += r.get("cost") or 0
        t.setSortingEnabled(True)
        t.resizeRowsToContents()
        t.total_label.setText(f"{len(rows)} טיפולים | סה״כ עלות: {total:,.0f} ₪")

    def _fill_repairs(self, rows):
        t = self.repairs_table
        t.setSortingEnabled(False)
        t.setRowCount(len(rows))
        total = 0.0
        for i, r in enumerate(rows):
            t.setItem(i, 0, DateItem(r["repair_date"]))
            t.setItem(i, 1, NumItem(r.get("odometer_km")))
            t.setItem(i, 2, QTableWidgetItem(r.get("garage") or ""))
            t.setItem(i, 3, QTableWidgetItem(r.get("description") or ""))
            t.setItem(i, 4, NumItem(r.get("cost"), "" if r.get("cost") is None else f"{r['cost']:,.0f}"))
            t.item(i, 0).setData(Qt.UserRole + 1, r["id"])
            total += r.get("cost") or 0
        t.setSortingEnabled(True)
        t.resizeRowsToContents()
        t.total_label.setText(f"{len(rows)} תיקונים | סה״כ עלות: {total:,.0f} ₪")

    @staticmethod
    def _selected_id(table: QTableWidget) -> Optional[int]:
        rows = table.selectionModel().selectedRows()
        if not rows:
            return None
        return table.item(rows[0].row(), 0).data(Qt.UserRole + 1)

    def _mark(self):
        self.changed = True
        self.refresh()

    # ---------- פעולות ----------
    def edit_vehicle(self):
        if VehicleFormDialog(self.repo, self, vehicle=self.vehicle).exec():
            self._mark()

    def delete_vehicle(self):
        if confirm(self, f"למחוק את הרכב {format_plate(self.vehicle['plate'])} וכל ההיסטוריה שלו?\nפעולה זו אינה הפיכה.\n\nטיפ: אפשר במקום זאת לסמן את הרכב כלא פעיל דרך 'עריכת פרטים'.", "מחיקת רכב"):
            self.repo.delete_vehicle(self.vid)
            self.changed = True
            self.accept()

    def add_reading(self):
        last = self.status.last_point.km if self.status.last_point else None
        if ReadingDialog(self.repo, self.vid, self, last_km=last).exec():
            self._mark()

    def delete_reading(self):
        rid = self._selected_id(self.readings_table)
        if rid is None:
            return show_error(self, "יש לבחור שורה למחיקה", "בחירה")
        if confirm(self, "למחוק את קריאת הקילומטראז׳ שנבחרה?"):
            self.repo.delete_reading(rid)
            self._mark()

    def add_service(self):
        if ServiceDialog(self.repo, self.vid, self, suggested_km=self.status.current_km).exec():
            self._mark()

    def edit_service(self):
        sid = self._selected_id(self.services_table)
        if sid is None:
            return show_error(self, "יש לבחור טיפול לעריכה", "בחירה")
        svc = next(s for s in self.repo.services(self.vid) if s["id"] == sid)
        if ServiceDialog(self.repo, self.vid, self, service=svc).exec():
            self._mark()

    def delete_service(self):
        sid = self._selected_id(self.services_table)
        if sid is None:
            return show_error(self, "יש לבחור טיפול למחיקה", "בחירה")
        if confirm(self, "למחוק את הטיפול שנבחר?"):
            self.repo.delete_service(sid)
            self._mark()

    def add_repair(self):
        if RepairDialog(self.repo, self.vid, self, suggested_km=self.status.current_km).exec():
            self._mark()

    def edit_repair(self):
        rid = self._selected_id(self.repairs_table)
        if rid is None:
            return show_error(self, "יש לבחור תיקון לעריכה", "בחירה")
        rep = next(r for r in self.repo.repairs(self.vid) if r["id"] == rid)
        if RepairDialog(self.repo, self.vid, self, repair=rep).exec():
            self._mark()

    def delete_repair(self):
        rid = self._selected_id(self.repairs_table)
        if rid is None:
            return show_error(self, "יש לבחור תיקון למחיקה", "בחירה")
        if confirm(self, "למחוק את התיקון שנבחר?"):
            self.repo.delete_repair(rid)
            self._mark()
