"""Synthetic state-transition tests only; no task, ACL, service or host changes."""
from dataclasses import replace

import pytest

from installer.ls5_disposable_release_model import State, Stop, stage, commit, recover

OLD = "a" * 40
NEW = "b" * 40
GOOD = dict(manifest_valid=True, files_verified=True, trusted_custody=True,
            runtime_closed=True, reparse_free=True, no_writers=True)
RECOVERY = dict(target_verified=True, journal_valid=True, stable_identity=True)


def test_disposable_install_stage_commit_stop_restart_rollback_model():
    initial = State(current=OLD)
    staged = stage(initial, NEW, **GOOD)
    assert staged.current == OLD and staged.pending == NEW
    active = commit(staged)
    assert active.current == NEW and active.previous == OLD
    restarted = recover(active, **RECOVERY)
    assert restarted.current == NEW and restarted.phase == "idle"
    rollback = stage(restarted, OLD, **GOOD)
    assert recover(rollback, **RECOVERY).current == NEW


def test_interrupted_stage_restores_previous():
    staged = stage(State(current=OLD), NEW, **GOOD)
    assert recover(staged, **RECOVERY) == State(current=OLD)


@pytest.mark.parametrize("field", list(GOOD))
def test_untrusted_stage_is_blocked(field):
    bad = dict(GOOD, **{field: False})
    with pytest.raises(Stop):
        stage(State(current=OLD), NEW, **bad)


@pytest.mark.parametrize("field", list(RECOVERY))
def test_untrusted_recovery_is_blocked(field):
    staged = stage(State(current=OLD), NEW, **GOOD)
    with pytest.raises(Stop):
        recover(staged, **dict(RECOVERY, **{field: False}))


def test_tampered_journal_and_pointer_are_blocked():
    staged = stage(State(current=OLD), NEW, **GOOD)
    for mutation in (dict(journal_previous="c" * 40),
                     dict(journal_candidate=OLD),
                     dict(current="d" * 40),
                     dict(phase="unknown")):
        with pytest.raises(Stop):
            recover(replace(staged, **mutation), **RECOVERY)


def test_replay_and_concurrent_stage_are_blocked():
    staged = stage(State(current=OLD), NEW, **GOOD)
    for state, candidate in ((State(current=OLD), OLD), (staged, "c" * 40)):
        with pytest.raises(Stop):
            stage(state, candidate, **GOOD)


@pytest.mark.parametrize("candidate", ["", "../evil", "C:\\bad", "a" * 39, "A" * 40, "é" * 40])
def test_version_path_unicode_and_case_alias_rejected(candidate):
    with pytest.raises(Stop):
        stage(State(current=OLD), candidate, **GOOD)


def test_commit_requires_prepared_journal():
    with pytest.raises(Stop):
        commit(State(current=OLD))

@pytest.mark.parametrize("forgery", ["false", 1, ["trusted"], {"trusted": True}])
def test_truthy_attestation_forgery_is_blocked(forgery):
    with pytest.raises(Stop):
        stage(State(current=OLD), NEW, **dict(GOOD, trusted_custody=forgery))
    prepared = stage(State(current=OLD), NEW, **GOOD)
    with pytest.raises(Stop):
        recover(prepared, **dict(RECOVERY, journal_valid=forgery))
