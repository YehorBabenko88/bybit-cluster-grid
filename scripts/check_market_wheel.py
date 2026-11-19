"""Record installed Grid wheel evidence for the release coordinator."""

import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
from zipfile import ZipFile


PACKAGE = "unified-grid-market-data"
ENTRY_POINT = "grid.terminan_gateway:main"
LEGACY_PREFIXES = ("strategy_", "scientific_", "historical_experiment_")
LEGACY_FILES = {"position_sizing_research.py", "markov_strategy_context.py"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--head", required=True)
    parser.add_argument("--wheel-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if head != args.head:
        raise SystemExit("Grid checkout does not match expected HEAD")
    wheels = sorted(args.wheel_dir.glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit("expected exactly one Grid wheel")
    wheel = wheels[0]
    distribution = metadata.distribution(PACKAGE)
    entry, = distribution.entry_points.select(group="console_scripts", name="grid-market-readonly")
    if entry.value != ENTRY_POINT:
        raise SystemExit("unexpected Grid entry point")
    entry_function = entry.load()

    from grid import terminan_gateway

    installed = Path(distribution.locate_file("grid/terminan_gateway.py")).resolve()
    if Path(terminan_gateway.__file__).resolve() != installed or entry_function is not terminan_gateway.main:
        raise SystemExit("Grid entry point did not load from the installed package")
    capabilities = terminan_gateway.snapshot("/internal/v1/capabilities")
    if capabilities.get("read_only") is not True or capabilities.get("api_version") != {"major": 1, "minor": 0}:
        raise SystemExit("unexpected Grid read-only capability contract")

    modules = sorted(path.as_posix() for path in distribution.files
                     if path.parts[0] == "grid" and path.suffix == ".py")
    with ZipFile(wheel) as archive:
        wheel_modules = sorted(name for name in archive.namelist()
                               if name.startswith("grid/") and name.endswith(".py"))
        if modules != wheel_modules or archive.read("grid/terminan_gateway.py") != installed.read_bytes():
            raise SystemExit("installed Grid modules do not match the supplied wheel")
    legacy = [module for module in modules
              if Path(module).name.startswith(LEGACY_PREFIXES) or Path(module).name in LEGACY_FILES]
    with wheel.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    report = {
        "schema": "grid.installed-wheel-evidence.v1",
        "source_head": head,
        "platform": platform.system(),
        "python": platform.python_version(),
        "package": PACKAGE,
        "version": distribution.version,
        "requires_python": distribution.metadata["Requires-Python"],
        "requires_dist": sorted(distribution.requires or ()),
        "wheel": wheel.name,
        "wheel_sha256": digest,
        "entry_point": ENTRY_POINT,
        "market_api_version": capabilities["api_version"],
        "source_status": capabilities["status"],
        "legacy_modules_detected": legacy,
        "release_status": "NO_GO",
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Grid wheel verified on Python {sys.version.split()[0]}; {len(legacy)} legacy modules detected.")


if __name__ == "__main__":
    main()
