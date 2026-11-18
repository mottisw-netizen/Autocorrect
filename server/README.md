# שרת Autocorrect

השרת מחזיק את מפתח ה-AI, כך שהלקוחות לא צריכים מפתח משלהם. כל לקוח מקבל **קוד גישה** קצר (למשל `ABCD-EFGH-JKMN`) עם מגבלת שימוש יומית.

## בחירת ספק AI

ההגדרה נעשית במשתני סביבה, בלי לשנות קוד:

| משתנה | ערך |
|---|---|
| `PROVIDER` | `anthropic` (ברירת מחדל) או `openrouter` |
| `ANTHROPIC_API_KEY` | המפתח מ-platform.claude.com (כשהספק הוא anthropic) |
| `OPENROUTER_API_KEY` | המפתח מ-openrouter.ai (כשהספק הוא openrouter) |
| `OPENROUTER_MODEL` | מזהה מודל מ-openrouter.ai/models (חובה כשהספק הוא openrouter) |
| `MAX_CHARS` | אורך טקסט מקסימלי לבקשה (ברירת מחדל: 10000) |

## העלאה לאוויר

השרת ארוז כ-Docker. אפשר להעלות אותו לכל שירות שמריץ Docker, למשל Railway, Fly.io או Render:

1. יוצרים שירות חדש מהתיקייה `server` במאגר.
2. מגדירים את משתני הסביבה שבטבלה.
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
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
uvicorn app:app --port 8000
```
