# Releasing data changes

Correcting a verse should not require rebuilding an app. This is how a fix
reaches every reader.

```sh
# 1. record the fix
$EDITOR corrections/am-2000.json

# 2. cut a release — one command does everything
python tools/release.py

# 3. publish
git add -A && git commit && git push          # web + patches, live on deploy
gh release upload data-v2 dist/sqlite/*.gz    # mobile databases
```

Readers on the web see it on their next load. Mobile apps pick up a **68 KB
patch** instead of re-downloading a 14 MB database.

---

## The moving parts

| path | what | in git |
| --- | --- | --- |
| `corrections/<edition>.json` | the fixes, as data | yes |
| `data/` | published JSON, corrections applied | yes |
| `data/revisions.json` | what clients poll | yes |
| `data/patches/<edition>/<n>.json` | catch-up for clients | yes |
| `legacy/minified/` | v1 Amharic bundle | yes |
| `dist/sqlite/` | mobile databases | **no** — release assets |

## Why corrections are a separate file

`data` is *generated* from the Scripture App Builder dump. Editing a
verse there directly works right up until someone re-runs `build_bible.py`,
which silently overwrites it.

Keeping fixes in `corrections/` solves both halves of the problem at once:
a rebuild can re-apply them, and the same entries *generate* the patch clients
download. One edit, one source of truth, both outputs — they cannot drift.

### Correction format

```json
{
  "edition": "am-2000",
  "corrections": [
    {
      "op": "verse",
      "book": "GEN", "chapter": 1, "verse": 2,
      "field": "t",
      "was": "…ጨለማም በውኃው ላይ ነበረ፤ የግዚአብሔርም መንፈስ…",
      "to":  "…ጨለማም በውኃው ላይ ነበረ፤ የእግዚአብሔርም መንፈስ…",
      "note": "missing እ",
      "revision": 2
    }
  ]
}
```

* `field` is `t` (verse text) or `alt` (Ge'ez numeral).
* `was` is optional but strongly recommended: applying refuses to overwrite a
  verse that no longer matches, so a stale correction fails loudly instead of
  quietly clobbering good text.
* `revision` is left `null` when you add an entry. `release.py` fills it in
  with the revision that first shipped the fix. **Don't set it by hand.**

Applying is idempotent — running twice changes nothing the second time.

```sh
python tools/apply_corrections.py --all --check   # report, write nothing
python tools/apply_corrections.py am-2000         # apply one edition
```

## Revisions and patches

Each edition carries a `revision`, bumped whenever its data changes, and a
`baseline` — the oldest revision that can still catch up by patching.

```jsonc
// data/revisions.json
{
  "schema": 1,
  "generated": "2026-07-28T…Z",
  "editions": {
    "am-2000": {
      "revision": 2,
      "baseline": 1,
      "patches": [2],
      "books": 89, "chapters": 1596, "verses": 44200,
      "json": "data/am-2000",
      "db": { "file": "am-2000.db.gz", "bytes": 13929881, "sha256": "7aa480…" }
    }
  }
}
```

A patch is the ops from one revision to the next:

```jsonc
// data/patches/am-2000/2.json
{ "edition": "am-2000", "from": 1, "to": 2, "generated": "…",
  "ops": [ { "op": "verse", "book": "GEN", "chapter": 1, "verse": 2,
             "field": "t", "to": "…" } ] }
```

### What a client does

1. Fetch `revisions.json` (small, revalidated).
2. For each installed edition, compare the stored revision to `revision`.
3. If stored `>= baseline`, fetch patches `stored+1 … revision` and apply each
   op as `UPDATE verse SET text = ? WHERE book = ? AND chapter = ? AND verse = ?`.
   Store the new revision.
4. Otherwise download `db.file`, verify `sha256`, replace the database.

Bump `baseline` with `python tools/release.py --baseline` when `data` is
regenerated wholesale — that tells clients not to try patching across a rebuild.

The database records its own revision, so a client can recover it without
keeping separate bookkeeping:

```sql
SELECT value FROM meta WHERE key = 'revision';
```

## The release runner

```sh
python tools/release.py [--dry-run] [--skip-sqlite] [--skip-minify]
                        [--tokenizer trigram|unicode61] [--baseline]
```

In order: applies corrections → assigns revisions to new ones → writes patches
→ rebuilds `legacy/minified/` → rebuilds `dist/sqlite/` → writes `revisions.json`
with each database's size and `sha256`.

`--dry-run` reports exactly what would change and writes nothing. Use it first.
`--skip-sqlite` gives a fast data-only pass; the SQLite build takes a few
minutes for all nine editions.

It refuses to release if any correction is **stale** (the verse no longer
matches `was`) rather than guessing.

## Minifying

Two v1 scripts, both anchored at the repo root so they run from any directory.
`release.py` runs both; these are the manual equivalents.

**`tools/minify_json.py`** merges `legacy/am/*.json` into one bundle:

```sh
python tools/minify_json.py
# -> legacy/minified/80-weahadu.json   (~12 MB, whitespace stripped)
```

**`tools/minify_single_chapters.py`** writes one minified file per book plus an
index for building menus:

```sh
python tools/minify_single_chapters.py
python tools/minify_single_chapters.py --input-dir legacy/am \
    --output-dir legacy/minified/singleChapter --index-file index.json
# -> legacy/minified/singleChapter/01-genesis.json …
# -> legacy/minified/singleChapter/index.json  { count, files: [ … ] }
```

Both operate on **`legacy/am`** (v1, Amharic only) and are unaffected by
corrections, which apply to `data`. Keep running them only while v1
consumers exist.

> The committed `legacy/minified/` had drifted out of date — it was missing
> `82-1_celement.json` and `83-didascalia.json` entirely. Running `release.py`
> rather than the scripts by hand is what stops that recurring.

For `data` there is no separate minify step: it ships indented because
gzip removes the whitespace on the wire anyway, so compacting would shrink the
repo without making downloads meaningfully smaller.

## Caching

`vercel.json` splits the data by how it changes:

| path | cache |
| --- | --- |
| `data/revisions.json` | 60 s, must-revalidate — the freshness signal |
| `data/*/books/*` | a year, `immutable` — safe because of `?v=` |
| `data/patches/*` | a year, `immutable` — a patch never changes |
| everything else under `data/`, `legacy/minified/` | 1 h browser, 1 y CDN |

The reader appends `?v=<revision>` to every book and meta request, so a
corrected edition gets a fresh URL and everything else stays cached. Rules are
ordered general → specific, so the outcome is safe whichever way Vercel
resolves overlapping matches.

## Publishing the databases

`dist/` is gitignored — 191 MB of generated output does not belong in the repo,
and re-uploading it on every deploy would be wasteful. Publish it as release
assets instead:

```sh
gh release create data-v2 dist/sqlite/*.db.gz \
    --title "Data revision 2" \
    --notes "am-2000: 216 verse corrections (missing እ in የእግዚአብሔር)"
```

`docs/MOBILE.md` points clients at
`releases/latest/download/<edition>.db.gz`, so publishing a new release is all
it takes for a first install to pick up the current data. Existing installs
patch instead and never touch the release.

## Adding a whole new edition

1. Rebuild `data` with `tools/build_bible.py` (needs the USFM dump).
2. `python tools/release.py --baseline` — a wholesale rebuild is not patchable.
3. Publish new release assets.
