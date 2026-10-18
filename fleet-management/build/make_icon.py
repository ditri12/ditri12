"""יוצר קובץ אייקון (ICO/PNG) לתוכנה מתוך הציור שבקוד. משמש בבנייה: python build/make_icon.py build/icon.ico"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from PySide6.QtGui import QGuiApplication  # noqa: E402

app = QGuiApplication([])
from fleet_app.main import make_icon  # noqa: E402

out = sys.argv[1] if len(sys.argv) > 1 else "icon.ico"
pm = make_icon().pixmap(256, 256)
ok = pm.save(out)
print(("created " if ok else "FAILED ") + out)
sys.exit(0 if ok else 1)
