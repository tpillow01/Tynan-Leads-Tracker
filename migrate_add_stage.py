# migrate_add_stage.py
from app import db, app
from sqlalchemy import text

with app.app_context():
    cols = {row[1] for row in db.session.execute(text("PRAGMA table_info(lead)"))}
    if "stage" not in cols:
        db.session.execute(text('ALTER TABLE lead ADD COLUMN "stage" VARCHAR(20)'))
        db.session.commit()
        print("Added column: stage")
    else:
        print("Column 'stage' already exists.")
