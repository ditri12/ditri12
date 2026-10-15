#!/usr/bin/env python3
"""Build the lab-equipment manufacturers database from the research batch files.

Inputs : research/batch_*.json   (one JSON array per research batch, schema in research/SCHEMA.md)
Outputs: data/manufacturers.json  (merged, with metadata header)
         data/manufacturers.csv   (flat, UTF-8 with BOM so Excel shows Hebrew correctly)
         data/manufacturers.xlsx  (4 sheets: Manufacturers, Israel entities, Products, Summary)
         data/manufacturers.sql   (SQLite-compatible schema + inserts, 3 normalised tables)
         data/manufacturers.sqlite
         index.html               (self-contained interactive viewer, Hebrew RTL)

Run:  python3 build.py
"""
import csv
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESEARCH = ROOT / "research"
DATA = ROOT / "data"
TEMPLATE = ROOT / "template" / "index.template.html"
OUT_HTML = ROOT / "index.html"

REQUIRED_KEYS = [
    "id", "name", "aka", "hq_city", "hq_country", "parent", "ownership", "founded", "website",
    "category", "employees", "employees_year", "employees_note", "revenue_original", "revenue_usd_m",
    "revenue_year", "revenue_scope", "revenue_note", "size_basis", "top_products", "israel_presence",
    "israel_entities", "israel_note", "sources", "confidence", "confidence_note",
]
PRESENCE = ["subsidiary", "distributor", "parent_subsidiary", "none_found", "unclear", "pending"]
PRESENCE_HE = {
    "subsidiary": "חברה-בת / משרד של היצרן בישראל",
    "distributor": "מפיץ / נציג ישראלי",
    "parent_subsidiary": "נמכר דרך החברה-האם בישראל",
    "none_found": "לא נמצא ייצוג",
    "unclear": "לא ברור",
    "pending": "טרם נבדק",
}
CHECK = ["verified", "partial", "unverified", "pending"]
CHECK_HE = {
    "verified": "אומת ממקור",
    "partial": "חיפוש חלקי (ללא פתיחת אתרי היצרן/המפיץ)",
    "unverified": "ידע קודם, לא אומת מקוון",
    "pending": "טרם נבדק",
}
EMP_SCOPE = ["company", "parent", "estimate"]
OVERRIDES = RESEARCH / "overrides.json"
ENTITY_TYPE_HE = {"subsidiary": "חברה-בת", "distributor": "מפיץ", "service": "שירות"}


def load_rows():
    rows = []
    files = sorted(RESEARCH.glob("batch_*.json"))
    if not files:
        sys.exit("no research/batch_*.json files found")
    for f in files:
        with open(f, encoding="utf-8") as fh:
            batch = json.load(fh)
        if not isinstance(batch, list):
            sys.exit(f"{f.name}: expected a JSON array")
        rows.extend(batch)
    rows.sort(key=lambda r: r["id"])
    if OVERRIDES.exists():
        with open(OVERRIDES, encoding="utf-8") as fh:
            overrides = json.load(fh)
        by_id = {r["id"]: r for r in rows}
        for key, patch in overrides.items():
            if key.startswith("_"):
                continue
            target = by_id.get(int(key))
            if target is None:
                sys.exit(f"override for unknown id {key}")
            for k, v in patch.items():
                if k == "sources":
                    target["sources"] = list(dict.fromkeys((target.get("sources") or []) + list(v)))
                else:
                    target[k] = v
    prefixes = {
        "pending": "טרם נבדק — ממתין לסבב המחקר הבא.",
        "partial": "חיפוש רשת בלבד; דפי ״מפיצים״ של היצרן ואתרי המפיצים לא נפתחו (חסימת רשת).",
        "unverified": "על בסיס ידע קודם; לא אומת מקוון בסבב זה.",
    }
    for r in rows:
        r.setdefault("employees_scope", "company")
        if "israel_check" not in r:
            p = r.get("israel_presence")
            r["israel_check"] = "pending" if p == "pending" else ("partial" if p in ("none_found", "unclear") else "verified")
        pre = prefixes.get(r["israel_check"])
        note = (r.get("israel_note") or "").strip()
        if pre and not note.startswith(pre):
            r["israel_note"] = (pre + " " + note).strip()
    problems = []
    ids = [r["id"] for r in rows]
    if ids != list(range(1, len(rows) + 1)):
        problems.append(f"ids are not 1..{len(rows)}: {ids}")
    for r in rows:
        missing = [k for k in REQUIRED_KEYS if k not in r]
        if missing:
            problems.append(f"{r.get('name')}: missing keys {missing}")
        if r.get("israel_presence") not in PRESENCE:
            problems.append(f"{r.get('name')}: bad israel_presence {r.get('israel_presence')!r}")
        if len(r.get("top_products") or []) != 3:
            problems.append(f"{r.get('name')}: top_products must have 3 items")
        for e in r.get("israel_entities") or []:
            if e.get("type") not in ENTITY_TYPE_HE:
                problems.append(f"{r.get('name')}: bad entity type {e.get('type')!r}")
        if r.get("revenue_usd_m") is not None and not isinstance(r["revenue_usd_m"], (int, float)):
            problems.append(f"{r.get('name')}: revenue_usd_m must be a number or null")
        if r.get("employees") is not None and not isinstance(r["employees"], int):
            problems.append(f"{r.get('name')}: employees must be an integer or null")
        if r.get("israel_check") not in CHECK:
            problems.append(f"{r.get('name')}: bad israel_check {r.get('israel_check')!r}")
        if r.get("employees_scope") not in EMP_SCOPE:
            problems.append(f"{r.get('name')}: bad employees_scope {r.get('employees_scope')!r}")
    if problems:
        sys.exit("validation problems:\n  " + "\n  ".join(problems))
    return rows


def fmt_products(r):
    return " | ".join(f"{p['name']} — {p['desc']}" for p in r["top_products"])


def fmt_entities(r):
    out = []
    for e in r["israel_entities"]:
        label = e["name"]
        if e.get("name_he"):
            label += f" ({e['name_he']})"
        label += f" [{ENTITY_TYPE_HE.get(e['type'], e['type'])}"
        if e.get("scope"):
            label += f"; {e['scope']}"
        label += "]"
        out.append(label)
    return " | ".join(out)


def write_json(rows, generated):
    DATA.mkdir(exist_ok=True)
    doc = {
        "title": "Top 100 laboratory-equipment manufacturers — size, flagship products, Israeli representation",
        "title_he": "100 יצרני ציוד המעבדה המובילים בעולם — גודל, מוצרים מובילים וייצוג בישראל",
        "generated": generated,
        "count": len(rows),
        "fx_note": "revenue_usd_m converted at approximate 2025 average rates (EUR 1.10, GBP 1.30, CHF 1.17, JPY 0.0067, CNY 0.139, SEK 0.098, SGD 0.76)",
        "israel_presence_values": PRESENCE_HE,
        "israel_check_values": CHECK_HE,
        "employees_scope_values": {"company": "headcount of the listed company", "parent": "parent group headcount", "estimate": "approximate / unverified"},
        "manufacturers": rows,
    }
    with open(DATA / "manufacturers.json", "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)


CSV_COLUMNS = [
    ("id", "#"), ("name", "יצרן / Manufacturer"), ("aka", "מותגים / Brands"), ("hq_city", "עיר / HQ city"),
    ("hq_country", "מדינה / Country"), ("parent", "חברת-אם / Parent"), ("ownership", "בעלות / Ownership"),
    ("founded", "שנת ייסוד / Founded"), ("website", "אתר / Website"), ("category", "קטגוריה / Category"),
    ("employees", "עובדים / Employees"), ("employees_year", "שנת נתון עובדים / Employees year"),
    ("employees_scope", "היקף נתון העובדים / Employees scope"),
    ("employees_note", "הערת עובדים / Employees note"), ("revenue_original", "הכנסות (מטבע מקורי) / Revenue"),
    ("revenue_usd_m", "הכנסות מיליוני $ / Revenue USD M"), ("revenue_year", "שנת כספים / Fiscal year"),
    ("revenue_scope", "היקף ההכנסות / Revenue scope"), ("revenue_note", "הערת הכנסות / Revenue note"),
    ("size_basis", "בסיס הנתונים / Size basis"), ("product_1", "מוצר מוביל 1 / Top product 1"),
    ("product_2", "מוצר מוביל 2 / Top product 2"), ("product_3", "מוצר מוביל 3 / Top product 3"),
    ("israel_presence", "ייצוג בישראל / Israel presence"), ("israel_presence_he", "ייצוג בישראל (עברית)"),
    ("israel_check", "סטטוס אימות / Verification"), ("israel_check_he", "סטטוס אימות (עברית)"),
    ("israel_entities", "נציגים / מפיצים בישראל / Israeli entities"), ("israel_note", "הערת ישראל / Israel note"),
    ("confidence", "רמת ודאות / Confidence"), ("confidence_note", "הערת ודאות / Confidence note"),
    ("sources", "מקורות / Sources"),
]


def flat_row(r):
    d = {k: r.get(k) for k in REQUIRED_KEYS}
    for i, p in enumerate(r["top_products"], 1):
        d[f"product_{i}"] = f"{p['name']} — {p['desc']}"
    d["israel_presence_he"] = PRESENCE_HE[r["israel_presence"]]
    d["israel_check"] = r["israel_check"]
    d["israel_check_he"] = CHECK_HE[r["israel_check"]]
    d["employees_scope"] = r["employees_scope"]
    d["israel_entities"] = fmt_entities(r)
    d["sources"] = " ; ".join(r["sources"])
    return d


def write_csv(rows):
    with open(DATA / "manufacturers.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([h for _, h in CSV_COLUMNS])
        for r in rows:
            d = flat_row(r)
            w.writerow(["" if d.get(k) is None else d.get(k) for k, _ in CSV_COLUMNS])


def write_xlsx(rows, generated):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    base = Font(name="Arial", size=10)
    bold = Font(name="Arial", size=10, bold=True)
    head_font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="0B7285")
    wrap = Alignment(wrap_text=True, vertical="top")

    # --- Sheet 1: Manufacturers (one row per company) ---
    ws = wb.active
    ws.title = "Manufacturers"
    ws.sheet_view.rightToLeft = True
    widths = {
        "id": 5, "name": 28, "aka": 30, "hq_city": 18, "hq_country": 12, "parent": 18, "ownership": 24,
        "founded": 9, "website": 28, "category": 30, "employees": 11, "employees_year": 9,
        "employees_note": 32, "employees_scope": 10, "israel_check": 11, "israel_check_he": 24, "revenue_original": 20, "revenue_usd_m": 12, "revenue_year": 12,
        "revenue_scope": 11, "revenue_note": 32, "size_basis": 10, "product_1": 36, "product_2": 36,
        "product_3": 36, "israel_presence": 16, "israel_presence_he": 26, "israel_entities": 48,
        "israel_note": 50, "confidence": 10, "confidence_note": 32, "sources": 60,
    }
    for c, (key, header) in enumerate(CSV_COLUMNS, 1):
        cell = ws.cell(row=1, column=c, value=header)
        cell.font = head_font
        cell.fill = head_fill
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(c)].width = widths.get(key, 18)
    for i, r in enumerate(rows, 2):
        d = flat_row(r)
        for c, (key, _) in enumerate(CSV_COLUMNS, 1):
            v = d.get(key)
            cell = ws.cell(row=i, column=c, value=v)
            cell.font = base
            cell.alignment = wrap
            if key in ("employees", "revenue_usd_m") and isinstance(v, (int, float)):
                cell.number_format = "#,##0"
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(CSV_COLUMNS))}{len(rows) + 1}"
    ws.row_dimensions[1].height = 32

    # --- Sheet 2: Israel entities (one row per Israeli partner) ---
    ws2 = wb.create_sheet("Israel entities")
    ws2.sheet_view.rightToLeft = True
    h2 = ["# יצרן", "יצרן / Manufacturer", "ייצוג בישראל / Presence", "גוף ישראלי / Israeli entity",
          "שם בעברית / Hebrew name", "סוג / Type", "תחום / Scope", "אתר / Website", "מקור / Source"]
    for c, h in enumerate(h2, 1):
        cell = ws2.cell(row=1, column=c, value=h)
        cell.font, cell.fill = head_font, head_fill
    for w, c in zip([7, 28, 18, 34, 20, 12, 40, 30, 60], range(1, 10)):
        ws2.column_dimensions[get_column_letter(c)].width = w
    row_i = 2
    for r in rows:
        if not r["israel_entities"]:
            vals = [r["id"], r["name"], r["israel_presence"], "—", "", "", "", "", ""]
            for c, v in enumerate(vals, 1):
                cell = ws2.cell(row=row_i, column=c, value=v)
                cell.font, cell.alignment = base, wrap
            row_i += 1
            continue
        for e in r["israel_entities"]:
            vals = [r["id"], r["name"], r["israel_presence"], e["name"], e.get("name_he", ""),
                    ENTITY_TYPE_HE.get(e["type"], e["type"]), e.get("scope", ""), e.get("website", ""),
                    e.get("source", "")]
            for c, v in enumerate(vals, 1):
                cell = ws2.cell(row=row_i, column=c, value=v)
                cell.font, cell.alignment = base, wrap
            row_i += 1
    ws2.freeze_panes = "C2"
    ws2.auto_filter.ref = f"A1:I{row_i - 1}"

    # --- Sheet 3: Products (one row per flagship product) ---
    ws3 = wb.create_sheet("Products")
    ws3.sheet_view.rightToLeft = True
    h3 = ["# יצרן", "יצרן / Manufacturer", "מס׳ / Rank", "מוצר / Product", "תיאור / Description"]
    for c, h in enumerate(h3, 1):
        cell = ws3.cell(row=1, column=c, value=h)
        cell.font, cell.fill = head_font, head_fill
    for w, c in zip([7, 28, 7, 34, 50], range(1, 6)):
        ws3.column_dimensions[get_column_letter(c)].width = w
    row_i = 2
    for r in rows:
        for n, p in enumerate(r["top_products"], 1):
            for c, v in enumerate([r["id"], r["name"], n, p["name"], p["desc"]], 1):
                cell = ws3.cell(row=row_i, column=c, value=v)
                cell.font, cell.alignment = base, wrap
            row_i += 1
    ws3.freeze_panes = "C2"
    ws3.auto_filter.ref = f"A1:E{row_i - 1}"

    # --- Sheet 4: Summary (live formulas over the Manufacturers sheet) ---
    ws4 = wb.create_sheet("Summary")
    ws4.sheet_view.rightToLeft = True
    ws4.column_dimensions["A"].width = 44
    ws4.column_dimensions["B"].width = 14
    ws4.column_dimensions["C"].width = 60
    ws4["A1"] = "סיכום / Summary"
    ws4["A1"].font = Font(name="Arial", size=12, bold=True)
    ws4["A2"] = f"נוצר / Generated: {generated}"
    ws4["A2"].font = base
    n = len(rows) + 1
    col_presence = get_column_letter([k for k, _ in CSV_COLUMNS].index("israel_presence") + 1)
    col_emp = get_column_letter([k for k, _ in CSV_COLUMNS].index("employees") + 1)
    col_rev = get_column_letter([k for k, _ in CSV_COLUMNS].index("revenue_usd_m") + 1)
    col_conf = get_column_letter([k for k, _ in CSV_COLUMNS].index("confidence") + 1)
    lines = [
        ("סה״כ יצרנים / Manufacturers", f"=COUNTA(Manufacturers!A2:A{n})", ""),
    ]
    for key, he in PRESENCE_HE.items():
        lines.append((f"{he} ({key})", f'=COUNTIF(Manufacturers!{col_presence}2:{col_presence}{n},"{key}")', ""))
    col_check = get_column_letter([k for k, _ in CSV_COLUMNS].index("israel_check") + 1)
    for key, he in CHECK_HE.items():
        lines.append((f"אימות: {he} ({key})", f'=COUNTIF(Manufacturers!{col_check}2:{col_check}{n},"{key}")', ""))
    lines += [
        ("יצרנים עם ייצוג כלשהו בישראל / Any Israeli channel",
         f'=COUNTIF(Manufacturers!{col_presence}2:{col_presence}{n},"subsidiary")'
         f'+COUNTIF(Manufacturers!{col_presence}2:{col_presence}{n},"distributor")'
         f'+COUNTIF(Manufacturers!{col_presence}2:{col_presence}{n},"parent_subsidiary")', ""),
        ("סה״כ עובדים (היכן שדווח) / Employees total", f"=SUM(Manufacturers!{col_emp}2:{col_emp}{n})",
         "sum of reported/estimated headcounts; parent-level figures inflate the total"),
        ("חציון עובדים / Median employees", f"=MEDIAN(Manufacturers!{col_emp}2:{col_emp}{n})", ""),
        ("סה״כ הכנסות מיליוני $ / Revenue USD M total", f"=SUM(Manufacturers!{col_rev}2:{col_rev}{n})",
         "mixes company, segment, parent and estimated figures — indicative only"),
        ("חציון הכנסות מיליוני $ / Median revenue USD M", f"=MEDIAN(Manufacturers!{col_rev}2:{col_rev}{n})", ""),
        ("רמת ודאות גבוהה / High confidence", f'=COUNTIF(Manufacturers!{col_conf}2:{col_conf}{n},"high")', ""),
        ("רמת ודאות בינונית / Medium confidence", f'=COUNTIF(Manufacturers!{col_conf}2:{col_conf}{n},"medium")', ""),
        ("רמת ודאות נמוכה / Low confidence", f'=COUNTIF(Manufacturers!{col_conf}2:{col_conf}{n},"low")', ""),
    ]
    for i, (label, formula, note) in enumerate(lines, 4):
        ws4.cell(row=i, column=1, value=label).font = bold
        c = ws4.cell(row=i, column=2, value=formula)
        c.font = base
        c.number_format = "#,##0"
        ws4.cell(row=i, column=3, value=note).font = Font(name="Arial", size=9, italic=True)
    note_row = 4 + len(lines) + 1
    notes = [
        "הערות / Notes:",
        "• revenue_usd_m: converted at approximate 2025 average FX rates (EUR 1.10, GBP 1.30, CHF 1.17, JPY 0.0067, CNY 0.139, SEK 0.098, SGD 0.76).",
        "• size_basis = estimate: private company, figure is a public estimate (see revenue_note / employees_note).",
        "• revenue_scope = parent / segment: figure is the parent group's or a business segment's, not the listed brand alone.",
        "• israel_presence = none_found: no public evidence of an Israeli channel was found in the research — it does not prove there is none.",
        "• Israeli representation changes often; verify with the manufacturer before relying on it commercially.",
    ]
    for i, t in enumerate(notes):
        ws4.cell(row=note_row + i, column=1, value=t).font = bold if i == 0 else base
    wb.save(DATA / "manufacturers.xlsx")


def sql_quote(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


SCHEMA = """\
CREATE TABLE manufacturers (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  aka TEXT,
  hq_city TEXT,
  hq_country TEXT,
  parent TEXT,
  ownership TEXT,
  founded INTEGER,
  website TEXT,
  category TEXT,
  employees INTEGER,
  employees_year INTEGER,
  employees_note TEXT,
  employees_scope TEXT,        -- company | parent | estimate
  revenue_original TEXT,
  revenue_usd_m REAL,
  revenue_year TEXT,
  revenue_scope TEXT,          -- company | segment | parent | estimate
  revenue_note TEXT,
  size_basis TEXT,             -- reported | estimate | mixed
  israel_presence TEXT,        -- subsidiary | distributor | parent_subsidiary | none_found | unclear
  israel_check TEXT,           -- verified | partial | unverified | pending
  israel_note TEXT,
  confidence TEXT,             -- high | medium | low
  confidence_note TEXT
);
CREATE TABLE products (
  manufacturer_id INTEGER NOT NULL REFERENCES manufacturers(id),
  rank INTEGER NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  PRIMARY KEY (manufacturer_id, rank)
);
CREATE TABLE israel_entities (
  id INTEGER PRIMARY KEY,
  manufacturer_id INTEGER NOT NULL REFERENCES manufacturers(id),
  name TEXT NOT NULL,
  name_he TEXT,
  type TEXT,                   -- subsidiary | distributor | service
  scope TEXT,
  website TEXT,
  source TEXT
);
CREATE TABLE sources (
  manufacturer_id INTEGER NOT NULL REFERENCES manufacturers(id),
  url TEXT NOT NULL
);
"""


def write_sql_and_sqlite(rows, generated):
    stmts = [f"-- Top 100 laboratory-equipment manufacturers; generated {generated}", "BEGIN;", SCHEMA.rstrip()]
    cols = [k for k in REQUIRED_KEYS if k not in ("top_products", "israel_entities", "sources")] + ["employees_scope", "israel_check"]
    ent_id = 0
    for r in rows:
        stmts.append(
            f"INSERT INTO manufacturers ({', '.join(cols)}) VALUES ({', '.join(sql_quote(r.get(c)) for c in cols)});"
        )
        for n, p in enumerate(r["top_products"], 1):
            stmts.append(
                "INSERT INTO products (manufacturer_id, rank, name, description) VALUES "
                f"({r['id']}, {n}, {sql_quote(p['name'])}, {sql_quote(p['desc'])});"
            )
        for e in r["israel_entities"]:
            ent_id += 1
            stmts.append(
                "INSERT INTO israel_entities (id, manufacturer_id, name, name_he, type, scope, website, source) VALUES "
                f"({ent_id}, {r['id']}, {sql_quote(e['name'])}, {sql_quote(e.get('name_he'))}, {sql_quote(e['type'])}, "
                f"{sql_quote(e.get('scope'))}, {sql_quote(e.get('website'))}, {sql_quote(e.get('source'))});"
            )
        for u in r["sources"]:
            stmts.append(f"INSERT INTO sources (manufacturer_id, url) VALUES ({r['id']}, {sql_quote(u)});")
    stmts.append("COMMIT;")
    sql = "\n".join(stmts) + "\n"
    (DATA / "manufacturers.sql").write_text(sql, encoding="utf-8")
    db_path = DATA / "manufacturers.sqlite"
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.executescript(sql)
    con.commit()
    con.close()


def write_html(rows, generated):
    tpl = TEMPLATE.read_text(encoding="utf-8")
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = (tpl.replace("__DATA_JSON__", payload)
               .replace("__GENERATED__", generated)
               .replace("__COUNT__", str(len(rows))))
    OUT_HTML.write_text(html, encoding="utf-8")


def main():
    generated = dt.date.today().isoformat()
    rows = load_rows()
    write_json(rows, generated)
    write_csv(rows)
    write_xlsx(rows, generated)
    write_sql_and_sqlite(rows, generated)
    write_html(rows, generated)
    counts = {p: sum(1 for r in rows if r["israel_presence"] == p) for p in PRESENCE}
    print(f"built {len(rows)} manufacturers -> data/ + index.html ; israel_presence counts: {counts}")


if __name__ == "__main__":
    main()
