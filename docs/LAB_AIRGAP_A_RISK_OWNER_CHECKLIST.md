# Risk and owner checklist — unresolved L1/L2 conditions

All resources/roles below are PROPOSED / UNVERIFIED; assignments are requested,
not verified. All physical activities remain NO-GO. Human review count: zero.

| Risk | Priority / proposed accountable role | Closure evidence required; current state |
|---|---|---|
| Shared privileged host control falsifies observations | P1 / security reviewer + observer owners | Separate trusted collection/custody and limited claim; UNVERIFIED |
| Wireless/bridge/shared integration breaks air-gap | P1 / architecture reviewer + hardware owner | Independently reviewed physical/device/topology packet; UNVERIFIED |
| No independently monotonic anchor / correlated rollback | P1 / external trust owner | Reviewed surviving root/storage/time model; NOT_IMPLEMENTED; hard blocker for certification |
| Shuttle falsely treated as witness or fresh challenge | P1 / evidence custodian | Outbound-only scope and explicit no-freshness claim accepted by two reviewers; UNVERIFIED |
| Evidence firmware/parser/malware attack | P1 / quarantine owner | Dedicated intake, bounded safe-format controls and media custody; UNVERIFIED |
| Operator/observers share keys/admins/restore domain | P1 / two human reviewers | Independent custody evidence and conflict disclosure; UNVERIFIED |
| PGDATA path contracts disagree | P1 / adapter + native contract owners | Versioned mapping and adversarial tests without bypass/schema-2; UNRESOLVED |
| Privilege/ACL/handle/ABA sampling creates false PASS | P1 / security reviewer | Case-specific evidence limitations, negative review and refusal on ambiguity; NOT_RUN |
| Trial exceeds owned fixture or quota | P1 / operator + STOP custodian | Ownership/capacity and stop boundaries independently approved; UNVERIFIED |
| Power loss/cleanup failure followed by silent retry | P1 / recovery owner | Pending/committed reconciliation, re-entry block, new approval; NOT_IMPLEMENTED |
| Automated readiness promotion or fake human review | P1 / project owner | Explicit human decisions on exact SHA; zero received, no automated authority |
| Removal destroys WAL/history or another installation | P1 / resource + archive owners | Separate ownership-verified teardown approval; never automatic deletion; NOT_AUTHORIZED |

## Human inputs required (private where sensitive)

- Hardware capability and dedicated ownership, Windows/Hyper-V/image versions;
  symbolic public inventory only, private evidence of devices/storage isolation.
- Four independent custody assignments: operator, observer A, observer B, STOP;
  two independent human architecture/security reviewers of this exact plan.
- Separate quarantine/archive devices, owned export media, retention/quota and
  firmware/parser/content controls; no returning media or unreviewed imports.
- Trusted time policy, external root/ledger design and explicit acceptance of
  unproved freshness/anti-rollback limits; never equate signed files with witnesses.
- Reviewed PGDATA mapping, collector provenance, twelve case scopes, emergency
  STOP/recovery/removal procedures and separate L2/L3/L4 authorizations.

Please request two real independent humans to review the new Draft PR. Each should
record review scope, exact SHA, concerns, conflicts/dependencies and a decision;
an AI-authored placeholder is not an approval. Do not ask for secrets, actual SID
dumps, key material or private IPs in GitHub comments. Arrange an approved private
review channel for identifying evidence; public decisions may reference redacted
records. A later change invalidates review scope until reviewers assess that SHA.

**L1 NO-GO:** two reviews and resource/trust/PGDATA assumptions outstanding.
**L2 NO-GO:** no resource provisioning or native/physical experiment authorization.
No test result clears these conditions automatically.
