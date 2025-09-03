# enrich_leads_from_notes.py
import re
from app import app, db, Lead

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+?1[\s\-\.]?)?(?:\(?\d{3}\)?[\s\-\.]?)?\d{3}[\s\-\.]?\d{4}")

NAME_HINTS = ["attn", "contact", "signed by", "spoke with", "talked to", "name:"]

INDUSTRY_MAP = {
    "service": "Material Handling",
    "rental": "Material Handling",
    "parts": "Material Handling",
    "tynan": "Material Handling",
    "dealer": "Material Handling",
    "construction": "Construction",
    "warehouse": "Warehousing",
    "manufactur": "Manufacturing",
}

def guess_name(notes: str) -> str | None:
    if not notes: return None
    low = notes.lower()
    for h in NAME_HINTS:
        if h in low:
            # take ~40 chars after the hint
            start = low.find(h) + len(h)
            fragment = notes[start:start+40]
            # crude “Title Case” span until punctuation/newline
            fragment = fragment.replace(":", " ").replace("-", " ")
            parts = re.findall(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}", fragment)
            if parts:
                # choose the longest candidate
                return max(parts, key=len)
    return None

def map_industry(source: str | None) -> str | None:
    if not source: return None
    s = source.lower()
    for k, v in INDUSTRY_MAP.items():
        if k in s:
            return v
    return None

with app.app_context():
    changed = 0
    for lead in Lead.query.all():
        notes = (lead.notes or "")[:500]  # limit scan
        if not lead.contact_email:
            m = EMAIL_RE.search(notes)
            if m: lead.contact_email = m.group(0)
        if not lead.phone:
            m = PHONE_RE.search(notes)
            if m: lead.phone = m.group(0)
        if not lead.contact_name:
            n = guess_name(notes)
            if n: lead.contact_name = n
        if not lead.industry:
            ind = map_industry(lead.source)
            if ind: lead.industry = ind
        if any([EMAIL_RE.search(notes), PHONE_RE.search(notes), guess_name(notes), map_industry(lead.source)]):
            changed += 1
    db.session.commit()
    print(f"Enriched {changed} leads where possible.")
