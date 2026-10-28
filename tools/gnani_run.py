"""Runs one real Gnani call end to end and saves the exact responses.
Usage (venv active, in your project folder):
    python gnani_run.py TPA_SETTLEMENT-VH-2026-448120 98XXXXXXXX "Vidal Health TPA"
      args: <clientReferenceId> <whitelisted 10-digit phone> <name>
Needs in .env:  GNANI_API_KEY=...      (optional: GNANI_BOT_ID=...; if missing, it finds your agent named 'vasool')
Never paste the key anywhere else. Saves gnani_real/<ref>_trigger.json, _logs.json, _stats.json and prints them."""
import os, sys, json, time, requests
from dotenv import load_dotenv
load_dotenv()
KEY = os.environ.get("GNANI_API_KEY"); BOT = os.environ.get("GNANI_BOT_ID")
if not KEY or len(sys.argv) < 4: sys.exit(__doc__)
REF, PHONE, NAME = sys.argv[1], sys.argv[2].replace(" ", "")[-10:], sys.argv[3]
BASE = "https://api.inya.ai/platform"; H = {"x-api-key": KEY, "Content-Type": "application/json", "Accept": "application/json"}
os.makedirs("gnani_real", exist_ok=True)
def save(tag, r):
    try: body = r.json()
    except Exception: body = {"raw": r.text}
    with open(f"gnani_real/{REF}_{tag}.json", "w", encoding="utf-8") as f: json.dump(body, f, indent=2, ensure_ascii=False)
    print(f"\n===== {tag} (HTTP {r.status_code}) =====\n" + json.dumps(body, indent=2, ensure_ascii=False)[:6000]); return body
def find_dicts(x, key):
    if isinstance(x, dict):
        if key in x: yield x
        for v in x.values(): yield from find_dicts(v, key)
    elif isinstance(x, list):
        for v in x: yield from find_dicts(v, key)

if not BOT:
    ar = requests.get(f"{BASE}/v1/agents", params={"pageNo": 1, "pageSize": 10}, headers=H, timeout=30)
    try: agents = list(find_dicts(ar.json(), "botId"))
    except Exception: agents = []
    named = [a for a in agents if "vasool" in str(a.get("botName", "")).lower()] or agents
    if not named: sys.exit("Could not find your agent. Set GNANI_BOT_ID in .env (agent settings). HTTP %s" % ar.status_code)
    BOT = named[0]["botId"]; print("Using agent:", named[0].get("botName"), BOT)

T0 = time.time()
r = requests.post(f"{BASE}/v1/agents/{BOT}/trigger_call", params={"environment": "development"}, headers=H, timeout=30,
                  json={"phone": PHONE, "countryCode": "+91", "name": NAME, "clientReferenceId": REF})
save("trigger", r)
if r.status_code >= 300: sys.exit("Trigger failed. 400 usually means the number is not whitelisted; 401 or 403 means a key, permission or environment problem.")
input("\nYour phone should ring now. Answer it, play the insurer, speak the lines, finish the call, then press Enter here... ")

cid = None
for attempt in range(8):
    for params in ({"environment": "development", "botId": BOT}, {"environment": "development"}, {}):
        lr = requests.post(f"{BASE}/v1/conversations/logs", params=params, headers=H, timeout=30, json={"pageNo": 1, "pageSize": 10})
        if lr.status_code < 300: break
    try: rows = [d for d in find_dicts(lr.json(), "conversationId")]
    except Exception: rows = []
    rows = [d for d in rows if str(d.get("conversationId", "")).isdigit() or d.get("conversationId")]
    if rows:
        rows.sort(key=lambda d: float(d.get("startTime") or 0), reverse=True)
        cid = rows[0]["conversationId"]; save("logs", lr); print("Using conversation:", cid); break
    print(f"No conversation in the logs yet, waiting 15s ({attempt + 1}/8)..."); time.sleep(15)
if not cid: sys.exit("Could not find the conversation. Check Monitor, Conversations in the dashboard and run again.")

for attempt in range(8):
    sr = requests.get(f"{BASE}/v1/conversations/{cid}/stats", headers=H, timeout=30)
    if sr.status_code < 300: save("stats", sr); break
    print(f"Stats not ready (HTTP {sr.status_code}), waiting 15s ({attempt + 1}/8)..."); time.sleep(15)
else: sys.exit("Stats never became available.")
print("\nDone. The three files are in the gnani_real folder. Paste their contents into the chat (never the API key).")
