"""
API Client Registry
===================
All verification API clients are registered here.
The API Router uses this registry to find the right client for each document type.

To add a new API:
1. Create a new client file in utils/api_clients/
2. Subclass BaseAPIClient
3. Define api_name, document_types, and verify()
4. Import and add to REGISTERED_CLIENTS below

That's it. The router will automatically route matching document types to it.
"""

from utils.api_clients.base import BaseAPIClient
from utils.api_clients.college_client import CollegeAPIClient
from utils.api_clients.government_client import AadhaarAPIClient, PANAPIClient, PassportAPIClient


# ─── Register all clients here ───────────────────────────────────────────────
# Order matters: more specific clients should come first.
# The router uses the FIRST matching client it finds.

REGISTERED_CLIENTS: list[BaseAPIClient] = [
    # ── Academic / Educational ──────────────────────────────────────────────
    CollegeAPIClient(),

    # ── Government ID ────────────────────────────────────────────────────────
    AadhaarAPIClient(),
    PANAPIClient(),
    PassportAPIClient(),

    # ── Add more clients here ─────────────────────────────────────────────────
    # DrivingLicenseAPIClient(),     # utils/api_clients/driving_license_client.py
    # VoterIDAPIClient(),            # utils/api_clients/voter_id_client.py
    # EmploymentAPIClient(),         # utils/api_clients/employment_client.py
    # ProfessionalCertAPIClient(),   # utils/api_clients/professional_cert_client.py
    # CompanyRegistrationClient(),   # utils/api_clients/company_client.py
]


def get_all_clients() -> list[BaseAPIClient]:
    return REGISTERED_CLIENTS


def get_client_for_document(document_type: str) -> BaseAPIClient | None:
    """Find the best matching client for a document type."""
    for client in REGISTERED_CLIENTS:
        if client.is_applicable(document_type):
            return client
    return None


def get_all_supported_document_types() -> dict[str, str]:
    """Return a flat map of {document_type: api_name} for all registered clients."""
    result = {}
    for client in REGISTERED_CLIENTS:
        for doc_type in client.document_types:
            result[doc_type] = client.api_name
    return result
