#!/usr/bin/env python3
"""
Quick integration test — verifies the backend API is working correctly.
Run AFTER starting the backend with: python run.py --backend-only

Usage:
    python test_api.py
    python test_api.py --url http://localhost:8000
"""

import sys
import json
import argparse
import requests

GREEN = "\033[92m"
RED   = "\033[91m"
YELLOW= "\033[93m"
BLUE  = "\033[94m"
BOLD  = "\033[1m"
RESET = "\033[0m"

BASE = "http://localhost:8000"


def ok(msg): print(f"  {GREEN}✓ {msg}{RESET}")
def fail(msg): print(f"  {RED}✗ {msg}{RESET}")
def warn(msg): print(f"  {YELLOW}⚠ {msg}{RESET}")
def section(title): print(f"\n{BOLD}{BLUE}── {title} ──{RESET}")


def test_health():
    section("Health Checks")
    for path, name in [
        ("/health", "Root"),
        ("/api/college/health", "College API"),
        ("/api/government/health", "Government API"),
        ("/api/corporate/health", "Corporate API"),
    ]:
        try:
            r = requests.get(f"{BASE}{path}", timeout=5)
            if r.status_code == 200:
                ok(f"{name}: {r.json().get('status','ok')}")
            else:
                fail(f"{name}: HTTP {r.status_code}")
        except Exception as e:
            fail(f"{name}: {e}")


def test_college_registry():
    section("College Registry")
    r = requests.get(f"{BASE}/api/college/colleges", timeout=5)
    colleges = r.json()
    ok(f"Found {len(colleges)} registered colleges:")
    for c in colleges:
        print(f"      • {c['name']} ({c['accreditation']})")


def test_college_resolve():
    section("College Name Resolution")
    test_names = [
        "MIT Pune", "VJTI Mumbai", "IIT Bombay", "Some Random College"
    ]
    for name in test_names:
        r = requests.get(f"{BASE}/api/college/resolve-college", params={"name": name}, timeout=5)
        data = r.json()
        if data.get("found"):
            ok(f"'{name}' → '{data['official_name']}'")
        else:
            warn(f"'{name}' → Not found")


def test_student_verification():
    section("Student Verification Tests")

    tests = [
        {
            "name": "VALID: Priya Sharma by PRN + Name",
            "payload": {
                "full_name": "Priya Sharma",
                "prn": "1234567890",
                "college_name": "MIT Pune",
                "passing_year": "2023",
                "degree": "B.E.",
            },
            "expected_status": "VALID",
        },
        {
            "name": "VALID: Aditya Kulkarni by Certificate Number",
            "payload": {
                "certificate_number": "MIT/BE/IT/2024/042",
                "full_name": "Aditya Kulkarni",
            },
            "expected_status": "VALID",
        },
        {
            "name": "VALID: Rohan Mehta at VJTI",
            "payload": {
                "full_name": "Rohan Mehta",
                "prn": "5555123456",
                "college_name": "VJTI Mumbai",
                "degree": "B.Tech",
                "branch": "Computer Science",
            },
            "expected_status": "VALID",
        },
        {
            "name": "MISMATCH: Correct PRN but wrong name",
            "payload": {
                "prn": "1234567890",
                "full_name": "Fake Person Name",
                "passing_year": "2023",
            },
            "expected_status": "INVALID",  # name mismatch
        },
        {
            "name": "NOT FOUND: Non-existent student",
            "payload": {
                "full_name": "Nobody Here",
                "prn": "0000000000",
                "college_name": "MIT Pune",
            },
            "expected_status": "NOT_FOUND",
        },
        {
            "name": "PARTIAL: Name only (low confidence)",
            "payload": {
                "full_name": "Priya Sharma",
            },
            "expected_status": None,  # Any — just check it responds
        },
    ]

    for test in tests:
        r = requests.post(f"{BASE}/api/college/verify-student",
                          json=test["payload"], timeout=5)
        data = r.json()
        actual_status = data.get("status")
        confidence = data.get("confidence", 0)
        found = data.get("found", False)
        matched = data.get("matched_fields", [])
        message = data.get("message", "")

        expected = test.get("expected_status")
        passed = (expected is None or actual_status == expected
                  or (expected == "INVALID" and actual_status in ("INVALID", "PARTIAL_MATCH", "NOT_FOUND")))

        if passed:
            ok(f"{test['name']}")
            print(f"       Status: {actual_status} | Confidence: {confidence:.0%} | Matched: {matched}")
        else:
            fail(f"{test['name']}")
            print(f"       Expected: {expected} | Got: {actual_status} | Message: {message}")


def test_government_apis():
    section("Government ID APIs (Dummy)")

    # Aadhaar
    r = requests.post(f"{BASE}/api/government/verify-aadhaar",
                      json={"aadhaar_number": "1234 5678 9012", "full_name": "Priya Sharma"}, timeout=5)
    data = r.json()
    if data.get("status") == "VALID":
        ok(f"Aadhaar verification: VALID (confidence: {data.get('confidence', 0):.0%})")
    else:
        warn(f"Aadhaar: {data.get('status')} — {data.get('message')}")

    # PAN
    r = requests.post(f"{BASE}/api/government/verify-pan",
                      json={"pan_number": "ABCPS1234P", "full_name": "Priya Sharma"}, timeout=5)
    data = r.json()
    if data.get("status") == "VALID":
        ok(f"PAN verification: VALID (confidence: {data.get('confidence', 0):.0%})")
    else:
        warn(f"PAN: {data.get('status')}")

    # Passport
    r = requests.post(f"{BASE}/api/government/verify-passport",
                      json={"passport_number": "A1234567", "full_name": "Priya Sharma"}, timeout=5)
    data = r.json()
    if data.get("status") == "VALID":
        ok(f"Passport verification: VALID — expires {data.get('expiry_date', 'N/A')}")
    else:
        warn(f"Passport: {data.get('status')}")


def main():
    global BASE
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000", help="Backend base URL")
    args = parser.parse_args()
    BASE = args.url.rstrip("/")

    print(f"\n{BOLD}DocVerify AI — Backend API Tests{RESET}")
    print(f"Target: {BLUE}{BASE}{RESET}\n")

    try:
        requests.get(f"{BASE}/health", timeout=3)
    except Exception:
        print(f"{RED}ERROR: Cannot reach {BASE}{RESET}")
        print(f"Start the backend with: {YELLOW}python run.py --backend-only{RESET}")
        sys.exit(1)

    test_health()
    test_college_registry()
    test_college_resolve()
    test_student_verification()
    test_government_apis()

    print(f"\n{GREEN}{BOLD}All tests complete.{RESET}\n")


if __name__ == "__main__":
    main()
