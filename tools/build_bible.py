#!/usr/bin/env python3
"""Build the multi-language bible data set from the decrypted SAB dump.

Layout produced (see BIBLE.md):

    data/
      canon.json          ordered book registry -- language-neutral join key
      editions.json       index of every edition
      names/<lang>.json   UI book names, one file per UI language
      <edition>/
        meta.json         edition metadata + its own book names
        books/01-genesis.json

Content files carry no book names at all. Names live in canon/names (for UI
chrome) and in each edition's meta.json (for the names that edition itself
uses). Filenames are canon-stable: 01-genesis.json is Genesis in every
edition, so a 66-book edition simply has gaps in the numbering.

Usage:
    python build_bible.py outputs/source --out data
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from usfm2json import ChapterParser, verse_segments, norm_space  # noqa: E402

# --------------------------------------------------------------------------
# the editions
#
# Years and publishers come from each collection's <book-collection-abbrev>
# and <book-collection-description> in the app config. "EC" is the Ethiopian
# calendar, which is how these editions are dated; C45 is dated GC.
# --------------------------------------------------------------------------

EDITIONS = [
    dict(id='am-2000', collection='C18', language='am', script='Ethi',
         title='መጽሐፍ ቅዱስ፣ ሰማንያ አሐዱ በአማርኛ', abbrev='መጽሐፍ ቅዱስ አማርኛ የ2000 ዓ.ም ዕትም',
         title_en='Amharic Bible, 81 books, 2000 EC edition',
         year=2000, era='EC', canon='eotc-81',
         publisher='የኢትዮጵያ መጽሐፍ ቅዱስ ማኅበር'),
    dict(id='am-1980', collection='C03', language='am', script='Ethi',
         title='መጽሐፍ ቅዱስ ሰማንያ አሐዱ በአማርኛ', abbrev='መጽሐፍ ቅዱስ በአማርኛ 1980',
         title_en='Amharic Bible, 81 books, 1980 EC edition',
         year=1980, era='EC', canon='eotc-81',
         publisher='የኢትዮጵያ መጽሐፍ ቅዱስ ማኅበር'),
    dict(id='gez-1980', collection='C02', language='gez', script='Ethi',
         title='መጽሐፍ ቅዱስ ሰማንያ አሐዱ በግእዝ', abbrev='መጽሐፍ ቅዱስ በግእዝ 1980',
         title_en="Ge'ez Bible, 81 books, 1980 EC edition",
         year=1980, era='EC', canon='eotc-81',
         publisher='የኢትዮጵያ መጽሐፍ ቅዱስ ማኅበር'),
    dict(id='gez-2014', collection='C44', language='gez', script='Ethi',
         title='መጽሐፍ ቅዱስ፣ ሰማንያ አሐዱ በግእዝ፣ የ 2014 ዓ.ም ዕትም', abbrev='ግእዝ 2014',
         title_en="Ge'ez Bible, 81 books, 2014 EC edition (partial)",
         year=2014, era='EC', canon='eotc-81', partial=True,
         publisher='የኢትዮጵያ መጽሐፍ ቅዱስ ማኅበር'),
    dict(id='en-kjv', collection='C04', language='en', script='Latn',
         title='Bible King James Version (KJV)', abbrev='English Bible (KJV)',
         title_en='King James Version with Apocrypha',
         year=1611, era='GC', canon='kjv-81', publisher=None,
         remap={'LJE': 'LJE-KJV', '1ES': '1ES-KJV', '2ES': '2ES-KJV',
                '1MA': '1MA-KJV', '2MA': '2MA-KJV'}),
    dict(id='am-nasv-2001', collection='C45', language='am', script='Ethi',
         title='መጽሐፍ ቅዱስ ስድሳ ስድስቱ፣ አዲሱ መደበኛ ትርጕም', abbrev='አዲሱ.መ.ትር 2001',
         title_en='New Amharic Standard Version, 2001 GC',
         year=2001, era='GC', canon='protestant-66',
         publisher='International Bible Society'),
    dict(id='am-1962', collection='C46', language='am', script='Ethi',
         title='መጽሐፍ ቅዱስ ስድሳ ስድስቱ፣ ቀዳማዊ ኃይለ ሥላሴ ዘመነ መንግሥት', abbrev='አማርኛ 1962',
         title_en='Amharic Bible, Haile Selassie I era, 1962 EC',
         year=1962, era='EC', canon='protestant-66',
         publisher='የኢትዮጵያ መጽሐፍ ቅዱስ ማኅበር'),
    dict(id='ti-1997', collection='C47', language='ti', script='Ethi',
         title='መጽሐፍ ቅዱስ ስድሳ ስድስቱ፣ ትግርኛ መደበኛ ትርጕም', abbrev='ትግርኛ',
         title_en='Tigrinya Standard Translation, 1997 EC',
         year=1997, era='EC', canon='protestant-66',
         publisher='የኢትዮጵያ መጽሐፍ ቅዱስ ማኅበር'),
    dict(id='om-kitaaba', collection='C48', language='om', script='Latn',
         title='Kitaaba Qulqulluu, Afaan Oromoo', abbrev='Afaan Oromoo',
         title_en='Oromo Bible', year=None, era=None, canon='protestant-66',
         publisher='Waldaa Kitaaba Qulqulluu Ethiopia'),
]

# The edition whose book order and id set define the canon registry: the
# 2000 EC Amharic 81-book bible, which is a superset of every other edition
# here (the union of book ids across all nine is exactly its 94).
PROJECT = 'Nehemiah Open Source'
DATASET = '80-weahadu'

CANON_SOURCE = 'C18'
# English names come from the KJV collection; it covers 81 of the 94 ids.
ENGLISH_SOURCE = 'C04'

LANG_NAMES = {'am': 'አማርኛ', 'gez': 'ግእዝ', 'ti': 'ትግርኛ',
              'om': 'Afaan Oromoo', 'en': 'English'}

# The 66 books whose id means the same thing in every edition here; their
# English name and slug can safely be taken from the KJV collection.
STANDARD_66 = set("""GEN EXO LEV NUM DEU JOS JDG RUT 1SA 2SA 1KI 2KI 1CH 2CH EZR
NEH EST JOB PSA PRO ECC SNG ISA JER LAM EZK DAN HOS JOL AMO OBA JON MIC NAM HAB
ZEP HAG ZEC MAL MAT MRK LUK JHN ACT ROM 1CO 2CO GAL EPH PHP COL 1TH 2TH 1TI 2TI
TIT PHM HEB JAS 1PE 2PE 1JN 2JN 3JN JUD REV""".split())

# Outside those 66 the USFM id is just a slot, and SAB fills it differently per
# collection: C18's LJE is ተረፈ ኤርምያስ (Rest of Jeremiah) while the KJV
# collection's LJE is the Epistle of Jeremy, and C18's 1ES is ዕዝራ ሱቱኤል where
# KJV's is 1 Esdras. So the EOTC canon's own naming is spelled out here rather
# than inherited from KJV. Slugs follow the spellings already used in legacy/am.
EOTC_BOOKS = {
    'TOB': ('tobit', 'Tobit'),
    'JDT': ('yodit', 'Judith'),
    'ESG': ('esther-greek', 'Esther (Greek)'),
    'WIS': ('wisdom-of-solomon', 'Wisdom of Solomon'),
    'SIR': ('sirach', 'Sirach'),
    'BAR': ('baruch', 'Baruch'),
    'LJE': ('teref-ermias', 'Rest of Jeremiah'),
    'S3Y': ('seleste-dekik', 'Song of the Three Holy Children'),
    'SUS': ('susanna', 'Susanna'),
    '1MA': ('1-maccabees', '1 Maccabees (Ethiopic)'),
    '2MA': ('2-maccabees', '2 Maccabees (Ethiopic)'),
    '3MA': ('3-maccabees', '3 Maccabees (Ethiopic)'),
    '4MA': ('admonition', 'Book of Admonition'),
    '1ES': ('ezra-sutuel', 'Ezra Sutuel'),
    '2ES': ('ezra-kalie', 'Ezra Kalie'),
    'MAN': ('prayer-of-manasseh', 'Prayer of Manasseh'),
    'DAG': ('teref-daniel', 'Rest of Daniel'),
    'JUB': ('kufale', 'Jubilees'),
    'ENO': ('enoch', 'Enoch'),
    'OTH': ('1-covenant', 'Book of the Covenant I'),
    'LAO': ('2-covenant', 'Book of the Covenant II'),
    'XXG': ('sirate-tsion', 'Order of Zion'),
    'XXA': ('josippon', 'Josippon'),
    'XXB': ('1-clement', 'Clement'),
    'XXC': ('didascalia', 'Didascalia'),
    'XXD': ('tizaz', 'Book of the Commandments'),
    'XXE': ('abtilis', 'Abtilis'),
    'XXF': ('gitsew', 'Gitsew'),
}

TESTAMENT = {'OT': 'old', 'DC': 'deuterocanonical', 'NT': 'new', 'NTC': 'new'}

# Five deuterocanonical slots hold a genuinely different work in the KJV
# collection than in the EOTC ones -- the Ethiopic Maccabees are 36 and 21
# chapters where the Greek are 16 and 15, and ተረፈ ኤርምያስ is not the Epistle of
# Jeremy. Sharing a filename would silently break any parallel view, so KJV's
# versions get canon slots of their own. Everything else lines up.
CANON_EXTRA = [
    ('LJE-KJV', 'jeremys-letter', 'Letter of Jeremiah'),
    ('1ES-KJV', '1-esdras', '1 Esdras'),
    ('2ES-KJV', '2-esdras', '2 Esdras'),
    ('1MA-KJV', '1-maccabees-greek', '1 Maccabees (Greek)'),
    ('2MA-KJV', '2-maccabees-greek', '2 Maccabees (Greek)'),
]

HEADING_KIND = [
    (re.compile(r'^ms\d*$'), 'major'),
    (re.compile(r'^mt\d*$'), 'title'),
    (re.compile(r'^s\d*$'), 'section'),
    (re.compile(r'^d$'), 'descriptive'),
    (re.compile(r'^r$'), 'reference'),
    (re.compile(r'^sp$'), 'speaker'),
    (re.compile(r'^sr$'), 'range'),
    (re.compile(r'^is\d*$'), 'intro'),
    (re.compile(r'^imt\d*$'), 'intro-title'),
    (re.compile(r'^mr$'), 'reference'),
]


def heading_kind(style):
    for rx, kind in HEADING_KIND:
        if rx.match(style or ''):
            return kind
    return 'section'


def slugify(name):
    s = (name or '').strip().lower()
    s = s.replace("'", '').replace('’', '')
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s or 'book'


def as_number(value):
    """Verse/chapter numbers are integers in ~99.97% of cases; the rest
    (`3b`, `98a`, `70t`) stay strings so nothing is silently lost."""
    if value is None:
        return None
    s = str(value)
    return int(s) if s.isdigit() else s


# --------------------------------------------------------------------------
# reading the dump
# --------------------------------------------------------------------------

def load_index(root):
    with open(os.path.join(root, 'index.json'), encoding='utf-8') as fh:
        return json.load(fh)


def parse_book(root, col, book):
    """Parse every chapter file of one book. Returns (meta, [chapter dicts])."""
    bdir = os.path.join(root, 'usfm', col['dir'], book['dir'])
    if not os.path.isdir(bdir):
        return {}, []
    meta = {}
    chapters = []
    warnings = []
    for fn in sorted(f for f in os.listdir(bdir) if f.endswith('.usfm')):
        num = int(fn[:-5])
        with open(os.path.join(bdir, fn), encoding='utf-8', errors='replace') as fh:
            src = fh.read()
        parsed = ChapterParser(warnings.append).parse(src)
        for k, v in parsed['meta'].items():
            meta.setdefault(k, []).extend(v if isinstance(v, list) else [v])
        if num == 0 and not parsed['verses'] and not parsed['chapter']:
            continue
        chapters.append(build_chapter(parsed, num))
    return meta, chapters


def build_chapter(parsed, fallback_no):
    """Flat verses + positional headings.

    Section headings are edition-specific and do not line up across editions,
    so they are recorded as markers pointing at the verse they precede rather
    than as containers wrapping the verses.
    """
    paragraphs = parsed['paragraphs']
    verse_index = {}
    order = []
    for v in parsed['verses']:
        verse_index[id(v)] = v
        order.append(v)

    # which verse does each heading precede?
    headings = []
    pending = []
    for p in paragraphs:
        if p.get('heading'):
            text = p.get('text')
            if text:
                # match on the literal marker (`ms1`), not the normalised
                # lookup key (`ms#`), which no pattern would match
                pending.append({'style': p['style'],
                                'kind': heading_kind(p['style']),
                                'text': text})
            continue
        first = None
        for node in p['content']:
            if node['type'] == 'verse':
                first = node['ref']
                break
        if pending:
            for h in pending:
                h['before'] = as_number(first['verse']) if first is not None else None
                headings.append(h)
            pending = []
    for h in pending:                       # trailing headings, nothing after
        h['before'] = None
        headings.append(h)

    verses = []
    for v in order:
        segs = verse_segments(v, paragraphs)
        rec = {'n': as_number(v['verse']),
               't': norm_space(' '.join(t for _, t in segs))}
        if v.get('verse_alt'):
            rec['alt'] = v['verse_alt']
        # only carry the line breakdown when it actually adds something
        if len(segs) > 1:
            rec['lines'] = [{'style': s, 't': t} for s, t in segs]
        if v.get('cross_refs'):
            rec['refs'] = [_ref(x) for x in v['cross_refs']]
        if v.get('footnotes'):
            rec['notes'] = [_note(x) for x in v['footnotes']]
        verses.append(rec)

    out = {'n': as_number(parsed['chapter']) or fallback_no, 'verses': verses}
    if headings:
        out['headings'] = headings
    alt = parsed['meta'].get('chapter_alt')
    if alt:
        out['alt'] = alt[0]
    return out


def _ref(x):
    r = {}
    if x.get('xo'):
        r['origin'] = ' '.join(x['xo'])
    if x.get('xt'):
        r['target'] = ' '.join(x['xt'])
    if x.get('text') and not r:
        r['target'] = x['text']
    return r


def _note(x):
    r = {}
    if x.get('fr'):
        r['origin'] = ' '.join(x['fr'])
    body = []
    for k in ('ft', 'fq', 'fqa', 'fk', 'fv', 'fp'):
        if x.get(k):
            body.extend(x[k])
    if x.get('text'):
        body.append(x['text'])
    if body:
        r['text'] = ' '.join(body)
    if x.get('caller'):
        r['caller'] = x['caller']
    return r


# --------------------------------------------------------------------------
# main build
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('root', help='dump root (contains index.json and usfm/)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--indent', type=int, default=1, help='0 for compact')
    args = ap.parse_args()

    root = args.root
    out = args.out
    indent = args.indent or None
    index = load_index(root)
    cols = {c['id']: c for c in index['collections']}

    missing = [e['collection'] for e in EDITIONS if e['collection'] not in cols]
    if missing:
        sys.exit('collections not found in the dump: %s' % missing)

    # ---- canon registry ------------------------------------------------
    canon_col = cols[CANON_SOURCE]
    english = {b['id']: b['name'] for b in cols[ENGLISH_SOURCE]['books']}

    canon = []
    seen = set()
    unnamed = []
    for i, b in enumerate(canon_col['books'], 1):
        bid = b['id']
        if bid in seen:
            continue
        seen.add(bid)
        if bid in STANDARD_66:
            en = english.get(bid) or bid
            slug = slugify(en)
        elif bid in EOTC_BOOKS:
            slug, en = EOTC_BOOKS[bid]
        else:
            slug, en = slugify(bid), bid
            unnamed.append(bid)
        canon.append({
            'id': bid,
            'order': i,
            'slug': slug,
            'file': '%02d-%s.json' % (i, slug),
            'name_en': en,
            'testament': TESTAMENT.get(b.get('group')),
            'section': b.get('section'),
        })
    for j, (bid, slug, en) in enumerate(CANON_EXTRA, len(canon) + 1):
        canon.append({
            'id': bid, 'order': j, 'slug': slug,
            'file': '%02d-%s.json' % (j, slug), 'name_en': en,
            'testament': 'deuterocanonical', 'section': None,
        })
    canon_by_id = {c['id']: c for c in canon}
    if unnamed:
        print('WARNING: no English name/slug defined for: %s' % unnamed, file=sys.stderr)

    os.makedirs(out, exist_ok=True)
    _write(os.path.join(out, 'canon.json'), canon, indent)

    # ---- per-language UI names ----------------------------------------
    # English comes from the canon table, not from the KJV collection: outside
    # the standard 66 the KJV names describe different books (see EOTC_BOOKS).
    names = {'en': {c['id']: {'name': c['name_en']} for c in canon}}
    for ed in EDITIONS:
        lang = ed['language']
        if lang == 'en':
            continue
        col = cols[ed['collection']]
        bucket = names.setdefault(lang, {})
        for b in col['books']:
            if b['id'] in canon_by_id and b['id'] not in bucket:
                entry = {'name': b['name']}
                if b.get('vernacular'):
                    entry['abbr'] = b['vernacular']
                bucket[b['id']] = entry
    os.makedirs(os.path.join(out, 'names'), exist_ok=True)
    for lang, bucket in names.items():
        ordered = {c['id']: bucket[c['id']] for c in canon if c['id'] in bucket}
        _write(os.path.join(out, 'names', '%s.json' % lang), ordered, indent)

    # ---- editions -------------------------------------------------------
    edition_index = []
    for ed in EDITIONS:
        col = cols[ed['collection']]
        edir = os.path.join(out, ed['id'])
        bdir = os.path.join(edir, 'books')
        os.makedirs(bdir, exist_ok=True)

        remap = ed.get('remap', {})
        book_entries = []
        n_ch = n_v = 0
        for pos, b in enumerate(col['books'], 1):
            canon_id = remap.get(b['id'], b['id'])
            entry = canon_by_id.get(canon_id)
            if entry is None:
                continue
            meta, chapters = parse_book(root, col, b)
            if not chapters:
                continue                     # stub books (ESG, MAN, SUS, ...)
            doc = {
                'edition': ed['id'],
                'book': entry['id'],
                'usfm_id': b['id'],
                'order': entry['order'],
                'chapters': chapters,
            }
            _write(os.path.join(bdir, entry['file']), doc, indent)
            nv = sum(len(c['verses']) for c in chapters)
            n_ch += len(chapters)
            n_v += nv
            book_entries.append({
                'id': entry['id'],
                'usfm_id': b['id'],
                'file': 'books/' + entry['file'],
                'order': entry['order'],
                'position': pos,
                'name': b['name'],
                'abbr': b.get('vernacular'),
                'chapters': len(chapters),
                'verses': nv,
            })

        meta = {k: v for k, v in ed.items() if k != 'collection'}
        meta.update({
            'language_name': LANG_NAMES.get(ed['language'], ed['language']),
            'direction': 'ltr',
            'source': {'project': PROJECT, 'dataset': DATASET,
                       'collection': ed['collection'],
                       'collection_name': col['name']},
            'stats': {'books': len(book_entries), 'chapters': n_ch, 'verses': n_v},
            'books': book_entries,
        })
        _write(os.path.join(edir, 'meta.json'), meta, indent)
        edition_index.append({k: meta[k] for k in
                              ('id', 'title', 'title_en', 'abbrev', 'language',
                               'language_name', 'script', 'year', 'era', 'canon',
                               'publisher', 'stats')})
        print('%-14s %-5s %3d books %6d chapters %7d verses'
              % (ed['id'], ed['collection'], len(book_entries), n_ch, n_v))

    _write(os.path.join(out, 'editions.json'),
           {'editions': edition_index, 'canon': 'canon.json'}, indent)
    print('\ncanon: %d books -> %s' % (len(canon), os.path.join(out, 'canon.json')))


def _write(path, data, indent):
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=indent)


if __name__ == '__main__':
    main()
