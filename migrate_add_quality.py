# migrate_add_quality.py
from app import db, app
from sqlalchemy import text

with app.app_context():
    cols = {row[1] for row in db.session.execute(text("PRAGMA table_info(lead)"))}
    if "quality" not in cols:
        db.session.execute(text('ALTER TABLE lead ADD COLUMN "quality" VARCHAR(20)'))
        db.session.commit()
        print("Added column: quality")
    else:
        print("Column 'quality' already exists.")
