# Vasool API reference pack (fetched 3 Oct 2026)

Use this for Part 1 Q4 (exact endpoint, request, response) and for the wizard console. "Verified" means I read it on the provider's own docs page today. "Modelled" means the endpoint is real but the response body was not shown in the public page, so the sample follows the documented fields and should be checked against the provider's Try-It panel.

## 1. Gnani (Agent Builder Platform API)
Base URL `https://api.inya.ai/platform`. Auth header `x-api-key: <key>` (key needs the `agents` permission for calls, `conversations` for logs and stats).
Docs: docs.gnani.ai/Platform/Trigger_Call, /Get_Conversation_Logs, /Get_Conversation_Stats, docs.gnani.ai/A04_Whitelisting. Status: verified.

| Step | Endpoint | Request | Response (key fields) |
|---|---|---|---|
| 1 Place the call | `POST /v1/agents/{botId}/trigger_call?environment=development` | `{"phone":"98XXXXXXXX","countryCode":"+91","name":"Vidal Health TPA","clientReferenceId":"TPA_SETTLEMENT-VH-2026-448120"}` | `{"status":"success","message":"Call is being triggered to 98XXXXXXXX","response":{"clientReferenceId":"..."},"requestId":"..."}`. **No conversationId.** |
| 2 Find the call | `POST /v1/conversations/logs?environment=development` | `{"searchTerm":"TPA_SETTLEMENT-VH-2026-448120","pageNo":1,"pageSize":5}` | `response.data[0].conversationId`, `name`, `startTime`, `endTime` |
| 3 Read the result | `GET /v1/conversations/{conversationId}/stats` | none | `response[0].callStatus` (ANSWERED, NO ANSWER), `overallCallDisposition`, `utteranceAnalytics[]` with `role` (assistant or user), `content`, `timestamp`; `callSummary` may be null |

Gotchas from the docs: calls only go to whitelisted numbers (unlisted returns 400 "Phone number is not registered for outbound calls"); developer keys must pass `environment=development` (else 403); stats can lag 30 to 60 seconds after the call; `overallCallDisposition` codes are whatever your disposition prompt defines (your Round 2 research proposed SETTLEMENT_NOTE_OBTAINED, TPA_UNREACHABLE).

**How to run it for real (no code needed from the server):**
1. Open the Gnani Agent Builder dashboard (docs.gnani.ai/introduction). Create one agent per call script (TPA settlement, Sanjeevani receipt, Sanjeevani payout); copy each `botId`. Create an API key with the agents and conversations permissions.
2. Sidebar, Phone Numbers, Whitelisted, Add Number: add the phone of whoever will play the insurer (the verification OTP goes to that phone).
3. When the agent (`gnani_call`) asks for a call, the wizard console shows its request. Run step 1 yourself (curl or the dashboard Test, Trigger Agent Call), answer the phone as the TPA, wait a minute, run steps 2 and 3, and paste the real responses back.
4. In `.env` set `GNANI_MODE=real`.

Suggested call-agent prompts (paste into each Gnani agent): "You are Vasool, calling on behalf of claimant Ravi Menon (member VH-20458821, claim VH-2026-448120). Ask for the settlement status, the amount paid, the outstanding balance and the settlement note reference. Repeat each figure back once, then end the call politely." For the Sanjeevani agents change the purpose to confirming receipt of a courier pack (policy SJV-5540218) or the disbursed amount for claim SJV-CL-2026-09417.

## 2. Pine Labs (Online Payments, UPI One-Time Mandate)
Base URLs: UAT `https://pluraluat.v2.pinepg.in`, production `https://api.pluralpay.in`; `<subscription-base-url>` comes from your Pine Labs account manager (the SBMD sample shows `/ps` in front of the subscription paths). Headers: `Authorization: Bearer <token>`, `Merchant-ID` on subscription and presentation calls, `Request-ID` and `Request-Timestamp` on Payments. OTM must be enabled by the Pine Labs account manager, so the curtain plays this rail. **Amounts are in paise: Rs 1,499 = 149900.**
Docs: pinelabs.com/docs/online-payments/one-time-mandate/integration-steps. Status: request shapes verified; token, customer and presentation responses verified (same schemas on the Reserve Pay page); OT subscription, payment and fetch responses modelled on the documented fields.

| Step | Endpoint | Request (essentials) | Response (key fields) |
|---|---|---|---|
| 1 Token | `POST /api/auth/v1/token` | `{"client_id","client_secret","grant_type":"client_credentials"}` | `access_token`, `expires_in` |
| 2 Customer | `POST /api/v1/customer` | `merchant_customer_reference, first_name, last_name, country_code, mobile_number, email_id` | `customer_id`, `status: ACTIVE` |
| 3 OT subscription | `POST <subscription-base-url>/api/v1/public/subscriptions/ot` | `merchant_subscription_reference, customer_id, plan_details{amount:149900,currency:"INR",validity_days:30,description}, callback_url` | `subscription_id`, `order_id`, `status: CREATED`, `execution_mode: DIRECT_EXECUTION`, `plan_details.frequency: OT` |
| 4 Register mandate | `POST /api/pay/v1/orders/{order_id}/payments` | `payments[0]{payment_method:"UPI", merchant_payment_reference, payment_amount{value:149900,currency:"INR"}, payment_option{upi_details{txn_mode:"INTENT"}}, mandate_info{request_type:"CREATE_MANDATE"}}` | `data.status: PENDING` (challenge_url depends on environment) |
| 5 Check active | `GET <subscription-base-url>/api/v1/subscriptions/ot/{subscription_id}` | none | `status: ACTIVE` only after the claimant approves |
| 6 Capture | `POST <subscription-base-url>/api/v1/public/presentations` | `subscription_id, amount{value:149900,currency:"INR"}, merchant_presentation_reference, merchant_retry_id` | `presentation_id`, `status: PENDING`, `order_id`, `pdn_status` |
| 7 Confirm | `GET <subscription-base-url>/api/v1/public/presentations/reference/{merchant_presentation_reference}` | none | `status: SUCCESS` |

Rules from the docs: no presentation before the subscription is ACTIVE or RESUMED; presentation amount must not exceed `plan_details.amount`; references must be unique; one capture only (from your Round 2 notes: OTM closes after one capture and the claimant cannot revoke it from their UPI app).

## 3. Delhivery (Express API)
Auth header `Authorization: Token <token>`. Test base `https://staging-express.delhivery.com`, production `https://track.delhivery.com`. Docs: delhivery-express-api-doc.readme.io (Order Creation, Order Tracking, Pickup Request Creation, Reverse Pickups). You have no account, so the curtain plays this rail.

| Step | Endpoint | Request (essentials) | Response (key fields) | Status |
|---|---|---|---|---|
| 1 Create reverse-pickup shipment | `POST /api/cmu/create.json` | body `format=json&data={...}`; `shipments[]` with name, add, pin, phone, order, `payment_mode:"Pickup"`, return_* keys for the insurer's office; `pickup_location.name` must match the registered warehouse exactly (case sensitive); QC per your Round 2 research (max 2 items, 6 questions each) | `success`, `packages[0].waybill`, `payment:"Pickup"`, `serviceable` | endpoint and rules verified, response modelled |
| 2 Pickup request | `POST /fm/request/new/` | `pickup_time, pickup_date, pickup_location, expected_package_count` | `pickup_id` | request and URL verified; flagged assumption (docs describe warehouse pickups, RVP statuses also schedule automatically) |
| 3 Track | `GET /api/v1/packages/json/?waybill={wb}` | none | `ShipmentData[0].Shipment.Status{Status,StatusType,StatusDateTime,Instructions}`, `Scans[]` | URL verified, body modelled; 750 requests per 5 minutes per IP |
| 4 Proof of delivery | `GET /api/rest/fetch/pkg/document/?doc_type=SIGNATURE_URL&waybill={wb}` | doc_type SIGNATURE_URL, EPOD, RVP_QC_IMAGE or SELLER_RETURN_IMAGE | document URL | from your Round 2 research, not re-checked today |

Reverse-pickup status table (verified, from the docs): PP Open (request created), PP Scheduled, PP Dispatched (executive out to collect), PU In Transit, PU Pending (reached the processing centre), PU Dispatched (out to the client), **DL DTO (accepted by the client and POD received)**, CN Canceled, CN Closed. Use these exact statuses in the timeline.

## 4. Up to 3 imagined capabilities for Part 1 Q4 (list separately)
1. **Gnani structured extraction.** `GET /v1/conversations/{conversationId}/extractions` returning `{amount_paid, outstanding, reference, confidence}`. Gnani already holds the transcript and the disposition analytics for every call. Today Vasool parses the transcript itself and cross-checks (your claim_amount_extraction row).
2. **Delhivery receiver identity on the proof of delivery.** `GET /api/rest/fetch/pkg/document/?doc_type=RECEIVER_DETAILS&waybill={wb}` returning `{receiver_name, designation, delivery_otp_verified}`. Delhivery's field-executive app already captures the signature and the delivery moment. Today a signature proves someone signed, not who.
3. **Pine Labs mandate release.** `POST /api/v1/public/subscriptions/ot/{subscription_id}/release` for merchant-side release of an unused one-time mandate. Pine Labs already holds the mandate state. Needed when the fee is waived (nothing recoverable), since your Round 2 notes say the claimant cannot self-revoke an active OTM.

## 5. Corrections to make in the agent and the screens
- Gnani trigger returns no conversationId: the agent must call the logs endpoint (new tool `gnani_find_conversation`).
- Gnani transcript roles are `assistant` (your call agent) and `user` (the person called), not speaker names.
- Pine Labs uses paise and the Merchant-ID header; the fee hold is the OT subscription amount.
- Delhivery proof of delivery has no "signed by" field; do not display a name.
