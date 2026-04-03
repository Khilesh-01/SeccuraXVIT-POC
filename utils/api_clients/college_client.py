"""
College Verification API Client
Calls the DocVerify backend /api/college/verify-student endpoint.
Handles college certificate, degree, marksheet, and academic documents.
"""

import os
import re
import requests
from utils.api_clients.base import BaseAPIClient, APICallResult, APICallStatus

BACKEND_BASE_URL = os.environ.get("DOCVERIFY_BACKEND_URL", "http://localhost:8000")


# Fields on a college certificate that we send to the API for verification
# These are the fields that MATTER for originality — not all fields need DB check
COLLEGE_VERIFIABLE_FIELDS = [
    "full_name",
    "student_name",
    "name",
    "prn",
    "prn_number",
    "enrollment_number",
    "enrollment_no",
    "roll_number",
    "certificate_number",
    "date_of_birth",
    "dob",
    "passing_year",
    "year_of_passing",
    "admission_year",
    "year_of_admission",
    "degree",
    "programme",
    "course",
    "branch",
    "department",
    "specialization",
    "college_name",
    "institution",
    "university",
]

# Field name normalization map: extracted key → API request key
FIELD_ALIAS_MAP = {
    "student_name": "full_name",
    "name": "full_name",
    "candidate_name": "full_name",
    "prn_number": "prn",
    "permanent_registration_number": "prn",
    "dob": "date_of_birth",
    "birth_date": "date_of_birth",
    "year_of_passing": "passing_year",
    "passing_out_year": "passing_year",
    "year_of_graduation": "passing_year",
    "graduation_year": "passing_year",
    "year_of_admission": "admission_year",
    "programme": "degree",
    "course": "degree",
    "qualification": "degree",
    "department": "branch",
    "specialization": "branch",
    "stream": "branch",
    "institution": "college_name",
    "college": "college_name",
    "university": "college_name",
    "issued_by": "college_name",
    "enrollment_number": "enrollment_no",
    "enrollment": "enrollment_no",
}


class CollegeAPIClient(BaseAPIClient):
    """Calls backend /api/college/verify-student to validate academic certificates."""

    @property
    def api_name(self) -> str:
        return "College Verification DB API"

    @property
    def document_types(self) -> list[str]:
        return [
            "degree certificate",
            "degree_certificate",
            "graduation certificate",
            "academic certificate",
            "provisional certificate",
            "marksheet",
            "transcript",
            "convocation certificate",
            "college certificate",
            "university certificate",
            "b.e. certificate",
            "b.tech certificate",
            "m.tech certificate",
            "mba certificate",
            "diploma certificate",
            "engineering certificate",
        ]

    def _normalize_extracted_fields(self, extracted: dict[str, str]) -> dict:
        """
        Map raw extracted field names to the college API's expected field names.
        Returns a clean dict ready to send as a StudentLookupRequest.
        """
        normalized = {}
        for raw_key, value in extracted.items():
            if not value or not value.strip():
                continue
            key = raw_key.lower().strip().replace(" ", "_")
            # Apply alias map
            mapped_key = FIELD_ALIAS_MAP.get(key, key)
            # Only include fields the college API understands
            if mapped_key in COLLEGE_VERIFIABLE_FIELDS or key in COLLEGE_VERIFIABLE_FIELDS:
                normalized[mapped_key] = value.strip()

        return normalized

    def _extract_year(self, value: str) -> str | None:
        """Extract a 4-digit year from a string like '2023', 'May 2023', etc."""
        match = re.search(r"\b(19|20)\d{2}\b", value)
        return match.group() if match else None

    def verify(self, extracted_fields: dict[str, str]) -> APICallResult:
        """Verify academic certificate fields against the College DB API."""
        mapped = self._normalize_extracted_fields(extracted_fields)

        if not mapped:
            return APICallResult(
                status=APICallStatus.NOT_APPLICABLE,
                confidence=0.0,
                matched_fields=[],
                mismatched_fields=[],
                unverified_fields=list(extracted_fields.keys()),
                message="No college-verifiable fields found in extracted data.",
                api_name=self.api_name,
                endpoint_called="N/A",
            )

        # Build request payload — map to StudentLookupRequest fields
        payload = {}
        if "full_name" in mapped:
            payload["full_name"] = mapped["full_name"]
        if "prn" in mapped:
            payload["prn"] = re.sub(r"\D", "", mapped["prn"])  # Digits only
        if "enrollment_no" in mapped:
            payload["enrollment_no"] = mapped["enrollment_no"]
        if "roll_number" in mapped:
            payload["roll_number"] = mapped["roll_number"]
        if "certificate_number" in mapped:
            payload["certificate_number"] = mapped["certificate_number"]
        if "date_of_birth" in mapped:
            payload["date_of_birth"] = mapped["date_of_birth"]
        if "passing_year" in mapped:
            yr = self._extract_year(mapped["passing_year"])
            if yr:
                payload["passing_year"] = yr
        if "admission_year" in mapped:
            yr = self._extract_year(mapped["admission_year"])
            if yr:
                payload["admission_year"] = yr
        if "degree" in mapped:
            payload["degree"] = mapped["degree"]
        if "branch" in mapped:
            payload["branch"] = mapped["branch"]
        if "college_name" in mapped:
            payload["college_name"] = mapped["college_name"]

        endpoint = f"{BACKEND_BASE_URL}/api/college/verify-student"

        try:
            response = requests.post(endpoint, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()

            api_status = data.get("status", "NOT_FOUND")
            found = data.get("found", False)
            confidence = float(data.get("confidence", 0.0))
            matched = data.get("matched_fields", [])
            mismatched = data.get("mismatched_fields", [])
            unverified = data.get("unverified_fields", [])
            message = data.get("message", "")

            if not found or api_status == "NOT_FOUND":
                call_status = APICallStatus.NOT_FOUND
            elif api_status == "VALID":
                call_status = APICallStatus.SUCCESS
            elif api_status == "PARTIAL_MATCH":
                call_status = APICallStatus.PARTIAL_MATCH
            else:
                call_status = APICallStatus.INVALID

            return APICallResult(
                status=call_status,
                confidence=confidence,
                matched_fields=matched,
                mismatched_fields=mismatched,
                unverified_fields=unverified,
                message=message,
                raw_response=data,
                api_name=self.api_name,
                endpoint_called=endpoint,
            )

        except requests.exceptions.ConnectionError:
            return APICallResult(
                status=APICallStatus.UNREACHABLE,
                confidence=0.0,
                matched_fields=[],
                mismatched_fields=[],
                unverified_fields=list(payload.keys()),
                message=f"Cannot reach College API at {BACKEND_BASE_URL}. Is the backend running?",
                api_name=self.api_name,
                endpoint_called=endpoint,
            )
        except requests.exceptions.Timeout:
            return APICallResult(
                status=APICallStatus.UNREACHABLE,
                confidence=0.0,
                matched_fields=[],
                mismatched_fields=[],
                unverified_fields=list(payload.keys()),
                message="College API request timed out.",
                api_name=self.api_name,
                endpoint_called=endpoint,
            )
        except Exception as e:
            return APICallResult(
                status=APICallStatus.UNREACHABLE,
                confidence=0.0,
                matched_fields=[],
                mismatched_fields=[],
                unverified_fields=list(payload.keys()),
                message=f"College API error: {str(e)}",
                api_name=self.api_name,
                endpoint_called=endpoint,
            )
