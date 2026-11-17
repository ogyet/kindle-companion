# kindle-companion

**I wanted my Kindle to work the way I read, not the way Amazon decided I should. So I jailbroke it, then taught Claude to run my kindle.**

## Why I built this

I got a Kindle and couldn't turn it the way I wanted. Landscape mode is limited, and that was the first sign the thing was built for someone who isn't me.

The second problem was worse: **I never looked at my highlights.** Highlighting feels like learning. It isn't. A highlight you never revisit is just a sentence you paid to underline, and it fades within weeks. Mine were stranded in two places, the stock reader's `My Clippings.txt` and KOReader, like ingredients stashed in two different walk-ins.

So I jailbroke it. That's a jarringly boring process: read the guide, find the right files for your exact model and firmware, copy them over, tap through the steps. I let Claude do the grunt work. It reads the live guide, downloads the files the guide links to, copies them over, and tells me what to tap. (The tapping on the Kindle itself is still yours.)

Then I kept going. One chore at a time, I expanded what the skill could do until my books worked the way I want them to work:

- a weekly highlights report that ties what I underlined to what I'm actually working on, quizzes me, and drags an old highlight back out of the cooler to see if it still holds up
- books sent over from Calibre, with no duplicates
- AZW3 books moved to EPUB **without losing my place**
- piles like "Now / Sometime / Reference"
- duplicates and leftover folders hunted down

So here we are.

The plumbing is the unglamorous part. The 2024+ Kindles (Paperwhite 12th gen, Colorsoft, Scribe) don't show up in Finder. No drive, no icon, nothing. Just a polite, expensive silence. The tools that do speak its language (MTP) tend to drop the connection after every command, like a bad date. This skill deals with that so you don't have to.

I don't want to memorize flags for any of it. I want to say *"put my new Calibre books on the Kindle"* and have it done. But this device holds my reading progress and my notes, and I'm not handing a stranger a knife and walking out of the kitchen. So the rule is simple: **Claude proposes, small scripts do the cooking, and nothing on the Kindle changes until I've seen the plan.**

**Does it work?** On my Kindle, a Paperwhite 12th gen, from a Mac. That's the honest answer. Other models should behave the same way, but I haven't tried them. This is a well-tested personal tool, not a polished product. Take a backup first (`kindle.py backup` does it), and don't blame me if you skip that step.

## What it is

A [Claude Code](https://claude.com/claude-code) skill for looking after a Kindle from a Mac. You talk in plain words, Claude does the work with a handful of small scripts, and you see a plan before anything on the device changes. It handles the **2024+ MTP-only Kindles** (Paperwhite 12th gen, Colorsoft, Kindle 12th gen, Scribe) that Finder can't see, and older Kindles that mount as an ordinary USB drive.

## What's on the menu

| | Stock Kindle | Jailbroken (KOReader) |
|---|:-:|:-:|
| **Weekly highlights report**: what you highlighted, why it matters for *your* goals, connections between books, recall questions, an old highlight brought back, one thing to do | ✓ | ✓ |
| **Highlights archive**: `My Clippings.txt` plus KOReader highlights in one deduplicated file; Markdown export for Obsidian | ✓ | ✓ |
| **AZW3/MOBI → EPUB migration** that keeps your reading position | | ✓ |
| **Collections**: topic or action lists ("1 · Now", "2 · Sometime") | | ✓ |
| **Add books from Calibre**, with a duplicate check | ✓ | ✓ |
| **Clean-up**: duplicates (keeps the copy with notes or progress), leftover folders, printable book list | ✓ | ✓ |
| **KOReader plugins**: install or update from GitHub releases (SimpleUI, Storefront, …) | | ✓ |
| **Jailbreak guide**: reads the *live* kindlemodding.org guide for your model and firmware, downloads the files it links to, copies them, walks you through the on-device steps | ✓ | — |
| **Connect and take stock**: model from the serial number, storage, book list, jailbreak signs | ✓ | ✓ |
| **Backup**: metadata-only or full | ✓ | ✓ |

## Just ask

- "Pull my highlights and write this week's report."
- "Move my AZW3 books to EPUB for KOReader and keep my place in each."
- "Send the last 5 books I added to Calibre to my Kindle."
- "Make KOReader collections: Now, Sometime, Reference, from this list…"
- "Find duplicates and leftover folders on my Kindle."
- "Install SimpleUI and Storefront in KOReader."
- "What Kindle do I have, and can it be jailbroken?"
- "Back up my Kindle."

## How it keeps its hands to itself

- **Plan, dry run, then apply.** Scripts study an offline snapshot and write a JSON plan. You read it. Only then does `kindle.py apply` touch the device.
- **One device session per command.** MTP Kindles drop off after each session, so every change in a plan happens in a single connection. No loops, no pestering the cable.
- **Fenced-in paths.** It writes only under `documents/`, `koreader/`, `extensions/` and `mrpackages/`, and deletes only under `documents/` and `koreader/plugins/`. Root-level files (the jailbreak ones) need an explicit flag.
- **Automatic backups** of every small file before it's deleted or replaced: reading data, sidecars, collections.
- **Your data stays on your Mac**, in `~/Documents/Kindle Companion/`.
- **No DRM removal, no Amazon scraping.** Amazon purchases never go into a delete, migration or collection plan.

**Jailbreaking is your call and your risk.** Amazon doesn't support it, and a wrong move can brick the device. The skill follows the community guide at [kindlemodding.org](https://kindlemodding.org) step by step and never improvises. Improvising is how you end up with an expensive paperweight.

## Get it running

All you need is [Claude Code](https://claude.com/claude-code), or any agent that supports [Agent Skills](https://docs.claude.com/en/docs/claude-code/skills). A couple of packages might be useful: `brew install libmtp` if your Kindle is one of the MTP-only models, and [Calibre](https://calibre-ebook.com) for sideloading, conversion and migration. The scripts use the `python3` that ships with Apple's command line tools, and no pip packages.

The scripts are only tested on a Mac, for my own personal use. But since you'll be driving them with an agent, you can easily get them working on your own machine. Do that at your own risk.

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

### The extensions I run on my Kindle

On top of the plugins KOReader ships with, I added these six:

- **SimpleUI**: a customizable home screen with a bottom navigation bar, a top bar and widgets.
- **Storefront**: a plugin store inside KOReader. Discover, install and update plugins, patches, fonts and screensavers without leaving the device.
- **Readest**: keeps KOReader and the Readest reading app in sync.
- **Reading Insights**: a full-screen overview of your reading history, built from KOReader's own statistics.
- **Readwise Reader**: downloads the articles you saved in Readwise Reader onto the Kindle, and can send your highlights back to Readwise. It needs a Readwise subscription.
- **Glimpse**: peek at maps, family trees and other reference images from anywhere in a book, without losing your place.

Plugins come and go, so check that each repo is still active before you install it. Claude can fetch and install any of them for you (`fetch.py release OWNER/REPO`).

## What's in the skill

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
