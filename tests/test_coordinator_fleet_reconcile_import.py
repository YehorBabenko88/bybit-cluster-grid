"""Regression coverage for coordinator fleet reconciliation wiring."""

import grid.coordinator as coordinator
from grid.fleet_control import reconcile_fleet_operation


def test_coordinator_imports_fleet_reconciler():
    """The refresh loop and command ACK endpoint must resolve this symbol."""
    assert coordinator.reconcile_fleet_operation is reconcile_fleet_operation
    assert callable(coordinator.reconcile_fleet_operation)
