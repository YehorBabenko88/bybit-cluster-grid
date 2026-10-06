# Windows agent network onboarding

Grid agents are DB-less and should reach CONTROL over Tailscale only.

## One-time tailnet policy

Do not maintain per-machine 100.x address rules. Authorize two tags in the Tailscale admin policy:

- `tag:grid-control` for CONTROL nodes.
- `tag:grid-node` for PILOT/NORMAL agents.
- Allow TCP 8765 from `tag:grid-node` to `tag:grid-control`.
- Do not grant agent-to-agent access unless a separate operational need exists.

The exact policy syntax should be managed centrally in the tailnet administrator UI. The installer deliberately does not carry a Tailscale API/OAuth secret, so a compromised worker cannot rewrite network policy.

## Automated bootstrap

`bootstrap.ps1` now:
1. installs the official Tailscale package with winget when needed;
2. authenticates with a one-time auth key only when the client is not already Running;
3. uses `tag:grid-control` for CONTROL and `tag:grid-node` for agents by default;
4. enables unattended mode;
5. tests the actual CONTROL TCP port and `/health` before enrollment;
6. detects ESET services and adds an ESET-specific diagnostic when connectivity is blocked.

Use tag-scoped, reusable/ephemeral Tailscale auth keys according to the operator's tailnet policy. Never persist the key in Grid configuration.

## ESET and Windows Firewall

Grid does not disable or weaken endpoint security. Normal agents initiate outbound TCP to CONTROL:8765 and require no inbound Grid port. CONTROL needs inbound TCP 8765 from the Tailscale interface/tailnet only.

If ESET Firewall is centrally managed, create one policy allowing the Grid/Tailscale path and assign it to the Windows machines that can become Grid nodes. This is preferable to creating a local exception on every PC.

If ESET is locally managed, the bootstrap network preflight fails closed with a specific diagnostic. The operator should add the narrow outbound exception in ESET and rerun bootstrap. Do not disable ESET as a workaround.

## Adding PC5, PC6, ...

Once the tag policy and (if applicable) ESET policy exist, adding a machine should require only:
1. obtain a one-use Grid enrollment token from Telegram;
2. run the signed/hash-verified onboarding bundle as Administrator with the CONTROL Tailscale URL and a Tailscale auth key if the PC is not already authenticated;
3. wait for the bootstrap preflight and enrollment to complete.

No per-PC Tailscale IP ACL should be necessary.
