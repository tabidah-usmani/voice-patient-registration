from sqlalchemy.orm import Session
from sqlalchemy import and_
from app import models, schemas
from datetime import datetime

def get_patient(db: Session, patient_id: str):
    return db.query(models.Patient).filter(
        models.Patient.patient_id == patient_id,
        models.Patient.deleted_at.is_(None)
    ).first()

def get_patient_by_phone(db: Session, phone_number: str):
    return db.query(models.Patient).filter(
        models.Patient.phone_number == phone_number,
        models.Patient.deleted_at.is_(None)
    ).first()

def list_patients(db: Session, last_name=None, date_of_birth=None, phone_number=None):
    query = db.query(models.Patient).filter(models.Patient.deleted_at.is_(None))
    if last_name:
        query = query.filter(models.Patient.last_name.ilike(last_name))
    if date_of_birth:
        query = query.filter(models.Patient.date_of_birth == date_of_birth)
    if phone_number:
        query = query.filter(models.Patient.phone_number == phone_number)
    return query.all()

def create_patient(db: Session, patient: schemas.PatientCreate):
    db_patient = models.Patient(**patient.model_dump())
    db.add(db_patient)
    db.commit()
    db.refresh(db_patient)
    return db_patient

def update_patient(db: Session, patient_id: str, patient: schemas.PatientUpdate):
    db_patient = get_patient(db, patient_id)
    if not db_patient:
        return None
    update_data = patient.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_patient, key, value)
    db_patient.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(db_patient)
    return db_patient

def soft_delete_patient(db: Session, patient_id: str):
    db_patient = get_patient(db, patient_id)
    if not db_patient:
        return None
    db_patient.deleted_at = datetime.utcnow()
    db.commit()
    return db_patient