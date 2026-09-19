# Coordinator control plane

Workers do not expose inbound management ports. They poll/piggyback commands over their authenticated heartbeat to the coordinator.

Command lifecycle:
queued -> delivered -> done/failed.

Initial actions:
- pause/resume collection assignment
- restart supervised process
- rollback release
- uninstall

Update installation is intentionally separate from arbitrary shell execution. The coordinator sends structured allow-listed commands, not raw PowerShell/cmd strings.

This reduces remote-management risk and makes Telegram an authenticated front-end to a narrow command API rather than a remote shell.

Before any release rollout, preflight must compile the Python package and validate required files. Canary rollout precedes stable rollout.
