"""Fail-closed validation of an immutable three-repository commissioning manifest.

This does not fetch code, access hosts, run deployments or authorize trading.
"""
import argparse
import json
import re
from pathlib import Path

REPOSITORIES = {
    "grid": "YehorBabenko88/bybit-cluster-grid",
    "strattester": "YehorBabenko88/strattester",
    "terminan": "YehorBabenko88/Terminan",
}
SHA = re.compile(r"[0-9a-f]{40}\Z")


def validate(data):
    if not isinstance(data, dict) or set(data) != {"schema", "mode", "repositories"}:
        raise ValueError("manifest must contain only schema, mode and repositories")
    if type(data["schema"]) is not int or data["schema"] != 1:
        raise ValueError("unsupported manifest schema")
    if data["mode"] != "read-only":
        raise ValueError("only read-only commissioning is allowed")
    repos = data["repositories"]
    if not isinstance(repos, dict) or set(repos) != set(REPOSITORIES):
        raise ValueError("exactly grid, strattester and terminan must be pinned")
    for key, name in REPOSITORIES.items():
        entry = repos[key]
        if not isinstance(entry, dict) or set(entry) != {"repository", "commit"}:
            raise ValueError(f"{key}: expected repository and commit")
        if entry["repository"] != name:
            raise ValueError(f"{key}: unexpected repository")
        sha = entry["commit"]
        if not isinstance(sha, str) or not SHA.fullmatch(sha):
            raise ValueError(f"{key}: full lowercase 40-character commit required")
        if sha == "0" * 40:
            raise ValueError(f"{key}: placeholder SHA forbidden")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    validate(json.loads(args.manifest.read_text(encoding="utf-8")))
    print("Manifest structure valid. This does NOT prove commits exist or authorize deployment.")


if __name__ == "__main__":
    main()
