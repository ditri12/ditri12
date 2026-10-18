#!/usr/bin/env python3
"""יצירת נתוני דוגמה להתנסות: python seed_demo.py [נתיב לקובץ]
ברירת מחדל: demo.db בתיקיית התוכנה. להרצה עם הדוגמה: FLEET_DB=demo.db python fleet_manager.py
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fleet_app.db import Repo  # noqa: E402

today = date.today()


def d(days_ago):
    return (today - timedelta(days=days_ago)).isoformat()


def seed(path):
    if os.path.exists(path):
        os.remove(path)
    repo = Repo(path)
    # 1. רכב שנוסע הרבה - חריגה שנתית וטיפול קרוב
    v1 = repo.create_vehicle({
        "plate": "12-345-67", "make": "טויוטה", "model": "קורולה", "year": 2022, "driver": "דני כהן",
        "test_expiry": d(-200), "insurance_expiry": d(-20), "initial_km": 61000, "initial_km_date": d(300),
        "last_service_date": d(150), "last_service_km": 77000, "last_service_garage": "מוסך הגליל", "last_service_description": "החלפת שמן ופילטרים, בדיקת בלמים", "last_service_cost": 950,
    })
    repo.add_reading(v1, {"reading_date": d(60), "km": 86500})
    repo.add_reading(v1, {"reading_date": d(3), "km": 91200})
    repo.add_repair(v1, {"repair_date": d(90), "odometer_km": 83000, "garage": "מוסך הגליל", "description": "החלפת רפידות בלם קדמיות", "cost": 780})
    # 2. רכב תקין
    v2 = repo.create_vehicle({
        "plate": "87-654-32", "make": "יונדאי", "model": "i20", "year": 2023, "driver": "מיכל לוי",
        "test_expiry": d(-300), "insurance_expiry": d(-250), "initial_km": 20000, "initial_km_date": d(200),
        "last_service_date": d(40), "last_service_km": 26000, "last_service_garage": "מוסך מרכז", "last_service_description": "טיפול 25,000: שמן, פילטר אוויר, סיבוב גלגלים", "last_service_cost": 700,
    })
    repo.add_reading(v2, {"reading_date": d(5), "km": 27600})
    # 3. רכב באיחור לטיפול (שנה עברה) וטסט שפג
    v3 = repo.create_vehicle({
        "plate": "555-44-333", "make": "סקודה", "model": "אוקטביה", "year": 2020, "driver": "מחלקת שירות",
        "test_expiry": d(12), "insurance_expiry": d(-100), "initial_km": 140000, "initial_km_date": d(400),
        "last_service_date": d(390), "last_service_km": 139500, "last_service_garage": "סקודה שירות", "last_service_description": "טיפול שנתי, החלפת מצתים",
    })
    repo.add_reading(v3, {"reading_date": d(30), "km": 149000})
    repo.add_repair(v3, {"repair_date": d(200), "odometer_km": 144000, "garage": "פחחות אבי", "description": "תיקון פגוש אחורי וצביעה", "cost": 2400})
    repo.add_repair(v3, {"repair_date": d(45), "odometer_km": 148500, "garage": "סקודה שירות", "description": "החלפת מצבר", "cost": 650})
    # 4. רכב חדש ללא נתונים
    repo.create_vehicle({"plate": "11-222-33", "make": "קיה", "model": "פיקנטו", "year": 2025, "driver": "", "test_expiry": d(-360)})
    repo.close()
    print(f"נוצר קובץ דוגמה: {path}")


if __name__ == "__main__":
    seed(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo.db"))
