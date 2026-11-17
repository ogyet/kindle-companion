# Library: sideload, migrate, collections, clean-up

## Sideloading from Calibre

- **Find the books:** `calibre_find.py "title or author"` prints the Calibre id, format and path. `--ids 12 40` looks up exact books; `--recent 10` lists the newest. It reads Calibre's `metadata.db` read-only, and works while Calibre is closed.
- **Check for duplicates:** look in the snapshot's `library.py books --json` output first.
- **Choose the format:**
  - **KOReader:** EPUB.
  - **Stock Kindle reader:** AZW3, or EPUB through Amazon's Send-to-Kindle. The stock reader can't open sideloaded EPUBs; Send-to-Kindle converts them in Amazon's cloud.
  - Convert with Calibre's `ebook-convert in.epub out.azw3` (into staging, not the Calibre library) only if the user asks.
- **Write the plan:** `put` ops to `documents/`, then dry-run and apply.
- **Naming:** when Calibre sends books itself, it names them `Title - Author (id).ext` and writes `metadata.calibre` (in the Kindle root on MTP models, in `documents/` on USB-drive models). The scripts use that file to tie Kindle files back to Calibre ids. Files you `put` keep their Calibre library filename. That's fine; the scripts match on title as a fallback.
- **Missing covers** on sideloaded books in the stock reader: Calibre's "Kindle cover" fix, and the device sometimes deleting thumbnails, are known problems. Sending the book through Calibre's own Send to device usually fixes it. KOReader shows covers from the EPUB itself.

## AZW3/MOBI → EPUB migration (`migrate.py`)

This moves books from the stock reader into KOReader without losing your place.

**The method:**
1. **Read the stock position.** The stock reader saves it in `documents/<book>.sdr/<book>.azw3f` (or `.azw3r`, `.yjr`). That's a "KRDS" binary file; `krds.py` decodes it. The `lpr` record (last position read) is a character offset into the KF8 text.
2. **Turn it into a fraction.** `krds.kf8_text_length()` reads the AZW3's total text length from its KF8 header, using Calibre's copy of the same file, and divides.
3. **Write the fraction for KOReader.** It goes into a new sidecar `<epub>.sdr/metadata.epub.lua` as `last_percent` and `percent_finished`. With no `last_xpointer` present, KOReader opens the EPUB at that percentage.

**Accuracy:** within a page or two, since the two formats lay out text a little differently. Tested on a Paperwhite 12th gen in November 2026: every carried-over book opened at the expected percentage.

**Order inside the plan:**
1. Delete the old file and its `.sdr`. If the old and new files share a name stem, only the stock reader's own files are deleted, never KOReader's.
2. Upload the EPUB, if it isn't already on the Kindle.
3. Upload the sidecar.

**What's protected:**
- An EPUB that already has KOReader progress keeps it.
- Amazon purchases are skipped.
- Stock highlights stay in `My Clippings.txt`, which is never touched. Run `highlights.py ingest` first anyway.
- Every small file is backed up by `apply`.

**After applying:** ask the user to open two or three migrated books in KOReader and check the page.

## Collections (`collections_kc.py`)

- **Stock reader collections** live in the Kindle's internal database. They can't be edited over USB without root access, so this skill manages **KOReader** collections only.
- **Sources for good collections:**
  - the user's goals
  - their NotebookLM topics or other study notes
  - "action" lists, for example: 1 · Now, 2 · Sometime, 3 · Curiosity, 4 · Reference, 5 · Skip. The number prefix keeps them in order.
- **`wanted.json`** holds names mapped to titles, title fragments, or `documents/...` paths.
  - Ambiguous matches are reported, never guessed.
  - Amazon and KFX books are excluded, because KOReader can't open them.
  - `--replace NAME` rebuilds one collection; otherwise books are added to what's there.
- **Before applying,** the user quits KOReader.
- **Finding them:** KOReader shows collections at File browser › (top-left menu) › Collections. SimpleUI shows them as shelves on its home screen. If the user expected them to "organize the library" on the stock home screen, explain that the stock reader can't see KOReader collections.

## Duplicates (`library.py dupes`)

**Grouping:** books are grouped by normalized title plus author surname.

**Which copy is kept, in order:**
1. has KOReader highlights
2. has KOReader progress
3. is an EPUB
4. has stock reading data
5. is larger

**Copies that are never deleted:**
- **Amazon purchases:** delete these on the Kindle itself, so Amazon's records stay right.
- **Copies with their own highlights:** marked CHECK.
- **Kindle-format copies with stock reading data:** marked MIGRATE; use migrate.py so the position carries over.

## Orphans (`library.py orphans`)

**What counts as an orphan:** a `.sdr` folder whose book is gone.
- Both `Book.sdr` (KOReader and the stock reader) and `Book.epub.sdr` (Calibre covers, page-number files) belong to `Book.epub`.
- Folders holding highlights are kept until the user has run `highlights.py ingest`.

## Book list

`library.py books --md "$HOME/Documents/Kindle Companion/book-list.md"` lists title, author, format, progress, highlight count and collections. For a printed copy, the user can open it in any Markdown viewer and print.
