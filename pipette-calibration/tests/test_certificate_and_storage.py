from datetime import date

import pytest

from pipette_cal.certificate import CertificateInfo, build_certificate, default_filename
from pipette_cal.models import Level, get_spec
from pipette_cal.physics import Environment, z_factor
from pipette_cal.stats import evaluate
from pipette_cal.storage import AppConfig, CalibrationRecord, History


def _result(model="P200"):
    env = Environment(21.5, 48.0, 1009.0)
    spec = get_spec(model)
    z = z_factor(env)
    weights = {lv: [spec.volume_for(lv) / 1000 / z * f for f in (0.998, 1.001, 1.0, 0.999)]
               for lv in Level}
    return evaluate(spec, env, weights)


def test_certificate_is_two_pages(tmp_path):
    res = _result()
    info = CertificateInfo("LG-CAL-2026-0001", date(2026, 11, 12), date(2027, 11, 12),
                           "SN-12345", "D200", operator="D. Test", comments="ok")
    out = build_certificate(tmp_path / "cert.pdf", info, res)
    data = out.read_bytes()
    assert data.startswith(b"%PDF")
    assert data.count(b"/Type /Page\n") + data.count(b"/Type /Page\r") == 2 or \
        data.count(b"/Type /Page") - data.count(b"/Type /Pages") == 2
    assert default_filename(info, "P200") == "LG-CAL-2026-0001_P200_SN-12345_20261112.pdf"


def test_certificate_with_long_comment_still_two_pages(tmp_path):
    res = _result("P8x1200")
    info = CertificateInfo("LG-CAL-2026-0002", date(2026, 1, 5), date(2027, 1, 5),
                           "MC/9", "D1200", comments="word " * 40)
    data = build_certificate(tmp_path / "c.pdf", info, res).read_bytes()
    assert data.count(b"/Type /Page") - data.count(b"/Type /Pages") == 2


def test_history_document_numbers_and_search(tmp_path):
    h = History(tmp_path / "h.sqlite")
    assert h.next_document_number(date(2026, 3, 1)) == "LG-CAL-2026-0001"
    rec = CalibrationRecord("LG-CAL-2026-0001", "2026-03-01 10:00:00", "P200", "SN-1",
                            "D200", "PASS", "op", {"a": 1})
    h.add(rec)
    assert rec.id == 1
    assert h.next_document_number(date(2026, 3, 2)) == "LG-CAL-2026-0002"
    assert h.next_document_number(date(2027, 1, 1)) == "LG-CAL-2027-0001"
    assert h.list(search="SN-1")[0].payload == {"a": 1}
    assert h.list(search="nothing") == []
    assert h.last_for_serial("SN-1").document_no == "LG-CAL-2026-0001"
    assert h.get(1).model == "P200" and h.get(99) is None
    h.close()


def test_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("pipette_cal.storage.app_data_dir", lambda: tmp_path)
    cfg = AppConfig.load()
    assert cfg.scale_ip == "10.0.0.112"
    cfg.scale_ip = "192.168.1.5"
    cfg.operator = "Dmitri"
    cfg.save()
    again = AppConfig.load()
    assert again.scale_ip == "192.168.1.5" and again.operator == "Dmitri"
    (tmp_path / "config.json").write_text("{not json")
    assert AppConfig.load().scale_ip == "10.0.0.112"
