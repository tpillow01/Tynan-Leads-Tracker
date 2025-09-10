import os
import re
from datetime import datetime, date
from collections import Counter

from flask import (
    Flask, render_template, request, redirect, url_for, flash, abort, jsonify
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, func

# --------------------
# Flask Config
# --------------------
app = Flask(__name__)
app.secret_key = os.getenv("APP_SECRET_KEY", "dev-insecure")

db_url = os.getenv("DATABASE_URL")  # Render will set this for Postgres
if db_url:
    # Normalize for SQLAlchemy and enforce SSL
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://")
    if "sslmode=" not in db_url:
        db_url += ("&" if "?" in db_url else "?") + "sslmode=require"
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
else:
    # Local development fallback
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///leads.db"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# Ensure tables exist even when running under gunicorn on Render
@app.before_first_request
def _create_all():
    db.create_all()

# --------------------
# AI Analysis (optional)
# --------------------
def _fallback_analysis(lead):
    name = (lead.company or lead.contact_name or "this lead")
    return (
        f"Playbook preview for {name}:\n"
        "- Channel: Start with email, follow with phone within 2–3 days.\n"
        "- Cadence: Day 0 (email), Day 3 (call), Day 7 (value resource), Day 14 (final check-in).\n"
        "- Talking points: reliability, total cost of ownership, parts/service support, and an offer to assess current fleet.\n"
        "- CTA: 15-minute discovery call to confirm daily usage, lift height, aisle width, and power preference."
    )

try:
    from utils.ai_analysis import analyze_lead as _ai_analyze
except Exception:
    _ai_analyze = None

def get_analysis_for(lead):
    try:
        if _ai_analyze:
            return _ai_analyze(lead)
    except Exception:
        return _fallback_analysis(lead) + f"\n\n(Note: AI module error was handled.)"
    return _fallback_analysis(lead)

# --------------------
# Database Model (all fields optional)
# --------------------
class Lead(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Base fields
    company = db.Column(db.String(200), nullable=True)
    contact_name = db.Column(db.String(200), nullable=True)
    contact_email = db.Column(db.String(200), nullable=True)
    phone = db.Column(db.String(100), nullable=True)
    industry = db.Column(db.String(200), nullable=True)
    fleet_size = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    # Imported sheet fields
    lead_date = db.Column(db.Date, nullable=True)          # "Date"
    rep = db.Column(db.String(200), nullable=True)         # "Territory/ Sales Rep"
    source = db.Column(db.String(200), nullable=True)      # "Source"
    address = db.Column(db.String(300), nullable=True)     # "Address"
    city = db.Column(db.String(200), nullable=True)        # "City"

    # Classifications
    quality = db.Column(db.String(20), nullable=True)      # 'good'|'warm'|'bad'|None (unknown)
    stage = db.Column(db.String(20), nullable=True)        # 'new','contacted','qualified','quoted','won','lost'|None (treat None as 'new')

# --------------------
# Core Reps (seed list for dropdowns)
# --------------------
REPS = ["John Battiston", "Kirk Whitaker", "Thomas Phillips"]

def all_reps_options():
    """Return sorted, de-duplicated list of reps/territories for dropdowns."""
    reps_db = [r[0] for r in db.session.query(Lead.rep)
               .filter(Lead.rep.isnot(None), Lead.rep != "")
               .distinct().all()]
    merged = {r.strip() for r in [*REPS, *reps_db] if r and r.strip()}
    return sorted(merged, key=lambda s: s.lower())

# --------------------
# Helpers
# --------------------
ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}

def normalize_columns(df):
    # local import so pandas is only loaded when this runs
    import pandas as pd
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df

def is_empty(v) -> bool:
    try:
        # local import to use pd.isna
        import pandas as pd
        if pd.isna(v):
            return True
    except Exception:
        pass
    if v is None:
        return True
    return isinstance(v, str) and v.strip() == ""

def parse_date_safe(v):
    # local import for Timestamp/to_datetime
    import pandas as pd
    from datetime import datetime, date

    if is_empty(v):
        return None
    if isinstance(v, pd.Timestamp):
        return v.date()
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        ts = pd.to_datetime(v, errors="coerce")
        if pd.isna(ts):
            return None
        return ts.date()
    except Exception:
        return None

def row_to_lead_kwargs(row):
    cols = row.index
    def pick_text(*names):
        for n in names:
            if n in cols:
             return None
    return dict(
        company      = pick_text("company"),
        notes        = pick_text("notes", "comments", "details", "remarks"),
        lead_date    = parse_date_safe(row.get("date")) if "date" in cols else None,
        rep          = pick_text("territory/ sales rep", "territory", "sales rep", "rep"),
        source       = pick_text("source"),
        address      = pick_text("address"),
        city         = pick_text("city"),
        contact_name = pick_text("contact", "contact name", "name", "primary contact"),
        contact_email= pick_text("email", "contact email", "e-mail"),
        phone        = pick_text("phone", "phone number", "tel"),
        industry     = pick_text("industry", "segment", "sic", "naics"),
        fleet_size   = pick_text("fleet size", "trucks", "forklifts", "units"),
    )

def apply_filters(query, q, rep_filter, quality_filter):
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Lead.company.ilike(like),
            Lead.contact_name.ilike(like),
            Lead.contact_email.ilike(like),
            Lead.phone.ilike(like),
            Lead.industry.ilike(like),
            Lead.fleet_size.ilike(like),
            Lead.notes.ilike(like),
            Lead.source.ilike(like),
            Lead.address.ilike(like),
            Lead.city.ilike(like),
            Lead.rep.ilike(like),
        ))
    if rep_filter:
        query = query.filter(Lead.rep == rep_filter)
    if quality_filter:
        if quality_filter == "unknown":
            query = query.filter((Lead.quality == None) | (Lead.quality == ""))
        else:
            query = query.filter(Lead.quality == quality_filter)
    return query

def stage_or_default(s):
    return (s or "new").lower()

STAGES = ["new","contacted","qualified","quoted","won","lost"]

# --------------------
# NAV / Landing
# --------------------
@app.route("/")
def home():
    return redirect(url_for("kanban_view"))

# --------------------
# KANBAN VIEW
# --------------------
@app.route("/kanban")
def kanban_view():
    q = (request.args.get("q") or "").strip()
    rep_filter = (request.args.get("rep") or "").strip()
    quality_filter = (request.args.get("quality") or "").strip().lower()

    # Base query with existing helper
    query = apply_filters(Lead.query, q, rep_filter, quality_filter)

    # EXCLUDE all dead leads from the board
    query = query.filter(or_(Lead.stage == None, Lead.stage != "lost"))

    leads = query.order_by(
        Lead.lead_date.desc().nullslast(),
        Lead.created_at.desc()
    ).all()

    # --- Group into 3 lanes ---
    groups = {
        "no_contact": [],         # 'new' or None
        "in_discussion": [],      # 'qualified','quoted','won'
        "waiting_response": []    # 'contacted'
    }

    for l in leads:
        s = (l.stage or "new").lower()
        if s in {"qualified", "quoted", "won"}:
            groups["in_discussion"].append(l)
        elif s == "contacted":
            groups["waiting_response"].append(l)
        else:
            groups["no_contact"].append(l)

    # Sort lanes alphabetically by company, blanks last
    def _cmp_company(lead):
        name = (lead.company or "").strip().lower()
        return (name == "", name)

    for key in ("no_contact", "in_discussion", "waiting_response"):
        groups[key].sort(key=_cmp_company)

    # Columns config: (title, drop_target_stage, key)
    columns = [
        ("Haven't Contacted", "new", "no_contact"),
        ("In Discussion",     "qualified", "in_discussion"),
        ("Waiting Response",  "contacted", "waiting_response"),
    ]

    reps = [r[0] for r in db.session.query(Lead.rep)
            .filter(Lead.rep.isnot(None), Lead.rep != "")
            .distinct().order_by(Lead.rep.asc()).all()]

    return render_template(
        "kanban.html",
        columns=columns,
        groups=groups,
        q=q,
        rep_filter=rep_filter,
        quality_filter=quality_filter,
        reps=reps
    )

@app.post("/api/kanban/update")
def api_kanban_update():
    data = request.get_json(silent=True) or {}
    lead_id = data.get("lead_id")
    new_stage = stage_or_default(data.get("stage"))
    if new_stage not in STAGES:
        return jsonify({"ok": False, "error": "invalid stage"}), 400
    lead = Lead.query.get_or_404(int(lead_id))
    lead.stage = new_stage
    db.session.commit()
    return jsonify({"ok": True})

# Quick classification from Kanban cards (AJAX or redirect)
@app.post("/lead/<int:lead_id>/quality/<value>")
def set_quality(lead_id, value):
    value = (value or "").lower()
    if value not in ("good", "warm", "bad"):
        abort(400, "invalid quality")
    lead = Lead.query.get_or_404(lead_id)
    lead.quality = value
    db.session.commit()
    if request.headers.get("X-Requested-With") == "fetch" or request.accept_mimetypes.best == "application/json":
        return jsonify({"ok": True})
    flash(f"Marked lead as {value.title()}.", "success")
    return redirect(request.referrer or url_for("kanban_view"))

# Mark a lead as DEAD (stage='lost')
@app.post("/lead/<int:lead_id>/dead")
def mark_dead(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    lead.stage = "lost"
    db.session.commit()
    if request.headers.get("X-Requested-With") == "fetch" or request.accept_mimetypes.best == "application/json":
        return jsonify({"ok": True})
    flash("Lead marked as Dead.", "success")
    return redirect(request.referrer or url_for("kanban_view"))

# --------------------
# Dead Leads (grid view)
# --------------------
@app.route("/dead")
def dead_leads_view():
    q = (request.args.get("q") or "").strip()
    rep_filter = (request.args.get("rep") or "").strip()
    quality_filter = (request.args.get("quality") or "").strip().lower()

    query = apply_filters(Lead.query, q, rep_filter, quality_filter)
    query = query.filter(Lead.stage == "lost")

    leads = query.order_by(func.lower(func.coalesce(Lead.company, "zzzzzzzz"))).all()

    reps = [r[0] for r in db.session.query(Lead.rep)
            .filter(Lead.rep.isnot(None), Lead.rep != "")
            .distinct().order_by(Lead.rep.asc()).all()]

    return render_template("dead.html",
                           leads=leads,
                           q=q,
                           rep_filter=rep_filter,
                           quality_filter=quality_filter,
                           reps=reps)

# Restore a dead lead back to the main board
@app.post("/lead/<int:lead_id>/restore")
def restore_dead(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    lead.stage = "new"
    db.session.commit()
    if request.headers.get("X-Requested-With") == "fetch" or request.accept_mimetypes.best == "application/json":
        return jsonify({"ok": True})
    flash("Lead restored to the board.", "success")
    return redirect(request.referrer or url_for("dead_leads_view"))

# --------------------
# INBOX VIEW (split)
# --------------------
@app.route("/inbox")
def inbox_view():
    q = (request.args.get("q") or "").strip()
    rep_filter = (request.args.get("rep") or "").strip()
    quality_filter = (request.args.get("quality") or "").strip().lower()
    sort = (request.args.get("sort") or "lead_date").strip().lower()
    direction = (request.args.get("dir") or "desc").strip().lower()
    page = int(request.args.get("page") or 1)
    per_page = int(request.args.get("per_page") or 25)

    query = apply_filters(Lead.query, q, rep_filter, quality_filter)

    sort_map = {
        "lead_date": Lead.lead_date,
        "created": Lead.created_at,
        "company": Lead.company,
        "rep": Lead.rep,
        "source": Lead.source,
        "city": Lead.city,
        "stage": Lead.stage,
        "quality": Lead.quality,
    }
    sort_col = sort_map.get(sort, Lead.lead_date)
    if direction == "asc":
        query = query.order_by(sort_col.asc().nullslast(), Lead.created_at.desc())
    else:
        query = query.order_by(sort_col.desc().nullslast(), Lead.created_at.desc())

    reps = all_reps_options()

    pagination = db.paginate(query, page=page, per_page=per_page, error_out=False)
    return render_template("inbox.html",
                           leads=pagination.items,
                           pagination=pagination,
                           q=q, rep_filter=rep_filter,
                           quality_filter=quality_filter,
                           sort=sort, direction=direction,
                           reps=reps, per_page=per_page)

@app.get("/lead/<int:lead_id>/panel")
def lead_panel(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    analysis = get_analysis_for(lead)
    return render_template("partials/lead_panel.html", lead=lead, analysis=analysis)

# --------------------
# ANALYTICS VIEW
# --------------------
@app.route("/analytics")
def analytics():
    leads = Lead.query.all()

    def label_quality(qval):
        return (qval or "unknown").lower()

    def label_stage(sval):
        return (sval or "new").lower()

    by_quality = Counter(label_quality(l.quality) for l in leads)
    by_stage = Counter(label_stage(l.stage) for l in leads)
    by_rep = Counter((l.rep or "Unassigned") for l in leads)

    by_month = Counter()
    for l in leads:
        d = l.lead_date or (l.created_at.date() if l.created_at else None)
        if d:
            key = f"{d.year}-{d.month:02d}"
            by_month[key] += 1

    rep_labels = sorted(by_rep.keys())
    rep_values = [by_rep[k] for k in rep_labels]

    quality_labels = ["good","warm","bad","unknown"]
    quality_values = [by_quality.get(k,0) for k in quality_labels]

    stage_labels = ["new","contacted","qualified","quoted","won","lost"]
    stage_values = [by_stage.get(k,0) for k in stage_labels]

    month_labels = sorted(by_month.keys())
    month_values = [by_month[m] for m in month_labels]

    kpis = {
        "total": len(leads),
        "good": by_quality.get("good",0),
        "warm": by_quality.get("warm",0),
        "bad": by_quality.get("bad",0),
        "unknown": by_quality.get("unknown",0),
    }

    return render_template("analytics.html",
                           kpis=kpis,
                           rep_labels=rep_labels, rep_values=rep_values,
                           quality_labels=quality_labels, quality_values=quality_values,
                           stage_labels=stage_labels, stage_values=stage_values,
                           month_labels=month_labels, month_values=month_values)

# --------------------
# Lead detail (deep view)
# --------------------
@app.route("/lead/<int:lead_id>")
def lead_detail(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    analysis = get_analysis_for(lead)
    return render_template("lead_detail.html", lead=lead, analysis=analysis)

# --------------------
# Add Lead (rep/territory dropdown uses seed + DB)
# --------------------
@app.route("/add", methods=["GET", "POST"])
def add_lead():
    if request.method == "POST":
        rep_select = (request.form.get("rep_select") or "").strip()
        rep_other  = (request.form.get("rep_other") or "").strip()
        rep_direct = (request.form.get("rep") or "").strip()
        rep = rep_other or (None if rep_select == "__other__" else rep_select) or rep_direct or None

        new_lead = Lead(
            company      = request.form.get("company") or None,
            contact_name = request.form.get("contact_name") or None,
            contact_email= request.form.get("contact_email") or None,
            phone        = request.form.get("phone") or None,
            industry     = request.form.get("industry") or None,
            fleet_size   = request.form.get("fleet_size") or None,
            notes        = request.form.get("notes") or None,
            lead_date    = (datetime.strptime(request.form["lead_date"], "%Y-%m-%d").date()
                            if request.form.get("lead_date") else None),
            source       = request.form.get("source") or None,
            address      = request.form.get("address") or None,
            city         = request.form.get("city") or None,
            rep          = rep,
        )
        db.session.add(new_lead)
        db.session.commit()
        flash("Lead added.", "success")
        return redirect(url_for("home"))
    return render_template("add_lead.html", reps=all_reps_options())

# --------------------
# In-app Importer
# --------------------
@app.route("/import", methods=["GET", "POST"])
def import_leads_view():
    # localize heavy imports so the app can start without them
    import tempfile
    import pandas as pd

    if request.method == "POST":
        f = request.files.get("file")
        if not f or f.filename == "":
            flash("Please choose a file.", "error"); return redirect(url_for("import_leads_view"))
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            flash("Unsupported file type. Use .xlsx, .xls, or .csv", "error"); return redirect(url_for("import_leads_view"))

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            f.save(tmp.name); path = tmp.name

        try:
            df = pd.read_excel(path) if ext in [".xlsx",".xls"] else pd.read_csv(path)
        except Exception as e:
            flash(f"Could not read file: {e}", "error"); return redirect(url_for("import_leads_view"))
        if df is None or df.empty:
            flash("No rows found in file.", "error"); return redirect(url_for("import_leads_view"))

        df = normalize_columns(df)
        # ... (rest of your import logic unchanged)

        inserted = skipped = updated = 0
        for _, row in df.iterrows():
            kwargs = row_to_lead_kwargs(row)
            if "lead_date" in kwargs:
                kwargs["lead_date"] = parse_date_safe(kwargs["lead_date"])
            for k, v in list(kwargs.items()):
                if k != "lead_date" and (v is None or (isinstance(v, str) and v.strip() == "")):
                    kwargs[k] = None
            model_cols = {c.key for c in Lead.__table__.columns}
            safe = {k: v for k, v in kwargs.items() if k in model_cols}

            company = safe.get("company")
            email = safe.get("contact_email")
            qy = Lead.query
            if company: qy = qy.filter(Lead.company == company)
            if email:   qy = qy.filter(Lead.contact_email == email)
            existing = qy.first() if (company or email) else None

            if existing:
                changed = False
                for k, v in safe.items():
                    if v is not None and getattr(existing, k) != v:
                        setattr(existing, k, v); changed = True
                if changed: updated += 1
                else: skipped += 1
            else:
                db.session.add(Lead(**safe)); inserted += 1

        db.session.commit()
        flash(f"Imported {inserted} new, Updated {updated}, Skipped {skipped}.", "success")
        return redirect(url_for("home"))

    return render_template("import.html")

# --------------------
# Run Server (Port 5020)
# --------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5020)
