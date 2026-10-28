import math, random, os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth

W, H = A4
NAVY = colors.HexColor("#14325c"); INK = colors.HexColor("#1b1b1b"); GREY = colors.HexColor("#5b6470")
LINE = colors.HexColor("#c9ced6"); BLUE = colors.HexColor("#1d3fa8"); TEAL = colors.HexColor("#0b5b63"); RED = colors.HexColor("#8a1c2b")
OUT = "mock_documents"; os.makedirs(OUT, exist_ok=True)
HOSP = "Sunrise Multispeciality Hospital"
HADDR = "Road No. 36, Jubilee Hills, Hyderabad 500033   |   Tel 040-5550 0100   |   Reg. No. SMH/HYD/2014/0417"

def rs(n):
    s = str(int(n))
    if len(s) <= 3: return s
    head, tail = s[:-3], s[-3:]; parts = []
    while len(head) > 2: parts.insert(0, head[-2:]); head = head[:-2]
    if head: parts.insert(0, head)
    return ",".join(parts + [tail])

def cv(name, title):
    c = canvas.Canvas(f"{OUT}/{name}", pagesize=A4); c.setTitle(title); c.setAuthor("Fictional simulation document"); return c
def T(c, x, y, s, size=9, bold=False, col=INK, al="l"):
    c.setFillColor(col); c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    {"l": c.drawString, "r": c.drawRightString, "c": c.drawCentredString}[al](x, y, s)
def foot(c, n=1):
    T(c, W/2, 22, "Fictional document created for a software simulation. Not a real medical, insurance or financial record.", 6.5, col=GREY, al="c")
    T(c, W-36, 22, f"Page {n}", 6.5, col=GREY, al="r")
def head(c, title, name=HOSP, sub=HADDR, col=NAVY):
    c.setFillColor(col); c.rect(0, H-70, W, 70, stroke=0, fill=1)
    T(c, 36, H-34, name, 18, True, colors.white); T(c, 36, H-51, sub, 8, col=colors.HexColor("#d5deec"))
    T(c, W/2, H-96, title, 13, True, al="c"); c.setStrokeColor(LINE); c.line(36, H-105, W-36, H-105); return H-124
def para(c, x, y, s, w, size=9, lead=12.5, bold=False):
    f = "Helvetica-Bold" if bold else "Helvetica"; c.setFont(f, size); c.setFillColor(INK)
    for ln in simpleSplit(s, f, size, w): c.drawString(x, y, ln); y -= lead
    return y
def kv(c, x, y, items, cols=2, lw=82, size=9):
    w = (W-72)/cols
    for i, (k, v) in enumerate(items):
        cx = x + (i % cols)*w; cy = y - (i//cols)*16
        T(c, cx, cy, k+":", size-1, col=GREY); T(c, cx+lw, cy, v, size, True)
    return y - ((len(items)+cols-1)//cols)*16 - 8
def sec(c, y, s):
    T(c, 36, y, s, 10, True, NAVY); c.setStrokeColor(LINE); c.line(36, y-3, W-36, y-3); return y-17
def table(c, x, y, heads, rows, widths, rh=17, size=8.5, right=(), boldrows=()):
    tw = sum(widths); top = y
    c.setFillColor(colors.HexColor("#e8edf5")); c.rect(x, y-rh, tw, rh, stroke=0, fill=1); c.setStrokeColor(LINE)
    def row(cells, yy, bold):
        cx = x
        for i, (cell, wd) in enumerate(zip(cells, widths)):
            c.setFillColor(INK); c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
            (c.drawRightString(cx+wd-5, yy-rh+5, str(cell)) if i in right else c.drawString(cx+5, yy-rh+5, str(cell))); cx += wd
        c.line(x, yy-rh, x+tw, yy-rh)
    c.line(x, y, x+tw, y); row(heads, y, True); y -= rh
    for i, r in enumerate(rows): row(r, y, i in boldrows); y -= rh
    cx = x
    for wd in [0]+list(widths): cx += wd; c.line(cx, top, cx, y)
    return y - 8
def seal(c, cx, cy, r=46, top=HOSP.upper(), bot="HYDERABAD", m1="REG. NO.", m2="SMH/HYD/2014/0417", col=BLUE, rot=-9):
    c.saveState(); c.translate(cx, cy); c.rotate(rot); c.setStrokeColor(col); c.setFillColor(col); c.setFillAlpha(.82); c.setStrokeAlpha(.82)
    c.setLineWidth(1.6); c.circle(0, 0, r, 1, 0); c.setLineWidth(.6); c.circle(0, 0, r-4, 1, 0); c.circle(0, 0, r-22, 1, 0)
    rt = r-12; fs = 5.2; c.setFont("Helvetica-Bold", fs)
    tw = sum(stringWidth(ch, "Helvetica-Bold", fs) for ch in top); a0 = math.degrees(tw/rt)/2; cum = 0
    for ch in top:
        w = stringWidth(ch, "Helvetica-Bold", fs); ang = a0 - math.degrees((cum+w/2)/rt); cum += w
        c.saveState(); c.rotate(ang); c.drawCentredString(0, rt-1.5, ch); c.restoreState()
    tw = sum(stringWidth(ch, "Helvetica-Bold", fs) for ch in bot); a0 = -math.degrees(tw/rt)/2; cum = 0
    for ch in bot:
        w = stringWidth(ch, "Helvetica-Bold", fs); ang = a0 + math.degrees((cum+w/2)/rt); cum += w
        c.saveState(); c.rotate(ang); c.drawCentredString(0, -rt-1, ch); c.restoreState()
    c.setFont("Helvetica-Bold", 5.6); c.drawCentredString(0, 8, m1); c.setFont("Helvetica-Bold", 4.3); c.drawCentredString(0, 0, m2)
    c.setFont("Helvetica-Bold", 9); c.drawCentredString(0, -12, "+ SEAL +"); c.restoreState()
def sign(c, x, y, seed=1, w=120, col=BLUE, name="", role=""):
    r = random.Random(seed); c.saveState(); c.setStrokeColor(col); c.setLineWidth(1.25); c.setLineCap(1)
    p = c.beginPath(); px = x; p.moveTo(px, y)
    for i in range(7):
        nx = px + w/7; p.curveTo(px+r.uniform(0, w/14), y+r.uniform(8, 22), nx-r.uniform(0, w/14), y+r.uniform(-14, 6), nx, y+r.uniform(-4, 8)); px = nx
    c.drawPath(p, 1, 0); c.setLineWidth(.8); c.line(x+6, y-9, x+w-12, y-4); c.restoreState()
    if name: T(c, x, y-22, name, 8, True); 
    if role: T(c, x, y-32, role, 7, col=GREY)

# ---- case data (matches case_items.md)
PT = [("Patient", "Mr. Ravi Menon"), ("UHID", "SMH-0098231"), ("Age / Sex", "38 yrs / Male"), ("IP No.", "IP/2026/08817")]
STAY = [("Admitted", "08 Sep 2026, 10:20"), ("Discharged", "12 Sep 2026, 11:05")]
DR = "Dr. Anil Kapoor, MS (Surgery)"; DRREG = "Reg. No. TSMC/54821"
BILL = [("1", "Room and nursing, single private room (4 nights)", "4 x 27,500", 110000), ("2", "Surgeon and anaesthetist fees", "1", 90000),
        ("3", "Operation theatre charges", "1", 60000), ("4", "Medicines and consumables (see pharmacy bill)", "1", 62000),
        ("5", "Investigations (laboratory, MRCP, ultrasound, ECG, X-ray)", "1", 40000), ("6", "Nursing and ward services", "1", 50000),
        ("7", "Admission kit", "1", 2500), ("8", "Personal care items", "1", 3000), ("9", "Registration and administrative charges", "1", 2500)]
assert sum(b[3] for b in BILL) == 420000
PHARM = [("1", "Laparoscopic disposable kit (trocars, clip applier, endo-bag)", "LK2611", 1, 38000), ("2", "Surgical sutures and haemostats", "SU4410", 1, 6200),
         ("3", "Anaesthesia drugs and consumables", "AN0932", 1, 5800), ("4", "Inj. Ceftriaxone 1 g", "CT7781", 8, 310), ("5", "Inj. Paracetamol 1 g", "PC3320", 10, 190),
         ("6", "Inj. Pantoprazole 40 mg", "PN5512", 8, 150), ("7", "IV fluids (Ringer lactate / normal saline)", "IV8806", 24, 120), ("8", "Oral medicines course (analgesic, PPI, antibiotic)", "OR1175", 1, 3540)]
def amt(r): return r[3] * r[4] if r[0] != "8" else 3540
assert sum(r[3]*r[4] for r in PHARM) == 62000

# 1 claim form
def claim_form():
    c = cv("01_claim_form_signed.pdf", "Claim form"); y = head(c, "REIMBURSEMENT CLAIM FORM", "Sanjeevani Health Insurance", "Claims Desk, Banjara Hills, Hyderabad 500034   |   Policy SJV-5540218", TEAL)
    y = sec(c, y, "A. Policy details"); y = kv(c, 36, y, [("Policy no.", "SJV-5540218"), ("Plan", "Sanjeevani Comprehensive"), ("Policy period", "01 Apr 2026 to 31 Mar 2027"), ("Sum insured", "Rs 5,00,000"), ("Policyholder", "Ravi Menon")])
    y = sec(c, y, "B. Insured person"); y = kv(c, 36, y, [("Name", "Ravi Menon"), ("Date of birth", "14 Mar 1988"), ("Age / Sex", "38 / Male"), ("Relationship", "Self"), ("Mobile", "+91 98480 12345"), ("Email", "ravi.menon@example.com")])
    y = kv(c, 36, y, [("Address", "Flat 402, Lakeview Residency, Madhapur, Hyderabad 500081")], 1)
    y = sec(c, y, "C. Hospitalisation"); y = kv(c, 36, y, [("Hospital", HOSP+", Hyderabad")], 1)
    y = kv(c, 36, y, [("Hospital reg. no.", "SMH/HYD/2014/0417"), ("IP no.", "IP/2026/08817"), ("Admitted", "08 Sep 2026"), ("Discharged", "12 Sep 2026"), ("Treating doctor", DR)], 2, 90)
    y = kv(c, 36, y, [("Diagnosis", "Chronic calculous cholecystitis with cholelithiasis"), ("Procedure", "Laparoscopic cholecystectomy, 09 Sep 2026")], 1)
    y = sec(c, y, "D. Other insurance (contribution clause)"); y = kv(c, 36, y, [("Primary insurer", "Vidal Health TPA"), ("Member ID", "VH-20458821"), ("Policy no.", "VHI-3301876"), ("Primary claim no.", "VH-2026-448120"), ("Paid by primary", "Rs 3,00,000"), ("Balance billed", "Rs 1,20,000")], 2, 92)
    y = sec(c, y, "E. Amount claimed from this policy"); T(c, 36, y, "Rs 1,20,000 (balance of the hospital bill after the primary insurer's payment)", 10, True); y -= 24
    y = sec(c, y, "F. Payout details"); y = kv(c, 36, y, [("Account holder", "Ravi Menon"), ("Bank", "Demo Bank, Madhapur"), ("Account no.", "XXXXXXXX4417"), ("IFSC", "DEMO0001234")], 2, 86)
    y = sec(c, y, "G. Declaration"); y = para(c, 36, y, "I declare that the information given is true and complete. I authorise the insurer to obtain records from the hospital and from my other insurer.", W-72, 8.5)
    T(c, 36, y-20, "Date: 01 Oct 2026      Place: Hyderabad", 9); sign(c, 330, y-14, 11, 130, name="Ravi Menon", role="Signature of the policyholder"); foot(c); c.save()

# 2 TPA card
def card(c, y, title, rows, col, sub, back=False):
    x, w, h = 115, 365, 225
    c.setFillColor(colors.white); c.setStrokeColor(col); c.setLineWidth(1.4); c.roundRect(x, y-h, w, h, 14, 1, 1)
    c.setFillColor(col); c.roundRect(x, y-52, w, 52, 14, 1, 0); c.rect(x, y-52, w, 20, 0, 1)
    T(c, x+16, y-26, title, 14, True, colors.white); T(c, x+16, y-42, sub, 8, col=colors.HexColor("#dde7f3"))
    yy = y-80
    for k, v in rows: T(c, x+16, yy, k, 8.5, col=GREY); T(c, x+120, yy, v, 10, True); yy -= 22
def tpa_card():
    c = cv("02_vidal_tpa_card.pdf", "TPA card"); y = H-80
    T(c, W/2, y+20, "Vidal Health Insurance TPA: health card (photocopy)", 11, True, al="c")
    card(c, y, "Vidal Health Insurance TPA", [("Member name", "RAVI MENON"), ("Member ID", "VH-20458821"), ("Policy no.", "VHI-3301876"), ("Plan", "Vidal Individual Plus"), ("Sum insured", "Rs 3,00,000"), ("Valid", "01 Apr 2026 to 31 Mar 2027")], TEAL, "Cashless hospitalisation card")
    c.setFillColor(colors.white); c.setStrokeColor(TEAL); c.roundRect(115, y-500, 365, 225, 14, 1, 1)
    T(c, 131, y-298, "Terms and helpline", 11, True, TEAL); para(c, 131, y-318, "Show this card and a photo ID at the network hospital desk. Cashless approval is subject to policy terms. Keep the member ID for all claims.", 330, 8.5)
    T(c, 131, y-390, "Helpline: 1800 000 0000 (demo)   |   claims@vidalhealth.example", 8.5, True); T(c, 131, y-410, "Fictional card for a software simulation", 7, col=GREY); foot(c); c.save()

# 3 ID proof
def id_proof():
    c = cv("03_identity_proof.pdf", "Identity proof"); y = H-90; T(c, W/2, y+20, "Identity proof (photocopy)", 11, True, al="c")
    x, w, h = 140, 315, 205; c.setFillColor(colors.white); c.setStrokeColor(NAVY); c.setLineWidth(1.3); c.roundRect(x, y-h, w, h, 10, 1, 1)
    c.setFillColor(NAVY); c.roundRect(x, y-44, w, 44, 10, 1, 0); c.rect(x, y-44, w, 16, 0, 1)
    T(c, x+14, y-27, "MERIDIAN SOFTWARE PVT LTD", 12, True, colors.white); T(c, x+14, y-38, "Employee identity card", 7.5, col=colors.HexColor("#d5deec"))
    c.setFillColor(colors.HexColor("#e3e7ed")); c.rect(x+14, y-150, 78, 92, 1, 1); c.setFillColor(colors.HexColor("#9aa3b0")); c.circle(x+53, y-96, 15, 1, 0); c.ellipse(x+31, y-150, x+75, y-112, 1, 0)
    yy = y-70
    for k, v in [("Name", "Ravi Menon"), ("Employee ID", "MS-20418"), ("Designation", "Senior Engineer"), ("Date of birth", "14 Mar 1988"), ("Valid till", "31 Dec 2026")]:
        T(c, x+108, yy, k, 7.5, col=GREY); T(c, x+170, yy, v, 9, True); yy -= 17
    T(c, x+14, y-170, "Address: Flat 402, Lakeview Residency, Madhapur, Hyderabad 500081", 7.2); T(c, x+14, y-188, "Fictional ID card created for a software simulation", 6.5, col=GREY); foot(c); c.save()

# 4 discharge summary
def discharge():
    c = cv("04_discharge_summary.pdf", "Discharge summary"); y = head(c, "DISCHARGE SUMMARY")
    y = kv(c, 36, y, PT + STAY + [("Ward", "Single private room 412"), ("Consultant", DR)])
    for h, t in [("Diagnosis", "Chronic calculous cholecystitis with cholelithiasis (symptomatic gallstones)."),
                 ("Procedure", "Laparoscopic cholecystectomy under general anaesthesia on 09 Sep 2026. Surgeon: Dr. Anil Kapoor. Anaesthetist: Dr. Meera Iyer."),
                 ("Presenting complaints", "Recurrent right upper abdominal pain and nausea for 3 months, worse after meals. Ultrasound and MRCP showed multiple gallstones with a thickened gallbladder wall."),
                 ("Hospital course", "Admitted electively on 08 Sep 2026 after pre-operative work-up. Uneventful laparoscopic surgery on 09 Sep. Post-operative recovery was smooth, pain controlled with injectables, oral diet started on day 2, drain removed on day 3. Wounds clean and dry."),
                 ("Condition at discharge", "Stable, afebrile, tolerating normal diet, ambulant. Discharged on 12 Sep 2026."),
                 ("Medicines on discharge", "Tab. Pantoprazole 40 mg once daily before breakfast for 14 days; Tab. Paracetamol 650 mg three times daily for 5 days; Tab. Cefixime 200 mg twice daily for 5 days."),
                 ("Advice and follow-up", "Light diet for two weeks, avoid heavy lifting for four weeks. Review with Dr. Anil Kapoor on 22 Sep 2026 with this summary. Return earlier for fever, vomiting, jaundice or wound discharge.")]:
        y = sec(c, y, h); y = para(c, 36, y, t, W-72, 9.2, 13) - 6
    T(c, 36, 120, "Prepared by: Dr. Meera Iyer, Resident", 8, col=GREY); sign(c, 330, 108, 21, 130, BLUE, DR, DRREG + "   |   Consultant Surgeon")
    seal(c, 250, 112, 46); foot(c); c.save()

# 5 inpatient bill
def ip_bill():
    c = cv("05_inpatient_bill.pdf", "In-patient bill"); y = head(c, "FINAL IN-PATIENT BILL")
    y = kv(c, 36, y, [("Bill no.", "SUN/IP/2026/08817-B"), ("Bill date", "12 Sep 2026")] + PT + STAY + [("Payer", "Cashless: Vidal Health TPA"), ("Member ID", "VH-20458821")])
    rows = [(a, b, q, rs(m)) for a, b, q, m in BILL]; rows.append(("", "Gross total", "", rs(420000)))
    y = table(c, 36, y, ["No.", "Description", "Qty / days", "Amount (Rs)"], rows, [34, 300, 80, 91], right=(3,), boldrows=(len(rows)-1,))
    y = table(c, 36, y-6, ["Settlement", "Amount (Rs)"], [("Net bill amount", rs(420000)), ("Settled by Vidal Health TPA (claim VH-2026-448120)", rs(300000)), ("Paid by patient (receipt SUN/RC/2026/11742)", rs(120000)), ("Balance due", "0")], [415, 90], right=(1,), boldrows=(3,))
    T(c, 36, y-6, "Amount in words: Rupees Four Lakh Twenty Thousand only. All charges are as per the hospital tariff.", 8.2, col=GREY)
    sign(c, 380, 130, 31, 130, BLUE, "Accounts Officer", HOSP); seal(c, 270, 124, 46); foot(c); c.save()

# 6 prescription
def prescription():
    c = cv("06_doctors_prescription.pdf", "Prescription"); y = head(c, "PRESCRIPTION", "Dr. Anil Kapoor, MS (General and Laparoscopic Surgery)", "Consultant Surgeon, Sunrise Multispeciality Hospital   |   " + DRREG, TEAL)
    y = kv(c, 36, y, [("Patient", "Mr. Ravi Menon"), ("Date", "06 Sep 2026"), ("Age / Sex", "38 yrs / Male"), ("UHID", "SMH-0098231")])
    y = sec(c, y, "Diagnosis"); y = para(c, 36, y, "Chronic calculous cholecystitis with multiple gallstones. Advised laparoscopic cholecystectomy; admit on 08 Sep 2026.", W-72) - 4
    y = sec(c, y, "Rx")
    y = table(c, 36, y, ["Medicine", "Dose", "Frequency", "Duration"], [("Tab. Pantoprazole 40 mg", "1 tablet", "Before breakfast", "7 days"), ("Tab. Ursodeoxycholic acid 300 mg", "1 tablet", "Morning and night", "7 days"), ("Tab. Paracetamol 650 mg", "1 tablet", "If pain, up to 3 a day", "As needed")], [190, 80, 150, 85])
    y = sec(c, y, "Advice"); y = para(c, 36, y, "Nothing by mouth after midnight before admission. Continue regular medicines unless told otherwise. Carry all previous reports and the insurance card to the hospital.", W-72)
    sign(c, 360, 250, 41, 130, BLUE, DR, DRREG); seal(c, 270, 242, 40, "DR. ANIL KAPOOR MS", "TSMC/54821", "CONSULTANT", "SURGEON", rot=6); foot(c); c.save()

# 7 pharmacy bill (sealed and not sealed)
def pharmacy(sealed):
    c = cv("07_pharmacy_bills_sealed.pdf" if sealed else "07_pharmacy_bills_NO_SEAL_for_retake.pdf", "Pharmacy bill")
    y = head(c, "PHARMACY BILL WITH BREAK-UPS", HOSP + ", In-patient Pharmacy", HADDR)
    y = kv(c, 36, y, [("Bill no.", "SUN/PH/2026/20931"), ("Bill date", "12 Sep 2026")] + PT + [("IP bill ref.", "SUN/IP/2026/08817-B"), ("Period", "08 to 12 Sep 2026")])
    rows = [(a, b, bt, q, rs(r), rs(q*r)) for a, b, bt, q, r in PHARM] + [("", "Total", "", "", "", rs(62000))]
    y = table(c, 36, y, ["No.", "Item", "Batch", "Qty", "Rate", "Amount (Rs)"], rows, [30, 255, 55, 35, 55, 75], right=(3, 4, 5), boldrows=(len(rows)-1,))
    T(c, 36, y-4, "All rates inclusive of taxes. Amount in words: Rupees Sixty-two Thousand only.", 8.2, col=GREY)
    sign(c, 380, 130, 51, 130, BLUE, "Pharmacist in charge", "In-patient Pharmacy")
    if sealed: seal(c, 270, 124, 46)
    foot(c); c.save()

# 8 investigation reports (4 pages)
def investigations():
    c = cv("08_investigation_reports.pdf", "Investigation reports")
    reps = [("ULTRASOUND ABDOMEN", "04 Sep 2026", "Gallbladder is distended with multiple echogenic calculi, largest 14 mm, with posterior acoustic shadowing. Wall thickened to 5 mm. No pericholecystic fluid. Common bile duct 5 mm. Liver, pancreas, spleen and both kidneys normal.", "Cholelithiasis with chronic cholecystitis."),
            ("MRCP", "05 Sep 2026", "Multiple filling defects within the gallbladder consistent with calculi. Intra- and extrahepatic bile ducts are not dilated. No choledocholithiasis. Pancreatic duct normal.", "Gallstones; no common bile duct stones."),
            ("ECG (12 LEAD)", "07 Sep 2026", "Normal sinus rhythm, heart rate 76 per minute. PR 160 ms, QRS 88 ms, QTc 410 ms. No ST-T changes.", "Normal ECG. Fit for anaesthesia from a cardiac standpoint."),
            ("X-RAY CHEST (PA VIEW)", "07 Sep 2026", "Both lung fields are clear. Cardiac size is normal. Costophrenic angles are sharp. Bony thorax unremarkable.", "Normal chest radiograph.")]
    for n, (t, d, f, imp) in enumerate(reps, 1):
        y = head(c, t + " REPORT", HOSP + ", Diagnostics and Imaging", HADDR, TEAL); y = kv(c, 36, y, PT + [("Report date", d), ("Referred by", DR)])
        y = sec(c, y, "Findings"); y = para(c, 36, y, f, W-72, 10, 14) - 8; y = sec(c, y, "Impression"); y = para(c, 36, y, imp, W-72, 10.5, 14, True)
        sign(c, 360, 150, 60+n, 130, BLUE, "Dr. R. Sen, MD (Radiology)" if n != 3 else "Dr. P. Nair, MD (Cardiology)", "Reporting consultant"); foot(c, n); c.showPage()
    c.save()

# 9 lab reports
def labs():
    c = cv("09_laboratory_reports.pdf", "Laboratory reports"); y = head(c, "LABORATORY REPORT", HOSP + ", Clinical Laboratory", HADDR, TEAL)
    y = kv(c, 36, y, PT + [("Collected", "07 Sep 2026, 08:10"), ("Reported", "07 Sep 2026, 13:40")])
    R = [("Haemoglobin", "13.8", "g/dL", "13.0 - 17.0", ""), ("Total leucocyte count", "7,400", "/cumm", "4,000 - 11,000", ""), ("Platelet count", "2.45", "lakh/cumm", "1.5 - 4.1", ""), ("Total bilirubin", "0.9", "mg/dL", "0.2 - 1.2", ""),
         ("SGOT (AST)", "34", "U/L", "up to 40", ""), ("SGPT (ALT)", "41", "U/L", "up to 45", ""), ("Alkaline phosphatase", "112", "U/L", "44 - 147", ""), ("Serum creatinine", "0.9", "mg/dL", "0.7 - 1.3", ""),
         ("Blood urea", "26", "mg/dL", "15 - 40", ""), ("Random blood sugar", "104", "mg/dL", "70 - 140", ""), ("PT / INR", "1.02", "ratio", "0.9 - 1.2", ""), ("HBsAg / HIV / HCV", "Non-reactive", "", "Non-reactive", "")]
    y = table(c, 36, y, ["Test", "Result", "Unit", "Reference range", "Flag"], R, [190, 85, 80, 110, 40], rh=19, right=(1,))
    T(c, 36, y-4, "All values within normal limits. Pre-operative screening.", 9, True); sign(c, 360, 170, 71, 130, BLUE, "Dr. S. Reddy, MD (Pathology)", "Consultant pathologist"); seal(c, 250, 162, 40, "CLINICAL LABORATORY", "SUNRISE HOSPITAL", "PATHOLOGY", "LAB", rot=5); foot(c); c.save()

# 10 paid receipt
def receipt():
    c = cv("10_paid_receipt.pdf", "Payment receipt"); y = head(c, "PAYMENT RECEIPT")
    y = kv(c, 36, y, [("Receipt no.", "SUN/RC/2026/11742"), ("Date", "12 Sep 2026")] + PT[:2] + [("Against bill", "SUN/IP/2026/08817-B"), ("IP no.", "IP/2026/08817")])
    y = para(c, 36, y-6, "Received with thanks from Mr. Ravi Menon the sum of Rs 1,20,000 (Rupees One Lakh Twenty Thousand only) towards the in-patient bill for the stay from 08 Sep 2026 to 12 Sep 2026.", W-72, 11, 16) - 8
    y = table(c, 36, y, ["Particulars", "Amount (Rs)"], [("Total hospital bill", rs(420000)), ("Settled by Vidal Health TPA, cashless (claim VH-2026-448120)", rs(300000)), ("Paid by patient now", rs(120000)), ("Balance due", "0")], [415, 90], rh=20, right=(1,), boldrows=(2,))
    y = kv(c, 36, y-4, [("Mode of payment", "UPI"), ("Transaction ref.", "DEMO2026091200417")], 1, 100)
    sign(c, 380, 190, 81, 130, BLUE, "Cashier, Accounts", HOSP); seal(c, 270, 184, 46); foot(c); c.save()

# 11 registration copy
def registration():
    c = cv("11_hospital_registration_copy.pdf", "Hospital registration"); c.setStrokeColor(NAVY); c.setLineWidth(2.5); c.rect(30, 30, W-60, H-60); c.setLineWidth(.7); c.rect(36, 36, W-72, H-72)
    T(c, W/2, H-110, "CERTIFICATE OF REGISTRATION", 20, True, NAVY, "c"); T(c, W/2, H-132, "Clinical establishment, in-patient facility (attested copy)", 10, col=GREY, al="c")
    y = H-190; T(c, W/2, y, "This is to certify that", 11, al="c"); T(c, W/2, y-34, HOSP, 20, True, al="c"); T(c, W/2, y-54, "Road No. 36, Jubilee Hills, Hyderabad 500033", 11, al="c")
    y = para(c, 90, y-100, "has been registered as a 150-bedded multispeciality hospital with in-patient, operation theatre, intensive care, laboratory and imaging services, under the registration number below, subject to the conditions of the registering authority.", W-180, 11, 17)
    y = kv(c, 120, y-24, [("Registration no.", "SMH/HYD/2014/0417"), ("Date of first issue", "12 Jun 2014"), ("Valid from", "01 Apr 2023"), ("Valid until", "31 Mar 2028"), ("Beds", "150")], 1, 140, 11)
    T(c, 90, 190, "Attested true copy", 9, col=GREY); sign(c, 340, 170, 91, 140, BLUE, "Registering authority", "Clinical Establishments registry (fictional)"); seal(c, 200, 160, 52); foot(c); c.save()

claim_form(); tpa_card(); id_proof(); discharge(); ip_bill(); prescription(); pharmacy(True); pharmacy(False); investigations(); labs(); receipt(); registration()
print(sorted(os.listdir(OUT)))
