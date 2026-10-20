import unittest
from audit.integration_ci.evidence_manifest import CRITICAL, validate_manifest

SHA = "a" * 40

def manifest():
    return {"commit_sha": SHA, "required_workflows": sorted(CRITICAL),
            "source": "github-actions", "synthetic": False}

class EvidenceManifestTests(unittest.TestCase):
    def test_valid_metadata_not_readiness(self):
        self.assertEqual(validate_manifest(manifest(), SHA), [])
    def test_wrong_sha(self):
        m = manifest()
        m["commit_sha"] = "b" * 40
        self.assertTrue(validate_manifest(m, SHA))
    def test_missing_duplicate_and_bad_workflow(self):
        for changed in (sorted(CRITICAL)[:-1], sorted(CRITICAL) + [sorted(CRITICAL)[0]], [None]):
            with self.subTest(changed=changed):
                m = manifest()
                m["required_workflows"] = changed
                self.assertTrue(validate_manifest(m, SHA))
    def test_synthetic_source(self):
        for field, value in (("synthetic", True), ("synthetic", "false"), ("source", "manual")):
            m = manifest()
            m[field] = value
            self.assertTrue(validate_manifest(m, SHA))

if __name__ == "__main__":
    unittest.main()
