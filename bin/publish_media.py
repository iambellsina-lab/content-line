#!/usr/bin/env python3
"""publish_media.py: give local images (or short videos) a public web address.

Scheduling tools such as Metricool take media as a public URL, not as a file on your
computer. This script puts your files into a GitHub repository you own and prints the
public "raw" address of each one:

    https://raw.githubusercontent.com/<owner>/<repo>/<branch>/<folder>/<date>/<file>

What it does, in order:
  1. checks every file you named (exists, is an image or video, is under GitHub's size limit)
  2. copies them into <your local clone>/<folder>/<YYYY-MM-DD>/
  3. git add, git commit (only those files), git push
  4. prints one URL per file, on its own line, on standard output

It is safe to run twice. A file that is already there and unchanged is skipped, and "nothing
to commit" is not an error: the URLs are printed anyway.

Usage:
    python3 bin/publish_media.py out/carousel-01.png out/carousel-02.png
    python3 bin/publish_media.py out/*.png --dry-run     # show the URLs, change nothing
    python3 bin/publish_media.py out/clip.mp4 --no-push  # copy and commit, do not push
    python3 bin/publish_media.py out/*.png --json        # machine-readable result

On Windows write `python` for `python3`.

WHERE THE REPOSITORY IS NAMED (nothing is built into the script). Each setting is looked for in
this order: command-line flag, environment variable, config file, then the clone's own git
settings.

    setting        flag          environment variable            config file key
    local clone    --local       CONTENT_LINE_MEDIA_LOCAL        local_clone
    owner          --owner       CONTENT_LINE_MEDIA_OWNER        owner
    repo name      --repo        CONTENT_LINE_MEDIA_REPO         repo     ("owner/repo" also works)
    branch         --branch      CONTENT_LINE_MEDIA_BRANCH       branch   (default: the clone's branch)
    folder         --folder      CONTENT_LINE_MEDIA_FOLDER       folder   (default: media)

Owner, repo and branch can be left out when the clone already points at GitHub: they are read
from `git remote get-url origin` and the clone's current branch.

The config file is JSON. It is found at --config, then $CONTENT_LINE_MEDIA_CONFIG, then
./media-repo.json, then media-repo.json in the kit folder. See specs/media-repo.example.json.

ONE-TIME SETUP (yours, not this script's):
  - create the repository on GitHub and make it PUBLIC. A private repository gives addresses
    that a scheduling tool cannot open.
  - clone it onto this computer:  git clone https://github.com/<owner>/<repo>.git
  - be signed in to GitHub for git on this computer (GitHub Desktop, `gh auth login`, or a
    saved credential), because this script never asks for or stores a password.

ANYTHING YOU PUT IN A PUBLIC REPOSITORY IS PUBLIC. Publish only what you are ready for the
world to see.
"""
from __future__ import annotations

import argparse
import datetime
import filecmp
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path
from urllib.parse import quote

KIT_ROOT = Path(__file__).resolve().parent.parent
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov", ".webm"}
WARN_BYTES = 50 * 1000 * 1000       # GitHub warns above 50 MB
MAX_BYTES = 100 * 1000 * 1000       # GitHub refuses a pushed file above 100 MB
DEFAULT_FOLDER = "media"
NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors="replace")        # type: ignore[attr-defined]
    except Exception:                            # noqa: BLE001
        pass


class PublishError(Exception):
    """A problem the user can fix. The message says how."""


def say(msg: str) -> None:
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# Pure helpers: no git, no network, no disk writes. These are what the tests call.
# ---------------------------------------------------------------------------


def parse_remote_url(url: str) -> tuple[str, str] | None:
    """(owner, repo) from a GitHub remote address, or None if it is not one."""
    url = url.strip()
    m = (re.match(r"^https?://(?:[^@/]+@)?github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", url)
         or re.match(r"^(?:ssh://)?git@github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", url))
    return (m.group(1), m.group(2)) if m else None


def safe_name(filename: str) -> str:
    """A file name that is safe in a URL: letters, digits, dot, dash, underscore."""
    p = Path(unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode("ascii"))
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", p.stem).strip("-.") or "file"
    return stem + p.suffix.lower()


def clean_folder(folder: str) -> str:
    parts = [x for x in re.split(r"[\\/]+", folder.strip()) if x]
    if any(x in (".", "..") for x in parts) or not all(NAME_RE.match(x) for x in parts):
        raise PublishError(f'the folder name "{folder}" may only hold letters, digits, dot, dash and '
                           'underscore, with / between levels, and no "..".')
    return "/".join(parts)


def dest_path(folder: str, date: str, filename: str) -> str:
    """Path inside the repository, always with forward slashes."""
    parts = [clean_folder(folder)] if clean_folder(folder) else []
    return "/".join(parts + [date, safe_name(filename)])


def raw_url(owner: str, repo: str, branch: str, rel_path: str) -> str:
    return "https://raw.githubusercontent.com/%s/%s/%s/%s" % (
        owner, repo, quote(branch, safe="/"), quote(rel_path, safe="/"))


def check_date(value: str) -> str:
    try:
        datetime.datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise PublishError(f'the date "{value}" must look like 2026-10-01 (year-month-day).')
    return value


def check_name(label: str, value: str) -> str:
    if not value or not NAME_RE.match(value):
        raise PublishError(f'the {label} "{value}" is not valid. Use only letters, digits, dot, dash and underscore.')
    return value


def load_config(config_arg: str | None) -> tuple[dict, str]:
    """(settings, where they came from). Missing file is fine unless it was named on purpose."""
    candidates = []
    if config_arg:
        candidates.append((Path(config_arg), True))
    if os.environ.get("CONTENT_LINE_MEDIA_CONFIG"):
        candidates.append((Path(os.environ["CONTENT_LINE_MEDIA_CONFIG"]), True))
    candidates += [(Path.cwd() / "media-repo.json", False), (KIT_ROOT / "media-repo.json", False)]
    for path, must in candidates:
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError as exc:
                raise PublishError(f"{path} is not valid JSON (line {exc.lineno}, column {exc.colno}: {exc.msg}).")
            if not isinstance(data, dict):
                raise PublishError(f"{path} must be a JSON object, a block that starts with {{ and ends with }}.")
            return {k: v for k, v in data.items() if not k.startswith("_")}, str(path)
        if must:
            raise PublishError(f"config file not found: {path}")
    return {}, ""


def pick(flag, env_name: str, config: dict, key: str):
    """flag, then environment variable, then config file."""
    if flag:
        return flag
    if os.environ.get(env_name):
        return os.environ[env_name]
    return config.get(key) or None


def split_owner_repo(owner: str | None, repo: str | None) -> tuple[str | None, str | None]:
    if repo and "/" in repo:
        o, r = repo.split("/", 1)
        return (owner or o), r.removesuffix(".git")
    return owner, (repo.removesuffix(".git") if repo else repo)


def validate_files(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for raw in paths:
        p = Path(raw).expanduser()
        if not p.is_file():
            raise PublishError(f"not a file: {raw}")
        if p.suffix.lower() not in ALLOWED_EXT:
            raise PublishError(f"{raw} is a {p.suffix or 'file with no extension'}. This script publishes "
                               + ", ".join(sorted(ALLOWED_EXT)) + " only.")
        size = p.stat().st_size
        if size > MAX_BYTES:
            raise PublishError(f"{raw} is {size / 1e6:.0f} MB. GitHub refuses files over 100 MB. "
                               "Make it shorter or smaller first.")
        if size > WARN_BYTES:
            say(f"warning: {raw} is {size / 1e6:.0f} MB. GitHub warns above 50 MB, and a scheduler may be slow to fetch it.")
        out.append(p)
    return out


def file_digest(p: Path) -> str:
    h = hashlib.sha1()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def plan_items(files: list[Path], folder: str, date: str, owner: str, repo: str, branch: str) -> list[dict]:
    """Decide each file's path and URL. Pure. Two different files that would get the same name
    in one batch are told apart by a short hash; the same file named twice is listed once."""
    items: list[dict] = []
    seen: dict[str, str] = {}               # rel path -> digest of the file that claimed it
    for p in files:
        digest = file_digest(p)
        rel = dest_path(folder, date, p.name)
        if rel in seen:
            if seen[rel] == digest:
                continue                     # exactly the same file listed twice
            stem, ext = os.path.splitext(rel)
            rel = f"{stem}-{digest[:8]}{ext}"
        seen[rel] = digest
        items.append({"source": str(p), "path": rel, "url": raw_url(owner, repo, branch, rel)})
    return items


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------


def git(clone: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    exe = shutil.which("git")
    if not exe:
        raise PublishError("git is not installed. macOS: xcode-select --install   Windows: winget install Git.Git   "
                           "Linux: sudo apt install git. Then open a NEW terminal window.")
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")      # never sit waiting for a password nobody can see
    res = subprocess.run([exe, "-C", str(clone), *args], capture_output=True, text=True, env=env)
    if check and res.returncode != 0:
        raise PublishError(f"git {' '.join(args[:2])} failed:\n  " + (res.stderr or res.stdout).strip().replace("\n", "\n  "))
    return res


def inspect_clone(clone: Path, remote: str) -> tuple[str | None, str | None, str]:
    """(owner, repo, current branch) read from the clone. Raises if it is not a git folder."""
    if not clone.is_dir():
        raise PublishError(f"the local clone folder does not exist: {clone}\n"
                           "  Make it first with:  git clone https://github.com/<owner>/<repo>.git " + str(clone))
    probe = git(clone, "rev-parse", "--is-inside-work-tree", check=False)
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        raise PublishError(f"{clone} is not a git repository (no .git folder inside it).\n"
                           "  Point --local at the folder you got from: git clone https://github.com/<owner>/<repo>.git")
    branch = git(clone, "rev-parse", "--abbrev-ref", "HEAD", check=False).stdout.strip()
    if not branch or branch == "HEAD":
        branch = git(clone, "symbolic-ref", "--short", "HEAD", check=False).stdout.strip()
    url = git(clone, "remote", "get-url", remote, check=False).stdout.strip()
    parsed = parse_remote_url(url) if url else None
    return (parsed[0] if parsed else None), (parsed[1] if parsed else None), branch


def publish(items: list[dict], clone: Path, date: str, remote: str, branch: str,
            push: bool, message: str | None) -> dict:
    """Copy, commit and (unless told not to) push. Returns counts. Raises PublishError."""
    new = updated = same = 0
    rels = []
    for it in items:
        dest = clone / Path(*it["path"].split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            if filecmp.cmp(it["source"], dest, shallow=False):
                it["status"] = "unchanged"
                same += 1
            else:
                shutil.copy2(it["source"], dest)
                it["status"] = "updated"
                updated += 1
        else:
            shutil.copy2(it["source"], dest)
            it["status"] = "new"
            new += 1
        rels.append(it["path"])

    git(clone, "add", "--", *rels)
    staged = git(clone, "diff", "--cached", "--quiet", "--", *rels, check=False)
    committed = False
    if staged.returncode == 1:
        n_changed = new + updated
        msg = message or f"Add media {date} ({n_changed} file{'s' if n_changed != 1 else ''})"
        res = git(clone, "commit", "-m", msg, "--", *rels, check=False)
        if res.returncode != 0:
            text = (res.stderr or res.stdout)
            if "tell me who you are" in text or "user.name" in text or "user.email" in text:
                raise PublishError("git does not know who you are yet. Run these two lines once, with your own "
                                   'details, then run this again:\n  git config --global user.name "Your Name"\n'
                                   '  git config --global user.email "you@example.com"')
            raise PublishError("git commit failed:\n  " + text.strip().replace("\n", "\n  "))
        committed = True
    elif staged.returncode != 0:
        raise PublishError("git could not compare the files:\n  " + (staged.stderr or staged.stdout).strip())

    pushed = False
    if push:
        print(f"  these files become PUBLIC and permanent at {remote}", flush=True)
        print("  anyone with the link can view them. use --no-push to stop here.", flush=True)
        if git(clone, "remote", "get-url", remote, check=False).returncode != 0:
            raise PublishError(f'the clone has no remote called "{remote}", so there is nowhere to push.\n'
                               "  If you made this folder with git init, add one: "
                               "git remote add origin https://github.com/<owner>/<repo>.git")
        res = git(clone, "push", remote, branch, check=False)
        if res.returncode != 0:
            text = (res.stderr or res.stdout).strip()
            hint = ""
            if "rejected" in text or "non-fast-forward" in text or "fetch first" in text:
                hint = "\n  The repository has newer changes. Run  git pull --rebase  in the clone, then run this again."
            elif "could not read Username" in text or "Authentication" in text or "denied" in text or "403" in text:
                hint = ("\n  git is not signed in to GitHub on this computer. Sign in with GitHub Desktop or "
                        "`gh auth login`, then run this again. Your files are already committed, so nothing is lost.")
            raise PublishError("git push failed:\n  " + text.replace("\n", "\n  ") + hint)
        pushed = True
    return {"new": new, "updated": updated, "unchanged": same, "committed": committed, "pushed": pushed}


def verify_urls(items: list[dict]) -> int:
    """Ask the web whether each address answers. Needs the network. Returns how many did not."""
    import time
    import urllib.error
    import urllib.request
    bad = 0
    for it in items:
        ok = False
        for attempt in range(4):                      # a fresh push can take a few seconds to appear
            try:
                req = urllib.request.Request(it["url"], method="HEAD")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    ok = resp.status == 200
            except (urllib.error.URLError, OSError):
                ok = False
            if ok:
                break
            time.sleep(3)
        say(("  live   " if ok else "  NOT LIVE   ") + it["url"])
        bad += 0 if ok else 1
    return bad


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Copy local images or videos into your GitHub media repository and print their public URLs.",
        epilog="Settings can come from flags, environment variables or a config file. Run with --help-config "
               "or read the top of this file.")
    ap.add_argument("files", nargs="*", help="image or video files to publish")
    ap.add_argument("--local", help="folder of your local clone of the media repository")
    ap.add_argument("--owner", help="GitHub user or organisation that owns the repository")
    ap.add_argument("--repo", help="repository name (or owner/repo)")
    ap.add_argument("--branch", help="branch to push (default: the clone's current branch)")
    ap.add_argument("--folder", help=f"folder inside the repository (default: {DEFAULT_FOLDER})")
    ap.add_argument("--remote", default="origin", help="git remote name (default: origin)")
    ap.add_argument("--date", help="dated sub-folder name, YYYY-MM-DD (default: today)")
    ap.add_argument("--message", help="commit message (default: Add media <date> (<n> files))")
    ap.add_argument("--config", help="path to a JSON config file")
    ap.add_argument("--dry-run", action="store_true", help="print the URLs that would be used, change nothing")
    ap.add_argument("--no-push", action="store_true", help="copy and commit, but do not push")
    ap.add_argument("--verify", action="store_true", help="after pushing, check that each URL answers (needs internet)")
    ap.add_argument("--json", action="store_true", help="print the result as JSON instead of one URL per line")
    return ap


def run(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    if not args.files:
        raise PublishError("name at least one file, for example: python3 bin/publish_media.py out/carousel-01.png")

    config, config_src = load_config(args.config)
    local = pick(args.local, "CONTENT_LINE_MEDIA_LOCAL", config, "local_clone")
    repo = pick(args.repo, "CONTENT_LINE_MEDIA_REPO", config, "repo")
    # an owner written inside "owner/repo" beats the config file's owner, never a flag or env owner
    owner = pick(args.owner, "CONTENT_LINE_MEDIA_OWNER", {}, "owner") or (
        None if (repo and "/" in repo) else config.get("owner"))
    branch = pick(args.branch, "CONTENT_LINE_MEDIA_BRANCH", config, "branch")
    folder = pick(args.folder, "CONTENT_LINE_MEDIA_FOLDER", config, "folder") or DEFAULT_FOLDER
    owner, repo = split_owner_repo(owner, repo)
    date = check_date(args.date or datetime.date.today().isoformat())
    files = validate_files(args.files)

    clone = Path(local).expanduser() if local else None
    if clone is not None and (clone.is_dir() or not args.dry_run):
        g_owner, g_repo, g_branch = inspect_clone(clone, args.remote)
        if branch and branch != g_branch and not args.dry_run:
            raise PublishError(f'the clone is on branch "{g_branch}" but the settings say "{branch}". '
                               f"Run  git -C {clone} checkout {branch}  first, or remove the branch setting.")
        owner, repo, branch = owner or g_owner, repo or g_repo, branch or g_branch

    missing = [n for n, v in (("owner", owner), ("repo", repo), ("branch", branch)) if not v]
    if clone is None and not args.dry_run:
        raise PublishError(
            "no local clone is set, so there is nowhere to copy the files.\n"
            "  Give the folder of your clone with --local /path/to/clone, or set CONTENT_LINE_MEDIA_LOCAL,\n"
            "  or put \"local_clone\" in media-repo.json (see specs/media-repo.example.json).")
    if missing:
        raise PublishError("cannot build the public address: " + ", ".join(missing) + " not set.\n"
                           "  Set them with --owner/--repo/--branch, the CONTENT_LINE_MEDIA_* environment variables, "
                           "or media-repo.json. If you pass --local to a clone whose remote is on GitHub, they are read from it.")
    check_name("owner", owner)
    check_name("repo", repo)
    check_name("branch", branch.replace("/", "-"))

    items = plan_items(files, folder, date, owner, repo, branch)

    if args.dry_run:
        say(f"dry run: nothing copied, committed or pushed. Settings from: {config_src or 'flags and environment'}")
        for it in items:
            it["status"] = "would publish"
    else:
        assert clone is not None
        summary = publish(items, clone, date, args.remote, branch, not args.no_push, args.message)
        if not summary["committed"]:
            say("Nothing new to commit: every file is already in the repository unchanged.")
        say("%d new, %d updated, %d unchanged. %s" % (
            summary["new"], summary["updated"], summary["unchanged"],
            "Pushed." if summary["pushed"] else "NOT pushed (--no-push): the addresses below will not work until you push."))
        if args.verify and summary["pushed"]:
            if verify_urls(items):
                say("Some addresses did not answer. If the repository is private, make it public. "
                    "Otherwise wait a minute and try --verify again.")

    if args.json:
        print(json.dumps(items, indent=2))
    else:
        for it in items:
            print(it["url"])
    return 0


def main() -> None:
    try:
        sys.exit(run(sys.argv[1:]))
    except PublishError as exc:
        say(f"publish_media: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
