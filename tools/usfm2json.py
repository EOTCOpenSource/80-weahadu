#!/usr/bin/env python3
"""Convert the decrypted Scripture App Builder USFM into JSON.

The marker semantics are not guessed -- they are lifted from the app itself.
The SAB engine registers every marker it understands in `l9.b.d()` as

    c(String name, k8.g category, EnumSet<l9.e> attributes)

with category one of NONE / PARAGRAPH_STYLE / CHARACTER_STYLE and attributes
drawn from a 33-value enum (VERSE_NUMBER, SECTION_HEADING, FOOTNOTE,
CROSS_REF, POETRY, TABLE, ...). That table was extracted verbatim into
`sab_markers.json`, which drives this converter.

Marker lookup follows the app's own `l9.b.e()`: try the literal name, and on a
miss retry with every digit replaced by '#' (so `mt1` resolves via `mt#`,
`tc3` via `tc#`, `zoli2` via `zoli#`).

Two output schemas:

  --schema rich   full structure: sections, paragraphs, verses, inline spans,
                  footnotes, cross references, alternate (Ge'ez) verse numbers.
  --schema repo   matches the existing legacy/am/*.json shape:
                  book_name_am / chapters[] / sections[] / verses[{verse,text}]

Usage:
    python usfm2json.py outputs/source --out outputs/json
    python usfm2json.py outputs/source --out outputs/json --collection C03
    python usfm2json.py outputs/source --out outputs/json --schema repo
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# --------------------------------------------------------------------------
# marker table (extracted from the app)
# --------------------------------------------------------------------------

with open(os.path.join(HERE, 'sab_markers.json'), encoding='utf-8') as fh:
    MARKERS = json.load(fh)

# Markers that occur in this data but are absent from the app's own registry,
# so the app silently drops them. Standard USFM defines them, and they carry
# real content, so they are handled here rather than lost.
#   \ca (፩)\ca*  -- alternate (Ge'ez) chapter number, the \c counterpart of \va
EXTENSIONS = {
    'ca': {'category': 'CHARACTER_STYLE', 'attrs': ['INLINE', 'CHAPTER_CHARACTER']},
}
for _name, _spec in EXTENSIONS.items():
    MARKERS.setdefault(_name, _spec)


def has_attr(name, attr):
    m = MARKERS.get(name)
    return bool(m) and attr in m['attrs']


def category(name):
    m = MARKERS.get(name)
    return m['category'] if m else None


# Markers whose *content is not body text*: they carry metadata about the book
# rather than scripture, so their text never lands in a verse.
META_MARKERS = {'id', 'ide', 'h', 'toc1', 'toc2', 'toc3', 'toca1', 'toca2',
                'toca3', 'rem', 'sts', 'usfm', 'restore', 'periph'}

# Note-like markers open a container closed by \x* / \f* etc.
NOTE_MARKERS = {n for n in MARKERS
                if has_attr(n, 'FOOTNOTE') or has_attr(n, 'CROSS_REF')}
NOTE_OPENERS = {'f', 'fe', 'ef', 'fdc', 'x', 'ex', 'xdc'}

HEADING_ATTR = 'SECTION_HEADING'
MAJOR_TITLE_ATTR = 'MAJOR_TITLE'

# Standard USFM ids, used to derive a testament when the book uses them.
OT_IDS = """GEN EXO LEV NUM DEU JOS JDG RUT 1SA 2SA 1KI 2KI 1CH 2CH EZR NEH
EST JOB PSA PRO ECC SNG ISA JER LAM EZK DAN HOS JOL AMO OBA JON MIC NAM HAB
ZEP HAG ZEC MAL""".split()
NT_IDS = """MAT MRK LUK JHN ACT ROM 1CO 2CO GAL EPH PHP COL 1TH 2TH 1TI 2TI
TIT PHM HEB JAS 1PE 2PE 1JN 2JN 3JN JUD REV""".split()

GROUP_TESTAMENT = {'OT': 'old', 'NT': 'new', 'NTC': 'new', 'DC': 'deuterocanonical'}

# --------------------------------------------------------------------------
# tokenizer
# --------------------------------------------------------------------------

# A marker is a backslash, an optional '+' (nested character marker), the
# name, an optional '*' (closing form), then -- for *opening* markers only --
# one separating space that belongs to the syntax rather than the content.
# After a closing marker (\bd*, \f*) any space is real text: swallowing it
# glues words together across an inline footnote.
TOKEN_RE = re.compile(r'\\(\+?)([A-Za-z][A-Za-z0-9_\-]*)(\*?)([ \t]?)')
DIGITS_RE = re.compile(r'\d')
GLUED_NUM_RE = re.compile(r'^([A-Za-z]+?)(\d+)$')
GLUED_WORD_RE = re.compile(r'^(zbr|zhr)(\S.*)$')

# Styles imported from Word documents keep their original names, prefixed to
# say how SAB renders them: the app's <styles> block declares them as CSS
# selectors -- `span.c_SubtleEmphasis` (character) and `div.p_NormalWeb`
# (paragraph) -- so the prefix is the category. The underscore is what
# distinguishes them from the built-in markers `\c` and `\p`.
IMPORTED_RE = re.compile(r'^([cp])_[A-Za-z0-9_\-]+$')


class Tok:
    __slots__ = ('kind', 'name', 'closing', 'nested', 'text')

    def __init__(self, kind, name=None, closing=False, nested=False, text=''):
        self.kind = kind          # 'marker' | 'text'
        self.name = name
        self.closing = closing
        self.nested = nested
        self.text = text

    def __repr__(self):
        return ('<%s %s%s>' % (self.kind, self.name or '', '*' if self.closing else '')
                if self.kind == 'marker' else '<text %r>' % self.text[:30])


def resolve(name):
    """Mirror the app's marker lookup; return (canonical, glued_extra).

    glued_extra is the text that was jammed onto the marker in malformed
    source (e.g. `\\c63`, `\\zbrGalanni`), which the app would otherwise
    fail to resolve at all.
    """
    if name in MARKERS:
        return name, None
    m = IMPORTED_RE.match(name)
    if m:
        MARKERS[name] = {
            'category': 'CHARACTER_STYLE' if m.group(1) == 'c' else 'PARAGRAPH_STYLE',
            'attrs': ['INLINE'] if m.group(1) == 'c' else ['PARAGRAPH'],
            'imported': True,
        }
        return name, None
    normalized = DIGITS_RE.sub('#', name)
    if normalized in MARKERS:
        return normalized, None
    m = GLUED_NUM_RE.match(name)
    if m and m.group(1) in MARKERS:
        return m.group(1), m.group(2)
    m = GLUED_WORD_RE.match(name)
    if m:
        return m.group(1), m.group(2)
    return None, None


def tokenize(src):
    out = []
    pos = 0
    for m in TOKEN_RE.finditer(src):
        if m.start() > pos:
            out.append(Tok('text', text=src[pos:m.start()]))
        raw = m.group(2)
        closing = m.group(3) == '*'
        canonical, glued = resolve(raw)
        out.append(Tok('marker', name=canonical or raw, closing=closing,
                       nested=m.group(1) == '+'))
        out[-1].text = raw           # keep the literal for warnings
        if glued:
            out.append(Tok('text', text=glued + ' '))
        pos = m.end()
        if closing and m.group(4):
            pos -= len(m.group(4))   # give the space back to the content
    if pos < len(src):
        out.append(Tok('text', text=src[pos:]))
    return out


# --------------------------------------------------------------------------
# text helpers
# --------------------------------------------------------------------------

def norm_space(s):
    return re.sub(r'[ \t\r\n\u00a0]+', ' ', s).strip()


def flatten(nodes):
    """Plain text of a content tree.

    Nodes flagged `captured` hold data lifted out into its own field
    (alternate verse/chapter numbers) and must not reappear in body text.
    """
    parts = []
    for n in nodes:
        if n.get('captured'):
            continue
        if n['type'] == 'text':
            parts.append(n['text'])
        elif n['type'] == 'char':
            parts.append(flatten(n['content']))
        elif n['type'] == 'break':
            parts.append(' ')
    return ''.join(parts)


# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------

class ChapterParser:
    """Parse one chapter file into paragraphs / verses / notes."""

    def __init__(self, warn):
        self.warn = warn

    def parse(self, src):
        toks = tokenize(src)
        self.meta = {}
        self.paragraphs = []
        self.chapter_num = None
        self.para = None           # current paragraph dict
        self.stack = []            # open character markers -> content lists
        self.verse = None          # current verse dict
        self.pending_alt = None
        self.verses = []           # ordered verse records
        self.notes_target = None   # note dict currently being filled
        self.note_field = None

        i = 0
        n = len(toks)
        while i < n:
            t = toks[i]
            if t.kind == 'text':
                self.add_text(t.text)
                i += 1
                continue
            i = self.handle_marker(toks, i)
        self.close_paragraph()
        return {
            'meta': self.meta,
            'chapter': self.chapter_num,
            'paragraphs': self.paragraphs,
            'verses': self.verses,
        }

    # -- content sinks -----------------------------------------------------

    def sink(self):
        """Where text currently goes."""
        if self.notes_target is not None:
            return self.notes_target['_content']
        if self.stack:
            return self.stack[-1]['content']
        if self.para is None:
            self.open_paragraph('p')
        return self.para['content']

    def add_text(self, text):
        if not text:
            return
        if self.meta_sink is not None:
            self.meta_sink.append(text)
            return
        sink = self.sink()
        if sink and sink[-1]['type'] == 'text':
            sink[-1]['text'] += text
        else:
            sink.append({'type': 'text', 'text': text})

    meta_sink = None

    # -- paragraphs --------------------------------------------------------

    def open_paragraph(self, style, literal=None):
        self.close_paragraph()
        self.para = {'style': literal or style, 'lookup': style, 'content': [],
                     'poetry': has_attr(style, 'POETRY'),
                     'heading': has_attr(style, HEADING_ATTR) or has_attr(style, MAJOR_TITLE_ATTR),
                     'table_row': style == 'tr',
                     'list_item': has_attr(style, 'LIST_ITEM') or has_attr(style, 'LIST'),
                     'ordered': (style.startswith('zoli') or style.startswith('ili'))
                                if has_attr(style, 'LIST_ITEM') or has_attr(style, 'LIST')
                                else None,
                     'introduction': has_attr(style, 'INTRODUCTION')}

    def close_paragraph(self):
        while self.stack:
            self.stack.pop()
        if self.para is not None:
            text = norm_space(flatten(self.para['content']))
            # `\p` followed only by a newline is a layout artefact of the
            # source, not a paragraph. Keep verse-bearing ones regardless:
            # a handful of verses legitimately have no text.
            has_verse = any(n['type'] == 'verse' for n in self.para['content'])
            if text or has_verse:
                self.para['text'] = text
                self.paragraphs.append(self.para)
        self.para = None

    # -- markers -----------------------------------------------------------

    def handle_marker(self, toks, i):
        t = toks[i]
        name = t.name
        known = name in MARKERS

        if not known:
            self.warn(t.text)
            return i + 1

        if t.closing:
            self.close_marker(name)
            return i + 1

        cat = category(name)

        # --- metadata lines (\id \toc1 \h \rem ...) -----------------------
        if name in META_MARKERS:
            self.close_paragraph()
            buf = []
            self.meta_sink = buf
            i += 1
            while i < len(toks) and not (toks[i].kind == 'marker' and not toks[i].closing):
                if toks[i].kind == 'text':
                    buf.append(toks[i].text)
                i += 1
            self.meta_sink = None
            value = norm_space(''.join(buf))
            if value:
                self.meta.setdefault(name, []).append(value)
            return i

        # --- chapter ------------------------------------------------------
        if has_attr(name, 'CHAPTER_NUMBER'):
            self.close_paragraph()
            num, rest = self.take_number(toks, i + 1)
            self.chapter_num = num
            return rest

        # --- verse --------------------------------------------------------
        if has_attr(name, 'VERSE_NUMBER'):
            num, rest = self.take_number(toks, i + 1)
            self.start_verse(num)
            return rest

        # --- notes (footnote / cross reference) ---------------------------
        if name in NOTE_OPENERS:
            return self.read_note(toks, i)

        # --- headings & paragraph styles ----------------------------------
        if cat == 'PARAGRAPH_STYLE':
            self.open_paragraph(name, t.text)
            return i + 1

        if name == 'b':            # blank line
            self.close_paragraph()
            return i + 1

        if name in ('zbr', 'zhr'):
            self.sink().append({'type': 'break', 'style': name})
            return i + 1

        if name == 'tr':           # table row
            self.open_paragraph('tr')
            return i + 1

        # SAB's own list markers (\zoli1 ordered, \zuli1 unordered) sit in the
        # NONE category but behave as line-level elements, so they open a
        # paragraph rather than running on into the previous one.
        if has_attr(name, 'LIST_ITEM'):
            self.open_paragraph(name, t.text)
            return i + 1

        # \zon1 <n> only carries the start number for the ordered list below it.
        if has_attr(name, 'LIST_ITEM_SETTINGS'):
            self.close_paragraph()
            num, rest = self.take_number(toks, i + 1)
            self.meta.setdefault('list_start', []).append(num)
            return rest

        # --- character styles ---------------------------------------------
        if cat == 'CHARACTER_STYLE' or has_attr(name, 'INLINE'):
            node = {'type': 'char', 'style': name, 'literal': t.text, 'content': []}
            self.sink().append(node)
            self.stack.append(node)
            return i + 1

        # anything else: ignore the marker, keep its text inline
        return i + 1

    def close_marker(self, name):
        for idx in range(len(self.stack) - 1, -1, -1):
            if self.stack[idx]['style'] == name:
                closed = self.stack[idx]
                del self.stack[idx:]
                value = norm_space(flatten(closed['content']))
                # \va/\vp carry an alternate rendering of the verse number and
                # \ca/\cp of the chapter number: lift them out of the body text.
                if closed['style'] in ('va', 'vp') and self.verse is not None:
                    self.verse['verse_alt'] = value
                    closed['captured'] = True
                elif closed['style'] in ('ca', 'cp'):
                    self.meta.setdefault('chapter_alt', []).append(value)
                    closed['captured'] = True
                return
        # stray closer -- harmless, the app ignores it too

    def take_number(self, toks, i):
        """Read the numeric argument that follows \\c or \\v."""
        num = None
        while i < len(toks):
            t = toks[i]
            if t.kind != 'text':
                break
            m = re.match(r'\s*([0-9]+(?:[-\u2013][0-9]+)?[a-z]?)\s*(.*)$', t.text, re.S)
            if m:
                num = m.group(1)
                rest = m.group(2)
                toks[i] = Tok('text', text=rest)
                return num, i
            if t.text.strip() == '':
                i += 1
                continue
            break
        return num, i

    def start_verse(self, num):
        if self.para is None:
            self.open_paragraph('p')
        self.verse = {'verse': num, 'verse_alt': None, 'content': [],
                      'footnotes': [], 'cross_refs': []}
        self.verses.append(self.verse)
        marker = {'type': 'verse', 'verse': num, 'ref': self.verse}
        self.para['content'].append(marker)

    # -- notes -------------------------------------------------------------

    def read_note(self, toks, i):
        opener = toks[i].name
        kind = 'cross_ref' if has_attr(opener, 'CROSS_REF') else 'footnote'
        note = {'style': opener, 'caller': None, 'fields': [], '_content': []}
        self.notes_target = note
        i += 1

        # caller is the first text token ('+', '-', '*' or a custom symbol)
        if i < len(toks) and toks[i].kind == 'text':
            m = re.match(r'\s*(\S)\s*(.*)$', toks[i].text, re.S)
            if m and m.group(1) in '+-*?':
                note['caller'] = m.group(1)
                toks[i] = Tok('text', text=m.group(2))

        field = None
        depth_done = False
        while i < len(toks) and not depth_done:
            t = toks[i]
            if t.kind == 'text':
                if field is not None:
                    field['content'].append({'type': 'text', 'text': t.text})
                else:
                    note['_content'].append({'type': 'text', 'text': t.text})
                i += 1
                continue
            if t.closing and t.name == opener:
                i += 1
                depth_done = True
                break
            if t.closing:
                if field is not None and field['style'] == t.name:
                    field = None
                i += 1
                continue
            if t.name in MARKERS and (has_attr(t.name, 'FOOTNOTE') or has_attr(t.name, 'CROSS_REF')):
                field = {'style': t.name, 'content': []}
                note['fields'].append(field)
                i += 1
                continue
            # a paragraph marker inside an unterminated note ends it
            if category(t.name) == 'PARAGRAPH_STYLE' or has_attr(t.name, 'VERSE_NUMBER'):
                depth_done = True
                break
            if field is not None:
                field['content'].append({'type': 'text', 'text': ''})
            i += 1

        self.notes_target = None
        rec = {'caller': note['caller'], 'style': note['style']}
        for f in note['fields']:
            rec.setdefault(f['style'], []).append(norm_space(flatten(f['content'])))
        leftover = norm_space(flatten(note['_content']))
        if leftover:
            rec['text'] = leftover
        if self.verse is not None:
            (self.verse['cross_refs'] if kind == 'cross_ref'
             else self.verse['footnotes']).append(rec)
        else:
            self.meta.setdefault('_notes', []).append(rec)
        return i


# --------------------------------------------------------------------------
# assembly into book documents
# --------------------------------------------------------------------------

def verse_text(verse, paragraphs):
    """Concatenate everything belonging to a verse across paragraph breaks."""
    parts = []
    collecting = False
    for p in paragraphs:
        if p.get('heading'):
            continue
        for node in p['content']:
            if node['type'] == 'verse':
                collecting = node['ref'] is verse
                continue
            if collecting:
                parts.append(flatten([node]))
        if collecting:
            parts.append(' ')
    return norm_space(''.join(parts))


def verse_segments(verse, paragraphs):
    """Same walk as verse_text(), but keeping the paragraph boundaries.

    A verse in poetry spans several lines (`\\p` then `\\q1`/`\\q2`); renderers
    need those breaks to indent correctly, so return [(style, text), ...]
    instead of one joined string.
    """
    segs = []
    collecting = False
    for p in paragraphs:
        if p.get('heading'):
            continue
        buf = []
        for node in p['content']:
            if node['type'] == 'verse':
                collecting = node['ref'] is verse
                continue
            if collecting:
                buf.append(flatten([node]))
        if buf:
            text = norm_space(''.join(buf))
            if text:
                segs.append((p['style'], text))
    return segs


def build_chapter(parsed, chapter_no):
    """Group paragraphs into sections keyed by heading, with verses.

    A heading marker opens a new section for everything that follows it.
    Leading material before the first heading forms an untitled section.
    """
    sections = [{'title': None, 'title_style': None, 'verses': [], 'paragraphs': []}]
    section_of_verse = {}
    started = False          # has any body paragraph landed in this section?

    for p in parsed['paragraphs']:
        if p.get('heading'):
            title = p.get('text') or None
            if started or sections[-1]['title']:
                sections.append({'title': title, 'title_style': p['style'],
                                 'verses': [], 'paragraphs': []})
            else:
                sections[-1]['title'] = title
                sections[-1]['title_style'] = p['style']
            started = False
            continue
        started = True
        para = {'style': p['style'], 'text': p.get('text', ''),
                'poetry': p['poetry'], 'list_item': p['list_item'],
                'table_row': p['table_row']}
        if p.get('ordered') is not None:
            para['ordered'] = p['ordered']
        sections[-1]['paragraphs'].append(para)
        for node in p['content']:
            if node['type'] == 'verse':
                section_of_verse.setdefault(id(node['ref']), len(sections) - 1)

    for v in parsed['verses']:
        rec = {
            'verse': v['verse'],
            'verse_alt': v['verse_alt'],
            'text': verse_text(v, parsed['paragraphs']),
        }
        if v['footnotes']:
            rec['footnotes'] = v['footnotes']
        if v['cross_refs']:
            rec['cross_refs'] = v['cross_refs']
        si = section_of_verse.get(id(v), 0)
        if si < len(sections):
            sections[si]['verses'].append(rec)
        else:
            sections[-1]['verses'].append(rec)

    sections = [s for s in sections if s['verses'] or s['paragraphs'] or s['title']]
    alt = parsed['meta'].get('chapter_alt')
    out = {'chapter': parsed['chapter'] or str(chapter_no), 'sections': sections}
    if alt:
        out['chapter_alt'] = alt[0]
    return out


def testament_of(book_id, group):
    if group in GROUP_TESTAMENT:
        return GROUP_TESTAMENT[group]
    if book_id in OT_IDS:
        return 'old'
    if book_id in NT_IDS:
        return 'new'
    return None


def to_repo_schema(doc):
    """Reshape to the existing legacy/am/*.json layout."""
    out = {
        'book_number': doc['book'].get('number'),
        'book_name_am': doc['book']['name'],
        'book_short_name_am': doc['book'].get('toc3') or doc['book'].get('vernacular'),
        'book_name_en': doc['book'].get('id'),
        'book_short_name_en': doc['book'].get('id'),
        'testament': doc['book'].get('testament'),
        'chapters': [],
    }
    for ch in doc['chapters']:
        sections = []
        for s in ch['sections']:
            # the repo layout groups verses under a heading, so a heading with
            # nothing under it (two adjacent headings, e.g. \ms1 then \s1)
            # carries no verses and is dropped here. The rich schema keeps it.
            if not s['verses']:
                continue
            sections.append({
                'title': s['title'],
                'verses': [{'verse': v['verse'], 'text': v['text']}
                           for v in s['verses']],
            })
        out['chapters'].append({'chapter': ch['chapter'], 'sections': sections})
    return out


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------

def convert(root, outdir, schema='rich', only=None, indent=1, quiet=False):
    with open(os.path.join(root, 'index.json'), encoding='utf-8') as fh:
        index = json.load(fh)
    usfm_root = os.path.join(root, 'usfm')
    os.makedirs(outdir, exist_ok=True)

    warnings = {}
    written = 0
    for col in index['collections']:
        if only and col['id'] not in only:
            continue
        # Mirror the usfm/ tree: "C03 መጽሐፍ ቅዱስ ሰማንያ አሐዱ በአማርኛ", not bare "C03".
        col_out = os.path.join(outdir, safe_name(col.get('dir')
                                                 or '%s %s' % (col['id'], col['name'])))
        os.makedirs(col_out, exist_ok=True)
        col_dir = os.path.join(usfm_root, col['dir'])
        for bi, book in enumerate(col['books'], 1):
            bdir = os.path.join(col_dir, book['dir'])
            if not os.path.isdir(bdir):
                continue

            def warn(marker, _c=col['id'], _b=book['id']):
                warnings.setdefault(marker, []).append('%s/%s' % (_c, _b))

            meta = {}
            chapters = []
            files = sorted(f for f in os.listdir(bdir) if f.endswith('.usfm'))
            for fn in files:
                num = int(fn[:-5])
                with open(os.path.join(bdir, fn), encoding='utf-8', errors='replace') as fh:
                    src = fh.read()
                parsed = ChapterParser(warn).parse(src)
                for k, v in parsed['meta'].items():
                    meta.setdefault(k, []).extend(v if isinstance(v, list) else [v])
                if num == 0 and not parsed['verses'] and not parsed['chapter']:
                    continue          # pure front matter
                chapters.append(build_chapter(parsed, num))

            def first(k):
                v = meta.get(k)
                return v[0] if v else None

            doc = {
                'collection': {'id': col['id'], 'name': col['name']},
                'book': {
                    'id': book['id'],
                    'number': bi,
                    'name': book['name'],
                    'vernacular': book.get('vernacular'),
                    'group': book.get('group'),
                    'section': book.get('section'),
                    'testament': testament_of(book['id'], book.get('group')),
                    'usfm_id': first('id'),
                    'toc1': first('toc1'),
                    'toc2': first('toc2'),
                    'toc3': first('toc3'),
                    'header': first('h'),
                },
                'chapters': chapters,
            }
            if schema == 'repo':
                doc = to_repo_schema(doc)

            # "001-GEN ኦሪት ዘፍጥረት.json": ordinal for sorting, book id for
            # matching, vernacular name so the file is readable on its own.
            name = '%03d-%s.json' % (bi, safe_name(book.get('dir')
                                                   or '%s %s' % (book['id'], book['name'])))
            with open(os.path.join(col_out, name), 'w', encoding='utf-8') as fh:
                json.dump(doc, fh, ensure_ascii=False, indent=indent)
            written += 1
            if not quiet and written % 200 == 0:
                print('  %d books...' % written, file=sys.stderr)

    if warnings:
        with open(os.path.join(outdir, '_unknown_markers.json'), 'w', encoding='utf-8') as fh:
            json.dump({k: {'count': len(v), 'books': sorted(set(v))[:10]}
                       for k, v in sorted(warnings.items(), key=lambda kv: -len(kv[1]))},
                      fh, ensure_ascii=False, indent=1)
    return written, warnings


def safe_name(s, maxlen=80):
    """Filesystem-safe name that keeps Ethiopic script intact.

    Only characters Windows actually rejects are replaced -- transliterating
    or stripping to ASCII would erase the Amharic/Ge'ez names entirely.
    """
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', s or '')
    s = re.sub(r'\s+', ' ', s).strip(' .')
    return s[:maxlen].strip() or 'unnamed'


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('root', help='dump root (contains index.json and usfm/)')
    ap.add_argument('--out', required=True, help='output directory')
    ap.add_argument('--schema', choices=['rich', 'repo'], default='rich')
    ap.add_argument('--collection', action='append',
                    help='limit to a collection id (repeatable), e.g. C03')
    ap.add_argument('--indent', type=int, default=1, help='0 for compact')
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()

    written, warnings = convert(args.root, args.out, args.schema,
                                set(args.collection) if args.collection else None,
                                args.indent or None, args.quiet)
    print('wrote %d book files to %s (schema=%s)' % (written, args.out, args.schema))
    if warnings:
        top = sorted(warnings.items(), key=lambda kv: -len(kv[1]))[:8]
        print('unknown markers: %d kinds (see _unknown_markers.json)' % len(warnings))
        for k, v in top:
            print('   \\%s x%d' % (k, len(v)))


if __name__ == '__main__':
    main()
