"""בדיקה חיה של מאגר משרד התחבורה (רצה ב-CI, שם יש גישה לאינטרנט):
מושך רשומה כלשהי מהמאגר, מריץ עליה זיהוי לפי מספר רכב ומדפיס את התוצאה."""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from fleet_app import gov_lookup  # noqa: E402

rid = gov_lookup.RESOURCES[0][0]
url = f"{gov_lookup.API_URL}?resource_id={rid}&limit=1"
with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": gov_lookup.USER_AGENT}), timeout=20) as r:
    data = json.loads(r.read().decode("utf-8"))
rec = data["result"]["records"][0]
print("FIELDS:", sorted(rec.keys()))
print("SAMPLE:", json.dumps(rec, ensure_ascii=False))
plate = str(rec["mispar_rechev"])
info = gov_lookup.lookup_plate(plate)
print("LOOKUP:", plate, "->", info.summary())
print("TEST EXPIRY:", info.test_expiry, "| LAST TEST KM:", info.last_test_km, "| SOURCE:", info.source)
print("NOTES:", info.notes_text().replace("\n", " | "))
for rid2, name in gov_lookup.RESOURCES[1:]:
    try:
        recs = gov_lookup._fetch(rid2, "1", 20)
        print("RESOURCE OK:", name, rid2)
    except Exception as e:  # noqa: BLE001
        print("RESOURCE FAIL:", name, rid2, e)
try:
    recs = gov_lookup._fetch(gov_lookup.TEST_RESOURCE, plate, 20)
    print("TEST RESOURCE:", recs[:1])
except Exception as e:  # noqa: BLE001
    print("TEST RESOURCE FAIL:", e)
