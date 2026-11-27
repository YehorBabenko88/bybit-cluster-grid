"""Validate the published v2 DTO schema against actual canonical producer output."""
import copy
import json
import runpy
import unittest
from pathlib import Path
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from market_data_v2.read_api import qualified_snapshot
from market_data_v2.qualified_read_contract import ProvenanceReadError

_ROOT=Path(__file__).resolve().parents[2]
_SCHEMA=json.loads((_ROOT/"docs/contracts/qualified-read-envelope-v1.schema.json").read_text(encoding="utf-8"))
_NSPACE=runpy.run_path(str(_ROOT/"scripts/qualified_read_v2_fixture.py"))


class QualifiedReadV2SchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Draft202012Validator.check_schema(_SCHEMA)
        cls.validator=Draft202012Validator(_SCHEMA,format_checker=Draft202012Validator.FORMAT_CHECKER)

    def test_canonical_producer_fixture_qualifies_without_paper_authority(self):
        fixture=_NSPACE["build_fixture"]()
        self.assertTrue(fixture["synthetic_only"])
        self.assertEqual(fixture["source_record"]["producer"],"market_data")
        self.validator.validate(fixture["qualified_read"])
        self.assertEqual(fixture["qualified_read"]["status"],"PARTIAL")
        self.assertFalse(fixture["qualified_read"]["paper_admitted"])

    def test_explicit_empty_source_conforms_unavailable(self):
        envelope=qualified_snapshot("BTCUSDT",1,reader=lambda *_:[],now_ms=1800000120000)
        self.validator.validate(envelope)
        self.assertEqual(envelope["status"],"UNAVAILABLE")

    def test_no_available_or_trading_promotions(self):
        fixture=_NSPACE["build_fixture"]()
        baseline=fixture["qualified_read"]
        changes=(
            ("status","AVAILABLE"),("paper_admitted",True),
            ("trading_authorized",True),("execution_authority",True),
            ("immutable",True),("source_authenticity","VERIFIED"),
            ("storage_immutability","ROLE_AND_TRIGGER_GUARDED_LAB_ONLY"),
            ("api_version",{"major":1,"minor":1}),
            ("producer","bybit-cluster-grid"),
            ("reason","FRESHNESS_WATERMARK_EXPIRED"),
        )
        for field,forged in changes:
            envelope=copy.deepcopy(baseline)
            envelope[field]=forged
            with self.subTest(field=field),self.assertRaises(ValidationError):
                self.validator.validate(envelope)

    def test_unknown_columns_and_unavailable_with_rows_rejected(self):
        baseline=_NSPACE["build_fixture"]()["qualified_read"]
        poisoned=copy.deepcopy(baseline)
        poisoned["signed_storage_receipt"]={"claim":True}
        with self.assertRaises(ValidationError):
            self.validator.validate(poisoned)
        missing=qualified_snapshot("BTCUSDT",1,reader=lambda *_:[],now_ms=1800000120000)
        missing["rows"]=[{"forged":True}]
        with self.assertRaises(ValidationError):
            self.validator.validate(missing)

if __name__=="__main__":
    unittest.main()
