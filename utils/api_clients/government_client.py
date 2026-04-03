"""
Government ID Verification API Client
Calls the DocVerify backend /api/government/* endpoints.
Handles Aadhaar, PAN, and Passport documents.
"""

import os
import re
import requests
from utils.api_clients.base import BaseAPIClient, APICallResult, APICallStatus

BACKEND_BASE_URL = os.environ.get("DOCVERIFY_BACKEND_URL", "http://localhost:8000")


# ─── Field alias maps ────────────────────────────────────────────────────────

AADHAAR_FIELD_MAP = {
    "aadhaar": "aadhaar_number",
    "aadhaar_no": "aadhaar_number",
    "uid": "aadhaar_number",
    "uid_number": "aadhaar_number",
    "unique_identification_number": "aadhaar_number",
    "name": "full_name",
    "holder_name": "full_name",
    "card_holder": "full_name",
    "student_name": "full_name",
    "candidate_name": "full_name",
}

PAN_FIELD_MAP = {
    "pan": "pan_number",
    "pan_no": "pan_number",
    "permanent_account_number": "pan_number",
    "name": "full_name",
    "holder_name": "full_name",
    "card_holder": "full_name",
}

PASSPORT_FIELD_MAP = {
    "passport": "passport_number",
    "passport_no": "passport_number",
    "travel_document_number": "passport_number",
    "name": "full_name",
    "holder_name": "full_name",
    "given_name": "full_name",
    "surname": "full_name",
}


def _normalize_fields(extracted: dict, alias_map: dict) -> dict:
    """Apply alias map to normalize field names."""
    normalized = {}
    for raw_key, value in extracted.items():
        if not value or not str(value).strip():
            continue
        key = raw_key.lower().strip().replace(" ", "_")
        mapped_key = alias_map.get(key, key)
        normalized[mapped_key] = str(value).strip()
    return normalized


def _safe_post(endpoint: str, payload: dict, api_name: str) -> APICallResult:
    """Make a POST request with standard error handling."""
    try:
        response = requests.post(endpoint, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()

        api_status = data.get("status", "NOT_FOUND")
        confidence = float(data.get("confidence", 0.0))
        matched = data.get("matched_fields", [])
        message = data.get("message", "")

        if api_status == "VALID":
            call_status = APICallStatus.SUCCESS
        elif api_status == "INVALID":
            call_status = APICallStatus.INVALID
        else:
            call_status = APICallStatus.NOT_FOUND

        return APICallResult(
            status=call_status,
            confidence=confidence,
            matched_fields=matched,
            mismatched_fields=[],
            unverified_fields=[],
            message=message,
            raw_response=data,
            api_name=api_name,
            endpoint_called=endpoint,
        )
    except requests.exceptions.ConnectionError:
        return APICallResult(
            status=APICallStatus.UNREACHABLE,
            confidence=0.0,
            matched_fields=[], mismatched_fields=[], unverified_fields=list(payload.keys()),
            message=f"Cannot reach Government API at {BACKEND_BASE_URL}. Is the backend running?",
            api_name=api_name, endpoint_called=endpoint,
        )
    except Exception as e:
        return APICallResult(
            status=APICallStatus.UNREACHABLE,
            confidence=0.0,
            matched_fields=[], mismatched_fields=[], unverified_fields=list(payload.keys()),
            message=f"Government API error: {e}",
            api_name=api_name, endpoint_called=endpoint,
        )


# ─── Aadhaar Client ──────────────────────────────────────────────────────────

class AadhaarAPIClient(BaseAPIClient):
    """Calls backend /api/government/verify-aadhaar."""

    @property
    def api_name(self) -> str:
        return "Aadhaar Verification API"

    @property
    def document_types(self) -> list[str]:
        return ["aadhaar", "aadhaar card", "aadhaar_card", "uid card", "unique identification"]

    def verify(self, extracted_fields: dict[str, str]) -> APICallResult:
        mapped = _normalize_fields(extracted_fields, AADHAAR_FIELD_MAP)
        aadhaar_num = mapped.get("aadhaar_number")
        if not aadhaar_num:
            return APICallResult(
                status=APICallStatus.NOT_APPLICABLE, confidence=0.0,
                matched_fields=[], mismatched_fields=[], unverified_fields=list(extracted_fields.keys()),
                message="No Aadhaar number found in extracted data.",
                api_name=self.api_name, endpoint_called="N/A",
            )
        payload = {"aadhaar_number": aadhaar_num}
        if "full_name" in mapped:
            payload["full_name"] = mapped["full_name"]
        return _safe_post(f"{BACKEND_BASE_URL}/api/government/verify-aadhaar", payload, self.api_name)


# ─── PAN Client ──────────────────────────────────────────────────────────────

class PANAPIClient(BaseAPIClient):
    """Calls backend /api/government/verify-pan."""

    @property
    def api_name(self) -> str:
        return "PAN Verification API"

    @property
    def document_types(self) -> list[str]:
        return ["pan", "pan card", "pan_card", "permanent account number"]

    def verify(self, extracted_fields: dict[str, str]) -> APICallResult:
        mapped = _normalize_fields(extracted_fields, PAN_FIELD_MAP)
        pan_num = mapped.get("pan_number")
        if not pan_num:
            return APICallResult(
                status=APICallStatus.NOT_APPLICABLE, confidence=0.0,
                matched_fields=[], mismatched_fields=[], unverified_fields=list(extracted_fields.keys()),
                message="No PAN number found in extracted data.",
                api_name=self.api_name, endpoint_called="N/A",
            )
        payload = {"pan_number": pan_num}
        if "full_name" in mapped:
            payload["full_name"] = mapped["full_name"]
        return _safe_post(f"{BACKEND_BASE_URL}/api/government/verify-pan", payload, self.api_name)


# ─── Passport Client ─────────────────────────────────────────────────────────

class PassportAPIClient(BaseAPIClient):
    """Calls backend /api/government/verify-passport."""

    @property
    def api_name(self) -> str:
        return "Passport Verification API"

    @property
    def document_types(self) -> list[str]:
        return ["passport", "travel document", "passport_card"]

    def verify(self, extracted_fields: dict[str, str]) -> APICallResult:
        mapped = _normalize_fields(extracted_fields, PASSPORT_FIELD_MAP)
        passport_num = mapped.get("passport_number")
        if not passport_num:
            return APICallResult(
                status=APICallStatus.NOT_APPLICABLE, confidence=0.0,
                matched_fields=[], mismatched_fields=[], unverified_fields=list(extracted_fields.keys()),
                message="No passport number found in extracted data.",
                api_name=self.api_name, endpoint_called="N/A",
            )
        payload = {"passport_number": passport_num}
        if "full_name" in mapped:
            payload["full_name"] = mapped["full_name"]
        return _safe_post(f"{BACKEND_BASE_URL}/api/government/verify-passport", payload, self.api_name)
