"""Shared helpers: KOReader Lua tables, snapshot reading, book discovery. Stdlib only.

A *snapshot* is a folder written by `kindle.py snapshot`: listing.json (every file/folder seen),
snapshot.json (device info) and files/<kindle path> (copies of small metadata files).
"""
import json
import os
import re
import unicodedata

BOOK_EXT = (".epub", ".azw3", ".azw", ".mobi", ".pdf", ".kfx", ".cbz", ".fb2", ".djvu", ".txt", ".docx")
KINDLE_ONLY_EXT = (".azw3", ".azw", ".mobi", ".kfx")
DEVICE_ROOT = "/mnt/us"  # how KOReader on a Kindle sees the USB root
HOME = os.path.expanduser(os.environ.get("KC_HOME", "~/Documents/Kindle Companion"))

# ------------------------------------------------------------------ Lua (KOReader's dump.lua format)
_TOK = re.compile(r'\s*(?:(--[^\n]*)|(\[)|(\])|(\{)|(\})|(=)|(,)|(;)|("(?:[^"\\]|\\.)*")|(\'(?:[^\'\\]|\\.)*\')|'
                  r'(-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)|(true|false|nil)|(return)|([A-Za-z_]\w*))', re.S)


def _tokens(s):
    i, out = 0, []
    while i < len(s):
        if not s[i:].strip():
            break
        m = _TOK.match(s, i)
        if not m or m.end() == i:
            raise ValueError(f"unexpected text at {i}: {s[i:i + 30]!r}")
        i = m.end()
        if m.group(1):
            continue
        out.append(next(g for g in m.groups()[1:] if g is not None))
    return out


def _unescape(q):
    body = q[1:-1]
    def rep(m):
        g = m.group(1)
        if g.isdigit():
            return chr(int(g))
        return {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "f": "\f", "v": "\v", "\n": "\n"}.get(g, g)
    s = re.sub(r'\\(\d{1,3}|.)', rep, body, flags=re.S)
    try:  # KOReader writes UTF-8 bytes; \ddd escapes may encode bytes of a multi-byte char
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


class _P:
    def __init__(self, t):
        self.t, self.i = t, 0

    def peek(self, k=0):
        return self.t[self.i + k] if self.i + k < len(self.t) else None

    def eat(self, x=None):
        v = self.peek()
        if x is not None and v != x:
            raise ValueError(f"expected {x!r}, got {v!r}")
        self.i += 1
        return v

    def value(self):
        v = self.peek()
        if v == "{":
            return self.table()
        self.eat()
        if v[0] in "\"'":
            return _unescape(v)
        if v in ("true", "false"):
            return v == "true"
        if v == "nil":
            return None
        return float(v) if any(c in v for c in ".eE") else int(v)

    def table(self):
        self.eat("{")
        d, arr = {}, 1
        while self.peek() != "}":
            if self.peek() == "[":
                self.eat("[")
                k = self.value()
                self.eat("]")
                self.eat("=")
            elif re.fullmatch(r"[A-Za-z_]\w*", self.peek() or "") and self.peek(1) == "=":
                k = self.eat()
                self.eat("=")
            else:
                k, arr = arr, arr + 1
            d[k] = self.value()
            if self.peek() in (",", ";"):
                self.eat()
        self.eat("}")
        return d


def lua_load(text):
    """Parse `return { ... }` (KOReader settings / sidecar / collection files). Empty text -> {}."""
    if not text.strip():
        return {}
    p = _P(_tokens(text))
    p.eat("return")
    return p.table()


def _lua_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r") + '"'


def lua_dump(v, ind=0):
    pad = "    " * (ind + 1)
    if isinstance(v, dict):
        if not v:
            return "{}"
        keys = sorted(v, key=lambda k: (isinstance(k, str), k if isinstance(k, str) else f"{k:012d}"))
        lines = [f"{pad}[{_lua_str(k) if isinstance(k, str) else k}] = {lua_dump(v[k], ind + 1)}," for k in keys]
        return "{\n" + "\n".join(lines) + "\n" + "    " * ind + "}"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return _lua_str(v)
    if v is None:
        return "nil"
    raise TypeError(type(v))


def lua_file_text(data, comment="written by kindle-companion"):
    text = f"-- {comment}\nreturn " + lua_dump(data) + "\n"
    if lua_load(text) != data:
        raise ValueError("Lua round-trip mismatch; refusing to write")
    return text


def lua_array(t):
    return [t[k] for k in sorted(k for k in t if isinstance(k, int))] if isinstance(t, dict) else []


# ------------------------------------------------------------------ text helpers
def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\(\d+\)$", "", s.strip())  # Calibre "(id)" suffix
    s = re.sub(r"[_:;,.!?'\"’“”()\[\]-]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def stem(path):
    b = os.path.basename(path)
    return b.rsplit(".", 1)[0] if "." in b else b


# ------------------------------------------------------------------ snapshot
class Snapshot:
    def __init__(self, path):
        self.path = path
        self.listing = json.load(open(os.path.join(path, "listing.json"), encoding="utf-8"))
        mp = os.path.join(path, "snapshot.json")
        self.meta = json.load(open(mp)) if os.path.exists(mp) else {}
        self.files = {e["path"]: e for e in self.listing if not e["dir"]}
        self.dirs = {e["path"] for e in self.listing if e["dir"]}
        self._calibre = None

    def local(self, kindle_path):
        p = os.path.join(self.path, "files", kindle_path)
        return p if os.path.exists(p) else None

    def read(self, kindle_path):
        p = self.local(kindle_path)
        return open(p, encoding="utf-8", errors="replace").read() if p else None

    def calibre_meta(self):
        """documents/metadata.calibre (written by Calibre's USB driver): lpath -> record."""
        if self._calibre is None:
            self._calibre = {}
            txt = self.read("metadata.calibre") or self.read("documents/metadata.calibre")  # MTP vs USB-drive Kindles
            if txt:
                try:
                    for m in json.loads(txt):
                        lp = (m.get("lpath") or "").lower()
                        self._calibre[lp] = m
                        self._calibre["documents/" + lp] = m
                except ValueError:
                    pass
        return self._calibre

    def books(self):
        """Every book file under documents/, with what we know about it."""
        out = []
        cal = self.calibre_meta()
        for p, e in sorted(self.files.items()):
            if not p.startswith("documents/") or not p.lower().endswith(BOOK_EXT):
                continue
            low = p.lower()
            if ".sdr/" in low or "/dictionaries/" in low or low.endswith(("-jb.azw3", "fontcal.azw3")) or "/.assets/" in low:
                continue
            if low.endswith(".txt") and os.path.basename(low) in ("my clippings.txt",):
                continue
            m = cal.get(low) or cal.get(low[len("documents/"):]) or {}
            title = m.get("title") or _title_from_name(p)
            authors = m.get("authors") or []
            out.append(Book(self, p, e["size"], e.get("mtime"), title, ", ".join(authors) if isinstance(authors, list) else str(authors),
                            m.get("application_id")))
        return out

    def sidecar_dir(self, book_path):
        return book_path.rsplit(".", 1)[0] + ".sdr"

    def koreader_sidecar(self, book_path):
        """Parsed KOReader metadata for a book (doc-folder mode, or koreader/docsettings 'dir' mode)."""
        ext = book_path.rsplit(".", 1)[-1].lower()
        cands = [f"{self.sidecar_dir(book_path)}/metadata.{ext}.lua",
                 f"koreader/docsettings/mnt/us/{self.sidecar_dir(book_path)}/metadata.{ext}.lua"]
        for c in cands:
            t = self.read(c)
            if t:
                try:
                    return lua_load(t)
                except ValueError:
                    return {"_unreadable": True}
        return None

    def all_koreader_sidecars(self):
        """Every metadata.*.lua anywhere in the snapshot, including hash mode: (kindle_path, parsed)."""
        for p in self.files:
            if re.search(r"/metadata\.[a-z0-9]+\.lua$", p) and not p.endswith(".old"):
                t = self.read(p)
                if not t:
                    continue
                try:
                    yield p, lua_load(t)
                except ValueError:
                    continue

    def stock_reading_files(self, book_path):
        sdr = self.sidecar_dir(book_path) + "/"
        return [p for p in self.files if p.startswith(sdr) and p.lower().endswith((".azw3f", ".azw3r", ".yjr", ".yjf", ".mbp", ".mbs"))]

    def collections(self):
        t = self.read("koreader/settings/collection.lua")
        return lua_load(t) if t else {}


def _title_from_name(p):
    s = stem(p)
    s = re.sub(r"\s*\(\d+\)$", "", s)  # Calibre id suffix
    s = re.sub(r"_[A-Z0-9]{10}$", "", s)  # Amazon ASIN suffix
    return s.replace("_", " ").strip()


class Book:
    def __init__(self, snap, path, size, mtime, title, authors, calibre_id):
        self.snap, self.path, self.size, self.mtime = snap, path, size, mtime
        title = re.sub(r"[ _]B0[0-9A-Z]{8}$", "", (title or "").strip())  # Amazon ASIN left in the title
        authors = "" if (authors or "").strip().lower() in ("unknown", "") else authors
        self.title, self.authors, self.calibre_id = title, authors, calibre_id
        if " - " in title and not authors:  # Calibre's "Title - Author" file naming
            self.title, self.authors = title.rsplit(" - ", 1)
        self.ext = path.rsplit(".", 1)[-1].lower()
        ko = snap.koreader_sidecar(path) or {}
        props = ko.get("doc_props") or {}
        if props.get("title") and not calibre_id:
            self.title = props["title"]
        if props.get("authors") and not self.authors:
            self.authors = props["authors"].replace("\n", ", ")
        self.ko = ko
        self.percent = ko.get("percent_finished")
        self.status = (ko.get("summary") or {}).get("status")
        self.annotations = len([a for a in lua_array(ko.get("annotations") or {}) if a.get("pos0") is not None])
        if not self.annotations and ko.get("bookmarks"):
            self.annotations = len([b for b in lua_array(ko["bookmarks"]) if b.get("highlighted") or b.get("pos0")])
        self.stock_files = snap.stock_reading_files(path)
        self.amazon = "/downloads/" in path.lower() or bool(re.search(r"_[A-Z0-9]{10}\.(azw|azw3|kfx)$", path, re.I)) or "_EBOK" in path

    @property
    def device_path(self):
        return f"{DEVICE_ROOT}/{self.path}"

    def key(self):
        a = norm(self.authors).split(" ")[-1] if self.authors else ""
        return (norm(self.title)[:60], a)

    def as_dict(self):
        return {"path": self.path, "title": self.title, "authors": self.authors, "format": self.ext,
                "size_mb": round(self.size / 1e6, 1), "calibre_id": self.calibre_id,
                "koreader_percent": round(self.percent * 100, 1) if isinstance(self.percent, (int, float)) else None,
                "status": self.status, "highlights": self.annotations, "stock_reading_data": bool(self.stock_files),
                "amazon_purchase": self.amazon}


def latest_snapshot(home=HOME):
    d = os.path.join(home, "snapshots")
    if not os.path.isdir(d):
        return None
    snaps = sorted(x for x in os.listdir(d) if os.path.exists(os.path.join(d, x, "listing.json")))
    return os.path.join(d, snaps[-1]) if snaps else None


def write_plan(path, ops, note=""):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    json.dump({"note": note, "ops": ops}, open(path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return path
