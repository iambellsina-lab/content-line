#!/usr/bin/env python3
"""
carousel_render.py - a BRAND AGNOSTIC carousel renderer. Brand file in, carousel file in,
finished PNG slides out. Nothing in this file knows about any one client.

    .venv/bin/python bin/carousel_render.py --brand BRAND.json --carousel CAROUSEL.json
    .venv/bin/python bin/carousel_render.py --brand BRAND.json --selftest work/torture
    .venv/bin/python bin/carousel_render.py --contact-sheet SHEET.png DIR_OR_PNGS...

Where this came from. Studio/bin/ort_design_render.py already solved wrapping, fitting, safe
margins and PNG output at 1080x1350 and 1080x1920, and its hard-won lesson is recorded in its
own comments: a long title drew as ONE line, ran off both edges, and the body was positioned
from the FIRST title line, so a three line title sat on top of its own body. Everything below
is built so that cannot happen: every element wraps, the whole block shrinks together until it
fits its box, and the block is laid out from measured heights rather than from fixed offsets.
What this file adds is that nothing is hardwired to one brand, and that it checks its own work.

HOW IT CHECKS ITS OWN WORK, which is the part that matters. Every slide is drawn in two layers:
a background layer (the flat colour and any full bleed panel) and an INK layer, which is RGBA
and transparent and carries every pixel of type and every rule. After drawing, the ink layer's
alpha channel is measured with getbbox(). That bounding box is the real extent of the ink, as
rasterised, not as predicted from font metrics. If it crosses a margin the slide is a failure
and the run exits non zero. A return code from Pillow proves a file was written; this proves
the type is inside the frame.

IT REFUSES RATHER THAN CRASHING on: a font file that is missing or will not load, a slide with
no text, text that cannot be made to fit even at the minimum scale, a colour that fails its
contrast threshold against its own background, an unknown colour or font name, a role the brand
file does not define. Each one prints what is wrong, which slide, and what to change.

CONTRAST. Ratios are WCAG 2.1 relative luminance. The default threshold is 4.5, which is the
normal text rule. An element may declare a lower "min_contrast" and 3.0 is the WCAG large text
allowance; that is the honest way to use a brand colour that is too light for body copy at
display size without inventing a different colour. It is a setting per element so that the
brand file, not this code, decides.

THE FILE FORMATS are documented in specs/carousel-brand.example.json and in CAROUSELS.md.
"""
import argparse
import json
import math
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.stderr.write("carousel_render: Pillow is not installed in this interpreter.\n"
                     "  Run setup.sh, then use .venv/bin/python to run this script.\n")
    raise SystemExit(2)

# The elements a slide can carry, in the order they stack down the page. Every one is optional
# except "text". A role in the brand file styles the ones it wants and omits the rest, which is
# how a cover, a body slide and a final slide come out looking different from the same code.
ELEMENTS = ("label", "text", "attrib", "question", "cta")

# Letterspacing is applied BETWEEN LETTERS, never around punctuation. Tracked small caps with
# this rule missing put a full stop adrift in its own pocket of air, so "DR. FRED DIDOMENICO"
# read as "DR . FRED" and "THE H.E.A.L.E.D. SYSTEM" came out as a row of floating dots. Found by
# opening the PNG and reading it; every exit code in that run was zero.
TIGHT_AFTER = ".,:;!?-/'" + "\u2019\u201c\u201d\u2013\u2014"  # quotes and the two long dashes, by code point

FIT_SCALE_FLOOR = 0.50   # never shrink an element below half its configured size
FIT_SCALE_STEP = 0.01


class Refusal(Exception):
    """Something would produce an unreadable or wrong slide. Say so, do not draw it."""


# ---------------------------------------------------------------- colour helpers

def hexrgb(h, where):
    s = str(h).lstrip("#")
    if len(s) != 6 or any(c not in "0123456789abcdefABCDEF" for c in s):
        raise Refusal(f"{where}: {h!r} is not a six digit hex colour like \"#319CB7\".")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def _channel(v):
    v = v / 255.0
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def luminance(rgb):
    r, g, b = (_channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(rgb_a, rgb_b):
    la, lb = luminance(rgb_a), luminance(rgb_b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# ---------------------------------------------------------------- the brand file

class Brand:
    def __init__(self, path):
        self.path = Path(path)
        try:
            self.raw = json.loads(self.path.read_text())
        except FileNotFoundError:
            raise Refusal(f"brand file not found: {self.path}")
        except json.JSONDecodeError as e:
            raise Refusal(f"brand file {self.path} is not valid JSON: {e}")

        self.name = self.raw.get("name", self.path.stem)
        size = self.raw.get("size", [1080, 1350])
        if (not isinstance(size, (list, tuple)) or len(size) != 2
                or not all(isinstance(v, int) and v > 0 for v in size)):
            raise Refusal('brand "size" must be two positive integers, for example [1080, 1350].')
        self.size = (int(size[0]), int(size[1]))
        self.min_contrast_default = float(self.raw.get("min_contrast_default", 4.5))

        self.fonts_cfg = self.raw.get("fonts") or {}
        if not self.fonts_cfg:
            raise Refusal('brand file has no "fonts" block.')
        self.themes = self.raw.get("themes") or {}
        if not self.themes:
            raise Refusal('brand file has no "themes" block.')
        self._font_cache = {}
        self.check_fonts()

    # Fonts are checked up front, all of them, before a single pixel is drawn, so a missing
    # font is one clear message at the start instead of a traceback partway through a batch.
    def check_fonts(self):
        missing = []
        for key, cfg in self.fonts_cfg.items():
            f = cfg.get("file")
            if not f:
                missing.append(f'  font "{key}": no "file" given')
                continue
            p = Path(f)
            if not p.exists():
                missing.append(f'  font "{key}": file does not exist on this machine: {f}')
                continue
            try:
                ImageFont.truetype(str(p), 32, index=int(cfg.get("index", 0)))
            except Exception as e:
                missing.append(f'  font "{key}": {p} would not load at index '
                               f'{cfg.get("index", 0)}: {e}')
        if missing:
            raise Refusal("these fonts are not usable on this machine:\n" + "\n".join(missing)
                          + "\nFix the paths in the brand file. /System/Library/Fonts/ and "
                            "/System/Library/Fonts/Supplemental/ are where macOS keeps its own.")

    def font(self, key, px, where):
        if key not in self.fonts_cfg:
            raise Refusal(f'{where}: font "{key}" is not in the brand file\'s "fonts" block '
                          f'(it has: {", ".join(sorted(self.fonts_cfg))}).')
        px = max(1, int(round(px)))
        ck = (key, px)
        if ck not in self._font_cache:
            cfg = self.fonts_cfg[key]
            self._font_cache[ck] = ImageFont.truetype(
                str(cfg["file"]), px, index=int(cfg.get("index", 0)))
        return self._font_cache[ck]

    def theme(self, name):
        if name not in self.themes:
            raise Refusal(f'theme "{name}" is not in the brand file '
                          f'(it has: {", ".join(sorted(self.themes))}). '
                          f'A slide in the wrong theme is a real error, so this will not guess.')
        return self.themes[name]


def colour(theme, key, where):
    pal = theme.get("palette") or {}
    if key in pal:
        return hexrgb(pal[key], f"{where} (palette.{key})")
    if isinstance(key, str) and key.startswith("#"):
        return hexrgb(key, where)
    raise Refusal(f'{where}: colour "{key}" is not in this theme\'s palette '
                  f'(it has: {", ".join(sorted(pal))}).')


# ---------------------------------------------------------------- text fitting

def _greedy(para, font, max_w):
    lines, cur = [], ""
    for word in para.split():
        trial = f"{cur} {word}".strip()
        if font.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    lines.append(cur)
    return lines


def wrap(text, font, max_w, balance=True):
    """Wrap to max_w, honouring any line breaks the copy already carries.

    Greedy wrapping fills each line to the brim and dumps the remainder on the last one, so a
    paragraph routinely ends on a runt: "Honor God within yourself. God, Source, Higher Power,
    however you name / it." Three words left alone under a full measure reads as a mistake, and
    on a card that somebody sees for one second it is the thing they notice.

    Balancing fixes it without touching the copy. The paragraph is wrapped greedily to find how
    many lines it needs, then the narrowest width that still needs exactly that many lines is
    found by bisection and the paragraph is wrapped again at that width. The line count never
    changes and no line ever gets wider than max_w, so nothing can overflow: the words simply
    spread evenly instead of piling up at the top.
    """
    out = []
    for para in str(text).split("\n"):
        if not para.strip():
            out.append("")
            continue
        lines = _greedy(para, font, max_w)
        if balance and len(lines) > 1:
            n = len(lines)
            lo, hi = 1, int(max_w)
            while lo < hi:
                mid = (lo + hi) // 2
                if len(_greedy(para, font, mid)) <= n:
                    hi = mid
                else:
                    lo = mid + 1
            cand = _greedy(para, font, lo)
            if len(cand) == n and max(font.getlength(x) for x in cand) <= max_w:
                lines = cand
        out.extend(lines)
    return out


def _tracks(text, tracking):
    """The extra space after each character except the last. Zero next to punctuation."""
    for i in range(len(text) - 1):
        a, b = text[i], text[i + 1]
        yield 0.0 if (a in TIGHT_AFTER or b in TIGHT_AFTER) else tracking


def measured_width(lines, font, tracking=0.0):
    w = 0.0
    for ln in lines:
        if not ln:
            continue
        lw = font.getlength(ln)
        if tracking:
            lw = sum(font.getlength(c) for c in ln) + sum(_tracks(ln, tracking))
        w = max(w, lw)
    return w


def layout(slide, role_cfg, brand, box_w, box_h, where):
    """Shrink every element together until the whole block fits the box.

    One scale factor drives the lot. Shrinking only the headline is what lets a headline and a
    body drift apart until they look like two different designs; shrinking together keeps the
    type hierarchy the brand file asked for at every size.
    """
    present = [k for k in ELEMENTS if slide.get(k) not in (None, "")]
    if "text" not in present:
        raise Refusal(f'{where}: no "text". A slide with nothing to read is not a slide.')
    for k in present:
        if k not in role_cfg:
            raise Refusal(f'{where}: slide carries "{k}" but role "{slide.get("role")}" does not '
                          f'style it. Add a "{k}" block to that role in the brand file, or take '
                          f'"{k}" off this slide.')

    scale = 1.0
    too_wide = None
    while scale >= FIT_SCALE_FLOOR - 1e-9:
        blocks, total_h, ok = [], 0.0, True
        for idx, k in enumerate(present):
            cfg = role_cfg[k]
            px = max(1.0, float(cfg.get("px", 48)) * scale)
            px_min = float(cfg.get("px_min", 0))
            if px_min and px < px_min:
                px = px_min
            font = brand.font(cfg.get("font", "body"), px, f"{where}.{k}")
            tracking = float(cfg.get("tracking", 0.0)) * scale
            lines = wrap(slide[k], font, box_w, balance=cfg.get("balance", True))
            if measured_width(lines, font, tracking) > box_w:
                ok = False
                too_wide = (k, round(measured_width(lines, font, tracking)), round(box_w))
                break
            lh = float(cfg.get("line_height", 1.15))
            h = len(lines) * px * lh
            gap = 0.0 if idx == 0 else float(cfg.get("gap_before", 36)) * scale
            blocks.append({"key": k, "cfg": cfg, "font": font, "px": px, "lines": lines,
                           "tracking": tracking, "h": h, "gap": gap})
            total_h += gap + h
        if ok:
            rule = role_cfg.get("rule") or {}
            if rule.get("enabled"):
                total_h += float(rule.get("gap_before", 40)) * scale + float(rule.get("h", 4))
            if total_h <= box_h:
                return blocks, total_h, scale
        scale -= FIT_SCALE_STEP

    if too_wide:
        k, got, lim = too_wide
        raise Refusal(f'{where}: the "{k}" text will not fit the {lim}px box even shrunk to '
                      f'{int(FIT_SCALE_FLOOR * 100)}% (it measures {got}px). It is probably one '
                      f'unbreakable word, or a URL. Shorten it, or widen the role\'s box.')
    raise Refusal(f'{where}: this slide\'s text is too tall for its {round(box_h)}px box even '
                  f'shrunk to {int(FIT_SCALE_FLOOR * 100)}%. Cut words, or give the role a '
                  f'taller box. Air is safe; a slide crammed to the margins is not.')


# ---------------------------------------------------------------- drawing

def draw_line(d, text, font, x, y_top, fill, align="center", tracking=0.0, box=None):
    """Draw one line. y_top is the top of the line box (Pillow's ascender anchor)."""
    if not text:
        return
    if tracking:
        total = sum(font.getlength(c) for c in text) + sum(_tracks(text, tracking))
        if align == "center":
            cx = x - total / 2
        elif align == "right":
            cx = x - total
        else:
            cx = x
        # Each character is placed on the BASELINE, not by its own top. Drawing a tracked string
        # character by character with a top anchor aligns every glyph's top to the same line, so
        # a full stop floats up to cap height: "H.E.A.L.E.D." came out as a row of raised dots.
        # Magnified the pixels to find it. Every exit code in that run was zero.
        base_y = y_top + font.getmetrics()[0]
        for c, t in zip(text, list(_tracks(text, tracking)) + [0.0]):
            d.text((cx, base_y), c, font=font, fill=fill, anchor="ls")
            cx += font.getlength(c) + t
        return
    anchor = {"center": "mt", "left": "lt", "right": "rt"}[align]
    d.text((x, y_top), text, font=font, fill=fill, anchor=anchor)


def check_contrast(brand, theme, cfg, bg_rgb, where, findings):
    fg = colour(theme, cfg.get("colour", "ink"), where)
    need = float(cfg.get("min_contrast", brand.min_contrast_default))
    got = contrast(fg, bg_rgb)
    findings.append({"where": where, "ratio": round(got, 2), "need": need,
                     "pass": got >= need - 0.005})
    if got < need - 0.005:
        raise Refusal(f"{where}: contrast {got:.2f}:1 against its own background fails the "
                      f"{need}:1 this element asks for. These get read on a phone. Darken the "
                      f"colour, or, if it is genuinely large display type, set "
                      f'"min_contrast": 3.0 on that element and mean it.')
    return fg


def render_slide(brand, theme, slide, index, total, where):
    role = slide.get("role", "body")
    roles = theme.get("roles") or {}
    if role not in roles:
        raise Refusal(f'{where}: role "{role}" is not defined in this theme '
                      f'(it has: {", ".join(sorted(roles))}).')
    rc = roles[role]
    W, H = brand.size
    margin = {**{"top": 80, "right": 80, "bottom": 80, "left": 80},
              **(theme.get("margin") or {})}
    bg = colour(theme, rc.get("bg", "bg"), f"{where}.bg")

    box = rc.get("box") or {}
    bx = float(box.get("x", margin["left"]))
    by = float(box.get("y", margin["top"]))
    bw = float(box.get("w", W - margin["left"] - margin["right"]))
    bh = float(box.get("h", H - margin["top"] - margin["bottom"]))
    if bx < margin["left"] or by < margin["top"] \
            or bx + bw > W - margin["right"] or by + bh > H - margin["bottom"]:
        raise Refusal(f'{where}: role "{role}" has a text box that starts or ends outside the '
                      f'margins. The box must sit inside them, that is what they are for.')

    findings = []
    blocks, total_h, scale = layout(slide, rc, brand, bw, bh, where)
    for b in blocks:
        b["fill"] = check_contrast(brand, theme, b["cfg"], bg, f"{where}.{b['key']}", findings)

    # Two layers. Panels and the flat colour go on the background; every pixel of type and every
    # rule goes on the ink layer, so the ink bounding box measured afterwards is the truth.
    base = Image.new("RGB", (W, H), bg)
    bd = ImageDraw.Draw(base)
    for i, panel in enumerate(rc.get("panels") or []):
        pc = colour(theme, panel.get("colour", "accent"), f"{where}.panels[{i}]")
        bd.rectangle([float(panel["x"]), float(panel["y"]),
                      float(panel["x"]) + float(panel["w"]) - 1,
                      float(panel["y"]) + float(panel["h"]) - 1], fill=pc)

    ink = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ink)

    anchor = rc.get("anchor", "center")
    if anchor == "center":
        y = by + (bh - total_h) / 2
    elif anchor == "bottom":
        y = by + bh - total_h
    else:
        y = by

    # The rule may sit after any named element, not only at the bottom. "after": "text" on a
    # quote slide puts the hairline between the sentence and its source line, which is where a
    # reader expects it; left at the bottom it reads as an underline on the source instead.
    rule = rc.get("rule") or {}
    rule_on = bool(rule.get("enabled"))
    rule_after = rule.get("after")
    if rule_on and rule_after and rule_after not in [b["key"] for b in blocks]:
        raise Refusal(f'{where}: the rule is set to follow "{rule_after}", which this slide does '
                      f'not carry. Give the rule no "after" to put it at the bottom.')
    rule_drawn = [False]

    def draw_rule(y_at):
        rw, rh = float(rule.get("w", 120)), float(rule.get("h", 4))
        rcol = check_contrast(brand, theme, rule, bg, f"{where}.rule", findings)
        ralign = rule.get("align", "center")
        rx = {"center": bx + bw / 2 - rw / 2, "left": bx, "right": bx + bw - rw}[ralign]
        d.rectangle([rx, y_at, rx + rw - 1, y_at + rh - 1], fill=rcol + (255,))
        rule_drawn[0] = True
        return y_at + rh

    for b in blocks:
        y += b["gap"]
        cfg = b["cfg"]
        align = cfg.get("align", "center")
        x = {"center": bx + bw / 2, "left": bx, "right": bx + bw}[align]
        lh = float(cfg.get("line_height", 1.15))
        for ln in b["lines"]:
            draw_line(d, ln, b["font"], x, y, b["fill"] + (255,), align, b["tracking"])
            y += b["px"] * lh
        if rule_on and rule_after == b["key"]:
            y = draw_rule(y + float(rule.get("gap_before", 40)) * scale)

    if rule_on and not rule_drawn[0]:
        draw_rule(y + float(rule.get("gap_before", 40)) * scale)

    # Page furniture. Each one is drawn only if the role asks for it, which is what lets a cover
    # carry a swipe cue and a final slide not.
    for key in ("footer", "counter", "swipe"):
        want = rc.get(key)
        if not want:
            continue
        cfg = dict(theme.get(key) or {})
        if isinstance(want, dict):
            cfg.update(want)
        if not cfg:
            raise Refusal(f'{where}: role "{role}" asks for "{key}" but neither the theme nor '
                          f'the role defines it.')
        if key == "counter":
            text = str(cfg.get("format", "{n}/{N}")).format(n=index, N=total)
        else:
            text = str(cfg.get("text", ""))
        if not text:
            raise Refusal(f'{where}: "{key}" has no text.')
        fill = check_contrast(brand, theme, cfg, bg, f"{where}.{key}", findings)
        f = brand.font(cfg.get("font", "body"), float(cfg.get("px", 24)), f"{where}.{key}")
        align = cfg.get("align", "center")
        fx = float(cfg["x"]) if "x" in cfg else {"center": W / 2,
                                                 "left": margin["left"],
                                                 "right": W - margin["right"]}[align]
        draw_line(d, text, f, fx, float(cfg.get("y_top", H - margin["bottom"] - 30)),
                  fill + (255,), align, float(cfg.get("tracking", 0.0)))

    base.paste(ink, (0, 0), ink)

    # The proof. Measured from the rasterised alpha, not predicted from metrics.
    bbox = ink.getchannel("A").getbbox()
    if bbox is None:
        raise Refusal(f"{where}: nothing was drawn. A blank slide is never the right answer.")
    l, t, r, btm = bbox
    over = []
    if l < margin["left"]:
        over.append(f"left ink at x={l}, margin {margin['left']}")
    if t < margin["top"]:
        over.append(f"top ink at y={t}, margin {margin['top']}")
    if r > W - margin["right"]:
        over.append(f"right ink at x={r}, margin ends {W - margin['right']}")
    if btm > H - margin["bottom"]:
        over.append(f"bottom ink at y={btm}, margin ends {H - margin['bottom']}")
    if over:
        raise Refusal(f"{where}: INK CROSSES A MARGIN. " + "; ".join(over)
                      + ". This is measured off the rendered pixels, so it is real.")

    report = {
        "where": where, "role": role, "size": [W, H], "scale": round(scale, 3),
        "ink_bbox": [l, t, r, btm],
        "clearance": {"left": l - margin["left"], "top": t - margin["top"],
                      "right": (W - margin["right"]) - r,
                      "bottom": (H - margin["bottom"]) - btm},
        "lines": {b["key"]: len(b["lines"]) for b in blocks},
        "px": {b["key"]: round(b["px"], 1) for b in blocks},
        "contrast": findings,
    }
    return base, report


# ---------------------------------------------------------------- carousel + sheet

def stamp_hold(im, text):
    """Burn a hold bar across the top of a slide.

    WHY THIS EXISTS. A carousel was rendered with HOLD in its folder name and in
    every filename, and nowhere on any pixel. Opened on 2026-10-09 it was a
    finished, polished, post-ready cover with a swipe cue, sitting in an outbox
    beside carousels that really were closer to ready. The folder's README said
    plainly why it was held, and a README is the one thing somebody dragging
    images into a post does not read.

    A marker that lives only in a filename is not a marker. Put it on the pixels.
    """
    from PIL import ImageDraw as _D
    w, h = im.size
    bar_h = max(48, h // 22)
    d = _D.Draw(im, "RGBA")
    d.rectangle([0, 0, w, bar_h], fill=(190, 24, 24, 235))
    f = _pick_font(["Helvetica Bold", "Arial Bold", "HelveticaNeue-Bold"], int(bar_h * 0.44))
    msg = str(text).upper()
    try:
        tw = d.textlength(msg, font=f)
    except Exception:
        tw = len(msg) * bar_h * 0.25
    d.text(((w - tw) / 2, (bar_h - int(bar_h * 0.44)) / 2 - 1), msg, font=f, fill=(255, 255, 255, 255))
    return im


def _pick_font(names, size):
    from PIL import ImageFont
    roots = ["/System/Library/Fonts/Supplemental/", "/System/Library/Fonts/", "/Library/Fonts/"]
    for n in names:
        for r in roots:
            for ext in (".ttf", ".ttc", ".otf"):
                try:
                    return ImageFont.truetype(r + n.replace(" ", "") + ext, size)
                except Exception:
                    pass
    try:
        return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", size)
    except Exception:
        return ImageFont.load_default()


def render_carousel(brand, car, out_dir, stem=None, hold=None):
    theme_name = car.get("theme")
    if not theme_name:
        raise Refusal('carousel file has no "theme". Which brand a slide belongs to is never '
                      'guessed here: name it.')
    theme = brand.theme(theme_name)
    slides = car.get("slides") or []
    if not slides:
        raise Refusal('carousel file has no "slides".')
    stem = stem or car.get("slug") or "carousel"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    total = len(slides)
    written, reports = [], []
    for i, slide in enumerate(slides, start=1):
        where = f"{stem} slide {i:02d}"
        im, rep = render_slide(brand, theme, slide, i, total, where)
        hold_text = hold or car.get("hold")
        if hold_text:
            im = stamp_hold(im, hold_text)
            rep["hold"] = str(hold_text)
        p = out_dir / f"{stem}-{i:02d}.png"
        im.save(p)
        rep["file"] = str(p)
        rep["bytes"] = p.stat().st_size
        if rep["bytes"] < 1000:
            raise Refusal(f"{where}: wrote {p} but it is only {rep['bytes']} bytes. "
                          f"A near empty PNG is a failure however the save call returned.")
        written.append(p)
        reports.append(rep)
    return written, reports


def contact_sheet(pngs, out_path, cols=5, thumb_w=260, pad=14, label=True):
    pngs = list(pngs)
    if not pngs:
        raise Refusal("contact sheet: no PNGs given.")
    ims = []
    for p in pngs:
        im = Image.open(p).convert("RGB")
        tw = thumb_w
        th = max(1, round(im.height * tw / im.width))
        ims.append((Path(p).name, im.resize((tw, th), Image.LANCZOS)))
    cols = max(1, min(cols, len(ims)))
    rows = math.ceil(len(ims) / cols)
    cw = thumb_w
    ch = max(i.height for _, i in ims)
    cap = 22 if label else 0
    W = cols * cw + (cols + 1) * pad
    H = rows * (ch + cap) + (rows + 1) * pad
    sheet = Image.new("RGB", (W, H), (238, 238, 240))
    d = ImageDraw.Draw(sheet)
    try:
        lf = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 13)
    except Exception:
        lf = ImageFont.load_default()
    for k, (name, im) in enumerate(ims):
        r, c = divmod(k, cols)
        x = pad + c * (cw + pad)
        y = pad + r * (ch + cap + pad)
        d.rectangle([x - 1, y - 1, x + cw, y + im.height], outline=(170, 170, 175))
        sheet.paste(im, (x, y))
        if label:
            d.text((x, y + im.height + 4), name, font=lf, fill=(40, 40, 44))
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)
    return out_path, (W, H), len(ims)


SELFTEST_SLIDES = [
    {"role": "cover",
     "text": "This cover headline is deliberately far longer than any real cover headline would "
             "ever be, so that it has to wrap onto many lines and shrink to fit its box, and so "
             "that the margin measurement afterwards has something to measure."},
    {"role": "body",
     "label": "W",
     "text": "This body slide carries a label, a very long main paragraph that must wrap and "
             "shrink, an attribution and a call to action all at once, which is the worst case "
             "for the vertical layout because every element competes for the same box.",
     "question": "And a question line underneath it that is also longer than it should be?",
     "attrib": "A LONG ATTRIBUTION LINE WITH TRACKING APPLIED TO IT",
     "cta": "A call to action that is also too long to sit on one line comfortably."},
    {"role": "final", "text": "Short.", "cta": "One line."},
]


def main():
    ap = argparse.ArgumentParser(description="Brand agnostic carousel renderer.")
    ap.add_argument("--brand")
    ap.add_argument("--carousel")
    ap.add_argument("--out-dir")
    ap.add_argument("--stem")
    ap.add_argument("--hold", metavar="TEXT",
                    help="burn a red hold bar across the top of every slide. A carousel that is "
                         "not cleared to post must say so on the pixels, because a folder name "
                         "and a README do not travel with an image.")
    ap.add_argument("--theme", help="override the carousel file's theme (use with care)")
    ap.add_argument("--selftest", metavar="OUT_DIR",
                    help="render deliberately overlong text in every theme and prove the edges")
    ap.add_argument("--contact-sheet", metavar="OUT_PNG")
    ap.add_argument("--cols", type=int, default=5)
    ap.add_argument("--report", metavar="OUT_JSON")
    ap.add_argument("inputs", nargs="*", help="PNGs or directories, for --contact-sheet")
    a = ap.parse_args()

    try:
        if a.contact_sheet and not a.brand:
            pngs = []
            for i in a.inputs:
                p = Path(i)
                pngs.extend(sorted(p.glob("**/*.png")) if p.is_dir() else [p])
            out, size, n = contact_sheet(pngs, a.contact_sheet, cols=a.cols)
            print(f"contact sheet: {out}  {size[0]}x{size[1]}  {n} slides")
            return 0

        if not a.brand:
            ap.error("--brand is required")
        brand = Brand(a.brand)
        print(f"brand: {brand.name}  canvas {brand.size[0]}x{brand.size[1]}  "
              f"themes: {', '.join(sorted(brand.themes))}")
        print(f"fonts checked and loadable: {', '.join(sorted(brand.fonts_cfg))}")

        all_reports, all_pngs = [], []

        if a.selftest:
            for tname in sorted(brand.themes):
                car = {"theme": tname, "slug": f"selftest-{tname}", "slides": SELFTEST_SLIDES}
                w, r = render_carousel(brand, car, a.selftest, f"selftest-{tname}")
                all_pngs += w
                all_reports += r
                print(f"selftest {tname}: {len(w)} slides, all ink inside the margins")
        elif a.carousel:
            car = json.loads(Path(a.carousel).read_text())
            if a.theme:
                car["theme"] = a.theme
            out_dir = a.out_dir or car.get("out_dir") or "."
            w, r = render_carousel(brand, car, out_dir, a.stem, hold=a.hold)
            all_pngs += w
            all_reports += r
        else:
            ap.error("give --carousel or --selftest")

        for rep in all_reports:
            cl = rep["clearance"]
            print(f"  {Path(rep['file']).name}  {rep['role']:<6} scale {rep['scale']:.2f}  "
                  f"bbox {rep['ink_bbox']}  clearance L{cl['left']} T{cl['top']} "
                  f"R{cl['right']} B{cl['bottom']}  {rep['bytes'] / 1000:.0f} KB")

        worst = min((f["ratio"] for rep in all_reports for f in rep["contrast"]), default=None)
        if worst is not None:
            print(f"lowest contrast ratio anywhere in this run: {worst}:1")

        if a.contact_sheet and all_pngs:
            out, size, n = contact_sheet(all_pngs, a.contact_sheet, cols=a.cols)
            print(f"contact sheet: {out}  {size[0]}x{size[1]}  {n} slides")

        if a.report:
            Path(a.report).parent.mkdir(parents=True, exist_ok=True)
            Path(a.report).write_text(json.dumps(all_reports, indent=2))
            print(f"report: {a.report}")

        print(f"OK: {len(all_pngs)} slides, every one measured inside its margins.")
        return 0

    except Refusal as e:
        sys.stderr.write(f"\ncarousel_render REFUSED:\n  {e}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
