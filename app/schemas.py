from pydantic import BaseModel, EmailStr, field_validator
from datetime import date, datetime
from typing import Optional
import re

US_STATES = {"AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY","DC"}

class PatientBase(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date
    sex: str
    phone_number: str
    email: Optional[EmailStr] = None
    address_line_1: str
    address_line_2: Optional[str] = None
    city: str
    state: str
    zip_code: str
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: Optional[str] = "English"
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    @field_validator("first_name", "last_name")
    @classmethod
    def name_format(cls, v):
        if not re.match(r"^[A-Za-z\-' ]{1,50}$", v):
            raise ValueError("Name must be 1-50 alphabetic characters, hyphens, or apostrophes")
        return v

    @field_validator("date_of_birth")
    @classmethod
    def dob_not_future(cls, v):
        if v > date.today():
            raise ValueError("Date of birth cannot be in the future")
        return v

    @field_validator("sex")
    @classmethod
    def sex_enum(cls, v):
        allowed = {"Male", "Female", "Other", "Decline to Answer"}
        if v not in allowed:
            raise ValueError(f"sex must be one of {allowed}")
        return v

    @field_validator("phone_number", "emergency_contact_phone")
    @classmethod
    def phone_format(cls, v):
        if v is None:
            return v
        digits = re.sub(r"\D", "", v)
        if len(digits) != 10:
            raise ValueError("Phone number must be a valid 10-digit US number")
        return digits

    @field_validator("state")
    @classmethod
    def state_valid(cls, v):
        if v.upper() not in US_STATES:
            raise ValueError("state must be a valid 2-letter US state abbreviation")
        return v.upper()

    @field_validator("zip_code")
    @classmethod
    def zip_format(cls, v):
        if not re.match(r"^\d{5}(-\d{4})?$", v):
            raise ValueError("zip_code must be 5-digit or ZIP+4 format")
        return v

class PatientCreate(PatientBase):
    pass

class PatientUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    sex: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[EmailStr] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    @field_validator("first_name", "last_name")
    @classmethod
    def name_format(cls, v):
        if v is None:
            return v
        if not re.match(r"^[A-Za-z\-' ]{1,50}$", v):
            raise ValueError("Name must be 1-50 alphabetic characters, hyphens, or apostrophes")
        return v

    @field_validator("date_of_birth")
    @classmethod
    def dob_not_future(cls, v):
        if v is not None and v > date.today():
            raise ValueError("Date of birth cannot be in the future")
        return v

    @field_validator("sex")
    @classmethod
    def sex_enum(cls, v):
        if v is None:
            return v
        allowed = {"Male", "Female", "Other", "Decline to Answer"}
        if v not in allowed:
            raise ValueError(f"sex must be one of {allowed}")
        return v

    @field_validator("phone_number", "emergency_contact_phone")
    @classmethod
    def phone_format(cls, v):
        if v is None:
            return v
        digits = re.sub(r"\D", "", v)
        if len(digits) != 10:
            raise ValueError("Phone number must be a valid 10-digit US number")
        return digits

    @field_validator("state")
    @classmethod
    def state_valid(cls, v):
        if v is None:
            return v
        if v.upper() not in US_STATES:
            raise ValueError("state must be a valid 2-letter US state abbreviation")
        return v.upper()

    @field_validator("zip_code")
    @classmethod
    def zip_format(cls, v):
        if v is None:
            return v
        if not re.match(r"^\d{5}(-\d{4})?$", v):
            raise ValueError("zip_code must be 5-digit or ZIP+4 format")
        return v

class PatientOut(PatientBase):
    patient_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True