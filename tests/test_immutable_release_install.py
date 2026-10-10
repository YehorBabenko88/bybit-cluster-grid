import pathlib
import tempfile
import unittest
import zipfile

from grid.update_manager import install_release


def package(path, payload):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("run_worker.py", payload)


class ImmutableReleaseTests(unittest.TestCase):
    def test_existing_release_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            archive = root / "release.zip"
            package(archive, "new")
            target = root / "releases" / "v1"
            target.mkdir(parents=True)
            (target / "run_worker.py").write_text("old")
            self.assertEqual(install_release(archive, "v1", root), target)
            self.assertEqual((target / "run_worker.py").read_text(), "old")
            self.assertFalse((root / "releases" / "v1.replaced").exists())

    def test_recovers_interrupted_legacy_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            archive = root / "release.zip"
            package(archive, "new")
            replaced = root / "releases" / "v1.replaced"
            replaced.mkdir(parents=True)
            (replaced / "run_worker.py").write_text("recover")
            target = install_release(archive, "v1", root)
            self.assertEqual((target / "run_worker.py").read_text(), "recover")

    def test_rejects_unrunnable_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            archive = root / "release.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("README.txt", "not runnable")
            with self.assertRaises(ValueError):
                install_release(archive, "v1", root)
            self.assertFalse((root / "releases" / "v1").exists())

    def test_rejects_path_traversal_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            archive = root / "release.zip"
            package(archive, "new")
            for version in ("../outside", "..", "x\\\\y", "x.staging"):
                with self.subTest(version=version):
                    with self.assertRaises(ValueError):
                        install_release(archive, version, root)


if __name__ == "__main__":
    unittest.main()
