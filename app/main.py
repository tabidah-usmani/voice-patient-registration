import logging
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import date
from fastapi.encoders import jsonable_encoder
from pydantic import ValidationError
from fastapi import Request
from fastapi.responses import HTMLResponse
import os
from app import models, schemas, crud
from app.database import engine, get_db, Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("patient-api")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Patient Registration API")

def envelope(data=None, error=None):
    return {"data": data, "error": error}

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(status_code=422, content=envelope(error=jsonable_encoder(exc.errors())))

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(status_code=exc.status_code, content=envelope(error=exc.detail))

@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request, exc):
    return JSONResponse(status_code=500, content=envelope(error="Internal data validation error"))

@app.on_event("startup")
def seed_data():
    db = next(get_db())
    if not crud.list_patients(db):
        seed = schemas.PatientCreate(
            first_name="Jane", last_name="Doe", date_of_birth=date(1990, 5, 12),
            sex="Female", phone_number="5551234567", email="jane.doe@example.com",
            address_line_1="123 Main St", city="Austin", state="TX", zip_code="73301"
        )
        crud.create_patient(db, seed)
        logger.info("Seeded demo patient Jane Doe")

@app.get("/patients")
def get_patients(
    last_name: str = Query(None),
    date_of_birth: date = Query(None),
    phone_number: str = Query(None),
    db: Session = Depends(get_db)
):
    patients = crud.list_patients(db, last_name, date_of_birth, phone_number)
    return envelope(data=[schemas.PatientOut.model_validate(p) for p in patients])

@app.get("/patients/{patient_id}")
def get_patient(patient_id: str, db: Session = Depends(get_db)):
    patient = crud.get_patient(db, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return envelope(data=schemas.PatientOut.model_validate(patient))

@app.get("/patients/{patient_id}/calls")
def get_patient_calls(patient_id: str, db: Session = Depends(get_db)):
    calls = db.query(models.CallTranscript).filter(
        models.CallTranscript.patient_id == patient_id
    ).order_by(models.CallTranscript.created_at.desc()).all()
    return envelope(data=[
        {
            "id": c.id,
            "call_id": c.call_id,
            "summary": c.summary,
            "transcript": c.transcript,
            "created_at": c.created_at,
        } for c in calls
    ])
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    with open(dashboard_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/")
def root():
    return {
        "status": "running",
        "message": "Voice AI Patient Registration API is live.",
        "docs": "/docs",
        "endpoints": {
            "list_patients": "GET /patients",
            "get_patient": "GET /patients/{id}",
            "create_patient": "POST /patients",
            "update_patient": "PUT /patients/{id}",
            "delete_patient": "DELETE /patients/{id}"
        }
    }

@app.get("/calls")
def get_all_calls(db: Session = Depends(get_db)):
    calls = db.query(models.CallTranscript).order_by(
        models.CallTranscript.created_at.desc()
    ).limit(50).all()
    return envelope(data=[
        {
            "id": c.id,
            "phone_number": c.phone_number,
            "patient_id": c.patient_id,
            "summary": c.summary,
            "created_at": c.created_at,
        } for c in calls
    ])
@app.post("/patients", status_code=201)
def create_patient(patient: schemas.PatientCreate, db: Session = Depends(get_db)):
    existing = crud.get_patient_by_phone(db, patient.phone_number)
    if existing:
        raise HTTPException(status_code=400, detail=f"Patient with this phone already exists: {existing.patient_id}")
    created = crud.create_patient(db, patient)
    logger.info(f"Created patient: {created.patient_id} {created.first_name} {created.last_name}")
    return envelope(data=schemas.PatientOut.model_validate(created))

@app.post("/vapi/register-patient")
async def vapi_register_patient(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    tool_calls = body.get("message", {}).get("toolCalls", [])
    if not tool_calls:
        return {"results": [{"toolCallId": "unknown", "result": "No tool call found"}]}

    call = tool_calls[0]
    call_id = call.get("id")
    arguments = call.get("function", {}).get("arguments", {})

    try:
        patient_data = schemas.PatientCreate(**arguments)
    except Exception as e:
        missing_fields = [err['loc'][0] for err in e.errors()] if hasattr(e, 'errors') else []
        return {
            "results": [{
                "toolCallId": call_id,
                "result": f"The following required fields were missing from this tool call: {', '.join(missing_fields)}. Please retry this tool call and include ALL of these fields with their actual values from the conversation."
            }]
        }

    existing = crud.get_patient_by_phone(db, patient_data.phone_number)
    if existing:
        return {"results": [{"toolCallId": call_id, "result": f"A patient with this phone number is already registered ({existing.first_name} {existing.last_name}). Ask the caller if they'd like to update instead."}]}

    created = crud.create_patient(db, patient_data)
    logger.info(f"Created patient via Vapi: {created.patient_id} {created.first_name} {created.last_name}")
    return {"results": [{"toolCallId": call_id, "result": f"Successfully registered {created.first_name} {created.last_name}."}]}


@app.post("/vapi/lookup-patient")
async def vapi_lookup_patient(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    tool_calls = body.get("message", {}).get("toolCalls", [])
    if not tool_calls:
        return {"results": [{"toolCallId": "unknown", "result": "No tool call found"}]}

    call = tool_calls[0]
    call_id = call.get("id")
    arguments = call.get("function", {}).get("arguments", {})
    phone_number = arguments.get("phone_number", "")
    phone_number = str(phone_number) if phone_number else ""
    patient = crud.get_patient_by_phone(db, phone_number)
    if not patient:
        return {"results": [{"toolCallId": call_id, "result": "No existing patient found with this phone number."}]}

    return {"results": [{"toolCallId": call_id, "result": f"Existing patient found: {patient.first_name} {patient.last_name}, DOB {patient.date_of_birth}."}]}

@app.post("/vapi/update-patient")
async def vapi_update_patient(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    tool_calls = body.get("message", {}).get("toolCalls", [])
    if not tool_calls:
        return {"results": [{"toolCallId": "unknown", "result": "No tool call found"}]}

    call = tool_calls[0]
    call_id = call.get("id")
    arguments = call.get("function", {}).get("arguments", {})

    phone_number = arguments.pop("phone_number", None)
    if not phone_number:
        return {"results": [{"toolCallId": call_id, "result": "Missing phone_number to identify which record to update."}]}
    phone_number = str(phone_number)

    existing = crud.get_patient_by_phone(db, phone_number)
    if not existing:
        return {"results": [{"toolCallId": call_id, "result": "No existing patient found with this phone number to update."}]}

    try:
        update_data = schemas.PatientUpdate(**arguments)
    except Exception as e:
        return {"results": [{"toolCallId": call_id, "result": f"Validation error: {str(e)}"}]}

    updated = crud.update_patient(db, existing.patient_id, update_data)
    logger.info(f"Updated patient via Vapi: {updated.patient_id} {updated.first_name} {updated.last_name}")
    return {"results": [{"toolCallId": call_id, "result": f"Successfully updated {updated.first_name} {updated.last_name}'s record."}]}

@app.post("/vapi/call-ended")
async def vapi_call_ended(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    message = body.get("message", {})
    message_type = message.get("type")

    # Temporary: log every payload type so we can see the real shape
    logger.info(f"Vapi webhook received, type={message_type}")

    # Only process actual end-of-call reports; ignore all other event types
    if message_type != "end-of-call-report":
        return {"received": True, "ignored_type": message_type}

    # Temporary: dump the full end-of-call payload once so we can see its real structure
    logger.info(f"FULL end-of-call-report payload: {message}")

    call = message.get("call", {})
    call_id = call.get("id")
    transcript = message.get("transcript")
    summary = message.get("summary")
    customer = call.get("customer", {})
    phone_number = str(customer.get("number", "")).lstrip("+1").strip()

    if not phone_number:
        logger.warning("Call-ended webhook received with no phone number; skipping transcript save")
        return {"received": True}

    matched_patient = crud.get_patient_by_phone(db, phone_number)

    record = models.CallTranscript(
        phone_number=phone_number,
        patient_id=matched_patient.patient_id if matched_patient else None,
        transcript=transcript,
        summary=summary,
        call_id=call_id,
    )
    db.add(record)
    db.commit()

    logger.info(f"Saved call transcript for {phone_number} (patient_id={record.patient_id})")
    return {"received": True}
@app.post("/vapi/schedule-appointment")

async def vapi_schedule_appointment(request: Request):
    body = await request.json()
    tool_calls = body.get("message", {}).get("toolCalls", [])
    if not tool_calls:
        return {"results": [{"toolCallId": "unknown", "result": "No tool call found"}]}

    call = tool_calls[0]
    call_id = call.get("id")
    arguments = call.get("function", {}).get("arguments", {})
    preferred_day = arguments.get("preferred_day", "the earliest available day")

    logger.info(f"Mock appointment scheduled, preferred_day={preferred_day}")

    return {
        "results": [{
            "toolCallId": call_id,
            "result": f"You're scheduled for a first appointment on Monday at 10:00 AM (based on your preference for {preferred_day}). A confirmation will be sent to the phone number on file."
        }]
    }

@app.put("/patients/{patient_id}")
def update_patient(patient_id: str, patient: schemas.PatientUpdate, db: Session = Depends(get_db)):
    updated = crud.update_patient(db, patient_id, patient)
    if not updated:
        raise HTTPException(status_code=404, detail="Patient not found")
    logger.info(f"Updated patient: {patient_id}")
    return envelope(data=schemas.PatientOut.model_validate(updated))

@app.delete("/patients/{patient_id}")
def delete_patient(patient_id: str, db: Session = Depends(get_db)):
    deleted = crud.soft_delete_patient(db, patient_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Patient not found")
    logger.info(f"Soft-deleted patient: {patient_id}")
    return envelope(data={"patient_id": patient_id, "deleted_at": deleted.deleted_at})