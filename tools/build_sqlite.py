#!/usr/bin/env python3
"""Build SQLite databases from data/bible for the mobile apps.

Produces one small catalog plus one database per edition:

    dist/sqlite/catalog.db      canon, per-language book names, edition list
    dist/sqlite/am-2000.db      one edition: books, verses, headings, search
    dist/sqlite/gez-1980.db
    ...

The catalog is tiny and meant to ship inside the app bundle; edition databases
are downloaded on demand so a reader only pays for the translations they use.

Usage:
    python build_sqlite.py data/bible --out dist/sqlite
    python build_sqlite.py data/bible --out dist/sqlite --tokenizer unicode61
    python build_sqlite.py data/bible --out dist/sqlite --only am-2000 --gzip
"""
import argparse
import gzip
import json
import os
import shutil
import sqlite3
import sys

# Amharic, Ge'ez and Tigrinya are agglutinative: እግዚአብሔር appears as
# የእግዚአብሔርም, ለእግዚአብሔር, እግዚአብሔርን ... A word-boundary tokenizer such as
# unicode61 only finds the bare form, so trigram is the default -- it matches
# anywhere inside a word, at the cost of a larger index.
DEFAULT_TOKENIZER = 'trigram'

CATALOG_DDL = """
PRAGMA page_size = 4096;
CREATE TABLE edition (
    id TEXT PRIMARY KEY, title TEXT, title_en TEXT, abbrev TEXT,
    language TEXT, language_name TEXT, script TEXT, direction TEXT,
    year INTEGER, era TEXT, canon TEXT, publisher TEXT,
    books INTEGER, chapters INTEGER, verses INTEGER, file TEXT
);
CREATE TABLE canon (
    id TEXT PRIMARY KEY, ord INTEGER, slug TEXT, name_en TEXT,
    testament TEXT, section TEXT
);
CREATE TABLE book_name (
    lang TEXT, book TEXT, name TEXT, abbr TEXT,
    PRIMARY KEY (lang, book)
);
CREATE INDEX canon_ord ON canon(ord);
"""

EDITION_DDL = """
PRAGMA page_size = 4096;
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE book (
    id TEXT PRIMARY KEY, ord INTEGER, position INTEGER,
    name TEXT, abbr TEXT, chapters INTEGER, verses INTEGER
);
CREATE TABLE verse (
    id INTEGER PRIMARY KEY,
    book TEXT NOT NULL, chapter INTEGER NOT NULL,
    ord INTEGER NOT NULL,      -- position in the chapter; always usable for sorting
    verse INTEGER,             -- NULL for the handful of unnumbered verses
    label TEXT,                -- display form: "3", "3b", "98a"
    alt TEXT,                  -- Ge'ez numeral, e.g. ፩
    text TEXT NOT NULL,
    lines TEXT,                -- JSON array, only for multi-line (poetry) verses
    refs TEXT,                 -- JSON array of cross references
    notes TEXT                 -- JSON array of footnotes
);
CREATE UNIQUE INDEX verse_ref ON verse(book, chapter, ord);
CREATE INDEX verse_lookup ON verse(book, chapter, verse);
CREATE TABLE heading (
    book TEXT NOT NULL, chapter INTEGER NOT NULL,
    before INTEGER,            -- verse number it precedes; NULL = end of chapter
    ord INTEGER, kind TEXT, style TEXT, text TEXT
);
CREATE INDEX heading_ref ON heading(book, chapter);
CREATE TABLE chapter (
    book TEXT NOT NULL, n INTEGER NOT NULL, alt TEXT, verses INTEGER,
    PRIMARY KEY (book, n)
);
"""


def as_int(v):
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.isdigit():
        return int(v)
    return None


def js(v):
    return json.dumps(v, ensure_ascii=False, separators=(',', ':')) if v else None


def build_catalog(src, out, indent_report):
    path = os.path.join(out, 'catalog.db')
    if os.path.exists(path):
        os.remove(path)
    con = sqlite3.connect(path)
    con.executescript(CATALOG_DDL)

    editions = json.load(open(os.path.join(src, 'editions.json'), encoding='utf-8'))['editions']
    for e in editions:
        s = e['stats']
        con.execute(
            'INSERT INTO edition VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (e['id'], e['title'], e.get('title_en'), e.get('abbrev'),
             e['language'], e.get('language_name'), e.get('script'), 'ltr',
             e.get('year'), e.get('era'), e.get('canon'), e.get('publisher'),
             s['books'], s['chapters'], s['verses'], e['id'] + '.db'))

    canon = json.load(open(os.path.join(src, 'canon.json'), encoding='utf-8'))
    for c in canon:
        con.execute('INSERT INTO canon VALUES (?,?,?,?,?,?)',
                    (c['id'], c['order'], c['slug'], c.get('name_en'),
                     c.get('testament'), c.get('section')))

    ndir = os.path.join(src, 'names')
    for fn in sorted(os.listdir(ndir)):
        lang = fn[:-5]
        for bid, v in json.load(open(os.path.join(ndir, fn), encoding='utf-8')).items():
            con.execute('INSERT OR REPLACE INTO book_name VALUES (?,?,?,?)',
                        (lang, bid, v.get('name'), v.get('abbr')))

    con.commit()
    con.execute('VACUUM')
    con.close()
    indent_report('catalog.db', path)
    return editions


def build_edition(src, out, e, tokenizer, report):
    path = os.path.join(out, e['id'] + '.db')
    if os.path.exists(path):
        os.remove(path)
    con = sqlite3.connect(path)
    con.executescript(EDITION_DDL)

    meta = json.load(open(os.path.join(src, e['id'], 'meta.json'), encoding='utf-8'))
    for k in ('id', 'title', 'title_en', 'abbrev', 'language', 'language_name',
              'script', 'direction', 'year', 'era', 'canon', 'publisher'):
        if meta.get(k) is not None:
            con.execute('INSERT INTO meta VALUES (?,?)', (k, str(meta[k])))
    con.execute('INSERT INTO meta VALUES (?,?)', ('source_collection',
                                                  meta.get('source', {}).get('collection', '')))
    con.execute('INSERT INTO meta VALUES (?,?)', ('tokenizer', tokenizer))
    con.execute('INSERT INTO meta VALUES (?,?)', ('schema_version', '1'))
    # Stamp the data revision so a client can tell which patches it still
    # needs without re-deriving it from the content.
    revs = os.path.join(src, 'revisions.json')
    if os.path.exists(revs):
        with open(revs, encoding='utf-8') as fh:
            entry = json.load(fh).get('editions', {}).get(e['id'], {})
        for k in ('revision', 'baseline'):
            if entry.get(k) is not None:
                con.execute('INSERT INTO meta VALUES (?,?)', (k, str(entry[k])))

    vid = 0
    for b in meta['books']:
        con.execute('INSERT INTO book VALUES (?,?,?,?,?,?,?)',
                    (b['id'], b['order'], b['position'], b['name'],
                     b.get('abbr'), b['chapters'], b['verses']))
        doc = json.load(open(os.path.join(src, e['id'], b['file']), encoding='utf-8'))
        for ch in doc['chapters']:
            cn = as_int(ch['n'])
            con.execute('INSERT INTO chapter VALUES (?,?,?,?)',
                        (b['id'], cn, ch.get('alt'), len(ch['verses'])))
            for i, h in enumerate(ch.get('headings') or []):
                con.execute('INSERT INTO heading VALUES (?,?,?,?,?,?,?)',
                            (b['id'], cn, as_int(h.get('before')), i,
                             h.get('kind'), h.get('style'), h.get('text')))
            for i, v in enumerate(ch['verses']):
                vid += 1
                con.execute(
                    'INSERT INTO verse VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                    (vid, b['id'], cn, i, as_int(v.get('n')),
                     None if v.get('n') is None else str(v['n']),
                     v.get('alt'), v.get('t') or '',
                     js(v.get('lines')), js(v.get('refs')), js(v.get('notes'))))
    con.commit()

    con.execute("CREATE VIRTUAL TABLE verse_fts USING fts5("
                "text, content='verse', content_rowid='id', tokenize='%s')" % tokenizer)
    con.execute("INSERT INTO verse_fts(rowid, text) SELECT id, text FROM verse")
    con.commit()
    con.execute('PRAGMA journal_mode = DELETE')
    con.execute('VACUUM')
    con.execute('PRAGMA optimize')
    con.close()
    report(e['id'] + '.db', path, vid)
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('src', help='data/bible')
    ap.add_argument('--out', required=True)
    ap.add_argument('--tokenizer', default=DEFAULT_TOKENIZER,
                    choices=['trigram', 'unicode61'])
    ap.add_argument('--only', action='append', help='edition id (repeatable)')
    ap.add_argument('--gzip', action='store_true',
                    help='also write .db.gz for download')
    args = ap.parse_args()

    probe = sqlite3.connect(':memory:')
    try:
        probe.execute("CREATE VIRTUAL TABLE t USING fts5(x, tokenize='%s')" % args.tokenizer)
    except sqlite3.OperationalError as err:
        sys.exit('this Python has no FTS5 %s support: %s' % (args.tokenizer, err))
    probe.close()

    os.makedirs(args.out, exist_ok=True)
    total = 0

    def report(name, path, verses=None):
        nonlocal total
        size = os.path.getsize(path)
        total += size
        extra = ('%7d verses' % verses) if verses is not None else ' ' * 14
        line = '  %-18s %8.1f MB %s' % (name, size / 1e6, extra)
        if args.gzip:
            gzp = path + '.gz'
            with open(path, 'rb') as fi, gzip.open(gzp, 'wb', compresslevel=9) as fo:
                shutil.copyfileobj(fi, fo)
            line += '   gz %6.1f MB' % (os.path.getsize(gzp) / 1e6)
        print(line)

    print('tokenizer: %s\n' % args.tokenizer)
    editions = build_catalog(args.src, args.out, lambda n, p: report(n, p))
    for e in editions:
        if args.only and e['id'] not in args.only:
            continue
        build_edition(args.src, args.out, e, args.tokenizer, report)

    print('\ntotal %.1f MB in %s' % (total / 1e6, args.out))


if __name__ == '__main__':
    main()
