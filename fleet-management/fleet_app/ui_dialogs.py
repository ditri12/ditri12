"""טפסי הזנה: רכב, קריאת קילומטראז׳, טיפול, תיקון, הגדרות."""
from __future__ import annotations

from datetime import date
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget, QCheckBox,
)

from . import config
from .calc import Settings
from .db import Repo, ValidationError
from .widgets import GarageCombo, KmEdit, OptionalDateEdit, show_error


def _buttons(dialog: QDialog, ok_text="שמירה"):
    bb = QDialogButtonBox()
    ok = bb.addButton(ok_text, QDialogButtonBox.AcceptRole)
    cancel = bb.addButton("ביטול", QDialogButtonBox.RejectRole)
    ok.setDefault(True)
    bb.accepted.connect(dialog.accept)
    bb.rejected.connect(dialog.reject)
    return bb


class VehicleFormDialog(QDialog):
    """הקמת רכב חדש / עריכת פרטי רכב."""

    def __init__(self, repo: Repo, parent=None, vehicle: Optional[dict] = None):
        super().__init__(parent)
        self.repo = repo
        self.vehicle = vehicle
        self.setWindowTitle("עריכת פרטי רכב" if vehicle else "הקמת רכב חדש")
        self.setMinimumWidth(560)
        root = QVBoxLayout(self)

        details = QGroupBox("פרטי הרכב")
        form = QFormLayout(details)
        form.setLabelAlignment(Qt.AlignRight)
        self.plate = QLineEdit()
        self.plate.setPlaceholderText("לדוגמה 12-345-67")
        self.plate.setLayoutDirection(Qt.LeftToRight)
        self.make = QLineEdit()
        self.make.setPlaceholderText("טויוטה")
        self.model = QLineEdit()
        self.model.setPlaceholderText("קורולה")
        self.year = QSpinBox()
        self.year.setRange(0, 2100)
        self.year.setSpecialValueText(" ")
        self.year.setValue(0)
        self.year.setMinimumWidth(90)
        self.year.setLayoutDirection(Qt.LeftToRight)
        self.year.setButtonSymbols(QSpinBox.NoButtons)
        self.driver = QComboBox()
        self.driver.setEditable(True)
        self.driver.addItem("")
        self.driver.addItems(repo.drivers())
        self.driver.setCurrentIndex(0)
        self.driver.lineEdit().setPlaceholderText("שם הנהג / המחלקה")
        self.test_expiry = OptionalDateEdit()
        self.insurance_expiry = OptionalDateEdit()
        self.mileage_year_start = OptionalDateEdit()
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(60)
        form.addRow("מספר רישוי *", self.plate)
        row = QHBoxLayout()
        row.addWidget(self.make)
        row.addWidget(self.model)
        row.addWidget(QLabel("שנה"))
        row.addWidget(self.year)
        w = QWidget()
        w.setLayout(row)
        form.addRow("יצרן / דגם / שנה", w)
        form.addRow("נהג / שיוך", self.driver)
        form.addRow("תוקף טסט", self.test_expiry)
        form.addRow("תוקף ביטוח", self.insurance_expiry)
        hint = QLabel("אם יש תאריך תחילת ליסינג/מכסה שנתית - מכסת הקילומטרים תחושב משנה לשנה מתאריך זה. אחרת לפי שנה קלנדרית.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#5f6b7a;font-size:11px")
        form.addRow("תחילת שנת נסועה", self.mileage_year_start)
        form.addRow("", hint)
        form.addRow("הערות", self.notes)
        root.addWidget(details)

        if not vehicle:
            km_box = QGroupBox("קילומטראז׳ נוכחי (אופציונלי)")
            kf = QFormLayout(km_box)
            kf.setLabelAlignment(Qt.AlignRight)
            self.initial_km = KmEdit()
            self.initial_km_date = OptionalDateEdit(required=True, default=date.today())
            kf.addRow("קילומטראז׳", self.initial_km)
            kf.addRow("נכון לתאריך", self.initial_km_date)
            root.addWidget(km_box)

            svc_box = QGroupBox("טיפול אחרון (אופציונלי - נדרש לחישוב מועד הטיפול הבא)")
            sf = QFormLayout(svc_box)
            sf.setLabelAlignment(Qt.AlignRight)
            self.svc_date = OptionalDateEdit()
            self.svc_km = KmEdit()
            self.svc_garage = GarageCombo(repo.garages())
            self.svc_desc = QPlainTextEdit()
            self.svc_desc.setPlaceholderText("מה נעשה בטיפול: שמן, פילטרים, בלמים…")
            self.svc_desc.setFixedHeight(60)
            self.svc_cost = KmEdit(decimals=True)
            sf.addRow("תאריך הטיפול", self.svc_date)
            sf.addRow("קילומטראז׳ בטיפול", self.svc_km)
            sf.addRow("מוסך", self.svc_garage)
            sf.addRow("מה נעשה", self.svc_desc)
            sf.addRow("עלות (₪)", self.svc_cost)
            root.addWidget(svc_box)
        else:
            self.active = QCheckBox("רכב פעיל בצי")
            self.active.setChecked(bool(vehicle.get("active", 1)))
            root.addWidget(self.active)
            self._load(vehicle)

        root.addWidget(_buttons(self))
        self.result_id: Optional[int] = None

    def _load(self, v: dict):
        from .db import format_plate
        self.plate.setText(format_plate(v["plate"]))
        self.make.setText(v.get("make") or "")
        self.model.setText(v.get("model") or "")
        self.year.setValue(int(v["year"]) if v.get("year") else 0)
        self.driver.setCurrentText(v.get("driver") or "")
        self.test_expiry.set_value(v.get("test_expiry"))
        self.insurance_expiry.set_value(v.get("insurance_expiry"))
        self.mileage_year_start.set_value(v.get("mileage_year_start"))
        self.notes.setPlainText(v.get("notes") or "")

    def _data(self) -> dict:
        d = {
            "plate": self.plate.text(),
            "make": self.make.text(),
            "model": self.model.text(),
            "year": self.year.value() or None,
            "driver": self.driver.currentText(),
            "test_expiry": self.test_expiry.value(),
            "insurance_expiry": self.insurance_expiry.value(),
            "mileage_year_start": self.mileage_year_start.value(),
            "notes": self.notes.toPlainText(),
        }
        if self.vehicle:
            d["active"] = self.active.isChecked()
        else:
            d["initial_km"] = self.initial_km.value()
            d["initial_km_date"] = self.initial_km_date.value()
            d["last_service_date"] = self.svc_date.value()
            d["last_service_km"] = self.svc_km.value()
            d["last_service_garage"] = self.svc_garage.value()
            d["last_service_description"] = self.svc_desc.toPlainText()
            d["last_service_cost"] = self.svc_cost.value()
        return d

    def accept(self):
        try:
            d = self._data()
            if not self.vehicle and d["last_service_date"] and not d["last_service_km"] and d["initial_km"]:
                # אם לא הוזן ק״מ לטיפול אבל הוזן ק״מ נוכחי - עדיף להזהיר, החישוב לפי ק״מ לא יעבוד
                if QMessageBox.question(self, "חסר קילומטראז׳ בטיפול",
                                        "לא הוזן קילומטראז׳ בטיפול האחרון, ולכן מועד הטיפול הבא יחושב לפי תאריך בלבד. להמשיך?",
                                        QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                    return
            if self.vehicle:
                self.repo.update_vehicle(self.vehicle["id"], d)
                self.result_id = self.vehicle["id"]
            else:
                self.result_id = self.repo.create_vehicle(d)
        except ValidationError as e:
            show_error(self, str(e))
            return
        super().accept()


class ReadingDialog(QDialog):
    def __init__(self, repo: Repo, vehicle_id: int, parent=None, last_km: Optional[int] = None):
        super().__init__(parent)
        self.repo, self.vid = repo, vehicle_id
        self.setWindowTitle("הזנת קילומטראז׳")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        self.date = OptionalDateEdit(required=True, default=date.today())
        self.km = KmEdit()
        self.note = QLineEdit()
        self.note.setPlaceholderText("אופציונלי")
        form.addRow("תאריך הקריאה", self.date)
        form.addRow("קילומטראז׳ *", self.km)
        form.addRow("הערה", self.note)
        if last_km is not None:
            lbl = QLabel(f"קריאה אחרונה ידועה: {last_km:,} ק״מ")
            lbl.setStyleSheet("color:#5f6b7a")
            form.addRow("", lbl)
        lay.addLayout(form)
        lay.addWidget(_buttons(self))
        self.km.setFocus()

    def accept(self):
        d = {"reading_date": self.date.value(), "km": self.km.value(), "note": self.note.text()}
        try:
            self.repo.add_reading(self.vid, d)
        except ValidationError as e:
            msg = str(e)
            if "נמוך מקריאה קודמת" in msg:
                if QMessageBox.question(self, "בדיקת ערך", msg + "\n\nלשמור בכל זאת?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                    try:
                        self.repo.add_reading(self.vid, {**d, "force": True})
                    except ValidationError as e2:
                        show_error(self, str(e2))
                        return
                    return super().accept()
                return
            show_error(self, msg)
            return
        super().accept()


class ServiceDialog(QDialog):
    """טיפול תקופתי - הוספה או עריכה."""

    def __init__(self, repo: Repo, vehicle_id: int, parent=None, service: Optional[dict] = None, suggested_km: Optional[int] = None):
        super().__init__(parent)
        self.repo, self.vid, self.service = repo, vehicle_id, service
        self.setWindowTitle("עריכת טיפול" if service else "הזנת טיפול")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        self.date = OptionalDateEdit(required=True, default=date.today())
        self.km = KmEdit()
        self.garage = GarageCombo(repo.garages())
        self.desc = QPlainTextEdit()
        self.desc.setPlaceholderText("מה נעשה בטיפול: החלפת שמן ופילטרים, בדיקת בלמים, איזון גלגלים…")
        self.desc.setMinimumHeight(90)
        self.cost = KmEdit(decimals=True)
        form.addRow("תאריך הטיפול *", self.date)
        form.addRow("קילומטראז׳ בטיפול", self.km)
        form.addRow("מוסך", self.garage)
        form.addRow("מה נעשה בטיפול", self.desc)
        form.addRow("עלות (₪)", self.cost)
        lay.addLayout(form)
        lay.addWidget(_buttons(self))
        if service:
            self.date.set_value(service["service_date"])
            self.km.set_value(service.get("odometer_km"))
            self.garage.set_value(service.get("garage"))
            self.desc.setPlainText(service.get("description") or "")
            self.cost.set_value(service.get("cost"))
        elif suggested_km is not None:
            self.km.set_value(suggested_km)

    def accept(self):
        d = {"service_date": self.date.value(), "odometer_km": self.km.value(), "garage": self.garage.value(),
             "description": self.desc.toPlainText(), "cost": self.cost.value()}
        try:
            if self.service:
                self.repo.update_service(self.service["id"], d)
            else:
                self.repo.add_service(self.vid, d)
        except ValidationError as e:
            show_error(self, str(e))
            return
        super().accept()


class RepairDialog(QDialog):
    """תיקון - הוספה או עריכה."""

    def __init__(self, repo: Repo, vehicle_id: int, parent=None, repair: Optional[dict] = None, suggested_km: Optional[int] = None):
        super().__init__(parent)
        self.repo, self.vid, self.repair = repo, vehicle_id, repair
        self.setWindowTitle("עריכת תיקון" if repair else "הזנת תיקון")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        self.date = OptionalDateEdit(required=True, default=date.today())
        self.km = KmEdit()
        self.garage = GarageCombo(repo.garages())
        self.desc = QPlainTextEdit()
        self.desc.setPlaceholderText("מה תוקן: החלפת רפידות קדמיות, תיקון פח, החלפת מצבר…")
        self.desc.setMinimumHeight(90)
        self.cost = KmEdit(decimals=True)
        form.addRow("תאריך התיקון *", self.date)
        form.addRow("קילומטראז׳ בתיקון", self.km)
        form.addRow("מוסך *", self.garage)
        form.addRow("תיאור התיקון *", self.desc)
        form.addRow("עלות (₪)", self.cost)
        lay.addLayout(form)
        lay.addWidget(_buttons(self))
        if repair:
            self.date.set_value(repair["repair_date"])
            self.km.set_value(repair.get("odometer_km"))
            self.garage.set_value(repair.get("garage"))
            self.desc.setPlainText(repair.get("description") or "")
            self.cost.set_value(repair.get("cost"))
        elif suggested_km is not None:
            self.km.set_value(suggested_km)

    def accept(self):
        d = {"repair_date": self.date.value(), "odometer_km": self.km.value(), "garage": self.garage.value(),
             "description": self.desc.toPlainText(), "cost": self.cost.value()}
        if not d["garage"]:
            show_error(self, "חובה להזין את המוסך שבו בוצע התיקון")
            return
        try:
            if self.repair:
                self.repo.update_repair(self.repair["id"], d)
            else:
                self.repo.add_repair(self.vid, d)
        except ValidationError as e:
            show_error(self, str(e))
            return
        super().accept()


class SettingsDialog(QDialog):
    """הגדרות: מרווחי טיפול, מכסה שנתית, ספי התראה, מיקום קובץ הנתונים."""

    def __init__(self, repo: Repo, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("הגדרות")
        self.setMinimumWidth(520)
        s = repo.get_settings()
        lay = QVBoxLayout(self)

        box = QGroupBox("כללי תחזוקה והתראות")
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignRight)
        self.interval_km = QSpinBox(); self.interval_km.setRange(1000, 100000); self.interval_km.setSingleStep(1000); self.interval_km.setValue(s.service_interval_km)
        self.interval_months = QSpinBox(); self.interval_months.setRange(1, 60); self.interval_months.setValue(s.service_interval_months)
        self.annual_limit = QSpinBox(); self.annual_limit.setRange(1000, 500000); self.annual_limit.setSingleStep(1000); self.annual_limit.setValue(s.annual_km_limit)
        self.alert_days = QSpinBox(); self.alert_days.setRange(1, 365); self.alert_days.setValue(s.alert_days)
        self.alert_km = QSpinBox(); self.alert_km.setRange(0, 20000); self.alert_km.setSingleStep(100); self.alert_km.setValue(s.alert_km)
        for w in (self.interval_km, self.interval_months, self.annual_limit, self.alert_days, self.alert_km):
            w.setGroupSeparatorShown(True)
            w.setLayoutDirection(Qt.LeftToRight)
            w.setAlignment(Qt.AlignRight)
            w.setMinimumWidth(160)
        form.addRow("טיפול כל (ק״מ)", self.interval_km)
        form.addRow("או כל (חודשים)", self.interval_months)
        form.addRow("מכסת נסועה שנתית (ק״מ)", self.annual_limit)
        form.addRow("התראה לפני טסט/ביטוח/טיפול (ימים)", self.alert_days)
        form.addRow("התראה כשנותרו לטיפול (ק״מ)", self.alert_km)
        lay.addWidget(box)

        dbox = QGroupBox("קובץ הנתונים")
        dl = QVBoxLayout(dbox)
        self.db_label = QLabel(str(repo.path))
        self.db_label.setWordWrap(True)
        self.db_label.setLayoutDirection(Qt.LeftToRight)
        self.db_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        dl.addWidget(self.db_label)
        hint = QLabel("כדי שכמה עובדים יעבדו על אותם נתונים, אפשר לשמור את הקובץ בתיקייה משותפת ברשת ולבחור אותו בכל מחשב. השינוי נכנס לתוקף לאחר הפעלה מחדש של התוכנה.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#5f6b7a;font-size:11px")
        dl.addWidget(hint)
        row = QHBoxLayout()
        choose = QPushButton("בחירת קובץ נתונים אחר…")
        choose.clicked.connect(self._choose_db)
        reset = QPushButton("חזרה לברירת המחדל")
        reset.clicked.connect(self._reset_db)
        row.addWidget(choose)
        row.addWidget(reset)
        row.addStretch(1)
        dl.addLayout(row)
        lay.addWidget(dbox)

        lay.addWidget(_buttons(self))
        self.db_changed = False

    def _choose_db(self):
        path, _ = QFileDialog.getSaveFileName(self, "בחירת קובץ נתונים", str(self.repo.path), "קובץ נתונים (*.db);;כל הקבצים (*)", options=QFileDialog.DontConfirmOverwrite)
        if path:
            config.set_db_path(path)
            self.db_label.setText(path)
            self.db_changed = True

    def _reset_db(self):
        config.set_db_path(None)
        self.db_label.setText(str(config.default_db_path()))
        self.db_changed = True

    def accept(self):
        s = Settings(
            service_interval_km=self.interval_km.value(), service_interval_months=self.interval_months.value(),
            annual_km_limit=self.annual_limit.value(), alert_days=self.alert_days.value(), alert_km=self.alert_km.value(),
        )
        try:
            self.repo.update_settings(s)
        except ValidationError as e:
            show_error(self, str(e))
            return
        if self.db_changed:
            QMessageBox.information(self, "מיקום הנתונים שונה", "מיקום קובץ הנתונים ישתנה בהפעלה הבאה של התוכנה.")
        super().accept()
