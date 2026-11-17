"""KOReader collections: show them, or merge a plan of new/updated collections into collection.lua.

Usage:
  collections_kc.py show  [SNAP]
  collections_kc.py build [SNAP] --wanted WANTED.json --staging DIR [--plan OUT.json] [--replace NAME ...]

WANTED.json maps collection names to books, in display order:
  {"1 · Now": ["Mom Test", "documents/Founding Sales - Pete Kazanjy (12).epub"], "Negotiation": ["Never Split"]}
Each entry is a Kindle path or a piece of the title; titles must match exactly one book (ambiguous or
missing ones are listed and left out). Existing collections and their settings are kept; books are
added to same-named collections (use --replace NAME to rebuild one from scratch). Entries pointing at
files no longer on the Kindle are dropped everywhere. The staged collection.lua round-trips through
the parser before it is written, and the plan uploads it to koreader/settings/ (the old one is
backed up automatically). Quit KOReader before applying: it rewrites this file when it exits.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kc_lib import DEVICE_ROOT, Snapshot, latest_snapshot, lua_array, lua_file_text, norm, write_plan  # noqa: E402


def load_snap(a):
    return Snapshot(a.snap or latest_snapshot() or sys.exit("no snapshot; run kindle.py snapshot first"))


def resolve(entry, books):
    if entry.startswith("documents/") or entry.startswith(DEVICE_ROOT):
        p = entry[len(DEVICE_ROOT) + 1:] if entry.startswith(DEVICE_ROOT) else entry
        hit = [b for b in books if b.path == p]
        return hit, "path"
    q = norm(entry)
    exact = [b for b in books if norm(b.title) == q]
    if exact:
        hits = exact
    else:
        hits = [b for b in books if q in norm(b.title) or q in norm(os.path.basename(b.path))]
    if len(hits) > 1:  # same book in two formats: prefer the EPUB (what KOReader users read)
        titles = {b.key()[0] for b in hits}
        if len(titles) == 1 and any(b.ext == "epub" for b in hits):
            hits = [b for b in hits if b.ext == "epub"][:1]
    return hits, "title"


def cmd_show(a):
    s = load_snap(a)
    data = s.collections()
    if not data:
        print("No KOReader collections on this Kindle yet.")
        return
    on_device = {b.device_path for b in s.books()}
    for name, coll in sorted(data.items(), key=lambda kv: (kv[1].get("settings", {}).get("order", 99), kv[0])):
        files = [e.get("file") for e in lua_array(coll) if isinstance(e, dict)]
        gone = [f for f in files if f not in on_device]
        print(f"{name}: {len(files)} books" + (f" ({len(gone)} missing from the Kindle)" if gone else ""))
        for f in files:
            print(f"   {'  ' if f in on_device else '! '}{os.path.basename(f)}")


def cmd_build(a):
    s = load_snap(a)
    # KOReader can't open Amazon purchases (DRM) or KFX, so they never go into its collections.
    books = [b for b in s.books() if not b.amazon and b.ext != "kfx"]
    wanted = json.load(open(a.wanted, encoding="utf-8"))
    data = s.collections()
    data.setdefault("favorites", {"settings": {"order": 1}})
    on_device = {b.device_path for b in books}
    problems = []
    max_order = max([c.get("settings", {}).get("order", 0) for c in data.values() if isinstance(c, dict)] + [0])
    for name, entries in wanted.items():
        files = []
        for e in entries:
            hits, how = resolve(e, books)
            if len(hits) == 1:
                files.append(hits[0].device_path)
            elif not hits:
                problems.append(f"{name}: no book matches {e!r}")
            else:
                problems.append(f"{name}: {e!r} matches {len(hits)} books: " + "; ".join(os.path.basename(h.path) for h in hits[:4]))
        coll = data.get(name)
        if coll is None and not files:
            problems.append(f"{name}: nothing matched, so the collection was not created")
            continue
        if coll is None or name in a.replace:
            settings = (coll or {}).get("settings")
            if settings is None:
                max_order += 1
                settings = {"order": max_order}
            have = []
        else:
            settings = coll.get("settings", {"order": max_order + 1})
            have = [x for x in lua_array(coll) if isinstance(x, dict) and x.get("file")]
        known = {x["file"] for x in have}
        for f in files:
            if f not in known:
                have.append({"file": f})
                known.add(f)
        new = {"settings": settings}
        for n, x in enumerate(have, 1):
            x = dict(x)
            x["order"] = n
            new[n] = x
        data[name] = new
    dropped = 0
    for name, coll in list(data.items()):
        if not isinstance(coll, dict):
            continue
        kept = [x for x in lua_array(coll) if isinstance(x, dict) and x.get("file") in on_device]
        dropped += len(lua_array(coll)) - len(kept)
        newc = {k: v for k, v in coll.items() if not isinstance(k, int)}
        for n, x in enumerate(kept, 1):
            x = dict(x)
            x["order"] = n
            newc[n] = x
        data[name] = newc
    os.makedirs(a.staging, exist_ok=True)
    out = os.path.join(a.staging, "collection.lua")
    open(out, "w", encoding="utf-8").write(lua_file_text(data, "we can read Lua syntax here!"))
    for name, coll in sorted(data.items(), key=lambda kv: kv[1].get("settings", {}).get("order", 99)):
        print(f"  {name}: {len(lua_array(coll))} books")
    if dropped:
        print(f"  ({dropped} entries for books no longer on the Kindle were dropped)")
    for p in problems:
        print("  NOT ADDED: " + p)
    print(f"Staged: {out}")
    if a.plan:
        write_plan(a.plan, [{"op": "put", "local": out, "remote_dir": "koreader/settings"}],
                   "update KOReader collections (quit KOReader first)")
        print(f"Plan: {a.plan}")
    return 1 if problems else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("show")
    p.add_argument("snap", nargs="?")
    p = sub.add_parser("build")
    p.add_argument("snap", nargs="?")
    p.add_argument("--wanted", required=True)
    p.add_argument("--staging", required=True)
    p.add_argument("--plan")
    p.add_argument("--replace", nargs="*", default=[])
    a = ap.parse_args()
    sys.exit(cmd_show(a) if a.cmd == "show" else cmd_build(a))


if __name__ == "__main__":
    main()
