# `data/bible` — multi-language bible data

Nine bible editions in five languages, built from the decrypted Scripture App
Builder dump by `build_bible.py`.

```sh
python build_bible.py outputs/mezgebehiwot --out data/bible
python build_bible.py outputs/mezgebehiwot --out data/bible --indent 0   # compact
```

| edition | lang | books | chapters | verses | source |
| --- | --- | ---: | ---: | ---: | --- |
| `am-2000` መጽሐፍ ቅዱስ ሰማንያ አሐዱ, 2000 EC | am | 89 | 1,596 | 44,200 | C18 |
| `am-1980` መጽሐፍ ቅዱስ ሰማንያ አሐዱ, 1980 EC | am | 93 | 1,610 | 44,290 | C03 |
| `gez-1980` መጽሐፍ ቅዱስ ሰማንያ አሐዱ በግእዝ, 1980 EC | gez | 93 | 1,629 | 44,283 | C02 |
| `gez-2014` ግእዝ 2014 (partial) | gez | 27 | 260 | 7,958 | C44 |
| `en-kjv` King James Version with Apocrypha | en | 81 | 1,376 | 37,145 | C04 |
| `am-nasv-2001` አዲሱ መደበኛ ትርጕም, 2001 GC | am | 66 | 1,188 | 31,103 | C45 |
| `am-1962` ቀዳማዊ ኃይለ ሥላሴ ዘመነ መንግሥት, 1962 EC | am | 66 | 1,188 | 30,558 | C46 |
| `ti-1997` ትግርኛ መደበኛ ትርጕም, 1997 EC | ti | 66 | 1,189 | 30,740 | C47 |
| `om-kitaaba` Kitaaba Qulqulluu, Afaan Oromoo | om | 66 | 1,189 | 31,103 | C48 |

**647 books · 11,225 chapters · 301,380 verses · 103,032 cross references ·
6,213 footnotes.** 101 MB indented, 83 MB with `--indent 0`.

## Layout

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

* **`canon.json`** — identity and order. No language.
* **`names/<lang>.json`** — what to label a book in the *UI* language. A reader
  can use the Ge'ez text with an English book list.
* **`<edition>/meta.json`** — what *that edition* calls its own books, which
  differs: C02 calls Matthew ወንጌል ዘማቴዎስ, C18 calls it የማቴዎስ ወንጌል.

Book content files carry **no names at all**. Adding a language means dropping
in one `<edition>/` folder plus one `names/<lang>.json`; no existing file changes.

## Filenames are canon-stable

`01-genesis.json` is Genesis in every edition. A 66-book edition simply has
gaps in the numbering rather than renumbering, so files line up across editions
by name alone. Each `meta.json` carries a `position` field with that edition's
own display order (KJV puts Job at 18; the EOTC canon puts it at 27).

## Book format

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

* **Verses are flat, headings are positional.** `before` is the verse the
  heading precedes (`null` if nothing follows). Section headings are
  edition-specific and do not line up across editions — nesting verses inside
  them would make a parallel Amharic/Ge'ez view impossible without
  re-flattening, and would turn `GEN 1:1` into a scan.
* **`n`** is an integer. Three verses in the whole corpus (`3b`, `98a`, `70t`)
  stay strings rather than being silently coerced.
* **`alt`** is the Ge'ez numeral form of the verse number (`\va`), present on
  287k verses.
* **`lines`** appears only when a verse spans more than one line — poetry,
  where a verse starts on `\p` and continues on `\q1`/`\q2`. `t` is always the
  joined text; `lines` lets a renderer indent. 35,690 verses have it.
* **`refs`** cross references, **`notes`** footnotes.

## Caveats worth knowing

**Outside the standard 66, a USFM id is just a slot.** SAB fills it differently
per collection, so ids are not globally meaningful. Five KJV books occupy slots
that hold a *different work* in the EOTC editions:

| slot | EOTC editions | KJV |
| --- | --- | --- |
| `LJE` | ተረፈ ኤርምያስ, 1 ch | Epistle of Jeremy, 6 ch |
| `1MA` | መጽሐፈ መቃብያን ቀዳማዊ, 36 ch | 1 Maccabees, 16 ch |
| `2MA` | መጽሐፈ መቃብያን ካልእ, 21 ch | 2 Maccabees, 15 ch |
| `1ES` | መጽሐፈ ዕዝራ ሱቱኤል, 13 ch | 1 Esdras, 9 ch |
| `2ES` | መጽሐፈ ዕዝራ ካልዕ, 9 ch | 2 Esdras, 16 ch |

The Ethiopic Maccabees are not the Greek ones. Rather than let one filename
mean two books, KJV's versions get canon slots 95–99 of their own
(`95-jeremys-letter.json`, `96-1-esdras.json`, …). Everything else aligns.

**Five books in `am-2000` are stubs** — `ESG`, `DAG`, `MAN`, `S3Y`, `SUS` have
front matter but no chapters, so no file is written. That is deliberate in the
source: `ESG`'s front matter explains Esther was split in the 1980 edition and
merged in the 2000 one.

**`C33` is not a bible.** It is *Galmee Amnataa*, the Oromo counterpart of
መዝገበ ሃይማኖት (C01/C31/C32) — 2,462 verses, and its `GEN` slot holds
"Kadhannaa Yeroo Hundaa" (Daily Prayer). The Oromo bible is `C48`.

**`data/am` is superseded by `am-2000`.** It came from C18 but truncates
multi-line poetry verses — see `USFM2JSON.md`. Sirach loses 1,279 verses'
worth of text, Job 967, Proverbs 731.
