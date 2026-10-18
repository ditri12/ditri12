"""נקודת הכניסה של התוכנה."""
from __future__ import annotations

import os
import sqlite3
import sys

from PySide6.QtCore import QLocale, Qt
from PySide6.QtGui import QFont, QIcon, QPixmap, QPainter, QColor
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from . import APP_NAME, APP_TITLE, config
from .db import Repo

STYLE = """
QMainWindow, QDialog { background: #f4f6fa; }
QToolBar { background: #0f1b2d; border: 0; padding: 4px 8px; spacing: 6px; }
QToolBar QToolButton { color: #e5eaf0; padding: 6px 12px; border-radius: 6px; font-weight: 600; }
QToolBar QToolButton:hover { background: rgba(255,255,255,0.12); color: #fff; }
QTableWidget { background: #fff; border: 1px solid #e2e7ee; border-radius: 8px; gridline-color: #eef1f5; alternate-background-color: #f8fafc; }
QHeaderView::section { background: #f1f4f8; color: #4a5a6a; padding: 6px 8px; border: 0; border-bottom: 1px solid #e2e7ee; font-weight: 600; }
QTableWidget::item { padding: 4px 6px; }
QTableWidget::item:selected { background: #dbe7ff; color: #1b2430; }
QListWidget { background: #fff; border: 1px solid #e2e7ee; border-radius: 8px; }
QListWidget::item { padding: 5px 8px; margin: 2px; border-radius: 6px; }
QListWidget#Alerts { border: 0; background: transparent; }
QPushButton { background: #1f6feb; color: #fff; border: 1px solid #1f6feb; border-radius: 7px; padding: 6px 14px; font-weight: 600; }
QPushButton:hover { background: #185ac2; }
QPushButton:disabled { background: #b9c4d3; border-color: #b9c4d3; }
QPushButton#secondary { background: #fff; color: #1b2430; border-color: #cfd6df; }
QPushButton#secondary:hover { background: #f1f4f8; }
QPushButton#danger { background: #fff; color: #c0392b; border-color: #f1b7b1; }
QPushButton#danger:hover { background: #fdecea; }
QDialogButtonBox QPushButton { min-width: 90px; }
QLineEdit, QComboBox, QDateEdit, QSpinBox, QPlainTextEdit { background: #fff; border: 1px solid #cfd6df; border-radius: 6px; padding: 5px 8px; }
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus, QPlainTextEdit:focus { border-color: #1f6feb; }
QGroupBox { background: #fff; border: 1px solid #e2e7ee; border-radius: 10px; margin-top: 12px; padding: 14px 10px 8px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top right; right: 12px; padding: 0 6px; color: #4a5a6a; }
QTabWidget::pane { background: #fff; border: 1px solid #e2e7ee; border-radius: 8px; top: -1px; }
QTabBar::tab { background: #e9edf3; color: #4a5a6a; padding: 8px 18px; border-top-left-radius: 8px; border-top-right-radius: 8px; margin-left: 2px; font-weight: 600; }
QTabBar::tab:selected { background: #fff; color: #1b2430; }
QFrame#Header { background: #fff; border: 1px solid #e2e7ee; border-radius: 10px; }
QLabel#Plate { font-family: Consolas, "Courier New", monospace; font-size: 20px; font-weight: 700; background: #fff8c5; border: 1px solid #e3c900; border-radius: 5px; padding: 2px 10px; color: #222; }
QStatusBar { color: #5f6b7a; }
QSplitter::handle { background: transparent; height: 8px; }
"""


def make_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#1f6feb"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(0, 0, 64, 64, 14, 14)
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(12, 28, 40, 18, 5, 5)
    p.drawRoundedRect(20, 18, 24, 14, 4, 4)
    p.setBrush(QColor("#1f6feb"))
    p.drawEllipse(17, 40, 9, 9)
    p.drawEllipse(38, 40, 9, 9)
    p.end()
    return QIcon(pm)


def first_run_choose_location() -> None:
    """בהפעלה הראשונה: לשאול היכן לשמור את הרישום (מחשב זה או תיקייה משותפת ברשת)."""
    if config.is_configured() or os.environ.get("FLEET_DB"):
        return
    box = QMessageBox()
    box.setWindowTitle(APP_TITLE)
    box.setIcon(QMessageBox.Question)
    box.setText("ברוכים הבאים! היכן לשמור את רישום צי הרכב?")
    box.setInformativeText("אפשר לשמור במחשב זה בלבד, או בתיקייה משותפת ברשת כדי שכמה עובדים יעבדו על אותו רישום.\n"
                           "ניתן לשנות זאת בכל עת דרך 'הגדרות'.")
    local = box.addButton("במחשב זה", QMessageBox.AcceptRole)
    shared = box.addButton("בחירת תיקייה (למשל ברשת)…", QMessageBox.ActionRole)
    box.setDefaultButton(local)
    box.exec()
    if box.clickedButton() is shared:
        while True:
            folder = QFileDialog.getExistingDirectory(None, "בחירת תיקייה לשמירת הנתונים", str(config.default_data_dir()), QFileDialog.ShowDirsOnly)
            if not folder:
                break
            err = config.check_writable(folder)
            if err:
                QMessageBox.critical(None, APP_TITLE, err)
                continue
            config.set_data_dir(folder)
            break


def open_repo(app) -> Repo | None:
    first_run_choose_location()
    path = config.db_path()
    try:
        return Repo(path)
    except (sqlite3.Error, OSError) as e:
        QMessageBox.critical(None, APP_TITLE, f"לא ניתן לפתוח את קובץ הנתונים:\n{path}\n\n{e}\n\n"
                             "התוכנה תחזור לקובץ ברירת המחדל במחשב זה.")
        config.set_data_dir(None)
        try:
            return Repo(config.default_db_path())
        except (sqlite3.Error, OSError) as e2:
            QMessageBox.critical(None, APP_TITLE, f"גם קובץ ברירת המחדל לא נפתח:\n{e2}")
            return None


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_TITLE)
    app.setOrganizationName("Fleet")
    app.setLayoutDirection(Qt.RightToLeft)
    QLocale.setDefault(QLocale(QLocale.Hebrew, QLocale.Israel))
    font = QFont("Segoe UI" if sys.platform.startswith("win") else app.font().family(), 10)
    app.setFont(font)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setWindowIcon(make_icon())

    repo = open_repo(app)
    if repo is None:
        return 1
    from .ui_main import MainWindow
    win = MainWindow(repo)
    win.show()
    code = app.exec()
    repo.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
