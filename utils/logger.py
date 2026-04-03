from datetime import datetime
from typing import List
from agents.state import LogEntry
import json
import csv
import io


def make_log(agent: str, action: str, details: str, level: str = "INFO") -> LogEntry:
    return LogEntry(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        agent=agent,
        action=action,
        details=details,
        level=level,
    )


def logs_to_csv(logs: List[LogEntry]) -> str:
    """Convert logs to CSV string for download."""
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["timestamp", "agent", "action", "level", "details"],
    )
    writer.writeheader()
    for log in logs:
        writer.writerow(log)
    return output.getvalue()


def logs_to_json(logs: List[LogEntry], results: dict = None, verdict: str = "") -> str:
    """Convert full verification output to JSON for download."""
    payload = {
        "verification_timestamp": datetime.now().isoformat(),
        "overall_verdict": verdict,
        "field_results": results or {},
        "audit_logs": logs,
    }
    return json.dumps(payload, indent=2, default=str)
