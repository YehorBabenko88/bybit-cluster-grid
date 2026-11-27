"""Market Data v2: read-only protocol extension, not an acquisition process.

Imports the canonical Data49 producer/read path without modifying historical
v1.1 runtime members. A managed v2 server *replaces*, never parallels, the
same listener/entrypoint when explicitly selected by Root admission.
"""
from .qualified_read_contract import ProvenanceReadError, qualify_records
__all__=("ProvenanceReadError","qualify_records")
