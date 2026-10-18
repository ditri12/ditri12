import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fleet_app import calc, db  # noqa: E402


class RepoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = db.Repo(os.path.join(self.tmp.name, "t.db"))

    def tearDown(self):
        self.repo.close()
        self.tmp.cleanup()

    def test_create_with_initial_km_and_last_service(self):
        vid = self.repo.create_vehicle({
            "plate": "12-345-67", "make": "טויוטה", "model": "קורולה", "year": "2022", "driver": "דני",
            "test_expiry": "2026-11-01", "insurance_expiry": "2027-01-01",
            "initial_km": "48,500", "initial_km_date": "2026-10-01",
            "last_service_date": "2026-06-01", "last_service_km": "41000", "last_service_garage": "מוסך הגליל",
            "last_service_description": "שמן, פילטרים",
        })
        v = self.repo.get_vehicle(vid)
        self.assertEqual(v["plate"], "1234567")
        self.assertEqual(db.format_plate(v["plate"]), "12-345-67")
        self.assertEqual(len(self.repo.readings(vid)), 1)
        self.assertEqual(self.repo.readings(vid)[0]["km"], 48500)
        self.assertEqual(self.repo.services(vid)[0]["garage"], "מוסך הגליל")
        self.assertEqual(self.repo.garages(), ["מוסך הגליל"])

    def test_duplicate_plate(self):
        self.repo.create_vehicle({"plate": "1111111"})
        with self.assertRaises(db.ValidationError):
            self.repo.create_vehicle({"plate": "111-11-11"})

    def test_reading_sanity_check(self):
        vid = self.repo.create_vehicle({"plate": "2222222"})
        self.repo.add_reading(vid, {"reading_date": "2026-01-01", "km": 10000})
        with self.assertRaises(db.ValidationError):
            self.repo.add_reading(vid, {"reading_date": "2026-02-01", "km": 9000})
        self.repo.add_reading(vid, {"reading_date": "2026-02-01", "km": 9000, "force": True})
        self.assertEqual(len(self.repo.readings(vid)), 2)

    def test_repair_requires_description(self):
        vid = self.repo.create_vehicle({"plate": "3333333"})
        with self.assertRaises(db.ValidationError):
            self.repo.add_repair(vid, {"repair_date": "2026-01-01", "description": ""})
        rid = self.repo.add_repair(vid, {"repair_date": "2026-01-01", "description": "החלפת רפידות", "garage": "מוסך מרכז", "cost": "850"})
        self.repo.update_repair(rid, {"repair_date": "2026-01-02", "description": "החלפת רפידות קדמיות", "cost": "900"})
        self.assertEqual(self.repo.repairs(vid)[0]["cost"], 900)

    def test_settings_roundtrip(self):
        s = self.repo.get_settings()
        self.assertEqual(s.service_interval_km, 15000)
        s.annual_km_limit = 40000
        self.repo.update_settings(s)
        self.assertEqual(self.repo.get_settings().annual_km_limit, 40000)

    def test_cascade_delete(self):
        vid = self.repo.create_vehicle({"plate": "4444444", "initial_km": 100})
        self.repo.delete_vehicle(vid)
        self.assertEqual(self.repo.conn.execute("SELECT COUNT(*) FROM odometer_readings").fetchone()[0], 0)

    def test_compute_from_repo(self):
        vid = self.repo.create_vehicle({"plate": "5555555", "last_service_date": "2026-01-01", "last_service_km": "20000"})
        self.repo.add_reading(vid, {"reading_date": "2026-01-01", "km": 20000})
        self.repo.add_reading(vid, {"reading_date": "2026-07-01", "km": 34000})
        st = calc.compute_vehicle(self.repo.get_vehicle(vid), self.repo.readings(vid), self.repo.services(vid), self.repo.repairs(vid), self.repo.get_settings(), "2026-07-01")
        self.assertEqual(st.service.reason, "km")
        self.assertEqual(st.service.status, "soon")


if __name__ == "__main__":
    unittest.main()
