#!/usr/bin/env python3
"""
caption_video.py: burn timed caption cards onto YOUR OWN footage.

make_clip.py puts text over a generated background. This puts the same text
over a real recording (a phone video, a podcast camera file, a long take) and
exports it as a finished 1080x1920 vertical clip.

Many ffmpeg builds cannot draw text (no drawtext, no subtitles filter, no libass,
no libfreetype). So text is drawn with Pillow by make_clip.render_card (imported,
not copied) into transparent PNGs, shifted to the caption position, and composited
by ffmpeg as timed overlays that cut in and cut out with no fade.

What it does, in order:
  1. optional trim (spec "trim": {"start", "end"}), so one long recording
     yields a short pull
  2. scale to fill 1080x1920 and centre crop, never letterbox
  3. overlay each card between its start and end, hard cut both ways
  4. loudness normalise to -14 LUFS, true peak -1.0 dBTP (two passes, because
     one pass of loudnorm lands several LU off on a short clip)
  5. export h264 High, yuv420p, 30fps, AAC 48kHz 192k, +faststart

Usage (from the kit folder; on Windows write `python` for `python3`):
    python3 bin/caption_video.py specs/my-clip.json
    python3 bin/caption_video.py specs/my-clip.json --brand specs/yourbrand.json
    python3 bin/caption_video.py specs/my-clip.json --check
    python3 bin/caption_video.py specs/my-clip.json --keep

Spec (JSON). Only "source", "out" and "cards" are required. Look keys (font,
text_color, accent, max_lines, font_size, caption_position, caption_nudge) come
from the brand file and may be overridden here.

{
  "brand": "example-brand.json",             # optional, same as --brand
  "source": "footage/take1.mov",             # next to this spec, or where you run from
  "out": "out/take1-pull.mp4",               # relative to where you run from
  "trim": {"start": 62.0, "end": 94.5},      # optional, seconds in the source
  "times": "source",                         # card times are source seconds
                                             # (default). "clip" means seconds
                                             # from the start of the trimmed pull.
  "caption_position": "lower",               # lower (default) | center | upper
  "caption_nudge": 0,                        # optional px, + moves down. Clamped
                                             # so type stays in the safe band.
  "focus_x": 0.5,                            # 0 = crop from left edge of a wide
  "focus_y": 0.5,                            # source, 1 = right edge. 0.5 = centre
  "font_size": 84,                           # optional exact size. Default is the
                                             # largest size every card fits at,
                                             # capped at "font_size_max" (96)
  "cards": [
    {"text": "I say yes", "start": 64.0, "end": 65.1},
    {"text": "to everything.", "start": 65.1, "end": 66.4, "accent": ["everything."]}
  ]
}

Caption position. All text stays inside the centre 1080x1080 square (y 420 to
1500). "lower" puts the bottom edge of the text at y=1420, which is 500px up
from the bottom edge, the usual rule for anything that sits low. A face usually
fills the upper middle of a vertical frame, so lower keeps type off it. "center"
matches make_clip. "upper" is for footage where the subject sits low.
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import kit_common as kc  # noqa: E402  (before PIL: it can re-run us inside the kit .venv)
import make_clip  # noqa: E402  (imported as a module so nothing is copied)
from PIL import Image  # noqa: E402
from make_clip import (  # noqa: E402
    AUDIO_BITRATE, FPS, H, LUFS, SAFE_BOTTOM, SAFE_SIDE, SAFE_TOP, TRUE_PEAK,
    VIDEO_BITRATE, W, Card, die, ffmpeg_bin, hex_rgb, pick_font, render_card,
    uniform_font,
)

LOWER_BOTTOM = H - 500      # bottom edge of text in "lower": 500px up from the bottom
ACTION_RAIL  = 200          # keep type this far in from each side: the like and share column
UPPER_TOP = SAFE_TOP + 40   # top edge of text in "upper"
DEFAULT_FONT_CAP = 96       # footage needs smaller type than a text-only card
MAX_WORDS_PER_CARD = make_clip.MAX_WORDS_PER_CARD
POSITIONS = ("lower", "center", "upper")


warn = kc.warn


def probe(path: Path) -> dict:
    """Duration, whether there is an audio track, and the source size."""
    probe_bin = shutil.which("ffprobe")
    if not probe_bin:
        die("ffprobe is not on PATH")
    raw = subprocess.run(
        [probe_bin, "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height:stream_side_data=rotation",
         "-of", "json", str(path)],
        capture_output=True, text=True)
    if raw.returncode != 0:
        die(f"ffprobe could not read {path}: {raw.stderr.strip()[:300]}")
    info = json.loads(raw.stdout or "{}")
    streams = info.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video:
        die(f"{path} has no video stream")
    rotation = 0
    for sd in video.get("side_data_list", []) or []:
        if "rotation" in sd:
            rotation = int(sd["rotation"])
    w, h = int(video["width"]), int(video["height"])
    if abs(rotation) in (90, 270):  # ffmpeg autorotates, so size as displayed
        w, h = h, w
    return {
        "duration": float(info.get("format", {}).get("duration", 0) or 0),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
        "width": w,
        "height": h,
    }


# ---------------------------------------------------------------------------
# Cards: load, shift into clip time, place
# ---------------------------------------------------------------------------


def load_cards(spec: dict, t_offset: float, clip_len: float) -> list[Card]:
    raw_cards = spec.get("cards") or []
    if not raw_cards:
        die("spec needs a non-empty 'cards' list")
    cards: list[Card] = []
    for i, raw in enumerate(raw_cards):
        if "text" not in raw or "start" not in raw or "end" not in raw:
            die(f"card {i} needs text, start and end")
        start = float(raw["start"]) - t_offset
        end = float(raw["end"]) - t_offset
        text = str(raw["text"]).strip()
        if end <= start:
            die(f"card {i} ({text!r}) ends before it starts")
        if end <= 0 or start >= clip_len:
            warn(f"card {i} ({text!r}) falls outside the trimmed pull, dropped")
            continue
        if start < 0 or end > clip_len:
            warn(f"card {i} ({text!r}) crosses the trim edge, clamped")
        start, end = max(0.0, start), min(clip_len, end)
        if len(text.split()) > MAX_WORDS_PER_CARD:
            warn(f"card {i} has {len(text.split())} words, two to four reads best on screen")
        cards.append(Card(text, round(start, 3), round(end, 3), list(raw.get("accent", []))))
    if not cards:
        die("no cards left inside the trimmed pull")
    cards.sort(key=lambda c: c.start)
    for a, b in zip(cards, cards[1:]):
        if b.start < a.end - 1e-6:
            warn(f"cards {a.text!r} and {b.text!r} overlap, they would stack on screen")
    return cards


def place_card(png: Path, position: str, nudge: int) -> tuple[int, int]:
    """Move a card rendered by make_clip.render_card to the wanted band.

    render_card always centres the text block at the middle of the safe
    square. That is right for generated backgrounds and wrong for a face, so
    the finished PNG is shifted vertically. The text box is measured from the
    opaque pixels only, because the soft shadow is translucent and would make
    the box too big. Returns the (top, bottom) of the text after the shift.
    """
    img = Image.open(png).convert("RGBA")
    solid = img.getchannel("A").point(lambda a: 255 if a >= 200 else 0)
    box = solid.getbbox()
    if box is None:
        die(f"card {png.name} rendered with no visible text")
    top, bottom = box[1], box[3]
    height = bottom - top

    if position == "lower":
        target_top = LOWER_BOTTOM - height
    elif position == "upper":
        target_top = UPPER_TOP
    else:
        target_top = (SAFE_TOP + SAFE_BOTTOM) // 2 - height // 2
    target_top += nudge

    # A nudge must not push text past the band it was placed in. In "lower"
    # the governing floor is LOWER_BOTTOM, not the generic safe square.
    floor = LOWER_BOTTOM if position == "lower" else SAFE_BOTTOM
    lo, hi = SAFE_TOP, floor - height
    if hi < lo:
        warn(f"{png.name}: text block is {height}px tall, taller than the safe square")
        target_top = lo
    else:
        target_top = max(lo, min(hi, target_top))

    dy = target_top - top
    moved = Image.new("RGBA", img.size, (0, 0, 0, 0))
    moved.paste(img, (0, dy))
    moved.save(png)
    return target_top, target_top + height


# ---------------------------------------------------------------------------
# Audio: two-pass loudnorm
# ---------------------------------------------------------------------------


def measure_loudness(src: Path, t_start: float, clip_len: float) -> str | None:
    """Pass one. Returns the loudnorm filter string with measured values, or None."""
    cmd = [ffmpeg_bin(), "-hide_banner", "-nostats", "-ss", f"{t_start}", "-t", f"{clip_len}",
           "-i", str(src), "-vn", "-af",
           f"loudnorm=I={LUFS}:TP={TRUE_PEAK}:LRA=11:print_format=json", "-f", "null", "-"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", res.stderr, re.S)
    if res.returncode != 0 or not match:
        return None
    try:
        m = json.loads(match.group(0))
        vals = {k: float(m[k]) for k in
                ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")}
    except (ValueError, KeyError):
        return None
    if any(v in (float("inf"), float("-inf")) or v != v for v in vals.values()):
        return None  # silent audio, nothing to measure
    return (f"loudnorm=I={LUFS}:TP={TRUE_PEAK}:LRA=11:measured_I={vals['input_i']}:"
            f"measured_TP={vals['input_tp']}:measured_LRA={vals['input_lra']}:"
            f"measured_thresh={vals['input_thresh']}:offset={vals['target_offset']}:linear=true")


# ---------------------------------------------------------------------------


def build(spec: dict, workdir: Path, check_only: bool = False) -> Path:
    for key in ("source", "out"):
        if key not in spec:
            die(f"spec needs '{key}'")
    src = Path(spec["source"])
    if not src.exists():
        die(f"source not found: {src}")
    out_path = Path(spec["out"])
    out_path.parent.mkdir(parents=True, exist_ok=True)

    info = probe(src)
    trim = spec.get("trim") or {}
    t_start = float(trim.get("start", 0.0))
    t_end = float(trim.get("end", info["duration"]))
    if t_end > info["duration"] + 0.05:
        warn(f"trim end {t_end}s is past the source end {info['duration']:.2f}s, clamped")
    t_end = min(t_end, info["duration"])
    clip_len = round(t_end - t_start, 3)
    if t_start < 0 or clip_len <= 0:
        die(f"bad trim: start {t_start}, end {t_end}")

    times = spec.get("times", "source")
    if times not in ("source", "clip"):
        die("'times' must be 'source' or 'clip'")
    cards = load_cards(spec, t_start if times == "source" else 0.0, clip_len)

    position = spec.get("caption_position", "lower")
    if position not in POSITIONS:
        die(f"caption_position must be one of {POSITIONS}")
    nudge = int(spec.get("caption_nudge", 0))

    scale_up = max(W / info["width"], H / info["height"])
    if scale_up > 1.5:
        warn(f"source is {info['width']}x{info['height']}; filling 1080x1920 enlarges it "
             f"{scale_up:.2f}x and crops away most of a horizontal frame. Soft picture expected")

    # ---- captions: one font size for the whole pull -----------------------
    font_path = pick_font(spec.get("font"))
    text_rgb = hex_rgb(spec["text_color"])
    accent_rgb = hex_rgb(spec["accent"])
    look = {"shadow": spec.get("shadow"), "line_height": spec.get("line_height")}
    # The action rail lives 200px in from the right on Instagram and TikTok,
    # and render_card centres the block, so the usable width is W minus 200 a
    # side. Sizing to W - 2*SAFE_SIDE puts the last word of an ordinary card
    # under the like button.
    fitted = uniform_font(cards, font_path, W - (2 * ACTION_RAIL),
                          max_lines=int(spec.get("max_lines", 2)))
    size = int(spec["font_size"]) if spec.get("font_size") else min(
        fitted.size, int(spec.get("font_size_max", DEFAULT_FONT_CAP)))
    font = kc.load_font(font_path, size)

    card_files = []
    for i, card in enumerate(cards):
        p = workdir / f"card{i:03d}.png"
        render_card(card, font, text_rgb, accent_rgb, p,
                    max_width=W - (2 * ACTION_RAIL), look=look)
        top, bottom = place_card(p, position, nudge)
        card_files.append(p)
        print(f"  card {i}: {card.start:6.2f}s to {card.end:6.2f}s  "
              f"text y {top}-{bottom}  {card.text!r}", file=sys.stderr)
    print(f"  type size {size}px, position {position}, clip {clip_len}s "
          f"(source {t_start}s to {t_end}s)", file=sys.stderr)

    # ---- video chain -------------------------------------------------------
    fx = min(1.0, max(0.0, float(spec.get("focus_x", 0.5))))
    fy = min(1.0, max(0.0, float(spec.get("focus_y", 0.5))))
    base = (f"[0:v]fps={FPS},"
            f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={W}:{H}:x='(iw-ow)*{fx}':y='(ih-oh)*{fy}',"
            f"setsar=1,format=yuv420p,setpts=PTS-STARTPTS[bg]")
    chain, last = [base], "bg"
    for i, card in enumerate(cards):
        nxt = f"v{i}"
        # gte/lt, not between(): between() is inclusive at both ends, so on the
        # frame where one card ends and the next starts both would be drawn.
        chain.append(f"[{last}][{i + 1}:v]overlay=0:0:"
                     f"enable='gte(t,{card.start:.3f})*lt(t,{card.end:.3f})'[{nxt}]")
        last = nxt
    filter_complex = ";".join(chain)

    # ---- audio chain -------------------------------------------------------
    has_audio = info["has_audio"]
    if has_audio:
        norm = measure_loudness(src, t_start, clip_len) if not check_only else None
        if norm is None:
            if not check_only:
                warn("loudness measurement failed or audio is silent, using one-pass loudnorm")
            norm = f"loudnorm=I={LUFS}:TP={TRUE_PEAK}:LRA=11"
        filter_complex += f";[0:a:0]{norm},aresample=48000[aout]"
    else:
        warn("source has no audio track, writing a real silent track at 48kHz stereo")

    cmd = [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
           "-ss", f"{t_start}", "-t", f"{clip_len}", "-i", str(src)]
    for p in card_files:
        cmd += ["-loop", "1", "-framerate", str(FPS), "-t", f"{clip_len}", "-i", str(p)]
    if not has_audio:
        # Silence is a track; no track is a defect, because a video-only MP4 is
        # refused or mishandled by some uploads and breaks a later concat. This
        # input goes AFTER the cards so their filter_complex indices do not move.
        cmd += ["-f", "lavfi", "-t", f"{clip_len}",
                "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
    cmd += ["-filter_complex", filter_complex, "-map", f"[{last}]"]
    if has_audio:
        cmd += ["-map", "[aout]", "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", "48000", "-ac", "2"]
    else:
        cmd += ["-map", f"{len(card_files) + 1}:a", "-c:a", "aac",
                "-b:a", AUDIO_BITRATE, "-ar", "48000", "-ac", "2", "-shortest"]
    cmd += ["-c:v", "libx264", "-profile:v", "high", "-preset", "medium",
            "-b:v", VIDEO_BITRATE, "-maxrate", "15M", "-bufsize", "20M",
            "-pix_fmt", "yuv420p", "-r", str(FPS), "-movflags", "+faststart",
            "-t", f"{clip_len}", str(out_path)]

    if check_only:
        print(" ".join(f'"{c}"' if (" " in c or "[" in c) else c for c in cmd))
        return out_path
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        die(f"ffmpeg failed\n{res.stderr.strip()[:3000]}")
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Burn caption cards onto your own footage, 1080x1920.")
    ap.add_argument("spec", help="path to the JSON spec")
    ap.add_argument("--brand", help="path to a brand file (font, colours, caption position)")
    ap.add_argument("--check", action="store_true", help="print the ffmpeg command and stop")
    ap.add_argument("--keep", action="store_true", help="keep the card PNG workdir for inspection")
    args = ap.parse_args()

    spec = kc.load_spec(args.spec, args.brand)
    workdir = Path(tempfile.mkdtemp(prefix="captionvideo-"))
    try:
        out = build(spec, workdir, check_only=args.check)
        if not args.check:
            dur = make_clip.probe_duration(str(out))
            print(f"{out}  {out.stat().st_size / 1_000_000:.2f} MB" + (f"  {dur:.2f}s" if dur else ""))
    finally:
        if args.keep:
            print(f"card PNGs kept in {workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
