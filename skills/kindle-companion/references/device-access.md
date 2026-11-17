# Device access (macOS)

## Two kinds of Kindle

| Connection | Models | How `kindle.py` reaches it |
|---|---|---|
| **MTP** (no drive appears in Finder) | 2024+ Paperwhite (12th gen), Colorsoft, Kindle (12th gen, 2024), Scribe 2024 and later, and Scribe 2022 after firmware 5.16.3 | libmtp through `ctypes`: `brew install libmtp` |
| **USB drive** (mounts at `/Volumes/Kindle`) | most older models | ordinary file copies |

`kindle.py` picks automatically: a mounted `/Volumes/Kindle/documents` means USB drive, otherwise MTP. Set `KC_MOUNT` if the drive mounts under another name, and `KC_LIBMTP` if libmtp lives somewhere unusual.

## Why the Kindle needs replugging after a session, and the fix

libmtp's device table lists the 2024+ Kindles (USB id `1949:9981`, for example) with its "Android bugs" settings. One of them, `FORCE_RESET_ON_CLOSE`, sends a **USB reset** at the end of every session. To the Kindle a reset looks like being unplugged, so it leaves USB mode, and every tool built on libmtp (including the `mtp-*` commands) needed a replug before its next run.

`kindle.py` clears that one setting before connecting, so the Kindle should stay connected between commands. `info` prints `USB reset after each session: off`. If a session ever hangs or the device acts strangely, run that command with `KC_USB_RESET=1` to get libmtp's default behaviour back, and then replug.

Two habits still help:
- Batch many changes into one plan, so a run makes one connection rather than many.
- Only one program can hold the MTP device at a time; see the next section.

## Things that block MTP

| Blocker | Fix |
|---|---|
| **Calibre** (holds the device whenever it's open) | Quit it with Cmd-Q; closing the window isn't enough. |
| **OpenMTP, Android File Transfer** (its agent too), Amazon's USB file manager | Quit them. |
| **macOS `ptpcamerad` / `icdd`** (the camera services grab the device) | `kindle.py` stops them before connecting. They restart on their own, so this is harmless. |
| **Locked Kindle screen** | Unlock it. Storage may not show while the screen is locked. |

`kindle.py doctor` checks all of these. If `info` still fails:
1. unplug
2. unlock the Kindle
3. wait 5 seconds
4. plug in again
5. retry once

If it still fails, try another cable or port; a charge-only cable is the usual culprit.

## Snapshot layout

`kindle.py snapshot OUT` writes:
- `OUT/listing.json`: every file and folder under `documents/`, `koreader/settings`, `koreader/docsettings`, `koreader/hashdocsettings` and `koreader/plugins`, as `{path, dir, size, mtime}`.
- `OUT/snapshot.json`: when it was taken, the connection type, the model, the version string, free space, and jailbreak signs.
- `OUT/files/<kindle path>`: copies of small metadata files: `*.lua`, the stock reader's `.azw3f`, `.azw3r`, `.yjr` and `.yjf` files, `My Clippings.txt`, `metadata.calibre`.

Books themselves are not copied, unless you use `backup --with-books`.

## Plan format

```json
{"note": "why", "ops": [
  {"op": "put",      "local": "/abs/book.epub",       "remote_dir": "documents"},
  {"op": "put_tree", "local": "/abs/x.koplugin",      "remote_dir": "koreader/plugins"},
  {"op": "get",      "remote": "documents/My Clippings.txt", "local": "/abs/clip.txt"},
  {"op": "delete",   "remote": "documents/old.azw3"},
  {"op": "rmtree",   "remote": "documents/old.sdr"},
  {"op": "mkdir",    "remote": "documents/Samples"}
]}
```

- Ops run in order.
- The first error stops the run, unless that op sets `"stop_on_error": false`.
- `put` replaces a same-named file, after backing it up, and checks the size afterwards.
- `--dry-run` validates the plan and prints it without connecting.
- Remote paths are relative to the Kindle's USB root. On the device itself that root is `/mnt/us`, which is why KOReader files refer to `/mnt/us/documents/...`.
