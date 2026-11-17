# kindle-companion

A [Claude Code](https://claude.com/claude-code) skill for looking after a Kindle from a Mac. You ask in plain words ("put my new Calibre books on the Kindle", "move my AZW3s to EPUB without losing my place", "what did I highlight this week?"). Claude does the work with small, safe scripts, and shows you a plan before anything on the Kindle changes.

It works with the **2024+ MTP-only Kindles** (Paperwhite 12th gen, Colorsoft, Kindle 12th gen, Scribe), which don't appear in Finder and trip up most tools, as well as older Kindles that mount as a USB drive.

## Why I built this

I built this for my own Kindle, and I'm sharing it in case it saves someone else the same trouble.

When I got a 2024+ Kindle (a Paperwhite 12th gen), my usual routine stopped working. It doesn't appear in Finder, and most tools that expect a USB drive can't see it. The ones that do speak MTP often needed the cable replugged after every command. On top of that I wanted KOReader, which means a jailbreak whose method changes every few weeks, followed by a pile of small chores:

- sending books over from Calibre without sending duplicates
- moving AZW3 books to EPUB **without losing my place**
- sorting books into lists like "Now / Sometime / Reference"
- finding duplicates and leftover folders

The second reason is highlights. Highlighting feels like learning, but highlights I never look at again fade within weeks. Mine were also split between the stock reader's `My Clippings.txt` and KOReader. I wanted them in one place, plus a short weekly report that connects them to what I'm working on, so they actually get used.

**Why a Claude skill, and not just a script?** I don't want to remember flags. I'd rather say "put my new Calibre books on the Kindle" and have Claude work out the steps. But this is a device I care about, with my reading progress and notes on it, so the rule is: *Claude proposes, small scripts do the work, and nothing on the Kindle changes until I've seen the plan.*

**Status:** I've tested it on one device (a Paperwhite 12th gen) from a Mac. Other models should work through the same design, but I haven't tried them. Treat it as a well-tested personal tool, not a polished product, and take a backup first (`kindle.py backup` does this).

## What it does

| | Stock Kindle | Jailbroken (KOReader) |
|---|:-:|:-:|
| **Connect and take stock**: model from the serial number, storage, book list, jailbreak signs | ✓ | ✓ |
| **Jailbreak guide**: reads the *live* kindlemodding.org guide for your model and firmware, downloads the files it links to, copies them, walks you through the on-device steps | ✓ | — |
| **KOReader plugins**: install or update from GitHub releases (SimpleUI, Storefront, …) | | ✓ |
| **Add books from Calibre**, with a duplicate check | ✓ | ✓ |
| **AZW3/MOBI → EPUB migration** that keeps your reading position | | ✓ |
| **Collections**: topic or action lists ("1 · Now", "2 · Sometime") | | ✓ |
| **Clean-up**: duplicates (keeps the copy with notes or progress), leftover folders, printable book list | ✓ | ✓ |
| **Backup**: metadata-only or full | ✓ | ✓ |
| **Highlights archive**: `My Clippings.txt` plus KOReader highlights in one deduplicated file; Markdown export for Obsidian | ✓ | ✓ |
| **Weekly highlights report**: what you highlighted, why it matters for *your* goals, connections between books, recall questions, an old highlight brought back, one thing to do | ✓ | ✓ |

## Requirements

- macOS, with the `python3` that comes with the Xcode command line tools (3.9+). No pip packages needed.
- `brew install libmtp`, for MTP Kindles.
- [Calibre](https://calibre-ebook.com), optional. It's needed for sideloading, conversion and migration.
- Claude Code, or any agent that supports [Agent Skills](https://docs.claude.com/en/docs/claude-code/skills).

Windows and Linux aren't supported yet. MTP on Windows needs a different backend; pull requests are welcome.

## Install

**As a Claude Code plugin:**
```
/plugin marketplace add ogyet/kindle-companion
/plugin install kindle-companion@kindle-companion
```

**Or as a personal skill:**
```bash
git clone https://github.com/ogyet/kindle-companion.git
```
```bash
ln -s "$PWD/kindle-companion/skills/kindle-companion" ~/.claude/skills/kindle-companion
```

Then plug in your Kindle, unlock it, and ask Claude something like *"check my Kindle"*.

## Try asking

- "What Kindle do I have, and can it be jailbroken?"
- "Install SimpleUI and Storefront in KOReader."
- "Send the last 5 books I added to Calibre to my Kindle."
- "Move my AZW3 books to EPUB for KOReader and keep my place in each."
- "Make KOReader collections: Now, Sometime, Reference, from this list…"
- "Find duplicates and leftover folders on my Kindle."
- "Back up my Kindle."
- "Pull my highlights and write this week's report."

## How it stays safe

- **One device session per command.** MTP Kindles drop off after each session, so all the changes in a plan happen in one connection.
- **Plan, dry run, then apply.** Scripts analyze an offline snapshot and write a JSON plan. You see it before `kindle.py apply` runs.
- **Restricted paths.** It writes only under `documents/`, `koreader/`, `extensions/` and `mrpackages/`, and deletes only under `documents/` and `koreader/plugins/`. Root-level files (jailbreak files) need an explicit flag.
- **Automatic backups** of every small file before it's deleted or replaced: reading data, sidecars, collections.
- **Your data stays local** in `~/Documents/Kindle Companion/`.
- **No DRM removal, no Amazon scraping.** Amazon purchases are never put in delete, migration or collection plans.

**Jailbreaking is your choice and your risk.** Amazon doesn't support it, and mistakes can brick a device. The skill follows the community guide at [kindlemodding.org](https://kindlemodding.org) step by step and never improvises.

## Layout

```
skills/kindle-companion/
  SKILL.md                 instructions Claude follows
  references/              device access, jailbreak, KOReader, library, highlights report
  scripts/
    kindle.py              the only script that talks to the Kindle (libmtp via ctypes, or USB drive)
    library.py             book list, duplicates, orphans
    migrate.py             AZW3/MOBI -> EPUB with reading position
    collections_kc.py      KOReader collections
    highlights.py          highlights archive, report feed, Markdown export
    fetch.py               plugin and jailbreak downloads (GitHub, kindlemodding.org only)
    calibre_find.py        read-only Calibre library search
    krds.py, kc_lib.py     file-format helpers (Kindle reading data, KOReader Lua)
    models.json            serial number -> model table
tests/test_offline.py      synthetic tests, no device needed
```

Run the tests with `python3 -I -m unittest discover -s tests -v`.

## Credits

- [KOReader](https://github.com/koreader/koreader): the serial-number table in `models.json` comes from its Kindle device code (AGPL-3.0), and it documents the sidecar and collection formats.
- [KindleModding](https://kindlemodding.org): the jailbreak guides this skill follows.
- [libmtp](https://github.com/libmtp/libmtp).
- Plugin authors: SimpleUI, Storefront, and the others listed in `references/koreader.md`.

Kindle is a trademark of Amazon. This project is not affiliated with or endorsed by Amazon.

## License

MIT
