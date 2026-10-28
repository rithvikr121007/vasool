"""Fetches the REAL stats JSON for your three existing Gnani conversations and saves them unchanged.
No new call is needed. Put GNANI_API_KEY in .env, then:   python gnani_fetch_stats.py
Optional: pass other conversation ids as arguments. The key is never printed."""
import os, sys, json, requests
from dotenv import load_dotenv
load_dotenv()
KEY = os.environ.get("GNANI_API_KEY")
if not KEY: sys.exit("Put GNANI_API_KEY=... in .env first (Gnani Agents, account menu, Settings, API Keys).")
IDS = sys.argv[1:] or ["1791043954690585251", "1791044401569985251", "1791044554895085251"]
os.makedirs("gnani_real", exist_ok=True)
for cid in IDS:
    r = requests.get(f"https://api.inya.ai/platform/v1/conversations/{cid}/stats", headers={"x-api-key": KEY, "Accept": "application/json"}, timeout=30)
    try: body = r.json()
    except Exception: body = {"raw": r.text}
    path = f"gnani_real/stats_{cid}.json"
    with open(path, "w", encoding="utf-8") as f: json.dump(body, f, indent=2, ensure_ascii=False)
    print(cid, "HTTP", r.status_code, "->", path)
    if r.status_code >= 300: print("  ", json.dumps(body)[:300])
print("Done. These files are exactly what Gnani returned. Share them as your proof.")
