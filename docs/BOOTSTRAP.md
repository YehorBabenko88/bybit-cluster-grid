# Bootstrap policy

The bootstrap first inventories the machine and writes discovery.json.

Python:
- compatible Python >=3.11 may be used only to create a dedicated Grid venv;
- dependencies are installed/upgraded only inside that venv;
- an unrelated global Python environment is never modified;
- if no compatible Python exists, use the packaged isolated runtime.

PostgreSQL:
- discover PATH, Windows services and PostgreSQL registry installations;
- never upgrade, stop, reconfigure or remove an unrelated PostgreSQL instance;
- if an existing server is approved/reachable, provision a Grid-owned database and role only;
- otherwise install a dedicated Grid-owned PostgreSQL instance on a separate port/data directory;
- never guess an existing PostgreSQL administrator password.

Enrollment:
- deployment bundle contains/receives a short-lived one-time enrollment token;
- first contact exchanges it for a unique per-node credential;
- the one-time token is invalidated;
- future heartbeat/control uses the node credential;
- credentials can be revoked per machine without affecting the fleet.

Packages:
- requirements are upgraded only inside the Grid venv;
- release preflight must pass before service activation.
