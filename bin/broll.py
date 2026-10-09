#!/usr/bin/env python3
"""
broll.py: the second picture source. Cutaways, picture in picture, lower thirds.

Everything else in this kit has one camera. One speaker, one frame, captions burned
on top. The reference edit Bella sent is not that: it cuts to close-ups of
handwritten notes, document mock-ups, screen recordings and event footage, and it
does it every few seconds. That difference is one feature, not a rebuild, because
assemble_clip.py already composites a PNG over video at a timecode. A CUTAWAY IS
THE SAME MECHANISM WITH A DIFFERENT ASSET. This file is that mechanism.

WHAT IT IS: a second pass over a finished clip. In goes an assembled clip (the
output of bin/assemble_clip.py, or frankly any mp4) plus a JSON list of asset
layers. Out comes the same clip with the layers composited in.

    python3 bin/broll.py out/clip.mp4 --spec specs/example-broll.json

WHY A SEPARATE PASS AND NOT A LAYER TYPE INSIDE assemble_clip.py. Both were on the
table. assemble_clip's own layer list is text: read_cards() requires a "text" key
and draw_layers() rasterises every layer through Pillow, so it cannot carry an
image or a video asset without being changed, and it is owned elsewhere while this
is being written. A pass of its own:

  - works today, on any mp4, with no change to any other file in the kit
  - leaves the speaker's AUDIO BIT IDENTICAL. With no audio layer in the spec the
    base track is stream copied, so there is no second loudness pass and no second
    AAC generation over the voice
  - can be re-run and re-tuned on one clip without re-assembling it, which at
    roughly 1.2x realtime per clip is the expensive half of the chain

WHAT IT COSTS, and this is the honest half. The picture gets a second H.264
generation, because the captions are already burned into the base. At the kit's
delivery bitrate that is cheap, and it is not free. It also means A FULL FRAME
CUTAWAY COVERS THE BURNED IN CAPTIONS for its window. There is no putting a layer
underneath pixels that are already baked. Two answers, both in here:

  - pass --cuts with the cut list that made the clip and this NAMES the caption
    cards each full cutaway would hide, before anything is encoded
  - use a large "pip" instead, which sits above the caption band and leaves the
    words visible

The permanent fix is an asset layer type inside assemble_clip.py stage two, where
the asset would composite before the captions in the same single generation. That
is a change to a file this one is not allowed to touch, and it is reported rather
than made.

THE THREE LAYER TYPES, each an entry in "layers":

  full          the asset replaces the picture for a time range. The speaker keeps
                talking underneath. This is a cutaway.
  pip           the asset sits inset at a corner at a size you choose.
  lower_third   the asset sits across the bottom of the frame. A name card, a
                quote card, a logo lockup, usually a PNG with transparency.

List order is paint order. A pip listed after a full cutaway draws on top of it.

THE FOUR RULES, and how each one was decided here:

1. WHAT HAPPENS TO THE CUTAWAY'S OWN AUDIO. Default "silent": the asset's audio is
   never mapped and the speaker continues unbroken. That is the default because a
   cutaway in this kind of edit is illustration, and silencing the voice mid
   sentence to hear room tone off a stock clip is a mistake, not an option.
   "mix" ducks the asset under the speaker at "mix_gain_db" (default -18 dB) for
   the window only, which is what a screen recording with a beep in it needs.
   There is deliberately NO "replace" mode. Cutting the speaker's audio is a hard
   cut, and a hard cut belongs in the cut list's own segments where the planner
   and check_dupes.py can see it, not hidden in an overlay pass.

2. A CUTAWAY SHORTER THAN ITS WINDOW. Default "hold": the last frame freezes for
   the remainder. The alternative that looks like a bug is doing nothing, which is
   what plain ffmpeg does: the base clip reappears for the last fraction of a
   second and reads as a dropped frame. Measured here on 2026-10-08 with a 1.2s
   asset in a 1.5s window, and the base came back for 0.3s. "loop" repeats the
   asset instead, which suits a texture and not a document. "shrink" shortens the
   window to the asset and reports the new end. A still image has no length, so it
   always fills its window.

3. A CUTAWAY LONGER THAN ITS WINDOW. Default "trim": it plays from "asset_start"
   and stops at the window end. "fit" changes the speed so the whole asset fills
   the window exactly, in either direction, and warns past 2x or under 0.5x,
   because a sped up screen recording reads as a mistake. "fit" refuses to combine
   with audio "mix": re-pitching a voice is not something a cut list should do
   quietly.

4. AN ASSET THAT DOES NOT EXIST. Every asset is resolved, stat'd, probed with
   ffprobe AND decoded for one real frame before a single encode starts, and every
   problem in the spec is collected and printed together rather than one per run.
   Nothing is encoded if anything failed. The one frame decode is in there because
   a path that exists is not an asset that reads: a .heic off an iPhone resolves,
   stats and then cannot be decoded by most ffmpeg builds.

WRONG ASPECT RATIO is the fifth case and it has its own key, "fit":

  cover     (default for full and pip) fills the box and crops the overflow,
            centred by default, movable with focus_x and focus_y. A warning fires
            when covering throws away more than a quarter of the asset, which is
            what a 16:9 screen recording in a 9:16 frame does.
  contain   fits the whole asset inside the box and pads the rest TRANSPARENT, so
            the speaker shows through instead of black bars. Default for
            lower_third, because a card must not be cropped.
  stretch   distorts to fill. It is in here because sometimes a whole 16:9 screen
            has to be legible and nothing else will do. It warns every time.

NOTHING HERE CARRIES ANYBODY'S BRAND. Every size, position, colour and policy is a
value in the spec file. The code's own defaults are plain and documented in
DEFAULTS below, and specs/example-broll.json is the copy-and-change starting point.

USAGE

    # preflight only: read the spec, probe every asset, print the plan, encode nothing
    python3 bin/broll.py out/clip.mp4 --spec specs/example-broll.json --dry-run

    # name the caption cards a full cutaway would cover
    python3 bin/broll.py out/clip.mp4 --spec my-broll.json --cuts work/rl-cuts.json --piece A1

    # render, then pull proof frames from inside and outside the windows
    python3 bin/broll.py out/clip.mp4 --spec my-broll.json --frames 2.0,5.0,9.0

    # a batch is a shell loop. One clip in, one clip out, on purpose: it keeps
    # re-running this safe and keeps the spec readable
    for f in out/rl/*.mp4; do python3 bin/broll.py "$f" --spec broll/$(basename "$f" .mp4).json; done

WHAT IT DOES NOT DO. No motion, no animation, no rounded corners on a pip, no
transitions other than a fade on the asset's own alpha, no automatic choice of
which asset goes where. The cue list that picks assets off the transcript is a
planner job and is not in here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import kit_common as kc  # noqa: E402
from make_clip import AUDIO_BITRATE, VIDEO_BITRATE, ffmpeg_bin, has_filter  # noqa: E402

TOOL = "broll/1.0"
die = kc.die
warn = kc.warn

LAYER_TYPES = ("full", "pip", "lower_third")
AUDIO_MODES = ("silent", "mix")
SHORT_MODES = ("hold", "loop", "shrink")
LONG_MODES = ("trim", "fit")
FIT_MODES = ("cover", "contain", "stretch")

# Nine anchors for a pip. x_pct and y_pct in a layer override the anchor outright.
ANCHORS = ("top-left", "top-center", "top-right",
           "left-center", "center", "right-center",
           "bottom-left", "bottom-center", "bottom-right")

# Covering a box with an asset of another shape throws some of the asset away. Past
# this fraction kept, say so: 0.75 means a quarter of the picture gone, which is
# about what a 16:9 screen recording loses on the way into a 9:16 box.
COVER_WARN_KEPT = 0.75

# Above this the asset starts to read as louder than the room it is sitting in.
MIX_GAIN_WARN_DB = -6.0

# Plain and neutral on purpose. Nobody's look lives in the code: every one of these
# can be set once under "defaults" in the spec or per layer.
DEFAULTS: dict = {
    "audio": "silent",            # see rule 1
    "mix_gain_db": -18.0,
    "short": "hold",              # see rule 2
    "long": "trim",               # see rule 3
    "asset_start": 0.0,           # seconds into the asset to begin
    "opacity": 1.0,
    "fade_ms": 0,                 # 0 is a hard cut, which is the rest of the kit
    "focus_x": 0.5,
    "focus_y": 0.5,
    "pad_color": "black@0.0",     # transparent, so the speaker shows through
    "full": {"fit": "cover"},
    "pip": {"fit": "cover", "width_pct": 0.38, "height_pct": None,
            "position": "top-right", "margin_pct": 0.04},
    "lower_third": {"fit": "contain", "width_pct": 1.0, "height_pct": 0.18,
                    "bottom_pct": 0.12, "margin_pct": 0.0},
    "export": {"video_bitrate": VIDEO_BITRATE, "audio_bitrate": AUDIO_BITRATE,
               "crf": None, "maxrate": "15M", "bufsize": "20M", "preset": "medium"},
}


# ---------------------------------------------------------------------------
# Problems. Collected, not thrown one at a time
# ---------------------------------------------------------------------------


class Problems:
    """Every fault in the spec, reported together, before any encode.

    One error per run is how a buyer ends up running a preflight six times. The
    gate at the end is hard: any error and nothing is encoded.
    """

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.notes: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    def report_and_gate(self) -> None:
        sys.stdout.flush()
        for n in self.notes:
            warn(n)
        sys.stderr.flush()
        if not self.errors:
            return
        print(f"\n  {len(self.errors)} problem(s) in this spec. Nothing was encoded:",
              file=sys.stderr)
        for e in self.errors:
            print(f"    - {e}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Probing
# ---------------------------------------------------------------------------


def ffprobe_bin() -> str:
    found = shutil.which("ffprobe")
    if not found:
        die("ffprobe is not installed, or not on PATH. It ships with ffmpeg.\n"
            "  macOS: brew install ffmpeg      Debian or Ubuntu: sudo apt install ffmpeg")
    return found


def probe_media(path: Path) -> dict:
    """Size, length, frame rate, audio, and whether this is a still picture.

    Returns {"ok": False, "why": ...} rather than exiting, because a bad asset is a
    problem to collect alongside the others, not a reason to stop reading the spec.
    """
    raw = subprocess.run(
        [ffprobe_bin(), "-v", "error", "-show_entries",
         "format=duration,format_name:stream=codec_type,codec_name,width,height,"
         "r_frame_rate,nb_frames:stream_side_data=rotation",
         "-of", "json", str(path)],
        capture_output=True, text=True)
    if raw.returncode != 0:
        return {"ok": False, "why": f"ffprobe cannot read it: {raw.stderr.strip()[:200]}"}
    try:
        info = json.loads(raw.stdout or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "why": "ffprobe returned nothing readable"}
    streams = info.get("streams", []) or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video:
        return {"ok": False, "why": "it has no video or image stream, so there is "
                                    "nothing to show. An audio file is not an asset here"}
    rotation = 0
    for sd in video.get("side_data_list", []) or []:
        if "rotation" in sd:
            rotation = int(sd["rotation"])
    w, h = int(video.get("width") or 0), int(video.get("height") or 0)
    if abs(rotation) in (90, 270):          # ffmpeg autorotates, so size as displayed
        w, h = h, w
    if w <= 0 or h <= 0:
        return {"ok": False, "why": "it has no readable picture size"}
    fmt = info.get("format", {}) or {}
    duration = float(fmt.get("duration") or 0.0)
    frames_raw = str(video.get("nb_frames") or "0")
    frames = int(frames_raw) if frames_raw.isdigit() else 0
    # A still is a still if it has no length or exactly one frame. Said plainly
    # rather than guessed from the codec name, because "mjpeg" is both a photo and
    # a camera's video codec. A layer can override it with "still": true/false.
    still = duration <= 0.05 or frames == 1
    num, _, den = str(video.get("r_frame_rate") or "0/1").partition("/")
    try:
        fps = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    return {"ok": True, "width": w, "height": h, "duration": round(duration, 3),
            "still": still, "fps": round(fps, 3) if fps else 0.0,
            "has_audio": any(s.get("codec_type") == "audio" for s in streams),
            "codec": video.get("codec_name", "?"), "format": fmt.get("format_name", "?")}


def decode_one_frame(path: Path) -> str | None:
    """A path that exists is not an asset that reads.

    An iPhone .heic resolves, stats and then fails at the first encode on most
    ffmpeg builds, which is the worst place to find out. One frame decoded here
    costs a few milliseconds and settles it.
    """
    res = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", str(path),
                          "-frames:v", "1", "-f", "null", "-"],
                         capture_output=True, text=True)
    if res.returncode != 0:
        return (res.stderr.strip().splitlines() or ["ffmpeg could not decode it"])[-1][:200]
    return None


# ---------------------------------------------------------------------------
# The spec
# ---------------------------------------------------------------------------


@dataclass
class Layer:
    index: int
    kind: str
    asset: Path
    start: float
    end: float
    cfg: dict
    media: dict = field(default_factory=dict)
    box: tuple[int, int, int, int] = (0, 0, 0, 0)
    plan: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        return f"layer {self.index} ({self.kind}, {self.asset.name})"

    @property
    def window(self) -> float:
        return round(self.end - self.start, 3)


def merged_defaults(spec: dict) -> dict:
    """Spec "defaults" over the code's plain defaults, one level deep per type."""
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}
    over = spec.get("defaults") or {}
    if not isinstance(over, dict):
        die('"defaults" must be a JSON object')
    for k, v in over.items():
        if v is None:
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    exp = spec.get("export")
    if isinstance(exp, dict):
        out["export"].update({k: v for k, v in exp.items() if v is not None})
    return out


def _num(value, what: str, probs: Problems, lo: float | None = None,
         hi: float | None = None, default: float | None = None) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        probs.error(f"{what} must be a number, got {value!r}")
        return default if default is not None else 0.0
    if lo is not None and f < lo or hi is not None and f > hi:
        probs.error(f"{what} must be between {lo} and {hi}, got {f}")
        return default if default is not None else (lo if lo is not None else f)
    return f


def read_layers(spec: dict, spec_dir: Path, base: dict, probs: Problems) -> list[Layer]:
    raw_layers = spec.get("layers")
    if not isinstance(raw_layers, list) or not raw_layers:
        die('the spec needs a non-empty "layers" list. One entry per cutaway, pip or '
            'lower third. specs/example-broll.json has one of each.')
    base_len = base["duration"]
    defaults = merged_defaults(spec)
    layers: list[Layer] = []
    for i, raw in enumerate(raw_layers, start=1):
        if not isinstance(raw, dict):
            probs.error(f"layer {i} must be a JSON object")
            continue
        kind = str(raw.get("type") or raw.get("layer") or "").strip().lower().replace("-", "_")
        if kind in ("lowerthird", "third"):
            kind = "lower_third"
        if kind in ("cutaway", "broll", "b_roll"):
            kind = "full"
        if kind not in LAYER_TYPES:
            probs.error(f"layer {i} type {raw.get('type')!r} is not one of "
                        f"{', '.join(LAYER_TYPES)}")
            continue
        asset_ref = str(raw.get("asset") or raw.get("file") or "").strip()
        if not asset_ref:
            probs.error(f"layer {i} ({kind}) needs an \"asset\": the picture or video to show")
            continue
        asset = Path(kc.resolve_input(asset_ref, spec_dir)).expanduser()
        if "start" not in raw or "end" not in raw:
            probs.error(f"layer {i} ({asset.name}) needs \"start\" and \"end\" in seconds "
                        "of the finished clip")
            continue
        cfg = dict(defaults)
        cfg.update(dict(defaults.get(kind) or {}))
        for key in ("audio", "mix_gain_db", "short", "long", "asset_start", "opacity",
                    "fade_ms", "focus_x", "focus_y", "pad_color", "fit", "width_pct",
                    "height_pct", "bottom_pct", "margin_pct", "position", "x_pct",
                    "y_pct", "still", "note"):
            if key in raw and raw[key] is not None:
                cfg[key] = raw[key]

        start = _num(raw["start"], f"layer {i} start", probs, lo=0.0)
        end = _num(raw["end"], f"layer {i} end", probs, lo=0.0)
        layer = Layer(index=i, kind=kind, asset=asset, start=round(start, 3),
                      end=round(end, 3), cfg=cfg)

        if end <= start:
            probs.error(f"{layer.label} ends at {end}s, at or before its start {start}s")
            continue
        if start >= base_len:
            probs.error(f"{layer.label} starts at {start:.2f}s and the clip is only "
                        f"{base_len:.2f}s long. Nothing would be drawn")
            continue
        if end > base_len + 0.05:
            probs.note(f"{layer.label} runs to {end:.2f}s, past the end of the clip "
                       f"({base_len:.2f}s), clamped")
            layer.end = round(base_len, 3)

        for key, lo, hi in (("opacity", 0.0, 1.0), ("focus_x", 0.0, 1.0),
                            ("focus_y", 0.0, 1.0), ("fade_ms", 0.0, 5000.0),
                            ("asset_start", 0.0, 1e6)):
            cfg[key] = _num(cfg.get(key), f"{layer.label} {key}", probs, lo, hi,
                            default=DEFAULTS[key])
        if str(cfg.get("audio")) not in AUDIO_MODES:
            probs.error(f"{layer.label} audio must be one of {', '.join(AUDIO_MODES)}, "
                        f"got {cfg.get('audio')!r}. There is no \"replace\": silencing the "
                        "speaker is a hard cut and belongs in the cut list's segments")
        if str(cfg.get("short")) not in SHORT_MODES:
            probs.error(f"{layer.label} short must be one of {', '.join(SHORT_MODES)}")
        if str(cfg.get("long")) not in LONG_MODES:
            probs.error(f"{layer.label} long must be one of {', '.join(LONG_MODES)}")
        if str(cfg.get("fit")) not in FIT_MODES:
            probs.error(f"{layer.label} fit must be one of {', '.join(FIT_MODES)}")
        if kind == "pip":
            pos = str(cfg.get("position", "top-right")).lower().replace("_", "-")
            if pos not in ANCHORS and "x_pct" not in cfg:
                probs.error(f"{layer.label} position {cfg.get('position')!r} is not one of "
                            f"{', '.join(ANCHORS)}. Or give x_pct and y_pct instead")
            cfg["position"] = pos

        # The asset itself, before any encode: exists, has bytes, probes, decodes.
        if not asset.exists():
            probs.error(f"{layer.label} asset does not exist: {asset}\n"
                        f"        (the spec says {asset_ref!r}, looked for next to the "
                        "spec and then where you ran the command)")
            layers.append(layer)
            continue
        if asset.is_dir():
            probs.error(f"{layer.label} asset is a folder, not a file: {asset}")
            layers.append(layer)
            continue
        if asset.stat().st_size == 0:
            probs.error(f"{layer.label} asset is a zero byte file: {asset}")
            layers.append(layer)
            continue
        media = probe_media(asset)
        if not media.get("ok"):
            probs.error(f"{layer.label} asset cannot be used: {media.get('why')}\n"
                        f"        {asset}")
            layers.append(layer)
            continue
        bad = decode_one_frame(asset)
        if bad:
            probs.error(f"{layer.label} asset probes but will not decode: {bad}\n"
                        f"        {asset}\n"
                        "        An iPhone .heic does this. Export it as PNG or JPEG first")
            layers.append(layer)
            continue
        if "still" in cfg:
            media["still"] = bool(cfg["still"])
        layer.media = media
        layers.append(layer)
    return layers


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def even(n: float) -> int:
    """Even pixels. Odd overlay offsets and odd boxes land between chroma samples."""
    return max(2, int(round(n / 2.0)) * 2)


def box_for(layer: Layer, W: int, H: int, probs: Problems) -> tuple[int, int, int, int]:
    cfg = layer.cfg
    if layer.kind == "full":
        return 0, 0, even(W), even(H)

    margin = even(float(cfg.get("margin_pct", 0.0) or 0.0) * W)
    if layer.kind == "pip":
        bw = even(float(cfg.get("width_pct", 0.38)) * W)
        if cfg.get("height_pct"):
            bh = even(float(cfg["height_pct"]) * H)
        else:
            # Keep the asset's own shape, which is what stops a pip looking stretched
            aw, ah = layer.media.get("width", 16), layer.media.get("height", 9)
            bh = even(bw * (ah / max(1, aw)))
        pos = str(cfg.get("position", "top-right"))
        if pos == "center":
            pos = "center-center"
        row, _, col = pos.partition("-")
        xs = {"left": margin, "center": (W - bw) // 2, "right": W - bw - margin}
        ys = {"top": margin, "center": (H - bh) // 2, "bottom": H - bh - margin}
        x = xs.get(col, (W - bw) // 2)
        y = ys.get(row, (H - bh) // 2)
    else:   # lower_third
        bw = even(float(cfg.get("width_pct", 1.0)) * W - 2 * margin)
        bh = even(float(cfg.get("height_pct", 0.18)) * H)
        x = (W - bw) // 2
        y = H - bh - even(float(cfg.get("bottom_pct", 0.12)) * H)

    if "x_pct" in cfg and cfg["x_pct"] is not None:
        x = int(round(float(cfg["x_pct"]) * W))
    if "y_pct" in cfg and cfg["y_pct"] is not None:
        y = int(round(float(cfg["y_pct"]) * H))
    x, y, bw, bh = int(x), int(y), int(bw), int(bh)
    if bw < 16 or bh < 16:
        probs.error(f"{layer.label} works out to a {bw}x{bh} box, too small to see. "
                    "Check width_pct and height_pct")
    if x < 0 or y < 0 or x + bw > W or y + bh > H:
        probs.error(f"{layer.label} box {bw}x{bh} at {x},{y} falls outside the "
                    f"{W}x{H} frame. Reduce width_pct, height_pct or margin_pct")
    return x, y, bw, bh


def fit_steps(layer: Layer, bw: int, bh: int, probs: Problems) -> list[str]:
    cfg = layer.cfg
    fit = str(cfg.get("fit"))
    aw, ah = layer.media.get("width", bw), layer.media.get("height", bh)
    if fit == "stretch":
        probs.note(f"{layer.label} fit is \"stretch\", so the asset is distorted from "
                   f"{aw}x{ah} into {bw}x{bh}. It shows everything and it is visible")
        return [f"scale={bw}:{bh}:flags=lanczos", "setsar=1"]
    if fit == "contain":
        return [f"scale={bw}:{bh}:force_original_aspect_ratio=decrease:flags=lanczos",
                f"pad={bw}:{bh}:(ow-iw)/2:(oh-ih)/2:color={cfg.get('pad_color')}",
                "setsar=1"]
    ar_a, ar_b = aw / max(1, ah), bw / max(1, bh)
    kept = min(ar_a / ar_b, ar_b / ar_a)
    if kept < COVER_WARN_KEPT:
        probs.note(f"{layer.label} is {aw}x{ah} and the box is {bw}x{bh}, so covering it "
                   f"crops away {(1 - kept) * 100:.0f}% of the asset. "
                   "\"fit\": \"contain\" shows all of it on a transparent pad instead")
    fx = float(cfg.get("focus_x", 0.5))
    fy = float(cfg.get("focus_y", 0.5))
    return [f"scale={bw}:{bh}:force_original_aspect_ratio=increase:flags=lanczos",
            f"crop={bw}:{bh}:x='(iw-ow)*{fx:.3f}':y='(ih-oh)*{fy:.3f}'", "setsar=1"]


# ---------------------------------------------------------------------------
# Timing: the three policies, worked out before anything is built
# ---------------------------------------------------------------------------


def plan_timing(layer: Layer, fps: float, probs: Problems) -> None:
    """Fills layer.plan with take, hold, speed, loop and the final window."""
    cfg = layer.cfg
    media = layer.media
    win = layer.window
    if media.get("still"):
        layer.plan = {"take": None, "hold": 0.0, "speed": 1.0, "loop": False,
                      "why": "still image, fills its window"}
        return
    frame = 1.0 / max(1.0, fps)
    asset_start = float(cfg.get("asset_start", 0.0))
    dur = float(media.get("duration", 0.0))
    if asset_start >= dur:
        probs.error(f"{layer.label} asset_start is {asset_start:.2f}s and the asset is "
                    f"only {dur:.2f}s long. There would be nothing left to play")
        layer.plan = {"take": win, "hold": 0.0, "speed": 1.0, "loop": False, "why": "unusable"}
        return
    available = round(dur - asset_start, 3)

    if str(cfg.get("long")) == "fit":
        if str(cfg.get("audio")) == "mix":
            probs.error(f"{layer.label} asks for \"long\": \"fit\" and \"audio\": \"mix\" "
                        "together. Changing the speed re-pitches the asset's audio, so one "
                        "of the two has to go")
        speed = available / win if win > 0 else 1.0
        if speed > 2.0 or speed < 0.5:
            probs.note(f"{layer.label} fit means playing {available:.2f}s in {win:.2f}s, "
                       f"which is {speed:.2f}x. Past 2x or under 0.5x it reads as a mistake")
        layer.plan = {"take": available, "hold": 0.0, "speed": round(speed, 6), "loop": False,
                      "why": f"fit: {available:.2f}s of asset played at {speed:.2f}x"}
        return

    if available > win + frame:
        layer.plan = {"take": win, "hold": 0.0, "speed": 1.0, "loop": False,
                      "why": f"trim: {available:.2f}s available, {win:.2f}s used from "
                             f"{asset_start:.2f}s in"}
        return
    if available >= win - frame:
        layer.plan = {"take": win, "hold": 0.0, "speed": 1.0, "loop": False,
                      "why": "asset length matches the window"}
        return

    short = str(cfg.get("short"))
    deficit = round(win - available, 3)
    if short == "loop":
        layer.plan = {"take": win, "hold": 0.0, "speed": 1.0, "loop": True,
                      "why": f"loop: {available:.2f}s asset repeated to fill {win:.2f}s"}
    elif short == "shrink":
        layer.end = round(layer.start + available, 3)
        layer.plan = {"take": available, "hold": 0.0, "speed": 1.0, "loop": False,
                      "why": f"shrink: window cut from {win:.2f}s to {available:.2f}s, "
                             f"now ends at {layer.end:.2f}s"}
        probs.note(f"{layer.label} window shortened to the asset: ends at "
                   f"{layer.end:.2f}s instead of {layer.start + win:.2f}s")
    else:
        layer.plan = {"take": available, "hold": deficit, "speed": 1.0, "loop": False,
                      "why": f"hold: {available:.2f}s asset, last frame held "
                             f"{deficit:.2f}s to fill {win:.2f}s"}


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------


def build_cmd(base_path: Path, base: dict, layers: list[Layer], spec: dict,
              out: Path) -> list[str]:
    fps = base["fps"] or 30.0
    total = base["duration"]
    export = merged_defaults(spec)["export"]
    args: list[str] = ["-i", str(base_path)]
    chain: list[str] = ["[0:v]format=yuva420p[v0]"]
    audio_bits: list[str] = []
    mixes: list[str] = []

    for n, layer in enumerate(layers):
        idx = n + 1
        plan = layer.plan
        still = bool(layer.media.get("still"))
        if still:
            # A still is read ONCE, as a plain input, and stretched in the filter graph
            # below. It is not read with "-loop 1".
            #
            # WHY NOT -loop, measured on 2026-10-08: -loop belongs to the image2 family
            # of demuxers. Hand it a real iPhone .heic, which arrives through the mov
            # demuxer, and ffmpeg exits 8 with "Option loop not found" AFTER preflight
            # has passed the asset, because the file probes and decodes perfectly well.
            # That is the one failure this file promises not to have. Stretching the
            # frame in the filter graph instead works whatever the container is.
            args += ["-i", str(layer.asset)]
        else:
            if plan["loop"]:
                args += ["-stream_loop", "-1"]
            args += ["-ss", f"{float(layer.cfg.get('asset_start', 0.0)):.3f}"]
            args += ["-t", f"{plan['take']:.3f}", "-i", str(layer.asset)]

        x, y, bw, bh = layer.box
        steps = [f"[{idx}:v]format=rgba"]
        if still:
            # exactly one frame, then cloned across the whole clip. The overlay gate
            # below decides when it is actually visible, the same way assemble_clip.py
            # treats a caption PNG.
            steps += ["trim=end_frame=1", "setpts=PTS-STARTPTS", f"fps={fps:g}",
                      f"tpad=stop_mode=clone:stop_duration={total:.3f}"]
        else:
            steps.append(f"fps={fps:g}")
        steps.append("setsar=1")
        if plan["speed"] != 1.0:
            # setpts scales the timestamps, fps resamples back to the delivery rate
            steps.append(f"setpts=PTS/{plan['speed']:.6f}")
            steps.append(f"fps={fps:g}")
        steps += layer.plan["fit_steps"]
        opacity = float(layer.cfg.get("opacity", 1.0))
        if opacity < 1.0:
            steps.append(f"colorchannelmixer=aa={opacity:.3f}")
        if plan["hold"] > 0:
            # Freeze the last frame. Without this the base clip reappears for the
            # remainder of the window and reads as a dropped frame.
            steps.append(f"tpad=stop_mode=clone:stop_duration={plan['hold']:.3f}")
        if not still and layer.start > 0:
            # Shift the asset onto the clip's clock, so every time below is a time in
            # the finished clip and not a time inside the asset. The padded frames
            # are never drawn: the overlay gate is off before layer.start.
            steps.append(f"tpad=start_duration={layer.start:.3f}:start_mode=add:color=black")
        fade = float(layer.cfg.get("fade_ms", 0)) / 1000.0
        if fade > 0:
            # After the shift, so these are clip times. Measured on 2026-10-08: with
            # the fades before the shift the layer stayed invisible for its first
            # second, because the fade was running on the asset's own clock.
            steps.append(f"fade=t=in:st={layer.start:.3f}:d={fade:.3f}:alpha=1")
            steps.append(f"fade=t=out:st={max(0.0, layer.end - fade):.3f}:"
                         f"d={fade:.3f}:alpha=1")
        chain.append(",".join(steps) + f"[l{n}]")
        # gte/lt, not between(): between() is inclusive at both ends, so on the frame
        # where one layer ends and the next begins both would be drawn.
        chain.append(f"[v{n}][l{n}]overlay={x}:{y}:format=auto:eof_action=pass:"
                     f"repeatlast=0:enable='gte(t,{layer.start:.3f})*"
                     f"lt(t,{layer.end:.3f})'[v{n + 1}]")

        if str(layer.cfg.get("audio")) == "mix" and layer.media.get("has_audio") and not still:
            gain = float(layer.cfg.get("mix_gain_db", -18.0))
            delay = int(round(layer.start * 1000))
            audio_bits.append(f"[{idx}:a]volume={gain:.1f}dB,aresample=48000,"
                              f"adelay={delay}:all=1[am{idx}]")
            mixes.append(f"[am{idx}]")

    chain.append(f"[v{len(layers)}]format=yuv420p,setsar=1[vout]")

    cmd = [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error"] + args
    if mixes:
        # Mixing re-encodes the speaker's audio, which is why it is not the default.
        # normalize=0 so the base track keeps the level assemble_clip set, and
        # duration=first so the output is as long as the clip.
        chain.append("[0:a]aresample=48000[a0]")
        chain.append("[a0]" + "".join(mixes) +
                     f"amix=inputs={len(mixes) + 1}:normalize=0:dropout_transition=0:"
                     "duration=first[aout]")
        audio = ["-map", "[aout]", "-c:a", "aac", "-b:a", str(export["audio_bitrate"]),
                 "-ar", "48000", "-ac", "2"]
    elif base["has_audio"]:
        # The speaker's track, stream copied. Bit identical, no second AAC pass.
        audio = ["-map", "0:a:0", "-c:a", "copy"]
    else:
        audio = ["-an"]

    cmd += ["-filter_complex", ";".join(chain + audio_bits), "-map", "[vout]"] + audio
    video = ["-c:v", "libx264", "-profile:v", "high", "-preset", str(export["preset"]),
             "-pix_fmt", "yuv420p", "-r", f"{fps:g}", "-movflags", "+faststart"]
    if export.get("crf") is not None:
        video += ["-crf", str(int(export["crf"]))]
    else:
        video += ["-b:v", str(export["video_bitrate"]), "-maxrate", str(export["maxrate"]),
                  "-bufsize", str(export["bufsize"])]
    return cmd + video + ["-t", f"{total:.3f}", str(out)]


# ---------------------------------------------------------------------------
# The caption clash, named rather than guessed
# ---------------------------------------------------------------------------


def map_to_clip(t: float, segs: list[tuple[float, float]]) -> float | None:
    """Recording seconds to finished-clip seconds.

    Eight lines, and they are here rather than imported from assemble_clip.py on
    purpose: this pass runs on any mp4, including one that tool never touched, so
    it does not depend on it.
    """
    off = 0.0
    for a, b in segs:
        if a - 1e-6 <= t <= b + 1e-6:
            return round(off + max(0.0, min(b, t) - a), 3)
        off += b - a
    return None


def caption_clash(layers: list[Layer], cuts_path: Path, piece_name: str | None,
                  base_path: Path) -> None:
    """Which caption cards would a full frame cutaway hide. Named, before the encode."""
    data = kc.read_json(cuts_path, "cut list")
    pieces = data.get("pieces") or [data]
    stem = base_path.stem
    piece = None
    if piece_name:
        piece = next((p for p in pieces if piece_name.lower() in
                      str(p.get("piece") or p.get("name") or "").lower()), None)
        if piece is None:
            die(f"--piece {piece_name!r} matched no piece in {cuts_path.name}. "
                "Pieces in it: " + ", ".join(str(p.get('piece') or '?') for p in pieces))
    if piece is None:
        piece = next((p for p in pieces if str(p.get("filename") or "").replace(".mp4", "")
                      == stem), None)
    if piece is None and len(pieces) == 1:
        piece = pieces[0]
    if piece is None:
        warn(f"{cuts_path.name} holds {len(pieces)} pieces and none of their filenames "
             f"is {stem!r}. Name one with --piece to get the caption check")
        return
    cards = piece.get("cards") or piece.get("caption_cards") or []
    if not cards:
        print(f"  caption check: piece {piece.get('piece', '?')} has no cards in the "
              "cut list, so nothing can be covered")
        return
    times = str(piece.get("times") or data.get("times") or "clip").lower()
    segs = [(float(s["start"]), float(s["end"])) for s in piece.get("segments") or []
            if isinstance(s, dict) and "start" in s and "end" in s]
    placed: list[tuple[float, float, str]] = []
    for c in cards:
        try:
            a, b = float(c["start"]), float(c["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if times == "source":
            ma, mb = map_to_clip(a, segs), map_to_clip(b, segs)
            if ma is None:
                continue
            a, b = ma, mb if mb is not None else ma + (b - a)
        placed.append((a, b, str(c.get("text", "")).strip()))
    print(f"  caption check against {cuts_path.name}, piece "
          f"{piece.get('piece', '?')}: {len(placed)} cards on this clip's clock", flush=True)
    clean = True
    for layer in layers:
        if layer.kind != "full":
            continue
        hit = [t for a, b, t in placed
               if min(b, layer.end) - max(a, layer.start) > 0.08]
        if hit:
            clean = False
            warn(f"{layer.label} covers the whole frame from {layer.start:.2f}s to "
                 f"{layer.end:.2f}s, which hides {len(hit)} burned in caption card(s): "
                 + "; ".join(repr(h) for h in hit[:6])
                 + ("; ..." if len(hit) > 6 else "")
                 + "\n        Move the window, or use a large \"pip\" instead, which "
                   "sits above the caption band")
    if clean:
        print("    no full frame cutaway covers a caption card")


# ---------------------------------------------------------------------------
# Output checks, fingerprint, proof frames
# ---------------------------------------------------------------------------


def require_real_output(path: Path, expected: float) -> dict:
    """A file that exists is not a render that worked. ffmpeg can return 0 on nothing."""
    if not path.exists():
        die(f"ffmpeg said it succeeded and wrote no file at all: {path}")
    size = path.stat().st_size
    if size == 0:
        die(f"ffmpeg wrote a ZERO BYTE file at {path} and returned success. Nothing was "
            "rendered. The usual cause is a filter label that never reached the output.")
    info = probe_media(path)
    if not info.get("ok") or not info.get("duration"):
        die(f"{path.name} has no readable duration, so it is not a usable video")
    drift = abs(info["duration"] - expected)
    if drift > 0.5:
        die(f"the clip going in is {expected:.2f}s and the file coming out is "
            f"{info['duration']:.2f}s, {drift:.2f}s out. An overlay pass must not change "
            "the length, so this is a failure, not a warning.")
    if drift > 0.05:
        warn(f"{path.name} is {info['duration']:.2f}s against {expected:.2f}s in "
             f"({drift:.2f}s of frame rounding)")
    return info


def fingerprint(base_path: Path, layers: list[Layer], spec: dict) -> str:
    h = hashlib.sha256()
    h.update(TOOL.encode())
    for p in [base_path] + [l.asset for l in layers]:
        try:
            st = p.stat()
            h.update(f"{p}|{st.st_size}|{int(st.st_mtime)}".encode())
        except OSError:
            h.update(f"{p}|missing".encode())
    h.update(json.dumps([{"kind": l.kind, "start": l.start, "end": l.end,
                          "box": l.box, "cfg": {k: v for k, v in l.cfg.items()
                                                if not isinstance(v, dict)}}
                         for l in layers], sort_keys=True, default=str).encode())
    h.update(json.dumps(merged_defaults(spec), sort_keys=True, default=str).encode())
    return h.hexdigest()[:16]


def mean_rgb(path: Path, t: float) -> str:
    """The average colour of one frame, as six hex digits.

    A cheap, printable proof that the picture at this second is not the picture at
    that second. It is a number in a report rather than a claim in a sentence.
    """
    res = subprocess.run([ffmpeg_bin(), "-v", "error", "-ss", f"{t:.3f}", "-i", str(path),
                          "-frames:v", "1", "-vf", "scale=1:1,format=rgb24",
                          "-f", "rawvideo", "-"], capture_output=True)
    if res.returncode != 0 or len(res.stdout) < 3:
        return "??????"
    return res.stdout[:3].hex()


def pull_frames(path: Path, times: list[float], out_dir: Path,
                layers: list[Layer]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"  proof frames in {out_dir}")
    for t in times:
        png = out_dir / f"{path.stem}-t{str(t).replace('.', 'p')}.png"
        res = subprocess.run([ffmpeg_bin(), "-y", "-v", "error", "-ss", f"{t:.3f}",
                              "-i", str(path), "-frames:v", "1", str(png)],
                             capture_output=True, text=True)
        if res.returncode != 0:
            warn(f"could not pull a frame at {t:.2f}s: {res.stderr.strip()[:160]}")
            continue
        inside = [l.label for l in layers if l.start <= t < l.end]
        where = ("inside " + ", ".join(inside)) if inside else "outside every layer window"
        print(f"    {t:7.3f}s  mean {mean_rgb(path, t)}  {where}  {png.name}")


# ---------------------------------------------------------------------------


def proof_frames(out: Path, args, layers: list[Layer]) -> None:
    if not args.frames:
        return
    try:
        times = [float(t) for t in str(args.frames).split(",") if t.strip()]
    except ValueError:
        die("--frames takes comma separated seconds, for example 2.0,5.0,9.0")
    fdir = (Path(kc.resolve_output(args.frames_dir, Path.cwd())) if args.frames_dir
            else out.parent / "frames")
    pull_frames(out, times, fdir, layers)


def shell(cmd: list[str]) -> str:
    return " ".join(f'"{c}"' if (" " in c or "[" in c or "'" in c) else c for c in cmd)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="A second picture source for a finished clip: full frame cutaways, "
                    "picture in picture, lower thirds. The speaker's audio carries on "
                    "underneath and is stream copied unless a layer asks to be mixed.",
        epilog="The spec shape, with one of each layer type and a note on every value, "
               "is specs/example-broll.json. Run with --dry-run first: it probes and "
               "decodes every asset, prints the plan and encodes nothing.")
    ap.add_argument("clip", nargs="?", help="the finished clip to lay assets over. "
                                            "Or put \"base\" in the spec")
    ap.add_argument("--spec", required=True, help="the JSON asset layer list")
    ap.add_argument("--out", help="where the new file goes. Default: the clip's name "
                                  "with -broll before .mp4")
    ap.add_argument("--cuts", help="the cut list this clip was assembled from, so a full "
                                   "frame cutaway can name the caption cards it hides")
    ap.add_argument("--piece", help="which piece of that cut list this clip is")
    ap.add_argument("--frames", help="comma separated seconds to pull proof frames at "
                                     "after rendering, for example 2.0,5.0,9.0")
    ap.add_argument("--frames-dir", help="where the proof frames go. Default: a frames "
                                         "folder beside the output")
    ap.add_argument("--dry-run", action="store_true",
                    help="read the spec, check every asset, print the plan, encode nothing")
    ap.add_argument("--check", action="store_true", help="print the ffmpeg command and stop")
    ap.add_argument("--force", action="store_true", help="re-render even if the output is current")
    args = ap.parse_args()

    spec_path = Path(args.spec).expanduser()
    spec = kc.read_json(spec_path, "broll spec")
    spec_dir = spec_path.resolve().parent

    base_ref = args.clip or spec.get("base") or spec.get("clip")
    if not base_ref:
        die("name the finished clip to work on, either as the first argument or as "
            '"base" in the spec')
    base_path = Path(kc.resolve_input(str(base_ref), spec_dir)).expanduser()
    if not base_path.exists():
        die(f"clip not found: {base_path}")

    needed = ["overlay", "scale", "crop", "pad", "tpad", "format", "setpts", "fps"]
    thin = [f for f in needed if not has_filter(f)]
    if thin:
        die(f"this ffmpeg build is missing: {', '.join(thin)}.\n"
            "  Install a full ffmpeg build. macOS: brew install ffmpeg. "
            "Debian or Ubuntu: sudo apt install ffmpeg.")

    base = probe_media(base_path)
    if not base.get("ok"):
        die(f"cannot read {base_path}: {base.get('why')}")
    W, H = base["width"], base["height"]
    print(f"clip {base_path.name}  {W}x{H}  {base['duration']:.2f}s  "
          f"{base['fps']:g} fps  " + ("audio" if base["has_audio"] else "no audio"),
          flush=True)

    probs = Problems()
    layers = read_layers(spec, spec_dir, base, probs)
    for layer in layers:
        if not layer.media:
            continue                      # already an error, do not pile more on it
        layer.box = box_for(layer, W, H, probs)
        plan_timing(layer, base["fps"] or 30.0, probs)
        layer.plan["fit_steps"] = fit_steps(layer, layer.box[2], layer.box[3], probs)
        if str(layer.cfg.get("audio")) == "mix":
            if layer.media.get("still"):
                probs.note(f"{layer.label} asks to mix audio and a still image has none, "
                           "so the speaker continues alone")
            elif not layer.media.get("has_audio"):
                probs.note(f"{layer.label} asks to mix audio and the asset has no audio "
                           "track, so the speaker continues alone")
            elif float(layer.cfg.get("mix_gain_db", -18.0)) > MIX_GAIN_WARN_DB:
                probs.note(f"{layer.label} mixes its audio at "
                           f"{float(layer.cfg['mix_gain_db']):+.1f} dB, which can sit on "
                           "top of the speaker and can clip the sum. -18 is a bed")

    fulls = [l for l in layers if l.kind == "full"]
    for a, b in ((x, y) for i, x in enumerate(fulls) for y in fulls[i + 1:]):
        if min(a.end, b.end) - max(a.start, b.start) > 0.04:
            probs.note(f"{a.label} and {b.label} are both full frame and overlap. "
                       "The later one in the list is on top, so the earlier one is "
                       "partly invisible")
    probs.report_and_gate()

    print(f"  {len(layers)} layer(s), painted in list order:", flush=True)
    for layer in layers:
        x, y, bw, bh = layer.box
        m = layer.media
        length = "still" if m.get("still") else f"{m.get('duration', 0.0):.2f}s"
        print(f"    {layer.index}. {layer.kind:11} {layer.start:6.2f}s to {layer.end:6.2f}s "
              f"({layer.window:5.2f}s)  box {bw}x{bh} at {x},{y}  "
              f"asset {m.get('width')}x{m.get('height')} {m.get('codec')} {length}  "
              f"fit {layer.cfg.get('fit')}  audio {layer.cfg.get('audio')}")
        sys.stdout.flush()
        print(f"       {layer.plan['why']}  {layer.asset}")

    if args.cuts:
        caption_clash(layers, Path(args.cuts).expanduser(), args.piece, base_path)
    elif fulls:
        warn(f"{len(fulls)} full frame cutaway(s) will cover any burned in caption inside "
             "their window. Pass --cuts with the cut list that made this clip and the "
             "cards get named")

    out = Path(kc.resolve_output(str(args.out), Path.cwd())) if args.out else (
        Path(kc.resolve_output(str(spec["out"]), spec_dir)) if spec.get("out")
        else base_path.with_name(f"{base_path.stem}-broll.mp4"))
    if out.resolve() == base_path.resolve():
        die("the output is the same file as the clip going in. An overlay pass must not "
            "overwrite its own source: nothing would be recoverable if it failed halfway")

    if args.dry_run:
        print(f"  dry run: every asset read, nothing encoded. Would write {out}")
        return

    cmd = build_cmd(base_path, base, layers, spec, out)
    if args.check:
        # Before the "already current" check on purpose: asking to see the command is
        # asking to see the command, whether or not the file happens to be up to date.
        print(shell(cmd))
        return

    fp = fingerprint(base_path, layers, spec)
    side = out.with_name(out.name + ".broll.json")
    if not args.force and out.exists() and out.stat().st_size > 0 and side.exists():
        try:
            if json.loads(side.read_text()).get("fingerprint") == fp:
                print(f"  already current, skipped ({out.name}). --force re-renders")
                proof_frames(out, args, layers)
                return
        except (json.JSONDecodeError, OSError):
            pass

    out.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        die(f"the overlay pass failed (ffmpeg exit {res.returncode})\n"
            f"{res.stderr.strip()[:3000]}")
    info = require_real_output(out, base["duration"])
    side.write_text(json.dumps({
        "tool": TOOL, "fingerprint": fp, "written": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "base": str(base_path), "spec": str(spec_path),
        "layers": [{"type": l.kind, "asset": str(l.asset), "start": l.start,
                    "end": l.end, "box": list(l.box), "plan": l.plan["why"]}
                   for l in layers],
        "audio": ("mixed" if any(str(l.cfg.get("audio")) == "mix" and
                                 l.media.get("has_audio") for l in layers)
                  else "base track stream copied"),
        "duration_out": round(info["duration"], 3),
    }, indent=2, default=str) + "\n")
    print(f"  wrote {out}")
    print(f"    {info['width']}x{info['height']}  {info['duration']:.2f}s  "
          f"{out.stat().st_size / 1_000_000:.2f} MB  {len(layers)} layers  "
          f"{time.time() - started:.1f}s")

    proof_frames(out, args, layers)


if __name__ == "__main__":
    main()
