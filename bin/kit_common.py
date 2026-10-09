#!/usr/bin/env python3
"""kit_common.py: the parts every content-line script shares.

You do not run this file. make_clip.py and caption_video.py import it.

What lives here, and why it is in one place:

  1. Pillow bootstrap. If the Python you launched does not have Pillow but the kit has its
     own .venv folder, the script quietly re-runs itself with that venv. So
     `python3 bin/make_clip.py spec.json` works without activating anything.
  2. Font search. Brand fonts are yours. This finds a font on macOS, Linux or Windows, and
     if it cannot find one it says exactly what to install.
  3. Brand and spec loading. Colours, fonts and handles live in a brand file you supply
     (see specs/example-brand.json), never in the code.
  4. Path rules. A relative INPUT path is looked for next to the file that names it first,
     then in the folder you ran the command from. A relative OUTPUT path ("out") is placed
     next to the file that names it, full stop. Both ends of a spec therefore resolve against
     the same folder, so a spec writes to the same place however you invoke it.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parent.parent
IS_WINDOWS = os.name == "nt"
PILLOW_BUILTIN = "pillow-builtin"      # marker: use Pillow's own bundled typeface

# On Windows the console may be cp1252, and a curly quote in a caption would crash a print.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")      # type: ignore[attr-defined]
    except Exception:                               # noqa: BLE001
        pass


def _who() -> str:
    return Path(sys.argv[0]).stem or "content-line"


def die(msg: str) -> None:
    print(f"{_who()}: {msg}", file=sys.stderr)
    sys.exit(1)


def warn(msg: str) -> None:
    print(f"{_who()}: warning: {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 1. Pillow bootstrap
# ---------------------------------------------------------------------------


def kit_venv_python() -> Path | None:
    for rel in (("bin", "python"), ("Scripts", "python.exe")):
        p = KIT_ROOT / ".venv" / Path(*rel)
        if p.exists():
            return p
    return None


def ensure_pillow() -> None:
    """Make sure `import PIL` will work, re-running inside the kit's .venv if needed."""
    try:
        import PIL  # noqa: F401
        return
    except ImportError:
        pass
    py = kit_venv_python()
    already_in_venv = Path(sys.prefix).resolve() == (KIT_ROOT / ".venv").resolve()
    if py and not already_in_venv and not os.environ.get("CONTENT_LINE_REEXEC"):
        print(f"{_who()}: Pillow is not in this Python, re-running with the kit's own .venv", file=sys.stderr)
        env = dict(os.environ, CONTENT_LINE_REEXEC="1")
        sys.exit(subprocess.call([str(py)] + sys.argv, env=env))
    py_cmd = "python" if IS_WINDOWS else "python3"
    venv_py = r".venv\Scripts\python" if IS_WINDOWS else ".venv/bin/python"
    die("Pillow (the library that draws the captions) is not installed.\n"
        "  Fix, from the kit folder:\n"
        f"    {py_cmd} -m venv .venv\n"
        f"    {venv_py} -m pip install -r requirements.txt\n"
        "  or run the setup script that came with the kit. Then run this again.")


ensure_pillow()

from PIL import ImageFont  # noqa: E402  (after the bootstrap on purpose)

# ---------------------------------------------------------------------------
# 2. Fonts
# ---------------------------------------------------------------------------

# Tried in this order when no usable font is named: macOS, Linux, Windows, then anything
# Pillow itself can find, then the typeface Pillow carries inside itself.
# Set "font" in your brand file instead of relying on this. A fallback is a different
# typeface, not your look.
MAC_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Futura.ttc",
    "/Library/Fonts/Arial Bold.ttf",
]
LINUX_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/liberation-sans/LiberationSans-Bold.ttf",
    "/usr/share/fonts/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/noto/NotoSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
]
WINDOWS_FONTS = [
    "C:\\Windows\\Fonts\\arialbd.ttf",
    "C:\\Windows\\Fonts\\segoeuib.ttf",
    "C:\\Windows\\Fonts\\calibrib.ttf",
    "C:\\Windows\\Fonts\\verdanab.ttf",
    "C:\\Windows\\Fonts\\tahomabd.ttf",
]
# File names handed to Pillow, which searches the operating system's font folders itself.
PILLOW_NAMES = ["Arial Bold.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf",
                "FreeSansBold.ttf", "Helvetica.ttc", "NotoSans-Bold.ttf", "Verdana.ttf"]


def system_font_dirs() -> list[Path]:
    dirs = [Path("/System/Library/Fonts"), Path("/System/Library/Fonts/Supplemental"),
            Path("/Library/Fonts"), Path.home() / "Library" / "Fonts",
            Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
            Path.home() / ".fonts", Path.home() / ".local" / "share" / "fonts"]
    win = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    if win:
        dirs.append(Path(win) / "Fonts")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    return [d for d in dirs if d.is_dir()]


def system_fonts_enabled() -> bool:
    """CONTENT_LINE_SYSTEM_FONTS=off pretends this machine has no fonts at all, Pillow's
    built-in one included. It exists so the 'no font found' message can be tested for real."""
    return os.environ.get("CONTENT_LINE_SYSTEM_FONTS", "").strip().lower() not in ("off", "0", "none")


def _norm(name: str) -> str:
    stem = re.sub(r"\.(ttf|otf|ttc)$", "", name.strip(), flags=re.I)
    return re.sub(r"[\s_\-]+", "", stem).lower()


def _search_by_name(name: str) -> str | None:
    """'Montserrat-Bold' or 'Arial Bold' to a file in the system font folders."""
    want = _norm(name)
    for d in system_font_dirs():
        for root, _dirs, files in os.walk(d):
            for f in files:
                if f.lower().endswith((".ttf", ".otf", ".ttc")) and _norm(f) == want:
                    return str(Path(root) / f)
    return None


class FontNotFound(Exception):
    pass


NO_FONT_MESSAGE = (
    "no usable font found on this machine.\n"
    "  The captions are drawn by Pillow, so one font file is required. Do one of these:\n"
    "    1. Best: put your brand font (a .ttf or .otf file) in the kit folder and set\n"
    '       "font": "YourFont-Bold.ttf" in your brand file.\n'
    "    2. Windows: Arial and Segoe UI ship with Windows. If C:\\Windows\\Fonts is empty, install any font\n"
    "       from the Microsoft Store or download a .ttf from fonts.google.com.\n"
    "    3. macOS: Arial ships with macOS. Or download a .ttf from fonts.google.com.\n"
    "    4. Linux: sudo apt install fonts-dejavu-core   (or: sudo apt install fonts-liberation)\n"
    "  If you already have fonts, your Pillow may be missing FreeType. Fix with:\n"
    "    pip install --force-reinstall --no-cache-dir pillow"
)


def find_font(requested: str | None = None) -> str:
    """Return a font reference: a file path, a name Pillow can resolve, or PILLOW_BUILTIN.

    Order: the font you asked for (path, then name), macOS, Linux, Windows, Pillow's own
    search, Pillow's bundled typeface. Raises FontNotFound with an install message if none.
    """
    on = system_fonts_enabled()
    if requested:
        p = Path(str(requested)).expanduser()
        if p.is_file():
            return str(p)
        if on:
            hit = _search_by_name(str(requested))
            if hit:
                return hit
        warn(f'the font "{requested}" was not found, so a fallback typeface is being used. '
             'Set "font" in your brand file to a real .ttf or .otf file.')
    if on:
        for cand in MAC_FONTS + LINUX_FONTS + WINDOWS_FONTS:
            if os.path.isfile(cand):
                return cand
        for name in PILLOW_NAMES:
            try:
                ImageFont.truetype(name, 40)
                return name
            except (OSError, ValueError):
                continue
        try:
            from PIL import features
            if features.check("freetype2"):
                f = ImageFont.load_default(40)
                if isinstance(f, ImageFont.FreeTypeFont):
                    warn("no system font found, using the plain typeface built into Pillow. "
                         'It works, but set "font" in your brand file for your own look.')
                    return PILLOW_BUILTIN
        except Exception:                           # noqa: BLE001 (older Pillow has no load_default(size))
            pass
    raise FontNotFound(NO_FONT_MESSAGE)


def load_font(ref: str, size: int):
    if ref == PILLOW_BUILTIN:
        return ImageFont.load_default(size)
    return ImageFont.truetype(ref, size)


# ---------------------------------------------------------------------------
# 3. Brand and spec loading
# ---------------------------------------------------------------------------

# What a brand file may carry. A brand file never carries content or an output path.
# The second row is the assemble_clip.py look: a .ttc face index, the reframe, the
# caption fade, the colour tag fix, the grade, the skin pass and the export numbers.
# They are listed here so a buyer's style file can hold them, because a key that is
# not in this set is silently dropped out of a brand file.
BRAND_KEYS = {"name", "font", "text_color", "accent", "background", "shadow", "line_height",
              "max_lines", "max_lines_stills", "cover_lines", "handle", "caption_position",
              "caption_nudge", "font_size", "font_size_max",
              "font_index", "side_margin", "hook", "zoom", "focus_x", "focus_y", "fade_ms",
              "color_fix", "grade", "skin", "export", "keep_audio"}
# What only a spec carries: the content of one piece.
SPEC_KEYS = {"brand", "out", "cards", "script", "duration", "audio", "music", "source", "trim",
             "times", "focus_x", "focus_y",
             "segments", "caption_cards", "hook_text", "pieces", "out_dir", "filename", "piece"}

# Nested blocks that MERGE rather than replace, so a spec may change one value
# inside one of them without restating the whole block.
MERGE_DEEP = ("shadow", "hook", "grade", "skin", "export")

# Plain and neutral on purpose. Nobody's colours live in the code.
NEUTRAL = {
    "text_color": "#FFFFFF",
    "accent": "#FFFFFF",
    "background": {"type": "solid", "color": "#111111"},
    "shadow": {"enabled": True, "dx": 5, "dy": 6, "alpha": 190, "blur": 14},
    "line_height": 1.14,
}
NEUTRAL_GRADIENT = ("#111111", "#1E1E1E")


def read_json(path: Path, what: str) -> dict:
    try:
        # utf-8-sig so a file saved by Windows Notepad (which adds a BOM) still loads
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        die(f"{what} not found: {path}")
    except json.JSONDecodeError as exc:
        die(f"{what} {path} is not valid JSON. Line {exc.lineno}, column {exc.colno}: {exc.msg}.\n"
            "  The usual causes: a missing comma between two items, a trailing comma after the last\n"
            "  item, or a straight quote typed as a curly one.")
    if not isinstance(data, dict):
        die(f"{what} {path} must be a JSON object, a block that starts with {{ and ends with }}")
    return data  # type: ignore[return-value]


def resolve_input(value: str, base: Path) -> str:
    """A relative path is looked for next to the file that names it, then where you ran from."""
    p = Path(value).expanduser()
    if p.is_absolute():
        return str(p)
    for cand in (base / p, Path.cwd() / p):
        if cand.exists():
            return str(cand)
    return value


def resolve_output(value: str, base: Path) -> str:
    """Where a finished file goes.

    Unlike an input, this cannot check whether the path exists, so it cannot fall back to the
    current directory. It anchors to the file that named it. Without this, a spec saying
    "source": "../inbox/take.mp4" and "out": "../review/take.mp4" resolved those two identical
    prefixes against two different folders and wrote the finished video outside the kit while
    reporting success.
    """
    p = Path(value).expanduser()
    if p.is_absolute():
        return str(p)
    return str((base / p).resolve())


def _absolutize(layer: dict, base: Path) -> dict:
    layer = dict(layer)
    out = layer.get("out")
    if isinstance(out, str) and out:
        layer["out"] = resolve_output(out, base)
    for key in ("font", "audio", "music", "source"):
        v = layer.get(key)
        if isinstance(v, str) and v:
            layer[key] = resolve_input(v, base)
    bg = layer.get("background")
    if isinstance(bg, dict) and isinstance(bg.get("path"), str):
        layer["background"] = dict(bg, path=resolve_input(bg["path"], base))
    return layer


def load_spec(spec_arg: str, brand_arg: str | None = None) -> dict:
    """Read a spec and lay it over the brand file, which is laid over the neutral defaults."""
    spec_path = Path(spec_arg).expanduser()
    raw = read_json(spec_path, "spec")
    spec_dir = spec_path.resolve().parent
    spec = _absolutize(raw, spec_dir)

    brand_ref = brand_arg or raw.get("brand") or os.environ.get("CONTENT_LINE_BRAND")
    merged: dict = {k: (dict(v) if isinstance(v, dict) else v) for k, v in NEUTRAL.items()}
    if brand_ref:
        # a brand named inside a spec is looked for next to that spec; one named on the
        # command line or in the environment is looked for where you ran from
        bpath = Path(resolve_input(str(brand_ref), spec_dir if (raw.get("brand") and not brand_arg) else Path.cwd()))
        if not bpath.is_file():
            die(f"brand file not found: {brand_ref}\n  Looked next to the spec and in {Path.cwd()}. "
                "Copy specs/example-brand.json to a new name and fill it in.")
        brand_raw = read_json(bpath, "brand file")
        brand = _absolutize({k: v for k, v in brand_raw.items() if k in BRAND_KEYS}, bpath.resolve().parent)
        for k, v in brand.items():
            if v is None or v == "":
                continue                                    # null means "use the default"
            if k in MERGE_DEEP and isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k].update(v)
            else:
                merged[k] = v
        merged["_brand_path"] = str(bpath)
    else:
        merged["_brand_path"] = ""
        inline_look = any(k in raw for k in ("font", "text_color", "accent", "background"))
        if not inline_look:
            print(f"{_who()}: note: no brand file given, using plain white-on-dark defaults. "
                  "Add --brand specs/yourbrand.json for your own look.", file=sys.stderr)

    for k, v in spec.items():
        if k == "brand" or v is None:
            continue
        if k in MERGE_DEEP and isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k].update(v)
        else:
            merged[k] = v

    unknown = [k for k in raw if k not in BRAND_KEYS | SPEC_KEYS and not k.startswith("_")]
    if unknown:
        warn("ignored unknown key(s) in the spec: " + ", ".join(sorted(unknown))
             + ". Check the spelling against specs/example-brand.json.")
    return merged
