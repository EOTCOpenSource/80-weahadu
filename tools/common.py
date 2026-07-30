"""Shared helpers for the build scripts in tools/."""
import hashlib
import json
import os

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)


def repo(*parts):
    """Path relative to the repository root, whatever the working directory."""
    return os.path.join(REPO, *parts)


def rel(path):
    """Repo-relative display path, for readable log lines."""
    try:
        return os.path.relpath(path, REPO).replace('\\', '/')
    except ValueError:
        return path


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def write_json(path, data, indent=1):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=indent)
        fh.write('\n')


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for block in iter(lambda: fh.read(chunk), b''):
            h.update(block)
    return h.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()
