"""Grid-free hosted-child observations. No attestation or physical authority.

Importing this module performs no I/O. Only the guarded native-child entry point
opens sockets. Targets are parent-owned loopback endpoints and two literal
documentation destinations, never arbitrary addresses from configuration.
"""
import errno
import json
import os
import pathlib
import select
import socket
import sys
import time


DEADLINE_SECONDS = 6.0
MAX_TRACE = 80
MAX_JSON = 65536
ROOT = pathlib.Path(__file__).resolve().parent


def need(condition):
    if not condition:
        raise ValueError('TRANSPORT_INPUT_OR_SCOPE_REFUSED')


def hex_text(value, length):
    return type(value) is str and len(value) == length and all(c in '0123456789abcdef' for c in value)


def guid_text(value):
    return (type(value) is str and len(value) == 36 and
            [len(x) for x in value.split('-')] == [8, 4, 4, 4, 12] and
            hex_text(value.replace('-', ''), 32))


def native_scope(root, host, args, platform, isolated):
    p = pathlib.PureWindowsPath(root)
    alias = host.split('.')[0].upper().replace('-', '').replace('_', '')
    need(args == ['--native-child'] and platform == 'win32' and isolated is True)
    need(alias not in ('LS5', 'PC4') and not
         (alias.startswith('LS') and alias[2:].isdigit() and int(alias[2:]) == 5) and not
         (alias.startswith('PC') and alias[2:].isdigit() and int(alias[2:]) == 4))
    need(len(p.drive) == 2 and p.drive[0].isascii() and p.drive[0].isalpha() and p.drive[1] == ':')
    need(p.parent.name == 'AC' and p.parent.parent.parent.name == 'Packages')
    need(p.name.startswith('python-') and guid_text(p.name[7:]))
    need(p.parent.parent.name.startswith('g1-fixture-') and guid_text(p.parent.parent.name[11:]))


def parse_config(raw):
    need(type(raw) is str and len(raw.encode('utf-8')) <= MAX_JSON)
    # Bound nesting before invoking the recursive JSON decoder.
    depth = 0; quoted = False; escaped = False
    for c in raw:
        if quoted:
            if escaped: escaped = False
            elif c == '\\': escaped = True
            elif c == '"': quoted = False
        elif c == '"': quoted = True
        elif c in '[{':
            depth += 1; need(depth <= 8)
        elif c in ']}': depth -= 1
    def pairs(items):
        value = {}
        for key, child in items:
            need(key not in value); value[key] = child
        return value
    return validate_config(json.loads(raw, object_pairs_hook=pairs))


def validate_config(cfg):
    need(type(cfg) is dict and set(cfg) == set('schema head run_id attempt nonce parent_pid endpoints'.split()))
    need(type(cfg['schema']) is int and cfg['schema'] == 1)
    need(hex_text(cfg['head'], 40) and hex_text(cfg['nonce'], 32))
    for key in ('run_id', 'attempt'):
        value = cfg[key]
        need(type(value) is str and 1 <= len(value) <= 20 and
             all(c in '0123456789' for c in value) and value[0] != '0')
    need(type(cfg['parent_pid']) is int and 0 < cfg['parent_pid'] < 2**32)
    need(type(cfg['endpoints']) is list and len(cfg['endpoints']) == 4)
    combinations = set(); ports = set()
    for endpoint in cfg['endpoints']:
        need(type(endpoint) is list and len(endpoint) == 4)
        family, host, port, mode = endpoint
        need(type(family) is str and family in ('IPv4', 'IPv6'))
        need(type(host) is str and host == ('127.0.0.1' if family == 'IPv4' else '::1'))
        need(type(port) is int and 0 < port <= 65535)
        need(type(mode) is str and mode in ('listener', 'bound-not-listening'))
        need((family, mode) not in combinations and (family, port) not in ports)
        combinations.add((family, mode)); ports.add((family, port))
    return {**cfg, 'endpoints': [list(row) for row in cfg['endpoints']]}


def targets(cfg):
    return [tuple(row) for row in cfg['endpoints']] + [
        ('IPv4', '192.0.2.1', 9, 'external'), ('IPv6', '2001:db8::1', 9, 'external')]


def error_fact(error):
    def number(value): return value if type(value) is int and -(2**31) <= value < 2**32 else None
    return dict(kind=type(error).__name__[:64], winerror=number(getattr(error, 'winerror', None)),
                errno=number(getattr(error, 'errno', None)))


def classify(code):
    # These are numeric observations, never authenticated policy-denial evidence.
    if type(code) is int and code == 10013: return 'ERROR10013'
    if type(code) is int and code == 10061: return 'ERROR10061'
    return 'OTHER_ERROR'


def endpoint_fact(value):
    need(type(value) is tuple and len(value) in (2, 4) and type(value[0]) is str and
         len(value[0]) <= 64 and type(value[1]) is int and 0 <= value[1] <= 65535)
    return list(value)


def observe_attempt(target, socket_factory=socket.socket, poll=select.select,
                    clock=time.monotonic, utc_ms=lambda: time.time_ns() // 1000000):
    family, host, port, mode = target
    started = clock(); deadline = started + DEADLINE_SECONDS
    row = dict(family=family, host=host, port=port, mode=mode, started_utc_ms=utc_ms(),
               bind_policy='IMPLICIT_OS_SELECTED', deadline_ms=6000, elapsed_ms=0,
               initial_code=None, so_error=None,
               poll_trace=[], peer_endpoint=None, local_endpoint=None, local_error=None,
               error=None, stage='socket', connected=False, classification='INCOMPLETE',
               evidence='UNKNOWN', complete=False)
    client = None
    try:
        af = socket.AF_INET if family == 'IPv4' else socket.AF_INET6
        client = socket_factory(af, socket.SOCK_STREAM)
        row['stage'] = 'setblocking'; client.setblocking(False)
        # Match the original connect baseline: let Winsock select local binding.
        # Explicit loopback binds belong only to the same-child controls.
        row['stage'] = 'connect_ex'
        if clock() >= deadline:
            row.update(classification='TIMEOUT', complete=True)
        else:
            initial = client.connect_ex((host, port))
            need(type(initial) is int and 0 <= initial < 2**32)
            row['initial_code'] = initial
            code = initial
            pending = (10035, 10036, 10037, errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY)
            if initial in pending:
                code = None; row['stage'] = 'select'
                while clock() < deadline and len(row['poll_trace']) < MAX_TRACE:
                    ready = poll([client], [client], [client], min(0.1, max(0, deadline-clock())))
                    readable, writable, exceptional = ready
                    row['poll_trace'].append(dict(elapsed_ms=round((clock()-started)*1000),
                        readable=bool(readable), writable=bool(writable), exceptional=bool(exceptional)))
                    if readable or writable or exceptional:
                        row['stage'] = 'SO_ERROR'
                        code = client.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                        need(type(code) is int and 0 <= code < 2**32)
                        row['so_error'] = code
                        break
                if code is None:
                    expired = clock() >= deadline
                    row.update(classification='TIMEOUT' if expired else 'TRACE_LIMIT', complete=expired)
            if code == 0:
                row['stage'] = 'getpeername'
                peer = endpoint_fact(client.getpeername()); row['peer_endpoint'] = peer
                if peer[0] == host and peer[1] == port:
                    row.update(connected=True, classification='UNEXPECTED_CONNECTION', complete=True)
                else: row.update(classification='PEER_MISMATCH', complete=True)
            elif code is not None:
                row.update(classification=classify(code), complete=True)
    except (OSError, ValueError, TypeError) as error:
        row['error'] = error_fact(error)
        raw = row['error']['winerror']
        if raw is None: raw = row['error']['errno']
        if row['stage'] == 'getpeername': row['classification'] = 'ZERO_WITHOUT_PEER'
        elif isinstance(error, TimeoutError): row['classification'] = 'TIMEOUT'
        elif isinstance(error, OSError): row['classification'] = classify(raw)
        else: row['classification'] = 'OPERATION_ERROR'
    finally:
        if client is not None:
            try: row['local_endpoint'] = endpoint_fact(client.getsockname())
            except (OSError, ValueError, TypeError) as error: row['local_error'] = error_fact(error)
            try: client.close()
            except OSError as error: row['close_error'] = error_fact(error)
        row['elapsed_ms'] = max(0, round((clock()-started)*1000))
    return row


def self_controls(socket_factory=socket.socket, pair_factory=socket.socketpair, clock=time.monotonic):
    """Bounded same-child TCP v4/v6 and stock socketpair exchanges, no Grid."""
    deadline = clock() + DEADLINE_SECONDS
    rows = []
    for name, af, host in (('IPv4', socket.AF_INET, '127.0.0.1'),
                           ('IPv6', socket.AF_INET6, '::1'), ('socketpair', None, None)):
        row = dict(name=name, complete=False, evidence='UNKNOWN', error=None)
        held = []
        def budget(channel):
            remaining = deadline - clock(); need(remaining > 0)
            channel.settimeout(remaining)
        def receive(channel, count):
            data = b''
            while len(data) < count:
                budget(channel); chunk = channel.recv(count-len(data))
                need(type(chunk) is bytes and 0 < len(chunk) <= count-len(data)); data += chunk
            return data
        try:
            if af is None:
                left, right = pair_factory(); held.extend((left, right))
            else:
                server = socket_factory(af, socket.SOCK_STREAM); held.append(server)
                budget(server); server.bind((host, 0)); server.listen(1)
                left = socket_factory(af, socket.SOCK_STREAM); held.append(left)
                budget(left); left.connect(server.getsockname())
                budget(server); right, _ = server.accept(); held.append(right)
                need(left.getpeername() == right.getsockname() and left.getsockname() == right.getpeername())
            budget(left); left.sendall(b'probe-v1')
            need(receive(right, 8) == b'probe-v1')
            budget(right); right.sendall(b'ack-v1')
            need(receive(left, 6) == b'ack-v1')
            row['complete'] = True
        except (OSError, ValueError, TypeError) as error: row['error'] = error_fact(error)
        finally:
            for channel in reversed(held):
                try: channel.close()
                except OSError as error:
                    row['complete'] = False; row['close_error'] = error_fact(error)
        rows.append(row)
    return rows


def run_probe(cfg, observe=observe_attempt, controls=self_controls, pid=None,
              isolated=False, grid_modules=None):
    cfg = validate_config(cfg)
    rows = []
    for target in targets(cfg):
        try: row = observe(target)
        except (OSError, ValueError, TypeError) as error:
            row = dict(family=target[0], host=target[1], port=target[2], mode=target[3],
                       complete=False, evidence='UNKNOWN', classification='OPERATION_ERROR', error=error_fact(error))
        rows.append(row)
    try: control_rows = controls()
    except (OSError, ValueError, TypeError) as error:
        control_rows = [dict(complete=False, evidence='UNKNOWN', error=error_fact(error))]
    modules = sorted(grid_modules if grid_modules is not None else
                     [name for name in sys.modules if name == 'grid' or name.startswith('grid.')])
    complete = (isolated is True and not modules and len(control_rows) == 3 and
                all(row.get('complete') is True for row in control_rows + rows))
    return dict(schema=1, head=cfg['head'], run_id=cfg['run_id'], attempt=cfg['attempt'],
                nonce=cfg['nonce'], parent_pid=cfg['parent_pid'], pid=os.getpid() if pid is None else pid,
                python_version=sys.version.split()[0], isolated=isolated,
                grid_modules=modules, grid_modules_empty=not modules,
                self_controls=control_rows, attempts=rows,
                status='OBSERVED_NOT_ATTESTED' if complete else 'BLOCKED',
                physical_status='0/10 NOT_RUN', physical_ready=False, host_verified=False,
                verified_safety_cases=0, execution_authorized=False, cleanup_authorized=False,
                readiness_passed=False, automatic_resume=False)


def write_result(root, result):
    """Write the parent's existing empty slot; parent must verify held identity.

    These local checks are not ownership, ACL, or anti-rollback evidence.
    """
    raw = json.dumps(result, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                     allow_nan=False).encode('ascii')
    need(len(raw) <= MAX_JSON)
    root = pathlib.Path(root)
    data = root / 'Data'; path = data / 'result.json'
    for item in (root, data, path):
        need(not item.is_symlink() and not getattr(item, 'is_junction', lambda: False)())
    # r+b does not create or truncate; write only after descriptor-level checks.
    with path.open('r+b') as sink:
        fact = os.fstat(sink.fileno())
        need(fact.st_mode & 0o170000 == 0o100000 and fact.st_nlink == 1 and fact.st_size == 0)
        need(sink.write(raw) == len(raw))
        sink.flush(); os.fsync(sink.fileno())


def main():
    isolated = (sys.flags.isolated == 1 and sys.flags.no_site == 1 and
                sys.flags.dont_write_bytecode == 1)
    native_scope(str(ROOT), socket.gethostname(), sys.argv[1:], sys.platform, isolated)
    need(pathlib.Path(sys.executable).resolve() == ROOT / 'pythonw.exe')
    need(all(pathlib.Path(p).resolve().is_relative_to(ROOT) for p in sys.path))
    with (ROOT / 'config.json').open('r', encoding='utf-8') as source:
        cfg = parse_config(source.read(MAX_JSON+1))
    result = run_probe(cfg, isolated=isolated)
    write_result(ROOT, result)


if __name__ == '__main__':
    main()
