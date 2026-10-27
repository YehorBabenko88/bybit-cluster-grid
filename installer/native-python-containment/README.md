# Actual Python negative boundary — hosted only

No physical executor or authorization is exposed. Default/unknown argv refuses.
Native main also requires real hosted CI context and refuses machines named LS5/PC4.
Never spoof CI variables. Source changes and hosted GUID fixtures only.

The new entry point reuses the existing restricted-token, low-label, capability-free
AppContainer, private desktop, suspended atomic Job-list assignment and held
process identity code. The Job permits one active process, no breakaway, and kills
its owned process on last handle close. Only one own append-only diagnostic handle is explicitly inherited through an atomic HANDLE_LIST; ambient parent handles are excluded. A
purposefully inheritable shareable canary tests that restriction.

A measured CPython/runtime/dependency/Grid closure is copied CREATE_ONLY beneath a
fresh AppContainer profile. Source/native files and directories give package RX;
separate own Data and result give package write with low mandatory label. File
identities, descriptors and hashes are held/rechecked. No name-based cleanup,
profile deletion, existing directory adoption or existing ACL changes occur.
The runner disposes retained GUID resources. Copy input provenance is the pinned
GitHub setup-python action plus pinned direct requirements/resolved hash inventory;
this is not an external software-supply-chain or physical source attestation.

Explicit ._pth, -I -B -S, empty ambient PATH/Python variables and explicit environment
remove parent credentials and ambient Python paths. The child narrows DLL search
before third-party imports and enumerates loaded DLL paths to the measured root or
Windows System32/WinSxS. Windows OS trust and a nonmalicious controller custodian are
assumptions; a privileged local administrator can subvert the host. These checks do
not prove denial for every installed directory or every account's effective rights.

The actual Python driver imports actual Grid, calls Coordinator.startup expecting
permission-denied at real DB connection and no leader services, then calls Worker.run
and cancels it after observing INFRA_ONLY/no market tasks. A protected *shareable*
foreign canary must return AccessDenied5, not sharing violation; own data must work.
OS TCP denial is checked against own loopback listener and TEST-NET address only.
No real trading endpoint, DSN or external credentials are used.

These are real Windows/Python negative lifecycle tests, not Windows Grid E2E.
Capability-free AppContainer prevents required loopback networking; no capability,
loopback exemption, firewall/WFP or host-policy change is installed. A reviewed
brokered transport or separately authorized disposable VM remains necessary.

Owner signing-key custody, external durable consume-before-effects/replay anchor,
anti-rollback/trusted-time/reboot recovery and physical effective ACL/token/PGDATA
proof are independent P0 prerequisites. Local signatures/HashSets/files or simulated
restart cannot supply them. No G1 stage is enabled by this fixture's PASS.
Physical0/10 NOT_RUN. Execute/Cleanup NOT_AUTHORIZED. Deployment NO-GO.

Current loader investigation uses DEBUG_ONLY_THIS_PROCESS on the newly created
owned child; no process attachment or memory write/injection is exposed. Events
are bounded and bound to the held process ID, and record DLL/exception/exit data.
Only the first first-chance breakpoint mapped to the actual System32 ntdll image
is continued as handled; application/second-chance breakpoints are not swallowed.
Debug process/thread event handles belong to Windows; the debugger closes only
image/DLL file handles, per Microsoft WaitForDebugEvent lifecycle documentation:
https://learn.microsoft.com/en-us/windows/win32/api/debugapi/nf-debugapi-waitfordebugevent

Receipts explicitly say DEBUGGED boundary. A debugged startup cannot demonstrate
identical undebugged behavior. Earlier actual launch returned C0000142 before
Python entry; no successful real-runtime observation may be inferred from that.
The Python driver itself defaults PlanOnly, refuses LS5/PC4 and requires an owned
GUID AppContainer profile shape plus a private native-child argument before I/O.

Loader trace at91f343b showed only ntdll/kernel32/KernelBase before C0000142,
without Python DLL entry. The next diagnostic variant selects the unmodified
official pythonw.exe from that same measured setup-python distribution, verifies
its PE x64 GUI subsystem2 and uses explicit file-backed diagnostics. No PE header,
console privilege, AppContainer capability, Job limit or desktop ACL is relaxed.
This tests a console-initialization hypothesis; it is not a confirmed root cause
until actual hosted execution succeeds and its scope is independently reviewed.

At2e28d8f the official GUI launcher entered actual CPython and passed the first
four driver cases; the console-specific initialization refusal did not recur.
The next failure was the ambiguous CRT PermissionError probe. File-denial tests
now call CreateFileW directly and require exact error5; no sharing/unknown errno
is accepted, and no data write is attempted through an unexpectedly granted handle.

Native build provenance correction: all four native projects now list their
reviewed source files explicitly and disable default wildcard items. Checkout
verification rejects untracked C#/C/C++/MSBuild inputs, and native CI performs
pre/post build checks with ambient Directory.Build imports disabled. This closes
a demonstrated untracked build-input gap; it is not signed build provenance or
protection against a compromised CI/SDK/privileged host.

Each reported image/DLL load is now checked by the native parent before debug
continuation: measured files must match their retained file identity/descriptor;
other loads are limited to assumed-trusted Windows System32/WinSxS. Unknown
paths/handles and loads from writable Data are BLOCKED. This bounds reported
loader events; no untested guarantee about DLL entry-point timing or compromised
Windows/privileged administrators is asserted. The child also attempts a read
handle to its known live native parent and must receive exact AccessDenied5.

The absent-parent-file-handle probe distinguishes exact Win32 invalid handle6 from
ctypes' debugger-visible STATUS_INVALID_HANDLE (C0000008, signed/unsigned32).
Both mean the probed handle does not reference an available object; neither is used
as ACL-denial evidence. Other exceptions, AccessDenied, sharing and unknown states
block this absence probe. The debugger still does not swallow this exception.

The foreign FileIdInfo comparison decodes the two little-endian64 words and uses
the native observer's High:X16+Low:X16 representation. Raw memory hex has a
different byte order and must not be used to assert distinct identity.

Network evidence requires exact Winsock WSAEACCES10013. Timeouts, connection
refusal, unknown errors and errno-only13 do not prove OS policy denial; report
bounded numeric Win32/errno facts and remain BLOCKED. No loopback exemption,
capability or firewall policy is changed to make these checks pass. See Microsoft
[loopback isolation documentation](https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/troubleshooting-uwp-firewall).

Socket-stage diagnostics distinguish TimeoutError from Win32 denial, on bothIPv4/6.
Parent positive controls connect/accept each owned listener before child startup.
WSAGetLastError read after a Python exception is diagnostic only, not authoritative.
Read-only BFE/firewall/loopback-exemption metadata does not identify an effective WFP filter.
A separate hosted-only undebugged comparison keeps the same token/AppContainer/Job/
image/environment gates but without loader-event observation; its diagnostic receipt cannot replace required debugged
acceptance or authorize physical execution. It uses a separate fresh GUID bundle.

Read-only [NetworkIsolationDiagnoseConnectFailureAndGetInfo](https://learn.microsoft.com/en-us/windows/win32/api/networkisolation/nf-networkisolation-networkisolationdiagnoseconnectfailureandgetinfo)
queries only the two literal owned loopback targets. API failures/unknown NETISO
enums remain BLOCKED; successful diagnosis is not a grant, correlated WFP packet
receipt, or substitute for strict network denial. No capabilities are added.
