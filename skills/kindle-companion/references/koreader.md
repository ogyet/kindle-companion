# KOReader

KOReader is an open-source reader that runs on jailbroken Kindles. It reads EPUB, PDF, DjVu, CBZ, FB2, and DRM-free AZW3 and MOBI. It can't open Amazon purchases (DRM, KFX); those stay in the Kindle's own reader. Docs: https://koreader.rocks, plus the wiki at https://github.com/koreader/koreader/wiki

## Files KOReader keeps on the Kindle

| Path | What |
|---|---|
| `koreader/settings/collection.lua` | collections: `{["Name"] = {settings = {order = N}, [1] = {file = "/mnt/us/documents/x.epub", order = 1}, …}}` |
| `koreader/settings.reader.lua` | global settings, including `document_metadata_folder` ("doc", "dir" or "hash") |
| `documents/<book>.sdr/metadata.<ext>.lua` | per-book data in "doc" mode (the default): progress (`percent_finished`, `last_xpointer`), `annotations`, `doc_props`, and `summary.status` |
| `koreader/docsettings/mnt/us/documents/<book>.sdr/…` | the same data in "dir" mode |
| `koreader/hashdocsettings/<xx>/<hash>.sdr/…` | the same data in "hash" mode |
| `koreader/plugins/<name>.koplugin/` | installed plugins |

The sidecar folder is the book's path without its last extension, plus `.sdr`. So `Book (12).epub` → `Book (12).sdr/metadata.epub.lua`.

**Quit KOReader** (exit to the Kindle home screen) before changing its files over USB. It writes its settings and the current book's sidecar when it exits, which can overwrite your changes.

## Installing or updating a plugin

1. Check what's installed: look for `koreader/plugins/*.koplugin` in the snapshot listing (`library.py` doesn't list plugins; use `kindle.py ls koreader/plugins --depth 1`).
2. Ask before downloading, then run `fetch.py release OWNER/REPO --out "$HOME/Documents/Kindle Companion/staging/plugins" --plan <plan.json>`. It shows the release tag, its date and the plugin's version.
3. `kindle.py apply <plan.json> --dry-run`, then apply.
   - The plan removes the old plugin folder and copies the new one.
   - The plugin's settings live in `koreader/settings/`, so they survive.
4. The user restarts KOReader (Menu › Exit › Restart KOReader).

Always read the plugin's README first. Some need an extra step, such as a patch file or a font, that the plan doesn't cover.

## Plugin catalog (popular as of late 2026; verify each repo is still active before installing)

| Plugin | Repo | What it adds |
|---|---|---|
| SimpleUI | `doctorhetfield-cmd/simpleui.koplugin` | A customizable home screen with a bottom navigation bar, a top bar and desktop-style widgets. |
| Storefront | `ultimatejimmy/storefront.koplugin` | A plugin store inside KOReader: discover, install and update plugins, patches, fonts and screensavers on the device. It does not download books (for free books, use KOReader's built-in OPDS catalog). |
| Zen UI | `AnthonyGress/zen_ui.koplugin` | An alternative minimal interface. Pick it or SimpleUI, not both. |
| KoInsight | `dev107/KoInsight` | Reading statistics dashboard (a server on the Mac plus a plugin). |

Built in, nothing to install:
- **Calibre wireless** (wireless device connection)
- **Exporter** (highlights to Markdown, JSON, HTML or Readwise)
- **Statistics**
- **Wikipedia and dictionary lookup**
- **Progress sync**

For more plugins, see the lists at https://github.com/KindleTweaks/Awesome-Kindle and https://github.com/asapelkin/awesome-eink

## Calibre wireless

Use this to send books over Wi-Fi instead of USB.

**One-time setup in Calibre:**
1. Click Connect/share › Start wireless device connection.
2. Leave the password empty. KOReader's keyboard can be awkward, and the connection stays on the home network.

**On the Kindle, in KOReader:**
1. Make sure Wi-Fi is on.
2. Go to Menu › Tools › Calibre › Connect.
3. Optionally set the inbox folder to `/mnt/us/documents` and turn on "Automatic connection".

**Sending books:** in Calibre, select books › Send to device.

Calibre and `kindle.py` can't both hold a USB MTP Kindle at once, but wireless Calibre doesn't use USB.

## Screensaver

In KOReader, go to Menu › Settings › Screen › Sleep screen. Choose the book cover, a random image from a folder (for example `/mnt/us/screensaver`), or a message. To use your own images:
1. Put PNG/JPG files sized to the screen into `documents/screensaver/` with a `put` plan.
2. Point the sleep screen setting at `/mnt/us/documents/screensaver`.

The stock reader's lock-screen ads ("Special Offers") are a separate thing, removed through the Amazon account.
