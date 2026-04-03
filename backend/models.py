"""
DocVerify AI — Pydantic Models
Shared request/response models for all backend API routers.
"""

from typing import Optional, List
from pydantic import BaseModel


# ─── College Verification Models ──────────────────────────────────────────────

class StudentLookupRequest(BaseModel):
    """Request body for student verification."""
    full_name: Optional[str] = None
    prn: Optional[str] = None
    enrollment_no: Optional[str] = None
    roll_number: Optional[str] = None
    certificate_number: Optional[str] = None
    college_name: Optional[str] = None
    university_name: Optional[str] = None
    degree: Optional[str] = None
    branch: Optional[str] = None
    passing_year: Optional[str] = None
    admission_year: Optional[str] = None
    date_of_birth: Optional[str] = None


class StudentRecord(BaseModel):
    """Matched student record from the database."""
    student_id: str
    prn: str
    enrollment_no: str
    full_name: str
    date_of_birth: str
    gender: str
    degree: str
    branch: str
    specialization: Optional[str] = None
    admission_year: int
    passing_year: int
    cgpa: float
    grade: str
    certificate_number: str
    roll_number: str
    status: str
    college_name: str
    university: str


class VerificationResult(BaseModel):
    """Response body for student verification."""
    found: bool
    status: str                          # VALID / INVALID / PARTIAL_MATCH / NOT_FOUND
    confidence: float
    matched_fields: List[str]
    mismatched_fields: List[str]
    unverified_fields: List[str]
    record: Optional[StudentRecord] = None
    message: str


class CollegeInfo(BaseModel):
    """College information summary."""
    college_id: str
    name: str
    university: str
    accreditation: str
    established: int
    location: str
    degree_types: List[str]
    departments: List[str]


class APIResponse(BaseModel):
    """Generic API response wrapper."""
    status: str
    message: str
    data: Optional[dict] = None


# ─── Government ID Models ────────────────────────────────────────────────────

class AadhaarVerifyRequest(BaseModel):
    aadhaar_number: str
    full_name: Optional[str] = None


class PANVerifyRequest(BaseModel):
    pan_number: str
    full_name: Optional[str] = None


class PassportVerifyRequest(BaseModel):
    passport_number: str
    full_name: Optional[str] = None


class GovernmentVerificationResult(BaseModel):
    found: bool
    status: str
    confidence: float
    message: str
    matched_fields: List[str] = []
    expiry_date: Optional[str] = None
