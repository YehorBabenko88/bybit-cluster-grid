"""Read-only raw HEAD blob verification for the isolated qualification lane."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess


def verify(expected):
    env = os.environ.copy()
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
               GIT_NO_REPLACE_OBJECTS='1', GIT_CONFIG_COUNT='0')
    def git(*args):
        return subprocess.check_output(['git','--no-replace-objects','-c','core.fsmonitor=false',*args], env=env, timeout=30)
    head = git('rev-parse','HEAD').decode().strip()
    if head != expected or git('rev-parse','--show-object-format').strip() != b'sha1':
        raise ValueError('SOURCE_HEAD_OR_FORMAT_MISMATCH')
    root = Path(git('rev-parse','--show-toplevel').decode().strip()).resolve()
    entries = git('ls-tree','-r','-z','HEAD').split(b'\0')
    total = 0
    count = 0
    tracked = set()
    for entry in filter(None, entries):
        meta, raw_path = entry.split(b'\t',1)
        mode, kind, oid = meta.split()
        if mode not in (b'100644', b'100755') or kind != b'blob':
            raise ValueError('SOURCE_NONREGULAR_ENTRY')
        relative = Path(raw_path.decode('utf-8'))
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('SOURCE_PATH_INVALID')
        path = root / relative
        tracked.add(relative.as_posix())
        for ancestor in (path, *path.parents):
            if ancestor == root.parent:
                break
            if ancestor.is_symlink():
                raise ValueError('SOURCE_SYMLINK')
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16 * 1024**2:
            raise ValueError('SOURCE_FILE_BOUND')
        data = path.read_bytes()
        total += len(data)
        count += 1
        if total > 256 * 1024**2 or count > 10000:
            raise ValueError('SOURCE_TREE_BOUND')
        actual = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        if actual != oid.decode():
            raise ValueError('SOURCE_RAW_BLOB_MISMATCH:' + str(relative))
    evidence = {'qualification-source-before.json', 'qualification-source-after.json',
                'coordination-tests.xml', 'qualification-three/evidence.json',
                'qualification-three/qualification.snap'}
    observed = 0
    for folder, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(folder) == root and d == '.git')]
        for dirname in dirs:
            if (Path(folder) / dirname).is_symlink():
                raise ValueError('SOURCE_UNTRACKED_SYMLINK')
        for name in names:
            path = Path(folder) / name
            relative = path.relative_to(root).as_posix()
            observed += 1
            if observed > 12000:
                raise ValueError('SOURCE_UNTRACKED_SCAN_BOUND')
            if relative == '.git':
                continue
            if path.is_symlink() or (relative not in tracked and relative not in evidence):
                raise ValueError('SOURCE_UNEXPECTED_FILE:' + relative)
    return dict(head=head, tree=git('rev-parse','HEAD^{tree}').decode().strip(),
                raw_head_blobs_verified=count, raw_bytes=total, checkout_policy='core.autocrlf=false; raw blob equality',
                scope='EPHEMERAL_LINUX_ONLY', native_windows='NOT_RUN', physical='NOT_RUN',
                human_authentication='SYNTHETIC_AUTH')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    Path(args.output).write_text(json.dumps(verify(args.expected), indent=2))
