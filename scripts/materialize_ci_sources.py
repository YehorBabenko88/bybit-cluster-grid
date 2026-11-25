"""CI-only exact Git build-input materialization; no blind LF conversion."""
from pathlib import Path
import stat
import subprocess

def materialize(root, expected_sha, packages):
    root = Path(root).resolve(strict=True)
    def git(*args):
        return subprocess.check_output(['git', '--no-replace-objects', *args], cwd=root)
    if git('rev-parse', 'HEAD').decode('ascii').strip() != expected_sha:
        raise ValueError('checkout HEAD differs from approved source')
    names = ['pyproject.toml']
    names += [p for p in ('README.md', 'MANIFEST.in') if (root / p).exists()]
    for package in packages:
        base = root / package
        if base.is_symlink() or not base.is_dir():
            raise ValueError('package directory must be ordinary')
        names += [p.relative_to(root).as_posix() for p in base.rglob('*')
                  if p.suffix in {'.py', '.sql', '.html', '.md', '.json'}]
    for name in sorted(set(names)):
        target = root / name
        info = target.lstat()
        if (not stat.S_ISREG(info.st_mode) or target.is_symlink()
                or getattr(info, "st_file_attributes", 0) & 0x400
                or info.st_size > 2 * 1024 * 1024):
            raise ValueError('build input is not bounded ordinary file')
        if not target.resolve(strict=True).is_relative_to(root):
            raise ValueError('build input escaped checkout')
        committed = git('cat-file', 'blob', 'HEAD:' + name)
        working = target.read_bytes()
        if working != committed and working.replace(b'\r\n', b'\n') != committed:
            raise ValueError('build input differs from exact Git blob: ' + name)
        target.write_bytes(committed)
    return tuple(sorted(set(names)))
