"""Bounded, offline linear/1m Bybit page preparation; not a second runtime.

No provider send, storage write, clock qualification or checkpoint advancement.
Raw images preserve decoded exchange strings, not original HTTP response bytes.
"""
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import re

from .market_ingestion_domain import (INSTRUMENT_DOMAIN, INSTRUMENT_SCHEMA_SHA256,
                                      DomainFormatError, decode_domain)

NORMALIZATION_VERSION = 'bybit.linear.kline.1m.fixed-decimal.v1'
MAX_ROWS = 1000
MAX_DECIMAL_CHARACTERS = 80


class PageValidationError(ValueError):
    """Reject whole page rather than truncate, skip or silently pick conflicts."""


def _u63(value):
    if (type(value) is not str or not re.fullmatch(r'0|[1-9][0-9]{0,18}',value)
            or int(value) > 9223372036854775807):
        raise PageValidationError('expected canonical u63 string')
    return int(value)


def _decimal(value):
    if (type(value) is not str or len(value) > MAX_DECIMAL_CHARACTERS
            or not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',value)):
        raise PageValidationError('expected bounded unsigned fixed decimal string')
    whole, dot, fraction = value.partition('.')
    whole = whole.lstrip('0') or '0'
    fraction = fraction.rstrip('0')
    return whole + ('.' + fraction if fraction else '')


def _wire(value):
    return json.dumps(value,separators=(',',':'),ensure_ascii=True).encode('ascii')


@dataclass(frozen=True)
class PreparedKlinePage:
    normalization_version: str
    instrument_bytes: bytes
    requested_start_ms: str
    requested_end_ms: str
    raw_rows_bytes: bytes
    raw_rows_sha256: str
    normalized_rows_bytes: bytes
    normalized_rows_sha256: str
    duplicate_count: str
    suspected_gaps: tuple[tuple[str,str],...]
    unobserved_before_ms: str
    candidate_next_end_ms: str | None
    disposition: str = 'PREPARED_UNCOMMITTED'


def prepare_kline_page(instrument_bytes, rows, start_ms, end_ms):
    """Prepare an explicit half-open request range; short pages are not complete.

    Source is fixed linear/1m: price quote/base, volume base coin, turnover quote
    coin. All values remain decimal strings; no float or quantization is used.
    Suspected gaps need later supported-source recovery/integrity disposition.
    The candidate cursor is not safe to persist without actual atomic publication.
    """
    try:
        identity = decode_domain(INSTRUMENT_DOMAIN, INSTRUMENT_SCHEMA_SHA256,
                                 instrument_bytes)
    except DomainFormatError as exc:
        raise PageValidationError('invalid instrument identity') from exc
    if json.loads(identity.instrument_bytes)['category'] != 'linear':
        raise PageValidationError('normalization source is linear only')
    lo,hi=_u63(start_ms),_u63(end_ms)
    if not lo < hi or lo % 60000 or hi % 60000:
        raise PageValidationError('expected aligned half-open request range')
    if type(rows) is not list or len(rows) > MAX_ROWS:
        raise PageValidationError('page row type/cap')
    normalized=[]; previous=None; duplicate_count=0; gaps=[]
    # Hold at most1000 rows of7 bounded strings; no caller row references retained.
    raw_rows=[]
    for source in rows:
        if type(source) is not list or len(source)!=7:
            raise PageValidationError('expected seven exchange string columns')
        timestamp=_u63(source[0])
        if timestamp % 60000 or not lo <= timestamp < hi:
            raise PageValidationError('candle timestamp outside aligned request')
        values=[_decimal(value) for value in source[1:]]
        o,h,l,c,v,t=map(Decimal,values)
        if min(o,h,l,c)<=0 or not l<=o<=h or not l<=c<=h:
            raise PageValidationError('invalid OHLC values')
        current=[source[0],*values]
        raw_rows.append(source.copy())
        if previous is not None and timestamp > previous:
            raise PageValidationError('source must be reverse timestamp ordered')
        if previous == timestamp:
            if normalized[-1]!=current:
                raise PageValidationError('conflicting duplicate candle')
            duplicate_count+=1
            continue
        upper=hi if previous is None else previous
        if timestamp+60000 < upper:
            gaps.append((str(timestamp+60000),str(upper)))
        normalized.append(current);previous=timestamp
    if previous is None:
        gaps.append((start_ms,end_ms))
    raw,normal=_wire(raw_rows),_wire(normalized)
    return PreparedKlinePage(
        NORMALIZATION_VERSION,instrument_bytes,start_ms,end_ms,raw,
        hashlib.sha256(raw).hexdigest(),normal,hashlib.sha256(normal).hexdigest(),
        str(duplicate_count),tuple(sorted(gaps,key=lambda gap:int(gap[0]))),
        str(previous) if previous is not None else end_ms,
        str(previous-1) if previous is not None and previous>lo else None)
