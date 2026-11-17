"""Download KOReader plugins (GitHub releases) or jailbreak files (links from the kindlemodding.org guide).

Usage:
  fetch.py release OWNER/REPO --out DIR [--asset REGEX] [--plan OUT.json]
      latest GitHub release -> download the matching asset -> unzip -> find *.koplugin folders ->
      (with --plan) a plan that replaces koreader/plugins/<name>.koplugin with the new version
  fetch.py url URL --out DIR [--unzip]
      one file from an allowed host (kindlemodding.org, github.com and its download hosts);
      prints size and SHA-256 so it can be compared with the guide

Downloads only; never touches the Kindle. Zip entries with absolute paths or ".." are refused.
Plugin settings live in koreader/settings/, so replacing a plugin folder keeps your settings.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kc_lib import write_plan  # noqa: E402

ALLOWED = ("kindlemodding.org", "github.com", "api.github.com", "objects.githubusercontent.com",
           "release-assets.githubusercontent.com", "codeload.github.com", "raw.githubusercontent.com")
UA = {"User-Agent": "kindle-companion-skill", "Accept": "application/vnd.github+json"}


def allowed(url):
    host = urllib.parse.urlparse(url).hostname or ""
    return urllib.parse.urlparse(url).scheme == "https" and any(host == h or host.endswith("." + h) for h in ALLOWED)


def get(url, dest=None):
    if not allowed(url):
        sys.exit(f"Refusing to download from {url}: not an allowed host ({', '.join(ALLOWED)})")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        if not allowed(r.geturl()):
            sys.exit(f"Redirected to a host that isn't allowed: {r.geturl()}")
        data = r.read()
    if dest:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        open(dest, "wb").write(data)
    return data


def safe_unzip(path, outdir):
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if n.startswith("/") or ".." in n.split("/") or n.startswith("__MACOSX"):
                if n.startswith("__MACOSX"):
                    continue
                sys.exit(f"Unsafe path in zip, nothing extracted: {n}")
        for n in z.namelist():
            if not n.startswith("__MACOSX"):
                z.extract(n, outdir)


def describe(path):
    data = open(path, "rb").read()
    return len(data), hashlib.sha256(data).hexdigest()


def plugin_version(folder):
    meta = os.path.join(folder, "_meta.lua")
    if os.path.exists(meta):
        m = re.search(r'version\s*=\s*["\']?([\w.\-]+)', open(meta, encoding="utf-8", errors="replace").read())
        if m:
            return m.group(1)
    return None


def cmd_release(a):
    rel = json.loads(get(f"https://api.github.com/repos/{a.repo}/releases/latest"))
    assets = [x for x in rel.get("assets", []) if re.search(a.asset, x["name"], re.I)]
    if not assets:
        names = [x["name"] for x in rel.get("assets", [])]
        sys.exit(f"No asset matching {a.asset!r} in {a.repo} {rel.get('tag_name')}: {names}")
    asset = assets[0]
    dl = os.path.join(a.out, "download", asset["name"])
    get(asset["browser_download_url"], dl)
    size, sha = describe(dl)
    print(f"{a.repo} {rel.get('tag_name')} ({rel.get('published_at', '')[:10]}): {asset['name']}, {size // 1024} KB, sha256 {sha[:16]}…")
    staged = os.path.join(a.out, "staged", re.sub(r"\W+", "_", a.repo))
    if dl.endswith(".zip"):
        safe_unzip(dl, staged)
    found = []
    for dirpath, dirs, _ in os.walk(staged):
        for d in dirs:
            if d.endswith(".koplugin"):
                found.append(os.path.join(dirpath, d))
        dirs[:] = [d for d in dirs if not d.endswith(".koplugin")]
    if not found:
        sys.exit("No *.koplugin folder in the download; check the plugin's install instructions by hand.")
    ops = []
    for f in found:
        name = os.path.basename(f)
        print(f"  plugin folder: {name}  version {plugin_version(f) or '?'}  ({f})")
        ops += [{"op": "rmtree", "remote": f"koreader/plugins/{name}", "stop_on_error": True},
                {"op": "put_tree", "local": f, "remote_dir": "koreader/plugins"}]
    if a.plan:
        write_plan(a.plan, ops, f"install/update {a.repo} {rel.get('tag_name')}")
        print(f"Plan: {a.plan}  (restart KOReader after applying)")


def cmd_url(a):
    name = os.path.basename(urllib.parse.urlparse(a.url).path) or "download"
    dest = os.path.join(a.out, name)
    get(a.url, dest)
    size, sha = describe(dest)
    print(f"Saved {dest}: {size} bytes, sha256 {sha}")
    if a.unzip and dest.endswith(".zip"):
        target = os.path.join(a.out, name[:-4])
        safe_unzip(dest, target)
        for dirpath, _, files in os.walk(target):
            for fn in files:
                p = os.path.join(dirpath, fn)
                print(f"  {os.path.relpath(p, target)}  ({os.path.getsize(p)} bytes)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("release")
    p.add_argument("repo")
    p.add_argument("--out", required=True)
    p.add_argument("--asset", default=r"\.zip$")
    p.add_argument("--plan")
    p = sub.add_parser("url")
    p.add_argument("url")
    p.add_argument("--out", required=True)
    p.add_argument("--unzip", action="store_true")
    a = ap.parse_args()
    cmd_release(a) if a.cmd == "release" else cmd_url(a)


if __name__ == "__main__":
    main()
