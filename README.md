# ta-shma-to-otzaria

מייצא ביוגרפיות רבנים מ-API של תא שמע לקובץ מעורפל, ומפרסם GitHub Release חדש רק כאשר הנתונים השתנו.

## איך זה עובד

Workflow בשם **Build biographies release** רץ פעם ביום (וגם ידנית דרך Actions → Run workflow):

1. מושך את כל ערכי הרבנים מ-`api.tashma.co.il` (scope‏ `rabanan:read`): רשימה, ערך מלא לכל רב (כולל `summary` ו-`biographyShort`), תאריכי לידה ופטירה, וקולקציית התרגומים.
2. בונה JSON קנוני ודטרמיניסטי ומחשב עליו SHA-256.
3. משווה מול ה-hash של הרילייס האחרון. אם אין שינוי — לא נוצר רילייס.
4. אם יש שינוי — נוצר רילייס `bio-YYYYMMDD-HHMMSS` עם שני קבצים:
   - `biographies.tsb` — קובץ הנתונים המעורפל
   - `biographies.sha256` — ה-hash של הנתונים הגולמיים (לזיהוי שינויים בריצה הבאה)

## פורמט הקובץ `.tsb` (TSB1)

| חלק | תוכן |
|---|---|
| בייטים 0–3 | ASCII‏ `TSB1` |
| בייטים 4 ואילך | ‎`gzip(JSON-UTF8)`‎ עם XOR מול keystream |

ה-keystream הוא `SHA256(OBF_KEY)` — ‏32 בייטים החוזרים מחזורית.

פענוח (פייתון, לצורך התיעוד — המימוש באוצריא יהיה ב-Dart):

```python
import gzip, hashlib, json

raw = open("biographies.tsb", "rb").read()
assert raw[:4] == b"TSB1"
ks = hashlib.sha256(OBF_KEY.encode()).digest()
plain = gzip.decompress(bytes(b ^ ks[i % 32] for i, b in enumerate(raw[4:])))
payload = json.loads(plain)
```

מבנה ה-JSON: `{"format": "tashma-biographies", "version": 1, "entries": [...], "translation": [...]}`. כל entry מכיל `id`, `name` (שם מורכב אם קיים), `birthHebrew`/`deathHebrew`, את המסמך המלא תחת `doc`, ושדות מפוענחים מהתרגומים תחת `resolved`.

## סודות (Secrets)

| שם | תוכן |
|---|---|
| `KEY` | מפתח ה-API של תא שמע |
| `OBF_KEY` | מפתח העירפול — אותו ערך צריך להיות זמין גם בצד אוצריא לפענוח |
