# Voice AI Agent — Patient Registration System

A voice-based AI agent, reachable by phone, that conversationally registers new patients, persists their demographic data to a database, and exposes that data through a REST API. Built as a take-home technical assessment.

## Live Deliverables

- **Phone number:** `<YOUR VAPI PHONE NUMBER>`
- **API base URL:** `https://voice-patient-registration-production-1afc.up.railway.app`
- **API docs (Swagger UI):** `https://voice-patient-registration-production-1afc.up.railway.app/docs`
- **Repository:** `https://github.com/tabidah-usmani/voice-patient-registration`

## Overview

A caller dials the phone number above and speaks naturally with a voice AI agent (built on Vapi) acting as an intake coordinator. The agent collects standard U.S. patient demographic fields, confirms the information back to the caller, and saves the record through a FastAPI backend into a persistent Postgres database. If the caller has registered before (matched by phone number), the agent recognizes them and offers to update their existing record instead of creating a duplicate. A separate REST API allows querying, creating, updating, and soft-deleting patient records independently of the voice flow.

## Architecture

```
Phone Call (Caller)
        |
        v
  Vapi Voice Agent  (LLM + Telephony + STT/TTS)
        |
        v
  /vapi/* adapter endpoints  (FastAPI)
        |
        v
  Service layer (crud.py)  <----  /patients REST API (external clients)
        |
        v
  PostgreSQL (Neon, hosted)
```

**Why an adapter layer (`/vapi/*` routes) instead of pointing Vapi directly at `/patients`:**
Vapi's tool-call webhook wraps function arguments inside its own JSON envelope (`message.toolCalls[0].function.arguments`), rather than sending a flat body matching the target schema. Rather than bending the public REST API's contract to accommodate one client's webhook format, three thin adapter endpoints (`/vapi/register-patient`, `/vapi/lookup-patient`, `/vapi/update-patient`) unwrap Vapi's envelope and delegate to the same `crud.py` service functions used by the public API. This keeps `/patients` RESTful and standards-compliant for any other consumer, while giving Vapi exactly the interface it needs.

## Tech Stack & Justification

| Layer | Choice | Why |
|---|---|---|
| Telephony + Voice AI | **Vapi** | Abstracts STT/TTS/turn-taking and phone provisioning, letting the 3-hour budget go toward prompt design and integration rather than building a speech pipeline from scratch. |
| LLM | Vapi's integrated model | Handles natural conversation, corrections, and tool-calling without separate orchestration code. |
| Backend | **FastAPI (Python)** | Async, fast to scaffold, and Pydantic gives free server-side request validation — directly satisfying the "validate all inputs server-side" requirement. |
| Database | **PostgreSQL (hosted on Neon)** | Originally planned as SQLite per the assessment's suggested shortcuts, but Railway's free tier does not expose persistent volumes, so SQLite's on-disk file would not survive redeploys. Neon's free-tier Postgres gives guaranteed persistence regardless of the app container's lifecycle, with no code changes needed beyond the connection string (SQLAlchemy abstracts the dialect). |
| Hosting | **Railway** | One-click deploy from GitHub, environment variable management, and public HTTPS domain generation. |

## Data Model

The `patients` table implements all 19 fields specified in the assessment brief (`patient_id`, name, date of birth, sex, contact info, address, insurance, emergency contact, and auto-managed timestamps), with a nullable `deleted_at` column used for soft-delete rather than hard-deleting records.

Server-side validation (via Pydantic, independent of whatever the voice agent already checked) enforces:
- Names: 1–50 alphabetic characters, hyphens, or apostrophes
- Date of birth: valid date, not in the future
- Sex: restricted to `Male`, `Female`, `Other`, `Decline to Answer`
- Phone numbers: exactly 10 digits (US), with input type-coerced to string before validation
- State: valid 2-letter U.S. abbreviation
- ZIP code: 5-digit or ZIP+4 format

## REST API

All responses use a consistent envelope: `{ "data": ..., "error": ... }`.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/patients` | List all patients. Supports `?last_name=`, `?date_of_birth=`, `?phone_number=` filters. |
| GET | `/patients/{id}` | Retrieve a single patient by UUID. |
| POST | `/patients` | Create a new patient. Rejects duplicate phone numbers with a 400. |
| PUT | `/patients/{id}` | Partial update of an existing patient. |
| DELETE | `/patients/{id}` | Soft-delete (sets `deleted_at`; record is never hard-deleted). |

Internal adapter endpoints used only by the Vapi voice agent:

| Method | Endpoint | Description |
|---|---|---|
| POST | `/vapi/lookup-patient` | Checks whether a patient exists for a given phone number. |
| POST | `/vapi/register-patient` | Creates a new patient from a Vapi tool call. |
| POST | `/vapi/update-patient` | Updates an existing patient (identified by phone number) from a Vapi tool call. |

## Voice Agent Design

The assistant is configured with a system prompt instructing it to:

1. Collect required fields (name, DOB, sex, phone, address) conversationally, in natural groupings rather than as a rigid checklist.
2. Look up the caller by phone number as soon as it's given, **before** asking anything further, using the `lookup_patient_by_phone` tool.
3. If a match is found, offer to update the existing record instead of creating a duplicate, and route to the `update_patient` tool rather than `register_patient`.
4. Re-prompt for a specific field (not the whole conversation) when given invalid input, rather than silently accepting it.
5. Handle corrections mid-conversation naturally (e.g., a caller re-spelling their last name) without restarting the flow.
6. Read back the full set of collected information and require explicit confirmation before saving.
7. Only after confirmation, offer optional fields (insurance, emergency contact, preferred language) as an opt-in bundle, per the assessment's conversational note.
8. On a save failure, apologize once, retry, and — if it still fails — offer a callback rather than leaving the caller with silence or a dead end.

Three tools connect the LLM to the backend: `lookup_patient_by_phone`, `register_patient`, and `update_patient`, each mapped to one of the `/vapi/*` adapter endpoints described above.

## Setup Instructions

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

Visit `http://127.0.0.1:8000/docs` for interactive API testing.

### Deployment (Railway)

1. Connect the GitHub repo to a new Railway service.
2. Set the **Custom Start Command** (Settings → Deploy):
   ```
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
3. Add the `DATABASE_URL` environment variable pointing to a hosted Postgres instance (e.g. Neon).
4. Generate a public domain under Settings → Networking.

### Vapi configuration

1. Provision a phone number in the Vapi dashboard.
2. Create three tools (`lookup_patient_by_phone`, `register_patient`, `update_patient`), each a POST request to the corresponding `/vapi/*` endpoint above.
3. Create an assistant with the system prompt described in this README, attach all three tools to it.
4. Attach the assistant to the phone number under the number's inbound assistant setting.

## Known Limitations & Trade-offs

- **No persistent volume on Railway's free tier** was the reason for switching from the originally planned SQLite to hosted Postgres (Neon) partway through development — documented here as the trade-off it was, rather than silently working around it.
- **Vapi's LLM occasionally emits phone numbers as JSON numbers rather than strings** in tool-call arguments, despite the tool schema declaring them as strings. This caused a Postgres type-mismatch error (`character varying = bigint`) on first integration. Fixed with defensive `str()` coercion at the API boundary rather than relying solely on the LLM to respect the declared schema type — a reminder that client-declared schemas aren't guaranteed at runtime.
- **Update-by-phone-number, not by UUID:** the `update_patient` tool identifies the record to update using the caller's phone number rather than requiring the agent to track and pass back a UUID across the conversation. This is simpler and more robust for an LLM to use correctly, at the cost of not supporting updates to the phone number field itself in the same call (a caller who wants to change their phone number would need a short follow-up flow not currently implemented).
- **No automated test suite** was built given the 3-hour time budget; manual testing was done via Swagger UI and live test calls.
- **Retry logic in the voice agent** is prompt-driven (the LLM decides to retry and eventually offer a callback) rather than governed by explicit backend retry/backoff logic — sufficient for this assessment's scope but a lighter guarantee than a production system would want.
- **Bonus features not attempted:** appointment scheduling, multi-language support, call transcript storage linked to patient records, and a dashboard UI were not built, in favor of hardening the core registration/update/duplicate-detection flow within the time limit.

## Next Steps

With more time, the following would be prioritized:
- Automated integration tests for the `/patients` and `/vapi/*` endpoints
- A lightweight dashboard UI listing registered patients
- Support for updating a caller's phone number itself (currently used as the lookup key)
- Structured call transcript logging linked to `patient_id` for audit purposes
- Multi-language support triggered by caller language detection