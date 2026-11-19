"""Record installed Grid wheel evidence for the release coordinator."""

import argparse
import ast
import hashlib
import importlib
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


def check_imports(module, source, allowed):
    for node in ast.walk(ast.parse(source, filename=module)):
        names = []
        if isinstance(node, ast.Import):
            names = [item.name for item in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level == 1:
                names = (["grid." + node.module] if node.module else
                         ["grid." + item.name for item in node.names])
            elif node.level:
                raise SystemExit(f"unexpected relative import in {module}")
            else:
                names = ([node.module] if node.module != "grid" else
                         ["grid." + item.name for item in node.names])
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id == "__import__"):
            if (len(node.args) != 1 or node.keywords or not isinstance(node.args[0], ast.Constant)
                    or not isinstance(node.args[0].value, str)):
                raise SystemExit(f"unresolved dynamic import in {module}")
            names = [node.args[0].value]
        for name in names:
            root, _, child = name.partition(".")
            if root == "grid":
                if child and child not in allowed:
                    raise SystemExit(f"{module} imports unpackaged Grid module {name}")
            elif root not in (sys.stdlib_module_names - {"importlib"}) | {"aiohttp", "psycopg"}:
                raise SystemExit(f"{module} imports unexpected dependency {name}")


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
    allowed = set(Path(__file__).resolve().parents[1]
                  .joinpath("market-wheel-modules.txt").read_text(encoding="utf-8").split())
    expected_files = {f"grid/{name}.py" for name in allowed} | {"grid/schema.sql"}
    distribution = metadata.distribution(PACKAGE)
    entry, = distribution.entry_points.select(group="console_scripts", name="grid-market-readonly")
    if entry.value != ENTRY_POINT:
        raise SystemExit("unexpected Grid entry point")
    installed_files = {path.as_posix() for path in distribution.files
                       if path.parts[0] == "grid" and path.suffix != ".pyc"}
    legacy = sorted(name for name in expected_files | installed_files
                    if Path(name).name.startswith(LEGACY_PREFIXES) or Path(name).name in LEGACY_FILES)
    if legacy or installed_files != expected_files:
        raise SystemExit(f"unexpected Grid package files: {sorted(installed_files ^ expected_files)}; legacy: {legacy}")
    with ZipFile(wheel) as archive:
        payload = [name for name in archive.namelist()
                   if not name.split("/", 1)[0].endswith(".dist-info")]
        if sorted(payload) != sorted(expected_files):
            raise SystemExit("unexpected files in Grid wheel")
        for name in sorted(expected_files):
            source = archive.read(name)
            if source != Path(distribution.locate_file(name)).read_bytes():
                raise SystemExit(f"installed Grid file differs from wheel: {name}")
            if name.endswith(".py"):
                check_imports(name, source, allowed)

    for module in sorted(allowed):
        name = "grid" if module == "__init__" else f"grid.{module}"
        loaded = importlib.import_module(name)
        if Path(loaded.__file__).resolve() != Path(distribution.locate_file(f"grid/{module}.py")).resolve():
            raise SystemExit(f"{name} did not load from the installed package")
    from grid import terminan_gateway

    if entry.load() is not terminan_gateway.main:
        raise SystemExit("unexpected installed Gateway callable")
    capabilities = terminan_gateway.snapshot("/internal/v1/capabilities")
    if capabilities.get("read_only") is not True or capabilities.get("api_version") != {"major": 1, "minor": 0}:
        raise SystemExit("unexpected Grid read-only capability contract")
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
        "installed_grid_files": sorted(installed_files),
        "legacy_modules_detected": legacy,
        "release_status": "NO_GO",
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Grid wheel verified on Python {sys.version.split()[0]}; {len(legacy)} legacy modules detected.")


if __name__ == "__main__":
    main()
