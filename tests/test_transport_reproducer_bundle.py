import copy
import hashlib
import unittest

from tools.transport_reproducer_bundle import validate_manifest, parse_manifest, select_profile


class ManifestTests(unittest.TestCase):
    def test_profile_selection_is_closed(self):
        self.assertEqual(select_profile([]), ('transport-input', 'integration/windows_transport_probe.py', 'TRANSPORT_INPUT_SHA256'))
        self.assertEqual(select_profile(['--pipe-prototype']), ('pipe-input', 'integration/windows_pipe_probe.py', 'PIPE_INPUT_SHA256'))
        for args in (['pipe-input'], ['--pipe-prototype', 'extra'], ['--pipe-prototype', '--pipe-prototype'], ['../pipe-input'], ['--driver=evil.py'], '--pipe-prototype', None):
            with self.subTest(args=args):
                with self.assertRaises(ValueError): select_profile(args)

    def setUp(self):
        self.head = 'a' * 40
        self.driver = b'import socket\n'
        self.pth = b'stdlib.zip\nDLLs\n'
        content = {'python.exe': b'exe', 'pythonw.exe': b'gui', 'python312.dll': b'dll',
                   'DLLs/_socket.pyd': b'pyd', 'stdlib.zip': b'zip',
                   'driver.py': self.driver, 'python._pth': self.pth,
                   'pythonw._pth': self.pth, 'python312._pth': self.pth}
        self.manifest = dict(Schema=1, Head=self.head, Run='1', Attempt='2', Python='3.12',
            Files={n: dict(Sha256=hashlib.sha256(b).hexdigest().upper(), Length=len(b)) for n, b in content.items()},
            Origins={n: 'git:' + self.head if n == 'driver.py' else 'fixed-isolated-paths' if n.endswith('._pth') else 'setup-python-stdlib' if n == 'stdlib.zip' else 'setup-python' for n in content})

    def check(self, manifest):
        return validate_manifest(manifest, self.head, '1', '2', self.driver)

    def test_closed_manifest(self):
        self.check(self.manifest)

    def test_rejects_mutations(self):
        mutations = [lambda m: m.update(Schema=True), lambda m: m.update(Extra=1),
            lambda m: m.update(Head='b'*40), lambda m: m['Files'].pop('python.exe'),
            lambda m: m['Files']['driver.py'].update(Length=True),
            lambda m: m['Files']['driver.py'].update(Length=-1),
            lambda m: m['Files']['driver.py'].update(Length=32*1024*1024+1),
            lambda m: m['Files']['driver.py'].update(Unexpected=1),
            lambda m: m['Files']['driver.py'].update(Sha256='a'*64),
            lambda m: m['Files']['python._pth'].update(Length=999),
            lambda m: m['Files']['pythonw._pth'].update(Sha256='A'*64),
            lambda m: m['Files']['python312._pth'].update(Sha256='A'*64),
            lambda m: m['Origins'].update({'driver.py': 'setup-python'}),
            lambda m: m['Origins'].update({'python.exe': True}),
            lambda m: m['Origins'].pop('stdlib.zip'),
            lambda m: m.update(Files=[]), lambda m: m.update(Origins=[]),
            lambda m: m.update(Python=False), lambda m: m.update(Run=True),
            lambda m: m['Files'].update({'Site/x.py': dict(Sha256='A'*64, Length=1)}),
            lambda m: m['Files'].update({'PYTHON.EXE': m['Files']['python.exe']}),
            lambda m: m['Files'].update({'DLLs/../x.dll': dict(Sha256='A'*64, Length=1)})]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                m = copy.deepcopy(self.manifest); mutate(m)
                with self.assertRaises(ValueError): self.check(m)

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ValueError): parse_manifest(b'{"Schema":1,"Schema":1}')
        with self.assertRaises(ValueError): parse_manifest(b'{"Files":{"x":{"Length":1,"Length":2}}}')

    def test_driver_pin_is_exact(self):
        with self.assertRaises(ValueError):
            validate_manifest(self.manifest, self.head, '1', '2', self.driver+b'\n')


if __name__ == '__main__': unittest.main()
