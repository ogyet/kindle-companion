# Highlights archive and weekly report

## Why a report, and what makes it useful

Highlighting feels like learning, but highlights you never revisit fade within weeks. The weekly report turns them into something you use:
- **Re-encounter:** reading them again a few days later.
- **Elaboration:** writing why they matter to your own situation.
- **Retrieval:** answering questions from memory.
- **Spacing:** older highlights come back after weeks.

Keep the report short enough to read in 5 minutes. It should end with one thing to do.

## Archive

- **Location:** `~/Documents/Kindle Companion/highlights/archive.jsonl`, one JSON object per highlight. It grows every time you run `highlights.py ingest <snapshot>`.
- **Sources:**
  - **`documents/My Clippings.txt`** is the stock reader's log. It covers every book read in the stock reader, including Amazon purchases.
    - When a highlight is extended or edited, the stock reader appends a new entry. Ingest keeps only the longest version.
    - A note is attached to the highlight that ends at the same location.
    - Dates in English, French, German and Spanish layouts are recognized. Other languages keep the highlight but leave its date empty.
  - **KOReader sidecars** (`metadata.*.lua`): both the 2024+ `annotations` format and the older `bookmarks`/`highlight` format. Page bookmarks without text are skipped.
- **Re-ingesting** never duplicates. A highlight's identity is a hash of the book and its normalized text, plus a containment check for extended highlights.

## Weekly report procedure

1. **Connect,** snapshot, and run `highlights.py ingest`. If the Kindle isn't at hand, report on what's already archived and say so.
2. **Get the data:** `highlights.py new --last-report --resurface 3 --json`. The first time, use `--since <date 7 days ago>`.
   - If `count` is 0, say so kindly. Offer a resurfacing-only mini report, or suggest highlighting 3 passages this week; don't pad.
3. **Read `goals.md`** (in the data folder). If it doesn't exist, ask the user 3 quick questions and save their answers:
   - What are you working on or deciding right now?
   - What skill are you trying to get better at?
   - What question keeps coming up for you?

   This file is what makes "why it matters" specific instead of generic. Update it when the user's focus changes.
4. **Write** `reports/<YYYY>-W<NN>.md` using the template below. Write in your own words; quote at most one short line per book.
5. **Mark it done:** `highlights.py mark-report <file> --resurfaced <ids of the resurfaced items>`. That way the next report starts where this one ended, and the same old highlights don't come back next week.
6. **Tell the user** the report's path and its single suggested action. Offer `highlights.py export` if they keep notes in Obsidian or a similar app.

## Template

```markdown
# Reading week <YYYY-Www> · <date range>

**This week:** <N> highlights from <M> books. <One sentence on the overall theme.>

## What you highlighted
### <Book> — <Author>
- **<Short paraphrase of the highlight, or a quote of 15 words or fewer>** (ch./loc.)
  *Why it matters:* <one or two sentences tying it to a specific goal in goals.md, or to a decision the user is facing. If it ties to nothing, say what kind of situation it would help in.>
  *Your note:* <their note, if any>
(repeat per book; group near-duplicate highlights into one bullet)

## Connections
- <Where two highlights (same or different books) agree, disagree, or build on each other. 1–3 bullets.>

## Test yourself (answer before peeking at the book)
1. <A question whose answer is one of this week's highlights; phrased as an application, not a definition>
2. …
3. …

## From the archive
- <Resurfaced highlight, paraphrased> (<book>, <how long ago>). <One line: does it still hold? How does it relate to this week?>

## One thing to do this week
<A single concrete action that applies the strongest idea to the user's goals, with a when.>
```

## Making it weekly

The highlights only reach the Mac when the Kindle is connected, so the dependable rhythm is a **habit, not a timer**: "plug in on Sunday evening, ask for the report." If the user wants a reminder:
- Claude Code's `/schedule` can run a weekly routine, but it only works with highlights already archived.
- A calendar reminder works too.

## Export

`highlights.py export [--book TEXT] [--out DIR]` writes one Markdown file per book:
- YAML front matter (title, author, highlight count, tag)
- highlights grouped by chapter, with notes and dates

The default folder is `highlights/books/`. Point `--out` at an Obsidian vault folder to sync.
