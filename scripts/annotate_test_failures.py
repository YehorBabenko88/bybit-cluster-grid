"""Bounded synthetic JUnit diagnostics; never publish tracebacks or environment.

Success here means diagnostics parsed, not that the test suite passed. The
workflow retains the original pytest step outcome and exact JUnit hash.
"""
import argparse
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

MAX_BYTES=16*1024*1024
MAX_CASES=10


def redact(value):
    value=re.sub(r'(?i)\bbearer\s+[^\s,;]+','Bearer [REDACTED]',value)
    # Entire URLs are withheld: userinfo, signed query strings and path secrets
    # must not become annotations even when unrelated to the immediate failure.
    value=re.sub(r'(?i)https?://[^\s<>]+','[URL_REDACTED]',value)
    value=re.sub(r'''(?ix)\b(password|passwd|pwd|access_token|refresh_token|token|secret|api[_-]?key|authorization|cookie|signature|sig)\b\s*[:=]\s*(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;]+)''',r'\1=[REDACTED]',value)
    return ''.join(c for c in value if ord(c)>=32 or c in '\r\n')


def escape(value):
    return value.replace('%','%25').replace('\r','%0D').replace('\n','%0A')


def annotations(raw):
    if type(raw) is not bytes or len(raw)>=MAX_BYTES or b'\x00' in raw or re.search(br'<!\s*(?:DOCTYPE|ENTITY)\b',raw,re.I):
        raise ValueError('JUNIT_DIAGNOSTICS_REJECTED')
    try:
        text=raw.decode('utf-8-sig')
        if re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b',text,re.I):
            raise ValueError('JUNIT_DIAGNOSTICS_REJECTED')
        root=ET.fromstring(text)
    except (ET.ParseError,ValueError,RecursionError) as exc:
        raise ValueError('JUNIT_DIAGNOSTICS_REJECTED') from exc
    if root.tag not in ('testsuite','testsuites'):
        raise ValueError('JUNIT_DIAGNOSTICS_REJECTED')
    lines=[]
    for case in root.iter('testcase'):
        outcome=case.find('failure')
        if outcome is None:outcome=case.find('error')
        if outcome is None:continue
        identity=redact('.'.join(x for x in (case.get('classname',''),case.get('name','UNKNOWN_TEST')) if x))[:200]
        message=redact(outcome.get('message','MESSAGE_UNAVAILABLE'))[-500:]
        lines.append('::error::'+escape(identity+': '+message))
        if len(lines)==MAX_CASES:break
    return lines


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('junit',type=Path)
    args=parser.parse_args(argv)
    try:
        with args.junit.open('rb') as stream:raw=stream.read(MAX_BYTES)
        for line in annotations(raw):print(line)
        return 0
    except (OSError,ValueError):
        # No path, raw parse error or input content is disclosed.
        print('::warning::JUNIT_DIAGNOSTICS_UNAVAILABLE')
        return 1


if __name__=='__main__':sys.exit(main())
