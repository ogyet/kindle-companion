"""Talk to a Kindle over USB from macOS: MTP Kindles (2024+ models) via libmtp, older ones as a USB drive.

Every command opens the device ONCE, does all its work, and releases it. Newer Kindles drop off USB
after each MTP session, so never call this in a loop of single-file commands; batch work into `apply`.

Usage (always run with `python3 -I`):
  kindle.py doctor                         check libmtp, Calibre, other MTP apps; read-only
  kindle.py info [--json]                  model, serial, firmware hint, storage, jailbreak signs
  kindle.py ls [PATH] [--depth N] [--json] list files (default: documents, depth 2)
  kindle.py snapshot OUT_DIR               listing + small metadata files (sidecars, clippings,
                                           KOReader settings) copied into OUT_DIR; read-only
  kindle.py backup OUT_DIR [--with-books]  snapshot plus (optionally) every book file
  kindle.py apply PLAN.json [--dry-run] [--allow-root] [--backup-dir DIR]
                                           run a reviewed plan of put/get/delete/rmtree/mkdir ops

Plan format (JSON): {"ops": [
  {"op": "put",     "local": "/path/book.epub",  "remote_dir": "documents"},
  {"op": "put_tree","local": "/path/x.koplugin", "remote_dir": "koreader/plugins"},
  {"op": "get",     "remote": "documents/My Clippings.txt", "local": "/tmp/clip.txt"},
  {"op": "delete",  "remote": "documents/old.azw3"},
  {"op": "rmtree",  "remote": "documents/old.sdr"},
  {"op": "mkdir",   "remote": "documents/Samples"} ]}
Safety: writes are limited to documents/, koreader/, extensions/, mrpackages/ (root-level files only
with --allow-root, used for jailbreak/hotfix files). Deletes are limited to documents/ and
koreader/plugins/. Any file under 20 MB is copied to the backup dir before it is deleted or replaced.
Env: KC_LIBMTP (path to libmtp.dylib), KC_MOUNT (USB-drive mount point, default /Volumes/Kindle).
"""
import argparse
import ctypes
import ctypes.util
import datetime as dt
import glob
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT_ID = 0xFFFFFFFF
FOLDER = 0
FORCE_RESET_ON_CLOSE = 0x10000000  # libmtp src/device-flags.h
BACKUP_MAX = 20 * 1024 * 1024
WRITE_ZONES = ("documents/", "koreader/", "extensions/", "mrpackages/")
DELETE_ZONES = ("documents/", "koreader/plugins/")
SNAPSHOT_SUFFIXES = (".lua", ".azw3f", ".azw3r", ".yjr", ".yjf", ".mbp", ".mbs", ".json", ".calibre", ".txt")
SNAPSHOT_MAX = 4 * 1024 * 1024
DEFAULT_HOME = os.path.expanduser("~/Documents/Kindle Companion")


def out(msg=""):
    print(msg, flush=True)


# ---------------------------------------------------------------- libmtp binding (mirrors libmtp.h 1.1.x)
class DeviceEntry(ctypes.Structure):
    _fields_ = [("vendor", ctypes.c_char_p), ("vendor_id", ctypes.c_uint16), ("product", ctypes.c_char_p),
                ("product_id", ctypes.c_uint16), ("device_flags", ctypes.c_uint32)]


class RawDevice(ctypes.Structure):
    _fields_ = [("device_entry", DeviceEntry), ("bus_location", ctypes.c_uint32), ("devnum", ctypes.c_uint8)]


class File(ctypes.Structure):
    pass


File._fields_ = [("item_id", ctypes.c_uint32), ("parent_id", ctypes.c_uint32), ("storage_id", ctypes.c_uint32),
                 ("filename", ctypes.c_void_p), ("filesize", ctypes.c_uint64), ("modificationdate", ctypes.c_long),
                 ("filetype", ctypes.c_int), ("next", ctypes.POINTER(File))]


class Storage(ctypes.Structure):
    pass


Storage._fields_ = [("id", ctypes.c_uint32), ("StorageType", ctypes.c_uint16), ("FilesystemType", ctypes.c_uint16),
                    ("AccessCapability", ctypes.c_uint16), ("MaxCapacity", ctypes.c_uint64),
                    ("FreeSpaceInBytes", ctypes.c_uint64), ("FreeSpaceInObjects", ctypes.c_uint64),
                    ("StorageDescription", ctypes.c_char_p), ("VolumeIdentifier", ctypes.c_char_p),
                    ("next", ctypes.POINTER(Storage)), ("prev", ctypes.POINTER(Storage))]


class MtpDevice(ctypes.Structure):
    _fields_ = [("object_bitsize", ctypes.c_uint8), ("params", ctypes.c_void_p), ("usbinfo", ctypes.c_void_p),
                ("storage", ctypes.POINTER(Storage))]  # remaining fields unused


def find_libmtp():
    cands = [os.environ.get("KC_LIBMTP"), "/opt/homebrew/lib/libmtp.dylib", "/usr/local/lib/libmtp.dylib",
             "/opt/local/lib/libmtp.dylib", ctypes.util.find_library("mtp")]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def load_libmtp():
    path = find_libmtp()
    if not path:
        sys.exit("libmtp not found. Install it with:  brew install libmtp   (or set KC_LIBMTP)")
    lib = ctypes.CDLL(path)
    P = ctypes.POINTER
    sig = {
        "LIBMTP_Init": (None, []),
        "LIBMTP_Detect_Raw_Devices": (ctypes.c_int, [P(P(RawDevice)), P(ctypes.c_int)]),
        "LIBMTP_Open_Raw_Device_Uncached": (P(MtpDevice), [P(RawDevice)]),
        "LIBMTP_Release_Device": (None, [P(MtpDevice)]),
        "LIBMTP_Get_Storage": (ctypes.c_int, [P(MtpDevice), ctypes.c_int]),
        "LIBMTP_Get_Files_And_Folders": (P(File), [P(MtpDevice), ctypes.c_uint32, ctypes.c_uint32]),
        "LIBMTP_destroy_file_t": (None, [P(File)]),
        "LIBMTP_new_file_t": (P(File), []),
        "LIBMTP_Get_File_To_File": (ctypes.c_int, [P(MtpDevice), ctypes.c_uint32, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_void_p]),
        "LIBMTP_Send_File_From_File": (ctypes.c_int, [P(MtpDevice), ctypes.c_char_p, P(File), ctypes.c_void_p, ctypes.c_void_p]),
        "LIBMTP_Create_Folder": (ctypes.c_uint32, [P(MtpDevice), ctypes.c_char_p, ctypes.c_uint32, ctypes.c_uint32]),
        "LIBMTP_Delete_Object": (ctypes.c_int, [P(MtpDevice), ctypes.c_uint32]),
        "LIBMTP_Clear_Errorstack": (None, [P(MtpDevice)]),
    }
    for name in ("Manufacturername", "Modelname", "Serialnumber", "Deviceversion", "Friendlyname"):
        sig["LIBMTP_Get_" + name] = (ctypes.c_void_p, [P(MtpDevice)])
    for name, (res, args) in sig.items():
        fn = getattr(lib, name)
        fn.restype, fn.argtypes = res, args
    return lib


class Entry:
    __slots__ = ("path", "name", "is_dir", "size", "mtime", "_id")

    def __init__(self, path, name, is_dir, size, mtime, _id=None):
        self.path, self.name, self.is_dir, self.size, self.mtime, self._id = path, name, is_dir, size, mtime, _id

    def as_dict(self):
        return {"path": self.path, "dir": self.is_dir, "size": self.size, "mtime": self.mtime}


class MTP:
    kind = "mtp"

    def __init__(self):
        self.lib = load_libmtp()
        self.lib.LIBMTP_Init()
        raw, n = ctypes.POINTER(RawDevice)(), ctypes.c_int(0)
        if self.lib.LIBMTP_Detect_Raw_Devices(ctypes.byref(raw), ctypes.byref(n)) != 0 or n.value < 1:
            raise SystemExit("No MTP device found. Is the Kindle plugged in and unlocked? Run `kindle.py doctor`.")
        # libmtp lists 2024+ Kindles (USB 1949:9981 and friends) with its "Android bugs" flag set, which
        # includes FORCE_RESET_ON_CLOSE: a USB reset after every session. To the Kindle that looks like
        # being unplugged, so it leaves USB mode and has to be replugged. libmtp reads the flags from this
        # raw-device struct when opening, so clearing the bit here keeps the Kindle connected between
        # commands. Set KC_USB_RESET=1 to restore libmtp's default if a session ever hangs.
        self.vid_pid = (raw[0].device_entry.vendor_id, raw[0].device_entry.product_id)
        self.reset_flag_was_set = bool(raw[0].device_entry.device_flags & FORCE_RESET_ON_CLOSE)
        if os.environ.get("KC_USB_RESET") != "1":
            raw[0].device_entry.device_flags &= ~FORCE_RESET_ON_CLOSE & 0xFFFFFFFF
        self.dev = self.lib.LIBMTP_Open_Raw_Device_Uncached(ctypes.byref(raw[0]))
        if not self.dev:
            raise SystemExit("Found the Kindle but could not open it: another app holds it (Calibre, OpenMTP, "
                             "Android File Transfer, or macOS ptpcamerad). Run `kindle.py doctor`.")
        self.lib.LIBMTP_Get_Storage(self.dev, 0)
        st = self.dev.contents.storage
        if not st:
            raise SystemExit("Kindle storage not visible: unlock the Kindle screen and replug.")
        self.sid = st.contents.id
        self.cap, self.free = st.contents.MaxCapacity, st.contents.FreeSpaceInBytes
        self._cache = {}

    def close(self):
        if self.dev:
            self.lib.LIBMTP_Release_Device(self.dev)
            self.dev = None

    def _str(self, name):
        p = getattr(self.lib, "LIBMTP_Get_" + name)(self.dev)
        return ctypes.string_at(p).decode("utf-8", "replace") if p else None

    def device_strings(self):
        s = {k: self._str(k) for k in ("Manufacturername", "Modelname", "Serialnumber", "Deviceversion", "Friendlyname")}
        if not s.get("Serialnumber"):  # 2024+ Kindles report "Kindle Paperwhite <SERIAL>" as the model name
            m = re.search(r"\b([A-Z0-9]{16})\b", f"{s.get('Modelname') or ''} {s.get('Friendlyname') or ''}")
            if m:
                s["Serialnumber"] = m.group(1)
                s["Modelname"] = (s.get("Modelname") or "").replace(m.group(1), "").strip()
                s["Friendlyname"] = (s.get("Friendlyname") or "").replace(m.group(1), "").strip()
        return s

    def _children(self, parent_id, parent_path):
        if parent_id in self._cache:
            return self._cache[parent_id]
        head = self.lib.LIBMTP_Get_Files_And_Folders(self.dev, self.sid, parent_id)
        items, cur = [], head
        while cur:
            f = cur.contents
            name = ctypes.string_at(f.filename).decode("utf-8", "replace") if f.filename else ""
            path = f"{parent_path}/{name}" if parent_path else name
            items.append(Entry(path, name, f.filetype == FOLDER, int(f.filesize), int(f.modificationdate), int(f.item_id)))
            # Copy the next address as a plain int BEFORE freeing: a ctypes pointer field is a view into
            # the struct's memory, so after destroy_file_t it would read freed memory (and the list ends).
            nxt = ctypes.cast(f.next, ctypes.c_void_p).value
            self.lib.LIBMTP_destroy_file_t(cur)
            cur = ctypes.cast(nxt, ctypes.POINTER(File)) if nxt else None
        self._cache[parent_id] = items
        return items

    def _resolve(self, path, mkdirs=False):
        cur, cur_path, is_dir = ROOT_ID, "", True
        for part in [p for p in path.strip("/").split("/") if p]:
            hit = next((e for e in self._children(cur, cur_path) if e.name == part), None)
            if hit is None:
                if not mkdirs:
                    return None
                new_id = self.lib.LIBMTP_Create_Folder(self.dev, part.encode(), 0 if cur == ROOT_ID else cur, self.sid)
                if not new_id:
                    self.lib.LIBMTP_Clear_Errorstack(self.dev)
                    raise IOError(f"could not create folder {cur_path}/{part}")
                self._cache.pop(cur, None)
                hit = Entry(f"{cur_path}/{part}".strip("/"), part, True, 0, 0, int(new_id))
            cur, cur_path, is_dir = hit._id, hit.path, hit.is_dir
        return Entry(cur_path, cur_path.rsplit("/", 1)[-1], is_dir, 0, 0, cur)

    def stat(self, path):
        parent, _, name = path.strip("/").rpartition("/")
        pe = self._resolve(parent) if parent else Entry("", "", True, 0, 0, ROOT_ID)
        if pe is None:
            return None
        return next((e for e in self._children(pe._id, pe.path) if e.name == name), None)

    def listdir(self, path):
        e = self._resolve(path) if path.strip("/") else Entry("", "", True, 0, 0, ROOT_ID)
        return self._children(e._id, e.path) if e and e.is_dir else []

    def get(self, path, local):
        e = self.stat(path)
        if e is None or e.is_dir:
            return False
        os.makedirs(os.path.dirname(os.path.abspath(local)), exist_ok=True)
        if self.lib.LIBMTP_Get_File_To_File(self.dev, e._id, local.encode(), None, None) != 0:
            self.lib.LIBMTP_Clear_Errorstack(self.dev)
            raise IOError(f"download failed: {path}")
        return True

    def put(self, local, remote_dir):
        d = self._resolve(remote_dir, mkdirs=True)
        name = os.path.basename(local)
        old = next((e for e in self._children(d._id, d.path) if e.name == name), None)
        if old:
            self.delete(old.path)
        f = self.lib.LIBMTP_new_file_t()
        libc = ctypes.CDLL(None)
        libc.strdup.restype, libc.strdup.argtypes = ctypes.c_void_p, [ctypes.c_char_p]
        f.contents.filename = libc.strdup(name.encode())
        f.contents.filesize = os.path.getsize(local)
        f.contents.parent_id = d._id
        f.contents.storage_id = self.sid
        rc = self.lib.LIBMTP_Send_File_From_File(self.dev, local.encode(), f, None, None)
        self.lib.LIBMTP_destroy_file_t(f)
        self._cache.pop(d._id, None)
        if rc != 0:
            self.lib.LIBMTP_Clear_Errorstack(self.dev)
            raise IOError(f"upload failed: {local}")

    def mkdir(self, path):
        self._resolve(path, mkdirs=True)

    def delete(self, path):
        e = self.stat(path)
        if e is None:
            return False
        if e.is_dir:
            raise IOError(f"{path} is a folder; use rmtree")
        if self.lib.LIBMTP_Delete_Object(self.dev, e._id) != 0:
            self.lib.LIBMTP_Clear_Errorstack(self.dev)
            raise IOError(f"delete failed: {path}")
        self._cache.clear()
        return True

    def rmtree(self, path):
        e = self.stat(path)
        if e is None:
            return False
        if not e.is_dir:
            raise IOError(f"{path} is a file; use delete")
        for c in list(self._children(e._id, e.path)):
            self.rmtree(c.path) if c.is_dir else self.delete(c.path)
        if self.lib.LIBMTP_Delete_Object(self.dev, e._id) != 0:
            self.lib.LIBMTP_Clear_Errorstack(self.dev)
            raise IOError(f"delete failed: {path}")
        self._cache.clear()
        return True


class Drive:
    """Older Kindles that mount as a USB drive."""
    kind = "usb-drive"

    def __init__(self, mount):
        self.root = mount
        st = os.statvfs(mount)
        self.cap, self.free = st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize

    def close(self):
        pass

    def _p(self, path):
        return os.path.join(self.root, path.strip("/"))

    def device_strings(self):
        return {"Modelname": "Kindle (USB drive)", "Serialnumber": None, "Deviceversion": None}

    def stat(self, path):
        p = self._p(path)
        if not os.path.exists(p):
            return None
        s = os.stat(p)
        return Entry(path.strip("/"), os.path.basename(p), os.path.isdir(p), s.st_size, int(s.st_mtime))

    def listdir(self, path):
        p = self._p(path)
        if not os.path.isdir(p):
            return []
        res = []
        for n in sorted(os.listdir(p)):
            if n.startswith("._"):
                continue
            rp = f"{path.strip('/')}/{n}".strip("/")
            res.append(self.stat(rp))
        return [r for r in res if r]

    def get(self, path, local):
        p = self._p(path)
        if not os.path.isfile(p):
            return False
        os.makedirs(os.path.dirname(os.path.abspath(local)), exist_ok=True)
        shutil.copy2(p, local)
        return True

    def put(self, local, remote_dir):
        os.makedirs(self._p(remote_dir), exist_ok=True)
        shutil.copy2(local, os.path.join(self._p(remote_dir), os.path.basename(local)))

    def mkdir(self, path):
        os.makedirs(self._p(path), exist_ok=True)

    def delete(self, path):
        p = self._p(path)
        if not os.path.exists(p):
            return False
        os.remove(p)
        return True

    def rmtree(self, path):
        p = self._p(path)
        if not os.path.exists(p):
            return False
        shutil.rmtree(p)
        return True


# ---------------------------------------------------------------- helpers
def mount_point():
    m = os.environ.get("KC_MOUNT", "/Volumes/Kindle")
    return m if os.path.isdir(os.path.join(m, "documents")) else None


def blockers():
    """Apps that hold an MTP device on macOS. Returns list of (name, pids)."""
    found = []
    for name, pattern in [("Calibre", "calibre.app/Contents/MacOS"), ("OpenMTP", "OpenMTP.app/Contents/MacOS"),
                          ("Android File Transfer", "Android File Transfer"), ("Kindle USB File Manager", "USB File Manager.app")]:
        r = subprocess.run(["pgrep", "-if", pattern], capture_output=True, text=True)
        pids = [p for p in r.stdout.split() if p and int(p) != os.getpid()]
        if pids:
            found.append((name, pids))
    return found


def free_ptp():
    """macOS's camera daemons grab MTP devices; they restart on their own, so stopping them is harmless."""
    for d in ("ptpcamerad", "icdd"):
        subprocess.run(["killall", d], capture_output=True)


def open_device(allow_busy=False):
    m = mount_point()
    if m:
        return Drive(m)
    busy = blockers()
    if busy and not allow_busy:
        names = ", ".join(n for n, _ in busy)
        raise SystemExit(f"{names} is running and will block the Kindle. Quit it (don't just close the window), then retry.")
    free_ptp()
    return MTP()


def walk(dev, path, depth, max_depth):
    for e in dev.listdir(path):
        yield e
        if e.is_dir and depth < max_depth:
            yield from walk(dev, e.path, depth + 1, max_depth)


def lookup_model(serial):
    if not serial:
        return None
    t = json.load(open(os.path.join(HERE, "models.json")))
    s = serial.replace(" ", "").upper()
    if s[:1] in ("B", "9") and s[2:4] in t["legacy"]:
        return t["legacy"][s[2:4]]
    return t["v2"].get(s[3:6])


def jailbreak_signs(dev):
    root = {e.name for e in dev.listdir("")}
    docs = {e.name for e in dev.listdir("documents")}
    return {
        "koreader": "koreader" in root,
        "kual_extensions_folder": "extensions" in root,
        "mrpi_folder": "mrpackages" in root,
        "hotfix": "libkh" in root or any("hotfix" in n.lower() for n in docs),
        "kmc_folder": "kmc" in root,
        "jailbreak_marker": any(n.lower().startswith("jailbr") or n.lower().endswith("-jb.azw3") for n in docs),
        "update_files_in_root": sorted(n for n in root if n.lower().startswith("update") and n.lower().endswith(".bin")),
    }


def in_zone(path, zones):
    p = path.strip("/") + "/"
    return any(p.startswith(z) for z in zones) and ".." not in p.split("/")


# ---------------------------------------------------------------- commands
def cmd_doctor(a):
    ok = True
    lib = find_libmtp()
    out(f"libmtp: {lib or 'MISSING  -> brew install libmtp'}")
    ok &= bool(lib)
    m = mount_point()
    out(f"USB-drive Kindle mounted: {m or 'no (fine for MTP Kindles)'}")
    for name, pids in blockers():
        out(f"BLOCKER: {name} is running (pids {' '.join(pids)}). Quit it before using the Kindle over MTP.")
        ok = False
    try:
        import sqlite3  # noqa: F401
    except ImportError:
        out("python sqlite3 missing")
    out("Status: " + ("ready" if ok else "fix the items above"))
    return 0 if ok else 1


def cmd_info(a):
    dev = open_device()
    try:
        s = dev.device_strings()
        model = lookup_model(s.get("Serialnumber"))
        info = {"connection": dev.kind, "strings": s, "model": model,
                "storage_gb": round(dev.cap / 1e9, 1), "free_gb": round(dev.free / 1e9, 2),
                "jailbreak_signs": jailbreak_signs(dev),
                "documents_visible": dev.stat("documents") is not None,
                "usb_reset_on_close": (None if dev.kind != "mtp" else
                                       ("on (KC_USB_RESET=1)" if os.environ.get("KC_USB_RESET") == "1" else
                                        "off" + (" (libmtp default was on; turned off so the Kindle stays connected)"
                                                 if dev.reset_flag_was_set else ""))),
                "book_files": sum(1 for e in dev.listdir("documents") if not e.is_dir and
                                  e.name.lower().endswith((".epub", ".azw3", ".azw", ".mobi", ".pdf", ".kfx", ".txt")))}
    finally:
        dev.close()
    if a.json:
        out(json.dumps(info, indent=1))
        return 0
    s = info["strings"]
    out(f"Connection: {info['connection']}")
    out(f"Model:      {(model or {}).get('name', 'unknown (check Settings > Device Options > Device Info)')}")
    if s.get("Serialnumber"):
        out(f"Serial:     {s['Serialnumber'][:6]}… (first 6 shown; enough to identify the model)")
    out(f"Version:    {s.get('Deviceversion') or 'unknown'}  (MTP version string; confirm firmware on the Kindle: "
        "Settings > Device Options > Device Info)")
    out(f"Storage:    {info['free_gb']} GB free of {info['storage_gb']} GB")
    out(f"Books in documents/: {info['book_files']}")
    if not info["documents_visible"]:
        out("WARNING: " + HIDDEN_STORAGE)
    out("Jailbreak signs: " + ", ".join(f"{k}={v}" for k, v in info["jailbreak_signs"].items()))
    if info["usb_reset_on_close"]:
        out(f"USB reset after each session: {info['usb_reset_on_close']}")
    return 0


def cmd_ls(a):
    dev = open_device()
    try:
        rows = list(walk(dev, a.path, 1, a.depth))
    finally:
        dev.close()
    if a.json:
        out(json.dumps([r.as_dict() for r in rows], indent=0))
    else:
        for r in rows:
            out(f"{'D' if r.is_dir else 'F'}\t{r.path}\t{r.size}")
        out(f"# {len(rows)} entries")
    return 0


HIDDEN_STORAGE = ("No documents/ folder is visible on the Kindle. Unlock its screen and dismiss any USB "
                  "prompt, then run the command again (no replug needed).")


def check_visible(dev):
    if dev.stat("documents") is None:
        raise SystemExit(HIDDEN_STORAGE)


def snapshot_into(dev, outdir, with_books=False):
    check_visible(dev)
    os.makedirs(outdir, exist_ok=True)
    listing, fetched, failed = [], 0, []
    roots = [("documents", 6), ("koreader/settings", 2), ("koreader/docsettings", 8), ("koreader/hashdocsettings", 4),
             ("koreader/plugins", 1)]
    for root, depth in roots:
        if dev.stat(root) is None:
            continue
        for e in walk(dev, root, 1, depth):
            listing.append(e.as_dict())
            if e.is_dir:
                continue
            small_meta = e.size <= SNAPSHOT_MAX and (e.name.lower().endswith(SNAPSHOT_SUFFIXES))
            is_book = e.name.lower().endswith((".epub", ".azw3", ".azw", ".mobi", ".pdf", ".kfx", ".cbz"))
            if small_meta or (with_books and is_book):
                try:
                    dev.get(e.path, os.path.join(outdir, "files", e.path))
                    fetched += 1
                except IOError as err:
                    failed.append(f"{e.path}: {err}")
    for name in ("metadata.calibre", "driveinfo.calibre"):  # MTP Kindles: Calibre keeps these in the root
        e = dev.stat(name)
        if e and not e.is_dir and e.size <= SNAPSHOT_MAX * 4:
            listing.append(e.as_dict())
            try:
                dev.get(name, os.path.join(outdir, "files", name))
                fetched += 1
            except IOError as err:
                failed.append(f"{name}: {err}")
    s = dev.device_strings()
    meta = {"taken": dt.datetime.now().isoformat(timespec="seconds"), "connection": dev.kind,
            "model": lookup_model(s.get("Serialnumber")), "device_version": s.get("Deviceversion"),
            "free_bytes": dev.free, "jailbreak_signs": jailbreak_signs(dev), "with_books": with_books}
    json.dump(listing, open(os.path.join(outdir, "listing.json"), "w"), indent=0)
    json.dump(meta, open(os.path.join(outdir, "snapshot.json"), "w"), indent=1)
    return len(listing), fetched, failed


def cmd_snapshot(a, with_books=False):
    dev = open_device()
    try:
        n, fetched, failed = snapshot_into(dev, a.out_dir, with_books)
    finally:
        dev.close()
    out(f"Snapshot in {a.out_dir}: {n} entries listed, {fetched} files copied, {len(failed)} failed")
    for f in failed[:20]:
        out(f"  FAILED {f}")
    return 1 if failed else 0


def check_plan(ops, allow_root):
    problems = []
    for i, op in enumerate(ops, 1):
        kind = op.get("op")
        target = op.get("remote_dir") if kind in ("put", "put_tree") else op.get("remote")
        if kind not in ("put", "put_tree", "get", "delete", "rmtree", "mkdir"):
            problems.append(f"#{i}: unknown op {kind!r}")
            continue
        if target is None:
            problems.append(f"#{i}: missing target")
            continue
        if kind in ("put", "put_tree"):
            if not os.path.exists(op.get("local", "")):
                problems.append(f"#{i}: local file missing: {op.get('local')}")
            if target.strip("/") == "":
                if not allow_root:
                    problems.append(f"#{i}: writing to the Kindle's root needs --allow-root (jailbreak files only)")
            elif not in_zone(target, WRITE_ZONES):
                problems.append(f"#{i}: refusing to write outside {', '.join(WRITE_ZONES)}: {target}")
        if kind in ("delete", "rmtree") and not in_zone(target, DELETE_ZONES):
            problems.append(f"#{i}: refusing to delete outside {', '.join(DELETE_ZONES)}: {target}")
        if kind in ("delete", "rmtree") and target.strip("/") in ("documents", "koreader/plugins"):
            problems.append(f"#{i}: refusing to delete a top-level folder: {target}")
        if kind == "mkdir" and not in_zone(target, WRITE_ZONES):
            problems.append(f"#{i}: refusing to create folders outside {', '.join(WRITE_ZONES)}")
    return problems


def backup_path(dev, path, bdir, log):
    """Copy a file (or folder of small files) to the backup dir before it changes."""
    e = dev.stat(path)
    if e is None:
        return
    items = [e] if not e.is_dir else [x for x in walk(dev, path, 1, 10) if not x.is_dir]
    for x in items:
        if x.size > BACKUP_MAX:
            log.append(f"  (not backed up, {x.size // 1_000_000} MB: {x.path})")
            continue
        dev.get(x.path, os.path.join(bdir, x.path))


def cmd_apply(a):
    plan = json.load(open(a.plan, encoding="utf-8"))
    ops = plan["ops"] if isinstance(plan, dict) else plan
    problems = check_plan(ops, a.allow_root)
    if problems:
        out("Plan refused, nothing changed:")
        for p in problems:
            out("  " + p)
        return 2
    for i, op in enumerate(ops, 1):
        tgt = op.get("remote_dir", op.get("remote"))
        out(f"{i:>3}. {op['op']:<8} {op.get('local', '')} {'->' if op['op'].startswith('put') else ''} {tgt}")
    if a.dry_run:
        out(f"Dry run: {len(ops)} ops checked, nothing changed.")
        return 0
    bdir = a.backup_dir or os.path.join(DEFAULT_HOME, "backups", dt.datetime.now().strftime("%Y-%m-%d_%H%M%S"))
    dev = open_device()
    try:
        check_visible(dev)
    except SystemExit:
        dev.close()
        raise
    done, errors, missing, log = 0, 0, 0, []
    try:
        for i, op in enumerate(ops, 1):
            kind = op["op"]
            try:
                if kind == "get":
                    if dev.get(op["remote"], op["local"]):
                        done += 1
                    else:
                        missing += 1
                        log.append(f"  missing on Kindle: {op['remote']}")
                elif kind == "mkdir":
                    dev.mkdir(op["remote"])
                    done += 1
                elif kind in ("delete", "rmtree"):
                    if dev.stat(op["remote"]) is None:
                        missing += 1
                        log.append(f"  already gone: {op['remote']}")
                        continue
                    backup_path(dev, op["remote"], bdir, log)
                    (dev.rmtree if kind == "rmtree" else dev.delete)(op["remote"])
                    done += 1
                elif kind == "put":
                    dest = f"{op['remote_dir'].strip('/')}/{os.path.basename(op['local'])}".strip("/")
                    if dev.stat(dest):
                        backup_path(dev, dest, bdir, log)
                    dev.put(op["local"], op["remote_dir"].strip("/"))
                    got = dev.stat(dest)
                    if not got or got.size != os.path.getsize(op["local"]):
                        raise IOError(f"size check failed after upload: {dest}")
                    done += 1
                elif kind == "put_tree":
                    base = os.path.basename(op["local"].rstrip("/"))
                    for dirpath, _, files in os.walk(op["local"]):
                        rel = os.path.relpath(dirpath, os.path.dirname(op["local"].rstrip("/")))
                        rdir = f"{op['remote_dir'].strip('/')}/{rel}".strip("/")
                        dev.mkdir(rdir)
                        for fn in files:
                            if fn == ".DS_Store":
                                continue
                            dev.put(os.path.join(dirpath, fn), rdir)
                    done += 1
                    log.append(f"  copied folder {base} -> {op['remote_dir']}")
            except IOError as err:
                errors += 1
                log.append(f"  ERROR #{i}: {err}")
                if op.get("stop_on_error", True):
                    log.append("  stopped: later steps were not run")
                    break
    finally:
        dev.close()
    for line in log:
        out(line)
    if os.path.isdir(bdir):
        out(f"Backups of changed files: {bdir}")
    out(f"SUMMARY ok={done} missing={missing} errors={errors}")
    return 1 if errors else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    p = sub.add_parser("info")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("ls")
    p.add_argument("path", nargs="?", default="documents")
    p.add_argument("--depth", type=int, default=2)
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("snapshot")
    p.add_argument("out_dir")
    p = sub.add_parser("backup")
    p.add_argument("out_dir")
    p.add_argument("--with-books", action="store_true")
    p = sub.add_parser("apply")
    p.add_argument("plan")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--allow-root", action="store_true")
    p.add_argument("--backup-dir")
    a = ap.parse_args()
    for k in ("out_dir", "plan", "backup_dir"):
        if getattr(a, k, None):
            setattr(a, k, os.path.expanduser(getattr(a, k)))
    if a.cmd == "doctor":
        return cmd_doctor(a)
    if a.cmd == "info":
        return cmd_info(a)
    if a.cmd == "ls":
        return cmd_ls(a)
    if a.cmd == "snapshot":
        return cmd_snapshot(a)
    if a.cmd == "backup":
        return cmd_snapshot(a, with_books=a.with_books)
    if a.cmd == "apply":
        return cmd_apply(a)


if __name__ == "__main__":
    sys.exit(main())
