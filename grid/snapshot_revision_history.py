"""Pure revision history consistency gate for synthetic provenance records.

This does not infer missing versions or authenticate producer history.
"""
from __future__ import annotations
from .snapshot_historical_provenance import (
    HistoricalProvenanceBlocked, validate_historical_bar,
)


def validate_revision_history(rows, *, knowledge_cutoff_ns):
    if type(rows) is not list or not rows:
        raise HistoricalProvenanceBlocked("Empty revision history")
    seen = set()
    last = {}
    for row in rows:
        validate_historical_bar(row, knowledge_cutoff_ns=knowledge_cutoff_ns)
        identity = (row["exchange"], row["market_type"], row["symbol"], row["event_ns"])
        revision = row["revision"]
        key = (identity, revision)
        if key in seen:
            raise HistoricalProvenanceBlocked("Duplicate historical revision")
        seen.add(key)
        previous = last.get(identity)
        if previous is None:
            if revision != 1:
                raise HistoricalProvenanceBlocked("Missing initial revision")
        elif (revision != previous[0] + 1
              or row["revision_recorded_ns"] < previous[1]
              or row["first_available_ns"] < previous[2]):
            raise HistoricalProvenanceBlocked("Gap or nonmonotonic revision history")
        last[identity] = (revision, row["revision_recorded_ns"],
                          row["first_available_ns"])
    return {"status": "STRUCTURE_ONLY", "history_verified": False}
