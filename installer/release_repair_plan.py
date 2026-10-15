"""Offline, read-only release assessment. No DB connection, target imports or repair."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from installer import windows_preflight as w


class Rejected(Exception):
    pass


def require(condition, code):
    if not condition:
        raise Rejected(code)


def read_file(path, limit=65536, optional=False):
    require(w.physical(path), 'REPAIR_PATH_REDIRECTED')
    if optional and not path.exists():
        return None
    require(path.is_file(), 'REPAIR_EVIDENCE_FILE_REQUIRED')
    with path.open('rb') as stream:
        value = stream.read(limit + 1)
    require(len(value) <= limit, 'REPAIR_EVIDENCE_TOO_LARGE')
    return value


def parse_json(value):
    try:
        return json.loads(value.decode('utf-8-sig'), object_pairs_hook=w.unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError):
        raise Rejected('REPAIR_JSON_INVALID') from None


def assess(root, reviewed, evidence_path, role='CONTROL'):
    result = {'schema': 1, 'mode': 'read-only-plan', 'activation_authorized': False,
              'repair_authorized': False, 'marker_removal_authorized': False,
              'database_checked_live': False, 'proposed_changes': []}
    try:
        root, evidence_path = Path(root).absolute(), Path(evidence_path).absolute()
        require(role in ('CONTROL', 'WORKER') and isinstance(reviewed, str)
                and w.SHA.fullmatch(reviewed), 'REPAIR_REQUEST_INVALID')
        require(root.is_dir() and w.physical(root), 'REPAIR_INSTALL_ROOT_INVALID')
        captured = {}
        def capture(name, path, limit=65536, optional=False):
            data = read_file(path, limit, optional)
            captured[name] = (path, limit, optional, data)
            return data
        pointers = {}
        for name in ('current', 'previous', 'pending', 'failed'):
            raw = capture(name, root / (name + '.version'), 256, name != 'current')
            if raw is None:
                pointers[name] = None
            else:
                value = raw.decode('ascii').strip()
                require(w.SHA.fullmatch(value), 'REPAIR_POINTER_INVALID')
                pointers[name] = value
        current, previous, pending = (pointers[n] for n in ('current','previous','pending'))
        require(pointers['failed'] != reviewed, 'REPAIR_REVIEWED_RELEASE_FAILED')
        raw = capture('journal', root / 'switch-journal.json', optional=True)
        journal = parse_json(raw) if raw is not None else None
        if raw is not None:
            require(isinstance(journal, dict) and set(journal) == {'schema','previous','candidate','phase'}, 'REPAIR_JOURNAL_INVALID')
            require(type(journal['schema']) is int and journal['schema'] == 1
                    and journal['phase'] in ('prepared','committed')
                    and all(isinstance(journal[n], str) and w.SHA.fullmatch(journal[n]) for n in ('previous','candidate'))
                    and journal['previous'] != journal['candidate'], 'REPAIR_JOURNAL_INVALID')
            require(current in (journal['previous'], journal['candidate'])
                    and (previous in (None, journal['previous']) or
                         (journal['phase'] == 'prepared' and current == journal['previous'] and pending is None))
                    and pending in (None, journal['candidate']), 'REPAIR_JOURNAL_CONFLICT')
            target = journal['previous'] if journal['phase'] == 'prepared' else journal['candidate']
            state = journal['phase'].upper() + '_JOURNAL'
        else:
            require(pending is None or (pending == current and previous is not None and previous != current), 'REPAIR_PENDING_AMBIGUOUS')
            target = current
            state = 'COMMITTED_PENDING' if pending else 'NO_PENDING_TRANSACTION'
        evidence = parse_json(capture('schema-evidence', evidence_path))
        require(isinstance(evidence, dict) and set(evidence) == {'schema','mode','activation_authorized','database_checked','status','checks'}, 'REPAIR_SCHEMA_EVIDENCE_INVALID')
        require(type(evidence['schema']) is int and evidence['schema'] == 1
                and evidence['mode'] == 'read-only' and evidence['status'] == 'PASS'
                and evidence['activation_authorized'] is False and evidence['database_checked'] is True,
                'REPAIR_SCHEMA_EVIDENCE_INVALID')
        checks = evidence['checks']
        require(isinstance(checks, dict) and {'release','database'} <= checks.keys()
                and all(isinstance(c,dict) and c.get('status') == 'PASS' for c in checks.values()), 'REPAIR_SCHEMA_EVIDENCE_INVALID')
        require(checks['release'] == {'status':'PASS','code':'RELEASE_VERIFIED','version':reviewed}, 'REPAIR_SCHEMA_RELEASE_MISMATCH')
        db = checks['database']
        require(set(db) == {'status','code','migration','runtime_state'}
                and db['code'] == 'DATABASE_READY' and type(db['migration']) is int
                and db['migration'] in (47,48) and db['runtime_state'] in w.QUIESCENT,
                'REPAIR_SCHEMA_EVIDENCE_INVALID')
        require(reviewed not in w.LEGACY_ROLLBACK, 'REPAIR_FENCED_CANDIDATE_REQUIRED')
        versions = {v for v in (current,previous,pending,reviewed) if v}
        if journal:
            versions.update((journal['previous'],journal['candidate']))
        for version in sorted(versions):
            release = root / 'releases' / version
            require(w.validate_release(release, version, role, legacy_rollback=version in w.LEGACY_ROLLBACK)['status'] == 'PASS', 'REPAIR_RELEASE_INTEGRITY_INVALID')
            capture('manifest-' + version, release / 'release-manifest.json', 32 * 1024**2)
        # A modern candidate must have the exact reviewed48 migration source;
        # filenames/modules alone cannot assert schema compatibility. Never import it.
        candidate_sql = capture('candidate-catalogue', root / 'releases' / reviewed / 'grid/migrations.py')
        trusted_sql = read_file(Path(__file__).resolve().parents[1] / 'grid/migrations.py')
        require(candidate_sql == trusted_sql, 'REPAIR_CANDIDATE_CATALOGUE_UNREVIEWED')
        # Catch cooperative changes while collecting evidence. This is not a
        # transaction or a licence to apply the plan after the mutex is released.
        for version in sorted(versions):
            require(w.validate_release(root / 'releases' / version, version, role, legacy_rollback=version in w.LEGACY_ROLLBACK)['status'] == 'PASS', 'REPAIR_RELEASE_EVIDENCE_CHANGED')
        require(all(read_file(path, limit, optional) == data for path,limit,optional,data in captured.values()), 'REPAIR_EVIDENCE_CHANGED')
        digest = hashlib.sha256(json.dumps({k:hashlib.sha256(v[3]).hexdigest() if v[3] is not None else None for k,v in captured.items()},sort_keys=True).encode()).hexdigest()
        result.update(status='PLAN_ONLY', code='OFFLINE_REPAIR_ASSESSED', transaction_state=state,
                      journal_target=target, reviewed_version=reviewed, observed_schema=db['migration'],
                      legacy_rollback_compatible=db['migration'] == 47,
                      current_is_historical=current in w.LEGACY_ROLLBACK,
                      journal_target_is_historical=target in w.LEGACY_ROLLBACK,
                      runtime_inventory='NOT_CHECKED_USE_POWERSHELL_WRAPPER',
                      evidence_kind='UNAUTHENTICATED_OFFLINE_SNAPSHOT', snapshot_sha256=digest,
                      blockers=['FRESH_DATABASE_AND_LEASE_EVIDENCE_REQUIRED',
                                'REVIEWED_OFFLINE_POINTER_REPAIR_NOT_IMPLEMENTED',
                                'NO_SERVICE_ACTIVATION_AUTHORIZED'],
                      review_steps=['Preserve journal, pointers, manifests and WAL.',
                                    'Review the journal-authoritative target without activating it.',
                                    'Review a separate fenced schema48-compatible pointer repair tool.',
                                    'Obtain fresh maintenance evidence and explicit authorization before any mutation.'])
    except Rejected as exc:
        result.update(status='BLOCKED', code=str(exc))
    except Exception:
        result.update(status='BLOCKED', code='REPAIR_EVIDENCE_UNAVAILABLE')
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--install-root', required=True, type=Path)
    p.add_argument('--reviewed-version', required=True)
    p.add_argument('--schema-evidence', required=True, type=Path)
    p.add_argument('--role', choices=('CONTROL','WORKER'), default='CONTROL')
    args = p.parse_args(argv)
    result = assess(args.install_root, args.reviewed_version, args.schema_evidence, args.role)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'PLAN_ONLY' else 2


if __name__ == '__main__':
    sys.exit(main())
