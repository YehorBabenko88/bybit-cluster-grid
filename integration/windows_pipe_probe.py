"""Hosted-only one-way FIXED_PING child. No Grid, sockets, broker, or replies.

Native APIs are imported and called only after the native-child scope guard.
Neither a matching frame nor a numeric PID establishes owner authority or a
binding to the full process lifetime. The parent retains those responsibilities.
"""
import hashlib
import json
import os
import pathlib
import sys

# Deliberately self-contained: the staged driver cannot import sibling source.
# This fixed grammar is checked against the separate offline validator in tests.
MAX_PAYLOAD = 512

def need(ok):
    if not ok: raise ValueError('PIPE_PROBE_REFUSED')

def hex_text(value, length):
    return type(value) is str and len(value) == length and all(c in '0123456789abcdef' for c in value)

def context(value):
    need(type(value) is dict and set(value) == {'head', 'run_id', 'attempt', 'nonce', 'pid'})
    need(hex_text(value['head'], 40) and hex_text(value['nonce'], 32))
    for key in ('run_id', 'attempt'):
        text = value[key]
        need(type(text) is str and 1 <= len(text) <= (20 if key == 'run_id' else 10) and
             text[0] != '0' and all(c in '0123456789' for c in text))
    need(type(value['pid']) is int and 0 < value['pid'] < 2**32)
    return dict(value)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode('ascii')

def parse_json(raw, bound):
    need(type(raw) is bytes and 0 < len(raw) <= bound)
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result); result[key] = value
        return result
    def constant(_): raise ValueError('PIPE_NONFINITE_REFUSED')
    try:
        return json.loads(raw.decode('ascii'), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, RecursionError): raise ValueError('PIPE_JSON_REFUSED') from None

def encode_ping(expected):
    payload = canonical(dict(schema=1, verb='ping', **context(expected)))
    need(len(payload) <= MAX_PAYLOAD)
    return len(payload).to_bytes(4, 'little') + payload

def validate_config(value):
    need(type(value) is dict and set(value) ==
         {'schema', 'head', 'run_id', 'attempt', 'nonce', 'parent_pid', 'canary'})
    need(type(value['schema']) is int and value['schema'] == 1)
    context(dict(head=value['head'], run_id=value['run_id'], attempt=value['attempt'],
                 nonce=value['nonce'], pid=value['parent_pid']))
    path = value['canary']
    need(type(path) is str and 3 < len(path) <= 260 and path.isascii())
    p = pathlib.PureWindowsPath(path)
    need(len(p.drive) == 2 and p.drive[0].isalpha() and p.drive[1] == ':' and p.is_absolute())
    need(all(c.isalnum() or c in ':\\/_. -' for c in path) and ':' not in path[2:])
    parts = path.replace('\\', '/')[3:].split('/')
    need(all(part and part not in ('.', '..') and part == part.strip() and
             not part.endswith(('.', ' ')) and part.split('.')[0].upper() not in
             {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(i) for i in range(1,10)),
              *('LPT'+str(i) for i in range(1,10))} for part in parts))
    return dict(value)

def parse_config(raw):
    return validate_config(parse_json(raw, 4096))

def native_scope(root, host, args, platform, isolated):
    need(platform == 'win32' and isolated is True and args == ['--native-child'])
    p = pathlib.PureWindowsPath(root)
    need(len(p.drive) == 2 and p.drive[0].isascii() and p.drive[0].isalpha() and p.drive[1] == ':')
    need(p.parent.name == 'AC' and p.parent.parent.parent.name == 'Packages')
    def guid(value):
        return len(value) == 36 and [len(x) for x in value.split('-')] == [8,4,4,4,12] and hex_text(value.replace('-', ''), 32)
    need(p.name.startswith('python-') and guid(p.name[7:]) and
         p.parent.parent.name.startswith('g1-fixture-') and guid(p.parent.parent.name[11:]))
    alias = host.split('.')[0].upper().replace('-', '').replace('_', '')
    need(type(host) is str and bool(alias))
    need(not any(alias.startswith(prefix) and alias[len(prefix):].isdigit() and
                 int(alias[len(prefix):]) == number for prefix, number in (('LS',5), ('PC',4))))

def closed_environment(environment):
    allowed = {'systemroot', 'windir', 'localappdata', 'userprofile', 'temp', 'tmp', 'programdata'}
    need(all(type(key) is str and key.lower() in allowed and type(value) is str
             for key, value in environment.items()))
    need(any(key.lower() == 'systemroot' and value for key, value in environment.items()))

def denial_fact(opened, error):
    need(type(opened) is bool and opened is False and type(error) is int and error == 5)
    return dict(opened=False, winerror=5, status='OBSERVED')

def require_written(ok, written, expected):
    need(type(ok) is bool and ok is True and type(written) is int and
         type(expected) is int and 4 < expected <= MAX_PAYLOAD+4 and written == expected)

ROOT = pathlib.Path(__file__).resolve().parent


class ProbeFailure(ValueError):
    def __init__(self, reason, opened=None, winerror=None):
        super().__init__('PIPE_PROBE_OPERATION_REFUSED')
        self.reason = reason; self.opened = opened; self.winerror = winerror


STAGES = {'PROFILE_GUARD', 'EXECUTABLE_GUARD', 'IMPORT_PATH_GUARD', 'NATIVE_HOST',
          'ENVIRONMENT_GUARD', 'CONFIG_READ', 'CONFIG_VALIDATE', 'CANARY_SCOPE',
          'MODULE_GUARD', 'NATIVE_SETUP', 'PIPE_HANDLE', 'PIPE_READ',
          'PARENT_PROCESS_READ', 'FOREIGN_CANARY_READ', 'FRAME_WRITE', 'RESULT_WRITE'}
REASONS = {'DENIAL_NOT_PROVEN_PIPE_READ', 'DENIAL_NOT_PROVEN_PARENT_PROCESS_READ',
           'DENIAL_NOT_PROVEN_FOREIGN_CANARY_READ', 'FRAME_WRITE_INCOMPLETE'}


def safe_integer(value):
    return value if type(value) is int and -(2**31) <= value < 2**32 else None


def failure_result(stage, error):
    """Fixed vocabulary only: never serialize messages, paths, or environment."""
    reason = 'UNEXPECTED_EXCEPTION'
    if isinstance(error, ProbeFailure) and error.reason in REASONS: reason = error.reason
    elif isinstance(error, OSError): reason = 'OS_ERROR'
    elif isinstance(error, ValueError): reason = 'VALUE_ERROR'
    elif isinstance(error, TypeError): reason = 'TYPE_ERROR'
    return dict(schema=1, status='BLOCKED', stage=stage if stage in STAGES else 'UNKNOWN_STAGE',
        reason=reason, error_class=('ProbeFailure' if isinstance(error, ProbeFailure) else
             'OSError' if isinstance(error, OSError) else 'ValueError' if isinstance(error, ValueError)
             else 'TypeError' if isinstance(error, TypeError) else 'Exception'),
        opened=getattr(error, 'opened', None) if type(getattr(error, 'opened', None)) is bool else None,
        winerror=safe_integer(getattr(error, 'winerror', None)),
        errno=safe_integer(getattr(error, 'errno', None)), pid=os.getpid(),
        owner_authenticated=False, process_lifetime_authenticated=False,
        physical='0/10 NOT_RUN', physical_ready=False, host_verified=False,
        execution_authorized=False, cleanup_authorized=False, readiness_passed=False,
        verified_safety_cases=0, automatic_resume=False)


def run_guarded(runner=None, root=ROOT):
    state = dict(result_allowed=False, stage='PROFILE_GUARD')
    try:
        (main if runner is None else runner)(state)
        return 0
    except Exception as error:
        if state['result_allowed'] is True:
            try: write_result(root, failure_result(state['stage'], error))
            except Exception: pass  # Never replace partial output or write to stdout.
        return 1


def execute_probe(cfg, pid, read_pipe, open_parent, open_canary, write_frame):
    """Injected operations permit fault testing without any native API calls."""
    cfg = validate_config(cfg)
    denials = {}
    for name, operation in (('pipe_read', read_pipe), ('parent_process_read', open_parent),
                            ('foreign_canary_read', open_canary)):
        opened, error = operation()
        try: denials[name] = denial_fact(opened, error)
        except ValueError:
            raise ProbeFailure('DENIAL_NOT_PROVEN_'+name.upper(), opened, error) from None
    context = {key: cfg[key] for key in ('head', 'run_id', 'attempt', 'nonce')}
    context['pid'] = pid; frame = encode_ping(context)
    ok, written, error = write_frame(frame)
    try: require_written(ok, written, len(frame))
    except ValueError: raise ProbeFailure('FRAME_WRITE_INCOMPLETE', None, error) from None
    return dict(schema=1, **context, parent_pid=cfg['parent_pid'],
        status='PARTIAL_NO_GRID_AUTHORITY', isolated=True, grid_modules_empty=True,
        denials=denials, frame_written_bytes=written, frame_sha256=hashlib.sha256(frame).hexdigest(),
        frame_write_winerror=error if not ok else None,
        owner_authenticated=False, process_lifetime_authenticated=False,
        physical='0/10 NOT_RUN', physical_ready=False, host_verified=False,
        execution_authorized=False, cleanup_authorized=False, readiness_passed=False,
        verified_safety_cases=0, automatic_resume=False)


def write_result(root, result):
    raw = canonical(result); need(len(raw) <= 65536)
    root = pathlib.Path(root); data = root/'Data'; path = data/'result.json'
    for item in (root, data, path):
        need(not item.is_symlink() and not getattr(item, 'is_junction', lambda: False)())
    with path.open('r+b') as sink:
        fact = os.fstat(sink.fileno())
        need(fact.st_mode & 0o170000 == 0o100000 and fact.st_nlink == 1 and fact.st_size == 0)
        need(sink.write(raw) == len(raw)); sink.flush(); os.fsync(sink.fileno())


def main(state):
    isolated = sys.flags.isolated == 1 and sys.flags.no_site == 1 and sys.flags.dont_write_bytecode == 1
    # Validate path/platform/isolation before importing ctypes or invoking APIs.
    native_scope(str(ROOT), 'UNMEASURED', sys.argv[1:], sys.platform, isolated)
    state['stage'] = 'EXECUTABLE_GUARD'
    need(pathlib.Path(sys.executable).resolve() == ROOT/'pythonw.exe')
    state['stage'] = 'IMPORT_PATH_GUARD'
    need(all(pathlib.Path(p).resolve().is_relative_to(ROOT) for p in sys.path))
    state['stage'] = 'NATIVE_HOST'
    import ctypes
    from ctypes import wintypes as W
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetComputerNameW.argtypes = [W.LPWSTR, ctypes.POINTER(W.DWORD)]
    kernel.GetComputerNameW.restype = W.BOOL
    name = ctypes.create_unicode_buffer(256); size = W.DWORD(256)
    need(bool(kernel.GetComputerNameW(name, ctypes.byref(size))))
    native_scope(str(ROOT), name.value, sys.argv[1:], sys.platform, isolated)
    state['result_allowed'] = True
    state['stage'] = 'ENVIRONMENT_GUARD'; closed_environment(os.environ)
    state['stage'] = 'CONFIG_READ'
    with (ROOT/'config.json').open('rb') as source: raw = source.read(4097)
    state['stage'] = 'CONFIG_VALIDATE'; cfg = parse_config(raw)
    state['stage'] = 'CANARY_SCOPE'
    need(not pathlib.PureWindowsPath(cfg['canary']).is_relative_to(pathlib.PureWindowsPath(ROOT)))
    state['stage'] = 'MODULE_GUARD'
    need(not any(n == 'grid' or n.startswith('grid.') for n in sys.modules))
    state['stage'] = 'NATIVE_SETUP'
    kernel.GetStdHandle.argtypes = [W.DWORD]; kernel.GetStdHandle.restype = W.HANDLE
    kernel.ReadFile.argtypes = [W.HANDLE, W.LPVOID, W.DWORD, ctypes.POINTER(W.DWORD), W.LPVOID]
    kernel.ReadFile.restype = W.BOOL
    kernel.WriteFile.argtypes = kernel.ReadFile.argtypes; kernel.WriteFile.restype = W.BOOL
    kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]; kernel.OpenProcess.restype = W.HANDLE
    kernel.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, W.LPVOID, W.DWORD, W.DWORD, W.HANDLE]
    kernel.CreateFileW.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]; kernel.CloseHandle.restype = W.BOOL
    invalid = ctypes.c_void_p(-1).value
    state['stage'] = 'PIPE_HANDLE'
    pipe = kernel.GetStdHandle(W.DWORD(-11))
    need(pipe not in (None, 0, invalid))
    def read_pipe():
        state['stage'] = 'PIPE_READ'
        buffer = ctypes.create_string_buffer(1); count = W.DWORD()
        ok = bool(kernel.ReadFile(pipe, buffer, 1, ctypes.byref(count), None))
        error = ctypes.get_last_error(); return ok, error
    def open_parent():
        state['stage'] = 'PARENT_PROCESS_READ'
        process = kernel.OpenProcess(0x10, False, cfg['parent_pid']); error = ctypes.get_last_error()
        opened = process not in (None, 0)
        if opened: need(bool(kernel.CloseHandle(process)))
        return opened, error
    def open_canary():
        state['stage'] = 'FOREIGN_CANARY_READ'
        canary = kernel.CreateFileW(cfg['canary'], 0x80000000, 7, None, 3, 0x80, None)
        error = ctypes.get_last_error(); opened = canary not in (None, 0, invalid)
        if opened: need(bool(kernel.CloseHandle(canary)))
        return opened, error
    def write_frame(frame):
        state['stage'] = 'FRAME_WRITE'
        payload = ctypes.create_string_buffer(frame); count = W.DWORD()
        ok = bool(kernel.WriteFile(pipe, payload, len(frame), ctypes.byref(count), None))
        error = ctypes.get_last_error(); return ok, count.value, error
    result = execute_probe(cfg, os.getpid(), read_pipe, open_parent, open_canary, write_frame)
    state['stage'] = 'RESULT_WRITE'
    write_result(ROOT, result)


if __name__ == '__main__':
    # Never emit traceback text into the one-way protocol handle.
    sys.exit(run_guarded())
