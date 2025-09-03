# migrate_add_columns.py
from app import db, app
from sqlalchemy import text

NEW_COLS = [
    ("lead", "lead_date", "DATE"),
    ("lead", "rep", "VARCHAR(200)"),
    ("lead", "source", "VARCHAR(200)"),
    ("lead", "address", "VARCHAR(300)"),
    ("lead", "city", "VARCHAR(200)"),
]

with app.app_context():
    # check existing columns
    cols = {row[1] for row in db.session.execute(text("PRAGMA table_info(lead)"))}
    for table, col, coltype in NEW_COLS:
        if col not in cols:
            db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN "{col}" {coltype}'))
    db.session.commit()
    print("Migration complete.")
