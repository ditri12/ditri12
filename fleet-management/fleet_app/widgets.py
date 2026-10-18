"""רכיבי ממשק משותפים."""
from __future__ import annotations

from datetime import date
from typing import Optional

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QAbstractItemView, QHeaderView,
)

from .calc import fmt_date, fmt_km, to_date

# צבעי סטטוס: (טקסט, רקע)
COLORS = {
    "ok": ("#1a7f37", "#e6f4ea"),
    "soon": ("#9a6700", "#fff4d6"),
    "warn": ("#9a6700", "#fff4d6"),
    "pace": ("#9a6700", "#fff4d6"),
    "overdue": ("#c0392b", "#fdecea"),
    "expired": ("#c0392b", "#fdecea"),
    "over": ("#c0392b", "#fdecea"),
    "danger": ("#c0392b", "#fdecea"),
    "unknown": ("#4a5a6a", "#eef1f5"),
    "info": ("#4a5a6a", "#eef1f5"),
    "neutral": ("#4a5a6a", "#eef1f5"),
}

STATUS_TEXT = {
    "ok": "תקין", "soon": "בקרוב", "overdue": "באיחור", "expired": "פג תוקף",
    "over": "חריגה", "pace": "קצב גבוה", "unknown": "לא הוזן", "danger": "דחוף", "warn": "אזהרה", "info": "מידע",
}


def status_colors(status: str):
    return COLORS.get(status, COLORS["neutral"])


def badge_html(status: str, text: Optional[str] = None) -> str:
    fg, bg = status_colors(status)
    t = text or STATUS_TEXT.get(status, status)
    return (f'<span style="background:{bg};color:{fg};border-radius:9px;padding:1px 8px;'
            f'font-weight:600;font-size:12px">{t}</span>')


class Badge(QLabel):
    def __init__(self, status="neutral", text=None, parent=None):
        super().__init__(parent)
        self.set_status(status, text)

    def set_status(self, status, text=None):
        fg, bg = status_colors(status)
        self.setText(text or STATUS_TEXT.get(status, status))
        self.setStyleSheet(f"QLabel{{background:{bg};color:{fg};border-radius:9px;padding:2px 10px;font-weight:600;font-size:12px}}")
        self.setAlignment(Qt.AlignCenter)


class StatCard(QFrame):
    """כרטיס מצב: כותרת, ערך גדול, שורת פירוט, סרגל התקדמות אופציונלי."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("StatCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)
        top = QHBoxLayout()
        self.title = QLabel(title)
        self.title.setObjectName("cardTitle")
        self.badge = Badge("neutral", "")
        self.badge.hide()
        top.addWidget(self.title)
        top.addStretch(1)
        top.addWidget(self.badge)
        lay.addLayout(top)
        self.value = QLabel("—")
        self.value.setObjectName("cardValue")
        f = QFont()
        f.setPointSize(16)
        f.setBold(True)
        self.value.setFont(f)
        lay.addWidget(self.value)
        self.sub = QLabel("")
        self.sub.setObjectName("cardSub")
        self.sub.setWordWrap(True)
        lay.addWidget(self.sub)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.bar.hide()
        lay.addWidget(self.bar)
        self.set_status("neutral")

    def set_status(self, status: str, badge_text: Optional[str] = None):
        fg, bg = status_colors(status)
        self.setStyleSheet(
            f"QFrame#StatCard{{background:#ffffff;border:1px solid #e2e7ee;border-right:5px solid {fg};border-radius:10px}}"
            f"QLabel#cardTitle{{color:#5f6b7a;font-size:12px}} QLabel#cardSub{{color:#5f6b7a;font-size:12px}}"
            f"QProgressBar{{background:#e6eaf0;border:0;border-radius:4px}} QProgressBar::chunk{{background:{fg};border-radius:4px}}")
        if badge_text is None and status in STATUS_TEXT and status != "neutral":
            badge_text = STATUS_TEXT[status]
        if badge_text:
            self.badge.set_status(status, badge_text)
            self.badge.show()
        else:
            self.badge.hide()

    def set_progress(self, fraction: Optional[float]):
        if fraction is None:
            self.bar.hide()
            return
        self.bar.setRange(0, 1000)
        self.bar.setValue(int(max(0.0, min(1.0, fraction)) * 1000))
        self.bar.show()


class OptionalDateEdit(QWidget):
    """שדה תאריך שאפשר להשאיר ריק (תיבת סימון + בורר תאריך עם לוח שנה)."""
    changed = Signal()

    def __init__(self, parent=None, default: Optional[date] = None, required=False):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.check = QCheckBox()
        self.edit = QDateEdit()
        # חשוב: כיוון התצוגה נקבע לפני פורמט התאריך - אחרת Qt הופך את סדר החלקים (שנה/חודש/יום) בסביבת RTL
        self.edit.setLayoutDirection(Qt.LeftToRight)
        self.edit.setCalendarPopup(True)
        self.edit.setDisplayFormat("dd/MM/yyyy")
        self.edit.setDate(QDate.currentDate())
        self.edit.setMinimumWidth(130)
        lay.addWidget(self.check)
        lay.addWidget(self.edit, 1)
        self.required = required
        if required:
            self.check.setChecked(True)
            self.check.hide()
        self.check.toggled.connect(self._toggled)
        self.edit.dateChanged.connect(lambda _d: self.changed.emit())
        self._toggled(self.check.isChecked())
        if default is not None:
            self.set_value(default)

    def _toggled(self, on):
        self.edit.setEnabled(on)
        self.changed.emit()

    def value(self) -> Optional[str]:
        if not self.check.isChecked():
            return None
        return self.edit.date().toPython().isoformat()

    def set_value(self, v):
        d = to_date(v)
        if d is None:
            if not self.required:
                self.check.setChecked(False)
            return
        self.check.setChecked(True)
        self.edit.setDate(QDate(d.year, d.month, d.day))


class KmEdit(QLineEdit):
    """שדה מספרי לקילומטראז׳/סכומים: מקבל ספרות ופסיקים בלבד."""

    def __init__(self, parent=None, decimals=False):
        super().__init__(parent)
        self.setPlaceholderText("0")
        self.setAlignment(Qt.AlignLeft)
        self.setLayoutDirection(Qt.LeftToRight)
        self.decimals = decimals
        self.textEdited.connect(self._clean)

    def _clean(self, s):
        allowed = "0123456789," + (".") if self.decimals else "0123456789,"
        cleaned = "".join(ch for ch in s if ch in allowed)
        if cleaned != s:
            self.setText(cleaned)

    def value(self) -> Optional[str]:
        t = self.text().replace(",", "").strip()
        return t or None

    def set_value(self, v):
        if v is None or v == "":
            self.setText("")
        elif self.decimals:
            self.setText(f"{float(v):g}")
        else:
            self.setText(f"{int(v):,}")


class GarageCombo(QComboBox):
    """בחירת מוסך מרשימת המוסכים שכבר הוזנו, עם אפשרות להקליד מוסך חדש."""

    def __init__(self, garages: list[str], parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.addItem("")
        self.addItems(garages)
        self.setCurrentIndex(0)
        self.lineEdit().setPlaceholderText("שם המוסך")

    def value(self) -> Optional[str]:
        t = self.currentText().strip()
        return t or None

    def set_value(self, v):
        self.setCurrentText(v or "")


class NumItem(QTableWidgetItem):
    """תא טבלה מספרי שממוין לפי הערך ולא לפי הטקסט."""

    def __init__(self, value, text: Optional[str] = None):
        super().__init__(text if text is not None else fmt_km(value))
        self.setData(Qt.UserRole, -1e18 if value is None else float(value))
        self.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def __lt__(self, other):
        return self.data(Qt.UserRole) < other.data(Qt.UserRole)


class DateItem(QTableWidgetItem):
    def __init__(self, value):
        d = to_date(value)
        super().__init__(fmt_date(d))
        self.setData(Qt.UserRole, d.toordinal() if d else 0)
        self.setTextAlignment(Qt.AlignCenter)

    def __lt__(self, other):
        return self.data(Qt.UserRole) < other.data(Qt.UserRole)


def status_item(status: str, text: Optional[str] = None) -> QTableWidgetItem:
    fg, bg = status_colors(status)
    it = QTableWidgetItem(text or STATUS_TEXT.get(status, status))
    it.setForeground(QColor(fg))
    it.setBackground(QColor(bg))
    it.setTextAlignment(Qt.AlignCenter)
    order = {"danger": 0, "overdue": 0, "expired": 0, "over": 0, "warn": 1, "soon": 1, "pace": 1, "unknown": 2, "info": 2, "ok": 3}
    it.setData(Qt.UserRole, order.get(status, 9))
    return it


def setup_table(table: QTableWidget, headers: list[str], stretch_col: Optional[int] = None):
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.setSortingEnabled(True)
    table.setWordWrap(True)
    hh = table.horizontalHeader()
    hh.setSectionResizeMode(QHeaderView.ResizeToContents)
    hh.setStretchLastSection(stretch_col is None)
    if stretch_col is not None:
        hh.setSectionResizeMode(stretch_col, QHeaderView.Stretch)
    hh.setHighlightSections(False)


def show_error(parent, text: str, title="שגיאה"):
    QMessageBox.critical(parent, title, text)


def confirm(parent, text: str, title="אישור") -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Question)
    box.setWindowTitle(title)
    box.setText(text)
    yes = box.addButton("כן", QMessageBox.YesRole)
    box.addButton("ביטול", QMessageBox.RejectRole)
    box.exec()
    return box.clickedButton() is yes
