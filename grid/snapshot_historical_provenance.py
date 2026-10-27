"""Fail-closed historical bar provenance validation.

No missing timestamps, revision history or availability is reconstructed.
"""
class HistoricalProvenanceBlocked(ValueError):
    pass


def validate_historical_bar(row, *, knowledge_cutoff_ns):
    required = {"exchange", "market_type", "symbol", "event_ns",
                "ingest_ns", "first_available_ns", "revision",
                "revision_recorded_ns", "producer_id", "source_epoch",
                "history_complete"}
    if type(row) is not dict or set(row) != required:
        raise HistoricalProvenanceBlocked("Missing historical provenance")
    for key in ("exchange", "market_type", "symbol", "producer_id", "source_epoch"):
        if type(row[key]) is not str or not row[key]:
            raise HistoricalProvenanceBlocked("Invalid source identity")
    if type(knowledge_cutoff_ns) is not int or knowledge_cutoff_ns < 0:
        raise HistoricalProvenanceBlocked("Invalid knowledge cutoff")
    for key in ("event_ns", "ingest_ns", "first_available_ns",
                "revision", "revision_recorded_ns"):
        if type(row[key]) is not int or row[key] < 0:
            raise HistoricalProvenanceBlocked("Invalid historical timestamp/revision")
    if (row["revision"] < 1 or row["history_complete"] is not True
            or not row["event_ns"] <= row["ingest_ns"] <= row["first_available_ns"]
            or not row["ingest_ns"] <= row["revision_recorded_ns"] <= row["first_available_ns"]
            or row["first_available_ns"] > knowledge_cutoff_ns):
        raise HistoricalProvenanceBlocked("Unproven historical availability")
    return {"status": "STRUCTURE_ONLY", "history_verified": False}
