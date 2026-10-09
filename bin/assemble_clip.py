#!/usr/bin/env python3
"""
assemble_clip.py: one long recording in, finished short clips out.

caption_video.py takes ONE continuous stretch of a recording and burns captions on
it. This takes MANY stretches of the same recording, plays them in the order the
cut list gives rather than the order they were said, and burns the captions on
that. One command can do a whole batch of pieces from one source file.

WHY EDIT ORDER IS THE POINT. People do not speak in the order a clip needs. The
first real batch built here took the hook from minute 19 and the story that proves
it from minute 3, and an earlier renderer that used ffmpeg's `select` filter put
them back in clock order, because select keeps what it keeps in source order. Six
finished videos were incoherent and had to be rebuilt. So order is imposed here,
not filtered: each segment is its own seeked input and they are concatenated in
list order.

WHAT IT DOES, in order:
  1. reads a JSON spec: the source, the segments, the caption cards, the look
  2. reports any footage two pieces of a batch share, before spending an encode
  3. stage one: segments concatenated in list order, reframed, optionally graded
     and skin-passed, colour tags corrected, out to a near lossless intermediate
  4. stage two: caption cards and the pinned hook burned onto the intermediate,
     out at the delivery bitrate
  5. checks the file it just wrote is not empty and is as long as the cut list says

WHY TWO STAGES, and it is not tidiness:
  - One pass would put every segment input and every caption input on a single
    filter graph. The real batch was 14 segments and 43 cards for one piece. That
    graph cannot be read, and when it fails the error names a label, not a card.
  - Loudness can only be measured on the ASSEMBLED audio. There is nothing to
    measure until the segments are joined, so the measurement sits between the
    stages.
  - The intermediate is written at crf 14, which is one visually free generation.

NOTHING IN HERE CARRIES ANYBODY'S BRAND. The font, the colours, the caption
height, the grade and the skin pass are all values in a style file. The one that
ships (specs/example-edit-style.json) is deliberately plain: white type, no grade,
no skin pass. Copy it, change it, keep it next to your own work.

Usage (from the kit folder; on Windows write `python` for `python3`):
    python3 bin/assemble_clip.py specs/example-edit.json
    python3 bin/assemble_clip.py cuts.json --style specs/mystyle.json
    python3 bin/assemble_clip.py cuts.json --only P4 --keep-audio
    python3 bin/assemble_clip.py cuts.json --dry-run      # arithmetic only, no encode
    python3 bin/assemble_clip.py cuts.json --check        # print the ffmpeg commands

THE SPEC. One piece:

{
  "brand": "example-edit-style.json",      # the look. --style overrides it
  "source": "footage/long-take.mov",       # the long recording
  "out": "../out/piece-1.mp4",
  "keep_audio": false,                     # see --keep-audio below
  "times": "clip",                         # card times: "clip" = seconds into the
                                           # finished piece (default). "source" =
                                           # seconds in the long recording, mapped
                                           # through the segment list for you
  "hook": {"text": "the line that pins it", "hold": 4.0},
  "segments": [
    {"start": 1140.2, "end": 1148.6, "note": "the hook, from minute 19"},
    {"start": 182.4,  "end": 195.0,  "note": "the story that proves it"}
  ],
  "cards": [
    {"text": "two to four words", "start": 0.0, "end": 1.6},
    {"text": "per card", "start": 1.6, "end": 3.0, "accent": ["card"]}
  ]
}

A batch of pieces from one source, which is the shape a cut list already has:

{
  "brand": "example-edit-style.json",
  "source": "footage/long-take.mov",
  "out_dir": "../out/batch1",
  "pieces": [
    {"piece": "P4", "filename": "stop-asking-how", "duration": 118.71,
     "segments": [...], "caption_cards": [...], "hook_text": "..."}
  ]
}

Both spellings are accepted on purpose, so a planning step can write one file and
this can render it without a conversion: "cards" or "caption_cards", "hook" or
"hook_text", "out" or "filename" beside "out_dir". A "duration" on a piece is
checked against the segments and a mismatch is reported.

--keep-audio leaves the sound completely alone: no loudness normalisation, no
filtering, no resampling. Use it when the audio was already processed somewhere
else, for example in the iPhone's Audio Studio. Without it the finished piece is
normalised to -14 LUFS, true peak -1.0 dBTP, measured on the assembled audio and
applied in one pass over the intermediate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import kit_common as kc  # noqa: E402  (before PIL: it can re-run us inside the kit .venv)
import caption_video  # noqa: E402  (imported as modules so nothing is copied)
import make_clip  # noqa: E402
from PIL import ImageFont  # noqa: E402
from make_clip import (  # noqa: E402
    AUDIO_BITRATE, FPS, H, LUFS, TRUE_PEAK, VIDEO_BITRATE, W,
    Card, ffmpeg_bin, has_filter, hex_rgb, pick_font, render_card,
)

TOOL = "assemble_clip/1.0"
die = kc.die
warn = kc.warn

# Shared footage between two pieces of one batch. Found the hard way: two pairs of
# finished reels shared more than 50 seconds each and two of them ended on an
# identical close. It is arithmetic to spot from a cut list and impossible to fix
# after rendering, so it is reported before anything is encoded.
SHARED_WARN_SECONDS = 10.0
SAME_ENDING_TOLERANCE = 0.25

# Plain and neutral on purpose. Nobody's look lives in the code.
DEFAULTS: dict = {
    "font_index": 0,            # a .ttc holds several faces; 0 is the first
    "side_margin": caption_video.ACTION_RAIL,
    "max_lines": 2,
    "font_size_max": caption_video.DEFAULT_FONT_CAP,
    "caption_position": "lower",
    "caption_nudge": 0,
    "hook": {"text": "", "hold": 4.0, "position": "upper", "nudge": 0, "size_pct": 0.8},
    "zoom": 1.0,
    "focus_x": 0.5,
    "focus_y": 0.5,
    "fade_ms": 0,
    "color_fix": "auto",
    "grade": {"enabled": False, "saturation": 1.0, "contrast": 1.0,
              "brightness": 0.0, "curves": ""},
    "skin": {"enabled": False, "sigma_s": 14, "sigma_r": 0.12, "mask_blur": 9,
             "u": [100, 132], "v": [134, 176]},
    "export": {"video_bitrate": VIDEO_BITRATE, "lufs": LUFS, "true_peak": TRUE_PEAK,
               "intermediate_crf": 14, "keep_audio_bitrate": "320k"},
    "times": "clip",
    "keep_audio": False,
}


def deep_merge(base: dict, over: dict) -> dict:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in over.items():
        if v is None:
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Colour. The HDR fix, and why three other approaches are not used
# ---------------------------------------------------------------------------

HDR_TRANSFERS = {"arib-std-b67", "smpte2084"}        # HLG and PQ
HDR_PRIMARIES = {"bt2020"}


def probe_colour(src: Path) -> dict:
    """What the source claims about its own colour. caption_video.probe does not
    ask for this, and the answer decides whether the tags need correcting."""
    fp = shutil.which("ffprobe")
    if not fp:
        die("ffprobe is not on PATH")
    res = subprocess.run(
        [fp, "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=color_transfer,color_primaries,color_space,pix_fmt",
         "-of", "json", str(src)], capture_output=True, text=True)
    if res.returncode != 0:
        return {}
    streams = (json.loads(res.stdout or "{}").get("streams") or [{}])
    return {k: str(v) for k, v in streams[0].items()}


def colour_fix_steps(colour: dict, mode: str) -> list[str]:
    """The `setparams` filter, which is the one approach that works.

    A phone that records HLG (an iPhone in Dolby Vision, for example) writes
    `color_transfer=arib-std-b67`, `color_primaries=bt2020`, 10 bit. Rendered to
    ordinary 8 bit H.264 the PICTURE is right but the FILE still claims HLG, so a
    player reinterprets SDR data as HDR and the clip looks wrong on a phone and
    right on a laptop, or the other way round.

    Three approaches were tried on real footage on 2026-10-05 and measured. None
    of these three is used here, and this is why:

      -color_trc bt709 -color_primaries bt709 as OUTPUT FLAGS
          The tags do not take. The output still reads arib-std-b67 and bt2020.
      format=gbrpf32le,tonemap=hable
          Crushed and dark, because there is no linearising stage without the
          zscale or libplacebo filter, and most ffmpeg builds have neither.
      avconvert, the macOS native converter
          Correct tags, but it pushes skin red: mean absolute difference from the
          source measured at 24 to 30 per channel.

    `setparams` sets the colour properties on the FRAMES, which the encoder then
    writes out. Measured difference from the source picture: 1.6 per channel,
    which is encoding noise. The tags are corrected and the image is not touched.

    Leaving the picture alone is right for flat, bright footage with no strong
    highlights, where HLG's lower range tracks SDR gamma closely. Footage with
    real highlight range needs genuine tone mapping, which needs an ffmpeg built
    with zscale or libplacebo. Set "color_fix": "off" and grade it elsewhere.
    """
    mode = str(mode or "auto").lower()
    if mode in ("off", "none", "false"):
        return []
    looks_hdr = (colour.get("color_transfer", "") in HDR_TRANSFERS
                 or colour.get("color_primaries", "") in HDR_PRIMARIES)
    if mode == "auto" and not looks_hdr:
        return []
    if mode == "auto":
        print(f"  colour: source reads {colour.get('color_transfer', '?')} / "
              f"{colour.get('color_primaries', '?')}, retagging the output bt709",
              file=sys.stderr)
    return ["setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709"]


# ---------------------------------------------------------------------------
# The spec
# ---------------------------------------------------------------------------


@dataclass
class Layer:
    text: str
    start: float
    end: float
    band: str                   # "caption" or "hook"
    accent: list[str] = field(default_factory=list)
    png: Path | None = None


@dataclass
class Piece:
    name: str
    out: Path
    segments: list[tuple[float, float]] = field(default_factory=list)
    cards: list[dict] = field(default_factory=list)
    hook: str = ""
    hook_hold: float = 0.0
    declared: float | None = None

    @property
    def total(self) -> float:
        return round(sum(b - a for a, b in self.segments), 3)


def _float(value, what: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        die(f"{what} must be a number, got {value!r}")
    return 0.0


def read_segments(raw, what: str, src_len: float) -> list[tuple[float, float]]:
    if not isinstance(raw, list) or not raw:
        die(f"{what} needs a non-empty 'segments' list. Each entry is "
            '{"start": seconds, "end": seconds}; any other keys in it are ignored, '
            "so a cut list with its own notes can be used as it stands.")
    segs: list[tuple[float, float]] = []
    for i, seg in enumerate(raw):
        if not isinstance(seg, dict) or "start" not in seg or "end" not in seg:
            die(f"{what} segment {i} needs 'start' and 'end' in seconds")
        a = _float(seg["start"], f"{what} segment {i} start")
        b = _float(seg["end"], f"{what} segment {i} end")
        if b <= a:
            die(f"{what} segment {i} ends before it starts: {a} to {b}")
        if a >= src_len:
            die(f"{what} segment {i} starts at {a:.2f}s, past the end of the "
                f"source ({src_len:.2f}s). Nothing would be rendered.")
        if b > src_len + 0.05:
            warn(f"{what} segment {i} ends at {b:.2f}s, past the source end "
                 f"({src_len:.2f}s), clamped")
            b = src_len
        segs.append((round(a, 3), round(b, 3)))
    return segs


def map_to_clip(t: float, segs: list[tuple[float, float]]) -> tuple[float, float] | None:
    """Source seconds to finished-piece seconds.

    Returns (clip_time, clip_end_of_that_segment), or None when the moment is in
    footage this piece does not use. A transcript of the long recording carries
    source times, so this is what lets a cut list and its captions share one clock.
    """
    off = 0.0
    for a, b in segs:
        if a - 1e-6 <= t <= b + 1e-6:
            return round(off + max(0.0, min(b, t) - a), 3), round(off + (b - a), 3)
        off += b - a
    return None


def read_cards(raw, piece: Piece, times: str) -> list[dict]:
    cards: list[dict] = []
    for i, c in enumerate(raw or []):
        if not isinstance(c, dict) or not str(c.get("text", "")).strip():
            warn(f"{piece.name}: card {i} has no text, dropped")
            continue
        text = str(c["text"]).strip()
        if "start" not in c or "end" not in c:
            die(f"{piece.name}: card {i} ({text!r}) needs 'start' and 'end'")
        a = _float(c["start"], f"{piece.name} card {i} start")
        b = _float(c["end"], f"{piece.name} card {i} end")
        if times == "source":
            ma, mb = map_to_clip(a, piece.segments), map_to_clip(b, piece.segments)
            if ma is None:
                warn(f"{piece.name}: card {i} ({text!r}) is at {a:.2f}s in the source, "
                     "which this piece does not use. Dropped")
                continue
            a, seg_end = ma
            b = mb[0] if mb is not None else seg_end
            if b <= a:
                # The card's words straddle a splice: its end is in a different
                # segment, or in footage this piece cut out. Hold it to the end of
                # the segment it starts in rather than dropping a line of speech.
                warn(f"{piece.name}: card {i} ({text!r}) crosses a cut, "
                     f"held to {seg_end:.2f}s")
                b = seg_end
        if b <= a:
            die(f"{piece.name}: card {i} ({text!r}) ends before it starts")
        if a >= piece.total:
            warn(f"{piece.name}: card {i} ({text!r}) starts at {a:.2f}s, past the "
                 f"end of the piece ({piece.total:.2f}s). Dropped")
            continue
        if b > piece.total + 0.05:
            warn(f"{piece.name}: card {i} ({text!r}) runs past the end of the piece, clamped")
            b = piece.total
        words = len(text.split())
        if words > make_clip.MAX_WORDS_PER_CARD:
            warn(f"{piece.name}: card {i} has {words} words. Two to four reads best on screen")
        cards.append({"text": text, "start": round(a, 3), "end": round(b, 3),
                      "accent": list(c.get("accent", []))})
    cards.sort(key=lambda c: c["start"])
    for x, y in zip(cards, cards[1:]):
        if y["start"] < x["end"] - 1e-6:
            warn(f"{piece.name}: {x['text']!r} and {y['text']!r} overlap in time, "
                 "they would stack on screen")
    return cards


def read_pieces(style: dict, spec_dir: Path, src_len: float) -> list[Piece]:
    """`style` is the spec laid over the style file laid over the neutral defaults,
    so a batch can set anything per piece and still inherit the rest."""
    spec = style
    raw_pieces = spec.get("pieces")
    if raw_pieces is None:
        raw_pieces = [spec]                 # one piece is a batch of one
    if not isinstance(raw_pieces, list) or not raw_pieces:
        die("'pieces' must be a non-empty list")
    out_dir = spec.get("out_dir")
    pieces: list[Piece] = []
    for i, raw in enumerate(raw_pieces):
        if not isinstance(raw, dict):
            die(f"piece {i} must be a JSON object")
        name = str(raw.get("piece") or raw.get("name") or raw.get("filename")
                   or Path(str(raw.get("out", ""))).stem or f"piece{i + 1}")
        stem = str(raw.get("filename") or name).replace(".mp4", "")
        if raw.get("out"):
            out = Path(kc.resolve_output(str(raw["out"]), spec_dir))
        elif out_dir:
            out = Path(kc.resolve_output(str(out_dir), spec_dir)) / f"{stem}.mp4"
        else:
            die(f"piece {name!r} has nowhere to go. Give it an \"out\", or give the "
                "spec an \"out_dir\" and each piece a \"filename\"")
        piece = Piece(name=name, out=out, declared=(
            _float(raw["duration"], f"{name} duration") if raw.get("duration") else None))
        piece.segments = read_segments(raw.get("segments"), f"piece {name!r}", src_len)
        times = str(raw.get("times") or spec.get("times") or "clip").lower()
        if times not in ("clip", "source"):
            die("'times' must be \"clip\" (seconds into the finished piece) or "
                "\"source\" (seconds in the long recording)")
        piece.cards = read_cards(raw.get("cards") or raw.get("caption_cards"), piece, times)
        # "hook" may be a block or a plain string, and "hook_text" is the spelling a
        # cut list uses. A style file's own hook block supplies whatever the piece
        # leaves out, including a hook line shared by every piece in a batch. Read
        # in this order because a one piece spec IS the merged style, so its
        # defaults are sitting in the same dictionary and must not win.
        hook_cfg = style.get("hook") or {}
        raw_hook = raw.get("hook")
        text, hold = "", hook_cfg.get("hold", 4.0)
        if isinstance(raw_hook, dict):
            text = str(raw_hook.get("text") or "").strip()
            hold = raw_hook.get("hold", hold)
        elif raw_hook:
            text = str(raw_hook).strip()
        piece.hook = text or str(raw.get("hook_text") or "").strip() or str(
            hook_cfg.get("text") or "").strip()
        piece.hook_hold = _float(hold, "hook hold")
        if piece.hook:
            piece.hook_hold = max(0.5, min(piece.hook_hold, piece.total))
        if piece.declared is not None and abs(piece.declared - piece.total) > 0.05:
            warn(f"piece {name!r} says duration {piece.declared:.2f}s and its segments "
                 f"sum to {piece.total:.2f}s. The segments are what gets rendered")
        pieces.append(piece)
    names = [p.name for p in pieces]
    if len(set(names)) != len(names):
        warn("two pieces share a name, so their reports read the same: " + ", ".join(names))
    outs = [str(p.out) for p in pieces]
    if len(set(outs)) != len(outs):
        die("two pieces write to the same file. One would overwrite the other.")
    return pieces


# ---------------------------------------------------------------------------
# The duplication check, before any encode
# ---------------------------------------------------------------------------


def shared_seconds(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> float:
    total = 0.0
    for s1, e1 in a:
        for s2, e2 in b:
            total += max(0.0, min(e1, e2) - max(s1, s2))
    return round(total, 2)


def duplication_report(pieces: list[Piece]) -> None:
    if len(pieces) < 2:
        return
    print("  cut list overlap, in source seconds:", file=sys.stderr, flush=True)
    said = 0
    for i, p in enumerate(pieces):
        for q in pieces[i + 1:]:
            shared = shared_seconds(p.segments, q.segments)
            same_end = (abs(p.segments[-1][0] - q.segments[-1][0]) < SAME_ENDING_TOLERANCE
                        and abs(p.segments[-1][1] - q.segments[-1][1]) < SAME_ENDING_TOLERANCE)
            if shared >= SHARED_WARN_SECONDS or same_end:
                pct_p = 100.0 * shared / max(p.total, 0.01)
                pct_q = 100.0 * shared / max(q.total, 0.01)
                warn(f"{p.name} and {q.name} share {shared:.1f}s of footage "
                     f"({pct_p:.0f}% of {p.name}, {pct_q:.0f}% of {q.name})"
                     + (". THEY ALSO END ON THE SAME SEGMENT, so two finished clips "
                        "close on the same words" if same_end else ""))
                said += 1
            elif shared > 0:
                print(f"    {p.name} / {q.name}: {shared:.1f}s", file=sys.stderr, flush=True)
                said += 1
    if not said:
        print("    none, no two pieces share any footage", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Type
# ---------------------------------------------------------------------------


def load_face(path: str, size: int, index: int) -> ImageFont.FreeTypeFont:
    """kit_common.load_font cannot reach past the first face of a .ttc collection.

    A .ttc holds several weights in one file and a kit buyer naming one gets
    whichever face is first, whatever their style file asked for.
    """
    if index in (0, None) or path == kc.PILLOW_BUILTIN:
        return kc.load_font(path, size)
    try:
        return ImageFont.truetype(path, size, index=int(index))
    except OSError as exc:
        die(f"cannot open face index {index} of {path}: {exc}\n"
            "  A .ttc file holds several faces, a .ttf holds one (index 0). Check "
            "'font_index' in your style file.")
    return kc.load_font(path, size)


def fit_size(cards: list[dict], font_path: str, index: int, max_width: int,
             max_lines: int, cap: int) -> int:
    """One type size for the whole piece, and the same rule as make_clip.uniform_font.

    Written out here only because uniform_font cannot pass a .ttc face index. The
    wrapping itself is make_clip.wrap, not a copy of it.
    """
    size = min(cap, 150)
    while size > 40:
        font = load_face(font_path, size, index)
        if all(len(make_clip.wrap(c["text"], font, max_width)) <= max_lines for c in cards):
            return size
        size -= 2
    return 40


def draw_layers(piece: Piece, style: dict, workdir: Path) -> list[Layer]:
    font_path = pick_font(style.get("font"))
    index = int(style.get("font_index", 0) or 0)
    margin = int(style.get("side_margin", caption_video.ACTION_RAIL))
    max_width = W - 2 * margin
    max_lines = int(style.get("max_lines", 2))
    cap = int(style.get("font_size_max", caption_video.DEFAULT_FONT_CAP))
    size = (int(style["font_size"]) if style.get("font_size")
            else min(cap, fit_size(piece.cards or [{"text": piece.hook or "x"}],
                                   font_path, index, max_width, max_lines, cap)))
    text_rgb, accent_rgb = hex_rgb(style["text_color"]), hex_rgb(style["accent"])
    look = {"shadow": style.get("shadow"), "line_height": style.get("line_height")}
    hook_cfg = style.get("hook") or {}

    layers: list[Layer] = []
    if piece.hook:
        layers.append(Layer(piece.hook, 0.0, piece.hook_hold, "hook"))
    for c in piece.cards:
        layers.append(Layer(c["text"], c["start"], c["end"], "caption", c["accent"]))

    for i, layer in enumerate(layers):
        hook = layer.band == "hook"
        px = max(28, int(size * float(hook_cfg.get("size_pct", 0.8)))) if hook else size
        font = load_face(font_path, px, index)
        layer.png = workdir / f"{'hook' if hook else f'card{i:03d}'}.png"
        render_card(Card(layer.text, layer.start, layer.end, layer.accent), font,
                    text_rgb, accent_rgb, layer.png, max_width=max_width, look=look)
        position = (str(hook_cfg.get("position", "upper")) if hook
                    else str(style.get("caption_position", "lower")))
        if position not in caption_video.POSITIONS:
            die(f"caption position must be one of {caption_video.POSITIONS}, got {position!r}")
        nudge = int(hook_cfg.get("nudge", 0) if hook else style.get("caption_nudge", 0))
        top, bottom = caption_video.place_card(layer.png, position, nudge)
        print(f"    {layer.band:7} {layer.start:6.2f}s to {layer.end:6.2f}s  "
              f"{px}px  y {top}-{bottom}  {layer.text!r}", file=sys.stderr)
    return layers


# ---------------------------------------------------------------------------
# The two stages
# ---------------------------------------------------------------------------


def stage1_cmd(src: Path, piece: Piece, style: dict, colour: dict, out: Path) -> list[str]:
    """Segments in LIST order, concatenated, reframed, graded, skin passed, retagged."""
    args: list[str] = []
    chain: list[str] = []
    labels = ""
    for i, (a, b) in enumerate(piece.segments):
        # -ss before -i so each input seeks instead of decoding from zero. Fourteen
        # segments of a one hour file decoded from the top would be fourteen hours
        # of decoding.
        args += ["-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(src)]
        chain.append(f"[{i}:v]setpts=PTS-STARTPTS,fps={FPS},setsar=1[v{i}]")
        # a:0 explicitly: a phone file can carry two audio streams (an AAC track
        # and a spatial one), and [i:a] would hand concat both of them.
        chain.append(f"[{i}:a:0]asetpts=PTS-STARTPTS[a{i}]")
        labels += f"[v{i}][a{i}]"
    chain.append(f"{labels}concat=n={len(piece.segments)}:v=1:a=1[vc][ac]")

    zoom = max(1.0, float(style.get("zoom", 1.0)))
    fx = min(1.0, max(0.0, float(style.get("focus_x", 0.5))))
    fy = min(1.0, max(0.0, float(style.get("focus_y", 0.5))))
    sw, sh = int(round(W * zoom)), int(round(H * zoom))
    steps = [f"scale={sw}:{sh}:force_original_aspect_ratio=increase:flags=lanczos",
             f"crop={W}:{H}:x='(iw-ow)*{fx}':y='(ih-oh)*{fy}'", "setsar=1"]

    grade = style.get("grade") or {}
    if grade.get("enabled"):
        steps.append("eq=saturation={:.3f}:contrast={:.3f}:brightness={:.3f}".format(
            float(grade.get("saturation", 1.0)), float(grade.get("contrast", 1.0)),
            float(grade.get("brightness", 0.0))))
        if str(grade.get("curves") or "").strip():
            steps.append(f"curves=all='{str(grade['curves']).strip()}'")

    skin = style.get("skin") or {}
    skin_on = bool(skin.get("enabled"))
    if skin_on:
        missing = [n for n in ("bilateral", "maskedmerge", "lutyuv", "gblur")
                   if not has_filter(n)]
        if missing:
            die("the skin pass needs these ffmpeg filters and this build does not have "
                f"them: {', '.join(missing)}.\n"
                "  Install a full ffmpeg build, or set \"skin\": {\"enabled\": false} in "
                "your style file. Everything else in this tool works without them.")
        # Bilateral smoothing, applied through a mask so the whole frame is not
        # flattened. bilateral is EDGE PRESERVING: it flattens low contrast texture
        # (a blemish on a flat cheek) and leaves real edges (eyelashes, nostrils,
        # hairline) alone. planes=1 is luma only, so skin COLOUR is untouched.
        # Strengths measured on a real face: 6/0.06 is barely visible, 14/0.12 is
        # the sweet spot, 24/0.18 is plastic.
        #
        # WHAT THE MASK ACTUALLY IS, checked by rendering it on 2026-10-08 rather
        # than trusting the description it arrived with. It was written as a chroma
        # test for skin tones, and it is NOT one: `format=gray` after the lutyuv
        # folds luma back in, and the mask that comes out is a soft low contrast
        # greyscale copy of the picture, averaging about half strength everywhere,
        # a little lower on dark hair and a little higher on a bright wall. So it
        # softens the treatment, it does not aim it.
        # The filter string is kept exactly as it was measured and approved on a
        # real face, because that is the version somebody actually looked at. What
        # keeps hair, eyes and a patterned background sharp is bilateral itself,
        # not the mask. Anyone making this a true skin selector has to rebuild it
        # with geq (which can read cb and cr together) and LOOK AT THE RESULT, not
        # reason about it.
        #
        # What it does not do, either way: it lowers the contrast of a blemish so
        # it reads less. It does not heal or paint anything out, and no filter can
        # tidy a flyaway hair, because that is a high contrast edge and an edge
        # preserving filter is built to protect those.
        steps.append("format=yuv444p")
        steps += colour_fix_steps(colour, style.get("color_fix", "auto"))
        chain.append("[vc]" + ",".join(steps) + ",split=3[sbase][ssmooth][smask]")
        chain.append("[ssmooth]bilateral=sigmaS={}:sigmaR={}:planes=1[smoothed]".format(
            float(skin.get("sigma_s", 14)), float(skin.get("sigma_r", 0.12))))
        u, v = list(skin.get("u", [100, 132])), list(skin.get("v", [134, 176]))
        chain.append(
            f"[smask]lutyuv=y=val:u='if(between(val,{int(u[0])},{int(u[1])}),255,0)'"
            f":v='if(between(val,{int(v[0])},{int(v[1])}),255,0)',format=gray,"
            f"gblur=sigma={float(skin.get('mask_blur', 9))}[mask]")
        chain.append("[sbase][smoothed][mask]maskedmerge,format=yuv420p[vout]")
    else:
        steps.append("format=yuv420p")
        steps += colour_fix_steps(colour, style.get("color_fix", "auto"))
        chain.append("[vc]" + ",".join(steps) + "[vout]")

    export = style.get("export") or {}
    return [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error"] + args + [
        "-filter_complex", ";".join(chain), "-map", "[vout]", "-map", "[ac]",
        "-c:v", "libx264", "-preset", "veryfast",
        "-crf", str(int(export.get("intermediate_crf", 14))),
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        # The intermediate's audio is the assembled source sound, untouched. Any
        # normalisation happens in stage two, after it can be measured.
        "-c:a", "aac", "-b:a", str(export.get("keep_audio_bitrate", "320k")),
        "-t", f"{piece.total:.3f}", str(out)]


def stage2_cmd(base: Path, piece: Piece, layers: list[Layer], style: dict,
               norm: str | None, keep_audio: bool, out: Path) -> list[str]:
    """Captions and the hook burned onto the intermediate, out at delivery bitrate."""
    total = piece.total
    fade = max(0.0, float(style.get("fade_ms", 0)) / 1000.0)
    args = ["-i", str(base)]
    chain = ["[0:v]format=yuva420p[v0]"]

    # A fade belongs on a card's first appearance and its last exit, not on every
    # handover. Measured: fading both ends of two touching cards drops the caption
    # band to zero brightness for two frames at every card change, which on a
    # rolling caption is a blink about once a second.
    touch = 1.5 / FPS

    def touching(layer: Layer, side: str) -> bool:
        edge = layer.start if side == "before" else layer.end
        return any(o is not layer and o.band == layer.band
                   and abs((o.end if side == "before" else o.start) - edge) < touch
                   for o in layers)

    for i, layer in enumerate(layers):
        args += ["-loop", "1", "-framerate", str(FPS), "-t", f"{total:.3f}", "-i", str(layer.png)]
        steps = [f"[{i + 1}:v]format=rgba"]
        if fade > 0:
            if not touching(layer, "before"):
                steps.append(f"fade=t=in:st={layer.start:.3f}:d={fade:.3f}:alpha=1")
            if not touching(layer, "after"):
                steps.append(f"fade=t=out:st={max(0.0, layer.end - fade):.3f}:"
                             f"d={fade:.3f}:alpha=1")
        chain.append(",".join(steps) + f"[l{i}]")
        # gte/lt, not between(): between() is inclusive at both ends, so on the
        # frame where one card ends and the next starts both would be drawn.
        chain.append(f"[v{i}][l{i}]overlay=0:0:format=auto:eof_action=pass:repeatlast=0:"
                     f"enable='gte(t,{layer.start:.3f})*lt(t,{layer.end:.3f})'[v{i + 1}]")
    chain.append(f"[v{len(layers)}]format=yuv420p,setsar=1[vout]")

    export = style.get("export") or {}
    cmd = [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error"] + args
    if keep_audio:
        audio = ["-c:a", "copy"]
    else:
        lufs = float(export.get("lufs", LUFS))
        peak = float(export.get("true_peak", TRUE_PEAK))
        chain.append(f"[0:a]{norm or f'loudnorm=I={lufs}:TP={peak}:LRA=11'},aresample=48000[aout]")
        audio = ["-map", "[aout]", "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", "48000", "-ac", "2"]
    cmd += ["-filter_complex", ";".join(chain), "-map", "[vout]"]
    if keep_audio:
        cmd += ["-map", "0:a:0"]
    cmd += audio + ["-c:v", "libx264", "-profile:v", "high", "-preset", "medium",
                    "-b:v", str(export.get("video_bitrate", VIDEO_BITRATE)),
                    "-maxrate", "15M", "-bufsize", "20M", "-pix_fmt", "yuv420p",
                    "-r", str(FPS), "-movflags", "+faststart",
                    "-t", f"{total:.3f}", str(out)]
    return cmd


def run_ff(cmd: list[str], what: str) -> None:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        die(f"{what} failed (ffmpeg exit {res.returncode})\n{res.stderr.strip()[:3000]}")


def require_real_output(path: Path, what: str, expected: float | None = None) -> dict:
    """A file that exists is not a render that worked.

    This is here because of a specific failure: a stage wrote a zero byte file,
    ffmpeg returned 0, and the run was reported as a success. So the size and the
    duration are both read back off the file before anything says it worked.
    """
    if not path.exists():
        die(f"{what}: ffmpeg said it succeeded and wrote no file at all: {path}")
    size = path.stat().st_size
    if size == 0:
        die(f"{what}: ffmpeg wrote a ZERO BYTE file at {path} and returned success. "
            "Nothing was rendered. The usual cause is a segment that starts past the "
            "end of the source, or a filter label that never reached the output.")
    if size < 20_000:
        warn(f"{what}: {path.name} is only {size} bytes, which is too small for real "
             "video. Look at it before using it.")
    info = caption_video.probe(path)
    if not info.get("duration"):
        die(f"{what}: {path.name} has no readable duration, so it is not a usable video")
    if expected is not None:
        drift = abs(info["duration"] - expected)
        if drift > 1.0:
            die(f"{what}: the cut list adds up to {expected:.2f}s and the file is "
                f"{info['duration']:.2f}s, {drift:.2f}s out. A segment was dropped or "
                "clamped. Nothing here is safe to post, so this is a failure, not a warning.")
        if drift > 0.1:
            warn(f"{what}: {info['duration']:.2f}s out against {expected:.2f}s expected "
                 f"({drift:.2f}s drift from frame rounding at the splices)")
    return info


# ---------------------------------------------------------------------------
# Skipping work that is already done
# ---------------------------------------------------------------------------


def fingerprint(src: Path, piece: Piece, style: dict, keep_audio: bool) -> str:
    h = hashlib.sha256()
    st = src.stat()
    h.update(TOOL.encode())
    h.update(f"{src}|{st.st_size}|{int(st.st_mtime)}|{keep_audio}".encode())
    h.update(json.dumps({"segments": piece.segments, "cards": piece.cards,
                         "hook": piece.hook, "hold": piece.hook_hold},
                        sort_keys=True).encode())
    h.update(json.dumps({k: v for k, v in style.items() if not k.startswith("_")},
                        sort_keys=True, default=str).encode())
    return h.hexdigest()[:16]


def sidecar(out: Path) -> Path:
    return out.with_name(out.name + ".assemble.json")


# ---------------------------------------------------------------------------


def render(piece: Piece, src: Path, style: dict, colour: dict, args) -> bool:
    keep_audio = bool(args.keep_audio or style.get("keep_audio"))
    fp = fingerprint(src, piece, style, keep_audio)
    side = sidecar(piece.out)
    if not args.force and piece.out.exists() and piece.out.stat().st_size > 0 and side.exists():
        try:
            if json.loads(side.read_text()).get("fingerprint") == fp:
                print(f"{piece.name}: already current, skipped ({piece.out.name}). "
                      "--force re-renders")
                return True
        except (json.JSONDecodeError, OSError):
            pass

    print(f"{piece.name}: {len(piece.segments)} segments  {piece.total:.2f}s  "
          f"{len(piece.cards)} cards" + (" + hook" if piece.hook else "")
          + ("  [source audio kept as recorded]" if keep_audio else ""), flush=True)
    workdir = Path(tempfile.mkdtemp(prefix="assemble-"))
    try:
        layers = draw_layers(piece, style, workdir)
        base = workdir / "intermediate.mp4"
        one = stage1_cmd(src, piece, style, colour, base)
        if args.check:
            print("# stage 1\n" + shell(one))
        else:
            started = time.time()
            run_ff(one, f"{piece.name} stage 1 (assembly)")
            require_real_output(base, f"{piece.name} stage 1", piece.total)
            print(f"    stage 1  {base.stat().st_size / 1_000_000:.1f} MB  "
                  f"{time.time() - started:.1f}s", file=sys.stderr)

        norm = None
        if not keep_audio and not args.check:
            # Measured on the ASSEMBLED audio, which is why this cannot happen
            # before stage one. One pass of loudnorm lands several LU off on a
            # short clip, so the measurement is taken and then applied.
            norm = caption_video.measure_loudness(base, 0.0, piece.total)
            if norm is None:
                warn(f"{piece.name}: loudness measurement failed or the audio is "
                     "silent, one-pass loudnorm used")

        piece.out.parent.mkdir(parents=True, exist_ok=True)
        two = stage2_cmd(base, piece, layers, style, norm, keep_audio, piece.out)
        if args.check:
            print("# stage 2\n" + shell(two))
            return True
        started = time.time()
        run_ff(two, f"{piece.name} stage 2 (captions)")
        info = require_real_output(piece.out, f"{piece.name} stage 2", piece.total)
        side.write_text(json.dumps({
            "tool": TOOL, "fingerprint": fp, "written": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "source": str(src), "segments": piece.segments, "layers": len(layers),
            "keep_audio": keep_audio, "duration_out": round(info["duration"], 3),
        }, indent=2) + "\n")
        print(f"  wrote {piece.out}")
        print(f"    {info['width']}x{info['height']}  {info['duration']:.2f}s  "
              f"{piece.out.stat().st_size / 1_000_000:.2f} MB  {len(layers)} layers  "
              f"{time.time() - started:.1f}s")
        return True
    finally:
        if args.keep:
            print(f"    layer PNGs and intermediate kept in {workdir}", file=sys.stderr)
        else:
            shutil.rmtree(workdir, ignore_errors=True)


def shell(cmd: list[str]) -> str:
    return " ".join(f'"{c}"' if (" " in c or "[" in c or "'" in c) else c for c in cmd)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="A long recording in, finished short clips out. Segments play in "
                    "the order the cut list gives, not the order they were said.",
        epilog="The cut list shape is in specs/example-edit.json and the look is in "
               "specs/example-edit-style.json, both with notes in them. bin/plan_clips.py "
               "writes a cut list this reads unchanged.")
    ap.add_argument("spec", help="path to the JSON cut list")
    ap.add_argument("--style", "--brand", dest="brand",
                    help="style file: font, colours, caption height, grade, skin pass")
    ap.add_argument("--only", action="append", default=[],
                    help="render just the pieces whose name contains this. Repeatable")
    ap.add_argument("--keep-audio", action="store_true",
                    help="leave the sound exactly as recorded: no loudness "
                         "normalisation, no filtering, no resampling")
    ap.add_argument("--force", action="store_true", help="re-render even if the output is current")
    ap.add_argument("--dry-run", action="store_true",
                    help="read the cut list, report the arithmetic and the overlaps, encode nothing")
    ap.add_argument("--check", action="store_true", help="print the ffmpeg commands and stop")
    ap.add_argument("--keep", action="store_true", help="keep the working folder for inspection")
    args = ap.parse_args()

    # Checked here rather than in kit_check.py, because these two are needed by this
    # tool alone: concat joins the segments and setparams corrects the colour tags.
    # The skin pass needs four more and asks for them only when it is switched on.
    thin = [f for f in ("concat", "setparams") if not has_filter(f)]
    if thin:
        die(f"this ffmpeg build is missing: {', '.join(thin)}.\n"
            "  Install a full ffmpeg build. macOS: brew install ffmpeg. "
            "Debian or Ubuntu: sudo apt install ffmpeg.")

    spec = kc.load_spec(args.spec, args.brand)
    style = deep_merge(DEFAULTS, spec)
    if not spec.get("source"):
        die("the spec needs a \"source\": the long recording everything is cut from")
    src = Path(str(spec["source"]))
    if not src.exists():
        die(f"source not found: {src}")
    info = caption_video.probe(src)
    if not info.get("has_audio"):
        die("this source has no audio track. assemble_clip joins segments of speech; "
            "use caption_video.py for silent footage.")
    colour = probe_colour(src)
    print(f"source {src.name}  {info['width']}x{info['height']}  {info['duration']:.2f}s"
          f"  {colour.get('pix_fmt', '?')}  {colour.get('color_transfer', '?')}", flush=True)
    scale_up = max(W / info["width"], H / info["height"])
    if scale_up > 1.5:
        warn(f"the source is {info['width']}x{info['height']}; filling 1080x1920 enlarges "
             f"it {scale_up:.2f}x and crops away most of a horizontal frame. Expect a soft "
             "picture and a tight crop. Film vertically, or accept both")

    spec_dir = Path(args.spec).expanduser().resolve().parent
    pieces = read_pieces(style, spec_dir, info["duration"])
    duplication_report(pieces)
    if args.only:
        pieces = [p for p in pieces if any(o.lower() in p.name.lower() for o in args.only)]
        if not pieces:
            die("--only matched no piece in this spec")

    if args.dry_run:
        for p in pieces:
            print(f"{p.name}: {len(p.segments)} segments  {p.total:.2f}s  "
                  f"{len(p.cards)} cards -> {p.out}")
        return
    failed = 0
    for p in pieces:
        if not render(p, src, style, colour, args):
            failed += 1
    if failed:
        die(f"{failed} of {len(pieces)} pieces did not render")


if __name__ == "__main__":
    main()
