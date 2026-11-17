---
name: kindle-companion
description: Manages a Kindle e-reader from a Mac over USB, including 2024+ MTP-only models (Paperwhite 12, Colorsoft, Scribe) that Finder and most tools can't see. Identifies the model and firmware, guides a jailbreak from the live kindlemodding.org guide and copies its files, installs and updates KOReader plugins, sideloads books from Calibre, migrates AZW3/MOBI books to EPUB while keeping the reading position, builds KOReader collections, finds duplicates and leftover folders, backs up the device, archives highlights from both the stock reader and KOReader, and writes a weekly highlights report on what the user highlighted and why it matters. Use this whenever the user mentions their Kindle, e-reader, KOReader, jailbreaking, sideloading, My Clippings, Kindle highlights or notes, book collections on the device, or a reading report, even if they don't name the skill.
allowed-tools: Bash(python3 -I ${CLAUDE_SKILL_DIR}/scripts/kindle.py doctor*) Bash(python3 -I ${CLAUDE_SKILL_DIR}/scripts/kindle.py info*) Bash(python3 -I ${CLAUDE_SKILL_DIR}/scripts/kindle.py ls*) Bash(python3 -I ${CLAUDE_SKILL_DIR}/scripts/kindle.py snapshot *) Bash(python3 -I ${CLAUDE_SKILL_DIR}/scripts/library.py *) Bash(python3 -I ${CLAUDE_SKILL_DIR}/scripts/collections_kc.py show*) Bash(python3 -I ${CLAUDE_SKILL_DIR}/scripts/highlights.py new*) Bash(python3 -I ${CLAUDE_SKILL_DIR}/scripts/highlights.py stats*) Bash(python3 -I ${CLAUDE_SKILL_DIR}/scripts/calibre_find.py *)
---

# Kindle Companion

Help the user look after their Kindle and get more out of what they read. Everything runs on the user's Mac against their own device and their own DRM-free files. The skill reads freely, but it changes the Kindle only through a written plan that the user has seen.

## How the pieces fit

- `scripts/kindle.py` is the only thing that talks to the Kindle. Each command opens the device **once**, does all its work, and releases it. Newer Kindles drop off USB after each MTP session, so never loop over single-file commands; put the work into one plan and `apply` it.
- `kindle.py snapshot DIR` copies the listing plus small metadata files (reading-data sidecars, `My Clippings.txt`, KOReader settings) to the Mac. Every other script works **offline on the snapshot** and writes a *plan* (JSON). `kindle.py apply PLAN` runs it in one session, after a `--dry-run`.
- `kindle.py apply` refuses to write outside `documents/`, `koreader/`, `extensions/` and `mrpackages/`, and refuses to delete outside `documents/` and `koreader/plugins/`. It backs up every file under 20 MB before deleting or replacing it, into `~/Documents/Kindle Companion/backups/<time>/`.
- **The user's data folder** is `~/Documents/Kindle Companion/`, which holds `snapshots/<YYYY-MM-DD_HHMM>/`, `backups/`, `staging/`, `highlights/archive.jsonl`, `reports/`, `goals.md` and `state.json`. Set `KC_HOME` to move it.

Run every script as `python3 -I <skill-dir>/scripts/<name>.py` (`-I` keeps Python from importing stray files from the current folder).

## Hard rules

1. **Show the plan, then wait for a yes** before any `kindle.py apply` that isn't a dry run, any download, and any jailbreak step. Read-only commands are fine anytime: `doctor`, `info`, `ls`, `snapshot`, the reports, `show`, `new` and `stats`.
2. **DRM-free files only.** Never remove DRM, never help extract Kindle keys, never scrape Amazon or the web reader. Leave Amazon purchases (`documents/Downloads/…`, `_ASIN` files, `.kfx`) alone; the scripts already skip them for delete, migrate and collection plans.
3. **Jailbreak: guide and copy, never improvise.** Re-read the live kindlemodding.org pages every time (exploits change within weeks). Copy only files those pages link to, then let the user do the on-device steps. Details are in `references/jailbreak.md`.
4. **Quit apps that hold the Kindle** (Calibre, OpenMTP, Android File Transfer) before device commands; `kindle.py` checks and tells you. Ask the user to quit them rather than killing them yourself. Quitting KOReader before collection changes matters too, because it rewrites `collection.lua` when it exits.
5. **Privacy.** Highlights, book lists and goals stay on the Mac. Don't send them to outside services unless the user asks. In chat, summarize highlights briefly in your own words rather than pasting long passages.

## Start of every session: connect

1. Run `kindle.py doctor`. If libmtp is missing, the user runs `brew install libmtp`; if Calibre is running, ask them to quit it.
2. Ask the user to plug in the Kindle and unlock its screen, then run `kindle.py info`.
   - **Model:** comes from the serial number, using KOReader's device table in `scripts/models.json`.
   - **Firmware:** the MTP version string is only a hint. Confirm the real firmware on the Kindle under Settings › Device Options › Device Info.
   - **Jailbreak signs:** reports whether KOReader, KUAL, MRPI and the hotfix are present.
3. Take a snapshot: `kindle.py snapshot "$HOME/Documents/Kindle Companion/snapshots/$(date +%Y-%m-%d_%H%M)"`. Reuse the newest snapshot unless the device has changed since.

If a command says "no MTP device" or "could not open": unlock the Kindle, replug, check the blockers again, and retry once. `references/device-access.md` has the full troubleshooting list.

## Jobs (pick what the user asked for)

### Jailbreak and post-jailbreak setup
Follow `references/jailbreak.md` exactly. It identifies the model and firmware, opens the live wizard and method page, summarizes the steps for the user, downloads the listed files with `fetch.py url` (with approval), copies them with a plan, and walks the user through the on-device steps. It then checks the post-jailbreak list: hotfix, KUAL + MRPI, updates blocked, KOReader.

### KOReader setup and plugins
Read `references/koreader.md`. Install or update a plugin with `fetch.py release OWNER/REPO --out <staging> --plan <plan>`, then dry-run and apply the plan, then tell the user to restart KOReader. Also covers Calibre wireless setup and the screensaver.

### Add books (sideload)
Run `calibre_find.py "terms"` to get paths, then check the snapshot so you don't send a duplicate. Write a plan of `put` ops to `documents/` and apply it. For a stock (non-jailbroken) Kindle, use EPUB or AZW3. For KOReader, use EPUB. See `references/library.md` for format and cover notes.

### AZW3/MOBI → EPUB migration (keeps reading position)
Run `migrate.py plan --staging <dir> --plan <plan>`, adding `--convert` when Calibre has no EPUB. Show the user the per-book list: the position it found, what gets uploaded, and what gets skipped. Run `highlights.py ingest` first so nothing is lost, then dry-run and apply. The method is in `references/library.md`.

### Collections
Run `collections_kc.py show` to see what's there. Agree the collections with the user: topics, or action lists such as "1 · Now / 2 · Sometime / 3 · Reference". Write `wanted.json`, then run `collections_kc.py build --wanted … --staging … --plan …`. Resolve every "NOT ADDED" line with the user (pick the right book or drop it). The user must quit KOReader before you apply. KOReader shows collections under the file browser's Collections menu, and in SimpleUI if it's installed.

### Clean-up and book list
- `library.py books --md <file>` writes the book list.
- `library.py dupes --plan …` finds duplicates. It keeps the copy with highlights or progress, prefers EPUB, marks Kindle-format copies with reading data as MIGRATE, and never deletes Amazon purchases.
- `library.py orphans --plan …` finds reading-data folders whose book is gone. Folders holding highlights are kept until you've ingested them.

Show the plan, wait for a yes, then apply.

### Backup
`kindle.py backup "$HOME/Documents/Kindle Companion/backups/full-$(date +%F)" [--with-books]`. Without `--with-books` it saves just the metadata, which is fast and small. With it, it also saves every book file. Suggest a backup before a jailbreak, a migration or a big clean-up.

### Highlights archive and weekly report
Follow `references/highlights-report.md`.
1. Snapshot the Kindle and run `highlights.py ingest`.
2. Run `highlights.py new --last-report --resurface 3 --json` (the first time, use `--since` a date 7 days ago).
3. Read the user's `goals.md`. Create it with them the first time: what they're working on, deciding, or trying to get better at.
4. Write the report in the template's structure to `reports/<YYYY>-W<NN>.md`.
5. Run `highlights.py mark-report <file> --resurfaced <ids>`.

Also offer `highlights.py export` for one Markdown file per book (Obsidian-friendly).

## Before you finish

- After any apply, read its `SUMMARY` line. If there were errors, take a fresh snapshot and report what actually changed; don't assume it all worked.
- Tell the user where the backups went and what to check on the Kindle itself, for example "open Founding Sales in KOReader; it should open at about 7%".

## Reference files

- `references/device-access.md`: MTP vs USB drive, macOS blockers, snapshot and plan formats, troubleshooting.
- `references/jailbreak.md`: the guide-and-copy jailbreak procedure and post-jailbreak checklist.
- `references/koreader.md`: plugin catalog, install and update, Calibre wireless, KOReader files.
- `references/library.md`: sideloading, migration method, collections, duplicates and orphans.
- `references/highlights-report.md`: archive format, weekly report template, spaced review.
