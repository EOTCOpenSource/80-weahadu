#!/usr/bin/env python3
"""Cut a data release: corrections -> revisions -> patches -> minified -> SQLite.

Run this after editing anything under corrections/. It is the single command
that keeps every published artefact in step with data/bible.

    python tools/release.py                 # full release
    python tools/release.py --dry-run       # report what would change
    python tools/release.py --skip-sqlite   # data + patches only (fast)

What it does, in order:

 1. applies corrections/<edition>.json to data/bible (idempotent)
 2. gives every not-yet-released correction the next revision number
 3. writes data/bible/patches/<edition>/<rev>.json -- what a client applies
    to catch up without re-downloading a whole database
 4. rebuilds minified/ (the v1 Amharic bundle)
 5. rebuilds dist/sqlite/ and records each database's size and sha256
 6. writes data/bible/revisions.json -- what clients poll

Clients compare their stored revision against revisions.json. If it is at or
above `baseline` they apply the patches they are missing; otherwise they
download the database again. Bump `baseline` when data/bible is regenerated
wholesale, so clients stop trying to patch across a rebuild.
"""
import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import repo, rel, read_json, write_json, sha256_file  # noqa: E402
import apply_corrections  # noqa: E402

REVISIONS = repo('data', 'bible', 'revisions.json')
PATCH_DIR = repo('data', 'bible', 'patches')
SQLITE_OUT = repo('dist', 'sqlite')
SCHEMA = 1


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def load_state():
    state = read_json(REVISIONS)
    if state and state.get('schema') == SCHEMA:
        return state
    return {'schema': SCHEMA, 'generated': None, 'editions': {}}


def edition_ids():
    cat = read_json(repo('data', 'bible', 'editions.json'))
    return [e['id'] for e in cat['editions']], {e['id']: e for e in cat['editions']}


def run(cmd, label):
    print('  %s' % label)
    p = subprocess.run([sys.executable] + cmd, cwd=repo(),
                       capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    if p.returncode != 0:
        print(p.stdout)
        print(p.stderr, file=sys.stderr)
        raise SystemExit('failed: %s' % label)
    for line in (p.stdout or '').strip().splitlines()[-12:]:
        print('      ' + line)
    return p.stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--skip-sqlite', action='store_true')
    ap.add_argument('--skip-minify', action='store_true')
    ap.add_argument('--tokenizer', default='trigram',
                    choices=['trigram', 'unicode61'])
    ap.add_argument('--baseline', action='store_true',
                    help='treat this as a wholesale rebuild: bump baseline so '
                         'clients full-download instead of patching')
    args = ap.parse_args()

    ids, catalog = edition_ids()
    state = load_state()
    stamp = now()

    # ---- 1. corrections -------------------------------------------------
    print('\n[1/5] corrections')
    changed = {}
    for ed in ids:
        items = apply_corrections.load(ed)
        if not items:
            continue
        r = apply_corrections.apply_edition(ed, check=args.dry_run)
        if r['stale']:
            raise SystemExit('  stale corrections in %s -- fix them before releasing' % ed)
        pending = [c for c in items if c.get('revision') is None]
        if pending:
            changed[ed] = (items, pending)
    if not changed:
        print('  no new corrections')

    # ---- 2. revisions ---------------------------------------------------
    print('\n[2/5] revisions')
    for ed in ids:
        entry = state['editions'].setdefault(ed, {'revision': 1, 'baseline': 1})
        if args.baseline:
            entry['revision'] = entry.get('revision', 1) + 1
            entry['baseline'] = entry['revision']
    for ed, (items, pending) in changed.items():
        entry = state['editions'][ed]
        nxt = entry.get('revision', 1) + 1
        for c in pending:
            c['revision'] = nxt
        entry['revision'] = nxt
        print('  %-14s revision %d -> %d  (%d correction(s))'
              % (ed, nxt - 1, nxt, len(pending)))
        if not args.dry_run:
            apply_corrections.save(ed, items)
    for ed in ids:
        if ed not in changed and not args.baseline:
            print('  %-14s revision %d (unchanged)' % (ed, state['editions'][ed]['revision']))

    # ---- 3. patches -----------------------------------------------------
    print('\n[3/5] patches')
    for ed, (items, pending) in changed.items():
        rev = state['editions'][ed]['revision']
        patch = {
            'edition': ed, 'from': rev - 1, 'to': rev, 'generated': stamp,
            'ops': [{'op': c.get('op', 'verse'), 'book': c['book'],
                     'chapter': c['chapter'], 'verse': c['verse'],
                     'field': c.get('field', 't'), 'to': c['to']}
                    for c in pending],
        }
        path = os.path.join(PATCH_DIR, ed, '%d.json' % rev)
        print('  %-14s %s  (%d op(s))' % (ed, rel(path), len(patch['ops'])))
        if not args.dry_run:
            write_json(path, patch)
    if not changed:
        print('  nothing to emit')

    for ed in ids:
        d = os.path.join(PATCH_DIR, ed)
        revs = sorted(int(f[:-5]) for f in os.listdir(d)) if os.path.isdir(d) else []
        state['editions'][ed]['patches'] = revs

    # ---- 4. minified (v1) ----------------------------------------------
    print('\n[4/5] minified/ (v1 Amharic bundle)')
    if args.skip_minify or args.dry_run:
        print('  skipped')
    else:
        run([repo('tools', 'minify_json.py')], 'minify_json.py')
        run([repo('tools', 'minify_single_chapters.py')], 'minify_single_chapters.py')

    # Write the manifest before building, so build_sqlite.py can stamp each
    # database with the revision it was built from.
    for ed in ids:
        entry = state['editions'][ed]
        s = catalog[ed]['stats']
        entry.update(books=s['books'], chapters=s['chapters'], verses=s['verses'],
                     json='data/bible/%s' % ed)
    state['generated'] = stamp
    if not args.dry_run:
        write_json(REVISIONS, state)

    # ---- 5. sqlite ------------------------------------------------------
    print('\n[5/5] dist/sqlite')
    if args.skip_sqlite or args.dry_run:
        print('  skipped')
    else:
        run([repo('tools', 'build_sqlite.py'), repo('data', 'bible'),
             '--out', SQLITE_OUT, '--gzip', '--tokenizer', args.tokenizer],
            'build_sqlite.py')
        for ed in ids:
            gz = os.path.join(SQLITE_OUT, ed + '.db.gz')
            if os.path.exists(gz):
                state['editions'][ed]['db'] = {
                    'file': ed + '.db.gz',
                    'bytes': os.path.getsize(gz),
                    'sha256': sha256_file(gz)}

    if args.dry_run:
        print('\ndry run -- revisions.json not written')
    else:
        write_json(REVISIONS, state)
        print('\nwrote %s' % rel(REVISIONS))

    print('\nsummary')
    for ed in ids:
        e = state['editions'][ed]
        db = e.get('db')
        print('  %-14s rev %-3d baseline %-3d patches %-14s %s'
              % (ed, e['revision'], e['baseline'],
                 ','.join(map(str, e['patches'])) or '-',
                 ('%.1f MB gz' % (db['bytes'] / 1e6)) if db else 'no db built'))


if __name__ == '__main__':
    main()
