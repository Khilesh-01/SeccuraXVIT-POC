"""
Smart API Router
================
Uses Gemini to intelligently decide:
1. Which external API to call for a given document type
2. Which specific extracted fields are "verifiable" (i.e., worth checking against a DB)
3. Which fields are purely structural (format/logic checks only — KYC rules)

This separates concerns:
- API-verifiable fields: name, PRN, cert number, passing year → call external API
- Rule-verifiable fields: date formats, ID patterns, expiry → KYC rule engine
- Non-verifiable fields: seals, signatures, watermarks → forgery agent only
"""

import json
import re
import os
from typing import Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from utils.api_clients.registry import get_all_supported_document_types, get_client_for_document
from utils.api_clients.base import APICallResult, APICallStatus
from utils.logger import make_log

ROUTER_SYSTEM = """You are an AI API routing agent for a document verification system.

Given:
1. A document type (e.g., "Degree Certificate", "Aadhaar Card", "PAN Card")
2. A list of extracted fields from the document
3. A list of available external verification APIs

Your job is to decide:
A) Which API should be called to verify this document (or "none" if no API is applicable)
B) Which extracted fields should be sent to that API for DB verification (the "key" fields that prove originality)
C) Which fields should only be checked by KYC rules (format/logic checks, not DB lookup)
D) Which fields cannot be verified by any means (decorative, seal descriptions, etc.)

GUIDELINES for which fields to verify via API:
- For COLLEGE/ACADEMIC documents: name, PRN, enrollment number, certificate number, passing year, degree, branch, college name
- For AADHAAR: aadhaar_number, full_name, date_of_birth (NEVER send address to external API)
- For PAN: pan_number, full_name
- For PASSPORT: passport_number, full_name, date_of_birth, expiry_date
- For DRIVING LICENSE: license_number, full_name, date_of_birth
- NEVER send sensitive fields like biometric data, partial numbers, or free-text descriptions

The "api_verifiable_fields" should be the MINIMAL set that proves the document is genuine.
Too many fields = unnecessary data exposure. Too few = weak verification.

Return ONLY valid JSON:
{
  "recommended_api": "college_db" | "aadhaar" | "pan" | "passport" | "driving_license" | "none",
  "api_display_name": "Human readable API name",
  "confidence_in_routing": 0.0-1.0,
  "routing_reason": "Why this API was chosen",
  "api_verifiable_fields": ["field1", "field2"],
  "rule_only_fields": ["field3", "field4"],
  "non_verifiable_fields": ["field5"],
  "privacy_excluded_fields": ["fields", "excluded", "for", "privacy"]
}"""


def route_to_api(
    document_type: str,
    extracted_fields: dict[str, str],
    logs: list,
) -> tuple[Optional[APICallResult], dict[str, dict]]:
    """
    Main entry point for API routing.
    
    Returns:
        - api_result: APICallResult or None (if no API applicable)
        - field_routing: {field_name: {category, api_name}}
    """
    logs.append(make_log("APIRouter", "ROUTING_START",
                          f"Routing document type '{document_type}' to appropriate verification API"))

    # ── Step 1: Ask Gemini which API to call ──────────────────────────────────
    supported_apis = get_all_supported_document_types()
    api_list_str = "\n".join([f"  - {dt} → {api}" for dt, api in list(supported_apis.items())[:20]])

    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
        )
        fields_preview = {k: v[:50] + "..." if len(str(v)) > 50 else v
                          for k, v in extracted_fields.items() if v}

        prompt = f"""{ROUTER_SYSTEM}

Document Type: {document_type}

Extracted Fields:
{json.dumps(fields_preview, indent=2)}

Available Verification APIs:
{api_list_str}

Decide the routing for this document."""

        response = llm.invoke([HumanMessage(content=prompt)])
        raw = response.content.strip()
        raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        routing = json.loads(raw)

    except Exception as e:
        logs.append(make_log("APIRouter", "ROUTING_ERROR",
                              f"LLM routing failed: {e}. Falling back to direct registry lookup.", "WARNING"))
        routing = {
            "recommended_api": "auto",
            "api_display_name": "Auto-detected",
            "confidence_in_routing": 0.5,
            "routing_reason": "Fallback: LLM routing unavailable",
            "api_verifiable_fields": list(extracted_fields.keys()),
            "rule_only_fields": [],
            "non_verifiable_fields": [],
            "privacy_excluded_fields": [],
        }

    recommended_api = routing.get("recommended_api", "none")
    api_verifiable = routing.get("api_verifiable_fields", [])
    routing_reason = routing.get("routing_reason", "")
    display_name = routing.get("api_display_name", recommended_api)

    logs.append(make_log("APIRouter", "ROUTING_DECISION",
                          f"Routed to: '{display_name}' — {routing_reason} "
                          f"(confidence: {routing.get('confidence_in_routing', 0):.0%})"))
    logs.append(make_log("APIRouter", "FIELDS_TO_VERIFY",
                          f"Fields for API verification: {api_verifiable}. "
                          f"Rule-only: {routing.get('rule_only_fields', [])}. "
                          f"Privacy-excluded: {routing.get('privacy_excluded_fields', [])}"))

    # ── Step 2: Find and call the appropriate client ──────────────────────────
    if recommended_api == "none":
        logs.append(make_log("APIRouter", "NO_API",
                              "No applicable external API for this document type — using rule-only KYC checks",
                              "WARNING"))
        return None, routing

    # Find client from registry
    client = get_client_for_document(document_type)
    if not client and recommended_api != "auto":
        # Try matching by recommended_api key
        for c in __import__("utils.api_clients.registry", fromlist=["get_all_clients"]).get_all_clients():
            if recommended_api.lower() in c.api_name.lower():
                client = c
                break

    if not client:
        logs.append(make_log("APIRouter", "CLIENT_NOT_FOUND",
                              f"No registered client for '{recommended_api}' — treating as unverifiable",
                              "WARNING"))
        return None, routing

    # Filter fields to only API-verifiable ones (privacy + scope)
    verifiable_subset = {k: v for k, v in extracted_fields.items()
                         if k in api_verifiable or any(
                             k.lower() in f.lower() or f.lower() in k.lower()
                             for f in api_verifiable
                         )}

    if not verifiable_subset:
        verifiable_subset = extracted_fields  # fallback: send all

    logs.append(make_log("APIRouter", "API_CALL",
                          f"Calling '{client.api_name}' with {len(verifiable_subset)} field(s): {list(verifiable_subset.keys())}"))

    # ── Step 3: Make the API call ─────────────────────────────────────────────
    api_result = client.verify(verifiable_subset)

    # ── Step 4: Log the result ────────────────────────────────────────────────
    status = api_result.status
    if status == APICallStatus.SUCCESS:
        logs.append(make_log("APIRouter", "API_RESULT",
                              f"✓ {client.api_name}: VERIFIED — {api_result.message} "
                              f"(confidence: {api_result.confidence:.0%}, matched: {api_result.matched_fields})",
                              "SUCCESS"))
    elif status == APICallStatus.NOT_FOUND:
        logs.append(make_log("APIRouter", "API_RESULT",
                              f"✗ {client.api_name}: NOT FOUND IN DB — {api_result.message} "
                              f"→ Certificate may be FRAUDULENT or issued by unregistered institution",
                              "WARNING"))
    elif status == APICallStatus.INVALID:
        logs.append(make_log("APIRouter", "API_RESULT",
                              f"✗ {client.api_name}: DATA MISMATCH — {api_result.message} "
                              f"Mismatched: {api_result.mismatched_fields}",
                              "WARNING"))
    elif status == APICallStatus.PARTIAL_MATCH:
        logs.append(make_log("APIRouter", "API_RESULT",
                              f"⚠ {client.api_name}: PARTIAL MATCH — {api_result.message} "
                              f"Matched: {api_result.matched_fields}, Mismatched: {api_result.mismatched_fields}",
                              "WARNING"))
    elif status == APICallStatus.UNREACHABLE:
        logs.append(make_log("APIRouter", "API_UNREACHABLE",
                              f"⚠ {client.api_name}: UNREACHABLE — {api_result.message} "
                              f"→ Fields marked UNVERIFIABLE (amber) — human review required",
                              "WARNING"))

    return api_result, routing
