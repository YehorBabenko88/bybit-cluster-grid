"""Disposable release-state model. No Windows API, host tasks, ACLs or production paths.

This is a negative-test fixture only, not an installer or authorization gate.
"""
from dataclasses import dataclass, replace
import re

SHA = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True)
class State:
    current: str
    previous: str | None = None
    pending: str | None = None
    phase: str = "idle"
    journal_previous: str | None = None
    journal_candidate: str | None = None


class Stop(Exception):
    pass


def validate_version(version):
    if not isinstance(version, str) or not SHA.fullmatch(version):
        raise Stop("INVALID_VERSION")


def stage(state, candidate, *, manifest_valid, files_verified, trusted_custody,
          runtime_closed, reparse_free, no_writers):
    validate_version(state.current)
    validate_version(candidate)
    if state.phase != "idle" or state.pending is not None:
        raise Stop("UNRESOLVED_TRANSACTION")
    if candidate == state.current:
        raise Stop("REPLAY_OR_NOOP")
    if not all((manifest_valid, files_verified, trusted_custody,
                runtime_closed, reparse_free, no_writers)):
        raise Stop("UNVERIFIED_STAGE")
    return replace(state, pending=candidate, phase="prepared",
                   journal_previous=state.current, journal_candidate=candidate)


def commit(state):
    if state.phase != "prepared" or state.pending != state.journal_candidate:
        raise Stop("INVALID_COMMIT")
    if state.current != state.journal_previous:
        raise Stop("CURRENT_CHANGED")
    return replace(state, current=state.pending, previous=state.current,
                   pending=None, phase="committed")


def recover(state, *, target_verified, journal_valid, stable_identity):
    if state.phase == "idle":
        return state
    if not all((target_verified, journal_valid, stable_identity)):
        raise Stop("RECOVERY_UNVERIFIED")
    if state.phase not in ("prepared", "committed"):
        raise Stop("INVALID_PHASE")
    for value in (state.current, state.journal_previous, state.journal_candidate):
        validate_version(value)
    if state.journal_previous == state.journal_candidate:
        raise Stop("JOURNAL_ALIAS")
    if state.current not in (state.journal_previous, state.journal_candidate):
        raise Stop("JOURNAL_CONFLICT")
    target = state.journal_previous if state.phase == "prepared" else state.journal_candidate
    return replace(state, current=target,
                   previous=state.journal_previous if state.phase == "committed" else state.previous,
                   pending=None, phase="idle", journal_previous=None, journal_candidate=None)
