#!/usr/bin/env python3
"""shelf_index.py: a folder of silent clips becomes a shelf you can build a reel from.

    python3 bin/shelf_index.py footage/cruise --out specs/shelf-cruise.json
    python3 bin/shelf_index.py footage/cruise --out specs/shelf-cruise.json --frames 4
    python3 bin/shelf_index.py footage/cruise --out specs/shelf-cruise.json --recursive
    python3 bin/shelf_index.py footage/cruise --out specs/shelf-cruise.json --print

WHY THIS EXISTS. Every other entry point in this kit starts from a transcript of
somebody talking. plan_clips.py, cards_from_srt.py, pick_pulls.py, run_line.py: all
of them read words off a tape. Hand the kit a folder of boat footage with nobody
speaking in it and there is no door to walk in through. This is that door. It reads
a folder of clips and writes down what is measurably true about each one, leaving one
empty slot per clip for the thing a machine cannot measure.

WHAT IT MEASURES, with ffprobe, and every one of these is a fact off the file:
    duration, width, height, the rotation tag, the display shape after rotation,
    orientation (vertical, horizontal or square), frame rate, whether there is an
    audio stream at all, file size.

WHAT IT DOES NOT DO, and this is the important half. IT DOES NOT LABEL THE CLIPS.
It writes "label": null and "keywords": [] and stops. Arithmetic cannot tell a
sunset from a railing, and this file does not pretend otherwise: there is no vision
call in here, no filename guessing, no keyword scraped off a path. A session opens
the extracted frames, looks at them, and fills the slots in. That costs attention,
and the report at the end says exactly how much is outstanding.

WHAT IT WRITES
    the shelf JSON at --out
    a frames folder beside it, N small JPEGs per clip, default 3, evenly spaced

    The frames exist so labelling is cheap: three 480-wide stills are a fraction of
    the tokens a video is, and they are what a session actually looks at.

RE-RUNNING IS SAFE AND THIS IS DELIBERATE. Point it at the same folder again and
every label already written is carried across, matched on path, size and duration.
A re-index after dropping four new clips in keeps the forty you labelled last week.
Only --relabel throws labels away, and it says how many it is about to drop.

Standard library plus ffmpeg and ffprobe. No Pillow, no network, no account.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".mpg", ".mpeg", ".3gp"}

# Small enough that three of them cost little to look at, large enough to tell a
# railing from a horizon.
FRAME_WIDTH = 480


def who() -> str:
    return Path(sys.argv[0]).stem or "shelf_index"


def die(msg: str) -> None:
    print("%s: %s" % (who(), msg), file=sys.stderr)
    sys.exit(1)


def need(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        die("%s is not on your PATH. On a Mac: brew install ffmpeg" % tool)
    return path


def probe(ffprobe: str, path: Path) -> dict:
    """Everything ffprobe will tell us about one file, or an error string."""
    cmd = [ffprobe, "-v", "error", "-print_format", "json",
           "-show_format", "-show_streams", str(path)]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return {"_error": "ffprobe timed out after 120s"}
    if res.returncode != 0:
        first = (res.stderr or "").strip().splitlines()
        return {"_error": first[0] if first else "ffprobe exited %d" % res.returncode}
    try:
        return json.loads(res.stdout or "{}")
    except ValueError as exc:
        return {"_error": "ffprobe output was not JSON: %s" % exc}


def rotation_of(stream: dict) -> int:
    """The rotation a player will apply, as a whole number of degrees.

    Two places carry it and which one depends on the camera and the ffmpeg build:
    the old tags.rotate, and side_data_list on newer files. Reading only one is how
    a phone clip gets called horizontal when it plays vertical.
    """
    tags = stream.get("tags") or {}
    for key in ("rotate", "Rotate"):
        if key in tags:
            try:
                return int(float(tags[key])) % 360
            except (TypeError, ValueError):
                pass
    for side in stream.get("side_data_list") or []:
        if "rotation" in side:
            try:
                return int(round(float(side["rotation"]))) % 360
            except (TypeError, ValueError):
                pass
    return 0


def fps_of(stream: dict) -> float | None:
    for key in ("avg_frame_rate", "r_frame_rate"):
        val = str(stream.get(key) or "")
        if "/" in val:
            num, _, den = val.partition("/")
            try:
                n, d = float(num), float(den)
            except ValueError:
                continue
            if d:
                return round(n / d, 3)
    return None


def measure(ffprobe: str, path: Path) -> dict:
    """One clip, measured. Never labelled."""
    info = probe(ffprobe, path)
    out: dict = {
        "path": None,          # filled in by the caller, relative to the shelf
        "name": path.name,
        "bytes": path.stat().st_size,
    }
    if "_error" in info:
        out["problem"] = info["_error"]
        return out

    video = None
    has_audio = False
    for stream in info.get("streams") or []:
        kind = stream.get("codec_type")
        if kind == "video" and video is None:
            video = stream
        elif kind == "audio":
            has_audio = True
    if video is None:
        out["problem"] = "no video stream in the file"
        return out

    dur = None
    for src in (video.get("duration"), (info.get("format") or {}).get("duration")):
        try:
            dur = round(float(src), 3)
            break
        except (TypeError, ValueError):
            continue

    w = int(video.get("width") or 0)
    h = int(video.get("height") or 0)
    rot = rotation_of(video)
    dw, dh = (h, w) if rot in (90, 270) else (w, h)

    if dw and dh:
        ratio = dw / float(dh)
        shape = "vertical" if ratio < 0.95 else ("horizontal" if ratio > 1.05 else "square")
    else:
        ratio, shape = None, "unknown"

    out.update({
        "duration_s": dur,
        "width": dw,
        "height": dh,
        "stored_width": w,
        "stored_height": h,
        "rotation": rot,
        "aspect": round(ratio, 4) if ratio else None,
        "orientation": shape,
        "fps": fps_of(video),
        "codec": video.get("codec_name"),
        "has_audio": has_audio,
    })
    if dur is None:
        out["problem"] = "ffprobe gave no duration"
    elif dur < 0.4:
        out["problem"] = "only %.2fs long, too short to hold a beat" % dur
    return out


def grab_frames(ffmpeg: str, clip: Path, dest: Path, stem: str, n: int,
                duration: float | None, force: bool) -> list[str]:
    """N evenly spaced stills, small. Returns the paths written, relative to dest."""
    if not duration or duration <= 0 or n <= 0:
        return []
    dest.mkdir(parents=True, exist_ok=True)
    made = []
    for i in range(n):
        # Evenly spaced INSIDE the clip rather than from zero: the first frame of a
        # handheld clip is usually the hand still moving onto the subject.
        at = duration * (i + 1) / (n + 1.0)
        name = "%s-%02d.jpg" % (stem, i + 1)
        target = dest / name
        if target.exists() and not force:
            made.append(name)
            continue
        cmd = [ffmpeg, "-nostdin", "-v", "error", "-y",
               "-ss", "%.3f" % at, "-i", str(clip),
               "-frames:v", "1",
               "-vf", "scale=%d:-2:flags=bicubic" % FRAME_WIDTH,
               "-q:v", "4", str(target)]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            continue
        if res.returncode == 0 and target.exists() and target.stat().st_size > 0:
            made.append(name)
    return made


def safe_stem(path: Path, used: set) -> str:
    base = "".join(c if (c.isalnum() or c in "-_") else "-" for c in path.stem).strip("-")
    base = base.lower()[:48] or "clip"
    stem, n = base, 2
    while stem in used:
        stem = "%s-%d" % (base, n)
        n += 1
    used.add(stem)
    return stem


LABEL_KEYS = ("label", "keywords", "usable", "focus_x", "focus_y", "note")


def carry_labels(old_path: Path, clips: list[dict], relabel: bool) -> tuple[int, int]:
    """Bring labels across from an earlier shelf. Matched on path, size and duration.

    Matching on the path alone would carry a label onto a different clip that had
    been dropped in under the same name, which is the one way this could put the
    wrong words against a picture.
    """
    if relabel or not old_path.exists():
        return 0, 0
    try:
        with open(old_path, "r", encoding="utf-8") as fh:
            old = json.load(fh)
    except (OSError, ValueError):
        return 0, 0
    index = {}
    for c in old.get("clips") or []:
        key = (c.get("path"), c.get("bytes"), c.get("duration_s"))
        index[key] = c
    carried = labelled = 0
    for clip in clips:
        prev = index.get((clip.get("path"), clip.get("bytes"), clip.get("duration_s")))
        if not prev:
            continue
        for key in LABEL_KEYS:
            if key in prev and prev[key] not in (None, [], ""):
                clip[key] = prev[key]
        carried += 1
        if clip.get("label"):
            labelled += 1
    return carried, labelled


HELP = {
    "_what_this_is":
        "A SHELF: every silent clip in one folder, measured, with an empty slot per clip "
        "for what is actually in it. bin/broll_reel.py reads this file and a cut list and "
        "writes the b-roll layers for a reel. Re-run bin/shelf_index.py on the same folder "
        "any time; labels already written are carried across.",
    "_the_part_that_needs_eyes":
        "label, keywords and usable are NOT measured and are not guessed. Open the frames "
        "listed under each clip, look at them, and fill them in. label is a short plain "
        "description of what is on screen (\"sunrise over the water from the top deck\"). "
        "keywords are the words a script might use when this picture would fit (\"morning\", "
        "\"ocean\", \"quiet\", \"start\"); broll_reel.py matches on those, so they are what "
        "decides where a clip lands. usable false keeps a clip on the shelf and out of every "
        "reel, which is what a blurry take wants. focus_x and focus_y choose what a cover "
        "crop keeps when the clip is the wrong shape for a vertical frame; 0.5 is centre.",
    "_orientation":
        "A horizontal clip in a 9:16 frame loses most of its width to the crop. broll_reel.py "
        "warns per clip rather than refusing, because a wide shot of a horizon crops fine and "
        "a wide shot of two people talking does not, and only a person looking at it knows "
        "which it is.",
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Index a folder of clips into a shelf for bin/broll_reel.py.")
    ap.add_argument("folder", help="a folder of clips")
    ap.add_argument("--out", help="where to write the shelf JSON "
                                  "(default: <folder>/shelf.json)")
    ap.add_argument("--frames", type=int, default=3,
                    help="stills to pull per clip, for labelling (default 3, 0 for none)")
    ap.add_argument("--frames-dir", help="where the stills go (default: frames/ beside --out)")
    ap.add_argument("--recursive", action="store_true", help="walk subfolders too")
    ap.add_argument("--relabel", action="store_true",
                    help="throw away the labels in the existing shelf and start over")
    ap.add_argument("--force-frames", action="store_true",
                    help="re-extract stills that are already there")
    ap.add_argument("--print", dest="to_stdout", action="store_true",
                    help="print the shelf to stdout and write nothing")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    args = ap.parse_args(argv)

    folder = Path(args.folder).expanduser()
    if not folder.is_dir():
        die("%s is not a folder" % folder)

    ffprobe = need("ffprobe")
    ffmpeg = need("ffmpeg")

    out_path = Path(args.out).expanduser() if args.out else folder / "shelf.json"
    frames_dir = (Path(args.frames_dir).expanduser() if args.frames_dir
                  else out_path.parent / "frames")

    walker = folder.rglob("*") if args.recursive else folder.glob("*")
    files = sorted(p for p in walker
                   if p.is_file() and p.suffix.lower() in VIDEO_EXT and not p.name.startswith("."))
    if not files:
        die("no video files in %s (looked for %s)"
            % (folder, " ".join(sorted(VIDEO_EXT))))

    clips, stems = [], set()
    for path in files:
        clip = measure(ffprobe, path)
        # Relative to the shelf file, so the shelf and the frames move together.
        try:
            clip["path"] = os.path.relpath(path, out_path.parent)
        except ValueError:
            clip["path"] = str(path)
        stem = safe_stem(path, stems)
        clip["id"] = stem
        for key in LABEL_KEYS:
            clip.setdefault(key, [] if key == "keywords" else None)
        if not args.to_stdout and not clip.get("problem"):
            names = grab_frames(ffmpeg, path, frames_dir, stem, args.frames,
                                clip.get("duration_s"), args.force_frames)
            if names:
                try:
                    rel = os.path.relpath(frames_dir, out_path.parent)
                except ValueError:
                    rel = str(frames_dir)
                clip["frames"] = [os.path.join(rel, n) for n in names]
        clips.append(clip)

    carried, kept_labels = carry_labels(out_path, clips, args.relabel)

    shelf = dict(HELP)
    shelf["folder"] = str(folder)
    shelf["clips"] = clips

    broken = [c for c in clips if c.get("problem")]
    usable = [c for c in clips if not c.get("problem") and c.get("usable") is not False]
    labelled = [c for c in usable if c.get("label")]
    unlabelled = [c for c in usable if not c.get("label")]
    horizontal = [c for c in usable if c.get("orientation") == "horizontal"]
    total_s = sum(c.get("duration_s") or 0.0 for c in usable)

    text = json.dumps(shelf, indent=2, ensure_ascii=False)
    if args.to_stdout:
        print(text)
    else:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")

    report = {
        "shelf": None if args.to_stdout else str(out_path),
        "clips": len(clips),
        "usable": len(usable),
        "labelled": len(labelled),
        "unlabelled": len(unlabelled),
        "unreadable": len(broken),
        "horizontal": len(horizontal),
        "seconds_on_the_shelf": round(total_s, 2),
        "labels_carried_over": kept_labels,
        "frames_per_clip": args.frames,
    }
    if args.json:
        print(json.dumps(report, indent=2))
        return 1 if broken and not usable else 0

    print("")
    print("shelf_index  %s" % folder)
    print("  %d clip(s), %.1fs on the shelf, %d usable" % (len(clips), total_s, len(usable)))
    if carried:
        print("  %d clip(s) matched the existing shelf, %d label(s) carried over"
              % (carried, kept_labels))
    if horizontal:
        print("  %d horizontal: a 9:16 frame crops the width off these" % len(horizontal))
        for c in horizontal[:4]:
            print("      %s  %dx%d" % (c["name"], c.get("width") or 0, c.get("height") or 0))
    for c in broken:
        print("  UNREADABLE  %s: %s" % (c["name"], c["problem"]))
    print("")
    if unlabelled:
        print("  %d clip(s) have no label yet, and a label is what decides where a clip lands."
              % len(unlabelled))
        if args.frames:
            print("  The frames to look at are in %s" % frames_dir)
        print("  Fill in label and keywords for each one, then run bin/broll_reel.py.")
    else:
        print("  Every usable clip is labelled. bin/broll_reel.py can build a reel from this.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
