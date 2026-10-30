import copy
import unittest
from grid.provenance import digest
from grid.history_export_v11 import export_records_v11, read_postgres_v11
from test_history_export import fixture


class TimedExport(unittest.TestCase):
    def test_source_failure_is_normalized_and_no_result_returned(self):
        class Failed:
            def cursor(self):raise RuntimeError('fixture driver details')
        r,q,t=fixture()
        with self.assertRaisesRegex(ValueError,'SOURCE_READ_UNAVAILABLE'):
            read_postgres_v11(Failed(),q,t)

    def test_preserves_clock_and_stable_content_identity(self):
        r,q,t=fixture();a=export_records_v11(r,q,t)
        self.assertEqual(a['schema'],'grid.history.v1.1')
        self.assertEqual(a['rows'][0]['watermark_ms'],60000)
        self.assertEqual(a['rows'][0]['source_receipt_hash'],t['receipt_pins'][r[0]['dataset_fingerprint']])
        self.assertEqual(a['watermark_ms'],q['end_ms'])
        self.assertEqual(a['rows'][0]['source_event_start_ms'],r[0]['source_event_start_ms'])
        self.assertEqual(a['rows'][0]['source_event_end_ms'],r[0]['source_event_end_ms'])
        b=export_records_v11(r,{**q,'as_of_ms':q['end_ms']+1000},t)
        self.assertEqual(a['dataset_id'],b['dataset_id'])
        self.assertNotEqual(a['dataset_fingerprint'],b['dataset_fingerprint'])
        self.assertEqual(a['dataset_fingerprint'],digest({k:v for k,v in a.items() if k!='dataset_fingerprint'}))

    def test_watermark_cannot_postdate_first_availability(self):
        r,q,t=fixture();fp=r[0]['dataset_fingerprint']
        t['receipts'][fp]['watermark_ms']=120000
        t['receipt_pins'][fp]=digest(t['receipts'][fp])
        with self.assertRaises(ValueError):export_records_v11(r,q,t)

    def test_no_missing_or_boolean_clock_or_changed_receipt(self):
        for value in (None,True,59999,999999999):
            r,q,t=fixture();fp=r[0]['dataset_fingerprint']
            t['receipts'][fp]['watermark_ms']=value;t['receipt_pins'][fp]=digest(t['receipts'][fp])
            with self.subTest(value=value),self.assertRaises(ValueError):export_records_v11(r,q,t)

if __name__=='__main__':unittest.main()
