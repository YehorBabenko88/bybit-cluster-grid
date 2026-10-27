"""Build a stock CPython transport closure on disposable hosted Windows only."""
import hashlib
import io
import json
import os
import re
import socket
import subprocess
import sys
import zipfile
from pathlib import Path

from tools.check_ddl_free_ci import verify_checkout
from tools.python_containment_bundle import hosted, regular, relative, pe_subsystem

ROOT = Path(__file__).resolve().parents[1]
PTH = b'stdlib.zip\nDLLs\n'


def need(ok):
    if not ok:
        raise ValueError('TRANSPORT_BUNDLE_REFUSED')


def select_profile(args):
    """Select one explicit fixed experiment; accepts no paths or extra flags."""
    need(type(args) is list and all(type(arg) is str for arg in args))
    if args == []:
        return ('transport-input', 'integration/windows_transport_probe.py', 'TRANSPORT_INPUT_SHA256')
    if args == ['--pipe-prototype']:
        return ('pipe-input', 'integration/windows_pipe_probe.py', 'PIPE_INPUT_SHA256')
    raise ValueError('TRANSPORT_BUNDLE_REFUSED')


def parse_manifest(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def validate_manifest(manifest, head, run, attempt, driver):
    """Pure, closed manifest policy; does not read files or launch processes."""
    need(type(manifest) is dict and set(manifest) == {'Schema', 'Head', 'Run', 'Attempt', 'Python', 'Files', 'Origins'})
    need(type(manifest['Schema']) is int and manifest['Schema'] == 1)
    need(type(head) is str and re.fullmatch('[0-9a-f]{40}', head) is not None)
    for value in (run, attempt):
        need(type(value) is str and re.fullmatch('[1-9][0-9]{0,19}', value) is not None)
    need(manifest['Head'] == head and manifest['Run'] == run and manifest['Attempt'] == attempt)
    need(type(manifest['Python']) is str and 0 < len(manifest['Python']) <= 4096)
    files, origins = manifest['Files'], manifest['Origins']
    need(type(files) is dict and type(origins) is dict and 0 < len(files) <= 20000 and set(files) == set(origins))
    need(type(driver) is bytes and 0 < len(driver) <= 32*1024*1024)
    folded = set(); total = 0
    for name, pin in files.items():
        relative(name)
        need(name.casefold() not in folded); folded.add(name.casefold())
        need(type(pin) is dict and set(pin) == {'Sha256', 'Length'})
        need(type(pin['Length']) is int and 0 <= pin['Length'] <= 32*1024*1024)
        need(type(pin['Sha256']) is str and re.fullmatch('[0-9A-F]{64}', pin['Sha256']) is not None)
        total += pin['Length']; need(total <= 512*1024*1024)
        if name == 'driver.py':
            origin = 'git:' + head; expected = driver
        elif name in ('python._pth', 'pythonw._pth') or re.fullmatch(r'python3[0-9]+\._pth', name):
            origin = 'fixed-isolated-paths'; expected = PTH
        elif name == 'stdlib.zip':
            origin = 'setup-python-stdlib'; expected = None
        else:
            need(name in ('python.exe', 'pythonw.exe') or re.fullmatch(r'[A-Za-z0-9_. ()-]+\.dll', name) is not None or re.fullmatch(r'DLLs/[A-Za-z0-9_. ()-]+\.(pyd|dll)', name) is not None)
            origin = 'setup-python'; expected = None
        need(type(origins[name]) is str and origins[name] == origin)
        if expected is not None:
            need(pin == dict(Sha256=hashlib.sha256(expected).hexdigest().upper(), Length=len(expected)))
    need({'python.exe', 'pythonw.exe', 'stdlib.zip', 'driver.py', 'python._pth', 'pythonw._pth'} <= set(files))
    need(any(re.fullmatch(r'python3[0-9]+\._pth', n) for n in files))
    need(any(n.startswith('DLLs/') and n.endswith('.pyd') for n in files))
    need(any(re.fullmatch(r'python3[0-9]+\.dll', n) for n in files))
    return manifest


def build(args=None):
    directory, driver_path, digest_variable = select_profile([] if args is None else args)
    hosted()
    need(sys.platform == 'win32' and os.environ.get('COMPUTERNAME', '').upper() not in ('PC4', 'LS5') and socket.gethostname().upper() not in ('PC4', 'LS5'))
    head = os.environ['EXACT_HEAD_SHA']; verify_checkout(ROOT, head)
    driver = subprocess.check_output(['git', 'show', head + ':' + driver_path], cwd=ROOT)
    output = ROOT/directory; output.mkdir()
    files = {}; origins = {}; folded = set(); total = 0

    def add(name, content, origin):
        nonlocal total
        relative(name)
        need(name.casefold() not in folded and len(files) < 20000 and type(content) is bytes and len(content) <= 32*1024*1024)
        total += len(content); need(total <= 512*1024*1024); folded.add(name.casefold())
        path = output/name; path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(content)
        files[name] = dict(Sha256=hashlib.sha256(content).hexdigest().upper(), Length=len(content)); origins[name] = origin

    base = Path(sys.base_prefix)
    add('python.exe', regular(base/'python.exe'), 'setup-python')
    gui = regular(base/'pythonw.exe'); need(pe_subsystem(gui) == 2)
    add('pythonw.exe', gui, 'setup-python')
    for path in sorted(base.glob('*.dll')):
        add(path.name, regular(path), 'setup-python')
    for path in sorted((base/'DLLs').glob('*')):
        if path.is_file() and path.suffix.lower() in ('.pyd', '.dll'):
            add('DLLs/'+path.name, regular(path), 'setup-python')
    std = io.BytesIO()
    with zipfile.ZipFile(std, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((base/'Lib').rglob('*')):
            rel = path.relative_to(base/'Lib')
            if any(p in ('site-packages', '__pycache__', 'test', 'tests', 'tkinter', 'idlelib', 'ensurepip', 'turtledemo') for p in rel.parts):
                continue
            if path.is_file() and path.suffix == '.py':
                archive.writestr(zipfile.ZipInfo(relative(rel.as_posix())), regular(path), compress_type=zipfile.ZIP_DEFLATED)
    add('stdlib.zip', std.getvalue(), 'setup-python-stdlib')
    add('driver.py', driver, 'git:'+head)
    for name in ('python._pth', 'pythonw._pth', f'python{sys.version_info.major}{sys.version_info.minor}._pth'):
        add(name, PTH, 'fixed-isolated-paths')
    manifest = dict(Schema=1, Head=head, Run=os.environ['GITHUB_RUN_ID'], Attempt=os.environ['GITHUB_RUN_ATTEMPT'], Python=sys.version, Files=files, Origins=origins)
    validate_manifest(manifest, head, manifest['Run'], manifest['Attempt'], driver)
    raw = json.dumps(manifest, sort_keys=True).encode()
    with (output/'manifest.json').open('xb') as stream:
        stream.write(raw)
    verify_checkout(ROOT, head)
    digest = hashlib.sha256(raw).hexdigest()
    print(json.dumps(dict(head=head, files=len(files), bytes=total, manifest_sha256=digest)))
    with open(os.environ['GITHUB_ENV'], 'a', encoding='utf-8') as stream:
        stream.write(digest_variable+'='+digest+'\n')


if __name__ == '__main__':
    build(sys.argv[1:])
