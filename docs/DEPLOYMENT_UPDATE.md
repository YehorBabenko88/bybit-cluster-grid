# Zero-touch deployment and update

First install requires one Administrator/UAC approval. After that the agent is remotely managed.

Layout:
- Program Files/BybitClusterGrid: immutable application releases
- ProgramData/BybitClusterGrid: config, logs, spool, runtime state/data

Do not git-pull into a running release. Update flow:
GitHub release -> coordinator approval -> agent download -> SHA-256 -> staging -> preflight -> atomic version switch -> restart -> health check -> success or rollback.

Channels:
- canary: test on one/few nodes
- stable: fleet rollout after canary
- pinned: hold a node on a selected version

Collector releases and strategy plugins are independent. Strategy experiments normally require no collector restart.

Failure policy:
- download/hash/preflight failure: stay on current release
- failed post-update health: rollback
- GitHub/coordinator unavailable: keep collecting
- repeated update failure: quarantine update and alert Telegram

Remote commands should support status, start, stop, restart, update, rollout, rollback, logs, DB/storage and uninstall. Uninstall preserves data by default; destructive purge is separate and explicit.
