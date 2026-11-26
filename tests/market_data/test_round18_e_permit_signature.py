"""Cross-package ABI probe against real E types, never synthetic permits.

This does NOT issue a permit, touch SQL, or claim native B/C/E acceptance.
Missing protected E installation is a SKIP and MUST NOT count as a PASS.
"""
import importlib
import inspect
import unittest


ARGS={
    "executor","operation_id","content_id","package_identity",
    "entrypoint","backend_pid","backend_start","symbol","start_ms",
    "fingerprint","owner","namespace","generation","token","epoch",
}
ISSUER_ARGS={
    "executor","operation_id","content_id","package_identity",
    "entrypoint","symbol","start_ms","fingerprint",
}


class Round18ExactEPermitContract(unittest.TestCase):
    def test_real_e_issuer_and_same_thread_permit_signatures(self):
        try:
            e=importlib.import_module("unified_system.lab_writer_authority")
        except ImportError:
            self.skipTest("NO_PROTECTED_E_PACKAGE_INSTALLED")
        self.assertEqual(
            set(inspect.signature(e.LabWriterOperationPermit.require_current).parameters)
            -{"self"},ARGS)
        self.assertEqual(
            set(inspect.signature(e.LabWriterAuthority.issue_operation_permit).parameters)
            -{"self"},ISSUER_ARGS)
        self.assertEqual(
            set(inspect.signature(e.LabWriterOperationPermit.consume).parameters),
            {"self","kwargs"})
        # E's real type/issuer are probed. No constructor bypass, no fake
        # capability and no success claim for a SQL transaction.


if __name__=="__main__":
    unittest.main()
