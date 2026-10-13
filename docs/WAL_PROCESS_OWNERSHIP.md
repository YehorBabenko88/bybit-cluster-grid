# WAL directory process ownership

SegmentWAL acquires an OS directory-owner lock before tail repair, checkpoint
cleanup or recovery. Windows uses a nonblocking msvcrt byte-range lock; POSIX uses
flock. The lock file is not deleted or replaced. Crash releases the owning process
descriptor; fork children explicitly close inherited descriptors without unlocking
the parent's open-file-description. IgnoreNew is still useful but not the sole guard.

Multiple handles in one PID share a counter and synchronous mutation/read lock.
Recovery iterators validate ownership, synchronize each read and are closed by
WAL.close. Storage closes only after producers/replay/write workers have stopped;
CONTROL releases the otherwise-unused ingestion WAL handle on leader loss.

An uncertain append IO failure blocks later append until exclusive recovery, so a
fully written but unacknowledged record cannot have its ID reused. Worker heartbeat
requests graceful supervisor restart on the fault signal. Duplicate/regressive
CRC-valid IDs are corruption: replay fails closed rather than skipping data.

The WAL record/CRC/checkpoint format is unchanged. Older WAL data remains readable;
previously corrupt duplicate-ID histories deliberately fail validation. A large-tail
test now uses distinct valid IDs, preserving its bounded-read assertion.

Only participating updated processes obey this advisory directory lock. Stop old
workers before enabling it: a running old binary that never locks this file is not
magically blocked on POSIX. The change does not claim lossless pre-WAL capture or
atomic fsync under power loss, and does not modify scheduler/service settings.

Deterministic tests exercise second-process open/recovery denial, same-PID IDs,
owner crash and recovery, uncertain fsync, duplicate IDs, blocked partial writes,
iterator invalidation and POSIX fork descriptor release. CI runs process tests on
Linux Python3.11/3.12 and Windows.
