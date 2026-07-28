# 80 weahadu — ሰማንያ ወአሃዱ

Open scripture data for the Ethiopian Orthodox Tewahedo canon.

**Nine bible editions in five languages — 647 books, 11,225 chapters, 301,380 verses.**
Amharic, Ge'ez, Tigrinya, Afaan Oromoo and English, with cross references,
footnotes, section headings, poetry line structure and Ge'ez verse numerals.

| Path | What |
| --- | --- |
| **`data/bible/`** | the multi-language data set — start here |
| `index.html` | reader web app, reads `data/bible` directly |
| `data/am/`, `minified/` | the original Amharic-only data (v1, see below) |

---

## `data/bible`

```
data/bible/
  canon.json          ordered book registry — the language-neutral join key
  editions.json       index of every edition
  names/am.json       UI book names, one file per UI language
  names/gez.json  names/ti.json  names/om.json  names/en.json
  am-2000/
    meta.json         edition metadata + the names this edition itself uses
    books/01-genesis.json
```

Three things live in three places on purpose:

* **`canon.json`** — identity and order, no language.
* **`names/<lang>.json`** — what to label a book in the *UI* language, so a
  reader can use the Ge'ez text with an English book list.
* **`<edition>/meta.json`** — what *that edition* calls its own books, which
  differs: `gez-1980` calls Matthew ወንጌል ዘማቴዎስ, `am-2000` calls it የማቴዎስ ወንጌል.

Book content files carry **no names at all**. Adding a language means dropping
in one `<edition>/` folder plus one `names/<lang>.json` — no existing file changes.

Filenames are canon-stable: `01-genesis.json` is Genesis in *every* edition, so
a 66-book edition simply has gaps in the numbering rather than renumbering.
Each `meta.json` carries a `position` field with that edition's own display
order (KJV puts Job at 18; the EOTC canon puts it at 27).

### Editions

| id | edition | lang | books | verses |
| --- | --- | --- | ---: | ---: |
| `am-2000` | መጽሐፍ ቅዱስ፣ ሰማንያ አሐዱ በአማርኛ — 2000 ዓ.ም | am | 89 | 44,200 |
| `am-1980` | መጽሐፍ ቅዱስ ሰማንያ አሐዱ በአማርኛ — 1980 ዓ.ም | am | 93 | 44,290 |
| `gez-1980` | መጽሐፍ ቅዱስ ሰማንያ አሐዱ በግእዝ — 1980 ዓ.ም | gez | 93 | 44,283 |
| `gez-2014` | ግእዝ 2014 ዓ.ም *(New Testament only)* | gez | 27 | 7,958 |
| `en-kjv` | King James Version with Apocrypha | en | 81 | 37,145 |
| `am-nasv-2001` | አዲሱ መደበኛ ትርጕም — 2001 GC | am | 66 | 31,103 |
| `am-1962` | ቀዳማዊ ኃይለ ሥላሴ ዘመነ መንግሥት — 1962 ዓ.ም | am | 66 | 30,558 |
| `ti-1997` | ትግርኛ መደበኛ ትርጕም — 1997 ዓ.ም | ti | 66 | 30,740 |
| `om-kitaaba` | Kitaaba Qulqulluu, Afaan Oromoo | om | 66 | 31,103 |

### Book format

```json
{
  "edition": "am-2000", "book": "GEN", "order": 1,
  "chapters": [{
    "n": 1,
    "headings": [
      { "style": "ms1", "kind": "major",   "text": "ምዕራፍ 1",     "before": 1 },
      { "style": "s1",  "kind": "section", "text": "የፍጥረት ታሪክ", "before": 1 }
    ],
    "verses": [{
      "n": 1, "alt": "፩",
      "t": "በመጀመሪያ እግዚአብሔር ሰማይንና ምድርን ፈጠረ።",
      "refs": [{ "origin": "1፥1", "target": "ኢዮብ 38፥4፤ …" }]
    }]
  }]
}
```

* **Verses are flat, headings are positional.** `before` is the verse a heading
  precedes (`null` if nothing follows). Section headings are edition-specific
  and do not line up across editions, so nesting verses inside them would make
  a parallel Amharic/Ge'ez view impossible without re-flattening.
* **`n`** is an integer. Three verses in the whole corpus (`3b`, `98a`, `70t`)
  stay strings rather than being silently coerced.
* **`alt`** — the Ge'ez numeral form of the verse number, on 287k verses.
* **`lines`** — present only when a verse spans more than one line (poetry,
  where a verse starts on `\p` and continues on `\q1`/`\q2`). `t` is always the
  joined text; `lines` lets a renderer indent. 35,690 verses have it.
* **`refs`** cross references, **`notes`** footnotes.

Full details, including the id-collision caveats, are in
**[BIBLE.md](BIBLE.md)**. The USFM → JSON conversion is documented in
**[USFM2JSON.md](USFM2JSON.md)**.

### Regenerating

```sh
python usfm2json.py  <dump> --out outputs/json     # USFM -> JSON
python build_bible.py <dump> --out data/bible      # -> the layout above
```

---

## Canon coverage

### Old Testament
1.  [x] Genesis (ኦሪት ዘፍጥረት)
2.  [x] Exodus (ኦሪት ዘጸአት)
3.  [x] Leviticus (ኦሪት ዘሌዋውያን)
4.  [x] Numbers (ኦሪት ዘኁልቍ)
5.  [x] Deuteronomy (ኦሪት ዘዳግም)
6.  [x] Joshua (መጽሐፈ ኢያሱ ወልደ ነዌ)
7.  [x] Judges (መጽሐፈ መሣፍንት)
8.  [x] Ruth (መጽሐፈ ሩት)
9.  [x] 1 Samuel (መጽሐፈ ሳሙኤል ቀዳማዊ)
10. [x] 2 Samuel (መጽሐፈ ሳሙኤል ካልእ)
11. [x] 1 Kings (መጽሐፈ ነገሥት ቀዳማዊ)
12. [x] 2 Kings (መጽሐፈ ነገሥት ካልእ)
13. [x] 1 Chronicles (መጽሐፈ ዜና መዋዕል ቀዳማዊ)
14. [x] 2 Chronicles (መጽሐፈ ዜና መዋዕል ካልእ)
15. [x] Jubilees (መጽሐፈ ኩፋሌ)
16. [x] Enoch (መጽሐፈ ሄኖክ)
17. [x] Ezra (መጽሐፈ ዕዝራ)
18. [x] Nehemiah (መጽሐፈ ነህምያ)
19. [x] Ezra (Sutu'el) (መጽሐፈ ዕዝራ ሱቱኤል)
20. [x] Ezra (kal) (መጽሐፈ ዕዝራ ካልእ)
21. [x] Tobit (መጽሐፈ ጦቢት)
22. [x] Judith (መጽሐፈ ዮዲት)
23. [x] Esther (መጽሐፈ አስቴር)
24. [x] 1 Maccabees (መጽሐፈ መቃብያን ቀዳማዊ)
25. [x] 2 Maccabees (መጽሐፈ መቃብያን ካልእ)
26. [x] 3 Maccabees (መጽሐፈ መቃብያን ሳልስ)
27. [x] Job (መጽሐፈ ኢዮብ)
28. [x] Psalms (መዝሙረ ዳዊት)
29. [x] Proverbs (መጽሐፈ ምሳሌ)
30. [x] Book of Admonition (መጽሐፈ ተግሳጽ)
31. [x] Wisdom of Solomon (መጽሐፈ ጥበብ)
32. [x] Ecclesiastes (መጽሐፈ መክብብ)
33. [x] Song of Solomon (መኃልየ መኃልይ ዘሰሎሞን)
34. [x] Sirach (መጽሐፈ ሲራክ)
35. [x] Isaiah (ትንቢተ ኢሳይያስ)
36. [x] Jeremiah (ትንቢተ ኤርምያስ)
37. [x] Baruch (መጽሐፈ ባሮክ)
38. [x] Lamentations (ሰቆቃወ ኤርምያስ)
39. [x] Teref Ermias (ተረፈ ኤርምያስ)
40. [x] Teref Baruch (ተረፈ ባሮክ)
41. [x] Ezekiel (ትንቢተ ሕዝቅኤል)
42. [x] Daniel (ትንቢተ ዳንኤል)
43. [x] Hosea (ትንቢተ ሆሴዕ)
44. [x] Amos (ትንቢተ አሞጽ)
45. [x] Micah (ትንቢተ ሚክያስ)
46. [x] Joel (ትንቢተ ኢዮኤል)
47. [x] Obadiah (ትንቢተ አብድዩ)
48. [x] Jonah (ትንቢተ ዮናስ)
49. [x] Nahum (ትንቢተ ናሆም)
50. [x] Habakkuk (ትንቢተ ዕንባቆም)
51. [x] Zephaniah (ትንቢተ ሶፎንያስ)
52. [x] Haggai (ትንቢተ ሐጌ)
53. [x] Zechariah (ትንቢተ ዘካርያስ)
54. [x] Malachi (ትንቢተ ሚልክያ)

---

### New Testament
55. [x] Matthew (የማቴዎስ ወንጌል)
56. [x] Mark (የማርቆስ ወንጌል)
57. [x] Luke (የሉቃስ ወንጌል)
58. [x] John (የዮሐንስ ወንጌል)
59. [x] Acts (የሐዋርያት ሥራ)
60. [x] Romans (ወደ ሮሜ ሰዎች)
61. [x] 1 Corinthians (ወደ ቆሮንቶስ ሰዎች ፩)
62. [x] 2 Corinthians (ወደ ቆሮንቶስ ሰዎች ፪)
63. [x] Galatians (ወደ ገላትያ ሰዎች)
64. [x] Ephesians (ወደ ኤፌሶን ሰዎች)
65. [x] Philippians (ወደ ፊልጵስዩስ ሰዎች)
66. [x] Colossians (ወደ ቆላስይስ ሰዎች)
67. [x] 1 Thessalonians (ወደ ተሰሎንቄ ሰዎች ፩)
68. [x] 2 Thessalonians (ወደ ተሰሎንቄ ሰዎች ፪)
69. [x] 1 Timothy (ወደ ጢሞቴዎስ ፩)
70. [x] 2 Timothy (ወደ ጢሞቴዎስ ፪)
71. [x] Titus (ወደ ቲቶ)
72. [x] Philemon (ወደ ፊልሞና)
73. [x] Hebrews (ወደ ዕብራውያን)
74. [x] 1 Peter (የጴጥሮስ መልእክት ፩)
75. [x] 2 Peter (የጴጥሮስ መልእክት ፪)
76. [x] 1 John (የዮሐንስ መልእክት ፩)
77. [x] 2 John (የዮሐንስ መልእክት ፪)
78. [x] 3 John (የዮሐንስ መልእክት ፫)
79. [x] James (የያዕቆብ መልእክት)
80. [x] Jude (የይሁዳ መልእክት)
81. [x] Revelation (የዮሐንስ ራእይ)

### Books of the canons

82. [x] 1 Book of covenant (አንደኛ ኪዳን) — `86-1-covenant.json`, 76 verses
83. [x] 2 Book of covenant (ሁለተኛ ኪዳን) — `94-2-covenant.json`, 79 verses
84. [x] Didascalia (ዲድስቅልያ) — 43 chapters
85. [x] Order of Zion (ሥርዓተ ጽዮን) — `87-sirate-tsion.json`, 81 verses
86. [x] Statutes of Apostles (አብጥሊስ) — `92-abtilis.json`, 82 verses
87. [x] Admonitions (ግጽው ሲኖዶስ) — `93-gitsew.json`, 72 verses
88. [x] Commandments (ትእዛዝ ሲኖዶስ) — `91-tizaz.json`, 56 verses
89. [x] 1 Clement (አንደኛ ቀሌሜንጦስ) — 12 chapters
90. [ ] 2 Clement (ሁለተኛ ቀሌሜንጦስ) — **still missing**

Also present, and not previously on this list:

- [x] Josippon (መጽሐፈ ዮሴፍ ወልደ ኮርዮን) — `88-josippon.json`, 72 chapters, 1,466 verses

Coverage above describes `am-2000`, the most complete edition. The 66-book
editions (`am-nasv-2001`, `am-1962`, `ti-1997`, `om-kitaaba`) carry the
protestant canon only.

---

## Source and rights

The text was recovered from Scripture App Builder app data. Copyright in these
translations rests with their publishers, named per edition in
`data/bible/<edition>/meta.json`:

- **የኢትዮጵያ መጽሐፍ ቅዱስ ማኅበር** (Ethiopian Bible Society) — `am-2000`, `am-1980`,
  `gez-1980`, `gez-2014`, `am-1962`, `ti-1997`
- **International Bible Society** — `am-nasv-2001` (አዲሱ መደበኛ ትርጕም™)
- **Waldaa Kitaaba Qulqulluu Ethiopia** — `om-kitaaba`
- **Public domain** — `en-kjv` (1611)

The repository licence covers this project's own code and structure, not the
underlying translations. Anyone redistributing this data — especially in a
published app — should confirm their position with the rights holders first.

---

## v1 data (`data/am`, `minified/`)

The original Amharic-only data set and its tooling (`minify_json.py`,
`minify_single_chapters.py`) are kept for compatibility with existing consumers.

**New work should use `data/bible/am-2000`, which supersedes it.** `data/am`
was derived from the same 2000 ዓ.ም edition but truncates multi-line verses: in
poetry a verse starts on one line and continues on the next, and only the first
line was captured. 3,593 verses are affected — Sirach 1,279, Job 967,
Proverbs 731, Song of Solomon 112, Lamentations 87.

### `minified/singleChapter/`

One minified JSON file per book plus an `index.json` for building menus,
keeping the same numeric order as `data/am`:

```json
{
  "book_number": 1,
  "book_name_am": "ኦሪት ዘፍጥረት",
  "book_short_name_am": "ዘፍ",
  "book_name_en": "Genesis",
  "book_short_name_en": "Gen",
  "testament": "old",
  "chapters": [{ "chapter": 1, "sections": [{ "title": "", "verses": [] }] }]
}
```

`index.json` contains `count` (total chapter files) and `files` (menu entries
in order, each with the fields above plus `file`).

```sh
python minify_single_chapters.py
python minify_single_chapters.py --input-dir data/am \
    --output-dir minified/singleChapter --index-file index.json
```
