"""
KYC Agent — Two-phase validation:
Phase 1: External API verification (DB lookup via API Router)
Phase 2: Rule-based KYC checks (format, expiry, pattern validation)
"""

import json
import re
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from agents.state import VerificationState, FieldResult
from utils.logger import make_log
from utils.api_router import route_to_api
from utils.api_clients.base import APICallStatus

RULE_KYC_SYSTEM = """You are a KYC compliance rule engine.
Validate document fields against format and logic rules ONLY — no DB/API calls.

Rules:
- Name: letters/spaces/dots/hyphens only, 2+ words, 2-100 chars
- Dates: valid calendar dates; DOB person 0-120 yrs; Issue date in past; flag expired expiry dates
- Aadhaar: 12 digits (spaces OK); PAN: XXXXX0000X; Passport(India): 1 letter+7 digits
- PRN: 10 digits; Certificate numbers: alphanumeric with /-, 8-30 chars
- Address: 20+ chars, contains locality/city hint
- Issuing authority: not blank

Return ONLY valid JSON, no markdown:
{
  "field_name": {
    "status": "valid" | "invalid" | "unverifiable",
    "confidence": 0.0-1.0,
    "reason": "Specific finding",
    "rule_applied": "Which rule was checked"
  }
}"""


def _api_status_to_field_status(api_status: APICallStatus) -> str:
    return {
        APICallStatus.SUCCESS: "verified",
        APICallStatus.NOT_FOUND: "invalid",
        APICallStatus.INVALID: "invalid",
        APICallStatus.PARTIAL_MATCH: "unverifiable",
        APICallStatus.UNREACHABLE: "unverifiable",
        APICallStatus.NOT_APPLICABLE: "unverifiable",
    }.get(api_status, "unverifiable")


def _api_status_to_reason(api_status: APICallStatus, message: str, api_name: str) -> str:
    prefixes = {
        APICallStatus.SUCCESS: f"Verified in {api_name}",
        APICallStatus.NOT_FOUND: f"NOT FOUND in {api_name} — record does not exist in DB",
        APICallStatus.INVALID: f"MISMATCH in {api_name} — data does not match database records",
        APICallStatus.PARTIAL_MATCH: f"Partial match in {api_name} — some fields match, needs review",
        APICallStatus.UNREACHABLE: f"{api_name} unreachable — cannot verify (API down or network error)",
        APICallStatus.NOT_APPLICABLE: "No applicable API for this field",
    }
    base = prefixes.get(api_status, "Unknown status")
    return f"{base}. {message}" if message else base


def kyc_agent(state: VerificationState) -> dict:
    """Two-phase KYC validation: API DB lookup + rule-based format checks."""
    logs = [make_log("KYCAgent", "STARTED", "Beginning two-phase KYC validation (API + Rules)")]

    if state.get("error"):
        logs.append(make_log("KYCAgent", "SKIPPED", "Skipping due to prior error", "WARNING"))
        return {"kyc_results": {}, "logs": logs}

    extracted = state.get("extracted_fields", {})
    if not extracted:
        logs.append(make_log("KYCAgent", "NO_FIELDS", "No fields to validate", "WARNING"))
        return {"kyc_results": {}, "logs": logs}

    document_type = state.get("document_type", "Unknown")
    kyc_results: dict[str, FieldResult] = {}

    # ── PHASE 1: External API Verification ───────────────────────────────────
    logs.append(make_log("KYCAgent", "PHASE1_START",
                          f"Phase 1: External API verification for document type: '{document_type}'"))

    api_result, routing_info = route_to_api(document_type, extracted, logs)

    api_verified_fields = set()
    api_field_statuses = {}

    if api_result is not None:
        overall_status = _api_status_to_field_status(api_result.status)
        overall_reason = _api_status_to_reason(api_result.status, api_result.message, api_result.api_name)

        # Fields explicitly matched by API
        for field in api_result.matched_fields:
            clean_field = field.replace("_partial", "")
            api_field_statuses[clean_field] = {
                "status": "verified",
                "reason": f"Field matched in {api_result.api_name} (confidence: {api_result.confidence:.0%})",
                "confidence": api_result.confidence,
            }
            api_verified_fields.add(clean_field)
            logs.append(make_log("KYCAgent", "API_FIELD_VERIFIED",
                                  f"'{clean_field}' VERIFIED by {api_result.api_name}", "SUCCESS"))

        # Fields that mismatched in API
        for field in api_result.mismatched_fields:
            api_field_statuses[field] = {
                "status": "invalid",
                "reason": f"Field MISMATCH in {api_result.api_name}: does not match database record",
                "confidence": api_result.confidence,
            }
            api_verified_fields.add(field)
            logs.append(make_log("KYCAgent", "API_FIELD_MISMATCH",
                                  f"'{field}' INVALID — mismatch in {api_result.api_name}", "WARNING"))

        # Fields sent to API but not explicitly matched/mismatched (e.g. NOT_FOUND scenario)
        api_verifiable_fields = routing_info.get("api_verifiable_fields", [])
        for field in api_verifiable_fields:
            if field not in api_field_statuses:
                api_field_statuses[field] = {
                    "status": overall_status,
                    "reason": overall_reason,
                    "confidence": api_result.confidence,
                }
                api_verified_fields.add(field)
                level = "SUCCESS" if overall_status == "verified" else "WARNING"
                logs.append(make_log("KYCAgent", f"API_FIELD_{overall_status.upper()}",
                                      f"'{field}' → {overall_status.upper()} via API: {overall_reason[:80]}", level))

        for field, fstatus in api_field_statuses.items():
            kyc_results[field] = FieldResult(
                value=extracted.get(field, ""),
                status=fstatus["status"],
                reason=fstatus["reason"],
                agent=f"KYCAgent[{api_result.api_name}]",
                confidence=fstatus["confidence"],
            )
    else:
        logs.append(make_log("KYCAgent", "PHASE1_SKIP",
                              "No external API applicable — proceeding to rule-based checks only", "WARNING"))

    # ── PHASE 2: Rule-Based KYC Checks ───────────────────────────────────────
    rule_fields = {k: v for k, v in extracted.items()
                   if k not in api_verified_fields and v and v.strip()}

    if rule_fields:
        logs.append(make_log("KYCAgent", "PHASE2_START",
                              f"Phase 2: Rule-based checks on {len(rule_fields)} fields: {list(rule_fields.keys())}"))
        try:
            llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
            from datetime import date
            today = date.today().isoformat()

            prompt = f"""{RULE_KYC_SYSTEM}

Today's date: {today}
Document type: {document_type}

Fields to validate (format/rule checks only):
{json.dumps(rule_fields, indent=2)}

Validate each field."""

            logs.append(make_log("KYCAgent", "PHASE2_LLM_CALL",
                                  f"Running rule checks via Gemini 2.5 on {len(rule_fields)} fields"))
            response = llm.invoke([HumanMessage(content=prompt)])
            raw = response.content.strip()
            raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
            rule_validation = json.loads(raw)

            for field, data in rule_validation.items():
                status = data.get("status", "unverifiable")
                if status == "valid":
                    status = "verified"
                reason = data.get("reason", "")
                rule = data.get("rule_applied", "")
                confidence = float(data.get("confidence", 0.5))

                kyc_results[field] = FieldResult(
                    value=extracted.get(field, ""),
                    status=status,
                    reason=f"{reason} [Rule: {rule}]" if rule else reason,
                    agent="KYCAgent[RuleEngine]",
                    confidence=confidence,
                )
                level = {"verified": "SUCCESS", "invalid": "WARNING", "unverifiable": "WARNING"}.get(status, "INFO")
                icon = {"verified": "✓", "invalid": "✗", "unverifiable": "?"}.get(status, "?")
                logs.append(make_log("KYCAgent", f"RULE_{status.upper()}",
                                      f"{icon} '{field}' → {status.upper()} ({confidence:.0%}): {reason}", level))

        except json.JSONDecodeError as e:
            logs.append(make_log("KYCAgent", "PHASE2_PARSE_ERROR", f"Rule engine parse error: {e}", "ERROR"))
        except Exception as e:
            logs.append(make_log("KYCAgent", "PHASE2_ERROR", f"Rule engine error: {e}", "ERROR"))
    else:
        logs.append(make_log("KYCAgent", "PHASE2_SKIP", "All fields handled by API verification", "INFO"))

    # ── Summary ───────────────────────────────────────────────────────────────
    verified = sum(1 for f in kyc_results.values() if f.get("status") == "verified")
    invalid = sum(1 for f in kyc_results.values() if f.get("status") == "invalid")
    unverif = sum(1 for f in kyc_results.values() if f.get("status") == "unverifiable")

    summary = (
        f"KYC complete. API phase: {len(api_field_statuses)} fields. "
        f"Rule phase: {len(rule_fields)} fields. "
        f"Results — Verified: {verified}, Invalid: {invalid}, Unverifiable: {unverif}"
    )
    logs.append(make_log("KYCAgent", "VALIDATION_COMPLETE", summary,
                          "WARNING" if invalid > 0 else "SUCCESS"))

    return {"kyc_results": kyc_results, "logs": logs, "current_step": "kyc_done"}
