# One-touch deployment concept

## Operator actions

### First machine
Run one elevated bootstrap command. It installs the Grid-owned Python environment,
CONTROL PostgreSQL, coordinator/archive scheduled tasks, Tailscale unattended mode,
and stores Telegram secrets locally. The system starts in INFRA_ONLY: no market
workload is allowed until explicit Telegram START after readiness checks.

### Second machine
Use Telegram /joinpilot to create a 15-minute one-use Grid enrollment token.
Run one elevated join command with the signed/hash-verified bundle, CONTROL MagicDNS
name/HTTPS URL, one-use Grid token, and one-use tagged Tailscale auth key.
The server, not the client, authorizes PILOT role.

### Additional machines
After PILOT reaches READY_FOR_EXPANSION, use /joinagent. Joining is otherwise identical.
Nodes are DB-less and can be added at any time. Removal is /uninstall NODE; the node
credential must be revoked server-side and the agent removes only Grid-owned software
unless explicit purge is confirmed.

## Availability contract

Collectors keep local WAL and continue bounded local capture during a temporary
CONTROL outage. They replay in order after CONTROL returns.

A single CONTROL machine is NOT highly available. Telegram and mutating coordination
cannot be promised while its PostgreSQL is down. Production HA requires at least two
control-capable machines plus replicated PostgreSQL and fencing. Exactly one leader
may run Telegram, scheduler, archive, rollout promotion and other mutating singleton
services. A standby may promote only after it can prove the old primary is fenced.
Fail-open dual-primary operation is forbidden.

## Remote administration

Windows Grid nodes use Tailscale unattended mode so tailnet connectivity survives
logout/reboot. Tailscale auth keys are onboarding inputs only and are never stored in
Grid .env or logs. Use tagged devices and least-privilege tailnet grants.

Do not git-pull into a running release. Development may happen remotely in GitHub,
but production nodes consume immutable release bundles:
release -> SHA-256 -> staging -> preflight -> canary -> health ACKs -> stable waves.
Any failed preflight/health check keeps or restores the previous release.

## Trading activation sequence

1. Complete historical strattester runs.
2. Require chronological out-of-sample folds and fee/slippage-aware statistics.
3. Promote only stable setup/regime combinations.
4. Start real-time market/grid observation in decision-only mode.
5. Run paper execution with immutable $100 trade plans and fixed initial SL/TP.
6. Compare live-paper expectancy with historical confidence intervals.
7. Only after explicit operator approval may a separate live execution layer be enabled.
