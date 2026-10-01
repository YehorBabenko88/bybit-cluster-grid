# Zero-touch onboarding and remote management

## Trust bootstrap
A completely unmanaged Windows computer cannot be safely installed remotely without an existing trusted management channel. Grid therefore requires exactly one trust-bootstrap action per new machine: run the onboarding script/package once as Administrator (UAC). After enrollment, normal lifecycle, updates, rollback, logs, stop/start and uninstall are controlled by CONTROL/Telegram.

If the environment already has a trusted management plane (Active Directory/GPO, Intune, RMM, or an operator-managed PowerShell Remoting policy), that system may execute the same onboarding command remotely; Grid does not store or distribute Windows administrator passwords.

## Roles
1. Install CONTROL on the first PC.
2. Before expansion, issue a PILOT token with Telegram: `/joinpilot LABEL`.
3. The token is one-use, expires after 15 minutes, and CONTROL authorizes the role. The enrolling client cannot promote itself.
4. Run `installer/join-agent.ps1` as Administrator on the target PC with the verified Windows bundle URL/SHA256, CONTROL URL and token.
5. After pilot validation reaches READY_FOR_EXPANSION, issue NORMAL tokens with `/joinagent LABEL` for additional PCs.

Node count is dynamic; no fixed fleet size is encoded.

## Network
Agents initiate HTTP(S) requests to CONTROL. No inbound agent firewall port is required.

CONTROL listens on TCP 8765. The Windows firewall rule permits only LocalSubnet and the Tailscale CGNAT range 100.64.0.0/10. Do not port-forward 8765 from the public Internet.

## Tailscale
Tailscale is optional and is a management transport, not the Grid trust root. A remote admin PC can reach CONTROL over its Tailscale IP/MagicDNS name. Agent-to-CONTROL traffic may also use Tailscale by setting COORDINATOR_URL to the CONTROL Tailscale address.

Recommended tailnet policy:
- admin devices -> CONTROL:8765 only;
- agents -> CONTROL:8765 only when agents use Tailscale transport;
- no broad agent-to-agent management access.

If Tailscale is unavailable, already-running market collection must not depend on it unless COORDINATOR_URL itself uses the Tailscale path.

## Updates
Do not git-pull a running installation. Use the existing release/canary/SHA256/preflight/atomic-switch/health/rollback pipeline.
