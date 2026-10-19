"""Offline policy gate for dangerous deployment commands and paths.

This is an advisory static scanner; absence of matches is NOT execution authorization.
"""
import re

FORBIDDEN = (
    ("schema-2 activation", re.compile(r"(?i)\b(?:enable|activate|apply|deploy)[-_ ]*schema[-_ ]*2\b")),
    ("service mutation", re.compile(r"(?i)\b(?:Start-Service|Restart-Service|Stop-Service|sc\.exe\s+(?:start|stop)|systemctl\s+(?:start|stop|restart))\b")),
    ("database mutation", re.compile(r"(?i)\b(?:initdb|pg_ctl\s+start|psql\s+.*(?:-c|--command))\b")),
    ("production host reference", re.compile(r"(?i)\b(?:LS5|LS7|LS-5|LS-7)\b")),
)

def scan_text(text):
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    findings = []
    for line_number, line in enumerate(text.splitlines(), 1):
        for name, pattern in FORBIDDEN:
            if pattern.search(line):
                findings.append({"line": line_number, "rule": name})
    return findings

def assess_text(text):
    findings = scan_text(text)
    return {"status": "BLOCKED_UNPROVEN" if findings else "STATIC_SCAN_ONLY",
            "findings": findings, "execution_authorized": False,
            "note": "Heuristic scan: review required; not proof of runtime safety"}
