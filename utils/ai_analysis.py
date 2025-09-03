"""
utils/ai_analysis.py

Generates a detailed, plain-text playbook for a Lead.
- Works fully offline with deterministic rules that produce clear, complete sentences.
- Optionally refines with OpenAI if OPENAI_API_KEY is set and `openai` is installed.

The output is organized in short sections so it reads like a mini brief.
"""

import os
import re
from datetime import datetime, timedelta, date

# Optional OpenAI
_OPENAI_KEY = os.getenv("OPENAI_API_KEY")
_openai = None
if _OPENAI_KEY:
    try:
        from openai import OpenAI
        _openai = OpenAI(api_key=_OPENAI_KEY)
    except Exception:
        _openai = None

# -------- Helpers --------
def _v(s): return (s or "").strip()
def _lower(s): return _v(s).lower()

def _safe_date(d):
    if isinstance(d, datetime): return d.date()
    if isinstance(d, date): return d
    return None

def _first_line(text: str, max_len: int = 120) -> str:
    """One-line distill from notes."""
    if not text:
        return "Unknown"
    s = text.strip().splitlines()[0]
    return (s[:max_len] + "…") if len(s) > max_len else s

# -------- “Daily Usage” (plain-English replacement for duty cycle) --------
_HOURS_RE = re.compile(r"(\d{1,2})\s*(?:hr|hrs|hour|hours)\b", re.I)

def _simplify_usage(lead) -> str:
    """
    Convert hints (notes/keywords) into plain-English 'Daily Usage'.
    Avoids jargon. Returns a friendly phrase.
    """
    notes = _lower(getattr(lead, "notes", ""))
    hours = 0
    for m in _HOURS_RE.finditer(notes):
        try:
            hours = max(hours, int(m.group(1)))
        except Exception:
            pass

    # strong keywords
    if any(k in notes for k in ["24/7", "24x7", "three shift", "3 shift", "triple shift"]):
        return "Heavy (multiple shifts / long hours)"
    if any(k in notes for k in ["two shift", "2 shift", "double shift"]):
        return "Medium to heavy (often two shifts)"

    # hour-based heuristics
    if hours >= 12:
        return "Heavy (long daily runtime)"
    if 8 <= hours < 12:
        return "Medium (about one shift)"
    if 1 <= hours < 8:
        return "Light to medium (a few hours daily)"
    return "Unknown"

# -------- Environment / operating context from notes & industry --------
def _env_from_lead(lead):
    notes = _lower(getattr(lead, "notes", ""))
    industry = _lower(getattr(lead, "industry", ""))

    cold = any(k in notes for k in ["cold", "freezer", "refrigerated", "cold storage"])
    dusty = any(k in notes for k in ["dust", "sawdust", "grain", "powder"])
    ramps = any(k in notes for k in ["ramp", "grade", "slope"])
    outdoor = any(k in notes for k in ["outdoor", "yard", "lot"]) or any(k in industry for k in ["construction", "yard", "lumber"])
    indoor = "indoor" in notes or "warehouse" in industry or "distribution" in industry

    return dict(cold=cold, dusty=dusty, ramps=ramps, outdoor=outdoor, indoor=indoor)

# -------- Industry heuristics (complete-sentence friendly) --------
def _industry_profile(industry: str):
    i = _lower(industry)
    profiles = [
        (("agriculture","agri","grain","bunge","food","edible oil","milling"),
         [
             "Tight delivery windows can create congestion at docks and slow throughput.",
             "Food-safety expectations favor clean power and low emissions inside processing areas.",
             "Outdoor yard moves and indoor transitions require the right tire and power mix."
         ],
         [
             "We typically lower total cost of ownership while maintaining reliable uptime.",
             "Parts availability and regional service coverage shorten downtime.",
             "Lithium options support clean, food-safe operations where needed."
         ],
         [
             "Segment by daily usage so indoor units stay clean and efficient.",
             "Use Li-ion for indoor food areas and pneumatic IC or Li-ion for yard work.",
             "Offer a quick survey of lift heights and aisle widths so the mast and attachments are correct."
         ]),
        (("manufacturing","fabrication","heavy machinery"),
         [
             "Mixed loads and shift patterns cause uneven wear and unexpected downtime.",
             "Unplanned stoppages quickly turn into lost production hours.",
             "Common attachments like a sideshifter or fork positioner improve throughput."
         ],
         [
             "A robust chassis and mast design handle longer shifts reliably.",
             "Predictive maintenance and proactive PM scheduling reduce surprises.",
             "Lead times are competitive with larger brands without sacrificing quality."
         ],
         [
             "Start with a short time-motion check to confirm daily usage.",
             "Standardize sideshifters and fork positioners on the busiest lanes.",
             "Pilot one Li-ion unit on the heaviest shift to prove the ROI with real data."
         ]),
        (("logistics","3pl","warehouse","distribution","ecommerce","retail"),
         [
             "Seasonal peaks demand surge capacity without overcommitting capital.",
             "Aisle width and racking heights must be verified before quoting masts.",
             "Operator turnover calls for simple controls and safety visibility aids."
         ],
         [
             "We provide reach and narrow-aisle configurations with excellent visibility.",
             "Rental and burst-capacity programs help cover peak months cost-effectively.",
             "Telematics and access control improve safety and utilization."
         ],
         [
             "Measure aisle width and lift height before specifying masts or cameras.",
             "Bundle flexible rental capacity for known peak periods to protect cash.",
             "Add blue lights or cameras and operator access control where appropriate."
         ]),
        (("construction","yard","lumber"),
         [
             "Uneven surfaces and outdoor exposure require the right tires and clearance.",
             "Fuel and energy costs add up over long travel paths.",
             "Small on-site teams need fast, predictable service support."
         ],
         [
             "Pneumatic tire IC or Li-ion units with higher ground clearance perform well.",
             "Mobile service and on-site PM options minimize travel and wait time.",
             "Pricing stays competitive even at higher capacities."
         ],
         [
             "Specify pneumatics and protective packages such as guards and lighting.",
             "Confirm grades and surface conditions to size power correctly.",
             "Offer service SLAs with response-time commitments."
         ]),
        (("cold","freezer","refrigerated"),
         [
             "Cold environments reduce battery performance and can create condensation.",
             "Corrosion risks increase on unprotected components.",
             "Operator comfort and visibility matter when temperatures stay low."
         ],
         [
             "Cold-store packages and select heaters preserve performance in the cold.",
             "Li-ion with thermal management handles frequent short charges well.",
             "Seals and grease choices withstand repeated condensation cycles."
         ],
         [
             "Use cold-store kits and treated components where corrosion is likely.",
             "Plan charging strategy and warm-up cycles before peak windows.",
             "Consider cab options or heated grips to sustain performance."
         ]),
    ]

    generic = dict(
        pains=[
            "Daily usage is unclear, which makes right-sizing equipment difficult.",
            "Irregular follow-up lowers response rate and reduces win probability.",
            "Price comparisons require a clear, one-page ROI story."
        ],
        proof=[
            "We maintain reliable service coverage with fast access to parts.",
            "Lower total cost of ownership is typical due to energy and PM savings.",
            "Short-term trials or rentals de-risk the final selection."
        ],
        tracks=[
            "Schedule a 15-minute discovery to map hours, loads, and aisle/lift needs.",
            "Offer a brief pilot or rental to validate comfort and performance.",
            "Share a one-page ROI that compares energy and maintenance to the status quo."
        ],
    )

    for keys, pains, proof, tracks in profiles:
        if any(k in i for k in keys):
            return dict(pains=pains, proof=proof, tracks=tracks)
    return generic

# -------- Channel & cadence (sentence style) --------
def _recommended_cadence(has_email: bool, has_phone: bool):
    steps = []
    if has_email:
        steps.append("Send a short email that introduces the value and offers a 15-minute discovery call.")
    if has_phone:
        steps.append("Place a brief call that references the email and proposes two time slots.")
    else:
        steps.append("If no phone, send a follow-up email with one relevant case study and two time windows.")
    steps.append("Share a concise one-pager (ROI summary, safety overview, or model comparison).")
    steps.append("If no movement, propose a site walk or a short demo.")
    return steps

def _qualification_questions():
    return [
        "Typical and peak load weights.",
        "Required lift height and common lift heights.",
        "Aisle width and turning constraints.",
        "Hours per shift and number of shifts per day.",
        "Environment: indoors, outdoors, or mixed; surface conditions and ramps.",
        "Preferred power (IC or Li-ion) and existing fueling/charging.",
        "Needed attachments (sideshifter, fork positioner, clamp, camera).",
        "Current issues: downtime, parts delays, operator problems.",
        "Seasonal peaks and any rental surge capacity needs."
    ]

def _subject_line(company: str, industry: str):
    base = "A practical idea to cut downtime and cost"
    if _v(industry): return f"{industry.title()} operations — {base}"
    if _v(company):  return f"{company} — {base}"
    return base

def _first_email_body(lead):
    company = _v(getattr(lead, "company", "")) or "your team"
    contact = _v(getattr(lead, "contact_name", "")) or "there"
    industry = _v(getattr(lead, "industry", ""))

    prof = _industry_profile(industry)
    pains = prof["pains"][:2]
    proof = prof["proof"][:2]

    lines = []
    lines.append(f"Hi {contact},")
    lines.append("")
    lines.append(f"I work with material handling teams like {company}. Based on similar {industry or 'operations'}, we typically help in two areas:")
    for p in pains:
        lines.append(f"• {p}")
    lines.append("")
    lines.append("Here is how we usually solve those problems:")
    for p in proof:
        lines.append(f"• {p}")
    lines.append("")
    # swapped “duty cycle” → “daily usage”
    lines.append("Would a quick 15-minute discovery call this week be helpful? I can share a one-page specification and ROI sketch tailored to your daily usage.")
    lines.append("")
    lines.append("Best,")
    lines.append("Thomas Phillips")
    lines.append("Tynan Equipment Company")
    return "\n".join(lines)

def _call_opener(industry: str):
    track = _industry_profile(industry)["tracks"][0]
    return (
        "Hi, this is Thomas with Tynan Equipment. We help teams reduce downtime and total cost on forklifts. "
        f"I would like to schedule a brief discovery so we can {track.lower()} Would you have ten to fifteen minutes this week?"
    )

# -------- Quote guidance based on usage + environment (folded into What Works) --------
def _quote_guidance(lead):
    usage = _simplify_usage(lead)
    env = _env_from_lead(lead)
    industry = _lower(getattr(lead, "industry", ""))

    # Truck spec
    if env["outdoor"] or any(k in industry for k in ["construction", "yard", "lumber"]):
        truck = "Pneumatic tires with higher ground clearance and protective guards; add lighting for outdoor use."
    elif env["cold"]:
        truck = "Cold-store package with corrosion protection; verify visibility and operator comfort."
    else:
        truck = "Cushion tires for smooth floors; size the mast to racking and common pallets."

    # Power & battery
    if usage.startswith("Heavy"):
        power = "80V or Li-ion sized for long hours; plan for opportunity charging or hot-swap if using lead-acid."
        service = "Tight PM cadence (monthly or bi-monthly), stock critical spares, and include a response-time SLA."
        charging = "Opportunity or fast chargers near break areas; verify circuits and clearances."
    elif "Medium" in usage:
        power = "48V (or 36/48V) right-sized to one shift; one battery per truck with overnight charging."
        service = "Regular PM schedule with warranty coverage for key components."
        charging = "Standard chargers placed near parking; plan circuit loads for concurrent charging."
    elif usage.startswith("Light"):
        power = "Standard capacity with overnight charging; one battery per truck."
        service = "Quarterly PM with basic wear-item coverage."
        charging = "Overnight charging in a safe, ventilated area; minimal infrastructure."
    else:
        power = "Choose between IC and Li-ion after confirming hours and loads; start from a one-shift baseline."
        service = "Baseline PM plan; tighten after usage is confirmed."
        charging = "Pick overnight vs opportunity charging after hours and breaks are clarified."

    # Environment modifiers
    if env["ramps"]:
        truck += " Confirm grades and size power/torque for ramp work."
    if env["dusty"]:
        truck += " Add filtration and seals where dust is present."
    if env["cold"]:
        power += " Prefer Li-ion with thermal management in cold storage."

    return dict(truck=truck, power=power, charging=charging, service=service, usage=usage)

# -------- Main entry --------
def analyze_lead(lead) -> str:
    company = _v(getattr(lead, "company", ""))
    contact = _v(getattr(lead, "contact_name", ""))
    email   = _v(getattr(lead, "contact_email", ""))
    phone   = _v(getattr(lead, "phone", ""))
    industry= _v(getattr(lead, "industry", ""))
    fleet   = _v(getattr(lead, "fleet_size", ""))
    notes   = _v(getattr(lead, "notes", ""))
    rep     = _v(getattr(lead, "rep", ""))
    source  = _v(getattr(lead, "source", ""))
    city    = _v(getattr(lead, "city", ""))
    address = _v(getattr(lead, "address", ""))
    created_at = getattr(lead, "created_at", None)
    lead_date  = getattr(lead, "lead_date", None)

    prof   = _industry_profile(industry)
    cadence = _recommended_cadence(bool(email), bool(phone))
    quals  = _qualification_questions()
    qg     = _quote_guidance(lead)

    # Decide next best step based on age
    today = datetime.utcnow().date()
    created_date = _safe_date(created_at) or today
    days_since = (today - created_date).days if created_date else 0

    if days_since <= 0:
        nba = "Send the introductory email today and offer two specific time slots for a 15-minute discovery call."
    elif days_since <= 2:
        nba = "Make the Day-3 touch. If you have a phone number, place a short call; otherwise, send a concise follow-up email."
    elif days_since <= 6:
        nba = "Share a relevant one-pager such as an ROI summary or a case study to move the conversation forward."
    else:
        nba = "Send a brief, respectful final check-in and propose a site walk or a short demo."

    subject = _subject_line(company, industry)
    email_body = _first_email_body(lead)
    call_open  = _call_opener(industry)
    notes_signal = _first_line(notes)

    # ---------- Offline baseline with headings matching the ORIGINAL PROMPT ----------
    # (Summary, Challenges, What Works, Talk Tracks, Cadence, Next Best Action,
    #  Email Subject, First-Touch Email, Call Opener, Qualification Checklist)

    # Summary
    summary = []
    summary.append("Summary")
    summary.append(f"Company: {company or 'Unknown'}")
    if contact: summary.append(f"Contact: {contact}")
    if email:   summary.append(f"Email: {email}")
    if phone:   summary.append(f"Phone: {phone}")
    if industry:summary.append(f"Industry: {industry}")
    if city:    summary.append(f"City: {city}")
    if source:  summary.append(f"Source: {source}")
    if rep:     summary.append(f"Rep: {rep}")
    if lead_date: summary.append(f"Lead date: {lead_date.isoformat()}")
    if notes:   summary.append(f"Notes: {notes_signal}")
    summary.append(f"Daily Usage: {qg['usage']}")

    # Challenges
    challenges = ["Challenges", " ".join(prof["pains"])]

    # What Works (fold in quote guidance)
    works_lines = ["What Works"]
    works_lines.append(qg["truck"])
    works_lines.append(qg["power"])
    works_lines.append(qg["charging"])
    works_lines.append(qg["service"])
    works_lines.append(" ".join(prof["proof"]))
    what_works = works_lines

    # Talk Tracks
    talk_tracks = ["Talk Tracks", " ".join(prof["tracks"])]

    # Cadence
    cadence_block = ["Cadence", " ".join(cadence)]

    # Next Best Action
    nba_block = ["Next Best Action", nba]

    # Email + Call
    email_subject_block = ["Email Subject", subject]
    first_touch_block   = ["First-Touch Email", email_body]
    call_opener_block   = ["Call Opener", call_open]

    # Qualification
    qual_block = ["Qualification Checklist", " ".join([f"• {q}" for q in quals])]

    sections = [
        "\n".join(summary),
        "\n".join(challenges),
        "\n".join(what_works),
        "\n".join(talk_tracks),
        "\n".join(cadence_block),
        "\n".join(nba_block),
        "\n".join(email_subject_block),
        "\n".join(first_touch_block),
        "\n".join(call_opener_block),
        "\n".join(qual_block),
    ]

    offline = "\n\n".join(sections).strip()

    # ---------- Optional refinement (ORIGINAL PROMPT KEPT) ----------
    if _openai:
        try:
            prompt = (
                "You are a precise sales coach for a forklift dealership. "
                "Rewrite the following outreach plan so it reads like a concise internal brief. "
                "Use short paragraphs and complete sentences. Keep it practical and specific. "
                "Maintain sections for: Summary, Challenges, What Works, Talk Tracks, Cadence, Next Best Action, "
                "Email Subject, First-Touch Email, Call Opener, and Qualification Checklist.\n\n"
                f"{offline}\n\nReturn plain text only."
            )
            resp = _openai.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[{"role":"user","content":prompt}],
                temperature=0.35,
            )
            txt = (resp.choices[0].message.content or "").strip()
            if txt:
                return txt
        except Exception:
            pass

    return offline
