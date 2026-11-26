"""Historical Grid import alias; canonical v2 validator lives only in Market Data.

Do not instantiate Grid transport/worker or a second consumer/validation kernel.
This alias is intentionally not included in the canonical installed wheel.
"""
from market_data_v2.qualified_read_contract import (
    ProvenanceReadError, validate_minute, qualify_records,
)
__all__=("ProvenanceReadError","validate_minute","qualify_records")
