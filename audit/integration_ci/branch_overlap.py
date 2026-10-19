"""Read-only changed-path collision analysis for parallel audit branches."""
from collections import defaultdict

def collisions(branch_files):
    """Return only paths changed in more than one branch; no git writes."""
    owners = defaultdict(set)
    for branch, paths in branch_files.items():
        for path in paths:
            if (not isinstance(path, str) or not path or "\\" in path or ":" in path
                    or "\x00" in path or any(part in ("", ".", "..") for part in path.split("/"))):
                raise ValueError("unsafe or invalid repository path")
            owners[path].add(branch)
    return {path: sorted(branches) for path, branches in sorted(owners.items()) if len(branches) > 1}

def audit(branch_files):
    conflicts = collisions(branch_files)
    return {"status": "BLOCKED" if conflicts else "NO_PATH_COLLISIONS",
            "conflicts": conflicts,
            "note": "No path collision is not proof of semantic compatibility or readiness"}
