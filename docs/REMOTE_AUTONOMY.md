# Remote autonomy target

After one local Administrator/UAC installation, normal operation requires no physical access.

Coordinator responsibilities:
- discover/reconcile Bybit universe
- assign symbols
- receive node telemetry
- issue allow-listed commands
- coordinate strategy jobs
- coordinate release channels
- expose Telegram control

Worker responsibilities:
- keep collecting when coordinator/GitHub is temporarily unavailable
- report health on heartbeat
- apply assignment diffs without restart
- execute structured commands
- run simulations at lower priority than collection
- reject work under resource pressure
- self-restart under OS supervision

Release safety:
1. build immutable release bundle
2. compile/test in CI
3. publish checksum
4. canary node download
5. checksum and local preflight
6. activate and restart
7. heartbeat health window
8. stable rollout or automatic rollback

Never use live git checkout as the production runtime. Never expose a generic remote shell through Telegram.

Initial bootstrap credentials should eventually use one-time enrollment tokens and per-node credentials rather than one fleet-wide shared token.
