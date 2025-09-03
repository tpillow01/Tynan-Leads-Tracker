import sys, os, argparse
import pandas as pd
from datetime import datetime, date
from app import db, Lead, app

def read_table(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(path)
    if ext == ".csv":
        return pd.read_csv(path)
    raise ValueError("Use .xlsx, .xls, or .csv")

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df

def is_empty(v) -> bool:
    # Treat pandas NA/NaT, None, and empty/whitespace strings as empty
    try:
        if pd.isna(v):
            return True
    except Exception:
        pass
    if v is None:
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    return False

def coerce_text(v):
    if is_empty(v):
        return None
    s = str(v).strip()
    return s if s else None

def parse_date_safe(v):
    # Always return a native Python date or None (never NaT)
    if is_empty(v):
        return None
    # If it's already a pandas Timestamp
    if isinstance(v, pd.Timestamp):
        return v.date()
    # If it's already a Python datetime/date
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    # Try to parse strings/numbers
    try:
        ts = pd.to_datetime(v, errors="coerce")
        if pd.isna(ts):
            return None
        # ts can be pandas Timestamp
        if isinstance(ts, pd.Timestamp):
            return ts.date()
        # Fallback: if it’s a datetime/date
        if isinstance(ts, datetime):
            return ts.date()
        if isinstance(ts, date):
            return ts
    except Exception:
        return None
    return None

def row_to_kwargs(row: pd.Series) -> dict:
    cols = row.index

    def pick_text(*names):
        for n in names:
            if n in cols:
                return coerce_text(row[n])
        return None

    # Map your headers -> Lead fields (all optional)
    return dict(
        # From your sheet
        lead_date   = parse_date_safe(row.get("date")) if "date" in cols else None,
        rep         = pick_text("territory/ sales rep", "territory", "sales rep", "rep"),
        source      = pick_text("source"),
        company     = pick_text("company"),
        address     = pick_text("address"),
        city        = pick_text("city"),
        notes       = pick_text("notes", "comments", "details", "remarks"),

        # Extras if present (kept optional)
        contact_name  = pick_text("contact", "contact name", "name", "primary contact"),
        contact_email = pick_text("email", "contact email", "e-mail"),
        phone         = pick_text("phone", "phone number", "tel"),
        industry      = pick_text("industry", "segment", "sic", "naics"),
        fleet_size    = pick_text("fleet size", "trucks", "forklifts", "units"),
    )

def scrub_kwargs(kwargs: dict) -> dict:
    """Ensure no NaT/NaN/empty leaks through. Only keep model columns."""
    # 1) coerce lead_date again just in case
    if "lead_date" in kwargs:
        kwargs["lead_date"] = parse_date_safe(kwargs["lead_date"])

    # 2) turn any remaining empties into None
    for k, v in list(kwargs.items()):
        if k == "lead_date":
            # already handled
            continue
        if is_empty(v):
            kwargs[k] = None

    # 3) keep only columns that exist on the model
    model_cols = {c.key for c in Lead.__table__.columns}
    safe = {k: v for k, v in kwargs.items() if k in model_cols}
    return safe

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="Excel/CSV file to import")
    ap.add_argument("--update", action="store_true",
                    help="If a lead exists (same Company or Email), update with non-empty values from the file.")
    args = ap.parse_args()

    path = args.path
    if not os.path.exists(path):
        print(f"File not found: {path}")
        sys.exit(1)

    df = read_table(path)
    if df is None or df.empty:
        print("No rows in file.")
        sys.exit(0)
    df = normalize_columns(df)

    inserted = 0
    skipped = 0
    updated = 0

    with app.app_context():
        db.create_all()

        for _, row in df.iterrows():
            kwargs = row_to_kwargs(row)
            safe_kwargs = scrub_kwargs(kwargs)

            company = safe_kwargs.get("company")
            email = safe_kwargs.get("contact_email")

            q = Lead.query
            if company:
                q = q.filter(Lead.company == company)
            if email:
                q = q.filter(Lead.contact_email == email)

            existing = q.first() if (company or email) else None

            if existing:
                if args.update:
                    # update only with non-empty values
                    changed = False
                    for k, v in safe_kwargs.items():
                        if v is not None and getattr(existing, k) != v:
                            setattr(existing, k, v)
                            changed = True
                    if changed:
                        updated += 1
                    else:
                        skipped += 1
                else:
                    skipped += 1
            else:
                db.session.add(Lead(**safe_kwargs))
                inserted += 1

        db.session.commit()

    print(f"Imported {inserted} new, Updated {updated}, Skipped {skipped} duplicates.")

if __name__ == "__main__":
    main()
