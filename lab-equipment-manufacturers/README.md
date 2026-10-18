# ספקי ציוד מעבדה – מאגר נתונים | Laboratory suppliers database

מאגר של **כל הספקים והיצרנים** המופיעים בדפי הספקים/המותגים של שלושה מפיצי ציוד מעבדה גדולים:

| קטלוג | דף המקור | ספקים |
|---|---|---|
| Dutscher (צרפת) | https://www.dutscher.com/brands (+ מותגי-הבית בדף private-label) | 227 |
| Thomas Scientific (ארה"ב) | https://www.thomassci.com/browse-by/suppliers | 1,006 |
| Quartzy (ארה"ב) | https://www.quartzy.com/suppliers | 377 |
| Quartzy – ספקים חדשים | https://info.quartzy.com/new-suppliers | 26 |

לאחר איחוד שמות זהים: **1,381 ספקים ייחודיים** (209 מופיעים ביותר מקטלוג אחד).

לכל ספק נאספים, ככל שקיימים מקורות פומביים: אתר, מדינה, חברת-אם, מספר עובדים והכנסות (עם שנת הנתון והמקור),
מוצרים מובילים/מייצגים, **ייצוג בישראל** (חברה-בת / מפיץ, עם פרטי קשר של הנציג ושנת הראיה) ופרטי קשר של היצרן.

## קבצים

| קובץ | תוכן |
|---|---|
| `index.html` | מציג אינטראקטיבי בעברית (RTL): חיפוש, סינון לפי קטלוג/מדינה/גודל/ייצוג, פירוט לכל ספק |
| `data/suppliers.json` | הנתונים המלאים (כולל אינדקס הנציגים הישראליים) |
| `data/suppliers.csv` | טבלה שטוחה (UTF-8 BOM, נפתח באקסל) |
| `data/suppliers.xlsx` | גיליונות: Suppliers, Israel entities, Products, By Israeli entity, Summary |
| `data/suppliers.sql`, `data/suppliers.sqlite` | סכמה יחסית: suppliers, products, israel_entities, sources |
| `research/catalog_suppliers.json` | רשימת-האב: שם, וריאנטים, הקטלוגים שבהם מופיע |
| `research/enrich/*.json` | שכבות העשרה (מחקר קודם מאומת, Wikidata/Clearbit, התאמות למפיצים ישראליים, מוצרים, אנשי קשר) |
| `research/israel/` | רשם המפיצים הישראליים ופרטי הקשר שלהם |
| `research/sources/` | דפי המקור שנסרקו (HTML/טקסט/קישורים) עם index.json לכל סריקה |
| `crawl/` | כלי הסריקה והעיבוד (ראו להלן) |
| `build.py` | בונה את כל הפלטים מרשימת-האב ושכבות ההעשרה |

## איך זה נבנה

סביבת העבודה חסומה לגלישה ישירה, ולכן הדפים נשלפים ב-GitHub Actions (`.github/workflows/fetch-pages.yml`, `run-script.yml`)
ומוחזרים לענף כקבצים:

1. `crawl/fetch.py` – שליפת דפים (HTTP או דפדפן Playwright; Thomas Scientific דורש Firefox בגלל Cloudflare), כולל מעקב קישורים ברמה אחת.
2. `crawl/parse_lists.py` – פירסור דפי הרשימות לרשימת-האב `research/catalog_suppliers.json`.
3. `crawl/resolve_companies.py` – זיהוי החברה ב-Wikidata (אתר, מדינה, מטה, חברת-אם, עובדים, הכנסות) וב-Clearbit (דומיין).
4. `crawl/match_israel.py` – סריקת אתרי מפיצים ישראליים והתאמת שמות הספקים לדפי המותגים שלהם.
5. `crawl/import_prior.py` – ייבוא המחקר המאומת מהמאגר הקודם (100 היצרנים המובילים) לספקים החופפים.
6. `build.py` – מיזוג השכבות ובניית JSON / CSV / XLSX / SQL / SQLite / HTML.

## סטטוסים ושדות מפתח

* `israel_presence`: `subsidiary` (חברה-בת), `distributor` (מפיץ/נציג), `parent_subsidiary` (דרך חברת-האם), `none_found` (נבדק ולא נמצא),
  `unclear`, `not_found_in_sweep` (לא נמצא בסריקת המפיצים – אינו הוכחה להיעדר ייצוג), `pending`.
* `israel_check`: `verified` (אומת מול אתר היצרן/המפיץ), `partial`, `sweep` (סריקת אתרי מפיצים בלבד).
* לכל נציג ישראלי: `match_basis` (`prior_research` / `distributor_site_sweep`), `match_confidence` (`exact` / `contained`), `evidence_year`, `status`.
* גודל: `employees.{value,year,scope,source}`, `revenue.{usd_m,original,year,scope,source}`; `source` ∈ prior / wikidata / manual.
* `website_source`: prior / wikidata / clearbit / manual; `website_candidate` – דומיין שזוהה אוטומטית וטרם אומת.

---

## English summary

Database of every supplier/brand listed on the supplier pages of Dutscher, Thomas Scientific and Quartzy
(1,381 distinct suppliers after name normalisation), enriched with website, country, parent, employees, revenue,
representative products, **Israeli representation** (subsidiary / distributor with contacts and evidence year) and
manufacturer contacts. Pages are fetched through GitHub Actions because the build container has no direct web access.
Outputs: `index.html` (Hebrew RTL viewer), `data/suppliers.{json,csv,xlsx,sql,sqlite}`.
