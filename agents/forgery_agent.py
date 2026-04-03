import json
import re
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from agents.state import VerificationState, FieldResult
from utils.logger import make_log

FORGERY_SYSTEM = """You are an expert AI forensic document analyst specializing in forgery and tampering detection.

Analyze the provided document image for signs of:
1. **Digital manipulation** – pixel artifacts, unusual sharpening/blurring around text
2. **Font inconsistencies** – mixed fonts, irregular character spacing, misaligned text
3. **Copy-paste artifacts** – edges around names/numbers suggesting overlaid content
4. **Color/ink inconsistencies** – sections with different ink color or printing quality
5. **Layout irregularities** – unusual spacing, misaligned fields, broken borders
6. **Seal/stamp authenticity** – blurry, pixelated, or digitally inserted stamps/seals
7. **Signature authenticity** – signs of tracing or digital insertion
8. **Background pattern integrity** – guilloche patterns, watermarks intact

For each extracted field provided, assess whether the field area appears authentic.

You will receive the extracted fields. Assess each one.

Return ONLY a valid JSON object. No markdown, no explanation.
Format:
{
  "field_name": {
    "status": "verified" | "invalid" | "unverifiable",
    "confidence": 0.0-1.0,
    "reason": "Brief explanation of finding"
  },
  "overall_document_integrity": {
    "status": "verified" | "invalid" | "unverifiable",
    "confidence": 0.0-1.0, 
    "reason": "Overall document assessment"
  }
}

Use:
- "verified" → No signs of tampering detected
- "invalid" → Clear signs of forgery or manipulation detected  
- "unverifiable" → Cannot determine authenticity (poor image quality, unusual format, etc.)"""


def forgery_detection_agent(state: VerificationState) -> dict:
    """Run forgery detection analysis on the document."""
    logs = [make_log("ForgeryDetectionAgent", "STARTED", "Initiating forensic analysis for tampering and forgery")]

    if state.get("error"):
        logs.append(make_log("ForgeryDetectionAgent", "SKIPPED", "Skipping due to prior error", "WARNING"))
        return {"forgery_results": {}, "logs": logs}

    extracted = state.get("extracted_fields", {})
    if not extracted:
        logs.append(make_log("ForgeryDetectionAgent", "NO_FIELDS", "No extracted fields to verify", "WARNING"))
        return {"forgery_results": {}, "logs": logs}

    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
        )

        fields_list = "\n".join([f"- {k}: {v}" for k, v in extracted.items() if v])
        prompt = f"""{FORGERY_SYSTEM}

Extracted fields from this document:
{fields_list}

Analyze the document image above and assess each field for authenticity."""

        message = HumanMessage(
            content=[
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{state['document_base64']}"
                    },
                },
                {"type": "text", "text": prompt},
            ]
        )

        logs.append(make_log("ForgeryDetectionAgent", "LLM_CALL", f"Analyzing {len(extracted)} fields for signs of forgery"))
        response = llm.invoke([message])
        raw = response.content.strip()
        raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        analysis = json.loads(raw)

        forgery_results: dict[str, FieldResult] = {}
        flagged = []
        for field, data in analysis.items():
            status = data.get("status", "unverifiable")
            reason = data.get("reason", "")
            confidence = float(data.get("confidence", 0.5))

            forgery_results[field] = FieldResult(
                value=extracted.get(field, ""),
                status=status,
                reason=reason,
                agent="ForgeryDetectionAgent",
                confidence=confidence,
            )

            if status == "invalid":
                flagged.append(field)
                logs.append(make_log("ForgeryDetectionAgent", "FRAUD_FLAG",
                                     f"⚠ Potential forgery detected in '{field}': {reason}", "WARNING"))
            elif status == "unverifiable":
                logs.append(make_log("ForgeryDetectionAgent", "UNVERIFIABLE",
                                     f"Cannot verify '{field}': {reason}", "WARNING"))
            else:
                logs.append(make_log("ForgeryDetectionAgent", "FIELD_CLEAR",
                                     f"'{field}' appears authentic (confidence: {confidence:.0%})", "SUCCESS"))

        summary = f"Forgery analysis complete. {len(flagged)} field(s) flagged: {flagged}" if flagged else "Forgery analysis complete. No forgery detected."
        logs.append(make_log("ForgeryDetectionAgent", "ANALYSIS_COMPLETE", summary,
                              "WARNING" if flagged else "SUCCESS"))

        return {
            "forgery_results": forgery_results,
            "logs": logs,
            "current_step": "forgery_done",
        }

    except json.JSONDecodeError as e:
        logs.append(make_log("ForgeryDetectionAgent", "PARSE_ERROR", f"Failed to parse response: {e}", "ERROR"))
        return {"forgery_results": {}, "logs": logs, "error": str(e)}
    except Exception as e:
        logs.append(make_log("ForgeryDetectionAgent", "ERROR", str(e), "ERROR"))
        return {"forgery_results": {}, "logs": logs, "error": str(e)}
