#!/usr/bin/env python3
"""Apply corrections/<edition>.json to data, in place and idempotently.

Corrections are kept as their own input rather than edited straight into
data, for two reasons: a rebuild from the original USFM would silently
clobber hand edits, and the same file is what generates the patch clients
download. One edit, one source, both outputs.

Applying does not need the original USFM dump -- it rewrites the published
JSON -- so anyone with a clone can run it.

    python tools/apply_corrections.py --all
    python tools/apply_corrections.py am-2000 --check    # report, change nothing
"""
import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import repo, rel, read_json, write_json  # noqa: E402

FIELDS = {'t': 't', 'text': 't', 'alt': 'alt'}


def editions_with_corrections():
    out = []
    for path in sorted(glob.glob(repo('corrections', '*.json'))):
        out.append(os.path.splitext(os.path.basename(path))[0])
    return out


def load(edition):
    doc = read_json(repo('corrections', edition + '.json'))
    if doc is None:
        return []
    items = doc if isinstance(doc, list) else doc.get('corrections', [])
    for i, c in enumerate(items):
        c.setdefault('op', 'verse')
        c['_index'] = i
    return items


def save(edition, items):
    path = repo('corrections', edition + '.json')
    doc = read_json(path) or {}
    if isinstance(doc, list):
        doc = {'edition': edition, 'corrections': doc}
    doc['edition'] = edition
    doc['corrections'] = [{k: v for k, v in c.items() if not k.startswith('_')}
                          for c in items]
    write_json(path, doc)


def apply_edition(edition, check=False, verbose=True):
    """Returns (applied, already, stale, missing) counts and the stale list."""
    items = load(edition)
    if not items:
        return dict(applied=0, already=0, stale=0, missing=0, details=[])

    meta = read_json(repo('data', edition, 'meta.json'))
    if meta is None:
        raise SystemExit('no such edition: %s' % edition)
    files = {b['id']: b['file'] for b in meta['books']}

    by_book = {}
    for c in items:
        if c.get('op', 'verse') != 'verse':
            continue
        by_book.setdefault(c['book'], []).append(c)

    applied = already = stale = missing = 0
    details = []

    for book, group in by_book.items():
        rel_file = files.get(book)
        if rel_file is None:
            missing += len(group)
            details.append(('missing-book', book, None, None))
            continue
        path = repo('data', edition, rel_file)
        doc = read_json(path)
        index = {}
        for ch in doc['chapters']:
            for v in ch['verses']:
                index[(ch['n'], v['n'])] = v

        dirty = False
        for c in group:
            v = index.get((c['chapter'], c['verse']))
            if v is None:
                missing += 1
                details.append(('missing-verse', book, c['chapter'], c['verse']))
                continue
            field = FIELDS.get(c.get('field', 't'), 't')
            current = v.get(field)
            if current == c['to']:
                already += 1
                continue
            # only rewrite what we expect to be rewriting
            if 'was' in c and current != c['was']:
                stale += 1
                details.append(('stale', book, c['chapter'], c['verse']))
                continue
            if not check:
                v[field] = c['to']
                dirty = True
            applied += 1

        if dirty and not check:
            write_json(path, doc)

    if verbose:
        note = ' (check only, nothing written)' if check else ''
        print('  %-14s applied %-4d already %-4d stale %-3d missing %-3d%s'
              % (edition, applied, already, stale, missing, note))
        for kind, book, ch, v in details[:8]:
            where = book if ch is None else '%s %s:%s' % (book, ch, v)
            print('      %-13s %s' % (kind, where))

    return dict(applied=applied, already=already, stale=stale,
                missing=missing, details=details)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('edition', nargs='?', help='edition id, or use --all')
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--check', action='store_true',
                    help='report what would change without writing')
    args = ap.parse_args()

    targets = editions_with_corrections() if args.all else [args.edition]
    if not targets or targets == [None]:
        ap.error('give an edition id or --all')

    print('corrections:')
    total = dict(applied=0, already=0, stale=0, missing=0)
    for ed in targets:
        r = apply_edition(ed, check=args.check)
        for k in total:
            total[k] += r[k]
    print('  total applied %(applied)d, already current %(already)d, '
          'stale %(stale)d, missing %(missing)d' % total)
    if total['stale']:
        print('\n  "stale" means the verse no longer matches the recorded `was`,')
        print('  so nothing was changed. Re-check the correction against the data.')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
