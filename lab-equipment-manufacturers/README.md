# מאגר יצרני ציוד מעבדה — 100 היצרנים המובילים בעולם

מאגר נתונים של 100 יצרני ציוד ומכשור המעבדה המובילים בעולם, עם:

- **גודל החברה** — מספר עובדים והכנסות שנתיות (במטבע המקורי ובהמרה לדולר), כולל שנת הנתון והיקפו (חברה / סגמנט / חברת-אם / הערכה).
- **3 מוצרים מובילים** לכל יצרן.
- **ייצוג בישראל** — האם ליצרן חברה-בת או משרד בישראל, ומי המפיצים / הנציגים הישראליים שמוכרים את מוצריו (כולל תחום הייצוג, אתר ומקור).
- **מקורות ורמת ודאות** לכל רשומה.

הנתונים נאספו ב-15.10.2026 מדוחות שנתיים, אתרי היצרנים, אתרי המפיצים הישראליים ועיתונות מקצועית.

## הקבצים

| קובץ | מה יש בו |
|---|---|
| [`index.html`](index.html) | דף צפייה אינטראקטיבי (עברית, RTL): חיפוש חופשי, סינון לפי ייצוג בישראל / קטגוריה / מדינה / גודל, מיון, פתיחת שורה לפרטים ומקורות, והעתקת הטבלה המסוננת לאקסל. קובץ עצמאי — מורידים ופותחים בדפדפן. |
| [`data/manufacturers.xlsx`](data/manufacturers.xlsx) | אקסל עם 4 גיליונות: `Manufacturers` (שורה ליצרן), `Israel entities` (שורה לכל נציג ישראלי), `Products` (שורה לכל מוצר), `Summary` (נוסחאות סיכום חיות). |
| [`data/manufacturers.csv`](data/manufacturers.csv) | אותה טבלה שטוחה, UTF-8 עם BOM (נפתח נכון באקסל בעברית). |
| [`data/manufacturers.json`](data/manufacturers.json) | הנתונים המלאים והמובנים (מוצרים ונציגים כרשימות), עם כותרת מטא-דאטה. |
| [`data/manufacturers.sqlite`](data/manufacturers.sqlite) / [`data/manufacturers.sql`](data/manufacturers.sql) | בסיס נתונים SQLite מנורמל (טבלאות `manufacturers`, `products`, `israel_entities`, `sources`) וסקריפט ה-SQL שיוצר אותו. |
| [`research/`](research/) | קובצי המחקר הגולמיים (10 קבצים × 10 יצרנים) וה-[סכמה](research/SCHEMA.md). |
| [`build.py`](build.py) | סקריפט הבנייה: ממזג את קובצי המחקר ומייצר את כל הפלטים מחדש (`python3 build.py`). |

## ערכי השדה "ייצוג בישראל"

| ערך | פירוש |
|---|---|
| `subsidiary` | ליצרן חברה-בת / משרד משלו בישראל (לעיתים לצד מפיצים). |
| `distributor` | המוצרים נמכרים בישראל דרך מפיץ / נציג ישראלי עצמאי. |
| `parent_subsidiary` | נמכר בישראל דרך החברה-הבת הישראלית של קבוצת-האם. |
| `none_found` | לא נמצאה עדות פומבית לערוץ מכירה ישראלי. **זו לא הוכחה שאין כזה.** |
| `unclear` | עדויות סותרות או מיושנות — ראו `israel_note`. |

## הסתייגויות

- נציגויות מתחלפות לעיתים קרובות. לפני החלטה מסחרית יש לאמת מול היצרן או המפיץ.
- הכנסות הומרו לדולר לפי שערי 2025 מקורבים (אירו 1.10, ליש״ט 1.30, פר״ש 1.17, ין 0.0067, יואן 0.139, כתר שוודי 0.098, דולר סינגפורי 0.76).
- לחברות פרטיות רבות (בעיקר יצרנים גרמניים ושווייצריים בבעלות משפחתית) אין נתונים רשמיים; הנתון מסומן `estimate` והמקור מצוין בהערה.
- לחברות-בת וחטיבות (למשל חברות דנהר, חטיבות הדיאגנוסטיקה של רוש / אבוט / סימנס) הנתון הוא של הסגמנט או של קבוצת-האם, ומסומן בהתאם.

---

## English summary

A database of the world's 100 leading laboratory-equipment manufacturers: company size (employees, annual revenue), three flagship products each, and whether/through whom their products are sold in Israel (own subsidiary, Israeli distributors with scope, website and source), plus sources and a confidence rating per record. Collected 2026-10-15. Deliverables: interactive Hebrew viewer (`index.html`), Excel (4 sheets), CSV, JSON, SQLite (+ SQL), raw research files and the build script. "none_found" means no public evidence of an Israeli channel was found, not proof of absence.
