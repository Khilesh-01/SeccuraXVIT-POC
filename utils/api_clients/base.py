"""
Base API Client — Abstract interface all verification API clients must implement.
Adding a new external API = subclass BaseAPIClient, implement the methods.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional
from enum import Enum


class APICallStatus(str, Enum):
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    INVALID = "invalid"
    UNREACHABLE = "unreachable"      # Amber — cannot reach API
    PARTIAL_MATCH = "partial_match"  # Some fields match, some don't
    NOT_APPLICABLE = "not_applicable"


@dataclass
class APICallResult:
    """Unified result returned by all API clients."""
    status: APICallStatus
    confidence: float                   # 0.0 – 1.0
    matched_fields: list[str]           # Fields that matched DB record
    mismatched_fields: list[str]        # Fields that didn't match
    unverified_fields: list[str]        # Fields not checked by this API
    message: str                        # Human-readable explanation
    raw_response: Optional[dict] = None # Full API response for logging
    api_name: str = ""
    endpoint_called: str = ""

    def to_field_statuses(self) -> dict[str, dict]:
        """
        Convert to per-field status dict for KYC agent consumption.
        Returns: {field_name: {status, reason, confidence}}
        """
        result = {}

        for field in self.matched_fields:
            clean = field.replace("_partial", "")
            result[clean] = {
                "status": "verified",
                "reason": f"Verified against {self.api_name}",
                "confidence": self.confidence,
            }

        for field in self.mismatched_fields:
            result[field] = {
                "status": "invalid",
                "reason": f"Field mismatch detected by {self.api_name}: {self.message}",
                "confidence": self.confidence,
            }

        for field in self.unverified_fields:
            if field not in result:
                result[field] = {
                    "status": "unverifiable",
                    "reason": f"Not checked by {self.api_name} — requires manual review",
                    "confidence": 0.5,
                }

        return result


class BaseAPIClient(ABC):
    """Abstract base for all verification API clients."""

    @property
    @abstractmethod
    def api_name(self) -> str:
        """Human-readable name of this API (e.g. 'College DB API')."""

    @property
    @abstractmethod
    def document_types(self) -> list[str]:
        """List of document types this client handles (e.g. ['degree_certificate', 'marksheet'])."""

    @abstractmethod
    def verify(self, extracted_fields: dict[str, str]) -> APICallResult:
        """
        Run verification against this API using the extracted document fields.
        
        Args:
            extracted_fields: Dict of field_name -> value from the OCR extraction agent.
        
        Returns:
            APICallResult with match status, confidence, and per-field results.
        """

    def is_applicable(self, document_type: str) -> bool:
        """Check if this client handles the given document type."""
        doc_lower = document_type.lower()
        return any(dt.lower() in doc_lower or doc_lower in dt.lower()
                   for dt in self.document_types)
