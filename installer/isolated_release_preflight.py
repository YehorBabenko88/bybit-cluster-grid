# Offline preflight delegates to the same modern validator used by commissioning.
# No target imports, credentials, HTTP or database checks.
import argparse
import json
from pathlib import Path
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from installer.windows_preflight import validate_release


def verify(root, sha, role):
    return {'schema': 1, 'scope': 'OFFLINE_RELEASE_INTEGRITY_ONLY',
            'activation_authorized': False, 'database_checked': False,
            'release': validate_release(root, sha, role)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-dir', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--role', choices=['CONTROL', 'WORKER'], required=True)
    args = parser.parse_args()
    result = verify(args.release_dir, args.commit, args.role)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['release']['status'] == 'PASS' else 2


if __name__ == '__main__':
    sys.exit(main())
