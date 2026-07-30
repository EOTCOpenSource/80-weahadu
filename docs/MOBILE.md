# SQLite for the mobile apps

`build_sqlite.py` turns `data/bible` into SQLite databases with full-text
search. Reading a chapter takes ~2 ms and a paginated search 8–60 ms.

```sh
python tools/build_sqlite.py data/bible --out dist/sqlite --gzip
```

`dist/` is gitignored — 191 MB of generated output doesn't belong in the repo.
Publish the files as **GitHub Release assets** and have the app download from
there, so the mobile artifacts aren't coupled to the web deployment.

## What gets built

| file | size | gzipped | what |
| --- | ---: | ---: | --- |
| `catalog.db` | 0.1 MB | 0.04 MB | canon, book names in 5 languages, edition list |
| `am-2000.db` | 30.3 MB | 13.9 MB | 44,200 verses |
| `am-1980.db` | 28.4 MB | 13.5 MB | 44,290 verses |
| `gez-1980.db` | 26.6 MB | 12.5 MB | 44,283 verses |
| `gez-2014.db` | 4.1 MB | 2.0 MB | 7,958 verses (NT only) |
| `en-kjv.db` | 20.8 MB | 11.7 MB | 37,145 verses |
| `am-nasv-2001.db` | 22.1 MB | 9.6 MB | 31,103 verses |
| `am-1962.db` | 16.7 MB | 8.1 MB | 30,558 verses |
| `ti-1997.db` | 19.3 MB | 9.0 MB | 30,740 verses |
| `om-kitaaba.db` | 22.5 MB | 11.6 MB | 31,103 verses |

**Bundle `catalog.db`** in the app — it is small, and it lets you show the
edition picker and a localized book list before anything is downloaded.
**Download edition databases on demand**, so a reader who only wants Amharic
never pays for the other eight.

## ⚠️ You must bundle SQLite, not use the system one

The search index uses the **`trigram`** tokenizer, which needs **SQLite 3.34+**
(released Dec 2020). Android's *system* SQLite is older than that on older
Android releases, so `sqflite` — which uses the system library — will fail to
query the index on those devices.

Use a bundled SQLite instead:

```yaml
dependencies:
  sqlite3: ^2.4.0
  sqlite3_flutter_libs: ^0.5.20   # ships a modern SQLite with FTS5
  path_provider: ^2.1.0
  http: ^1.2.0
  archive: ^3.6.0                 # only if you download the .gz
```

If you are locked to the system SQLite, rebuild with
`--tokenizer unicode61` (works back to SQLite 3.9). You lose recall — see
[Why trigram](#why-trigram) below.

## Why trigram

Amharic, Ge'ez and Tigrinya are agglutinative. እግዚአብሔር appears in the text as
የእግዚአብሔርም, ለእግዚአብሔር, እግዚአብሔርን and so on. A word-boundary tokenizer only
matches the bare form:

| query `እግዚአብሔር` in `am-2000` | hits | time |
| --- | ---: | ---: |
| `trigram` | **10,353** | 97 ms |
| `unicode61` (with `*`) | 6,752 | 9 ms |
| `LIKE '%…%'`, no index | 10,353 | 118 ms |

Trigram finds everything a substring search would, at index speed. It costs
about 42 % more disk. The 97 ms is a worst case — that is `count(*)` over the
single most common word in the Bible; a `LIMIT 20` page returns in ~57 ms, and
ordinary words land in under 10 ms.

## Schema

**`catalog.db`**

```sql
edition(id, title, title_en, abbrev, language, language_name, script,
        direction, year, era, canon, publisher, books, chapters, verses, file)
canon(id, ord, slug, name_en, testament, section)
book_name(lang, book, name, abbr)          -- book names per UI language
```

**`<edition>.db`**

```sql
meta(key, value)                            -- title, language, year, tokenizer…
book(id, ord, position, name, abbr, chapters, verses)
chapter(book, n, alt, verses)
verse(id, book, chapter, ord, verse, label, alt, text, lines, refs, notes)
heading(book, chapter, before, ord, kind, style, text)
verse_fts                                   -- FTS5 over verse.text
```

Notes on `verse`:

* `ord` is the position in the chapter and is **always** safe to sort by.
  `verse` is the integer number and is `NULL` for ~100 unnumbered verses;
  `label` is the display string and covers the three odd ones (`3b`, `98a`).
* `alt` is the Ge'ez numeral (፩), on 287k verses.
* `lines`, `refs`, `notes` are **JSON strings**, `NULL` when absent. `lines`
  only appears on the 35,690 verses that span more than one line (poetry).

`heading.before` is the verse number the heading precedes; `NULL` means end of
chapter. Headings are positional rather than nested because section headings
differ between editions and would otherwise break a parallel view.

## Using it from Flutter

### Open a database

```dart
import 'package:sqlite3/sqlite3.dart';
import 'package:path_provider/path_provider.dart';

Future<Database> openEdition(String editionId) async {
  final dir = await getApplicationSupportDirectory();
  return sqlite3.open('${dir.path}/bibles/$editionId.db', mode: OpenMode.readOnly);
}
```

Open read-only: it stops SQLite creating `-wal`/`-shm` side files next to a
database you never write to.

### Download an edition

```dart
Future<void> fetchEdition(String id) async {
  final dir = await getApplicationSupportDirectory();
  final out = File('${dir.path}/bibles/$id.db');
  if (out.existsSync()) return;
  await out.parent.create(recursive: true);

  final url = 'https://github.com/EOTCOpenSource/80-weahadu'
              '/releases/latest/download/$id.db.gz';
  final res = await http.get(Uri.parse(url));
  final tmp = File('${out.path}.part');
  await tmp.writeAsBytes(GZipDecoder().decodeBytes(res.bodyBytes));
  await tmp.rename(out.path);      // atomic: a killed download never half-installs
}
```

### Render a chapter

```dart
final headings = db.select(
  'SELECT before, kind, text FROM heading '
  'WHERE book = ? AND chapter = ? ORDER BY ord', [book, chapter]);

final verses = db.select(
  'SELECT ord, verse, label, alt, text, lines FROM verse '
  'WHERE book = ? AND chapter = ? ORDER BY ord', [book, chapter]);
```

Group the headings by `before` and emit them ahead of the matching verse. If
`lines` is non-null, decode it and render each entry as its own line, indenting
on `style` (`q1`, `q2`, `q3`); otherwise render `text` as one paragraph.

### Search

```dart
final rows = db.select('''
  SELECT v.book, v.chapter, v.label,
         snippet(verse_fts, 0, '<b>', '</b>', '…', 10) AS snippet
  FROM verse_fts JOIN verse v ON v.id = verse_fts.rowid
  WHERE verse_fts MATCH ?
  ORDER BY rank
  LIMIT 20 OFFSET ?
''', ['"$query"', page * 20]);
```

Wrap the term in double quotes so FTS5 treats it as a literal phrase — user
input containing `*`, `-`, `:` or `AND` is otherwise parsed as query syntax and
throws. Always paginate: some terms match ten thousand verses.

### The book list, in the reader's UI language

```dart
final books = catalog.select('''
  SELECT c.id, c.ord, c.testament, n.name, n.abbr
  FROM canon c
  LEFT JOIN book_name n ON n.book = c.id AND n.lang = ?
  ORDER BY c.ord
''', [uiLanguage]);
```

Book *names* come from `catalog.db` when you want them in the UI language, and
from the edition's own `book` table when you want what that edition calls them.
Both are correct for different screens.

### Parallel view

`book.id` is stable across editions, so a two-pane comparison is just the same
query against two databases:

```dart
final am  = amDb.select('SELECT ord,label,text FROM verse WHERE book=? AND chapter=? ORDER BY ord', ['GEN', 1]);
final gez = gezDb.select('SELECT ord,label,text FROM verse WHERE book=? AND chapter=? ORDER BY ord', ['GEN', 1]);
```

Align on `verse`, not `ord` — versification differs between editions
(Tigrinya's Genesis 1 has 30 verses where Amharic has 31), so row *n* of one
is not row *n* of the other.

Five deuterocanonical ids mean different books in KJV than in the EOTC
editions, so they were given separate canon slots (`1MA-KJV`, `LJE-KJV`, …).
Joining on `book.id` therefore never pairs the Ethiopic Maccabees with the
Greek ones. See [BIBLE.md](BIBLE.md).

## Staying up to date without shipping an app

A corrected verse should not need a store release. Each database records the
data revision it was built from:

```sql
SELECT value FROM meta WHERE key = 'revision';   -- e.g. 2
SELECT value FROM meta WHERE key = 'baseline';   -- e.g. 1
```

The site publishes `data/bible/revisions.json`. Poll it on launch and patch
what has moved — a typical correction release is a **68 KB patch** against a
**14 MB** database, so patching is roughly 200× cheaper than re-downloading.

```dart
Future<void> syncEdition(Database db, String id) async {
  final manifest = jsonDecode((await http.get(Uri.parse(
      'https://<your-site>/data/bible/revisions.json'))).body);
  final remote = manifest['editions'][id];
  final local = int.parse(db.select(
      "SELECT value FROM meta WHERE key='revision'").first['value'] as String);

  if (local >= remote['revision']) return;               // already current

  if (local < (remote['baseline'] as int)) {             // too far behind
    await fetchEdition(id);                              // full download
    return;
  }

  for (var r = local + 1; r <= remote['revision']; r++) {
    final patch = jsonDecode((await http.get(Uri.parse(
        'https://<your-site>/data/bible/patches/$id/$r.json'))).body);
    db.execute('BEGIN');
    for (final op in patch['ops']) {
      db.execute(
        'UPDATE verse SET ${op['field'] == 'alt' ? 'alt' : 'text'} = ? '
        'WHERE book = ? AND chapter = ? AND verse = ?',
        [op['to'], op['book'], op['chapter'], op['verse']]);
    }
    db.execute("UPDATE meta SET value = ? WHERE key = 'revision'", ['$r']);
    db.execute('COMMIT');
  }
}
```

Three things this has to get right:

* **Open the database writable** for syncing. The read-only handle in
  [Open a database](#open-a-database) is for reading; use a separate writable
  connection here.
* **Apply each revision in its own transaction** and update `meta.revision`
  inside it. A sync killed midway then resumes from the last complete
  revision rather than half-applying one.
* **Rebuild the search index** if you ever patch enough text to matter:
  `INSERT INTO verse_fts(verse_fts) VALUES('rebuild');`. FTS5 external-content
  tables do not follow `UPDATE`s on the content table automatically, so a
  patched verse stays searchable under its *old* text until you rebuild. For a
  handful of verses this is cosmetic; do it after a large patch.

When `baseline` moves, `data/bible` was regenerated wholesale and patching
across it is not meaningful — download the database again and verify its
`sha256` from the manifest.

See [RELEASING.md](RELEASING.md) for the publishing side.

## Verifying a build

```sh
sqlite3 dist/sqlite/am-2000.db "PRAGMA integrity_check;"
sqlite3 dist/sqlite/am-2000.db \
  "SELECT (SELECT count(*) FROM verse) = (SELECT count(*) FROM verse_fts);"
```

Both should return `ok` and `1`. The build checks FTS5 support before it starts
and exits with a clear message if the tokenizer is unavailable.
