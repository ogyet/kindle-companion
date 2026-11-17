"""Plan a move from Kindle formats (AZW3/AZW/MOBI) to EPUB for KOReader, keeping the reading position.

Usage:
  migrate.py plan [SNAP] --staging DIR [--plan OUT.json] [--convert] [--library CALIBRE_LIB] [--only TITLE ...]

What it does (read-only until you apply the plan with kindle.py apply):
  1. Finds sideloaded AZW3/AZW/MOBI books on the Kindle (Amazon purchases are skipped: DRM).
  2. Finds the same book in Calibre (by the Calibre id Calibre left on the device, else by title).
  3. Picks the EPUB: already on the Kindle > Calibre's EPUB > (with --convert) ebook-convert of
     Calibre's AZW3 into the staging folder. Calibre's library is never modified.
  4. Reads the Kindle's own last position from the .sdr reading-data file and turns it into a
     fraction of the book (position / KF8 text length). KOReader opens the EPUB at that percentage.
  5. Writes <epub>.sdr/metadata.epub.lua into staging and a plan: upload EPUB + sidecar, delete the old
     file and its .sdr (kindle.py backs the small files up first).
A book that already has KOReader progress on its EPUB keeps it: no sidecar is written for it.
Stock highlights live in documents/My Clippings.txt, which this never touches; run highlights.py ingest first anyway.
"""
import argparse
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import calibre_find  # noqa: E402
import krds  # noqa: E402
from kc_lib import KINDLE_ONLY_EXT, Snapshot, latest_snapshot, lua_file_text, norm, write_plan  # noqa: E402


def find_calibre(book, cal_all):
    if book.calibre_id:
        hit = [c for c in cal_all if c["calibre_id"] == book.calibre_id]
        if hit:
            return hit[0]
    t = norm(book.title)
    hits = [c for c in cal_all if norm(c["title"]) == t]
    if len(hits) > 1 and book.authors:
        hits = [c for c in hits if norm(book.authors).split(" ")[-1] in norm(c["authors"])]
    return hits[0] if len(hits) == 1 else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("snap", nargs="?")
    p.add_argument("--staging", required=True)
    p.add_argument("--plan")
    p.add_argument("--convert", action="store_true", help="convert with Calibre's ebook-convert when no EPUB exists")
    p.add_argument("--library")
    p.add_argument("--only", nargs="*", default=[])
    a = ap.parse_args()
    snap = Snapshot(a.snap or latest_snapshot() or sys.exit("no snapshot; run kindle.py snapshot first"))
    os.makedirs(a.staging, exist_ok=True)
    cal_all = calibre_find.lookup(library=a.library)
    if not cal_all:
        print("WARNING: Calibre library not found; only EPUBs already on the Kindle can be used.")
    books = snap.books()
    epubs_on_kindle = {b.key(): b for b in books if b.ext == "epub"}
    ops, report = [], {"migrate": [], "skipped": []}
    for b in books:
        if b.ext not in [e.strip(".") for e in KINDLE_ONLY_EXT] or b.ext == "kfx":
            continue
        if a.only and not any(norm(o) in norm(b.title) for o in a.only):
            continue
        if b.amazon:
            report["skipped"].append((b.title, "Amazon purchase (DRM); leave it in Kindle's own reader"))
            continue
        cal = find_calibre(b, cal_all)
        on_kindle = epubs_on_kindle.get(b.key())
        epub_local, epub_remote_name = None, None
        if on_kindle:
            epub_remote_name = os.path.basename(on_kindle.path)
        elif cal and "EPUB" in cal["formats"] and os.path.exists(cal["formats"]["EPUB"]):
            epub_local = cal["formats"]["EPUB"]
        elif cal and a.convert and any(f in cal["formats"] for f in ("AZW3", "MOBI", "AZW")):
            src = next(cal["formats"][f] for f in ("AZW3", "MOBI", "AZW") if f in cal["formats"])
            epub_local = os.path.join(a.staging, os.path.basename(b.path).rsplit(".", 1)[0] + ".epub")
            if not os.path.exists(epub_local):
                if not shutil.which("ebook-convert") and not os.path.exists("/Applications/calibre.app/Contents/MacOS/ebook-convert"):
                    report["skipped"].append((b.title, "needs conversion but Calibre's ebook-convert is missing"))
                    continue
                exe = shutil.which("ebook-convert") or "/Applications/calibre.app/Contents/MacOS/ebook-convert"
                r = subprocess.run([exe, src, epub_local], capture_output=True, text=True)
                if r.returncode != 0:
                    report["skipped"].append((b.title, "conversion failed: " + r.stderr[-200:]))
                    continue
        else:
            why = "not found in Calibre" if not cal else "Calibre has no EPUB (rerun with --convert)"
            report["skipped"].append((b.title, why))
            continue
        if epub_remote_name is None:
            epub_remote_name = os.path.basename(epub_local)
        epub_remote = f"{os.path.dirname(b.path)}/{epub_remote_name}"

        # reading position
        fraction, note = None, "never opened on the Kindle"
        stock = [f for f in b.stock_files if f.lower().endswith((".azw3f", ".azw3r", ".yjr", ".yjf"))]
        has_ko_progress = on_kindle is not None and isinstance(on_kindle.percent, (int, float)) and on_kindle.percent > 0
        if has_ko_progress:
            note = f"EPUB already has KOReader progress ({round(on_kindle.percent * 100)}%), kept"
        elif stock:
            pos = None
            for f in sorted(stock, key=lambda x: not x.endswith("f")):  # .azw3f first
                local = snap.local(f)
                if local:
                    try:
                        pos = krds.last_position(local)
                    except Exception as e:  # noqa: BLE001
                        note = f"reading data unreadable: {e}"
                    if pos:
                        break
            azw_src = (cal or {}).get("formats", {}).get(b.ext.upper())
            if pos and azw_src and os.path.exists(azw_src):
                tl = krds.kf8_text_length(azw_src)
                if tl:
                    fraction = round(min(pos / tl, 0.999), 4)
                    note = f"position {pos} of {tl} -> {round(fraction * 100, 1)}%"
            elif pos:
                note = "position found but Calibre's copy of the file is missing, so the % can't be computed"
        if fraction is not None:
            sdr_local = os.path.join(a.staging, epub_remote_name.rsplit(".", 1)[0] + ".sdr")
            os.makedirs(sdr_local, exist_ok=True)
            open(os.path.join(sdr_local, "metadata.epub.lua"), "w", encoding="utf-8").write(
                lua_file_text({"last_percent": fraction, "percent_finished": fraction},
                              "kindle-companion: reading position carried over from the Kindle's own reader"))
        # Old copy goes first. If the old and new files share a name stem they also share the .sdr
        # folder, so then only the Kindle's own reading files are removed, never KOReader's.
        ops.append({"op": "delete", "remote": b.path})
        old_sdr, new_sdr = snap.sidecar_dir(b.path), snap.sidecar_dir(epub_remote)
        if old_sdr in snap.dirs:
            if old_sdr == new_sdr:
                ops += [{"op": "delete", "remote": f} for f in b.stock_files]
            else:
                ops.append({"op": "rmtree", "remote": old_sdr})
        if epub_local:
            ops.append({"op": "put", "local": epub_local, "remote_dir": os.path.dirname(b.path)})
        if fraction is not None:
            ops.append({"op": "put_tree", "local": sdr_local, "remote_dir": os.path.dirname(b.path)})
        report["migrate"].append((b.title, epub_remote, note, "upload EPUB" if epub_local else "EPUB already on Kindle"))

    print(f"Migrate {len(report['migrate'])} book(s):")
    for t, er, note, src in report["migrate"]:
        print(f"  {t[:60]:60}  {src}; {note}")
    if report["skipped"]:
        print(f"\nSkipped {len(report['skipped'])}:")
        for t, why in report["skipped"]:
            print(f"  {t[:60]:60}  {why}")
    if a.plan and ops:
        write_plan(a.plan, ops, "AZW3/MOBI -> EPUB migration with reading positions")
        print(f"\nPlan: {a.plan} ({len(ops)} ops). Check it with: kindle.py apply {a.plan} --dry-run")


if __name__ == "__main__":
    main()
