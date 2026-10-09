#!/usr/bin/env python3
"""grade.py: give footage or a still a deliberate look, by name.

    python3 bin/grade.py in.mp4 --look warm-desert
    python3 bin/grade.py in.mp4 --look mono --out review/graded.mp4
    python3 bin/grade.py frame.png --look bleached --strength 0.6
    python3 bin/grade.py in.mp4 --look cool-night --check      # one graded still, fast
    python3 bin/grade.py --list

Why this exists: a grade is a forty character ffmpeg chain nobody can read or remember, and
getting one wrong is not obvious by eye. On 2026-10-01 three attempts at a film look came out
magenta and it was only caught by measuring: green was 32 points below red and blue. So this
tool holds the chains by name AND measures what it produced.

THE CAST CHECK, which is the point.
After grading, one frame is sampled and the average red, green and blue are compared. A look is
allowed its own intended cast (warm-desert is meant to be warm). What is NOT allowed is drifting
further than the look says it should. If it does, the tool says so and names the channel. A look
that silently turns skin magenta is the failure this prevents.

HALATION is deliberately absent. It is the glow around a highlight that real film has and
digital does not, and it is the single biggest "this looks like film" move. Every attempt here
using ffmpeg's blend=screen pulled green down hard across the whole frame, including on a
masked, thresholded copy. Not understood yet, so not shipped. Do not add it back without
running --check and reading the numbers.

Needs ffmpeg with the curves, eq, noise, vignette and hue filters, which is any normal build.
No Pillow, no network, no cost.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
STILL_EXT = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}

# Each look: the filter chain, and the cast it is ALLOWED to have, as (r-g, b-g) in 0..255
# averages with a tolerance. "intent" is what it is for, in plain words.
LOOKS: dict[str, dict] = {
    "neutral-film": {
        "intent": "The default. Lifted blacks, a gentle S, a little desaturation, fine grain. "
                  "Makes phone footage stop looking like phone footage without announcing itself.",
        "chain": ("curves=r='0/0.038 0.25/0.24 0.5/0.50 0.75/0.775 1/0.965':"
                  "g='0/0.038 0.25/0.24 0.5/0.50 0.75/0.775 1/0.965':"
                  "b='0/0.055 0.25/0.25 0.5/0.495 0.75/0.765 1/0.945',"
                  "eq=saturation=0.88:contrast=1.05:gamma=1.01,"
                  "noise=alls=6:allf=t+u,vignette=PI/7"),
        "cast": (0, -4), "tol": 9,
    },
    "warm-desert": {
        "intent": "Terracotta and late sun. Adobe, clay, stone, plants. The dream-home palette.",
        "chain": ("curves=r='0/0.045 0.25/0.26 0.5/0.52 1/0.98':"
                  "g='0/0.04 0.25/0.245 0.5/0.50 1/0.955':"
                  "b='0/0.05 0.25/0.23 0.5/0.47 1/0.91',"
                  "eq=saturation=0.95:contrast=1.04:gamma=1.02,"
                  "noise=alls=6:allf=t+u,vignette=PI/7"),
        "cast": (6, -10), "tol": 10,
    },
    "cool-night": {
        "intent": "Blue hour. Cold shadows, held highlights. For anything shot after dark or "
                  "anything that should feel like it was.",
        "chain": ("curves=r='0/0.03 0.25/0.22 0.5/0.48 1/0.94':"
                  "g='0/0.04 0.25/0.235 0.5/0.495 1/0.96':"
                  "b='0/0.075 0.25/0.28 0.5/0.535 1/0.99',"
                  "eq=saturation=0.84:contrast=1.08:gamma=0.99,"
                  "noise=alls=7:allf=t+u,vignette=PI/6"),
        "cast": (-6, 8), "tol": 10,
    },
    "bleached": {
        "intent": "Washed out, high key, blacks well off the floor. Editorial and slightly 1970s. "
                  "Suits daylight and pale rooms. Falls apart on anything already dark.",
        "chain": ("curves=r='0/0.10 0.25/0.33 0.5/0.57 1/0.99':"
                  "g='0/0.10 0.25/0.33 0.5/0.565 1/0.985':"
                  "b='0/0.105 0.25/0.325 0.5/0.555 1/0.97',"
                  "eq=saturation=0.74:contrast=0.94:gamma=1.06,"
                  "noise=alls=8:allf=t+u"),
        "cast": (1, -3), "tol": 9,
    },
    "mono": {
        "intent": "High contrast black and white with real grain. Hides bad colour entirely, "
                  "which is sometimes the honest answer.",
        "chain": ("hue=s=0,curves=r='0/0.02 0.25/0.19 0.5/0.50 0.75/0.82 1/0.99':"
                  "g='0/0.02 0.25/0.19 0.5/0.50 0.75/0.82 1/0.99':"
                  "b='0/0.02 0.25/0.19 0.5/0.50 0.75/0.82 1/0.99',"
                  "eq=contrast=1.12,noise=alls=10:allf=t+u,vignette=PI/6"),
        "cast": (0, 0), "tol": 4,
    },
}


def die(msg: str) -> None:
    print(f"grade: {msg}", file=sys.stderr)
    sys.exit(1)


def ffmpeg() -> str:
    f = shutil.which("ffmpeg")
    if not f:
        die("ffmpeg is not installed or not on PATH.\n"
            "  macOS: brew install ffmpeg   Windows: winget install Gyan.FFmpeg")
    return f  # type: ignore[return-value]


def scale_chain(chain: str, strength: float) -> str:
    """Blend the look toward no-op. 1.0 is the look as written, 0 is untouched.

    Only the numbers that are safe to move are moved: saturation and contrast toward 1,
    grain toward 0, and the curve control points toward the straight line y=x. Vignette and
    hue are left alone because they do not interpolate sensibly.
    """
    if strength >= 0.999:
        return chain
    s = max(0.0, min(1.0, strength))

    def lerp(v: float, target: float) -> float:
        return target + (v - target) * s

    def fix_curve(m: re.Match) -> str:
        pts = []
        for pair in m.group(2).split():
            a, b = pair.split("/")
            pts.append(f"{a}/{lerp(float(b), float(a)):.4f}")
        return f"{m.group(1)}='{' '.join(pts)}'"

    chain = re.sub(r"\b([rgb])='([^']+)'", fix_curve, chain)
    chain = re.sub(r"saturation=([\d.]+)", lambda m: f"saturation={lerp(float(m.group(1)), 1.0):.3f}", chain)
    chain = re.sub(r"contrast=([\d.]+)", lambda m: f"contrast={lerp(float(m.group(1)), 1.0):.3f}", chain)
    chain = re.sub(r"gamma=([\d.]+)", lambda m: f"gamma={lerp(float(m.group(1)), 1.0):.3f}", chain)
    chain = re.sub(r"alls=(\d+)", lambda m: f"alls={max(0, round(lerp(int(m.group(1)), 0)))}", chain)
    return chain


def sample_cast(path: Path, at: float = 1.0) -> tuple[int, int, int] | None:
    """Average R, G, B of one frame, read with ffmpeg alone so Pillow is not needed."""
    tmp = Path(tempfile.mkdtemp(prefix="grade-"))
    try:
        raw = tmp / "f.rawvideo"
        args = [ffmpeg(), "-v", "error"]
        if path.suffix.lower() in VIDEO_EXT:
            args += ["-ss", str(at)]
        args += ["-i", str(path), "-frames:v", "1", "-vf", "scale=64:64",
                 "-f", "rawvideo", "-pix_fmt", "rgb24", "-y", str(raw)]
        if subprocess.run(args, capture_output=True).returncode != 0 or not raw.exists():
            return None
        data = raw.read_bytes()
        if len(data) < 3:
            return None
        n = len(data) // 3
        return tuple(round(sum(data[i::3]) / n) for i in range(3))  # type: ignore[return-value]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_cast(before, after, look: dict, strength: float) -> tuple[bool, str]:
    """Did the grade drift further than the look says it should?"""
    if not before or not after:
        return True, "could not sample a frame, cast not checked"
    b_rg, b_bg = before[0] - before[1], before[2] - before[1]
    a_rg, a_bg = after[0] - after[1], after[2] - after[1]
    want_rg, want_bg = (c * strength for c in look["cast"])
    tol = look["tol"] + 4 * (1 - strength)
    drift_rg = abs((a_rg - b_rg) - want_rg)
    drift_bg = abs((a_bg - b_bg) - want_bg)
    detail = (f"before r-g {b_rg:+d} b-g {b_bg:+d} | after r-g {a_rg:+d} b-g {a_bg:+d} | "
              f"intended shift r-g {want_rg:+.0f} b-g {want_bg:+.0f} | tolerance {tol:.0f}")
    if drift_rg <= tol and drift_bg <= tol:
        return True, "cast as intended. " + detail
    off = []
    if drift_rg > tol:
        off.append(f"red against green is {drift_rg:.0f} off" +
                   ("  (too magenta)" if a_rg - b_rg > want_rg else "  (too green)"))
    if drift_bg > tol:
        off.append(f"blue against green is {drift_bg:.0f} off" +
                   ("  (too blue)" if a_bg - b_bg > want_bg else "  (too yellow)"))
    return False, "CAST DRIFTED: " + "; ".join(off) + ". " + detail


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Apply a named look to footage or a still, and check the result.")
    ap.add_argument("source", nargs="?", help="video or image to grade")
    ap.add_argument("--look", help="which look, see --list")
    ap.add_argument("--out", help="where to write (default: next to the source, -<look> appended)")
    ap.add_argument("--strength", type=float, default=1.0, help="0 to 1, how far toward the look (default 1)")
    ap.add_argument("--check", action="store_true", help="grade ONE still and report, change no video")
    ap.add_argument("--at", type=float, default=1.0, help="seconds into a video to sample for the check")
    ap.add_argument("--list", action="store_true", help="show the looks and what each is for")
    a = ap.parse_args(argv)

    if a.list or not a.source:
        print("looks:\n")
        for name, lk in LOOKS.items():
            print(f"  {name}\n      {lk['intent']}\n")
        if not a.source and not a.list:
            die("name a file to grade.")
        return 0

    src = Path(a.source).expanduser()
    if not src.is_file():
        die(f"not a file: {src}")
    if not a.look:
        die("say which look with --look, or run --list to see them.")
    if a.look not in LOOKS:
        die(f"no look called {a.look!r}. Run --list. Available: " + ", ".join(LOOKS))
    if not (0 <= a.strength <= 1):
        die("--strength is between 0 and 1")

    look = LOOKS[a.look]
    chain = scale_chain(look["chain"], a.strength)
    is_video = src.suffix.lower() in VIDEO_EXT
    if not is_video and src.suffix.lower() not in STILL_EXT:
        die(f"{src.suffix or 'that'} is not a video or image this tool handles.")

    before = sample_cast(src, a.at)

    if a.check:
        out = Path(tempfile.mkdtemp(prefix="grade-check-")) / f"{src.stem}-{a.look}.png"
        args = [ffmpeg(), "-v", "error"]
        if is_video:
            args += ["-ss", str(a.at)]
        args += ["-i", str(src), "-frames:v", "1", "-vf", chain, "-y", str(out)]
    else:
        default = src.with_name(f"{src.stem}-{a.look}{src.suffix}")
        out = Path(a.out).expanduser() if a.out else default
        out.parent.mkdir(parents=True, exist_ok=True)
        args = [ffmpeg(), "-v", "error", "-i", str(src), "-vf", chain]
        if is_video:
            args += ["-c:v", "libx264", "-profile:v", "high", "-preset", "medium",
                     "-b:v", "12M", "-maxrate", "15M", "-bufsize", "20M", "-pix_fmt", "yuv420p",
                     "-c:a", "copy", "-movflags", "+faststart"]
        args += ["-y", str(out)]

    res = subprocess.run(args, capture_output=True, text=True)
    if res.returncode != 0 or not out.exists():
        die("ffmpeg failed:\n  " + (res.stderr or res.stdout).strip()[:1200].replace("\n", "\n  "))

    after = sample_cast(out, a.at if is_video and not a.check else 0.0)
    ok, msg = check_cast(before, after, look, a.strength)

    print(f"{out}  {out.stat().st_size / 1_000_000:.2f} MB" + ("   (check only, one frame)" if a.check else ""))
    print(f"look: {a.look} at strength {a.strength}")
    print(("  ok   " if ok else "  WARN ") + msg)
    if not ok:
        print("  The look did not land where it says it should. Look at the frame before using it.\n"
              "  A grade that is wrong is not obvious by eye, which is exactly why this check exists.")
    return 0 if ok else 2


def main() -> None:
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
