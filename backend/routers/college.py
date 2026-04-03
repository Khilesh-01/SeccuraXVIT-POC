"""
College Verification API Router
Handles student lookup and certificate verification for educational institutions.
"""

import json
import re
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from backend.models import (
    StudentLookupRequest, VerificationResult, StudentRecord,
    CollegeInfo, APIResponse
)

router = APIRouter(prefix="/api/college", tags=["College Verification"])

# ─── Load DB ──────────────────────────────────────────────────────────────────
DB_PATH = Path(__file__).parent.parent / "data" / "college_db.json"
with open(DB_PATH) as f:
    _DB = json.load(f)

COLLEGES: dict = _DB["colleges"]
STUDENTS: list = _DB["students"]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def normalize(s: str) -> str:
    """Lowercase, strip extra spaces, remove punctuation."""
    if not s:
        return ""
    return re.sub(r"[^a-z0-9\s]", "", s.lower()).strip()


def name_similarity(a: str, b: str) -> float:
    """Simple token-overlap similarity for name matching."""
    a_tokens = set(normalize(a).split())
    b_tokens = set(normalize(b).split())
    if not a_tokens or not b_tokens:
        return 0.0
    overlap = a_tokens & b_tokens
    return len(overlap) / max(len(a_tokens), len(b_tokens))


def resolve_college_id(college_name: str) -> Optional[str]:
    """Map a free-text college name to a college_id using alias matching."""
    norm = normalize(college_name)
    for cid, cdata in COLLEGES.items():
        if normalize(cdata["name"]) == norm:
            return cid
        for alias in cdata.get("aliases", []):
            if normalize(alias) == norm:
                return cid
        # Partial substring match
        if norm in normalize(cdata["name"]) or normalize(cdata["name"]) in norm:
            return cid
    return None


def resolve_university_id(university_name: str) -> Optional[str]:
    """Find which college belongs to a university by name."""
    norm = normalize(university_name)
    for cid, cdata in COLLEGES.items():
        if normalize(cdata["university"]) == norm:
            return cid
        for alias in cdata.get("university_aliases", []):
            if normalize(alias) == norm:
                return cid
    return None


def student_to_record(student: dict) -> StudentRecord:
    college = COLLEGES.get(student["college_id"], {})
    return StudentRecord(
        student_id=student["student_id"],
        prn=student["prn"],
        enrollment_no=student["enrollment_no"],
        full_name=student["full_name"],
        date_of_birth=student["date_of_birth"],
        gender=student["gender"],
        degree=student["degree"],
        branch=student["branch"],
        specialization=student.get("specialization"),
        admission_year=student["admission_year"],
        passing_year=student["passing_year"],
        cgpa=student["cgpa"],
        grade=student["grade"],
        certificate_number=student["certificate_number"],
        roll_number=student["roll_number"],
        status=student["status"],
        college_name=college.get("name", student["college_id"]),
        university=college.get("university", ""),
    )


def match_student(req: StudentLookupRequest) -> tuple[Optional[dict], float, list, list, list]:
    """
    Core matching logic.
    Returns: (student_dict | None, confidence, matched_fields, mismatched_fields, unverified_fields)
    """
    # Resolve college_id from college_name if provided
    target_college_id = None
    if req.college_name:
        target_college_id = resolve_college_id(req.college_name)

    candidates = list(STUDENTS)

    # Filter by college if resolved
    if target_college_id:
        college_candidates = [s for s in candidates if s["college_id"] == target_college_id]
        if college_candidates:
            candidates = college_candidates
        # else: don't filter — college might be found by student match

    best_match = None
    best_score = 0.0
    best_matched = []
    best_mismatched = []

    for student in candidates:
        matched = []
        mismatched = []
        score = 0.0
        weight_total = 0.0

        # ── PRN (highest weight — unique identifier) ──
        if req.prn:
            weight_total += 3.0
            if normalize(req.prn) == normalize(student["prn"]):
                matched.append("prn")
                score += 3.0
            else:
                mismatched.append("prn")

        # ── Certificate Number ──
        if req.certificate_number:
            weight_total += 3.0
            if normalize(req.certificate_number) == normalize(student["certificate_number"]):
                matched.append("certificate_number")
                score += 3.0
            else:
                mismatched.append("certificate_number")

        # ── Enrollment Number ──
        if req.enrollment_no:
            weight_total += 2.5
            if normalize(req.enrollment_no) == normalize(student["enrollment_no"]):
                matched.append("enrollment_no")
                score += 2.5
            else:
                mismatched.append("enrollment_no")

        # ── Roll Number ──
        if req.roll_number:
            weight_total += 2.0
            if normalize(req.roll_number) == normalize(student["roll_number"]):
                matched.append("roll_number")
                score += 2.0
            else:
                mismatched.append("roll_number")

        # ── Full Name (fuzzy) ──
        if req.full_name:
            weight_total += 2.0
            sim = name_similarity(req.full_name, student["full_name"])
            # Also check name_variations
            for variation in student.get("name_variations", []):
                sim = max(sim, name_similarity(req.full_name, variation))
            if sim >= 0.85:
                matched.append("full_name")
                score += 2.0 * sim
            elif sim >= 0.5:
                matched.append("full_name_partial")
                score += 2.0 * sim * 0.5
            else:
                mismatched.append("full_name")

        # ── Date of Birth ──
        if req.date_of_birth:
            weight_total += 1.5
            # Normalize date formats: dd/mm/yyyy, yyyy-mm-dd, dd-mm-yyyy
            dob_norm = re.sub(r"[-/.]", "", req.date_of_birth)
            student_dob = re.sub(r"[-/.]", "", student["date_of_birth"])
            # Handle different orderings: extract year, month, day
            if dob_norm == student_dob or dob_norm[::-1] == student_dob:
                matched.append("date_of_birth")
                score += 1.5
            else:
                mismatched.append("date_of_birth")

        # ── Passing Year ──
        if req.passing_year:
            weight_total += 1.5
            try:
                py = int(re.sub(r"\D", "", req.passing_year))
                if py == student["passing_year"]:
                    matched.append("passing_year")
                    score += 1.5
                else:
                    mismatched.append("passing_year")
            except Exception:
                pass

        # ── Admission Year ──
        if req.admission_year:
            weight_total += 1.0
            try:
                ay = int(re.sub(r"\D", "", req.admission_year))
                if ay == student["admission_year"]:
                    matched.append("admission_year")
                    score += 1.0
                else:
                    mismatched.append("admission_year")
            except Exception:
                pass

        # ── Degree ──
        if req.degree:
            weight_total += 1.0
            if normalize(req.degree) in normalize(student["degree"]) or normalize(student["degree"]) in normalize(req.degree):
                matched.append("degree")
                score += 1.0
            else:
                mismatched.append("degree")

        # ── Branch / Department ──
        if req.branch:
            weight_total += 1.0
            if normalize(req.branch) in normalize(student["branch"]) or normalize(student["branch"]) in normalize(req.branch):
                matched.append("branch")
                score += 1.0
            else:
                mismatched.append("branch")

        # Compute normalized confidence
        if weight_total > 0:
            confidence = score / weight_total
        else:
            confidence = 0.0

        if confidence > best_score:
            best_score = confidence
            best_match = student
            best_matched = matched
            best_mismatched = mismatched

    # Determine unverified fields (those not provided in request)
    all_possible = ["prn", "certificate_number", "enrollment_no", "roll_number",
                    "full_name", "date_of_birth", "passing_year", "admission_year",
                    "degree", "branch"]
    provided_fields = set()
    for f in all_possible:
        val = getattr(req, f, None)
        if val:
            provided_fields.add(f)
    unverified = [f for f in all_possible if f not in provided_fields]

    return best_match, best_score, best_matched, best_mismatched, unverified


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/verify-student", response_model=VerificationResult)
def verify_student(req: StudentLookupRequest):
    """
    Primary endpoint: verify a student against the college database.
    Accepts any combination of known fields — the more provided, the higher confidence.
    Returns VALID (found & matches), INVALID (found but mismatches), or NOT_FOUND.
    """
    student, confidence, matched, mismatched, unverified = match_student(req)

    if student is None or confidence < 0.3:
        return VerificationResult(
            found=False,
            status="NOT_FOUND",
            confidence=0.0,
            matched_fields=[],
            mismatched_fields=[],
            unverified_fields=unverified,
            record=None,
            message="No matching student record found in the database.",
        )

    if confidence >= 0.75 and len(mismatched) == 0:
        status = "VALID"
        msg = f"Student record verified successfully. Matched {len(matched)} field(s) with {confidence:.0%} confidence."
    elif confidence >= 0.5 and len(mismatched) <= 2:
        status = "PARTIAL_MATCH"
        msg = f"Partial match found. {len(matched)} field(s) matched, {len(mismatched)} mismatched. Manual review recommended."
    else:
        status = "INVALID"
        msg = f"Record found but critical fields mismatch: {', '.join(mismatched)}. Possible fraudulent certificate."

    return VerificationResult(
        found=True,
        status=status,
        confidence=round(confidence, 3),
        matched_fields=matched,
        mismatched_fields=mismatched,
        unverified_fields=unverified,
        record=student_to_record(student),
        message=msg,
    )


@router.get("/college/{college_id}", response_model=CollegeInfo)
def get_college(college_id: str):
    """Get information about a registered college."""
    college = COLLEGES.get(college_id.upper())
    if not college:
        raise HTTPException(status_code=404, detail=f"College '{college_id}' not found.")
    return CollegeInfo(**{k: v for k, v in college.items() if k != "college_id" and k != "aliases" and k != "university_aliases" and k != "website"}, college_id=college_id)


@router.get("/colleges", response_model=list[CollegeInfo])
def list_colleges():
    """List all registered colleges in the database."""
    return [
        CollegeInfo(
            college_id=cid,
            name=c["name"],
            university=c["university"],
            accreditation=c["accreditation"],
            established=c["established"],
            location=c["location"],
            degree_types=c["degree_types"],
            departments=c["departments"],
        )
        for cid, c in COLLEGES.items()
    ]


@router.get("/resolve-college")
def resolve_college(name: str = Query(..., description="College name as extracted from document")):
    """
    Resolve a free-text college name to a registered college_id.
    Useful for pre-checking before calling verify-student.
    """
    college_id = resolve_college_id(name)
    if college_id:
        college = COLLEGES[college_id]
        return {
            "found": True,
            "college_id": college_id,
            "official_name": college["name"],
            "university": college["university"],
            "matched_input": name,
        }
    return {
        "found": False,
        "college_id": None,
        "official_name": None,
        "message": f"College '{name}' not found in registered institutions database.",
    }


@router.get("/health")
def college_api_health():
    return {
        "status": "healthy",
        "api": "College Verification API",
        "colleges_in_db": len(COLLEGES),
        "students_in_db": len(STUDENTS),
    }
