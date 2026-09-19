# Worker secret handling

Deployment and release bundles contain no permanent node credentials.

A short-lived one-time enrollment token is exchanged with the coordinator for a per-node credential. The returned credential is stored under ProgramData/BybitClusterGrid/secrets with inherited ACLs removed and access granted only to SYSTEM and Administrators.

The worker reads the credential at runtime. Do not commit it to GitHub, write it to normal logs, or expose it through Telegram/status endpoints.

This is local-machine protection, not hardware-backed secret storage. A later hardening step may protect the credential with Windows DPAPI or certificate-backed storage.
