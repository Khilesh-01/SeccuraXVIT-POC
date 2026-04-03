"""
Government ID Verification API Router (Placeholder)
Provides dummy verification endpoints for Aadhaar, PAN, and Passport.
"""

import re
from fastapi import APIRouter
from backend.models import (
    AadhaarVerifyRequest, PANVerifyRequest, PassportVerifyRequest,
    GovernmentVerificationResult
)

router = APIRouter(prefix="/api/government", tags=["Government ID Verification"])


# ─── Helpers ──────────────────────────────────────────────────────────────────

def is_valid_aadhaar_format(number: str) -> bool:
    """Check basic Aadhaar format: 12 digits (may have spaces)."""
    digits = re.sub(r"\s", "", number)
    return bool(re.match(r"^\d{12}$", digits))


def is_valid_pan_format(number: str) -> bool:
    """Check PAN format: ABCPS1234P (5 letters, 4 digits, 1 letter)."""
    return bool(re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", number.upper().strip()))


def is_valid_passport_format(number: str) -> bool:
    """Check Indian passport format: 1 letter + 7 digits."""
    return bool(re.match(r"^[A-Z]\d{7}$", number.upper().strip()))


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/verify-aadhaar", response_model=GovernmentVerificationResult)
def verify_aadhaar(req: AadhaarVerifyRequest):
    """
    Placeholder Aadhaar verification.
    Returns VALID if format is correct (dummy — no real UIDAI check).
    """
    if not is_valid_aadhaar_format(req.aadhaar_number):
        return GovernmentVerificationResult(
            found=False, status="INVALID", confidence=0.0,
            message="Invalid Aadhaar number format. Expected 12 digits.",
        )
    return GovernmentVerificationResult(
        found=True, status="VALID", confidence=0.85,
        matched_fields=["aadhaar_number"] + (["full_name"] if req.full_name else []),
        message="Aadhaar format valid (dummy verification — no live UIDAI check).",
    )


@router.post("/verify-pan", response_model=GovernmentVerificationResult)
def verify_pan(req: PANVerifyRequest):
    """
    Placeholder PAN verification.
    Returns VALID if format is correct.
    """
    if not is_valid_pan_format(req.pan_number):
        return GovernmentVerificationResult(
            found=False, status="INVALID", confidence=0.0,
            message="Invalid PAN format. Expected: ABCPS1234P.",
        )
    return GovernmentVerificationResult(
        found=True, status="VALID", confidence=0.80,
        matched_fields=["pan_number"] + (["full_name"] if req.full_name else []),
        message="PAN format valid (dummy verification — no live ITD check).",
    )


@router.post("/verify-passport", response_model=GovernmentVerificationResult)
def verify_passport(req: PassportVerifyRequest):
    """
    Placeholder passport verification.
    Returns VALID with a dummy expiry date if format is correct.
    """
    if not is_valid_passport_format(req.passport_number):
        return GovernmentVerificationResult(
            found=False, status="INVALID", confidence=0.0,
            message="Invalid passport number format. Expected: A1234567.",
        )
    return GovernmentVerificationResult(
        found=True, status="VALID", confidence=0.80,
        matched_fields=["passport_number"] + (["full_name"] if req.full_name else []),
        expiry_date="2030-12-31",
        message="Passport format valid (dummy verification — no live MEA check).",
    )


@router.get("/health")
def government_api_health():
    return {
        "status": "healthy",
        "api": "Government ID Verification API",
        "note": "Placeholder — format validation only",
    }
