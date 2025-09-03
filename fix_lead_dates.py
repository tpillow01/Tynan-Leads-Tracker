# fix_lead_dates.py
from datetime import date
from app import app, db, Lead

with app.app_context():
    fixed = 0
    for l in Lead.query.filter(Lead.lead_date.isnot(None)).all():
        y = l.lead_date.year
        if y > 2100 and y < 3000:
            new_year = 2000 + (y % 100)  # 2723 -> 2023, 2199 -> 2099
            l.lead_date = date(new_year, l.lead_date.month, l.lead_date.day)
            fixed += 1
    db.session.commit()
    print(f"Corrected {fixed} lead_date values.")
