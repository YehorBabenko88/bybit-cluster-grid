"""Finite binary64 presentation of canonical Math results, never a math engine.

Historical v1 schemas use JSON numbers. Decimal strings of those source numbers
are the explicit normalization policy; mathematical sums belong solely to Math.
Original precise provider payloads remain separate from these display DTOs.
"""
from decimal import Decimal
from math import isfinite
from market_math import exact_sum, executed_volume_delta


def binary64(value):
    result = float(value)
    if not isfinite(result) or (value != 0 and result == 0):
        raise ValueError('historical numeric DTO cannot represent amount')
    return result


def amount_total(values):
    return binary64(exact_sum(Decimal(str(value)) for value in values))


def volume_total(values):
    return amount_total(values)


def volume_delta(buy, sell):
    return binary64(executed_volume_delta(Decimal(str(buy)), Decimal(str(sell))))
