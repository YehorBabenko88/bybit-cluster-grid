"""Explicit unresolved-boundary reproductions, NOT authorization acceptance.

No Coordinator startup, external request, database or physical process is used.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from pathlib import Path

from grid.runtime_gate import market_work_allowed
from grid.fleet_control import reconcile_fleet_operation


def test_persisted_active_does_not_prove_operator_authorization(monkeypatch):
    monkeypatch.setenv('GRID_SHARED_TOKEN', '')
    pool = SimpleNamespace(fetchrow=AsyncMock(return_value={
        'state':'ACTIVE','requested_by':None,'reason':None,'updated_at':None}))
    # This is current behavior and an explicit deployment BLOCKER, not a desired
    # security invariant. Empty HTTP token does not quarantine market work.
    assert asyncio.run(market_work_allowed(pool)) is True


def test_empty_resume_currently_opens_active_without_ack(monkeypatch):
    import grid.fleet_control as fleet
    setter = AsyncMock()
    monkeypatch.setattr(fleet, 'set_runtime_state', setter)
    pool = SimpleNamespace(fetchrow=AsyncMock(return_value={
        'id':'synthetic-operation','action':'RESUME','snapshot':{},'targets':[]}),
        fetch=AsyncMock(return_value=[]),execute=AsyncMock())
    result = asyncio.run(reconcile_fleet_operation(pool))
    assert result['state'] == 'ACTIVE'
    assert setter.await_args.args[1] == 'ACTIVE'


def test_blocked_runbook_has_no_executable_coordinator_launch():
    text=(Path(__file__).resolve().parents[1]/'docs/PC4_DDL_FREE_INTEGRATION_RUNBOOK.md').read_text(encoding='utf-8')
    g5=text.split('### G5 ',1)[1].split('### G6 ',1)[0]
    assert "throw 'BLOCKED:" in g5
    assert not any(line.lstrip().startswith('& $Python') and 'uvicorn' in line for line in g5.splitlines())
