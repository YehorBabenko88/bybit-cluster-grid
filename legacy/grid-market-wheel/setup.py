"""Build the reusable market-data wheel from the existing Grid source."""

import hashlib
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

MODULE_FILE = Path(__file__).with_name("market-wheel-modules.txt")
MODULES = MODULE_FILE.read_bytes()


class MarketWheelBuild(build_py):
    def find_package_modules(self, package, package_dir):
        allowed = set(MODULES.decode("utf-8").split())
        return [item for item in super().find_package_modules(package, package_dir)
                if package == "grid" and item[1] in allowed]


setup(cmdclass={"build_py": MarketWheelBuild},
      options={"build": {"build_base": f"build/market-wheel-{hashlib.sha256(MODULES).hexdigest()[:12]}"}})
