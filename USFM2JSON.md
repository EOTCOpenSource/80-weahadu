# USFM → JSON

`usfm2json.py` converts the decrypted Scripture App Builder text into JSON.

```sh
# everything, full structure
python usfm2json.py outputs/mezgebehiwot --out outputs/json

# one collection, shaped like data/am/*.json
python usfm2json.py outputs/mezgebehiwot --out outputs/json-repo \
       --schema repo --collection C18
```

Inputs are the dump produced by the decryptor: a directory holding `index.json`
and `usfm/<collection>/<book>/NNN.usfm`.

Output is one JSON file per book, in a tree that mirrors the `usfm/` layout —
collection folders and filenames carry the vernacular name, not just the id:

```
outputs/json/
  C03 መጽሐፍ ቅዱስ ሰማንያ አሐዱ በአማርኛ/
    001-GEN ኦሪት ዘፍጥረት.json
    002-EXO ኦሪት ዘጸአት.json
    008-RUT መጽሐፈ ሩት.json
  C22 Synaxarium in English/
    001-MAT Synaxarium For Meskerem.json
```

The ordinal sorts, the USFM book id makes files easy to match across
collections, and the Amharic/Ge'ez name makes them readable on their own. Only
characters Windows actually rejects are substituted — the Ethiopic script is
kept intact rather than transliterated away. `--collection` still takes the
bare id (`--collection C03`).

## Where the marker rules come from

The marker semantics are **not guessed from the USFM spec** — they are lifted
out of the app. SAB's engine registers every marker it understands in
`l9.b.d()` (class `smali_classes3/l9/b.smali` in a decompiled SAB APK):

```
c(String name, k8.g category, EnumSet<l9.e> attributes)
```

* `k8.g` — `NONE`, `PARAGRAPH_STYLE`, `CHARACTER_STYLE`
* `l9.e` — 33 semantic flags: `VERSE_NUMBER`, `CHAPTER_NUMBER`,
  `SECTION_HEADING`, `MAJOR_TITLE`, `FOOTNOTE`, `CROSS_REF`, `POETRY`,
  `TABLE`, `LIST_ITEM`, `INTRODUCTION`, `INLINE`, …

That table — 163 markers — was extracted verbatim into **`sab_markers.json`**,
which drives the converter. Nothing about marker behaviour is hardcoded in the
script; change the table and the converter follows.

Marker lookup mirrors the app's own `l9.b.e()`: try the literal name, and on a
miss retry with every digit replaced by `#`. That is why `\mt1` resolves via
`mt#`, `\tc3` via `tc#`, `\zoli2` via `zoli#`.

### Markers this data uses

| Marker | Meaning here |
| --- | --- |
| `\c 1` | chapter number |
| `\v 1` | verse number |
| `\va ፩\va*` | the same verse number in Ge'ez numerals → `verse_alt` |
| `\ca (፩)\ca*` | Ge'ez chapter number → `chapter_alt` |
| `\p` `\m` `\q1` `\q2` `\pc` | paragraph / poetry line styles |
| `\ms1` `\ms2` `\s1` `\s2` `\d` | headings — each opens a new section |
| `\bd` `\it` `\bdit` `\ul` `\wj` `\tl` `\nd` | character styling (kept in `content`, flattened out of `text`) |
| `\x - \xo 1፥1 \xt ኢዮብ 38፥4።\x*` | cross reference → `cross_refs` |
| `\f + \fr 1.2 \ft note\f*` | footnote → `footnotes` |
| `\zoli1` `\zuli1` | ordered / unordered list item |
| `\zon1 3` | start number for the ordered list below |
| `\zbr` | line break |
| `\tr` `\tc1` | table row / cell |
| `\id` `\h` `\toc1..3` `\rem` | book metadata, never body text |
| `\c_SubtleEmphasis` `\p_NormalWeb` | styles imported from Word documents |

The last row is the one trap. SAB keeps imported Word style names verbatim and
declares them in the config's `<styles>` block as CSS selectors —
`span.c_SubtleEmphasis`, `div.p_NormalWeb` — so the prefix *is* the category:
`c_` is a character style, `p_` a paragraph style. The underscore is all that
separates `\c_SubtleEmphasis` from the chapter marker `\c`. There are 18 of
them across 22,410 occurrences; a tokenizer that stops at the underscore reads
them as `\c` and `\p` and corrupts both the chapter numbering and the text.

Two smaller details that matter:

* The single space after an **opening** marker is syntax and is dropped. After
  a **closing** marker (`\bd*`, `\f*`) it is real text — swallowing it glues
  words together across an inline footnote.
* Some source markers are malformed: `\c63`, `\id6800`, `\zbrGalanni`,
  `\zbr-`. The app fails to resolve these and drops them. The converter splits
  a known marker off the glued remainder and keeps the text.

## Output — `--schema rich`

```json
{
  "collection": { "id": "C18", "name": "መጽሐፍ ቅዱስ፣ ሰማንያ አሐዱ በአማርኛ" },
  "book": {
    "id": "GEN", "number": 1, "name": "ኦሪት ዘፍጥረት",
    "group": "OT", "section": "Pentateuch", "testament": "old",
    "usfm_id": "GEN", "toc1": "ኦሪት ዘፍጥረት", "toc3": "ዘፍጥ"
  },
  "chapters": [{
    "chapter": "1",
    "sections": [{
      "title": "የፍጥረት ታሪክ",
      "title_style": "s1",
      "verses": [{
        "verse": "1",
        "verse_alt": "፩",
        "text": "በመጀመሪያ እግዚአብሔር ሰማይንና ምድርን ፈጠረ።",
        "cross_refs": [{ "caller": "-", "style": "x",
                         "xo": ["1፥1"], "xt": ["ኢዮብ 38፥4፤ …"] }]
      }],
      "paragraphs": [{ "style": "p", "text": "…",
                       "poetry": false, "list_item": false,
                       "table_row": false }]
    }]
  }]
}
```

`verses` is the verse-addressable view; `paragraphs` preserves the original
line structure (poetry lines, list items, table rows) for material that has no
verse numbering at all — 14 of the 45 collections are prose with zero `\v`
markers.

## Output — `--schema repo`

Matches the existing `data/am/*.json` layout, so converted books drop straight
into the current pipeline:

```json
{
  "book_number": 1, "book_name_am": "ኦሪት ዘፍጥረት",
  "book_short_name_am": "ዘፍጥ", "book_name_en": "GEN",
  "book_short_name_en": "GEN", "testament": "old",
  "chapters": [{ "chapter": "1",
                 "sections": [{ "title": "የፍጥረት ታሪክ",
                                "verses": [{ "verse": "1", "text": "…" }] }] }]
}
```

Sections with no verses are dropped in this schema and kept in the rich one.

## Result

1,836 books · 20,656 chapters · **398,802 verses** · 107,509 cross references ·
6,644 footnotes · 287,372 Ge'ez verse numbers · 98,986 poetry lines.

The verse total matches the raw `\v` count in the source exactly, and the
cross-reference and footnote totals match their `\x` / `\f` counts once notes
that sit outside any verse (in titles and front matter) are accounted for.

Three markers remain unresolved, each appearing exactly once — `\sll`, `\Mae`,
`\ud`. They are typos in the source; they are listed in
`<out>/_unknown_markers.json` and their text is preserved.

### Which collection matches `data/am`

Every book in `data/am` was scored against C18, C03, C45, C02 and C44.
**C18** (መጽሐፍ ቅዱስ፣ ሰማንያ አሐዱ በአማርኛ) wins 73 of the 75 books that could be
matched by name — usually at 97–100 %. C03 is a genuinely different Amharic
translation, not a variant encoding, and scores 0–13 %.

Comparing all 39,019 shared verses against C18:

| | verses | share |
| --- | ---: | ---: |
| identical | 30,926 | 79.3 % |
| `data/am` is a **prefix** of the converted text | 3,593 | 9.2 % |
| genuinely different | 4,500 | 11.5 % |

The middle row is the interesting one: **`data/am` truncates multi-line verses.**
In poetic books a verse starts on a `\p` line and continues on `\q1`/`\q2`
lines; the existing data kept only the first line. For example Proverbs 1:2 —

```
\v 2 \va ፪\va* ጥበብንና ተግሣጽን ለማወቅ፥
\q2 የጥበብንም ቃል ለማወቅ፥
```

`data/am` has `ጥበብንና ተግሣጽን ለማወቅ፥`; this converter produces the whole verse.
The loss is concentrated exactly where you would expect: Sirach 1,279 verses,
Job 967, Proverbs 731, Song of Solomon 112, Lamentations 87.

The 11.5 % "genuinely different" is concentrated in three books — Psalms
(different versification: 2,426 verses in `data/am` vs 2,470 here),
Didascalia and Baruch — which came from a different source text.

Some individual verses differ because the app's own data has a typo
(`የግዚአብሔርም` for `የእግዚአብሔርም`) that `data/am` had corrected. The converter
reproduces the source faithfully rather than silently fixing it.

Note that a few collections carry two books under the same name — C18 has both
`EST` and a stub `ESG`, whose front matter explains that Esther was split in
the 1980 edition and merged in the 2000 one. `DAG`, `MAN`, `S3Y` and `SUS` are
stubs of the same kind: front matter only, no chapters.

### Known source-data quirks

* 2,038 verses (0.5 %) have no text in the source — only a cross reference
  and/or a Ge'ez number. They are emitted with `"text": ""`.
* The text contains zero-width spaces (`U+200B`) used as line-break hints
  inside Amharic words. They are preserved; strip them if your renderer does
  not want them.
