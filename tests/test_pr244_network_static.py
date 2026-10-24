"""Static network safety assertions against exact PR244 integration source, no sockets."""
import ast
from pathlib import Path

def test_first_boot_loopback_and_real_worker_source():
    source=Path("integration/first_boot.py").read_text(encoding="utf-8")
    tree=ast.parse(source)
    assert "from .first_boot_process import OwnedChild,stop_all" in source
    assert "for n in node_roots:await start_worker(n)" in source
    assert "('synthetic-a','synthetic-b')" in source
    assert "api='http://127.0.0.1:'" in source
    assert "loopback_endpoint(api)" in source
    assert "await asyncio.gather(*(enroll_given(x) for x in enrollments))" in source
    assert "await until(all_registered)" in source
    assert "await until(assigned)" in source
    assert "evidence.case('coordinator-crash-recovery')" in source
    assert "evidence.case('duplicate-ingest-idempotent')" in source
    assert tree is not None

def test_first_boot_external_network_denial_source():
    policy=Path("integration/first_boot_policy.py").read_text(encoding="utf-8")
    feed=Path("integration/synthetic_feed.py").read_text(encoding="utf-8")
    assert "if not local:raise PermissionError('FIRST_BOOT_EXTERNAL_NETWORK_BLOCKED')" in policy
    assert "if not local:raise PermissionError('FIRST_BOOT_EXTERNAL_DNS_BLOCKED')" in policy
    assert "RUNNER_ENVIRONMENT='github-hosted'" in policy
    assert "GITHUB_JOB='pg18'" in policy
    assert "COORDINATOR_CANDIDATES='[]'" in policy
    assert "POSTGRES_DSN=''" in policy
    assert "web.TCPSite(self.runner,'127.0.0.1',0)" in feed
