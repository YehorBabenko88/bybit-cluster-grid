import unittest

from installer.commissioning_manifest import validate


def manifest():
    return {
        "schema": 1,
        "mode": "read-only",
        "repositories": {
            "grid": {"repository": "YehorBabenko88/bybit-cluster-grid", "commit": "a" * 40},
            "strattester": {"repository": "YehorBabenko88/strattester", "commit": "b" * 40},
            "terminan": {"repository": "YehorBabenko88/Terminan", "commit": "c" * 40},
        },
    }


class CommissioningManifestTests(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(validate(manifest()))

    def test_missing_repo(self):
        x = manifest()
        del x["repositories"]["terminan"]
        with self.assertRaises(ValueError):
            validate(x)

    def test_branch_not_sha(self):
        x = manifest()
        x["repositories"]["grid"]["commit"] = "main"
        with self.assertRaises(ValueError):
            validate(x)

    def test_wrong_repo(self):
        x = manifest()
        x["repositories"]["grid"]["repository"] = "attacker/grid"
        with self.assertRaises(ValueError):
            validate(x)

    def test_trading_mode(self):
        x = manifest()
        x["mode"] = "live"
        with self.assertRaises(ValueError):
            validate(x)

    def test_placeholder_sha(self):
        x = manifest()
        x["repositories"]["grid"]["commit"] = "0" * 40
        with self.assertRaises(ValueError):
            validate(x)

    def test_schema_bool(self):
        x = manifest()
        x["schema"] = True
        with self.assertRaises(ValueError):
            validate(x)

    def test_extra_field(self):
        x = manifest()
        x["trade_enabled"] = True
        with self.assertRaises(ValueError):
            validate(x)


if __name__ == "__main__":
    unittest.main()
