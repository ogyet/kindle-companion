# Jailbreak: guide and copy

A jailbreak lets the Kindle run KOReader and other homebrew. Methods change fast: in 2026, new exploits were usually patched by Amazon within weeks. So this procedure never relies on memory. Each time, it reads the live guide at **kindlemodding.org**, the community's canonical source, and follows it.

You do two jobs:
- **Guide:** identify the device, find the right method, and explain each step in plain words.
- **Copy:** download the files the guide links to (after the user approves) and copy them to the Kindle with a plan.

The on-device steps (taps, typing codes, restarts) are the user's. Never invent a step, and never use a file the guide doesn't link to.

## 0. Ground rules to tell the user

- Amazon doesn't support jailbreaks, and a mistake can brick the device. It's the owner's device and the owner's choice. Following the guide exactly keeps the risk low.
- **Stay offline first.** Turn on airplane mode before starting (unless the method page says otherwise). An automatic update can patch the exploit mid-way.
- **Back up first:** `kindle.py backup "$HOME/Documents/Kindle Companion/backups/pre-jailbreak-$(date +%F)"`.
- **No DRM removal.** Removing DRM is not part of a jailbreak, and this skill doesn't do it.

## 1. Identify the device

- Run `kindle.py info`. It reports the model (decoded from the serial number) and the MTP version string.
- Ask the user to read the exact firmware on the Kindle: Settings › Device Options › Device Info (for example 5.20.2). That number decides the method, so don't guess it.
- Check `jailbreak_signs` in the output. If KOReader or KUAL folders already exist, the device may already be jailbroken; skip to the post-jailbreak checklist.

## 2. Read the live guide (every time)

Open these in the built-in browser, or fetch them, and read them before saying anything about methods:
- **Wizard:** https://kindlemodding.org/jailbreak-wizard.html. It also loads `https://kindlemodding.org/jailbreakFinder.js`, which holds the model + firmware → method table. Read that table if the page is hard to drive.
- **Jailbreak index:** https://kindlemodding.org/jailbreaking/. It lists every method page (for example Vera, Shadow, SpiderCat, WinterBreak).
- **Models table:** https://kindlemodding.org/kindle-hacking/models-table.html
- **The chosen method's page,** in full. Note its firmware range, requirements (a PC, registration, airplane mode), the files to download, and the order of steps.

If the user's firmware is newer than every listed range, say so plainly. Waiting is the safe answer: keep the Kindle offline and check the guide or its Discord later. Never try a method outside its stated range.

> Known-good data point, not a rule: in November 2026, Véra worked on a Paperwhite 12th gen on 5.20.2. Always confirm against the live page.

## 3. Summarize the plan for the user

Before downloading anything, give a short numbered list:
- which steps are theirs (on the device)
- which steps you'll do (download and copy)
- what to expect at each step (restarts, a "Jailbroken" book appearing, and so on)

Then wait for their yes.

## 4. Download (with approval) and copy

- **Download each file** the method page links to, with `fetch.py url <link> --out "$HOME/Documents/Kindle Companion/staging/jailbreak" [--unzip]`.
  - Before each download, state the filename, the source and the expected size, and get approval.
  - `fetch.py` only accepts kindlemodding.org and GitHub hosts. If the guide points elsewhere, show the user the link and let them download it themselves.
- **Compare the SHA-256** with any checksum the page lists.
- **Write a plan** with one `put` op per file to the exact folder the guide names:
  - Files that belong in the Kindle's root use `"remote_dir": ""` and need `kindle.py apply <plan> --allow-root`.
  - Everything else goes under `documents/`, `extensions/` or `mrpackages/`.
- **Dry-run, apply, then check:** run `kindle.py ls "" --depth 1` (or the target folder) and confirm the files are there with the right sizes.
- **Tell the user to eject or unplug** when the guide says to.

## 5. On-device steps (the user)

Relay the guide's steps one at a time and wait for "done" between them. If something unexpected appears on screen, stop and re-read the method page's troubleshooting or FAQ section. Don't improvise.

## 6. Post-jailbreak checklist

Every item has its own page linked from https://kindlemodding.org/jailbreaking/ (look under "post-jailbreak" and "what's next"). Read each page live and copy files the same way as in step 4.

1. **Hotfix.** It keeps the jailbreak working after reboots and minor updates. Re-run it after every firmware update.
2. **KUAL + MRPI:** the app launcher and the package installer, for `.bin` packages.
3. **Block automatic updates,** using the guide's current method (for example a filler file, or the update-blocking package).
   - Check it: `kindle.py info` lists `update_files_in_root`. Any `update*.bin` sitting in the root is a pending update; tell the user.
   - Delete one only if the guide says to, since `kindle.py` won't delete root files.
4. **KOReader:** https://kindlemodding.org/jailbreaking/whats-next/getting-koreader/. Then go to `koreader.md` for plugins.
5. **Re-check:** take a fresh `kindle.py info` and confirm KOReader, extensions/KUAL and mrpackages are present.

## Undo

For unjailbreaking, point to https://kindlemodding.org/jailbreaking/faq/unjailbreaking.html and follow it live.
