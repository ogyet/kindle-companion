"""Minimal reader for Kindle reader-data files (.azw3r / .yjr, "KRDS" format).

Layout: 8-byte magic, then type-tagged values. Tags:
  0x00 bool(1)  0x01 int32  0x02 int64  0x03 string(flag, u16 len, bytes)
  0x04 double   0x05 float  0x06 int8   0x07 one byte
  0xFE begin object (followed by a name string without tag) ... 0xFF end object
Top level: version (long), object count (int), then that many objects.
"""
import struct, sys

MAGIC = b"\x00\x00\x00\x00\x00\x1a\xb1\x26"


class R:
    def __init__(self, b):
        self.b, self.i = b, 0

    def take(self, n):
        v = self.b[self.i:self.i + n]
        if len(v) < n:
            raise EOFError
        self.i += n
        return v

    def raw_string(self):
        flag = self.take(1)[0]
        if flag == 1:  # null string
            return None
        (n,) = struct.unpack(">H", self.take(2))
        return self.take(n).decode("utf-8", "replace")

    def value(self):
        t = self.take(1)[0]
        if t == 0x00: return bool(self.take(1)[0])
        if t == 0x01: return struct.unpack(">i", self.take(4))[0]
        if t == 0x02: return struct.unpack(">q", self.take(8))[0]
        if t == 0x03: return self.raw_string()
        if t == 0x04: return struct.unpack(">d", self.take(8))[0]
        if t == 0x05: return struct.unpack(">f", self.take(4))[0]
        if t == 0x06: return self.take(1)[0]
        if t == 0x07: return self.take(1)[0]  # 1-byte value (seen as "lpr 07 02 ...")
        if t == 0xFE:
            name = self.raw_string()
            items = []
            while self.b[self.i] != 0xFF:
                items.append(self.value())
            self.i += 1
            return (name, items)
        raise ValueError(f"unknown tag 0x{t:02x} at {self.i - 1}")


def parse(path):
    b = open(path, "rb").read()
    if not b.startswith(MAGIC):
        raise ValueError("not a KRDS file")
    r = R(b)
    r.i = len(MAGIC)
    version = r.value()
    count = r.value()
    objs = {}
    for _ in range(count):
        name, items = r.value()
        objs[name] = items
    return objs


def first_position(items):
    """lpr/fpr objects hold e.g. [version, 'position-string', timestamp]."""
    for v in items:
        if isinstance(v, str) and v.strip().lstrip("-").isdigit():
            return int(v)
        if isinstance(v, int) and not isinstance(v, bool) and v > 0 and v < 10**9:
            pass
    return None


if __name__ == "__main__":
    o = parse(sys.argv[1])
    for k, v in o.items():
        short = [x if not isinstance(x, tuple) else f"<{x[0]}:{len(x[1])}>" for x in v][:8]
        print(k, short)


def kf8_text_length(path):
    """Text length of the KF8 part of an AZW3/MOBI file; Kindle positions (lpr) count characters of it."""
    import struct as st
    b = open(path, "rb").read()
    nrec = st.unpack(">H", b[76:78])[0]
    offs = [st.unpack(">I", b[78 + 8 * i:82 + 8 * i])[0] for i in range(nrec)]

    def rec0(off):
        tl = st.unpack(">I", b[off + 4:off + 8])[0]
        ver = st.unpack(">I", b[off + 36:off + 40])[0] if b[off + 16:off + 20] == b"MOBI" else None
        return tl, ver
    tl, ver = rec0(offs[0])
    if ver != 8:  # joint MOBI6+KF8 file: the KF8 header follows the BOUNDARY record
        for i, o in enumerate(offs[:-1]):
            if b[o:o + 8] == b"BOUNDARY":
                tl, ver = rec0(offs[i + 1])
                break
    return tl


def last_position(path):
    """Furthest-read position (lpr, else fpr) from a .azw3f/.azw3r/.yjr file, or None."""
    o = parse(path)
    for key in ("lpr", "fpr"):
        for v in o.get(key, []):
            if isinstance(v, str) and v.strip().isdigit():
                return int(v)
    return None
