"""Library reports and clean-up plans from a snapshot (read-only; plans are applied with kindle.py apply).

Usage:
  library.py books   [SNAP] [--md OUT.md] [--json]   book list with progress, highlights, collections
  library.py dupes   [SNAP] [--plan OUT.json]        duplicate books; plan deletes the weaker copies
  library.py orphans [SNAP] [--plan OUT.json]        .sdr folders whose book is gone
SNAP defaults to the newest folder in ~/Documents/Kindle Companion/snapshots/.

Which copy of a duplicate is kept (in order): has KOReader highlights > has KOReader progress >
has stock Kindle reading data > EPUB over Kindle formats > larger file. Amazon purchases are never
put in a delete plan: they're listed as REMOVE ON KINDLE (long-press the cover > Remove download), which
keeps the Kindle's library database right and leaves the book in the Amazon cloud library.
"""
import argparse
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krds  # noqa: E402
from kc_lib import Snapshot, latest_snapshot, lua_array, norm, write_plan  # noqa: E402


def snap_arg(a):
    p = a.snap or latest_snapshot()
    if not p:
        sys.exit("No snapshot found. Run: kindle.py snapshot \"~/Documents/Kindle Companion/snapshots/<date>\"")
    return Snapshot(p)


def membership(snap):
    out = collections.defaultdict(list)
    for name, coll in snap.collections().items():
        for e in lua_array(coll):
            if isinstance(e, dict) and e.get("file"):
                out[e["file"]].append(name)
    return out


def cmd_books(a):
    s = snap_arg(a)
    books = s.books()
    mem = membership(s)
    rows = []
    for b in books:
        d = b.as_dict()
        d["collections"] = mem.get(b.device_path, [])
        rows.append(d)
    if a.json:
        print(json.dumps(rows, indent=1, ensure_ascii=False))
        return
    lines = [f"# Books on the Kindle ({len(rows)})", "", f"Snapshot: {s.meta.get('taken', '?')}", "",
             "| # | Title | Author | Format | Read | Highlights | Collections |", "|---|---|---|---|---|---|---|"]
    for i, r in enumerate(sorted(rows, key=lambda r: r["title"].lower()), 1):
        read = f"{r['koreader_percent']}%" if r["koreader_percent"] is not None else ("stock data" if r["stock_reading_data"] else "")
        if r["status"] == "complete":
            read = "finished"
        lines.append(f"| {i} | {r['title'][:70]} | {r['authors'][:40]} | {r['format']} | {read} | {r['highlights'] or ''} | "
                     f"{', '.join(r['collections'])} |")
    text = "\n".join(lines) + "\n"
    if a.md:
        open(a.md, "w", encoding="utf-8").write(text)
        print(f"Wrote {a.md} ({len(rows)} books)")
    else:
        print(text)


def short_title(t):
    """'The Art of War_B0084B050M' / 'Art of War: Complete Edition' / 'The Art of War - Sun Tzu (12)' -> 'art of war'."""
    t = re.sub(r"_?B0[0-9A-Z]{8}$", "", (t or "").strip())  # Amazon ASIN suffix
    t = re.split(r"[:_]| - |\(", t)[0]  # drop subtitle, author, edition/series
    t = norm(t)
    t = re.sub(r"^(the|a|an) ", "", t)
    return re.sub(r" (the|a|an)$", "", t)  # Calibre sort names: "Art of War, The"


def surname(b):
    return norm(b.authors).split(" ")[-1] if b.authors and norm(b.authors) not in ("unknown", "") else None


def opened_in_stock_reader(b):
    """True if the stock reader saved a last-read position (lpr) for this copy."""
    for f in b.stock_files:
        local = b.snap.local(f)
        if not local:
            continue
        try:
            if any(isinstance(v, str) and v.strip() for v in krds.parse(local).get("lpr", [])):
                return True
        except Exception:  # noqa: BLE001  unreadable reading data counts as "not opened"
            continue
    return False


def rank(b):
    return (b.annotations > 0, isinstance(b.percent, (int, float)) and b.percent > 0, opened_in_stock_reader(b),
            b.ext == "epub", b.amazon, b.size)


def group_dupes(books):
    """Group by short title; split a group only when two copies name different authors (different books)."""
    by_title = collections.defaultdict(list)
    for b in books:
        if short_title(b.title):
            by_title[short_title(b.title)].append(b)
    groups = []
    for bs in by_title.values():
        named = {surname(b) for b in bs if surname(b)}
        if len(named) <= 1:
            groups.append(bs)
        else:  # e.g. two different books both called "Influence"
            for sn in named:
                groups.append([b for b in bs if surname(b) in (sn, None)])
    return [g for g in groups if len(g) > 1]


def cmd_dupes(a):
    s = snap_arg(a)
    ops, n, remove_on_kindle = [], 0, []
    for bs in sorted(group_dupes(s.books()), key=lambda g: short_title(g[0].title)):
        n += 1
        bs.sort(key=rank, reverse=True)
        keep, rest = bs[0], bs[1:]
        print(f"\n{keep.title} — {keep.authors or '?'}")
        print(f"  KEEP   {keep.path}  ({_why(keep)})")
        for b in rest:
            if b.amazon:
                print(f"  REMOVE ON KINDLE  {b.path}  ({_why(b)}; Amazon copy: long-press its cover > Remove download)")
                remove_on_kindle.append(b.path)
                continue
            if b.annotations:
                print(f"  CHECK  {b.path}  has {b.annotations} highlights too; export highlights first, then decide")
                continue
            if b.stock_files and b.ext in ("azw3", "azw", "mobi") and opened_in_stock_reader(b):
                print(f"  MIGRATE {b.path}  has the Kindle reader's position; use migrate.py so it carries over")
                continue
            if isinstance(b.percent, (int, float)) and b.percent > 0:
                print(f"  CHECK  {b.path}  has KOReader progress ({round(b.percent * 100)}%); decide by hand")
                continue
            print(f"  DELETE {b.path}  ({_why(b)})")
            ops.append({"op": "delete", "remote": b.path})
            sdr = s.sidecar_dir(b.path)
            if sdr in s.dirs:
                ops.append({"op": "rmtree", "remote": sdr})
    print(f"\n{n} duplicate group(s); {sum(1 for o in ops if o['op'] == 'delete')} file(s) in the delete plan, "
          f"{len(remove_on_kindle)} Amazon copies to remove on the Kindle itself")
    if a.plan and ops:
        write_plan(a.plan, ops, "delete weaker duplicate copies (review before applying)")
        print(f"Plan written: {a.plan}  (review, then: kindle.py apply {a.plan} --dry-run)")


def _why(b):
    bits = []
    if b.annotations:
        bits.append(f"{b.annotations} highlights")
    if isinstance(b.percent, (int, float)) and b.percent > 0:
        bits.append(f"{round(b.percent * 100)}% read in KOReader")
    if b.stock_files:
        bits.append("opened in the Kindle reader" if opened_in_stock_reader(b) else "never opened in the Kindle reader")
    if b.amazon:
        bits.append("Amazon purchase")
    else:
        bits.append("sideloaded")
    bits.append(f"{b.ext}, {round(b.size / 1e6, 1)} MB")
    return ", ".join(bits)


def cmd_orphans(a):
    s = snap_arg(a)
    # KOReader names the folder after the book without its extension ("x.sdr" for "x.epub");
    # Calibre and the Kindle also make "x.epub.sdr" (covers, page numbers). Both belong to the book.
    docs = [p for p in s.files if p.startswith("documents/")]
    book_stems = {p.rsplit(".", 1)[0] for p in docs} | set(docs)
    ops, keep_note = [], []
    for d in sorted(s.dirs):
        if not d.startswith("documents/") or not d.endswith(".sdr"):
            continue
        if d.lower().startswith("documents/downloads/") or ".sdr/" in d:
            continue  # Amazon's own area (purchases, updates) and folders nested in other .sdr folders: never touch
        if d[:-4] in book_stems:
            continue
        inside = [p for p in s.files if p.startswith(d + "/")]
        why = None
        for p in inside:
            low = p.lower()
            if low.endswith((".azw3r", ".yjr", ".mbp", ".pdr")):
                why = "stock reader data (may hold highlights)"
            elif low.endswith(".lua"):
                t = s.read(p) or ""
                if ('["annotations"]' in t and '["text"]' in t) or '["highlight"]' in t:
                    why = "KOReader highlights; run highlights.py ingest first"
        if why:
            keep_note.append((d, why))
            continue
        ops.append({"op": "rmtree", "remote": d})
    for d, why in keep_note:
        print(f"KEEP ({why}): {d}")
    for o in ops:
        print(f"ORPHAN {o['remote']}")
    print(f"{len(ops)} orphan folder(s) safe to remove, {len(keep_note)} kept because they may hold highlights")
    if a.plan and ops:
        write_plan(a.plan, ops, "remove reading-data folders whose book no longer exists")
        print(f"Plan written: {a.plan}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("books", "dupes", "orphans"):
        p = sub.add_parser(name)
        p.add_argument("snap", nargs="?")
        if name == "books":
            p.add_argument("--md")
            p.add_argument("--json", action="store_true")
        else:
            p.add_argument("--plan")
    a = ap.parse_args()
    {"books": cmd_books, "dupes": cmd_dupes, "orphans": cmd_orphans}[a.cmd](a)


if __name__ == "__main__":
    main()
