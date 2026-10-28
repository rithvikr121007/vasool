# Vasool: an AI agent that recovers the rest of a health-insurance claim

Built for The Ken Case-Build Competition 2026 (shortlisted to Semi-Finals nationally). All people, hospitals, insurers and documents in this project are fictional.

## The problem
When a first insurer pays only part of a hospital bill, the patient can claim the balance from a second insurer, but the two insurers don't coordinate. The patient has to collect settlement notes, assemble a document pack and chase a courier. Many give up and the claim lapses.

## What Vasool does
A claimant signs in, confirms three details, and uploads their documents. Vasool then:
1. **Reads and verifies each document** with a vision model (legibility, hospital seal and signature, matching IDs) and asks for a retake with a specific reason when something is wrong.
2. **Phones the primary insurer** (Gnani voice agent) to get the settlement note, and extracts the paid and outstanding amounts from the transcript.
3. **Works out eligibility** by classifying each bill line against the second insurer's policy schedule (payable, non-payable, sub-limits) and shows the claimant the amount and why.
4. **Fills the second insurer's claim form**, audits the full document checklist, and flags what is missing.
5. **Asks for an OTP and a fee hold** (UPI one-time mandate), books a reverse pickup, tracks delivery, confirms receipt with the insurer by phone, and captures the fee only after the insurer pays the full amount.

<img width="1911" height="1058" alt="05_documents_ready_to_send png" src="https://github.com/user-attachments/assets/1791f941-87d7-4eb6-9174-6ee74a2223d3" />
<img width="1917" height="1077" alt="04_documents_upload png" src="https://github.com/user-attachments/assets/45b545a3-6109-4cbd-bb1b-3e0883757d8d" />
<img width="1916" height="1072" alt="03_your_claim png" src="https://github.com/user-attachments/assets/c07de615-b66a-4df0-aaf2-91a25132c49b" />




## How it works
- **Agent:** Gemini (gemini-3.1-flash-lite) in a tool-calling loop. A written system prompt defines rules R0 to R7, hard limits (for example one fee capture only, no dispatch before authorisation) and an evidence standard for document verification.
- **Tools (12):** chat send, OTP, document status, timeline, screen control, Gnani call / find conversation / read stats, Pine Labs, Delhivery, Sheets, Gmail.
- **Server:** Flask. A stage-driven web app (polls `/state`) shows the claimant what the agent decides. A Telegram bot is the claimant's chat channel.
- **Wizard-of-Oz console:** the parts that don't exist yet (Pine Labs and Delhivery responses) are played by a person from the providers' documentation.

## What is real and what is simulated
| Part | Status |
|---|---|
| Gemini agent loop, tool calls, document reading and verification | Real |
| Telegram channel, OTP, web app | Real |
| Gnani voice calls | Real calls placed from the Gnani dashboard to a whitelisted phone. In the recorded run, the agent's Gnani calls are answered by a replay of those conversations (IDs, durations, transcripts). |
| Pine Labs UPI one-time mandate | Simulated from Pine Labs' documentation |
| Delhivery reverse pickup and tracking | Simulated from Delhivery's documentation |
| Documents, people, insurers | Fictional, generated for the demo |

## Engineering notes
- **Rate limits and outages:** retries with backoff on 429 and 503, optional fallback models, request pacing, and stripping of file payloads from history after review to cut token use.
- **Channel change:** WhatsApp (Meta Cloud API) was blocked by business verification, so the chat channel moved to Telegram.
- **Document verification:** the model must name the detected document type and cite visible evidence before it may mark a document verified.

## Run it
```
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env     # then fill in your own keys (see names inside)
python app.py
```
Open `/claim` for the claimant view and `/wizard` for the console. Never commit `.env`, `credentials.json` or tokens.

## Known limitations (what I would change next)
- Some demo events (delivery steps) were written by the app, not driven by the agent's own tracking calls.
- Decisions are logged but do not yet carry the rule they followed in a structured field.
- Gnani responses in the recording were replayed, not fetched live; raw API JSON was not captured.

## Not affiliated
This is a student project. It is not affiliated with The Ken, Gnani, Pine Labs, Delhivery or any insurer.

## Repository layout
- `app.py`, `prompt.md`: Flask server and the agent's system prompt
- `templates/`: claimant view (`claim.html`) and Wizard-of-Oz console (`wizard.html`)
- `mock_documents/`: 12 fictional PDFs and their generator (`make_docs.py`)
- `docs/`: competition write-up and API reference notes
- `tools/`: scripts used to fetch Gnani conversation stats
- Set `GNANI_WHITELIST` in `.env` to your own test number; it defaults to empty.
