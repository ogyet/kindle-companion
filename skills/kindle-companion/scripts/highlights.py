"""Highlights archive: collect Kindle + KOReader highlights into one local file, then report or export.

Usage:
  highlights.py ingest [SNAP]                     add new highlights from a snapshot to the archive
  highlights.py new [--since YYYY-MM-DD | --last-report] [--resurface N] [--json]
                                                  highlights for a report (grouped by book), plus N
                                                  older highlights to bring back for spaced review
  highlights.py mark-report PATH                  record that a report was written (sets --last-report)
  highlights.py export [--book TEXT] [--out DIR]  one Markdown file per book (Obsidian-friendly)
  highlights.py stats

Archive: ~/Documents/Kindle Companion/highlights/archive.jsonl (one JSON object per highlight). Fields:
  id, book, author, text, note, chapter, location, created (when highlighted, if known),
  first_seen (when ingested), source (kindle-clippings | koreader), color.
Sources: documents/My Clippings.txt (stock Kindle reader, all books incl. Amazon ones) and every
KOReader sidecar (metadata.*.lua) in the snapshot. Re-running ingest never duplicates: a highlight
that was extended later replaces the shorter version.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kc_lib import HOME, Snapshot, latest_snapshot, lua_array, norm  # noqa: E402

ARCH_DIR = os.path.join(HOME, "highlights")
ARCHIVE = os.path.join(ARCH_DIR, "archive.jsonl")
STATE = os.path.join(HOME, "state.json")

DATE_FORMATS = ["%A, %B %d, %Y %I:%M:%S %p", "%A, %d %B %Y %H:%M:%S", "%A, %B %d, %Y, %I:%M %p",
                "%A, %d %B %Y, %H:%M", "%d %B %Y %H:%M:%S", "%B %d, %Y %I:%M:%S %p"]


def load_state():
    return json.load(open(STATE)) if os.path.exists(STATE) else {}


def save_state(st):
    os.makedirs(HOME, exist_ok=True)
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w"), indent=1)
    os.replace(tmp, STATE)


def load_archive():
    if not os.path.exists(ARCHIVE):
        return []
    return [json.loads(l) for l in open(ARCHIVE, encoding="utf-8") if l.strip()]


def save_archive(rows):
    os.makedirs(ARCH_DIR, exist_ok=True)
    tmp = ARCHIVE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, ARCHIVE)


def hid(book, text):
    return hashlib.sha1(f"{norm(book)}|{norm(text)}".encode()).hexdigest()[:16]


# ------------------------------------------------------------------ My Clippings.txt
def parse_date(s):
    s = s.strip()
    for f in DATE_FORMATS:
        try:
            return dt.datetime.strptime(s, f).isoformat(timespec="seconds")
        except ValueError:
            continue
    return None


def parse_clippings(text):
    text = text.lstrip("﻿")
    out, notes = [], []
    for block in text.split("=========="):
        lines = [l.strip("﻿ \r") for l in block.strip().split("\n")]
        if len(lines) < 2:
            continue
        head, meta, body = lines[0], lines[1], "\n".join(lines[2:]).strip()
        m = re.match(r"^(.*)\(([^()]*)\)\s*$", head)
        book, author = (m.group(1).strip(), m.group(2).strip()) if m else (head.strip(), "")
        low = meta.lower()
        kind = "bookmark" if "bookmark" in low or "marque-page" in low or "lesezeichen" in low else \
            "note" if re.search(r"\bnote\b|notiz", low) else "highlight"
        loc = re.search(r"(?:location|loc\.|position|emplacement)\s*([\d-]+)", meta, re.I)
        page = re.search(r"page\s*([\divxlc-]+)", meta, re.I)
        added = re.split(r"\|\s*(?:Added on|Ajouté le|Hinzugefügt am|Añadido el)\s*", meta, maxsplit=1, flags=re.I)
        created = parse_date(added[1]) if len(added) > 1 else None
        item = {"book": book, "author": author, "text": body, "location": (loc.group(1) if loc else None),
                "page": (page.group(1) if page else None), "created": created, "source": "kindle-clippings"}
        if kind == "highlight" and body:
            out.append(item)
        elif kind == "note" and body:
            notes.append(item)
    for n in notes:  # a note sits at the end location of the highlight it belongs to
        nloc = (n["location"] or "").split("-")[-1]
        target = next((h for h in reversed(out) if h["book"] == n["book"] and h["location"] and
                       h["location"].split("-")[-1] == nloc), None)
        if target:
            target["note"] = n["text"]
        else:
            out.append({**n, "text": "", "note": n["text"]})
    return out


# ------------------------------------------------------------------ KOReader sidecars
def parse_koreader(path, data):
    props = data.get("doc_props") or {}
    if data.get("doc_path"):
        name = os.path.basename(data["doc_path"]).rsplit(".", 1)[0]
    else:  # ".../Book Title - Author (12).sdr/metadata.epub.lua" -> "Book Title - Author (12)"
        name = os.path.basename(os.path.dirname(path))[:-4]
    book = props.get("title") or re.sub(r"\s*\(\d+\)$", "", name)
    author = (props.get("authors") or "").replace("\n", ", ")
    if not props.get("title") and " - " in book and not author:
        book, author = book.rsplit(" - ", 1)
    out = []
    anns = lua_array(data.get("annotations") or {})
    if anns:
        for x in anns:
            if x.get("pos0") is None or not (x.get("text") or x.get("note")):
                continue  # page bookmark
            out.append({"book": book, "author": author, "text": (x.get("text") or "").strip(), "note": x.get("note"),
                        "chapter": x.get("chapter"), "location": str(x.get("pageno") or "") or None,
                        "created": _ko_date(x.get("datetime")), "color": x.get("color"), "source": "koreader"})
    else:  # pre-2024 sidecars: bookmarks + highlight tables
        for x in lua_array(data.get("bookmarks") or {}):
            if not (x.get("highlighted") or x.get("pos0")):
                continue
            note = x.get("text")
            if note and re.match(r"^(Page|Seite|Pagina) \d+ ", note):
                note = None
            out.append({"book": book, "author": author, "text": (x.get("notes") or "").strip(), "note": note,
                        "chapter": x.get("chapter"), "location": str(x.get("page")) if isinstance(x.get("page"), int) else None,
                        "created": _ko_date(x.get("datetime")), "source": "koreader"})
    return out


def _ko_date(s):
    if not s:
        return None
    try:
        return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").isoformat(timespec="seconds")
    except ValueError:
        return None


# ------------------------------------------------------------------ commands
def merge(archive, new_items, now):
    by_book = {}
    for r in archive:
        by_book.setdefault(norm(r["book"]), []).append(r)
    added = extended = 0
    for it in new_items:
        if not (it.get("text") or it.get("note")):
            continue
        it["id"] = hid(it["book"], it["text"] or it.get("note") or "")
        group = by_book.setdefault(norm(it["book"]), [])
        nt = norm(it["text"])
        dup = None
        for r in group:
            rt = norm(r["text"])
            short = min(len(nt), len(rt))
            if r["id"] == it["id"] or (short >= 20 and (nt in rt or rt in nt)):
                dup = r
                break
        if dup is None:
            it["first_seen"] = now
            group.append(it)
            archive.append(it)
            added += 1
        else:
            if len(nt) > len(norm(dup["text"])):  # highlight was extended later
                dup["text"], dup["id"] = it["text"], it["id"]
                extended += 1
            if it.get("note") and not dup.get("note"):
                dup["note"] = it["note"]
            for k in ("chapter", "created", "location", "color"):
                if it.get(k) and not dup.get(k):
                    dup[k] = it[k]
    return added, extended


def cmd_ingest(a):
    snap = Snapshot(a.snap or latest_snapshot() or sys.exit("no snapshot; run kindle.py snapshot first"))
    items, sources = [], {"kindle-clippings": 0, "koreader": 0}
    clip = snap.read("documents/My Clippings.txt")
    if clip:
        c = parse_clippings(clip)
        items += c
        sources["kindle-clippings"] = len(c)
    for path, data in snap.all_koreader_sidecars():
        k = parse_koreader(path, data)
        items += k
        sources["koreader"] += len(k)
    archive = load_archive()
    now = dt.datetime.now().isoformat(timespec="seconds")
    added, extended = merge(archive, items, now)
    save_archive(archive)
    st = load_state()
    st["last_ingest"] = now
    save_state(st)
    print(f"Read {sources['kindle-clippings']} from My Clippings.txt, {sources['koreader']} from KOReader. "
          f"New: {added}, extended: {extended}. Archive now holds {len(archive)} highlights ({ARCHIVE}).")


def when(r):
    return r.get("created") or r.get("first_seen") or ""


def cmd_new(a):
    rows = load_archive()
    st = load_state()
    since = a.since
    if a.last_report:
        since = st.get("last_report_at")
    if not since:
        since = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    # Use the highlight's own date when known; the ingest date only for highlights without one, so the
    # first ingest of an old Kindle doesn't flood the first report with years of highlights.
    fresh = [r for r in rows if (r.get("created") or r.get("first_seen") or "") >= since]
    fresh_ids = {r["id"] for r in fresh}
    groups = {}
    for r in sorted(fresh, key=when):
        groups.setdefault((r["book"], r.get("author") or ""), []).append(r)
    resurfaced = []
    if a.resurface:
        cutoff = (dt.date.today() - dt.timedelta(days=21)).isoformat()
        old = [r for r in rows if r["id"] not in fresh_ids and when(r) and when(r) < cutoff and len(r.get("text") or "") > 40]
        seen = set(st.get("resurfaced", []))
        old.sort(key=lambda r: (r["id"] in seen, hashlib.sha1((r["id"] + since).encode()).hexdigest()))
        resurfaced = old[:a.resurface]
    result = {"since": since, "count": len(fresh), "books": len(groups),
              "highlights": [{"book": b, "author": au, "items": [{k: r.get(k) for k in ("id", "text", "note", "chapter", "location", "created", "source")}
                                                                 for r in items]} for (b, au), items in groups.items()],
              "resurface": [{k: r.get(k) for k in ("id", "book", "author", "text", "note", "created")} for r in resurfaced]}
    if a.json:
        print(json.dumps(result, indent=1, ensure_ascii=False))
        return
    print(f"{len(fresh)} highlight(s) in {len(groups)} book(s) since {since}\n")
    for (b, au), items in groups.items():
        print(f"## {b}" + (f" — {au}" if au else ""))
        for r in items:
            print(f"- {r['text']}" + (f"\n  NOTE: {r['note']}" if r.get("note") else "") +
                  (f"  [{r['chapter']}]" if r.get("chapter") else ""))
        print()
    if resurfaced:
        print("## From the archive (spaced review)")
        for r in resurfaced:
            print(f"- {r['text']}  ({r['book']})")


def cmd_mark_report(a):
    st = load_state()
    st["last_report_at"] = dt.datetime.now().isoformat(timespec="seconds")
    st.setdefault("reports", []).append({"path": os.path.abspath(a.path), "at": st["last_report_at"]})
    if a.resurfaced:
        st["resurfaced"] = sorted(set(st.get("resurfaced", [])) | set(a.resurfaced))
    save_state(st)
    print(f"Recorded report {a.path}. Next `new --last-report` starts from {st['last_report_at']}.")


def slug(s):
    return re.sub(r"[^\w\- ]+", "", s).strip()[:80] or "Untitled"


def cmd_export(a):
    rows = load_archive()
    outdir = a.out or os.path.join(ARCH_DIR, "books")
    os.makedirs(outdir, exist_ok=True)
    books = {}
    for r in rows:
        if a.book and norm(a.book) not in norm(r["book"]):
            continue
        books.setdefault((r["book"], r.get("author") or ""), []).append(r)
    for (b, au), items in books.items():
        lines = ["---", f'title: "{b}"', f'author: "{au}"', f"highlights: {len(items)}", "tags: [kindle-highlights]", "---", "",
                 f"# {b}", ""]
        chapter = None
        for r in sorted(items, key=lambda r: (str(r.get("location") or "").zfill(8), when(r))):
            if r.get("chapter") and r["chapter"] != chapter:
                chapter = r["chapter"]
                lines += [f"## {chapter}", ""]
            if r.get("text"):
                lines.append("> " + r["text"].replace("\n", "\n> "))
            if r.get("note"):
                lines.append(f"\n**My note:** {r['note']}")
            lines += [f"\n<small>{r.get('source')}, {(r.get('created') or r.get('first_seen') or '')[:10]}</small>", ""]
        open(os.path.join(outdir, slug(b) + ".md"), "w", encoding="utf-8").write("\n".join(lines))
    print(f"Wrote {len(books)} book file(s) to {outdir}")


def cmd_stats(a):
    rows = load_archive()
    books = {}
    for r in rows:
        books[r["book"]] = books.get(r["book"], 0) + 1
    st = load_state()
    print(f"{len(rows)} highlights across {len(books)} books. Last ingest: {st.get('last_ingest', 'never')}; "
          f"last report: {st.get('last_report_at', 'never')}")
    for b, n in sorted(books.items(), key=lambda kv: -kv[1])[:15]:
        print(f"  {n:>4}  {b}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ingest")
    p.add_argument("snap", nargs="?")
    p = sub.add_parser("new")
    p.add_argument("--since")
    p.add_argument("--last-report", action="store_true")
    p.add_argument("--resurface", type=int, default=0)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("mark-report")
    p.add_argument("path")
    p.add_argument("--resurfaced", nargs="*", default=[])
    p = sub.add_parser("export")
    p.add_argument("--book")
    p.add_argument("--out")
    sub.add_parser("stats")
    a = ap.parse_args()
    {"ingest": cmd_ingest, "new": cmd_new, "mark-report": cmd_mark_report, "export": cmd_export, "stats": cmd_stats}[a.cmd](a)


if __name__ == "__main__":
    main()
