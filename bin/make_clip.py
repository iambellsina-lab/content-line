#!/usr/bin/env python3
"""
make_clip.py: turn a text spec into a finished vertical clip.

Many ffmpeg builds (including common Homebrew ones) have no drawtext, no subtitles
filter, no libass and no libfreetype, so ffmpeg cannot draw a character. This script
works anywhere because it does not ask it to: text is drawn with Pillow into
transparent PNGs, and ffmpeg only composites those PNGs over the background.

Usage (from the kit folder):
    python3 bin/make_clip.py specs/example-clip.json
    python3 bin/make_clip.py specs/example-clip.json --brand specs/yourbrand.json
    python3 bin/make_clip.py specs/example-brand.json        # preview a brand file on its own
    python3 bin/make_clip.py specs/example-clip.json --stills   # numbered PNGs for a carousel
    python3 bin/make_clip.py specs/example-clip.json --check    # print the ffmpeg command, stop
    python3 bin/make_clip.py specs/example-clip.json --which-font

On Windows use `python` in place of `python3`.

The look (font, colours, background, shadow, handle) comes from a brand file:
copy specs/example-brand.json, fill it in, and point at it with --brand or with
"brand" inside the spec. With no brand file the clip is plain white text on dark grey.

Spec (JSON). Only "cards" and "out" are required.

{
  "brand": "example-brand.json",          # optional, same as --brand
  "out": "out/first.mp4",                 # relative to the folder you run from
  "duration": 12.0,                       # omitted: taken from the last card
  "audio": "voice.mp3",                   # optional
  "music": "bed.mp3",                     # optional, ducked under voice
  "cards": [
    {"text": "I say yes", "start": 0.0, "end": 1.1},
    {"text": "to everything", "start": 1.1, "end": 2.2, "accent": ["everything"]}
  ]
}

Any brand key may also be written directly in the spec, and then wins over the brand
file. A relative path (font, audio, music, background image) is looked for next to
the file that names it, then in the folder you ran from.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit_common as kc  # noqa: E402  (must come before PIL: it can re-run us inside the kit .venv)
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

# ---------------------------------------------------------------------------
# Platform numbers. These are delivery choices for vertical short-form video,
# not brand choices. Edit them here if you need different ones.
# ---------------------------------------------------------------------------

W, H = 1080, 1920           # vertical canvas
FPS = 30                    # delivery frame rate
SAFE_TOP = 420              # the centre 1080x1080 square starts here
SAFE_BOTTOM = H - 420       # and ends here
SAFE_SIDE = 96              # breathing room so type never touches the edge
LUFS = -14.0                # integrated loudness
TRUE_PEAK = -1.0            # dBTP
AUDIO_BITRATE = "192k"
VIDEO_BITRATE = "12M"       # inside the 10 to 15 Mbps band
MUSIC_DUCK_DB = -15         # inside the 12 to 18 dB band

WORDS_PER_SECOND = 2.6      # unhurried speech, for estimating timings
MAX_WORDS_PER_CARD = 4      # the eye reads a card in one fixation


# ---------------------------------------------------------------------------


@dataclass
class Card:
    text: str
    start: float
    end: float
    accent: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start


die = kc.die
warn = kc.warn


def hex_rgb(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6:
        die(f"bad colour {value!r}, expected #RRGGBB")
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def pick_font(path: str | None = None) -> str:
    """The font to draw with: the one named, else the best this machine has. Dies with
    a message that says what to install if there is none."""
    try:
        return kc.find_font(path)
    except kc.FontNotFound as exc:
        die(str(exc))
    return ""  # unreachable, keeps the type checker quiet


def ffmpeg_bin() -> str:
    found = shutil.which("ffmpeg")
    if not found:
        die("ffmpeg is not installed, or not on PATH.\n"
            "  macOS: brew install ffmpeg      Windows: winget install ffmpeg\n"
            "  Debian or Ubuntu: sudo apt install ffmpeg\n"
            "  Then open a NEW terminal window and try again.")
    return found  # type: ignore[return-value]


def has_filter(name: str) -> bool:
    out = subprocess.run([ffmpeg_bin(), "-hide_banner", "-filters"],
                         capture_output=True, text=True).stdout
    return any(line.split()[1:2] == [name] for line in out.splitlines() if line.strip())


# ---------------------------------------------------------------------------
# Text rasterising. This is the part many ffmpeg builds cannot do.
# ---------------------------------------------------------------------------


def fit_font(font_path: str, text: str, max_width: int, start_size: int = 132):
    """Largest size that still fits the line inside max_width."""
    size = start_size
    while size > 28:
        font = kc.load_font(font_path, size)
        if font.getbbox(text)[2] - font.getbbox(text)[0] <= max_width:
            return font
        size -= 4
    return kc.load_font(font_path, 28)


def wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Wrap to max_width. A newline inside the text forces a line break."""
    lines = []
    for para in str(text).split("\n"):
        current = ""
        for word in para.split():
            trial = f"{current} {word}".strip()
            if font.getbbox(trial)[2] - font.getbbox(trial)[0] <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def uniform_font(cards: list[Card], font_path: str, max_width: int,
                 max_lines: int = 2) -> "ImageFont.FreeTypeFont":
    """One size for the whole clip.

    Short-form practice is one font, one weight. Sizing each card to its own longest
    word makes the type breathe in and out across the clip, which reads as a
    template. So pick the largest size at which every card still fits inside
    max_lines, and use it everywhere.
    """
    size = 150
    while size > 40:
        font = kc.load_font(font_path, size)
        if all(len(wrap(c.text, font, max_width)) <= max_lines for c in cards):
            return font
        size -= 2
    return kc.load_font(font_path, 40)


def render_card(card: Card, font: ImageFont.FreeTypeFont, text_rgb, accent_rgb,
                out_path: Path, max_width: int | None = None, look: dict | None = None) -> None:
    """One transparent PNG, text centred inside the safe square, with a shadow.

    White type on a white wall is the commonest unforced error in short form,
    so every card gets a soft drop shadow whether it looks like it needs one
    or not.

    max_width narrows the wrap. Captions burned over footage need it, because
    the platform action rail sits 200px in from the right and a block wrapped
    to the full safe width puts the last word under the like button. Default
    is unchanged, so the generated-background paths behave exactly as before.

    look carries the brand's "shadow" and "line_height". With none given the shadow
    stays on, because the commonest mistake in captions is unreadable type.
    """
    look = look or {}
    shadow_cfg = dict(kc.NEUTRAL["shadow"], **(look.get("shadow") or {}))
    line_height = float(look.get("line_height") or kc.NEUTRAL["line_height"])
    if max_width is None:
        max_width = W - (2 * SAFE_SIDE)
    lines = wrap(card.text, font, max_width)

    ascent, descent = font.getmetrics()
    line_h = int((ascent + descent) * line_height)
    block_h = line_h * len(lines)

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    sdraw = ImageDraw.Draw(shadow)

    safe_mid = (SAFE_TOP + SAFE_BOTTOM) // 2
    y = safe_mid - block_h // 2

    accent_set = {w.lower().strip(".,!?'\"") for w in card.accent}

    for line in lines:
        words = line.split()
        widths = [font.getbbox(w + " ")[2] - font.getbbox(w + " ")[0] for w in words]
        total = sum(widths) - (font.getbbox(" ")[2] - font.getbbox(" ")[0] if words else 0)
        x = (W - total) // 2
        for word, width in zip(words, widths):
            colour = accent_rgb if word.lower().strip(".,!?'\"") in accent_set else text_rgb
            if shadow_cfg.get("enabled", True):
                sdraw.text((x + int(shadow_cfg["dx"]), y + int(shadow_cfg["dy"])), word, font=font,
                           fill=(0, 0, 0, int(shadow_cfg["alpha"])))
            draw.text((x, y), word, font=font, fill=colour + (255,))
            x += width
        y += line_h

    if shadow_cfg.get("enabled", True):
        shadow = shadow.filter(ImageFilter.GaussianBlur(float(shadow_cfg["blur"])))
    out = Image.alpha_composite(shadow, canvas)
    out.save(out_path)


def make_background(spec: dict, out_path: Path) -> tuple[Path, str]:
    """Return (image path, motion mode). Images are prepared at 1.2x for motion."""
    bg = spec.get("background") or kc.NEUTRAL["background"]
    motion = bg.get("motion", "hold")

    if bg.get("type") == "image":
        src = Path(bg["path"])
        if not src.exists():
            die(f"background image not found: {src}")
        img = Image.open(src).convert("RGB")
        scale = max((W * 1.2) / img.width, (H * 1.2) / img.height)
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
        left = (img.width - int(W * 1.2)) // 2
        top = (img.height - int(H * 1.2)) // 2
        img = img.crop((left, top, left + int(W * 1.2), top + int(H * 1.2)))
        img.save(out_path)
        return out_path, motion

    if bg.get("type") == "solid":
        Image.new("RGB", (W, H), hex_rgb(bg.get("color", kc.NEUTRAL_GRADIENT[0]))).save(out_path)
        return out_path, "hold"

    top_rgb = hex_rgb(bg.get("from", kc.NEUTRAL_GRADIENT[0]))
    bot_rgb = hex_rgb(bg.get("to", kc.NEUTRAL_GRADIENT[1]))
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    for row in range(H):
        t = row / (H - 1)
        # ease the blend so the midpoint does not sit in a flat band
        t = t * t * (3 - 2 * t)
        draw.line([(0, row), (W, row)],
                  fill=tuple(int(top_rgb[i] + (bot_rgb[i] - top_rgb[i]) * t) for i in range(3)))
    img.save(out_path)
    return out_path, "hold"


# ---------------------------------------------------------------------------


def estimate_cards(text: str, start: float = 0.0) -> list[Card]:
    """Split a script into cards of at most four words, timed by speaking rate."""
    words = text.split()
    cards, t = [], start
    for i in range(0, len(words), MAX_WORDS_PER_CARD):
        chunk = words[i:i + MAX_WORDS_PER_CARD]
        dur = max(0.65, len(chunk) / WORDS_PER_SECOND)
        cards.append(Card(" ".join(chunk), round(t, 3), round(t + dur, 3)))
        t += dur
    return cards


def load_cards(spec: dict) -> list[Card]:
    if spec.get("cards"):
        cards = []
        for n, raw in enumerate(spec["cards"]):
            if not isinstance(raw, dict) or not all(k in raw for k in ("text", "start", "end")):
                die(f"card number {n + 1} needs text, start and end, for example "
                    '{"text": "Hello", "start": 0.0, "end": 1.2}')
            cards.append(Card(raw["text"], float(raw["start"]), float(raw["end"]),
                              list(raw.get("accent", []))))
        return cards
    if spec.get("script"):
        return estimate_cards(spec["script"])
    die("spec needs either 'cards' or 'script'")
    return []


def probe_duration(path: str) -> float | None:
    probe = shutil.which("ffprobe")
    if not probe:
        return None
    out = subprocess.run(
        [probe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return None


def build_stills(spec: dict) -> list[Path]:
    """Flatten each card onto the background and write numbered PNGs.

    Carousels need the same type, colour and safe zones as the video, so they
    share the card renderer rather than getting their own.
    """
    out_path = Path(spec["out"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    stem = out_path.with_suffix("")

    font_path = pick_font(spec.get("font"))
    text_rgb = hex_rgb(spec["text_color"])
    accent_rgb = hex_rgb(spec["accent"])
    cards = load_cards(spec)
    look = {"shadow": spec.get("shadow"), "line_height": spec.get("line_height")}
    font = uniform_font(cards, font_path, W - (2 * SAFE_SIDE),
                        max_lines=int(spec.get("max_lines_stills") or 4))

    # The cover is the only slide that has to stop a thumb, so it gets its own
    # size. Sizing it with the body cards makes it as quiet as the footnotes,
    # which is the commonest way a carousel dies before slide two.
    cover_font = uniform_font(cards[:1], font_path, W - (2 * SAFE_SIDE),
                              max_lines=int(spec.get("cover_lines", 3)))

    tmp = Path(tempfile.mkdtemp(prefix="stills-"))
    try:
        bg_path, _ = make_background(spec, tmp / "bg.png")
        bg = Image.open(bg_path).convert("RGB")
        if bg.size != (W, H):
            bg = bg.resize((W, H), Image.LANCZOS)

        handle = spec.get("handle", "")
        foot_font = kc.load_font(font_path, 34)
        total = len(cards)

        written = []
        for i, card in enumerate(cards, start=1):
            layer = tmp / f"card{i:02d}.png"
            render_card(card, cover_font if i == 1 else font, text_rgb, accent_rgb, layer, look=look)
            frame = bg.copy().convert("RGBA")
            frame.alpha_composite(Image.open(layer).convert("RGBA"))

            # Handle left, counter right, both above the action rail.
            draw = ImageDraw.Draw(frame)
            foot_y = H - 300
            muted = tuple(int(c * 0.55 + 255 * 0.12) for c in text_rgb) + (255,)
            if handle:
                draw.text((SAFE_SIDE, foot_y), handle, font=foot_font, fill=muted)
            label = f"{i}/{total}" if i < total else "•"
            lw = foot_font.getbbox(label)[2] - foot_font.getbbox(label)[0]
            draw.text((W - SAFE_SIDE - lw, foot_y), label, font=foot_font,
                      fill=accent_rgb + (255,))

            dest = Path(f"{stem}-{i:02d}.png")
            frame.convert("RGB").save(dest, quality=95)
            written.append(dest)
        return written
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build(spec: dict, workdir: Path, check_only: bool = False) -> Path:
    out_path = Path(spec["out"])
    out_path.parent.mkdir(parents=True, exist_ok=True)

    font_path = pick_font(spec.get("font"))
    text_rgb = hex_rgb(spec["text_color"])
    accent_rgb = hex_rgb(spec["accent"])
    look = {"shadow": spec.get("shadow"), "line_height": spec.get("line_height")}

    cards = load_cards(spec)
    if not cards:
        die("no cards to render")

    voice = spec.get("audio")
    duration = float(spec.get("duration") or 0) or None
    if voice and not duration:
        duration = probe_duration(voice)
    if not duration:
        duration = cards[-1].end + 0.6
    duration = round(float(duration), 3)

    bg_path, motion = make_background(spec, workdir / "bg.png")

    font = uniform_font(cards, font_path, W - (2 * SAFE_SIDE),
                        max_lines=int(spec.get("max_lines", 2)))
    card_files = []
    for i, card in enumerate(cards):
        p = workdir / f"card{i:03d}.png"
        render_card(card, font, text_rgb, accent_rgb, p, look=look)
        card_files.append(p)

    # ---- assemble the ffmpeg call -----------------------------------------
    cmd = [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error"]
    cmd += ["-loop", "1", "-framerate", str(FPS), "-t", f"{duration}", "-i", str(bg_path)]
    for p in card_files:
        cmd += ["-loop", "1", "-framerate", str(FPS), "-t", f"{duration}", "-i", str(p)]

    audio_inputs = []
    if voice:
        cmd += ["-i", voice]
        audio_inputs.append(("voice", len(card_files) + 1))
    if spec.get("music"):
        cmd += ["-i", spec["music"]]
        audio_inputs.append(("music", len(card_files) + 1 + len(audio_inputs)))

    total_frames = max(1, int(duration * FPS))
    if motion == "push":
        # One slow push. Keep it to at most one per 30 seconds of video.
        base = (f"[0:v]scale={int(W*1.2)}:{int(H*1.2)},"
                f"zoompan=z='min(zoom+0.00035,1.12)':d={total_frames}:"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
                f"format=yuv420p[bg]")
    elif motion == "drift":
        base = (f"[0:v]scale={int(W*1.2)}:{int(H*1.2)},"
                f"zoompan=z=1.12:d={total_frames}:"
                f"x='(iw-iw/zoom)*(on/{total_frames})':y='ih/2-(ih/zoom/2)':"
                f"s={W}x{H}:fps={FPS},format=yuv420p[bg]")
    else:
        base = f"[0:v]scale={W}:{H},format=yuv420p[bg]"

    chain = [base]
    last = "bg"
    for i, card in enumerate(cards):
        nxt = f"v{i}"
        # Cut in, cut out. No fade: a fading caption reads as lag.
        chain.append(
            f"[{last}][{i+1}:v]overlay=0:0:enable='between(t,{card.start:.3f},{card.end:.3f})'[{nxt}]"
        )
        last = nxt

    filter_complex = ";".join(chain)

    amap = None
    if audio_inputs:
        names = dict(audio_inputs)
        if "voice" in names and "music" in names:
            filter_complex += (
                f";[{names['music']}:a]volume={MUSIC_DUCK_DB}dB[mus]"
                f";[{names['voice']}:a][mus]amix=inputs=2:duration=first:dropout_transition=0[amix]"
                f";[amix]loudnorm=I={LUFS}:TP={TRUE_PEAK}:LRA=11[aout]"
            )
        else:
            only = names.get("voice", names.get("music"))
            filter_complex += f";[{only}:a]loudnorm=I={LUFS}:TP={TRUE_PEAK}:LRA=11[aout]"
        amap = "[aout]"

    cmd += ["-filter_complex", filter_complex, "-map", f"[{last}]"]
    if amap:
        cmd += ["-map", amap, "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", "48000", "-ac", "2"]
    cmd += [
        "-c:v", "libx264", "-profile:v", "high", "-preset", "medium",
        "-b:v", VIDEO_BITRATE, "-maxrate", "15M", "-bufsize", "20M",
        "-pix_fmt", "yuv420p", "-r", str(FPS), "-movflags", "+faststart",
        "-t", f"{duration}", str(out_path),
    ]

    if check_only:
        print(" ".join(f'"{c}"' if " " in c else c for c in cmd))
        return out_path

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        die(f"ffmpeg failed\n{result.stderr.strip()[:3000]}")
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Render a vertical caption clip.")
    ap.add_argument("spec", help="path to the JSON spec")
    ap.add_argument("--brand", help="path to a brand file (font, colours, background, handle)")
    ap.add_argument("--check", action="store_true", help="print the ffmpeg command and stop")
    ap.add_argument("--keep", action="store_true", help="keep the frame workdir for inspection")
    ap.add_argument("--stills", action="store_true",
                    help="write one numbered PNG per card instead of a video, for carousels")
    ap.add_argument("--which-font", action="store_true",
                    help="print which font file this spec would draw with, then stop")
    args = ap.parse_args()

    spec = kc.load_spec(args.spec, args.brand)

    if args.which_font:
        print(pick_font(spec.get("font")))
        return
    if "out" not in spec:
        die('the spec needs an "out" path, for example "out": "out/first.mp4"')

    if args.stills:
        for p in build_stills(spec):
            print(f"{p}  {p.stat().st_size/1000:.0f} KB")
        return

    workdir = Path(tempfile.mkdtemp(prefix="makeclip-"))
    try:
        out = build(spec, workdir, check_only=args.check)
        if not args.check:
            size = out.stat().st_size
            dur = probe_duration(str(out))
            print(f"{out}  {size/1_000_000:.2f} MB  {dur:.2f}s" if dur
                  else f"{out}  {size/1_000_000:.2f} MB")
    finally:
        if args.keep:
            print(f"frames kept in {workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
