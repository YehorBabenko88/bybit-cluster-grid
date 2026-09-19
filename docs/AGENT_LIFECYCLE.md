# Agent lifecycle

The coordinator is the single control plane. Telegram talks to the coordinator, never directly to every worker.

Desired lifecycle:
- install/register
- start
- pause/drain
- restart own grid service
- update grid software
- uninstall grid software and its dedicated database/files only
- never delete unrelated PostgreSQL clusters, user files or software

Workers continuously report:
- CPU load and core count
- RAM total/available/percentage
- disk total/free
- assigned symbol count
- websocket health/lag
- DB queue depth and DB size
- process uptime/restarts
- log/error counters
- software/version/dependency state

Resource protection:
- soft pressure: stop taking new symbols
- sustained pressure: coordinator drains expensive symbols
- critical disk: stop raw/high-frequency persistence first, preserve aggregates and safety margin
- DB lag: bounded queue/backpressure and disk spool
- internet loss: reconnect with exponential backoff
- process failure: OS service restarts agent
- logs: rotating files with bounded total size

Remote uninstall is a privileged operation and should require explicit confirmation/token; the worker only records an uninstall request, while a local maintenance component performs the allow-listed removal steps.
