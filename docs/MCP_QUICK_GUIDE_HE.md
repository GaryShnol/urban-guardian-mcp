# איך ה-MCP Urban Guardian עובד — הסבר קצר

**Urban Guardian** הוא שרת MCP (Model Context Protocol) שמספק כלים לניתוח תכנוני ונדל"ני בישראל — לפי כתובת או קואורדינטות.

---

## איך זה עובד (בגדול)

1. **מכניסים** כתובת (או קואורדינטות lat/lon).
2. **שלב 1** — גיאוקוד: המרת כתובת לנקודה על המפה (lat, lon).
3. **שלב 2** — נתונים תכנוניים: גוש/חלקה, תוכניות (תב"ע), היתרי בנייה בסביבה.
4. **שלב 3** — דו"ח: ציון Guardian (0–100), סיכום סיכונים והזדמנויות.

הלקוח (אפליקציה או AI כמו קלאוד) קורא לכלים דרך MCP או דרך REST API — אותה לוגיקה בשני הממשקים.

---

## הפעולות (הכלים)

| כלי | קלט | פלט | תיאור קצר |
|-----|-----|-----|------------|
| **geocode_address** | כתובת (מחרוזת) | lat, lon, display_name | המרת כתובת ישראלית לקואורדינטות. GovMap ראשון; אם לא זמין — Nominatim (OSM). אם לא נמצא — שגיאה + הצעות "האם התכוונת ל־?". |
| **get_cadastral_data** | latitude, longitude | gush, helka, note | גוש וחלקה בנקודה (זהות תכנונית / טאבו). נתונים מ־GovMap (שכבת חלקות/גושים). |
| **get_urban_plans** | latitude, longitude | plans, permits, note | תוכניות (תב"ע) והיתרי בנייה בנקודה/סביבה. נתונים מ־GovMap (רצף מגרשים). |
| **get_spatial_mining** | lat, lon, (אופציונלי: רדיוסים) | within_100m, within_500m, within_1000m | אותם תוכניות והיתרים במעגלים: 100m, 500m, 1000m. מתאים לשאלות "מה יש ליד". |
| **get_multi_radius_search** | latitude, longitude | bedroom_50m, permits_100m, lifestyle_300m, plans_500m, value_800m + summary | חיפוש לפי מעגלי השפעה: 50m (מיידי), 100m (היתרים), 300m (שכונה), 500m (תב"ע), 800m (תשתית). כולל דגלים (למשל: יש היתר ב־100m?). |
| **generate_guardian_report** | lat, lon, (כתובת, שפה) | guardian_score, consult, report, risks, opportunities | **מדד Guardian** — ניתוח משוקלל: יתרונות (תועלת), סיכונים, סטטוס תכנוני. מחזיר ציון 0–100, טקסט consult ודו"ח, רשימות risks ו־opportunities. |

---

## זרימה טיפוסית

1. **geocode_address**("הכתובת") → מקבלים `latitude`, `longitude`.
2. **get_cadastral_data**(lat, lon) → גוש, חלקה (אופציונלי לזהות משפטית).
3. **get_urban_plans**(lat, lon) או **get_multi_radius_search**(lat, lon) → תוכניות והיתרים בסביבה.
4. **generate_guardian_report**(lat, lon, address=..., language="he"|"en") → ציון, consult ודו"ח מוכן.

אפשר גם לקפוץ ישר ל־**generate_guardian_report** אם כבר יש קואורדינטות — הוא מריץ בפנימיות גוש/חלקה + חיפוש רב־רדיאוס ומחשב את הציון.

---

## מקורות נתונים

- **גיאוקוד:** GovMap (ברירת מחדל), Nominatim (גיבוי).
- **גוש/חלקה, תוכניות, היתרים:** GovMap (WFS / שכבות גיאו).

הכלים מחזירים JSON; שפת הדו"ח ב־generate_guardian_report נבחרת עם `language: "he"` או `"en"`.
