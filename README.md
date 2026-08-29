# Voice AI Agent — Patient Registration System

A voice-based AI agent, reachable by phone, that conversationally registers new patients, persists their demographic data to a database, and exposes that data through a REST API and a live dashboard. Built as a take-home technical assessment.

## Live Deliverables

- **Phone number:** `+1 (810) 267 8478`
- **API base URL:** `https://voice-patient-registration-production-1afc.up.railway.app`
- **API docs (Swagger UI):** `https://voice-patient-registration-production-1afc.up.railway.app/docs`
- **Dashboard (read-only patient view):** `https://voice-patient-registration-production-1afc.up.railway.app/dashboard`
- **Repository:** `https://github.com/tabidah-usmani/voice-patient-registration`
- **System prompt (full, commented):** [`system_prompt.md`](./system_prompt.md)

## Overview

A caller dials the phone number above and speaks naturally with a voice AI agent (built on Vapi) acting as an intake coordinator. The agent collects standard U.S. patient demographic fields, confirms the information back to the caller, and saves the record through a FastAPI backend into a persistent Postgres database. If the caller has registered before (matched by phone number), the agent recognizes them and offers to update their existing record instead of creating a duplicate. A separate REST API allows querying, creating, updating, and soft-deleting patient records independently of the voice flow, and a read-only dashboard gives a visual view of all registered patients. Call transcripts from every phone call are also captured and linked to the matching patient record where possible.

## Architecture

```
Phone Call (Caller)
        |
        v
  Vapi Voice Agent  (LLM + Telephony + STT/TTS)
        |
        |-- tool calls -------------------> /vapi/* adapter endpoints (FastAPI)
        |                                           |
        |                                           v
        |                                   Service layer (crud.py)  <----  /patients REST API (external clients)
        |                                           |
        |                                           v
        |                                   PostgreSQL (Neon, hosted)
        |
        '-- end-of-call webhook ----------> /vapi/call-ended --------------> call_transcripts table

                                            /dashboard  --(reads)-->  /patients
```

**Why an adapter layer (`/vapi/*` routes) instead of pointing Vapi directly at `/patients`:**
Vapi's tool-call webhook wraps function arguments inside its own JSON envelope (`message.toolCalls[0].function.arguments`), rather than sending a flat body matching the target schema. Rather than bending the public REST API's contract to accommodate one client's webhook format, dedicated adapter endpoints (`/vapi/register-patient`, `/vapi/lookup-patient`, `/vapi/update-patient`, `/vapi/schedule-appointment`, `/vapi/call-ended`) unwrap Vapi's envelope and delegate to the same `crud.py` service functions used by the public API. This keeps `/patients` RESTful and standards-compliant for any other consumer, while giving Vapi exactly the interface it needs.

## Tech Stack & Justification

| Layer | Choice | Why |
|---|---|---|
| Telephony + Voice AI | **Vapi** | Abstracts STT/TTS/turn-taking and phone provisioning, letting the time budget go toward prompt design and integration rather than building a speech pipeline from scratch. |
| LLM | Vapi's integrated model (Claude Sonnet) | Handles natural conversation, corrections, and tool-calling without separate orchestration code. |
| Backend | **FastAPI (Python)** | Async, fast to scaffold, and Pydantic gives free server-side request validation — directly satisfying the "validate all inputs server-side" requirement. |
| Database | **PostgreSQL (hosted on Neon)** | Originally planned as SQLite per the assessment's suggested shortcuts, but Railway's free tier does not expose persistent volumes, so SQLite's on-disk file would not survive redeploys. Neon's free-tier Postgres gives guaranteed persistence regardless of the app container's lifecycle, with no code changes needed beyond the connection string (SQLAlchemy abstracts the dialect). |
| Hosting | **Railway** | One-click deploy from GitHub, environment variable management, and public HTTPS domain generation. |
| Dashboard | Plain HTML/CSS/JS served directly by FastAPI | No build step, no extra hosting target, no new dependency — reads live from the existing `GET /patients` endpoint. |

## Data Model

The `patients` table implements all 19 fields specified in the assessment brief (`patient_id`, name, date of birth, sex, contact info, address, insurance, emergency contact, and auto-managed timestamps), with a nullable `deleted_at` column used for soft-delete rather than hard-deleting records.

A second table, `call_transcripts`, stores the transcript, AI-generated summary (if enabled), and Vapi call ID for every completed phone call, linked to `patient_id` when a phone-number match is found at call end.

Server-side validation (via Pydantic, independent of whatever the voice agent already checked) enforces:
- Names: 1–50 alphabetic characters, hyphens, or apostrophes
- Date of birth: valid date, not in the future
- Sex: restricted to `Male`, `Female`, `Other`, `Decline to Answer`
- Phone numbers: exactly 10 digits (US), coerced to string before validation (see Known Limitations)
- State: valid 2-letter U.S. abbreviation
- ZIP code: 5-digit or ZIP+4 format

## REST API

All responses use a consistent envelope: `{ "data": ..., "error": ... }`.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Root status check — confirms the API is live and links to `/docs`. |
| GET | `/patients` | List all patients. Supports `?last_name=`, `?date_of_birth=`, `?phone_number=` filters. |
| GET | `/patients/{id}` | Retrieve a single patient by UUID. |
| GET | `/patients/{id}/calls` | Retrieve all call transcripts linked to a patient. |
| GET | `/calls` | Retrieve the 50 most recent call transcripts across all patients (used by the dashboard's call-count stat). |
| POST | `/patients` | Create a new patient. Rejects duplicate phone numbers with a 400. |
| PUT | `/patients/{id}` | Partial update of an existing patient. |
| DELETE | `/patients/{id}` | Soft-delete (sets `deleted_at`; record is never hard-deleted). |
| GET | `/dashboard` | Read-only HTML dashboard listing all registered patients, with stats including total patients, insurance/emergency-contact coverage, and recorded call count. |

Internal adapter endpoints used only by the Vapi voice agent:

| Method | Endpoint | Description |
|---|---|---|
| POST | `/vapi/lookup-patient` | Checks whether a patient exists for a given phone number. |
| POST | `/vapi/register-patient` | Creates a new patient from a Vapi tool call. |
| POST | `/vapi/update-patient` | Updates an existing patient (identified by phone number) from a Vapi tool call. |
| POST | `/vapi/schedule-appointment` | Schedules a mock first appointment after registration, from a Vapi tool call. |
| POST | `/vapi/call-ended` | End-of-call webhook; stores the call transcript and links it to a patient if one matches by phone number. |

## Voice Agent Design

The assistant is configured with a system prompt (full text in [`system_prompt.md`](./system_prompt.md)) instructing it to:

1. Collect required fields (name, DOB, sex, phone, address) conversationally, in natural groupings rather than as a rigid checklist.
2. Look up the caller by phone number as soon as it's given, **before** asking anything further, using the `lookup_patient_by_phone` tool.
3. If a match is found, offer to update the existing record instead of creating a duplicate, and route to the `update_patient` tool rather than `register_patient`.
4. Re-prompt for a specific field (not the whole conversation) when given invalid input, rather than silently accepting it.
5. Handle corrections mid-conversation naturally (e.g., a caller re-spelling their last name) without restarting the flow.
6. Allow the caller to explicitly restart the conversation at any point.
7. Read back the full set of collected information and require explicit confirmation before saving.
8. Only after confirmation, offer optional fields (insurance, emergency contact, preferred language) as an opt-in bundle, per the assessment's conversational note.
9. On a save failure, apologize once, retry, and — if it still fails — offer a callback rather than leaving the caller with silence or a dead end.

Four tools connect the LLM to the backend: `lookup_patient_by_phone`, `register_patient`, `update_patient`, and `schedule_appointment`, each mapped to one of the `/vapi/*` adapter endpoints described above. The first three are fully verified over real inbound phone calls; `schedule_appointment` has been verified via Vapi's web-call testing widget. A separate, non-tool end-of-call webhook (`/vapi/call-ended`) fires automatically when each call ends, independent of anything the LLM decides — this is how call transcripts get captured even if a call ends unexpectedly mid-conversation. This webhook has been verified against Vapi's web-call testing widget but not yet against a real PSTN call (see Known Limitations).

## Bonus Features Implemented

Beyond the core requirements, the following bonus items from the assessment brief were implemented and tested:

- **Duplicate Detection:** The agent recognizes returning callers by phone number (via `lookup_patient_by_phone`) and offers to update their existing record instead of creating a duplicate. Fully verified over real phone calls.
- **Multi-language Support:** The system prompt instructs the agent to detect when a caller speaks in or requests another language (e.g., "Hablo español") and switch its responses accordingly for the remainder of the call.
- **Appointment Scheduling (mock):** After a successful registration, the agent offers to schedule a first appointment via a `schedule_appointment` tool, which returns mock confirmation details (no real calendar integration, per the assessment's guidance that mock data is acceptable). During development, this tool was initially misconfigured with the wrong webhook URL (pointing at the update-patient endpoint instead of its own), which was caught via call transcript review and corrected.
- **Call Recording/Transcript Storage:** Every call's transcript is captured via Vapi's end-of-call webhook and stored in a dedicated `call_transcripts` table, linked to the matching patient record by phone number where available. See the Data Model and REST API sections above.
- **Dashboard:** A read-only web dashboard (`/dashboard`) displays all registered patients with stats (total patients, insurance/emergency-contact coverage, and total recorded calls via `/calls`) and a searchable patient table, reading live from the existing `/patients` and `/calls` endpoints.
- **Automated Tests:** A pytest suite (`test_main.py`) covers patient CRUD, every field-level validation rule (state, DOB, phone, ZIP, sex), duplicate-phone rejection, and soft-delete behavior, running fully isolated against an in-memory SQLite database — no live server or external services required. See the Testing section below.



### Environment variables

```
DATABASE_URL=postgresql://<user>:<password>@<host>/<dbname>?sslmode=require
```

### Local development

```bash
python -m venv venv
venv\Scripts\Activate.ps1        # Windows PowerShell
# source venv/bin/activate       # macOS/Linux

pip install -r requirements.txt
uvicorn app.main:app --reload
```

Visit `http://127.0.0.1:8000/docs` for interactive API testing, or `http://127.0.0.1:8000/dashboard` for the patient dashboard.

### Deployment (Railway)

1. Connect the GitHub repo to a new Railway service.
2. Set the **Custom Start Command** (Settings → Deploy):
   ```
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
3. Add the `DATABASE_URL` environment variable pointing to a hosted Postgres instance (e.g. Neon).
4. Generate a public domain under Settings → Networking.

### Vapi configuration

1. Provision a phone number in the Vapi dashboard (this was provided free on Vapi's trial plan).
2. Create four tools (`lookup_patient_by_phone`, `register_patient`, `update_patient`, `schedule_appointment`), each a POST request to the corresponding `/vapi/*` endpoint above.
3. Set the assistant's **Server URL** (end-of-call webhook) to `/vapi/call-ended`, so transcripts are captured automatically at the end of every call.
4. Create an assistant with the system prompt in `system_prompt.md`, attach all three tools to it.
5. Attach the assistant to the phone number under the number's inbound assistant setting.

## Testing

Run the automated test suite with:
```bash
pip install pytest httpx
pytest test_main.py -v
```

This covers patient creation, retrieval, filtering, partial updates, soft-deletion, every field-level validation rule (invalid state, future date of birth, malformed phone number, invalid ZIP, invalid sex value), duplicate-phone rejection, and the root status endpoint — 18 tests total, running fully isolated against an in-memory SQLite database with no dependency on the live deployment, Postgres, or Vapi.

## Known Limitations & Trade-offs

- **No persistent volume on Railway's free tier** was the reason for switching from the originally planned SQLite to hosted Postgres (Neon) partway through development — documented here as the trade-off it was, rather than silently working around it.
- **Vapi's LLM occasionally emits phone numbers as JSON numbers rather than strings** in tool-call arguments, despite the tool schema declaring them as strings. This caused a Postgres type-mismatch error (`character varying = bigint`) on first integration. Fixed with defensive string coercion at the API boundary rather than relying solely on the LLM to respect the declared schema type.
- **Update-by-phone-number, not by UUID:** the `update_patient` tool identifies the record to update using the caller's phone number rather than requiring the agent to track and pass back a UUID across the conversation. This is simpler and more robust for an LLM to use correctly, at the cost of not supporting updates to the phone number field itself in the same call.
- **Call transcripts are only linked to a patient if their phone number matches an existing record at the time the call ends.** A call where a caller registers for the first time will link correctly, since the record is created before the call ends; a caller who never completes registration will have their transcript stored with `patient_id = null`.
- **Web test calls made from Vapi's dashboard widget do not include a phone number** (they use a `webCall` type with no caller ID), so transcripts from those test calls are intentionally skipped rather than saved with missing data — this only affects development-time testing, not real phone calls.
- **The end-of-call transcript-saving webhook has not been verified against a real inbound PSTN phone call**, only against Vapi's web-call widget (which, as noted above, carries no caller ID). The developer is based in Pakistan; two free verification paths were attempted and both were blocked by cost/plan restrictions rather than a code issue: (1) placing an outbound international call directly to the provisioned US number would incur real charges, and (2) Vapi's own outbound test-call feature, which would otherwise let Vapi dial out to a developer-supplied number at no cost, does not support international destinations on the free/trial phone number tier used for this assessment. The registration, lookup, and update flows were all fully verified over real phone calls placed earlier in development (calls made *to* the provisioned US number from a US-reachable line), so the tool-calling integration itself is confirmed working end-to-end over the phone — only the newer, separately-added end-of-call transcript webhook remains unverified specifically against a real (non-web) call. The endpoint code handles the expected Vapi payload shape and degrades safely (skips the save, logs the reason) if the phone number field is ever missing or in an unexpected format, so a live confirmation on a real call is a recommended first check during review, ideally by a US-based reviewer calling the number directly.
- **Vapi records and stores call audio** on its own infrastructure by default; no HIPAA compliance is claimed or required, per the assessment's explicit scope (no real patient data is used).
- **No automated test suite** was built given the time budget; manual testing was done via Swagger UI, the dashboard, and live test calls.
- **Retry logic in the voice agent** is prompt-driven (the LLM decides to retry and eventually offer a callback) rather than governed by explicit backend retry/backoff logic.
- **Remaining gaps:** the dashboard is intentionally read-only (no in-place editing), matching the assessment's suggestion of a display view rather than a management interface.

## Next Steps

With more time, the following would be prioritized:
- Support for updating a caller's phone number itself (currently used as the lookup key)
- Dashboard editing capability and a dedicated recent-calls table view (currently a count only)
- Explicit backend-level retry/backoff for tool-call failures, rather than relying on prompt instructions alone
- Broader automated test coverage extending into the `/vapi/*` adapter endpoints and the appointment-scheduling/lookup flows