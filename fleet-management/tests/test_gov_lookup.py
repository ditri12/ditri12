import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from fleet_app import gov_lookup  # noqa: E402

SAMPLE = {
    "_id": 1, "mispar_rechev": 1234567, "tozeret_cd": 123, "sug_degem": "P", "tozeret_nm": "TOYOTA JAPAN",
    "degem_cd": 45, "degem_nm": "ZRE210L", "ramat_gimur": "SUN", "ramat_eivzur_betihuty": 3, "kvutzat_zihum": 2,
    "shnat_yitzur": 2022, "degem_manoa": "2ZR", "mivchan_acharon_dt": "2026-03-11T00:00:00", "tokef_dt": "2027-03-11",
    "baalut": "חברה", "misgeret": "JTNB4MBE201234567", "tzeva_cd": 20, "tzeva_rechev": "לבן", "zmig_kidmi": "205/55R16",
    "zmig_ahori": "205/55R16", "sug_delek_nm": "היברידי", "horaat_rishum": 123, "moed_aliya_lakvish": "2022-05",
    "kinuy_mishari": "COROLLA",
}


class FakeResp:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class ParseTests(unittest.TestCase):
    def test_parse_record(self):
        info = gov_lookup.parse_record(SAMPLE, "x")
        self.assertEqual(info.make, "Toyota Japan")
        self.assertEqual(info.model, "Corolla")
        self.assertEqual(info.year, 2022)
        self.assertEqual(info.test_expiry.isoformat(), "2027-03-11")
        self.assertEqual(info.last_test_date.isoformat(), "2026-03-11")
        self.assertEqual(info.color, "לבן")
        self.assertEqual(info.fuel, "היברידי")
        self.assertIn("מספר שלדה", info.notes_text())
        self.assertIn("Toyota Japan Corolla 2022", info.summary())


class LookupTests(unittest.TestCase):
    def test_found_in_first_resource(self):
        def fake_urlopen(req, timeout=0):
            if gov_lookup.RESOURCES[0][0] in req.full_url:
                return FakeResp({"success": True, "result": {"records": [SAMPLE]}})
            if gov_lookup.TEST_RESOURCE in req.full_url:
                return FakeResp({"success": True, "result": {"records": [{"mispar_rechev": 1234567, "kilometer_test_aharon": "48,500"}]}})
            return FakeResp({"success": True, "result": {"records": []}})
        with mock.patch.object(gov_lookup.urllib.request, "urlopen", fake_urlopen):
            info = gov_lookup.lookup_plate("12-345-67")
        self.assertEqual(info.model, "Corolla")
        self.assertEqual(info.last_test_km, 48500)
        self.assertTrue(info.source.startswith("משרד התחבורה"))

    def test_not_found(self):
        with mock.patch.object(gov_lookup.urllib.request, "urlopen", lambda req, timeout=0: FakeResp({"success": True, "result": {"records": []}})):
            with self.assertRaises(gov_lookup.NotFound):
                gov_lookup.lookup_plate("7654321")

    def test_network_error(self):
        def boom(req, timeout=0):
            raise gov_lookup.urllib.error.URLError("no route")
        with mock.patch.object(gov_lookup.urllib.request, "urlopen", boom):
            with self.assertRaises(gov_lookup.NetworkError):
                gov_lookup.lookup_plate("7654321")

    def test_invalid_plate(self):
        with self.assertRaises(gov_lookup.NotFound):
            gov_lookup.lookup_plate("12")


if __name__ == "__main__":
    unittest.main()
