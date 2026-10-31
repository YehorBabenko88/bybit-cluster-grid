import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('annotations',Path(__file__).parents[1]/'scripts/annotate_test_failures.py')
a=importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class JunitAnnotationTests(unittest.TestCase):
    def test_emits_only_first_ten_failed_ids_and_message_attribute(self):
        raw=('<testsuite>'+''.join(f'<testcase classname="suite" name="test_{i}"><failure message="reason{i}">PRIVATE_TRACE</failure></testcase>' for i in range(12))+'<testcase name="passing"/></testsuite>').encode()
        lines=a.annotations(raw)
        self.assertEqual(len(lines),10)
        self.assertIn('suite.test_0: reason0',lines[0])
        self.assertNotIn('PRIVATE_TRACE',''.join(lines))
        self.assertNotIn('test_10',''.join(lines))

    def test_redacts_credentials_and_escapes_command_line_injection(self):
        raw=b'<testsuite><testcase name="test&#10;::error::injected"><failure message="Bearer abc.DEF password=secret https://user:pass@example.invalid/path api_key: xyz token=hidden&#13;&#10;100%"/></testcase></testsuite>'
        line=a.annotations(raw)[0]
        for secret in ('abc.DEF','secret','user:pass','xyz','hidden'):
            self.assertNotIn(secret,line)
        self.assertNotIn('\n',line)
        self.assertNotIn('\r',line)
        self.assertIn('%0A',line)
        self.assertIn('100%25',line)

    def test_bounds_messages_and_rejects_entities_or_oversized_documents(self):
        raw=('<testsuite><testcase name="x"><error message="'+'x'*2000+'"/></testcase></testsuite>').encode()
        self.assertLessEqual(len(a.annotations(raw)[0]),750)
        for bad in (b'<!DOCTYPE x [<!ENTITY e "test">]><testsuite/>',b'x'*a.MAX_BYTES,b'<testsuite>',
                    '<!DOCTYPE x [<!ENTITY e "test">]><testsuite/>'.encode('utf-16')):
            with self.assertRaises(ValueError):a.annotations(bad)

    def test_pass_only_document_produces_no_annotations(self):
        self.assertEqual(a.annotations(b'<testsuite><testcase name="test_ok"/></testsuite>'),[])

    def test_cli_diagnostics_do_not_relabel_failed_suite_or_disclose_bad_input(self):
        import contextlib
        import io
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'PRIVATE_INPUT.xml'
            path.write_bytes(b'<testsuite><testcase name="test_failed"><failure message="assertion"/></testcase></testsuite>')
            output=io.StringIO()
            with contextlib.redirect_stdout(output):status=a.main([str(path)])
            self.assertEqual(status,0)  # Parsing diagnostics is not a suite PASS.
            self.assertIn('::error::test_failed: assertion',output.getvalue())
            path.write_bytes(b'PRIVATE_MALFORMED_INPUT')
            output=io.StringIO()
            with contextlib.redirect_stdout(output):status=a.main([str(path)])
            self.assertEqual(status,1)
            self.assertEqual(output.getvalue(),'::warning::JUNIT_DIAGNOSTICS_UNAVAILABLE\n')
