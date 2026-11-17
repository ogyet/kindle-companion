"""Offline tests: no Kindle, no network, synthetic data only.  Run:  python3 -I -m unittest discover -s tests -v"""
import json
import os
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "kindle-companion", "scripts")
sys.path.insert(0, SCRIPTS)

import highlights  # noqa: E402
import kc_lib  # noqa: E402
import kindle  # noqa: E402
import krds  # noqa: E402


def krds_bytes(lpr):
    """Minimal KRDS file: version, count=1, object 'lpr' holding [int8 version, string position, long time]."""
    def s(txt):
        b = txt.encode()
        return b"\x00" + struct.pack(">H", len(b)) + b
    body = b"\x02" + struct.pack(">q", 1) + b"\x01" + struct.pack(">i", 1)
    body += b"\xfe" + s("lpr") + b"\x07\x02" + b"\x03" + s(str(lpr)) + b"\x02" + struct.pack(">q", 0) + b"\xff"
    return krds.MAGIC + body


def azw3_bytes(text_length):
    """Minimal PDB/MOBI container whose record 0 has a KF8 (version 8) MOBI header."""
    rec0 = bytearray(16 + 232)
    struct.pack_into(">I", rec0, 4, text_length)
    rec0[16:20] = b"MOBI"
    struct.pack_into(">I", rec0, 36, 8)
    header = bytearray(78 + 8 + 2)
    struct.pack_into(">H", header, 76, 1)
    struct.pack_into(">I", header, 78, len(header))
    return bytes(header) + bytes(rec0)


def make_snapshot(root, files):
    """files: {kindle_path: bytes_or_str_or_None}; None = listed but not copied (e.g. a book)."""
    listing, dirs = [], set()
    for p, content in files.items():
        parts = p.split("/")
        for i in range(1, len(parts)):
            dirs.add("/".join(parts[:i]))
        size = len(content) if content is not None else 1000
        listing.append({"path": p, "dir": False, "size": size, "mtime": 0})
        if content is not None:
            dest = os.path.join(root, "files", p)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            open(dest, "wb").write(content if isinstance(content, bytes) else content.encode())
    listing += [{"path": d, "dir": True, "size": 0, "mtime": 0} for d in sorted(dirs)]
    json.dump(listing, open(os.path.join(root, "listing.json"), "w"))
    json.dump({"taken": "test"}, open(os.path.join(root, "snapshot.json"), "w"))
    return root


def make_calibre(lib, books):
    """books: [(id, title, author, {FMT: bytes})] -> a tiny Calibre library with metadata.db."""
    os.makedirs(lib, exist_ok=True)
    con = sqlite3.connect(os.path.join(lib, "metadata.db"))
    con.executescript("""CREATE TABLE books(id INTEGER PRIMARY KEY, title TEXT, path TEXT, timestamp TEXT);
        CREATE TABLE authors(id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE books_authors_link(book INTEGER, author INTEGER);
        CREATE TABLE data(book INTEGER, format TEXT, name TEXT);""")
    for bid, title, author, fmts in books:
        path = f"{author}/{title} ({bid})"
        con.execute("INSERT INTO books VALUES(?,?,?,?)", (bid, title, path, "2026-01-01"))
        con.execute("INSERT INTO authors VALUES(?,?)", (bid, author))
        con.execute("INSERT INTO books_authors_link VALUES(?,?)", (bid, bid))
        os.makedirs(os.path.join(lib, path), exist_ok=True)
        for f, data in fmts.items():
            name = f"{title} - {author}"
            con.execute("INSERT INTO data VALUES(?,?,?)", (bid, f, name))
            open(os.path.join(lib, path, f"{name}.{f.lower()}"), "wb").write(data)
    con.commit()


def run(script, *args, env=None):
    e = dict(os.environ, **(env or {}))
    r = subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, script), *args], capture_output=True, text=True, env=e)
    return r.returncode, r.stdout + r.stderr


class Lua(unittest.TestCase):
    def test_roundtrip_and_escapes(self):
        data = {"Now": {"settings": {"order": 2}, 1: {"file": '/mnt/us/documents/A "quoted" \\ book.epub', "order": 1}},
                "favorites": {"settings": {"order": 1}}, "x": 0.25, "flag": True}
        text = kc_lib.lua_file_text(data)
        self.assertEqual(kc_lib.lua_load(text), data)

    def test_utf8_byte_escapes(self):
        self.assertEqual(kc_lib.lua_load('return {["t"] = "caf\\195\\169"}')["t"], "café")


class Krds(unittest.TestCase):
    def test_position_and_length(self):
        with tempfile.TemporaryDirectory() as d:
            f, b = os.path.join(d, "x.azw3f"), os.path.join(d, "x.azw3")
            open(f, "wb").write(krds_bytes(250000))
            open(b, "wb").write(azw3_bytes(1000000))
            self.assertEqual(krds.last_position(f), 250000)
            self.assertEqual(krds.kf8_text_length(b), 1000000)


class Clippings(unittest.TestCase):
    TEXT = ("﻿The Mom Test (Rob Fitzpatrick)\r\n- Your Highlight on page 12 | Location 180-182 | Added on Monday, November 10, 2026 10:12:33 AM\r\n\r\n"
            "Compliments are the fool's gold of customer learning.\r\n==========\r\n"
            "The Mom Test (Rob Fitzpatrick)\r\n- Your Note on page 12 | Location 182 | Added on Monday, November 10, 2026 10:13:01 AM\r\n\r\nUse in calls\r\n==========\r\n"
            "The Mom Test (Rob Fitzpatrick)\r\n- Your Highlight on page 12 | Location 180-183 | Added on Monday, November 10, 2026 10:14:00 AM\r\n\r\n"
            "Compliments are the fool's gold of customer learning. Deflect them.\r\n==========\r\n"
            "X (Y)\r\n- Your Bookmark on Location 70 | Added on Tuesday, September 2, 2025 08:01:00 AM\r\n\r\n\r\n==========\r\n")

    def test_parse_and_merge(self):
        items = highlights.parse_clippings(self.TEXT)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["note"], "Use in calls")
        self.assertEqual(items[0]["created"], "2026-11-10T10:12:33")
        arch = []
        added, extended = highlights.merge(arch, items, "2026-11-15T00:00:00")
        self.assertEqual((added, extended, len(arch)), (1, 1, 1))
        self.assertTrue(arch[0]["text"].endswith("Deflect them."))
        self.assertEqual(highlights.merge(arch, highlights.parse_clippings(self.TEXT), "later"), (0, 0))


class KOReaderAnnotations(unittest.TestCase):
    def test_new_and_legacy_formats(self):
        new = {"annotations": {1: {"pos0": "/a", "text": "Deep focus wins.", "note": "block mornings", "datetime": "2026-11-12 21:04:10",
                                   "chapter": "Rule 1", "pageno": 45},
                               2: {"page": "/b", "pageno": 50, "text": "bookmark only"}},
               "doc_props": {"title": "Deep Work", "authors": "Cal Newport"}}
        out = highlights.parse_koreader("documents/Deep Work - Cal Newport (7).sdr/metadata.epub.lua", new)
        self.assertEqual([(o["book"], o["author"], o["note"]) for o in out], [("Deep Work", "Cal Newport", "block mornings")])
        legacy = {"bookmarks": {1: {"highlighted": True, "notes": "Legacy text here", "text": "Page 3 Legacy text @ 2024", "pos0": "/x"}}}
        out = highlights.parse_koreader("documents/Old Book - Some One (3).sdr/metadata.epub.lua", legacy)
        self.assertEqual((out[0]["book"], out[0]["author"], out[0]["note"]), ("Old Book", "Some One (3)".replace(" (3)", ""), None))


class PlanSafety(unittest.TestCase):
    def test_refusals(self):
        with tempfile.NamedTemporaryFile() as f:
            ok = [{"op": "put", "local": f.name, "remote_dir": "documents"}, {"op": "rmtree", "remote": "documents/x.sdr"},
                  {"op": "put_tree", "local": f.name, "remote_dir": "koreader/plugins"}, {"op": "get", "remote": "documents/a", "local": "/tmp/a"}]
            self.assertEqual(kindle.check_plan(ok, False), [])
            bad = [{"op": "delete", "remote": "system/x"}, {"op": "rmtree", "remote": "documents"},
                   {"op": "put", "local": f.name, "remote_dir": ""}, {"op": "delete", "remote": "documents/../koreader/x"},
                   {"op": "put", "local": f.name, "remote_dir": "system"}, {"op": "delete", "remote": "koreader/settings/x.lua"}]
            probs = kindle.check_plan(bad, False)
            for i in range(1, 7):
                self.assertTrue(any(p.startswith(f"#{i}:") for p in probs), f"op {i} not refused: {probs}")
            self.assertEqual(kindle.check_plan([{"op": "put", "local": f.name, "remote_dir": ""}], True), [])

    def test_model_lookup(self):
        self.assertEqual(kindle.lookup_model("G0033X0000000000")["key"], "pw6")
        self.assertTrue(kindle.lookup_model("G0033X0000000000")["mtp"])
        self.assertEqual(kindle.lookup_model("B024000000000000")["key"], "pw")


class LibraryAndMigration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.snap = make_snapshot(os.path.join(t, "snap"), {
            "documents/Founding Sales - Pete Kazanjy.azw3": None,
            "documents/Founding Sales - Pete Kazanjy.sdr/Founding Sales - Pete Kazanjy.azw3f": krds_bytes(69000),
            "documents/Deep Work - Cal Newport (7).epub": None,
            "documents/Deep Work - Cal Newport (7).epub.sdr/cover.jpg": None,
            "documents/Deep Work - Cal Newport (7).sdr/metadata.epub.lua": 'return {["percent_finished"] = 0.3}',
            "documents/Deep Work - Cal Newport.azw3": None,
            "documents/Gone Book.sdr/metadata.epub.lua": 'return {["percent_finished"] = 0.1}',
            "documents/Gone Notes.sdr/metadata.epub.lua": 'return {["annotations"] = {[1] = {["pos0"] = "/a", ["text"] = "keep me"}}}',
            "documents/Downloads/Items01/Never Split the Difference_B014DUR7L2.kfx": None,
            "documents/Never Split the Difference - Chris Voss (34).epub": None,
            "documents/$100M Leads - Alex Hormozi (16).epub": None,
            "documents/$100M Offers - Alex Hormozi (31).epub": None,
            "documents/Downloads/Items01/Some Purchase_B000000000.sdr/Some Purchase_B000000000.yjr": krds_bytes(5),
            "koreader/settings/collection.lua": 'return {["favorites"] = {["settings"] = {["order"] = 1}}}',
        })
        self.lib = os.path.join(t, "Calibre")
        make_calibre(self.lib, [(5, "Founding Sales", "Pete Kazanjy", {"AZW3": azw3_bytes(1000000), "EPUB": b"PK-epub"})])

    def tearDown(self):
        self.tmp.cleanup()

    def test_orphans_keep_calibre_and_highlight_folders(self):
        code, out = run("library.py", "orphans", self.snap)
        self.assertIn("ORPHAN documents/Gone Book.sdr", out)
        self.assertIn("KEEP (KOReader highlights", out)
        self.assertNotIn("Deep Work - Cal Newport (7).epub.sdr", out)
        self.assertNotIn("Downloads", out)  # Amazon's area is never offered for deletion

    def test_dupes_prefer_epub_with_progress(self):
        plan = os.path.join(self.tmp.name, "d.json")
        code, out = run("library.py", "dupes", self.snap, "--plan", plan)
        self.assertIn("KEEP   documents/Deep Work - Cal Newport (7).epub", out)
        ops = json.load(open(plan))["ops"]
        self.assertIn({"op": "delete", "remote": "documents/Deep Work - Cal Newport.azw3"}, ops)
        self.assertFalse(any("kfx" in o["remote"] for o in ops))

    def test_migration_plan(self):
        plan, stage = os.path.join(self.tmp.name, "m.json"), os.path.join(self.tmp.name, "stage")
        code, out = run("migrate.py", "plan", self.snap, "--staging", stage, "--plan", plan, "--library", self.lib, "--only", "Founding Sales")
        self.assertEqual(code, 0, out)
        self.assertIn("6.9%", out)
        ops = json.load(open(plan))["ops"]
        self.assertEqual([o["op"] for o in ops], ["delete", "delete", "put", "put_tree"])  # same name stem: stock files removed, folder kept
        side = os.path.join(stage, "Founding Sales - Pete Kazanjy.sdr", "metadata.epub.lua")
        self.assertAlmostEqual(kc_lib.lua_load(open(side).read())["last_percent"], 0.069)
        self.assertEqual(kindle.check_plan(ops, False), [])

    def test_collections_build(self):
        wanted = os.path.join(self.tmp.name, "w.json")
        json.dump({"1 · Now": ["Founding Sales", "Never Split"], "Empty": ["Nope"], "Ambig": ["Hormozi"]}, open(wanted, "w"))
        stage = os.path.join(self.tmp.name, "c")
        code, out = run("collections_kc.py", "build", self.snap, "--wanted", wanted, "--staging", stage)
        data = kc_lib.lua_load(open(os.path.join(stage, "collection.lua")).read())
        files = [e["file"] for e in kc_lib.lua_array(data["1 · Now"])]
        self.assertIn("/mnt/us/documents/Never Split the Difference - Chris Voss (34).epub", files)
        self.assertNotIn("Empty", data)
        self.assertIn("matches 2 books", out)
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
