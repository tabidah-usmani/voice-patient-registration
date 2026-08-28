import uuid
from datetime import datetime
from sqlalchemy import Column, String, Date, DateTime
from app.database import Base

class Patient(Base):
    __tablename__ = "patients"

    patient_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    date_of_birth = Column(Date, nullable=False)
    sex = Column(String, nullable=False)  # Male, Female, Other, Decline to Answer
    phone_number = Column(String(10), nullable=False, index=True)
    email = Column(String, nullable=True)
    address_line_1 = Column(String, nullable=False)
    address_line_2 = Column(String, nullable=True)
    city = Column(String(100), nullable=False)
    state = Column(String(2), nullable=False)
    zip_code = Column(String(10), nullable=False)
    insurance_provider = Column(String, nullable=True)
    insurance_member_id = Column(String, nullable=True)
    preferred_language = Column(String, default="English")
    emergency_contact_name = Column(String, nullable=True)
    emergency_contact_phone = Column(String(10), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)