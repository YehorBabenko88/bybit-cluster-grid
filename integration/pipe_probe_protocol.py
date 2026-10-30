"""Bounded FIXED_PING grammar. Context matching is not owner authentication."""
import json
import pathlib


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


def validate_frame(raw, expected):
    expected = context(expected)
    need(type(raw) is bytes and 4 < len(raw) <= MAX_PAYLOAD+4)
    length = int.from_bytes(raw[:4], 'little')
    need(0 < length <= MAX_PAYLOAD and len(raw) == length+4)
    value = parse_json(raw[4:], MAX_PAYLOAD)
    need(type(value) is dict and set(value) == set(expected) | {'schema', 'verb'})
    need(type(value['schema']) is int and value['schema'] == 1 and
         type(value['verb']) is str and value['verb'] == 'ping')
    actual = context({key: value[key] for key in expected})
    need(actual == expected and raw == encode_ping(expected))
    return value


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
