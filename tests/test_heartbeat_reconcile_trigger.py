"""Heartbeat reconciliation must inspect dead collectors even when assignments are unchanged."""
from pathlib import Path


def test_heartbeat_detects_finished_collectors_without_assignment_change():
    worker=Path("grid/worker.py").read_text(encoding="utf-8")
    assert "dead_trade_tasks=any(task.done() for task in self.trade_tasks.values())" in worker
    assert "dead_micro_tasks=any(task.done() for task in self.micro_tasks)" in worker
    assert "if assignments_changed or dead_trade_tasks or dead_micro_tasks:" in worker
    assert "self.micro_signature=None" in worker
