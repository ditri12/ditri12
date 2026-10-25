"""זיהוי רכב לפי מספר רישוי מול מאגר הרכבים הפתוח של משרד התחבורה (data.gov.il).

המאגר ציבורי ואינו דורש מפתח. השאילתה: CKAN datastore_search עם סינון לפי mispar_rechev.
אם אין חיבור לאינטרנט או שהרכב לא נמצא, המערכת מבקשת הזנה ידנית.
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

API_URL = "https://data.gov.il/api/3/action/datastore_search"

# מאגרים לפי סוג רכב: פרטי/מסחרי קל, דו-גלגלי, רכב כבד. נבדקים לפי הסדר.
RESOURCES = [
    ("053cea08-09bc-40ec-8f7a-156f0677aff3", "רכב פרטי ומסחרי"),
    ("bf9df4e2-d90d-4c0a-a400-19e15af8e95f", "רכב דו-גלגלי"),
    ("cd3acc5c-03c3-4c89-9c54-d40f93c0d790", "רכב כבד"),
]
# מאגר מבחני רישוי שנתיים - מכיל את הקילומטראז׳ שנמדד בטסט האחרון
TEST_RESOURCE = "56063a99-8a3e-4ff4-912e-5966c0279bad"

USER_AGENT = "FleetManager/1.0 (+https://github.com/ditri12/ditri12)"


class LookupError_(Exception):
    """שגיאה כללית בזיהוי."""


class NetworkError(LookupError_):
    """אין חיבור למאגר (אינטרנט/חומת אש/המאגר לא זמין)."""


class NotFound(LookupError_):
    """מספר הרכב לא נמצא במאגרים."""


@dataclass
class VehicleInfo:
    plate: str
    make: Optional[str] = None
    model: Optional[str] = None
    trim: Optional[str] = None
    year: Optional[int] = None
    test_expiry: Optional[date] = None
    last_test_date: Optional[date] = None
    last_test_km: Optional[int] = None
    color: Optional[str] = None
    fuel: Optional[str] = None
    ownership: Optional[str] = None
    vin: Optional[str] = None
    on_road_date: Optional[str] = None   # חודש עלייה לכביש, למשל 2022-05
    source: str = ""
    raw: dict = field(default_factory=dict)

    def summary(self) -> str:
        parts = [p for p in (self.make, self.model, str(self.year) if self.year else None) if p]
        extra = [p for p in (self.color, self.fuel, self.ownership) if p]
        s = " ".join(parts)
        if extra:
            s += " (" + ", ".join(extra) + ")"
        return s

    def notes_text(self) -> str:
        """טקסט להוספה להערות הרכב עם הפרטים שאינם שדות במערכת."""
        lines = []
        if self.trim:
            lines.append(f"רמת גימור: {self.trim}")
        if self.color:
            lines.append(f"צבע: {self.color}")
        if self.fuel:
            lines.append(f"סוג דלק: {self.fuel}")
        if self.ownership:
            lines.append(f"בעלות: {self.ownership}")
        if self.vin:
            lines.append(f"מספר שלדה: {self.vin}")
        if self.on_road_date:
            lines.append(f"עלייה לכביש: {self.on_road_date}")
        if self.last_test_date:
            lines.append(f"טסט אחרון: {self.last_test_date.strftime('%d/%m/%Y')}")
        if self.last_test_km:
            lines.append(f"ק״מ בטסט האחרון: {self.last_test_km:,}")
        return "\n".join(lines)


# ---------- עזרי פענוח ----------

def _clean(v) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s and s.lower() not in ("null", "none", "nan") else None


def _parse_date(v) -> Optional[date]:
    s = _clean(v)
    if not s:
        return None
    s = s[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y%m%d"):
        try:
            from datetime import datetime
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_int(v) -> Optional[int]:
    s = _clean(v)
    if not s:
        return None
    try:
        return int(float(s.replace(",", "")))
    except ValueError:
        return None


def _title(s: Optional[str]) -> Optional[str]:
    """שמות יצרן/דגם במאגר באותיות גדולות באנגלית; מרככים לקריאות."""
    if not s:
        return None
    return s.title() if s.isupper() and s.isascii() else s


# במאגר שם היצרן כולל את מדינת הייצור, לעיתים קטועה: "טויוטה יפן", "סיטרואן פורטוג", "יונדאי קוריאה"
_COUNTRY_SUFFIXES = (
    "יפן", "קוריאה", "גרמניה", "צרפת", "ספרד", "פורטוגל", "פורטוג", "טורקיה", "סין", "ארה\"ב", "ארהב", "בריטניה",
    "אנגליה", "איטליה", "צ'כיה", "צכיה", "סלובקיה", "הונגריה", "פולין", "בלגיה", "הולנד", "שבדיה", "רומניה", "מקסיקו",
    "תאילנד", "הודו", "ברזיל", "דרום אפריקה", "אוסטריה", "סלובניה", "רוסיה", "אינדונזיה", "מרוקו", "וייטנאם", "טייוואן",
    "JAPAN", "KOREA", "GERMANY", "FRANCE", "SPAIN", "PORTUGAL", "TURKEY", "CHINA", "USA", "UK", "ITALY", "CZECH",
    "SLOVAKIA", "HUNGARY", "POLAND", "BELGIUM", "NETHERLANDS", "SWEDEN", "ROMANIA", "MEXICO", "THAILAND", "INDIA", "BRAZIL",
)


def clean_make(make: Optional[str]) -> Optional[str]:
    """מסיר את מדינת הייצור מסוף שם היצרן, אם נשארת לפחות מילה אחת."""
    if not make:
        return None
    words = make.split()
    for suffix in sorted(_COUNTRY_SUFFIXES, key=len, reverse=True):
        sw = suffix.split()
        if len(words) > len(sw) and [w.upper() for w in words[-len(sw):]] == [x.upper() for x in sw]:
            return " ".join(words[:-len(sw)])
    return make


def parse_record(rec: dict, source: str = "") -> VehicleInfo:
    plate = _clean(rec.get("mispar_rechev")) or ""
    make = clean_make(_clean(rec.get("tozeret_nm")))
    model = _clean(rec.get("kinuy_mishari")) or _clean(rec.get("degem_nm"))
    on_road = _clean(rec.get("moed_aliya_lakvish"))
    return VehicleInfo(
        plate=plate,
        make=_title(make),
        model=_title(model),
        trim=_clean(rec.get("ramat_gimur")),
        year=_parse_int(rec.get("shnat_yitzur")),
        test_expiry=_parse_date(rec.get("tokef_dt")),
        last_test_date=_parse_date(rec.get("mivchan_acharon_dt")),
        last_test_km=_parse_int(rec.get("kilometer_test_aharon")),
        color=_clean(rec.get("tzeva_rechev")),
        fuel=_clean(rec.get("sug_delek_nm")),
        ownership=_clean(rec.get("baalut")),
        vin=_clean(rec.get("misgeret")),
        on_road_date=on_road,
        source=source,
        raw=rec,
    )


# ---------- גישה לרשת ----------

def _fetch(resource_id: str, plate: str, timeout: float) -> list[dict]:
    params = {"resource_id": resource_id, "filters": json.dumps({"mispar_rechev": int(plate)}), "limit": 5}
    url = API_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []  # מאגר לא קיים/הוסר - ממשיכים למאגר הבא
        raise NetworkError(f"המאגר החזיר שגיאה {e.code}")
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as e:
        raise NetworkError(str(getattr(e, "reason", e)))
    except ValueError:
        raise NetworkError("תשובה לא תקינה מהמאגר")
    if not data.get("success"):
        return []
    return data.get("result", {}).get("records", []) or []


def lookup_plate(plate: str, timeout: float = 8.0, with_test_km: bool = True) -> VehicleInfo:
    """מחזיר פרטי רכב, או זורק NotFound / NetworkError."""
    digits = "".join(ch for ch in str(plate) if ch.isdigit())
    if not (5 <= len(digits) <= 8):
        raise NotFound("מספר רישוי לא תקין")
    network_errors = []
    for rid, name in RESOURCES:
        try:
            recs = _fetch(rid, digits, timeout)
        except NetworkError as e:
            network_errors.append(str(e))
            continue
        if recs:
            info = parse_record(recs[0], source=f"משרד התחבורה - {name}")
            if with_test_km:
                try:
                    trecs = _fetch(TEST_RESOURCE, digits, timeout)
                    if trecs:
                        t = parse_record(trecs[0])
                        info.last_test_km = info.last_test_km or t.last_test_km
                        info.last_test_date = info.last_test_date or t.last_test_date
                except NetworkError:
                    pass
            return info
    if network_errors and len(network_errors) == len(RESOURCES):
        raise NetworkError(network_errors[0])
    raise NotFound("הרכב לא נמצא במאגרי משרד התחבורה")


if __name__ == "__main__":  # בדיקה ידנית: python -m fleet_app.gov_lookup 1234567
    import sys
    try:
        info = lookup_plate(sys.argv[1])
        print(info.summary())
        print(info.notes_text())
        print("תוקף טסט:", info.test_expiry)
    except LookupError_ as e:
        print("לא זוהה:", e)
