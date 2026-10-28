# Q4: Every call Vasool makes to Pine Labs, Delhivery and Gnani

**How to read this.** Amounts are in paise (Rs 1,499 = 149900). **Gnani:** the calls were real. We placed them from the Gnani dashboard and spoke the insurers' side; the screenshots and voice recordings are in our evidence folder (link in the submission). **Pine Labs and Delhivery:** we played these rails from their documentation, so the responses are shaped after the fields each page describes (key fields shown), not copied from live accounts.

| Rail | Base URL | Documentation |
|---|---|---|
| Gnani | `https://api.inya.ai/platform` (header `x-api-key`) | docs.gnani.ai/Platform/Trigger_Call, /Get_Conversation_Logs, /Get_Conversation_Stats |
| Pine Labs | UAT `https://pluraluat.v2.pinepg.in`, production `https://api.pluralpay.in` (headers `Authorization: Bearer <token>`, `Merchant-ID`; the payments call also carries `Request-ID` and `Request-Timestamp`) | pinelabs.com/docs/online-payments/one-time-mandate/integration-steps |
| Delhivery | `https://track.delhivery.com` (header `Authorization: Token <API token>`) | delhivery-express-api-doc.readme.io: order-creation-api, pickup-request-creation-api, order-tracking-api, reverse-pickups |

---

## PART A: GNANI (voice calls to the whitelisted lines)

Vasool makes three calls: primary TPA (settlement note), Sanjeevani (receipt check), Sanjeevani (payout check). Each call uses the same three documented endpoints.

**What is real and what is replayed.** We built a Gnani voice agent named "vasool" in the Agent Builder, whitelisted our own phone, placed three real calls from the dashboard (Trigger Agent Call) and spoke the insurer's lines. The three conversations are in the dashboard under Monitor, Conversations. We could not retrieve the raw API JSON in time, so in the recorded run the agent's Gnani calls are answered by a replay of those real conversations. The conversation IDs, call durations and transcript wording are from the real calls. The other fields in the envelope follow Gnani's documented schema.

### A1. Trigger Call
- **Endpoint:** `POST /v1/agents/{botId}/trigger_call?environment=development`
- **Why:** place the outbound call (rules R2, R6, R7). Only whitelisted numbers work.
- **Request (call 1):** `{"phone": "98XXXXXXXX", "countryCode": "+91", "name": "Ravi Menon", "clientReferenceId": "TPA_SETTLEMENT-SJV-5540218"}`
- **Response (as documented):** `{"status": "success", "message": "Call is being triggered to 98XXXXXXXX"}`
- **Note:** the response carries no conversationId, so Vasool must look it up (A2).
- **Calls 2 and 3** use the same body with `CONFIRM_DELIVERY-SJV-5540218` and `CHECK_SETTLEMENT-SJV-5540218` as the `clientReferenceId`.

### A2. Find the conversation
- **Endpoint:** `POST /v1/conversations/logs?environment=development`
- **Request:** `{"searchTerm": "TPA_SETTLEMENT-SJV-5540218", "pageNo": 1, "pageSize": 5}`
- **Response (key field):** conversationId `1791043954690585251` (real, from the dashboard). Calls 2 and 3: `1791044401569985251` and `1791044554895085251`.

### A3. Read the call result
- **Endpoint:** `GET /v1/conversations/{conversationId}/stats`
- **Request:** `GET /v1/conversations/1791043954690585251/stats`
- **Response, call 1:** callStatus `ANSWERED`, 55 s, disposition `SETTLEMENT_NOTE_OBTAINED`. The transcript (`utteranceAnalytics`, roles assistant and user) includes: "rupees one lakh twenty thousand is outstanding of which eight thousand is non payable items the settlement note reference is vhsn nine zero four one seven".
- **Response, call 2:** 39 s, `RECEIPT_CONFIRMED`. Transcript includes: "twelve documents received in complete claim number sjv cl two zero two six zero nine four one seven".
- **Response, call 3:** 33 s, `DISBURSEMENT_CONFIRMED`. Transcript includes: "rupees one lakh twelve thousand has been disbursed to the policyholders registered account today".

---

## PART B: PINE LABS (Rs 1,499 UPI One-Time Mandate: reserve first, capture after settlement)

Flow: token, customer, one-time subscription, register mandate, check ACTIVE, (later) presentation, check SUCCESS.

### B1. Get access token
- **Endpoint:** `POST /api/auth/v1/token`
- **Request:** `{"client_id": "<id>", "client_secret": "<secret, masked>", "grant_type": "client_credentials"}`
- **Response:** `{"access_token": "eyJhbGciOi...", "expires_in": 3600}`

### B2. Create the customer
- **Endpoint:** `POST /api/v1/customer`
- **Request:** `{"merchant_customer_reference": "CUST-SJV-5540218", "first_name": "Ravi", "last_name": "Menon", "country_code": "91", "mobile_number": "9848012345", "email_id": "ravimenon@gmail.com"}`
- **Response:** `{"customer_id": "cust-v1-968ffaa21c18", "first_name": "Ravi", "last_name": "Menon", "status": "ACTIVE"}`

### B3. Create the one-time subscription (the fee hold)
- **Endpoint:** `POST <subscription-base-url>/api/v1/public/subscriptions/ot`
- **Request:** `{"merchant_subscription_reference": "SUB-SJV-5540218", "customer_id": "cust-v1-968ffaa21c18", "plan_details": {"amount": 149900, "currency": "INR", "validity_days": 30, "description": "Vasool service fee hold"}}`
- **Response:** `{"subscription_id": "v1-sub-261003172447-aa-c99afb", "order_id": "v1-261003172447-aa-8kQz2m", "status": "CREATED", "execution_mode": "DIRECT_EXECUTION", "plan_details": {"amount": 149900, "currency": "INR", "frequency": "OT"}}`
- **Rule from the docs:** the amount here is the most that can ever be captured.

### B4. Register the mandate (Ravi approves in his UPI app)
- **Endpoint:** `POST /api/pay/v1/orders/{order_id}/payments` (the `order_id` comes from B3)
- **Request:** `{"payments": [{"merchant_payment_reference": "PAY-SJV-5540218", "payment_amount": {"value": 149900, "currency": "INR"}, "payment_method": "UPI", "payment_option": {"upi_details": {"txn_mode": "INTENT"}}, "mandate_info": {"request_type": "CREATE_MANDATE"}}]}`
- **Response:** `{"data": {"order_id": "v1-261003172447-aa-8kQz2m", "status": "PENDING", "payments": [{"status": "PENDING", "payment_method": "UPI", "payment_amount": {"value": 149900, "currency": "INR"}}]}}`
- **Rule from the docs:** `payment_amount.value` must equal the subscription amount.

### B5. Confirm the hold is ACTIVE (before dispatch)
- **Endpoint:** `GET <subscription-base-url>/api/v1/subscriptions/ot/{subscription_id}`
- **Request:** `GET /api/v1/subscriptions/ot/v1-sub-261003172447-aa-c99afb`
- **Response:** `{"subscription_id": "v1-sub-261003172447-aa-c99afb", "status": "ACTIVE", "execution_mode": "DIRECT_EXECUTION", "plan_details": {"amount": 149900, "currency": "INR", "frequency": "OT"}}`

### B6. Capture the fee (once, only after the insurer confirms Rs 1,12,000)
- **Endpoint:** `POST <subscription-base-url>/api/v1/public/presentations`
- **Request:** `{"subscription_id": "v1-sub-261003172447-aa-c99afb", "amount": {"value": 149900, "currency": "INR"}, "merchant_presentation_reference": "PRES-SJV-5540218"}`
- **Response:** `{"subscription_id": "v1-sub-261003172447-aa-c99afb", "presentation_id": "v1-bil-261012110000-aa-pr7Hw", "amount": {"value": 149900, "currency": "INR"}, "merchant_presentation_reference": "PRES-SJV-5540218", "status": "PENDING"}`
- **Rule from the docs:** the mandate closes after one successful capture, so a second capture is impossible.

### B7. Check the capture result
- **Endpoint:** `GET <subscription-base-url>/api/v1/public/presentations/reference/{merchant_presentation_reference}`
- **Request:** `GET /api/v1/public/presentations/reference/PRES-SJV-5540218`
- **Response:** `{"subscription_id": "v1-sub-261003172447-aa-c99afb", "merchant_presentation_reference": "PRES-SJV-5540218", "amount": {"value": 149900, "currency": "INR"}, "status": "SUCCESS"}`

---

## PART C: DELHIVERY (pickup from Ravi's home, delivery to the claims office)

### C1. Create the reverse-pickup shipment
- **Endpoint:** `POST /api/cmu/create.json` (sent as `format=json&data=<JSON>`)
- **Request (the `data` JSON):** `{"shipments": [{"name": "Ravi Menon", "add": "Flat 402, Lakeview Residency, Madhapur, Hyderabad 500081", "phone": "9848012345", "order": "SJV-5540218", "pin": "500081", "payment_mode": "Pickup", "return_name": "Claims Desk, Sanjeevani Health Insurance", "return_add": "Banjara Hills, Hyderabad", "return_pin": "500034", "return_city": "Hyderabad", "return_state": "Telangana", "return_country": "India", "return_phone": "98XXXXXXXX"}], "pickup_location": {"name": "VASOOL_MAIN"}, "qc_type": "param", "custom_qc": {"items": [{"question": "Is the discharge summary original and signed?", "options": ["Yes", "No"]}, {"question": "Are all bills original and sealed?", "options": ["Yes", "No"]}]}}`
- **Response:** `{"success": true, "package_count": 1, "packages": [{"status": "Success", "client": "VASOOL_MAIN", "waybill": "VSLDEMO20261002", "payment": "Pickup", "serviceable": true}]}`
- **Rules from the docs:** `payment_mode: Pickup` marks the shipment as a reverse pickup. Without the `return_*` fields it would be delivered to our own warehouse. `pickup_location.name` must exactly match the registered warehouse name.
- **QC limit** (from our Round 2 research of the Delhivery QC settings): at most 2 QC items and 6 questions per item, otherwise QC is silently dropped.

### C2. Book the pickup slot (once)
- **Endpoint:** `POST /fm/request/new/`
- **Request:** `{"pickup_date": "2026-10-04", "pickup_time": "10:00:00", "pickup_location": "VASOOL_MAIN", "expected_package_count": 1}`
- **Response:** `{"pickup_id": 44225522, "pickup_location": "VASOOL_MAIN", "pickup_date": "2026-10-04", "pickup_time": "10:00:00", "expected_package_count": 1}`
- **Rule from the docs:** a new request for the same warehouse is allowed only after the earlier one is completed.
- **Note:** Delhivery's reverse-pickup statuses also move to "Scheduled" automatically after manifesting. We use this call to fix the slot the claimant chose.

### C3. Track the shipment (repeated as each status arrives)
- **Endpoint:** `GET /api/v1/packages/json/?waybill={waybill}&ref_ids={order}`
- **Request:** `GET /api/v1/packages/json/?waybill=VSLDEMO20261002&ref_ids=SJV-5540218`
- **Responses in order** (the documented reverse-pickup statuses): PP Open, PP Scheduled, PP Dispatched, PU In Transit, PU Pending, PU Dispatched, DL DTO.
- **Final response (key fields):** `{"ShipmentData": [{"Shipment": {"AWB": "VSLDEMO20261002", "Status": {"Status": "DTO", "StatusType": "DL"}, "Scans": [{"ScanDetail": {"ScanType": "DL", "Scan": "DTO", "Instructions": "Pickup shipment accepted by client and POD received"}}]}}]}`
- **Limit from the docs:** 750 requests per 5 minutes per IP.

### C4. Download the delivery signature
- **Endpoint:** `GET /api/rest/fetch/pkg/document/?doc_type=SIGNATURE_URL&waybill={waybill}`
- **Request:** `GET /api/rest/fetch/pkg/document/?doc_type=SIGNATURE_URL&waybill=VSLDEMO20261002`
- **Response:** the signature image URL for the waybill (in the simulation, the curtain returns our sample signature image).
- **Source:** Delhivery's Download Document API, found in their developer documentation during our Round 2 research. [Add the link you used.]
- **Why this matters:** a signature shows someone signed, not who. So Vasool then calls Sanjeevani through Gnani (A1 to A3) to confirm receipt.

---

## PART D: Three capabilities that do not exist yet

### D1. Gnani: typed figures from a call
- **Partner:** Gnani
- **Endpoint:** `GET /v1/conversations/{conversationId}/entities`
- **Returns:** `{"entities": [{"type": "AMOUNT_INR", "value": 112000, "confidence": 0.97, "utterance_index": 3}, {"type": "REFERENCE_NO", "value": "SJV-CL-2026-09417", "confidence": 0.94}]}`
- **Why it is possible:** Gnani already holds the call audio, the speech-recognition output for every turn, and number-in-words handling across Indian languages, so it could return the rupee figure directly. Today Vasool reads "rupees one lakh twelve thousand" out of the transcript text itself.

### D2. Delhivery: who actually received the pack
- **Partner:** Delhivery
- **Endpoint:** `GET /api/rest/fetch/pkg/receiver-details/?waybill={waybill}`
- **Returns:** `{"receiver_name": "...", "receiver_designation": "...", "delivery_otp_verified": true, "scan_time": "..."}`
- **Why it is possible:** Delhivery's delivery agent app already records the handover, the delivery scan time and the agent's location. As far as the public documentation shows, only the signature image is exposed.

### D3. Pine Labs: will this person's UPI account accept the hold?
- **Partner:** Pine Labs
- **Endpoint:** `POST /api/v1/public/subscriptions/ot/eligibility`
- **Request:** `{"customer_id": "cust-v1-968ffaa21c18", "amount": 149900, "currency": "INR"}`
- **Returns:** `{"eligible": true, "bank_supports_otm": true}` (or `"eligible": false` with a reason)
- **Why it is possible:** Pine Labs already knows which banks and UPI apps support One-Time Mandates and how each behaves; its own docs say bank behaviour varies. Checking first stops Ravi from being sent a hold that fails after he has uploaded everything.
