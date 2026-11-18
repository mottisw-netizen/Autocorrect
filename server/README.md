# שרת Autocorrect

השרת מחזיק את מפתח ה-AI, כך שהלקוחות לא צריכים מפתח משלהם. כל לקוח מקבל **קוד גישה** קצר (למשל `ABCD-EFGH-JKMN`) עם מגבלת שימוש יומית.

## בחירת ספק AI והחלפה ביניהם

השרת עובד עם **שרשרת ספקים**: הוא מנסה את הראשון ברשימה, ואם הספק נופל (תקלה, עומס, מפתח לא תקין), עובר אוטומטית לבא בתור. הספקים הנתמכים:

| סוג | מה זה | מפתח (משתנה סביבה) |
|---|---|---|
| `anthropic` | Claude ישירות | `ANTHROPIC_API_KEY` |
| `openrouter` | מאות מודלים במפתח אחד (Claude, GPT, Gemini, Llama…) | `OPENROUTER_API_KEY` |
| `openai_compatible` | כל שירות עם ממשק תואם OpenAI (OpenAI, Gemini, Groq, Ollama…) | `OPENAI_API_KEY` |

**החלפה בלי הפעלה מחדש** (נכנסת לתוקף בבקשה הבאה):

```bash
python manage.py providers show                              # מה פעיל עכשיו
python manage.py providers use anthropic                     # רק Claude
python manage.py providers use openrouter:<model-id>         # רק OpenRouter, עם מודל מסוים
python manage.py providers use openrouter:<model-id>,anthropic   # OpenRouter, ו-Claude כגיבוי
python manage.py providers reset                             # חזרה להגדרה ממשתני הסביבה
```

לשליטה מלאה אפשר להעביר רשימת JSON, למשל:
```bash
python manage.py providers use '[{"type":"openai_compatible","base_url":"https://api.groq.com/openai/v1","model":"...","api_key":"env:GROQ_API_KEY"}]'
```
את המפתחות עדיף להשאיר במשתני סביבה ולהפנות אליהם עם `env:NAME`, ולא לכתוב אותם בקובץ.

**הגדרת ברירת מחדל דרך משתני סביבה:** `AI_PROVIDERS=openrouter,anthropic`, יחד עם `ANTHROPIC_MODEL`, `ANTHROPIC_EFFORT` (ברירת מחדל: `low`), `OPENROUTER_MODEL`, `OPENAI_MODEL` ו-`OPENAI_BASE_URL`. מגבלת האורך לבקשה נקבעת ב-`MAX_CHARS` (ברירת מחדל: 10000).

**הוספת ספק חדש לגמרי** דורשת מחלקה אחת ב-`autocorrect_core/providers.py`.

## העלאה לאוויר

השרת ארוז כ-Docker. אפשר להעלות אותו לכל שירות שמריץ Docker, למשל Railway, Fly.io או Render:

1. יוצרים שירות חדש מהמאגר, עם `server/Dockerfile` (נבנה משורש המאגר: `docker build -f server/Dockerfile .`).
2. מגדירים את מפתח ה-AI (למשל `ANTHROPIC_API_KEY` או `OPENROUTER_API_KEY`) ואת `AI_PROVIDERS`.
3. **מחברים דיסק קבוע (Volume) לנתיב `/data`.** שם נשמרים קודי הגישה. בלי דיסק קבוע הקודים יימחקו בכל הפעלה מחדש.

## ניהול לקוחות

```bash
python manage.py add "דנה כהן" --limit 200   # יוצר קוד חדש (200 פעולות ביום)
python manage.py list                        # כל הלקוחות והשימוש שלהם היום
python manage.py disable ABCD-EFGH-JKMN      # חוסם קוד
python manage.py enable  ABCD-EFGH-JKMN
python manage.py limit   ABCD-EFGH-JKMN 500  # משנה מגבלה
```

הפקודות רצות על השרת עצמו (בשירותי האחסון יש בדרך כלל Shell או Console).

## הרצה מקומית לבדיקה

```bash
pip install -r requirements.txt   # מתוך התיקייה server
export ANTHROPIC_API_KEY=...
uvicorn app:app --port 8000
```

## גדילה

- כל בקשה רצה במקביל לאחרות, כך שמכונה אחת מטפלת בהרבה משתמשים בו-זמנית. רוב הזמן הולך על ההמתנה ל-AI.
- קודי הגישה נשמרים ב-SQLite, וזה מתאים לשרת יחיד. כדי להריץ כמה שרתים במקביל, צריך להחליף את `db.py` במסד משותף (למשל Postgres). שאר הקוד לא משתנה.
