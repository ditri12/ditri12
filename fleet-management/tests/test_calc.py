import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fleet_app import calc  # noqa: E402

S = calc.Settings()


def tl(*pairs):
    return [calc.Point(date.fromisoformat(d), k) for d, k in pairs]


class TimelineTests(unittest.TestCase):
    def test_merge_and_sort(self):
        t = calc.build_timeline(
            readings=[{"reading_date": "2026-03-01", "km": 10000}, {"reading_date": "2026-01-01", "km": 8000}],
            services=[{"service_date": "2026-02-01", "odometer_km": 9000}],
            repairs=[{"repair_date": "2026-03-01", "odometer_km": 10050}],
        )
        self.assertEqual([(p.date.isoformat(), p.km) for p in t],
                         [("2026-01-01", 8000), ("2026-02-01", 9000), ("2026-03-01", 10050)])

    def test_average(self):
        self.assertEqual(calc.average_daily_km(tl(("2026-01-01", 0), ("2026-01-31", 3000))), 100)
        self.assertIsNone(calc.average_daily_km(tl(("2026-01-01", 0))))

    def test_average_window(self):
        t = tl(("2020-01-01", 0), ("2025-10-01", 100000), ("2026-01-01", 109200))
        self.assertEqual(calc.average_daily_km(t), 100)


class ServiceTests(unittest.TestCase):
    def test_due_by_km(self):
        t = tl(("2026-01-01", 50000), ("2026-04-01", 59000))
        r = calc.service_forecast({"service_date": "2026-01-01", "odometer_km": 50000}, t, "2026-04-01", 100, S)
        self.assertEqual(r.reason, "km")
        self.assertEqual(r.due_km, 65000)
        self.assertEqual(r.km_remaining, 6000)
        self.assertEqual(r.expected_date.isoformat(), "2026-05-31")
        self.assertEqual(r.status, "ok")

    def test_due_by_date(self):
        t = tl(("2025-06-01", 50000), ("2026-05-01", 52000))
        r = calc.service_forecast({"service_date": "2025-06-01", "odometer_km": 50000}, t, "2026-05-10", calc.average_daily_km(t), S)
        self.assertEqual(r.reason, "date")
        self.assertEqual(r.expected_date.isoformat(), "2026-06-01")
        self.assertEqual(r.status, "soon")

    def test_overdue(self):
        t = tl(("2026-01-01", 50000), ("2026-03-01", 66000))
        r = calc.service_forecast({"service_date": "2026-01-01", "odometer_km": 50000}, t, "2026-03-05", calc.average_daily_km(t), S)
        self.assertEqual(r.status, "overdue")
        self.assertLess(r.km_remaining, 0)

    def test_unknown(self):
        self.assertEqual(calc.service_forecast(None, [], "2026-01-01", None, S).status, "unknown")


class MileageTests(unittest.TestCase):
    def test_over(self):
        t = tl(("2026-01-01", 10000), ("2026-07-01", 30000))
        r = calc.annual_projection(t, "2026-07-01", calc.average_daily_km(t), None, S)
        self.assertEqual(r.year_start.isoformat(), "2026-01-01")
        self.assertEqual(r.year_end.isoformat(), "2027-01-01")
        self.assertEqual(r.driven_so_far, 20000)
        self.assertGreater(r.projected_year_km, 35000)
        self.assertEqual(r.status, "over")

    def test_ok(self):
        t = tl(("2026-01-01", 10000), ("2026-07-01", 20000))
        r = calc.annual_projection(t, "2026-07-01", calc.average_daily_km(t), None, S)
        self.assertEqual(r.status, "ok")

    def test_interpolate_year_start(self):
        t = tl(("2025-12-01", 0), ("2026-01-31", 6100))
        r = calc.annual_projection(t, "2026-01-31", 100, None, S)
        self.assertFalse(r.partial_year)
        self.assertEqual(r.driven_so_far, 3000)

    def test_anchor(self):
        self.assertEqual(tuple(d.isoformat() for d in calc.year_window("2026-10-18", "2024-03-15")), ("2026-03-15", "2027-03-15"))
        self.assertEqual(tuple(d.isoformat() for d in calc.year_window("2026-02-01", "2024-03-15")), ("2025-03-15", "2026-03-15"))


class ExpiryTests(unittest.TestCase):
    def test_states(self):
        self.assertEqual(calc.expiry_status("2026-01-01", "2026-02-01", 30).status, "expired")
        self.assertEqual(calc.expiry_status("2026-02-20", "2026-02-01", 30).status, "soon")
        self.assertEqual(calc.expiry_status("2026-12-20", "2026-02-01", 30).status, "ok")
        self.assertEqual(calc.expiry_status(None, "2026-02-01", 30).status, "unknown")


class ComputeTests(unittest.TestCase):
    def test_aggregate(self):
        v = {"test_expiry": "2026-10-20", "insurance_expiry": "2027-05-01", "mileage_year_start": None}
        r = calc.compute_vehicle(
            v,
            readings=[{"reading_date": "2026-01-01", "km": 20000}, {"reading_date": "2026-10-01", "km": 50000}],
            services=[{"id": 1, "service_date": "2026-01-01", "odometer_km": 20000}],
            repairs=[], settings=S, today="2026-10-18",
        )
        self.assertEqual(sorted(a.type for a in r.alerts), ["mileage", "service", "test"])
        self.assertEqual(r.service.status, "overdue")
        self.assertEqual(r.mileage.status, "over")
        self.assertEqual(r.test.status, "soon")
        self.assertEqual(r.avg_daily_km, 109.9)
        self.assertEqual(r.worst_level, "danger")


if __name__ == "__main__":
    unittest.main()
