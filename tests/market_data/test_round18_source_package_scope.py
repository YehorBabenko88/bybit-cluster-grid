"""Source-only scope guard; not installed-wheel qualification or Root admission."""
import pathlib
import tomllib
import unittest


ROOT=pathlib.Path(__file__).resolve().parents[2]
EXPECTED={
    "grid.canonical_lab_continuous_collector",
    "grid.c_lab_journal_adapter",
    "grid.canonical_lab_fenced_writer",
    "grid.c_async_fenced_writer",
}


class Round18SourcePackageScope(unittest.TestCase):
    def test_only_four_existing_grid_runtime_modules_selected(self):
        config=tomllib.loads((ROOT/"pyproject.toml").read_text(encoding="utf-8"))
        tools=config["tool"]["setuptools"]
        self.assertEqual(set(tools["packages"]),{"market_data","market_data_v2"})
        self.assertEqual(set(tools["py-modules"]),EXPECTED)
        self.assertEqual(len(tools["py-modules"]),len(EXPECTED))
        self.assertEqual(config["project"]["name"],"market-data")
        for dotted in EXPECTED:
            self.assertTrue((ROOT/("grid/"+dotted.split(".")[1]+".py")).is_file())
        self.assertTrue((ROOT/"grid/__init__.py").is_file())

    def test_single_existing_wheel_not_second_grid_distribution(self):
        config=tomllib.loads((ROOT/"pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(config["build-system"]["build-backend"],"setuptools.build_meta")
        self.assertEqual(
            config["project"]["scripts"]["market-data"],"market_data.cli:main")
        self.assertNotIn("grid",config["tool"]["setuptools"]["packages"])


if __name__=="__main__":
    unittest.main()
