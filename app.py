"""Vasool Round 3 server. The agent is the model; this file is only plumbing.
Real connectors: WhatsApp (Meta Cloud API) / Telegram, web app. Curtain connectors (Gnani, Pine Labs,
Delhivery) block until a human pastes the real API response into /wizard."""
import os, re, json, time, uuid, queue, random, secrets, hmac, hashlib, mimetypes, threading, datetime
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, render_template, redirect
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
BASE = Path(__file__).parent
UPLOADS = BASE / "uploads"; UPLOADS.mkdir(exist_ok=True)
LOGFILE = BASE / "decision_log.jsonl"

# ---------- save everything the terminal shows (plain text, no colours) to terminal_logs/ ----------
import sys
class _Tee:
    _ansi = re.compile(r"\x1b\[[0-9;]*m")
    def __init__(self, stream, fh, lock): self._s, self._f, self._l = stream, fh, lock
    def write(self, text):
        n = self._s.write(text)
        with self._l:
            self._f.write(self._ansi.sub("", text)); self._f.flush()
        return n
    def flush(self): self._s.flush()
    def __getattr__(self, name): return getattr(self._s, name)
(BASE / "terminal_logs").mkdir(exist_ok=True)
TERMINAL_LOG = BASE / "terminal_logs" / f"run_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt"
_tl_file = open(TERMINAL_LOG, "w", encoding="utf-8"); _tl_lock = threading.Lock()
sys.stdout = _Tee(sys.stdout, _tl_file, _tl_lock); sys.stderr = _Tee(sys.stderr, _tl_file, _tl_lock)
print(f"Terminal log is being saved to: {TERMINAL_LOG}\n", flush=True)

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
PUBLIC = os.getenv("PUBLIC_URL", "http://localhost:5000").rstrip("/")
RAVI = "".join(ch for ch in os.getenv("RAVI_WHATSAPP", "") if ch.isdigit())
GRAPH = os.getenv("GRAPH_VERSION", "v23.0")
PROMPT = (BASE / "prompt.md").read_text(encoding="utf-8").replace("{{PUBLIC_URL}}", PUBLIC)

DOCS = {"claim_form": "Claim form, duly signed", "tpa_card": "Vidal Health TPA card (photocopy)",
        "id_proof": "Identity proof (photocopy)", "discharge_summary": "Discharge summary with hospital seal and signature",
        "inpatient_bills": "In-patient bills", "prescription": "Doctor's prescription",
        "pharmacy_bills": "Pharmacy bills with break-ups", "investigation_reports": "Investigation reports (MRI, ECG, CT scan, X-ray)",
        "lab_reports": "Laboratory reports", "paid_receipt": "Paid receipt with hospital seal and signature",
        "registration_copy": "Hospital registration copy (if required)"}

# Registration copy is explicitly optional in the sample checklist. All other
# document slots are required before the dispatch/pickup gate can open.
OPTIONAL_R3_DOCS = {"registration_copy"}
REQUIRED_R3_DOCS = [k for k in DOCS if k not in OPTIONAL_R3_DOCS]
def fresh_state():
    return {"stage": "identity", "docs": {k: {"label": v, "status": "empty", "reason": "", "detected_type": "", "evidence": ""} for k, v in DOCS.items()},
            "profile": {}, "basics": {}, "pickup": {}, "elig": None, "note": None, "transcript": [], "form": None,
            "timeline": [], "pay": None, "signature": "", "summary": None, "otp_pending": False, "otp_ok": False, "waiting_for_docs": False,
            "delivery": {"carrier": "Delhivery", "tracking_id": "VSLDEMO20261002", "status": "Not started", "progress": 0, "eta": ""},
            "payment_approved": False, "final_phase": 0}
STATE = fresh_state()
OTP = {"code": None, "exp": 0, "tries": 0}
def new_otp():
    OTP.update(code=f"{secrets.randbelow(10**6):06d}", exp=time.time() + 300, tries=0)
    return OTP["code"]

# Keep track of what the claimant has actually uploaded. This prevents the
# model from marking documents that were never uploaded as "verified" during R3.
UPLOADED_DOCS = set()

# Each document slot gets a new version whenever a new file is uploaded.
# A document that fails verification may NOT become verified again on the
# same upload version; it must receive a fresh upload first. This prevents
# the agent from reconsidering the same wrong file and accidentally clearing
# the RETAKE decision within the same Gemini turn.
DOC_VERSIONS = {k: 0 for k in DOCS}
RETAKE_VERSIONS = {}
VERIFIED_VERSIONS = {}

# Document uploads are debounced so the agent does not race ahead while the
# claimant is still uploading files one by one. The agent starts only after
# this many seconds have passed since the last document upload.
DOC_UPLOAD_SETTLE_SECONDS = float(os.getenv("DOC_UPLOAD_SETTLE_SECONDS", "10"))
DOC_BATCH = []
DOC_BATCH_NAMES = []
DOC_BATCH_TIMER = None
DOC_BATCH_LOCK = threading.Lock()

PEND, DONE = {}, []
PINE = {"n": 0, "mandate_id": "PL-DEMO-001", "active": False}
PINE_FAKE = os.getenv("PINELABS_MODE", "fake").lower() == "fake"
DELHIVERY_FAKE = os.getenv("DELHIVERY_MODE", "fake").lower() == "fake"
DELIVERY_STEP_SECONDS = float(os.getenv("DELIVERY_STEP_SECONDS", "3.0"))
DELIVERY_LOCK = threading.Lock()
DELIVERY_STARTED = False
DELIVERY_GEN = 0
client = None
GNANI_FAKE = os.getenv("GNANI_MODE", "fake").lower() == "fake"
GN = {"n": 0, "convs": {}}
_PAYOUT = ("Rs 1,12,000 has been disbursed to the policyholder's registered account today." if os.getenv("GNANI_PAYOUT") != "short"
           else "We have disbursed Rs 1,04,000. Rs 8,000 is deducted as proportionate deduction on room rent.")
# Transcripts below are copied word for word from the three real Gnani test calls (dashboard "Recording & Transcript").
SCRIPTS = [
 [("Vasool", "Hello, this is Vasool calling on behalf of Ravi Menon about claim VH-2026-448120."),
  ("TPA", "hello please confirm the member id"),
  ("Vasool", "Member I D V H-20458821. I need the settlement status for his hospitalisation at Sunrise Multispeciality Hospital"),
  ("TPA", "the claim is settled we paid three lakh rupees rupees three lakh which is the policy limit"),
  ("Vasool", "What is the outstanding balance against the hospital bill?"),
  ("TPA", "rupees one lakh twenty thousand is outstanding of which eight thousand is non payable items the settlement note reference is vhsn nine zero four one seven thank you"),
  ("Vasool", "Thank you for providing all the necessary details")],
 [("Vasool", "This is Vasool calling for Ravi Menon, policy SJV-5540218. Did your claims desk receive a courier pack from him?"),
  ("Sanjeevani", "yes it reached the claimed this morning"),
  ("Vasool", "Are all documents complete?"),
  ("Sanjeevani", "twelve documents received in complete claim number sjv cl two zero two six zero nine four one seven"),
  ("Vasool", "What is the turnaround?"),
  ("Sanjeevani", "seven working days from receipt"),
  ("Vasool", "Thank you for providing all the necessary details")],
 [("Vasool", "Hello , vasool Following up on claim SJV-CL-2026-09417 for Ravi Menon"),
  ("Sanjeevani", "just a minute ok the claim has been approved"),
  ("Vasool", "That's great news. Since the claim has been approved, can you confirm the disbursed amount?"),
  ("Sanjeevani", "rupees one lakh twelve thousand has been disbursed to the policyholders registered account today"),
  ("Vasool", "Thank you for providing all the necessary details")]]
# _docshape: Gnani fake follows docs.gnani.ai (Trigger Test Call, Get Conversation Logs, Get Conversation Statistics)
def _jb(body):
    if isinstance(body, dict): return body
    try: return json.loads(body)
    except Exception: return {}
def _rid(): return str(uuid.uuid4())
GN_WHITELIST = [x.strip() for x in os.getenv("GNANI_WHITELIST", "").split(",") if x.strip()]
GN_BOT = "fb79920229d144608ebf665a10e50275"
# Real values copied from the Gnani dashboard, one per call in order (comma separated in .env)
_REAL_IDS = [x.strip() for x in os.getenv("GNANI_CONVERSATION_IDS", "1791043954690585251,1791044401569985251,1791044554895085251").split(",") if x.strip()]
_REAL_DUR = [int(x) for x in os.getenv("GNANI_CALL_DURATIONS", "55,39,33").replace(" ", "").split(",") if x.isdigit()]
def _gn_script(ref, name):
    # By order of call, not by wording: 1st call = primary TPA (settlement note), 1st Sanjeevani call = receipt, every later call = payout follow-up.
    nm = str(name).lower(); t = (str(ref) + " " + nm).lower(); served = GN.setdefault("served", set())
    recv = any(k in t for k in ("receipt", "received", "recv", "delivery", "courier"))
    if 0 not in served and not recv and "sanjeevani" not in nm: sc = 0
    elif 1 not in served: sc = 1
    else: sc = 2
    served.add(sc); return sc
_GN_CODE = ["SETTLEMENT_NOTE_OBTAINED", "RECEIPT_CONFIRMED", "DISBURSEMENT_CONFIRMED"]
def gnani_fake(name, body):
    n = str(name)
    if "trigger" in n:
        b = _jb(body); phone = str(b.get("phone", "")).replace(" ", "")[-10:]
        if phone not in GN_WHITELIST:
            return {"status": "failure", "requestId": _rid(), "message": "Phone number is not registered for outbound calls"}
        GN["n"] += 1; sc = _gn_script(b.get("clientReferenceId"), b.get("name")); cid = _REAL_IDS[sc] if sc < len(_REAL_IDS) else str(1790960000000000000 + GN["n"] * 7919)
        GN["convs"][cid] = {"ref": b.get("clientReferenceId", ""), "name": b.get("name", ""), "script": sc, "t": int(time.time()), "i": sc + 1}
        GN["last"] = cid
        return {"status": "success", "message": f"Call is being triggered to {phone}", "response": ({"clientReferenceId": b["clientReferenceId"]} if b.get("clientReferenceId") else None), "requestId": _rid()}
    if "logs" in n:
        term = str(_jb(body).get("searchTerm", "")).lower(); rows = []
        for cid, c in GN["convs"].items():
            if not term or term in str(c["ref"]).lower() or term in str(c["name"]).lower() or term == cid:
                rows.append({"conversationId": cid, "botId": GN_BOT, "botName": "Vasool call agent", "startTime": float(c["t"]), "endTime": float(c["t"] + (_REAL_DUR[c["i"] - 1] if c["i"] <= len(_REAL_DUR) else 80)), "name": c["name"], "transcript": []})
        return {"status": "success", "message": "Conversations retrieved successfully", "response": {"pageNo": 1, "pageSize": 10, "totalCount": len(rows), "totalPages": 1 if rows else 0, "data": rows}, "requestId": _rid()}
    cid = str(body).strip().strip('"'); c = GN["convs"].get(cid)
    if not c: return {"status": "failure", "requestId": _rid(), "message": "Conversation not found"}
    lines = SCRIPTS[c["script"]]; t0 = c["t"]; turns = []
    for i, (who, text) in enumerate(lines):
        row = {"role": "assistant" if who == "Vasool" else "user", "content": text, "timestamp": t0 + 1.0 + i * 12.37}
        if row["role"] == "user": row.update({"totalResults": {"en-IN": text}, "detectedLanguage": "english", "userInterruptionFlag": False})
        turns.append(row)
    code = _GN_CODE[c["script"]]
    dur = _REAL_DUR[c["i"] - 1] if c["i"] <= len(_REAL_DUR) else 79
    if c["script"] == 2 and os.getenv("GNANI_PAYOUT") == "short": code = "AMOUNT_MISMATCH"
    return {"status": "success", "message": "Conversation details fetched successfully", "requestId": _rid(), "response": [{
        "userId": "29be0f97-51c6-49aa-a515-e0433649e69d", "bot": GN_BOT, "botName": "Vasool call agent", "conversationId": cid,
        "startTime": t0, "endTime": t0 + dur + 1, "callStatus": "ANSWERED", "callDuration": dur, "overallCallDisposition": code,
        "utteranceAnalytics": turns, "botId": GN_BOT}]}



_COL = {"tool": "36", "event": "33", "decision": "32", "whatsapp_out": "34", "claimant_input": "33", "error": "31", "warn": "31",
        "gnani_replay": "35", "pinelabs_fake": "35", "delhivery_fake": "35", "curtain_request": "35", "curtain_reply": "35"}
if os.name == "nt": os.system("")   # enables colours in the Windows terminal
def _fmt(v):
    if isinstance(v, str):
        try:
            j = json.loads(v)
            if isinstance(j, (dict, list)): v = j
        except Exception: pass
    return json.dumps(v, ensure_ascii=False, indent=2, default=str) if isinstance(v, (dict, list)) else str(v)
def _console(kind, kw):
    head = f"\x1b[{_COL.get(kind, '37')}m[{datetime.datetime.now():%H:%M:%S}] {kind.upper()}\x1b[0m"
    body = "".join(f"\n  {k}: " + _fmt(v).replace("\n", "\n    ") for k, v in kw.items())
    print(head + body + "\n", flush=True)

def log(kind, **kw):
    rec = {"t": datetime.datetime.now().isoformat(timespec="seconds"), "kind": kind, **kw}
    with LOGFILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    _console(kind, kw)

def _scrub(x):
    s_ = str(x)
    for k in ("TELEGRAM_BOT_TOKEN", "WHATSAPP_TOKEN", "GEMINI_API_KEY"):
        v = os.getenv(k)
        if v: s_ = s_.replace(v, "***")
    return s_

# ---------- real connectors ----------
CHANNEL = os.getenv("CHANNEL", "whatsapp").lower()
TG = {"chat": os.getenv("TELEGRAM_CHAT_ID", "")}

def tg_send(body):
    try:
        import requests
        if not TG["chat"]: return {"sent": False, "error": "no telegram chat yet: the claimant must message the bot first"}
        r = requests.post(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
                          json={"chat_id": TG["chat"], "text": body}, timeout=20)
        if r.status_code >= 300: raise RuntimeError(r.text)
        return {"sent": True}
    except Exception as e:
        log("error", where="telegram", msg=_scrub(repr(e))); return {"sent": False, "error": _scrub(e)}

def tg_poll():
    import requests
    base = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}"; off = 0
    while True:
        try:
            r = requests.get(base + "/getUpdates", params={"timeout": 30, "offset": off}, timeout=40).json()
            for u in r.get("result", []):
                off = u["update_id"] + 1; m = u.get("message") or {}
                if m.get("text"):
                    cid = str(m["chat"]["id"])
                    if not TG["chat"]: TG["chat"] = cid; log("info", msg="telegram chat locked to " + cid)
                    if cid == TG["chat"]: post_event("Chat message from the claimant: " + m["text"])
        except Exception as e:
            log("error", where="telegram_poll", msg=_scrub(repr(e))); time.sleep(5)

def wa_send(body):
    body = _norm_ids(body); log("whatsapp_out", body=body)
    if CHANNEL == "telegram": return tg_send(body)
    try:
        import requests
        r = requests.post(f"https://graph.facebook.com/{GRAPH}/{os.environ['WHATSAPP_PHONE_ID']}/messages",
            headers={"Authorization": "Bearer " + os.environ["WHATSAPP_TOKEN"]}, timeout=20,
            json={"messaging_product": "whatsapp", "to": RAVI, "type": "text", "text": {"body": body, "preview_url": True}})
        if r.status_code >= 300: raise RuntimeError(r.text)
        return {"sent": True}
    except Exception as e:
        log("error", where="whatsapp", msg=_scrub(repr(e))); return {"sent": False, "error": _scrub(e)}

def t_whatsapp_send(body): return wa_send(body)
def t_send_otp():
    new_otp(); STATE["otp_pending"] = True; STATE["otp_ok"] = False; STATE["stage"] = "authorize"
    return wa_send(f"Your Vasool code is {OTP['code']}. It confirms your claim details. Do not share it.")
DOC_TYPE_ALIASES = {
    "claim_form": ["claim form", "insurance claim form", "reimbursement claim form", "reimbursement claim"],
    "tpa_card": ["tpa card", "tpa health card", "health insurance card", "insurance card", "member card", "vidal health", "vidal tpa card", "cashless hospitalisation card", "cashless hospitalization card", "health card", "member id card"],
    # The supplied fictional sample is an employer-issued employee identity card;
    # the demo checklist accepts this as the identity-proof document.
    "id_proof": ["identity proof", "identity document", "employee identity card", "employee id", "employee id card", "corporate identity card", "corporate id", "aadhaar", "aadhar", "pan card", "passport", "driving licence", "driving license", "voter id", "voter identity"],
    "discharge_summary": ["discharge summary", "discharge report", "hospital discharge", "discharge certificate"],
    "inpatient_bills": ["inpatient bill", "in-patient bill", "final in-patient bill", "final inpatient bill", "hospital bill", "final hospital bill", "hospital invoice", "hospital final bill"],
    "prescription": ["prescription", "doctor prescription", "medical prescription", "doctor's prescription", "rx"],
    "pharmacy_bills": ["pharmacy bill", "pharmacy bills", "pharmacy invoice", "inpatient pharmacy bill", "in-patient pharmacy", "medicine bill", "medical store bill", "drug bill"],
    "investigation_reports": ["investigation report", "investigation reports", "mri", "mrcp", "ecg", "ct scan", "ct report", "x-ray", "x ray", "ultrasound", "diagnostic report", "diagnostic reports", "imaging report"],
    "lab_reports": ["lab report", "laboratory report", "pathology report", "blood test report", "test report", "clinical laboratory report"],
    "paid_receipt": ["paid receipt", "payment receipt", "hospital receipt", "paid bill receipt", "payment acknowledgement", "receipt"],
    "registration_copy": ["hospital registration", "registration copy", "registration certificate", "hospital registration copy", "certificate of registration", "attested true copy"],
}

DOCS_REQUIRING_SEAL_SIGNATURE = {"discharge_summary", "inpatient_bills", "paid_receipt", "pharmacy_bills"}


def _type_matches(doc, detected_type):
    def n(s):
        return re.sub(r"[^a-z0-9]+", "", str(s).lower())
    d = n(detected_type)
    if not d:
        return False
    if n(doc) in d or d in n(doc):
        return True
    return any(n(alias) in d for alias in DOC_TYPE_ALIASES.get(doc, []))


def _norm(s):
    return " ".join(str(s or "").lower().split())

def _contains_name(evidence):
    e = _norm(evidence)
    name = _norm(STATE.get("profile", {}).get("name", ""))
    if not name:
        return False
    return name in e

_NEG_WORDS = {"no", "not", "without", "missing", "absent", "unsigned", "unstamped", "lacks", "lacking", "cannot", "cant",
              "can't", "couldn't", "couldnt", "unable", "illegible", "unclear", "blank", "none", "isn't", "isnt", "wasn't", "wasnt"}
def _has_positive(evidence, terms):
    """True if a term appears affirmatively (not 'no seal', 'seal missing', 'unsigned')."""
    for clause in re.split(r"[.;,\n]", _norm(evidence)):
        for t in terms:
            for m in re.finditer(re.escape(_norm(t)), clause):
                if m.start() > 0 and clause[m.start() - 1].isalpha():
                    continue
                before = re.findall(r"[\w']+", clause[:m.start()])[-3:]
                after = re.findall(r"[\w']+", clause[m.end():])[:3]
                if not any(w in _NEG_WORDS for w in before + after):
                    return True
    return False

def _contains_any(evidence, terms):
    e = _norm(evidence)
    return any(_norm(t) in e for t in terms)

def _has_required_evidence(doc, evidence):
    e = _norm(evidence)
    if len(e) < 15:
        return False
    if doc in DOCS_REQUIRING_SEAL_SIGNATURE:
        return _has_positive(e, ["seal", "stamp"])   # "no seal" / "seal missing" still fails
    return True

    # These three slots explicitly require both the hospital seal/stamp and a
    # signature in the sample checklist.
    if doc in DOCS_REQUIRING_SEAL_SIGNATURE:
        has_seal = _has_positive(e, ["seal", "stamp", "hospital seal", "hospital stamp"])
        has_signature = _has_positive(e, ["signature", "signed", "doctor signature", "accounts officer", "cashier", "pharmacist"])
        # Paid-receipt evidence from the model can be concise. For this slot, a
        # receipt number plus payment amount plus an explicitly visible seal is
        # strong evidence; signature wording is encouraged by the prompt but is
        # not required to be repeated in the evidence sentence if the model has
        # clearly identified the receipt and seal.
        if doc == "paid_receipt":
            return (has_seal
                    and _contains_any(e, ["receipt number", "receipt ref", "sun/rc/", "payment receipt", "receipt"])
                    and (re.search(r"\brs(?![a-z])|₹", e) or _contains_any(e, ["payment", "paid", "amount"]))
                    and (_contains_name(evidence) or _contains_any(e, ["sunrise", "claimant", "upi"])))
        return has_seal and has_signature and (_contains_name(evidence) or _contains_any(e, ["sunrise", "claimant"]))

    if doc == "id_proof":
        # For this simulation, an employee identity card is accepted as identity
        # proof. Require the claimant identity to be visible and an actual ID
        # attribute to be identified by the model.
        return (_contains_name(evidence)
                and _contains_any(e, ["employee id", "employee identity", "dob", "date of birth", "address", "identity card"]))

    if doc == "tpa_card":
        primary_id = str(STATE.get("basics", {}).get("primary_id", "")).lower().strip()
        return (_contains_any(e, ["vidal", "tpa", "insurance card", "cashless hospitalisation", "cashless hospitalization"])
                and (bool(primary_id) and primary_id in e or _contains_any(e, ["member id", "policy number", "member number"])))

    # For the remaining document types, require concrete evidence from the file
    # rather than a generic "looks good" assertion.
    return _contains_name(evidence) or _contains_any(e, ["sunrise", "claim number", "member id", "policy", "bill number", "report number", "receipt number", "registration"])

def t_webapp_doc(doc, status, reason="", detected_type="", evidence=""):
    if doc not in STATE["docs"]:
        return {"ok": False, "error": f"unknown doc id {doc}"}
    if status not in ("verified", "missing", "retake"):
        return {"ok": False, "error": "status must be verified, missing, or retake"}

    uploaded = doc in UPLOADED_DOCS
    if status in ("verified", "retake") and not uploaded:
        return {"ok": False, "error": "document was never uploaded; mark it as missing"}
    if status == "missing" and uploaded:
        return {"ok": False, "error": "document was uploaded; use verified or retake"}

    version = DOC_VERSIONS.get(doc, 0)
    # Once this upload version has failed, the same file cannot be promoted
    # to VERIFIED without a new upload. This is an application-level gate,
    # independent of Gemini's next response.
    if status == "verified" and RETAKE_VERSIONS.get(doc) == version:
        STATE["waiting_for_docs"] = True
        return {
            "ok": False,
            "status": "retake",
            "blocked": "awaiting_new_upload",
            "error": f"This upload version was already rejected. Wait for a new upload before re-verifying {doc}."
        }

    detected_type = str(detected_type or "").strip()
    evidence = str(evidence or reason or "").strip()

    # A green result is allowed only when Gemini identifies the actual uploaded
    # document type and provides concrete evidence from the file. The backend
    # then applies deterministic consistency checks so a generic model reply
    # cannot turn an arbitrary upload into a green check.
    if status == "verified":
        if not _type_matches(doc, detected_type):
            status = "retake"
            reason = f"Wrong document type. AI identified this as '{detected_type or 'unknown document'}', but this slot requires '{DOCS[doc]}'."
        elif not _has_required_evidence(doc, evidence):
            status = "retake"
            if doc in DOCS_REQUIRING_SEAL_SIGNATURE:
                reason = "The AI could not verify the required hospital seal/stamp, signature, and claimant/hospital evidence from the uploaded file."
            elif doc == "id_proof":
                reason = "The AI identified the file as identity proof but could not clearly verify the claimant name and an identity attribute from the uploaded file."
            elif doc == "tpa_card":
                reason = "The AI identified an insurance/TPA card but could not verify the claimant/member information from the uploaded file."
            else:
                reason = "The AI did not provide enough concrete evidence from the uploaded file to verify it."

    STATE["docs"][doc].update(status=status, reason=reason, detected_type=detected_type, evidence=evidence)
    if status == "retake":
        RETAKE_VERSIONS[doc] = version
        VERIFIED_VERSIONS.pop(doc, None)
        # Keep the claimant on the document-verification screen during intake
        # so the replacement upload control is visible. Do not advance to
        # calling/settlement until the rejected file is replaced and verified.
        if STATE.get("stage") in ("docs", "verify"):
            STATE["stage"] = "verify"
    elif status == "verified":
        VERIFIED_VERSIONS[doc] = version
        RETAKE_VERSIONS.pop(doc, None)
    unresolved = any(STATE["docs"][k].get("status") in ("missing", "retake", "empty", "uploaded") for k in REQUIRED_R3_DOCS)
    STATE["waiting_for_docs"] = unresolved
    return {"ok": True, "status": status, "detected_type": detected_type, "evidence": evidence, "reason": reason}

def t_webapp_note(text): STATE["note"] = text; return {"ok": True}
_DLV_CHATTER = re.compile(r"field executive|out to collect|processing cent|in transit|pickup request created|pickup scheduled|picked up|dispatched for delivery|out for delivery|signature (captured|received|confirms)|(package|documents|shipment) (delivered|reached|out)|delivered to sanjeevani|awaiting confirmation|sorting hub", re.I)
_EARLY_LINE = re.compile(r"otp|fee hold|hold confirmed|dispatched|mandate|authori[sz]|pickup booked|audit|claim form|verified", re.I)
_RECEIPT_LINE = re.compile(r"receipt confirmed|confirmed receipt|claim number|receipt of", re.I)
_CAPTURE_LINE = re.compile(r"captur|1,499", re.I)
def _norm_ids(s):
    s = re.sub(r"SJV-?CL-?(\d{4})-?(\d{5})\b", r"SJV-CL-\1-\2", str(s), flags=re.I)
    return re.sub(r"\bVH-?SN-?(\d{5})\b", r"VH-SN-\1", s, flags=re.I)
def _fmt_dt(ts):
    d = datetime.datetime.fromtimestamp(ts)
    return f"{d.day} {d.strftime('%b')}, {d.strftime('%I:%M %p').lstrip('0')}"
def t_webapp_timeline(text):
    # One story, in time order. The scheduled tracker owns the delivery steps; the agent's lines are placed where they belong in the story.
    text = _norm_ids(text); when = key = None
    if STATE.get("payment_approved"):
        sched, ts = _mock_schedule()
        if _DLV_CHATTER.search(text):
            return {"ok": True, "note": "already shown by the delivery tracker"}
        if _EARLY_LINE.search(text):                          # authorisation / dispatch lines keep their real time
            hold = next((e for e in STATE["timeline"] if str(e.get("text", "")).startswith("Pine Labs fee hold active")), None)
            if hold and re.search(r"\botp\b", text, re.I):          # the OTP came before the fee hold, even if the agent wrote it later
                _add_demo_timeline(text, hold["t"], hold["k"] - 0.001, exact=True); return {"ok": True}
        elif _RECEIPT_LINE.search(text):
            key = ts["Receipt confirmed"] + 60; when = _fmt_dt(key)
        elif STATE.get("final_phase"):                        # after the 7-working-day clock event: payout and fee capture
            STATE["final_phase"] += 1
            key = ts["Amount processed"] + (120 if _CAPTURE_LINE.search(text) else 0) + STATE["final_phase"]
            when = _fmt_dt(key)
    _add_demo_timeline(text, when, key)
    return {"ok": True}
def t_webapp_summary(text): STATE["summary"] = text; return {"ok": True}
UI_KEYS = {"stage", "elig", "note", "transcript", "form", "pay", "signature", "summary"}
ORDER = ["identity", "basics", "docs", "verify", "calling", "note", "eligibility", "form", "audit", "pickup", "authorize", "track", "settled"]
AUTO = {"note": "note", "elig": "eligibility", "form": "form", "signature": "track", "summary": "settled"}
def t_webapp_set(key, value):
    if isinstance(value, str): value = _norm_ids(value)
    if key not in UI_KEYS:
        return {"ok": False, "error": "unknown key " + key}
    try:
        v = json.loads(value)
    except Exception:
        v = value
    if key == "stage" and v not in ORDER:
        return {"ok": False, "error": "unknown stage " + str(v)}
    if key in ("elig", "note", "summary") and not isinstance(v, dict):
        return {"ok": False, "error": key + " must be a JSON object"}

    if key == "stage" and v == "audit":
        # Deterministic application logic: only required checklist items that
        # were never uploaded become "missing". Registration copy is optional.
        for doc in REQUIRED_R3_DOCS:
            info = STATE["docs"][doc]
            if info.get("status") == "empty":
                info.update(status="missing", reason="Not uploaded yet — upload this document to continue.")
        STATE["waiting_for_docs"] = any(
            STATE["docs"][doc].get("status") in ("missing", "retake", "empty", "uploaded")
            for doc in REQUIRED_R3_DOCS
        )

    if key == "stage" and v == "pickup":
        unresolved = [
            doc for doc in REQUIRED_R3_DOCS
            if STATE["docs"][doc].get("status") != "verified"
        ]
        if STATE.get("note") is None:
            unresolved.append("settlement_note")
        if unresolved:
            return {"ok": False, "error": "cannot move to pickup; unresolved items: " + ", ".join(unresolved)}

    STATE[key] = v
    nxt = AUTO.get(key)
    if nxt and ORDER.index(nxt) > ORDER.index(STATE["stage"]):
        STATE["stage"] = nxt
    return {"ok": True}
def t_gmail_send(subject, body): log("gmail_out", subject=subject, body=body); return {"ok": False, "error": "gmail connector not connected yet"}
def t_sheets_append(row): log("sheets_out", row=row); return {"ok": False, "error": "sheets connector not connected yet"}

# ---------- curtain connectors (human pastes the real response) ----------
def curtain(connector, name, body):
    if connector == "gnani" and GNANI_FAKE:
        time.sleep(1.5); res = gnani_fake(name, body); log("gnani_replay", name=name, body=body, response=res); return {"response": res}
    rid = uuid.uuid4().hex[:6]; ev = threading.Event()
    PEND[rid] = {"id": rid, "connector": connector, "name": name, "body": body, "event": ev, "reply": None,
                 "t": datetime.datetime.now().strftime("%H:%M:%S")}
    log("curtain_request", id=rid, connector=connector, name=name, body=body)
    ev.wait(timeout=3600)
    p = PEND.pop(rid); r = p["reply"]
    DONE.append({"id": rid, "connector": connector, "name": name, "t": p["t"]})
    log("curtain_reply", id=rid, reply=r)
    if r is None: return {"error": "no response arrived (timeout)"}
    try: r = json.loads(r)
    except Exception: pass
    return {"response": r}

def t_gnani_call(request): return curtain("gnani", "trigger_call", request)
def t_gnani_get_stats(conversation_id): return curtain("gnani", "GET /v1/conversations/{id}/stats", conversation_id)
# _docshape: Pine Labs fake follows the UPI One-Time Mandate docs (amounts in paise; Rs 1,499 = 149900)
def _pl_ts(): return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
def _pl_id(p): return f"v1-{p}-{datetime.datetime.utcnow():%y%m%d%H%M%S}-aa-{uuid.uuid4().hex[:6]}"
def t_pinelabs(endpoint, body):
    if not PINE_FAKE: return curtain("pinelabs", endpoint, body)
    if PINE["n"] == 0:
        for k in ("cust", "sub", "order", "amount", "pres", "pres_ref", "paid"): PINE.pop(k, None)
    PINE["n"] += 1; e = str(endpoint).lower(); b = _jb(body)
    post = "get " not in e[:5]
    if "token" in e:
        res = {"access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ2YXNvb2wifQ.c2lnbmF0dXJl", "expires_in": 3600}
    elif "customer" in e:
        PINE["cust"] = "cust-v1-" + uuid.uuid4().hex[:12]
        res = {"customer_id": PINE["cust"], "global_customer_id": "pl-v1-" + uuid.uuid4().hex[:12], "customer_key": "ck-v1-" + uuid.uuid4().hex[:10],
               "first_name": b.get("first_name", "Ravi"), "last_name": b.get("last_name", "Menon"), "country_code": "91", "mobile_number": b.get("mobile_number", ""),
               "email_id": b.get("email_id", ""), "status": "ACTIVE", "created_at": _pl_ts(), "updated_at": _pl_ts()}
    elif "subscriptions/ot" in e and post and "{" not in e.split("subscriptions/ot")[-1][:2] and not e.split("subscriptions/ot")[-1].strip("/ ").startswith(("v1-sub", "<")):
        pd = b.get("plan_details", {}); PINE["amount"] = int(pd.get("amount", 149900)); PINE["sub"] = _pl_id("sub"); PINE["order"] = _pl_id("ord")
        res = {"subscription_id": PINE["sub"], "order_id": PINE["order"], "customer_id": b.get("customer_id", PINE.get("cust", "")), "status": "CREATED",
               "execution_mode": "DIRECT_EXECUTION", "start_date": _pl_ts(), "end_date": _pl_ts(),
               "plan_details": {"amount": PINE["amount"], "currency": "INR", "validity_days": pd.get("validity_days", 30), "description": pd.get("description", "Vasool service fee hold"), "frequency": "OT"},
               "merchant_subscription_reference": b.get("merchant_subscription_reference", ""), "redirect_url": None}
    elif "/payments" in e:
        v = (b.get("payments") or [{}])[0].get("payment_amount", {}).get("value", PINE.get("amount", 149900)); PINE["mandate_requested"] = True
        res = {"data": {"order_id": PINE.get("order", _pl_id("ord")), "type": "CHARGE", "status": "PENDING", "challenge_url": None,
                        "order_amount": {"value": v, "currency": "INR"}, "allowed_payment_methods": ["UPI"],
                        "payments": [{"id": _pl_id("pay") + "-up", "merchant_payment_reference": (b.get("payments") or [{}])[0].get("merchant_payment_reference", ""), "status": "PENDING",
                                      "payment_amount": {"value": v, "currency": "INR"}, "payment_method": "UPI", "payment_option": {"upi_data": {"txn_mode": "INTENT"}},
                                      "created_at": _pl_ts(), "updated_at": _pl_ts()}], "created_at": _pl_ts(), "updated_at": _pl_ts()}}
    elif "presentations/reference" in e or ("presentations/" in e and not post):
        res = {"subscription_id": PINE.get("sub", ""), "presentation_id": PINE.get("pres", ""), "merchant_presentation_reference": PINE.get("pres_ref", ""),
               "amount": {"value": PINE.get("amount", 149900), "currency": "INR"}, "status": "SUCCESS", "order_id": _pl_id("ord"), "failure_count": 0}
    elif "presentations" in e:
        if not STATE.get("payment_approved"):
            res = {"code": "INVALID_SUBSCRIPTION_STATE", "message": "Presentation can be created only when the subscription is ACTIVE or RESUMED"}
        elif PINE.get("pres"):
            res = {"code": "DUPLICATE_PRESENTATION", "message": "A presentation already exists for this one-time mandate"}
        else:
            amt = (b.get("amount") or {}).get("value", PINE.get("amount", 149900)); PINE["pres"] = _pl_id("bil"); PINE["pres_ref"] = b.get("merchant_presentation_reference", "")
            PINE["active"] = True
            res = {"subscription_id": b.get("subscription_id", PINE.get("sub", "")), "presentation_id": PINE["pres"], "due_date": _pl_ts(), "amount": {"value": amt, "currency": "INR"},
                   "merchant_presentation_reference": PINE["pres_ref"], "pdn_status": "NOT_APPLICABLE", "status": "PENDING", "failure_count": 0, "order_id": _pl_id("ord")}
    elif "subscriptions" in e:
        ok = bool(STATE.get("payment_approved")); PINE["active"] = ok
        res = {"subscription_id": PINE.get("sub", ""), "order_id": PINE.get("order", ""), "customer_id": PINE.get("cust", ""), "status": "ACTIVE" if ok else "CREATED",
               "execution_mode": "DIRECT_EXECUTION", "plan_details": {"amount": PINE.get("amount", 149900), "currency": "INR", "frequency": "OT"}}
    else:
        res = {"code": "NOT_FOUND", "message": "Unknown Pine Labs endpoint in this simulation: " + str(endpoint)}
    log("pinelabs_fake", endpoint=endpoint, body=body, response=res)
    return {"response": res}

# _docshape: Delhivery fake follows the Express API docs and the reverse-pickup (RVP) status table
DLV = {"gen": -1, "n": 0}
_RVP = [("PP", "Open", "Pickup request created"), ("PP", "Scheduled", "Pickup scheduled"), ("PP", "Dispatched", "Field executive out to collect the package"),
        ("PU", "In Transit", "Package picked up, in transit to the processing centre"), ("PU", "Pending", "Package reached the processing centre"),
        ("PU", "Dispatched", "Package dispatched for delivery to the client"), ("DL", "DTO", "Pickup shipment accepted by client and POD received")]
def t_delhivery(endpoint, body):
    if not DELHIVERY_FAKE: return curtain("delhivery", endpoint, body)
    if DLV["gen"] != DELIVERY_GEN: DLV.update(gen=DELIVERY_GEN, n=0)
    e = str(endpoint).lower(); wb = STATE["delivery"]["tracking_id"]; now = datetime.datetime.now()
    if "cmu/create" in e:
        res = {"cash_pickups_count": 0, "package_count": 1, "upload_wbn": "UPL" + uuid.uuid4().hex[:10].upper(), "replacement_count": 0, "pickups_count": 1,
               "packages": [{"status": "Success", "client": "VASOOL_MAIN", "sort_code": "HYD/BJH", "remarks": [""], "waybill": wb, "cod_amount": 0, "payment": "Pickup", "serviceable": True, "refnum": "VSL-" + now.strftime("%y%m%d")}],
               "cash_pickups": 0.0, "success": True, "prepaid_count": 0, "cod_count": 0, "cod_amount": 0.0}
    elif "fm/request" in e or "pickup" in e and "packages" not in e:
        b = _jb(body); res = {"pickup_id": 44000000 + int(now.strftime("%H%M%S")), "pickup_location": b.get("pickup_location", "VASOOL_MAIN"),
                              "pickup_date": b.get("pickup_date", now.strftime("%Y-%m-%d")), "pickup_time": b.get("pickup_time", "11:00:00"), "expected_package_count": b.get("expected_package_count", 1)}
    elif "fetch/pkg/document" in e or "doc_type" in e or "signature" in e or "epod" in e:
        dt = "EPOD" if "epod" in e else "SIGNATURE_URL"
        res = {"waybill": wb, "doc_type": dt, "url": "/demo-signature"}
    else:
        k = min(DLV["n"], len(_RVP) - 1); DLV["n"] += 1; scans = []
        for i in range(k + 1):
            t, sname, ins = _RVP[i]; ts = (now + datetime.timedelta(minutes=i * 40)).strftime("%Y-%m-%dT%H:%M:%S")
            scans.append({"ScanDetail": {"ScanDateTime": ts, "ScanType": t, "Scan": sname, "StatusDateTime": ts, "ScannedLocation": "Hyderabad_Madhapur_D (Telangana)" if i < 3 else "Hyderabad_Banjara_D (Telangana)", "Instructions": ins, "StatusCode": ""}})
        t, sname, ins = _RVP[k]
        res = {"ShipmentData": [{"Shipment": {"AWB": wb, "ReferenceNo": "VSL-" + now.strftime("%y%m%d"), "Status": {"Status": sname, "StatusLocation": scans[-1]["ScanDetail"]["ScannedLocation"], "StatusDateTime": scans[-1]["ScanDetail"]["ScanDateTime"], "StatusType": t, "Instructions": ins}, "Scans": scans}}]}
    log("delhivery_fake", endpoint=endpoint, body=body, response=res)
    return {"response": res}

# _docshape: Trigger Call does not return a conversationId, so the agent must look it up
def t_gnani_find_conversation(search_term):
    return curtain("gnani", "POST /v1/conversations/logs", {"searchTerm": search_term, "pageNo": 1, "pageSize": 5})


SPEC = [
 ("whatsapp_send", "Send a WhatsApp message to the claimant. One-way: updates and 'action needed' pings with the web app link. Never ask for anything in WhatsApp.", {"body": "Message text"}),
 ("send_otp", "Send the claimant a one-time code on WhatsApp. You never see the code; you are told when the claimant enters it correctly in the web app.", {}),
 ("webapp_doc", "Set a document status only after inspecting the actual uploaded file. For verified, detected_type must name what the image/PDF actually is and evidence must state concrete visual/text checks from the file. The backend validates that the detected type matches the requested slot and that required evidence is present. For this simulation, an employer-issued employee identity card is an acceptable identity-proof document. Use missing only when never uploaded; use retake for wrong/illegible documents or failed seal/signature checks.", {"doc": "document id", "status": "verified, missing, or retake", "reason": "concise outcome/reason; exact problem for retake or missing", "detected_type": "what the AI actually identifies the uploaded document as", "evidence": "concrete evidence observed in the uploaded file: legibility, names/IDs, dates, seal/stamp/signature where required"}),
 ("webapp_note", "Show a short message at the top of the claimant's web app screen.", {"text": "message"}),
 ("webapp_timeline", "Add a progress line to the claimant's timeline in the web app.", {"text": "line"}),
 ("webapp_summary", "Show the final summary in the web app.", {"text": "summary"}),
 ("gmail_send", "Email the human reviewer. Escalations only.", {"subject": "subject", "body": "body"}),
 ("sheets_append", "Append one row to the claim tracker sheet.", {"row": "JSON array of cell values, as a string"}),
 ("gnani_call", "Place a voice call to a whitelisted number through Gnani. Returns the real Gnani response.", {"request": "JSON body for the Gnani trigger_call API"}),
 ("gnani_get_stats", "Fetch GET /v1/conversations/{conversationId}/stats for a call.", {"conversation_id": "conversation id"}),
 ("pinelabs", "Call a Pine Labs API. Returns the API's response.", {"endpoint": "method and path", "body": "JSON body"}),
 ("delhivery", "Call a Delhivery API. Returns the API's response.", {"endpoint": "method and path", "body": "JSON body"}),
]
SPEC[:] = [x for x in SPEC if x[0] not in ("webapp_note", "webapp_summary")] + [("webapp_set",
 "Drive the claimant's web app screen. key is one of: stage, elig, note, transcript, form, pay, signature, summary. value is JSON (or a plain string for stage and signature). See the system prompt for each shape.",
 {"key": "key name", "value": "JSON text"})]
SPEC.append(("gnani_find_conversation", "Find the conversationId of a call you just triggered: POST /v1/conversations/logs with searchTerm (the clientReferenceId or name you sent). Trigger Call does not return a conversationId. Retry once after a short wait if the list is empty.", {"search_term": "clientReferenceId or name used in trigger_call"}))
for _i, _x in enumerate(SPEC):
    if _x[0] == "gnani_call": SPEC[_i] = ("gnani_call", "Place an outbound call through Gnani: POST /v1/agents/{botId}/trigger_call?environment=development. Body JSON: phone (10 digits, no country code), countryCode (+91), name, clientReferenceId (a purpose label such as TPA_SETTLEMENT-<claim no>). Only whitelisted numbers work. The response has NO conversationId.", {"request": "JSON body for trigger_call"})
    if _x[0] == "gnani_get_stats": SPEC[_i] = ("gnani_get_stats", "GET /v1/conversations/{conversationId}/stats. Returns callStatus, overallCallDisposition and utteranceAnalytics (role assistant = your call agent, user = the person called).", {"conversation_id": "conversationId from gnani_find_conversation"})
TOOLS = {n: globals()["t_" + n] for n, _, _ in SPEC}

def decl(name, desc, props):
    d = dict(name=name, description=desc)
    if props:
        d["parameters"] = {"type": "OBJECT", "required": list(props),
                           "properties": {k: {"type": "STRING", "description": v} for k, v in props.items()}}
    return types.FunctionDeclaration(**d)

CFG = types.GenerateContentConfig(system_instruction=PROMPT, temperature=0.2,
        tools=[types.Tool(function_declarations=[decl(*s) for s in SPEC])],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))

# ---------- the agent loop ----------
HIST, EVQ = [], queue.Queue()

TRANSIENT = ("429", "500", "502", "503", "504", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "overloaded", "high demand", "DEADLINE")
FALLBACK = os.getenv("GEMINI_FALLBACK_MODEL", "")
def gen():
    global client
    if client is None: client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    waits = [4, 8, 15, 25, 40, 60]; last = None
    for i, w in enumerate(waits + [0]):
        model = FALLBACK if (FALLBACK and i >= 4) else MODEL
        try: return client.models.generate_content(model=model, contents=HIST, config=CFG)
        except Exception as e:
            last = e
            if not any(t in str(e) for t in TRANSIENT): raise
            if i < len(waits):
                log("warn", msg=f"Gemini busy ({str(e)[:60]}), retry in {w}s on {FALLBACK if (FALLBACK and i + 1 >= 4) else MODEL}"); time.sleep(w)
    raise last

def strip_media():
    # Once Gemini has received and reviewed an uploaded file, replace the raw
    # bytes in conversation history with a small marker.  This is critical for
    # Flash-Lite quota: otherwise every follow-up tool-call turn resends every
    # PDF/image in the conversation.
    for c in HIST:
        if c.parts:
            c.parts = [types.Part(text="[uploaded file, already reviewed]") if p.inline_data else p for p in c.parts]

def _all_currently_uploaded_verified():
    if not UPLOADED_DOCS:
        return False
    return all(
        STATE["docs"][doc].get("status") == "verified"
        and VERIFIED_VERSIONS.get(doc) == DOC_VERSIONS.get(doc)
        for doc in UPLOADED_DOCS
    )

def turn(parts):
    n0 = len(HIST); HIST.append(types.Content(role="user", parts=parts))
    max_steps = int(os.getenv("MAX_AGENT_STEPS", "14"))
    for _ in range(max_steps):
        try: r = gen()
        except Exception as e:
            if len(HIST) == n0 + 1: del HIST[n0:]; e.clean = True
            raise
        if not r.candidates or not r.candidates[0].content:
            log("warn", msg="model returned no content"); break
        c = r.candidates[0].content; HIST.append(c)
        # Do not resend raw document bytes on the next agent-loop iteration.
        # Gemini has already inspected them in this response.
        strip_media()
        ps = c.parts or []
        for p in ps:
            if p.text: log("decision", text=p.text)
        calls = [p.function_call for p in ps if p.function_call]
        if not calls:
            stage = STATE.get("stage")
            otp_pending = bool(STATE.get("otp_pending"))
            otp_ok = bool(STATE.get("otp_ok"))

            # These stages legitimately wait for the outside world / claimant.
            # Everything else should continue with tool calls rather than ending
            # merely because Gemini produced a text-only response.
            if stage in ("identity", "basics", "docs", "verify", "eligibility", "pickup"):
                break

            if stage == "audit" and STATE.get("waiting_for_docs"):
                # The claimant needs to upload/fix documents. An upload event
                # will wake the agent again; do not burn Gemini calls while waiting.
                break

            if stage == "authorize" and otp_pending and not otp_ok:
                # send_otp has already happened; now the claimant must enter it.
                break

            if stage in ("calling", "note", "form", "audit", "track") or (stage == "authorize" and (otp_ok or not otp_pending)):
                HIST.append(types.Content(
                    role="user",
                    parts=[types.Part(text=(
                        f"CONTINUE THE AGENT WORK. You are currently in stage '{stage}'. "
                        "Do not end with a text-only response. Follow the system prompt and make the required tool call(s) now. "
                        "Do not merely describe what you would do. "
                        "For R3 audit, call webapp_doc for every checklist item and use missing for never-uploaded documents. "
                        "For authorize after OTP, create/confirm the Pine Labs hold as required. "
                        "For track, continue the required Delhivery/insurer tracking calls."
                    ))]
                ))
                continue

            # If an unfamiliar stage ever appears, preserve the old safe behavior.
            break
        out = []
        pause_for_documents = False
        for fc in calls:
            args = dict(fc.args or {})
            try: res = TOOLS[fc.name](**args)
            except Exception as e: res = {"error": repr(e)}
            log("tool", name=fc.name, args=args, result=res)
            out.append(types.Part.from_function_response(name=fc.name, response=res if isinstance(res, dict) else {"result": res}))
            # A missing/failed document is a hard wait point. Do not let Gemini
            # reconsider the same file or consume more quota until a new upload
            # event arrives.
            if isinstance(res, dict) and (
                res.get("blocked") == "awaiting_new_upload"
                or res.get("status") in ("missing", "retake")
            ):
                pause_for_documents = True
        HIST.append(types.Content(role="user", parts=out))
        if pause_for_documents:
            break

        # R0 is complete once every file that has actually been uploaded in the
        # current intake batch has been AI-verified.  Move deterministically to
        # the next agent state instead of spending another model turn merely to
        # request the same state transition.  This does NOT bypass the AI
        # verification; it only removes redundant orchestration tokens.
        if STATE.get("stage") in ("docs", "verify") and _all_currently_uploaded_verified():
            STATE["stage"] = "calling"
            STATE["waiting_for_docs"] = False
            _add_demo_timeline("All uploaded intake documents passed AI verification. Starting settlement note retrieval.")
            log("state_advance", from_stage="docs", to_stage="calling", reason="all uploaded intake documents verified")
            post_event("R0 intake verification is complete. Begin R2 settlement-note retrieval from the primary TPA.")
            break

        time.sleep(2)
    strip_media()

def worker():
    tries = {}
    while True:
        parts = EVQ.get()
        try: turn(parts)
        except Exception as e:
            log("error", where="agent", msg=repr(e)[:300])
            k = id(parts); tries[k] = tries.get(k, 0) + 1
            if getattr(e, "clean", False) and tries[k] <= 3:
                log("warn", msg="re-queueing the message in 20s"); time.sleep(20); EVQ.put(parts)

def post_event(text, files=()):
    parts = [types.Part(text=text)]
    for label, data, mime in files:
        parts += [types.Part(text=f"[file: {label}]"), types.Part.from_bytes(data=data, mime_type=mime)]
    log("event", text=text); EVQ.put(parts)

def _flush_doc_batch():
    global DOC_BATCH_TIMER, DOC_BATCH, DOC_BATCH_NAMES
    with DOC_BATCH_LOCK:
        files = list(DOC_BATCH)
        names = list(DOC_BATCH_NAMES)
        DOC_BATCH.clear()
        DOC_BATCH_NAMES.clear()
        DOC_BATCH_TIMER = None
    if not files:
        return
    intro = f"The claimant {json.dumps(STATE['profile'])} confirmed: {json.dumps(STATE['basics'])}. "
    post_event(intro + "The claimant submitted these documents in the web app: " + ", ".join(names) + ". Files are attached.", files)

def post_doc_event(files, names, first):
    global DOC_BATCH_TIMER, DOC_BATCH, DOC_BATCH_NAMES
    with DOC_BATCH_LOCK:
        DOC_BATCH.extend(files)
        DOC_BATCH_NAMES.extend(names)
        # Keep collecting while the claimant is uploading. Every new upload
        # resets the timer, so the agent starts only after the user pauses.
        if DOC_BATCH_TIMER is not None:
            DOC_BATCH_TIMER.cancel()
        DOC_BATCH_TIMER = threading.Timer(DOC_UPLOAD_SETTLE_SECONDS, _flush_doc_batch)
        DOC_BATCH_TIMER.daemon = True
        DOC_BATCH_TIMER.start()
    log("doc_batch_wait", first=first, names=names, settle_seconds=DOC_UPLOAD_SETTLE_SECONDS)

# ---------- deterministic demo logistics ----------
DEMO_DELIVERY_STEPS = [
    (0.0, "Pickup scheduled", "Delhivery pickup scheduled from your address."),
    (3.0, "Pickup agent assigned", "Delhivery pickup agent assigned for the selected slot."),
    (6.0, "Agent on the way", "Your Delhivery pickup agent is on the way."),
    (9.0, "Agent arrived", "Delhivery agent arrived at the pickup address."),
    (12.0, "Documents collected", "Documents collected after doorstep QC check."),
    (15.0, "Pickup confirmed", "Shipment picked up and sealed for transit."),
    (18.0, "In transit", "Shipment is moving through the Delhivery network."),
    (21.0, "Hyderabad hub", "Shipment reached the Hyderabad sorting hub."),
    (24.0, "Out for delivery", "Shipment is out for delivery to the secondary insurer."),
    (27.0, "Delivered", "Documents delivered to Sanjeevani Health Insurance claims office."),
    (30.0, "Proof of delivery", "Claims-office signature captured digitally in Delhivery EPOD."),
    (34.0, "Desk-level verification", "Vasool is confirming that the receiving signature belongs to the claims desk."),
    (38.0, "Receipt confirmed", "Sanjeevani claims desk confirmed receipt of the document packet."),
    (42.0, "Processing started", "Sanjeevani claim file logged; insurer processing has started."),
    (45.0, "Amount processed", "Sanjeevani processed the claim: Rs 1,12,000 approved and disbursed to the registered bank account."),
]

def _add_demo_timeline(text, when=None, key=None, exact=False):
    if any(str(e.get("text", "")).strip().lower() == str(text).strip().lower() for e in STATE["timeline"]): return
    now = time.time()
    STATE["timeline"].append({"t": when or datetime.datetime.now().strftime("%H:%M"), "text": text, "k": (key if exact else max(key, now)) if key else now})
    STATE["timeline"].sort(key=lambda e: e.get("k", 0))

def _add_workdays(d, n):
    while n:
        d += datetime.timedelta(days=1)
        if d.weekday() < 5: n -= 1
    return d

def _mock_schedule():
    raw = str(STATE.get("pickup", {}).get("date", "")).strip()
    d0 = None
    for cand in (raw, raw.split(",")[0].strip()):
        for fmt in ("%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%d %b", "%d %B"):
            try:
                d0 = datetime.datetime.strptime(cand, fmt).date()
                if d0.year == 1900: d0 = d0.replace(year=2026)
                break
            except Exception:
                pass
        if d0: break
    if d0 is None: d0 = datetime.date(2026, 10, 4)
    d1 = d0 + datetime.timedelta(days=1)
    d7 = _add_workdays(d1, 7)
    plan = {
        "Pickup scheduled": (d0, "09:00"), "Pickup agent assigned": (d0, "09:30"),
        "Agent on the way": (d0, "10:15"), "Agent arrived": (d0, "10:40"),
        "Documents collected": (d0, "10:55"), "Pickup confirmed": (d0, "11:10"),
        "In transit": (d0, "18:30"), "Hyderabad hub": (d1, "07:45"),
        "Out for delivery": (d1, "09:50"), "Delivered": (d1, "11:35"),
        "Proof of delivery": (d1, "11:42"), "Desk-level verification": (d1, "14:20"),
        "Receipt confirmed": (d1, "15:05"), "Processing started": (d1, "15:40"),
        "Amount processed": (d7, "16:10"),
    }
    out, ep = {}, {}
    for k, (d, hm) in plan.items():
        dt = datetime.datetime.combine(d, datetime.datetime.strptime(hm, "%H:%M").time())
        out[k] = f"{dt.day} {dt.strftime('%b')}, {dt.strftime('%I:%M %p').lstrip('0')}"
        ep[k] = dt.timestamp()
    return out, ep

def start_demo_delivery():
    global DELIVERY_STARTED
    with DELIVERY_LOCK:
        if DELIVERY_STARTED:
            return
        DELIVERY_STARTED = True
        my_gen = DELIVERY_GEN

    def run():
        try:
            base = time.time()
            sched, plan_ts = _mock_schedule()
            for offset, status, text in DEMO_DELIVERY_STEPS:
                delay = max(0.0, offset * (DELIVERY_STEP_SECONDS / 3.0) - (time.time() - base))
                if delay:
                    time.sleep(delay)
                if my_gen != DELIVERY_GEN:
                    return
                STATE["delivery"]["status"] = status
                STATE["delivery"]["progress"] = int((DEMO_DELIVERY_STEPS.index((offset, status, text)) + 1) * 100 / len(DEMO_DELIVERY_STEPS))
                if status == "Pickup scheduled":
                    STATE["delivery"]["eta"] = sched["Delivered"]
                if status == "Amount processed":
                    STATE["final_phase"] = 1
                    log("demo_delivery", status=status, text="clock event: seven working days passed")
                    post_event("Clock event: it is now " + sched[status] + " IST. Seven working days have passed since Sanjeevani confirmed receipt of the claim packet.")
                    continue
                _add_demo_timeline(text, sched.get(status), plan_ts.get(status))
                log("demo_delivery", status=status, text=text)
                if status == "Proof of delivery":
                    STATE["signature"] = "Sanjeevani Claims Desk  •  digitally signed"
                if status == "Desk-level verification":
                    post_event("Delhivery reported delivery and captured a digital signature. The receiving identity is not independently proven; confirm receipt with the insurer as required by R6.")
        finally:
            pass

    th = threading.Thread(target=run, daemon=True)
    th.start()

# ---------- web ----------
app = Flask(__name__)
import logging; logging.getLogger("werkzeug").setLevel(logging.ERROR)
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif", "application/pdf"}
EXT_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
            ".heic": "image/heic", ".heif": "image/heif", ".pdf": "application/pdf"}
def _mime_for(f):
    m = (f.mimetype or "").lower()
    if m not in ALLOWED_MIME:
        m = EXT_MIME.get(os.path.splitext(f.filename or "")[1].lower(), "")
    return m if m in ALLOWED_MIME else ""

@app.get("/")
def index(): return redirect("/claim")
@app.get("/claim")
def claim(): return render_template("claim.html")
@app.get("/state")
def state(): return jsonify({k: v for k, v in STATE.items()})

@app.post("/api/start")
def api_start():
    d = request.get_json(silent=True) or {}; STATE["profile"] = {k: d.get(k, "") for k in ("name", "phone", "email")}; log("claimant_input", screen="sign in", data=STATE["profile"])
    new_otp()
    r = wa_send(f"Your Vasool sign-in code is {OTP['code']}.")
    return jsonify({"sent": bool(r.get("sent")), "error": r.get("error", "")})

@app.post("/verify_otp")
def verify_otp():
    code = str((request.get_json(silent=True) or {}).get("code", "")).strip()
    if not OTP["code"] or time.time() > OTP["exp"]:
        return jsonify({"ok": False, "error": "code expired"})
    OTP["tries"] += 1
    if OTP["tries"] > 5:
        OTP["code"] = None
        return jsonify({"ok": False, "error": "too many attempts"})
    ok = hmac.compare_digest(code, OTP["code"])
    if ok:
        OTP["code"] = None
        if STATE["stage"] == "identity": STATE["stage"] = "basics"
        elif STATE["stage"] == "authorize" and STATE.get("otp_pending"):
            STATE["otp_pending"] = False; STATE["otp_ok"] = True
            post_event("The claimant entered the correct OTP in the web app.")
    return jsonify({"ok": ok})

@app.post("/api/basics")
def api_basics():
    if STATE["stage"] not in ("basics", "docs"): return jsonify({"ok": False, "error": "wrong stage"}), 409
    STATE["basics"] = request.json or {}; STATE["stage"] = "docs"; log("claimant_input", screen="your claim", data=STATE["basics"]); return jsonify({"ok": True})

@app.post("/submit_docs")
def submit_docs():
    if STATE["stage"] == "identity":
        return jsonify({"ok": False, "error": "verify identity first"}), 403
    files, names, rejected = [], [], []
    for doc, f in request.files.items():
        if doc not in DOCS or not f.filename:
            continue
        data = f.read(); mime = _mime_for(f)
        if not data or not mime:
            rejected.append(doc); continue
        (UPLOADS / f"{doc}_{secure_filename(f.filename) or 'upload'}").write_bytes(data)
        DOC_VERSIONS[doc] = DOC_VERSIONS.get(doc, 0) + 1
        RETAKE_VERSIONS.pop(doc, None)
        VERIFIED_VERSIONS.pop(doc, None)
        STATE["docs"][doc].update(status="uploaded", reason="", detected_type="", evidence="")
        STATE["waiting_for_docs"] = any(
            STATE["docs"][k].get("status") in ("missing", "retake", "empty", "uploaded")
            for k in REQUIRED_R3_DOCS
        )
        UPLOADED_DOCS.add(doc)
        files.append((f"uploaded file for slot {doc} (filename: {f.filename})", data, mime))
        names.append(doc)

    if not files:
        return jsonify({"ok": False, "rejected": rejected, "error": "unsupported or empty file (use JPG, PNG, WEBP, HEIC or PDF)"}), 400

    first = STATE["stage"] == "docs"
    if first:
        # Keep the user on Documents while they are still uploading. The
        # agent starts after DOC_UPLOAD_SETTLE_SECONDS of upload inactivity.
        STATE["stage"] = "docs"

    post_doc_event(files, names, first)
    return jsonify({"ok": True, "queued": True, "rejected": rejected, "settle_seconds": DOC_UPLOAD_SETTLE_SECONDS})

@app.post("/api/agree")
def api_agree():
    if STATE["stage"] != "eligibility": return jsonify({"ok": False, "error": "wrong stage"}), 409
    STATE["stage"] = "form"; post_event("The claimant agreed to the eligibility result and the claim amount."); return jsonify({"ok": True})

@app.post("/api/pickup")
def api_pickup():
    if STATE["stage"] != "pickup": return jsonify({"ok": False, "error": "wrong stage"}), 409
    d = request.json or {}; STATE["pickup"] = d; STATE["stage"] = "authorize"
    post_event("The claimant chose pickup details in the web app: " + json.dumps(d)); return jsonify({"ok": True})

@app.post("/api/paid")
def api_paid():
    # The claimant action is deterministic UI state: once the approved hold is
    # active, there is no reason for the page to keep waiting on Gemini merely
    # to navigate. The agent still receives the event and the Delhivery calls
    # remain logged as part of the simulation.
    if STATE.get("payment_approved"): return jsonify({"ok": True, "stage": STATE["stage"]})
    if STATE["stage"] != "authorize" or not STATE.get("otp_ok"):
        return jsonify({"ok": False, "error": "OTP not confirmed"}), 409
    STATE["payment_approved"] = True
    STATE["stage"] = "track"
    STATE["delivery"]["status"] = "Pickup scheduled"
    STATE["delivery"]["progress"] = 7
    _add_demo_timeline("Pine Labs fee hold active — ₹1,499 reserved, not charged.")
    _add_demo_timeline("Delhivery pickup request created for the approved document packet.")
    start_demo_delivery()
    post_event("The claimant approved the Pine Labs payment hold in the checkout. The hold is ACTIVE. Begin Delhivery dispatch and tracking.")
    return jsonify({"ok": True, "stage": "track"})

@app.get("/reset")
def reset():
    print("\n===== RESET: new demo run started =====\n", flush=True)
    global DOC_BATCH_TIMER, DELIVERY_STARTED, DELIVERY_GEN
    STATE.clear(); STATE.update(fresh_state()); HIST.clear(); OTP["code"] = None
    UPLOADED_DOCS.clear()
    for _doc in DOCS:
        DOC_VERSIONS[_doc] = 0
    RETAKE_VERSIONS.clear()
    VERIFIED_VERSIONS.clear()
    DELIVERY_STARTED = False; DELIVERY_GEN += 1
    GN["n"] = 0; GN["convs"].clear(); GN.pop("served", None); DONE.clear()
    while not EVQ.empty():
        try: EVQ.get_nowait()
        except queue.Empty: break
    PINE["n"] = 0; PINE["active"] = False
    with DOC_BATCH_LOCK:
        DOC_BATCH.clear(); DOC_BATCH_NAMES.clear()
        if DOC_BATCH_TIMER is not None:
            DOC_BATCH_TIMER.cancel()
            DOC_BATCH_TIMER = None
    return redirect("/claim")

@app.get("/whatsapp/webhook")
def wa_verify():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == os.getenv("WHATSAPP_VERIFY_TOKEN"):
        return request.args.get("hub.challenge", "")
    return "forbidden", 403

@app.post("/whatsapp/webhook")
def wa_incoming():
    secret = os.getenv("WHATSAPP_APP_SECRET", "")
    if secret:
        want = "sha256=" + hmac.new(secret.encode(), request.get_data(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(request.headers.get("X-Hub-Signature-256", ""), want): return "forbidden", 403
    d = request.get_json(silent=True) or {}
    print("WEBHOOK", json.dumps(d)[:600])
    for e in d.get("entry", []):
        for ch in e.get("changes", []):
            for m in ch.get("value", {}).get("messages", []) or []:
                if m.get("type") == "text" and (not RAVI or m.get("from") == RAVI):
                    post_event("WhatsApp message from the claimant: " + m["text"]["body"])
    return "ok", 200

@app.post("/dev/say")   # only for testing without Twilio; set DEV=1
def dev_say():
    if os.getenv("DEV") != "1": return "disabled", 403
    post_event("WhatsApp message from the claimant: " + (request.json or {}).get("text", "")); return jsonify({"ok": True})

@app.get("/wizard")
def wizard(): return render_template("wizard.html")
@app.get("/wizard/pending")
def wizard_pending():
    return jsonify({"pending": [{k: v for k, v in p.items() if k != "event"} for p in PEND.values()], "done": DONE[-10:]})
@app.post("/wizard/reply")
def wizard_reply():
    d = request.json or {}; p = PEND.get(d.get("id"))
    if not p: return jsonify({"ok": False}), 404
    p["reply"] = d.get("reply", ""); p["event"].set(); return jsonify({"ok": True})

threading.Thread(target=worker, daemon=True).start()
if CHANNEL == "telegram": threading.Thread(target=tg_poll, daemon=True).start()
if __name__ == "__main__":
    print(f"Vasool is running: {PUBLIC}/claim   (wizard console: {PUBLIC}/wizard)\n", flush=True)
    app.run(port=5000, debug=False, threaded=True)
