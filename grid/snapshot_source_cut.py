"""Strict source-cut evidence checks; never infer historical coherence.

This validates producer-supplied assertions only. Cross-store coherence is
not proven without independently authenticated coordinator receipts.
"""
class SourceCutBlocked(ValueError):
    pass


def validate_source_cuts(cuts, *, expected_epoch, expected_sources, knowledge_cutoff_ns):
    if (type(cuts) is not list or not cuts or type(expected_epoch) is not str
            or not expected_epoch or type(expected_sources) is not frozenset
            or not expected_sources or type(knowledge_cutoff_ns) is not int
            or knowledge_cutoff_ns < 0):
        raise SourceCutBlocked("Invalid source cut requirements")
    fields = {"source_id", "epoch_id", "snapshot_id", "cut_time_ns",
              "knowledge_cutoff_ns", "producer_attested"}
    seen = set()
    for cut in cuts:
        if type(cut) is not dict or set(cut) != fields:
            raise SourceCutBlocked("Incomplete source cut")
        source = cut["source_id"]
        if type(source) is not str or not source or source in seen:
            raise SourceCutBlocked("Duplicate source")
        seen.add(source)
        if (cut["epoch_id"] != expected_epoch
                or type(cut["snapshot_id"]) is not str or not cut["snapshot_id"]):
            raise SourceCutBlocked("Missing or mixed epoch identity")
        if (type(cut["cut_time_ns"]) is not int or cut["cut_time_ns"] < 0
                or type(cut["knowledge_cutoff_ns"]) is not int
                or cut["knowledge_cutoff_ns"] != knowledge_cutoff_ns
                or cut["cut_time_ns"] > knowledge_cutoff_ns):
            raise SourceCutBlocked("Inconsistent source cut time")
        if cut["producer_attested"] is not True:
            raise SourceCutBlocked("Source cut not producer-attested")
    if seen != expected_sources:
        raise SourceCutBlocked("Missing or unexpected sources")
    return {"status": "STRUCTURE_ONLY", "coherence_verified": False}
