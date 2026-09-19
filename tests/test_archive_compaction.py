from datetime import datetime,timezone
from grid.archive_compaction import CompactionEvidence,safe_to_delete_raw
def test_raw_archive_deletion_requires_nonempty_verified_derivatives():
    t=datetime(2026,1,1,tzinfo=timezone.utc)
    assert safe_to_delete_raw(CompactionEvidence(10000,1440,50000,t,t))
    assert not safe_to_delete_raw(CompactionEvidence(10000,0,0,t,t))
