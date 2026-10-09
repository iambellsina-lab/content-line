#!/usr/bin/env python3
"""kit_check.py: run this first. It tells you whether this computer can run the content line.

    python3 bin/kit_check.py                 # every check, including real test renders
    python3 bin/kit_check.py --quick         # skip the test renders and the whisper load
    python3 bin/kit_check.py --offline       # and ask nothing of the network
    python3 bin/kit_check.py --brand specs/yourbrand.json   # also prove YOUR brand file renders
    python3 bin/kit_check.py --require-whisper              # make a missing whisper a FAIL
    python3 bin/kit_check.py --check-model-url              # HEAD the model URL even if it is here

On Windows write `python` instead of `python3`.

Standard library only, so it runs before anything is installed. The file itself parses on
Python 3.6 and newer, so an old Python reports "too old" instead of crashing on syntax.

Each item prints PASS, FAIL, WARN, INFO or SKIP. A FAIL always carries a fix line.
Exit code 0 means no FAIL. Exit code 1 means at least one FAIL. WARN never fails the run.

What it checks, in order:
  1. Python 3.10 or newer (the interpreter running this file)
  2. ffmpeg and ffprobe on PATH, with the libx264 and aac encoders and the mp4 muxer
  3. every ffmpeg filter the scripts use, listing any that are missing
  4. whether drawtext, subtitles and ass exist (INFO only: the kit never uses them)
  5. a Python that has Pillow: the kit's own .venv folder if it exists, else the Python
     running this check
  6. Pillow was built with FreeType (text cannot be drawn without it)
  7. a usable font, and the brand file's font if you pass --brand
  8. the kit scripts are present and parse
  9. whisper-cli and the model file (optional: only the transcription route needs them)
 10. that the model download URL still answers and still serves the number of bytes
     transcribe.py claims. One HEAD request, no download. Skipped when the model is
     already here, and skipped cleanly when there is no network to ask
 11. unless --quick: a real render through make_clip.py with no brand, another with
     specs/example-brand.json (or your --brand), a check that text really appears in the
     frame, a real caption_video.py render, a real assemble_clip.py render of two out of
     order segments with a caption on them, pick_pulls.py on a sample transcript,
     cards_from_srt.py turning that pull into a spec, plan_clips.py and check_dupes.py,
     and a whisper run. All output goes to a temp folder that is removed afterwards.

Nothing here spends money or writes into your project. It touches the network exactly
once, for check 10, to ask the size of a file it does not fetch. --offline turns that off.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
MIN_PY = (3, 10)
IS_WINDOWS = os.name == "nt"
PYCMD = "python" if IS_WINDOWS else "python3"
VENV_PY_REL = os.path.join(".venv", "Scripts", "python") if IS_WINDOWS else os.path.join(".venv", "bin", "python")

# Every ffmpeg filter the scripts name, and WHAT BREAKS without it. The message matters
# more than the list: "missing: maskedmerge" tells a buyer nothing, and "the skin pass,
# which you can switch off" tells them whether to care.
#
# Two tiers. A "hard" filter is one the kit cannot run without, so a missing one is a FAIL.
# An "option" filter is needed by one feature that ships switched off, so a missing one is a
# WARN and the message says which feature goes. assemble_clip.py checks the same four option
# filters itself, at the moment the skin pass is actually asked for.
#
# The message is printed when the filter is MISSING, which is the only time anybody needs
# to read it. The PASS line says how many were checked.
FILTERS = [
    ("overlay", "hard", "no caption or hook card can be drawn onto the picture"),
    ("scale", "hard", "nothing can be reframed to 1080x1920"),
    ("crop", "hard", "a horizontal source cannot be cropped to vertical"),
    ("fps", "hard", "the output cannot be held at a steady 30fps"),
    ("zoompan", "hard", "make_clip.py cannot move across a still image"),
    ("format", "hard", "pixel formats cannot be set, so nothing encodes"),
    ("setpts", "hard", "a segment's timestamps cannot be reset, so a join stalls"),
    ("setsar", "hard", "the output can come out with non square pixels and look stretched"),
    ("volume", "hard", "music cannot be held under speech"),
    ("amix", "hard", "music and speech cannot be mixed together"),
    ("loudnorm", "hard", "audio cannot be normalised to -14 LUFS"),
    ("aresample", "hard", "audio cannot be resampled to 48 kHz"),
    ("anullsrc", "hard", "silent footage cannot be given the silent track an mp4 needs"),
    ("concat", "hard", "assemble_clip.py cannot join one clip's segments, which is the "
                       "whole tool: a clip is several moments played in edit order"),
    ("setparams", "hard", "iPhone HLG footage keeps its HDR tags, so a finished clip looks "
                          "right on a laptop and wrong on a phone. There is no second route: "
                          "the zscale filter most recipes use is absent from stock builds"),
    ("fade", "hard", "caption cards cannot fade in or out, so any style file with "
                     "\"fade_ms\" above 0 fails at the render"),
    ("bilateral", "option", "the skin pass, which does the smoothing itself. Set "
                            "\"skin\": {\"enabled\": false} in your style file and "
                            "everything else in the kit works"),
    ("maskedmerge", "option", "the skin pass, which blends the smoothed picture back "
                              "through its mask instead of flattening the whole frame"),
    ("lutyuv", "option", "the skin pass, which builds its mask with it"),
    ("gblur", "option", "the skin pass, which softens the edge of its mask with it"),
]
REQUIRED_FILTERS = [name for name, tier, _why in FILTERS if tier == "hard"]
OPTIONAL_FILTERS = [name for name, tier, _why in FILTERS if tier == "option"]
FILTER_WHY = dict((name, why) for name, _tier, why in FILTERS)
REQUIRED_ENCODERS = ["libx264", "aac"]
TEXT_FILTERS = ["drawtext", "subtitles", "ass"]
SCRIPTS = ["kit_common.py", "make_clip.py", "caption_video.py", "pick_pulls.py",
           "cards_from_srt.py", "publish_media.py", "transcribe.py", "assemble_clip.py",
           "check_dupes.py", "plan_clips.py", "name_clip.py",
           # Added 2026-10-08 after the first run of the whole chain WITH b-roll. These four
           # are chain steps a buyer runs and none of them was parse checked here. This is a
           # parse check only: no smoke run is claimed for them, and the comment says so on
           # purpose so nobody reads a PASS on this line as "it rendered".
           "caption_check.py", "caption_repair.py", "hear_joins.py", "broll.py"]

# A filename a buyer can live with: lowercase, digits and single hyphens, no edges.
GOOD_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Text that must never survive into a caption, per awkward fixture. A speaker label is not a
# caption, and a card must not carry the words of two people.
FORBIDDEN_IN_CARDS = {"crosstalk.srt": ("ANNA:", "BEN:", ">>"),
                      "junk-cues.srt": ("[MUSIC]", "(applause)")}
MODEL_MIN_BYTES = 50 * 1000 * 1000      # the smallest real whisper.cpp model is about 75 MB
GGML_MAGIC = b"lmgg"                     # the first four bytes of a whisper.cpp ggml model file

STATUSES = []


def report(status, name, detail="", fix=""):
    """Print one result line. A FAIL or WARN may carry a fix, printed beneath it."""
    STATUSES.append(status)
    line = "[%s] %s" % (status, name)
    if detail:
        line += "  " + detail
    print(line)
    sys.stdout.flush()
    if fix and status in ("FAIL", "WARN"):
        parts = fix.split("\n")
        print("       fix: " + parts[0])
        for extra in parts[1:]:
            print("            " + extra)


def run(cmd, timeout=60, cwd=None, env=None):
    """Run a command. Returns (returncode, stdout, stderr). returncode is None if it could not run."""
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             universal_newlines=True, cwd=cwd, env=env)
        try:
            out, err = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            p.communicate()
            return None, "", "timed out after %ss" % timeout
        return p.returncode, out, err
    except (OSError, ValueError) as exc:
        return None, "", str(exc)


def tail(text, n=3):
    lines = [ln for ln in (text or "").strip().splitlines() if ln.strip()]
    return " | ".join(lines[-n:])[:300]


# --------------------------------------------------------------------------- python

def check_python():
    v = sys.version_info
    shown = "%d.%d.%d" % (v[0], v[1], v[2])
    if (v[0], v[1]) >= MIN_PY:
        report("PASS", "Python version", "%s at %s" % (shown, sys.executable))
    else:
        report("FAIL", "Python version",
               "%s at %s, the kit needs %d.%d or newer" % (shown, sys.executable, MIN_PY[0], MIN_PY[1]),
               "Install a current Python: macOS brew install python, Windows python.org (tick 'Add to PATH').\n"
               "Then run this check with it, for example: python3.12 bin/kit_check.py")


# --------------------------------------------------------------------------- ffmpeg

def check_ffmpeg():
    """Returns the ffmpeg path, or None. Reports every ffmpeg related item."""
    ff = shutil.which("ffmpeg")
    fp = shutil.which("ffprobe")
    install = ("macOS: brew install ffmpeg\nWindows: winget install ffmpeg   (or download from ffmpeg.org)\n"
               "Debian or Ubuntu: sudo apt install ffmpeg\n"
               "Then open a NEW terminal window so PATH refreshes.")
    if not ff:
        report("FAIL", "ffmpeg on PATH", "not found", install)
        for name in REQUIRED_ENCODERS:
            report("SKIP", "ffmpeg encoder " + name, "no ffmpeg to ask")
        report("SKIP", "ffmpeg filters", "no ffmpeg to ask")
        report("FAIL" if not fp else "PASS", "ffprobe on PATH",
               fp or "not found", "" if fp else "It ships in the same package as ffmpeg.")
        return None
    rc, out, _ = run([ff, "-version"], 20)
    first = (out or "").splitlines()[0] if out else "version unreadable"
    report("PASS", "ffmpeg on PATH", "%s  (%s)" % (ff, first))

    if fp:
        report("PASS", "ffprobe on PATH", fp)
    else:
        report("FAIL", "ffprobe on PATH", "not found",
               "It ships in the same package as ffmpeg. Reinstall ffmpeg.")

    rc, out, err = run([ff, "-hide_banner", "-encoders"], 30)
    encoders = set()
    for line in (out or "").splitlines():
        m = re.match(r"^\s*[VAS][.FSXBD]{5}\s+(\S+)", line)
        if m:
            encoders.add(m.group(1))
    for name in REQUIRED_ENCODERS:
        if name in encoders:
            report("PASS", "ffmpeg encoder " + name)
        elif name == "libx264":
            report("FAIL", "ffmpeg encoder libx264", "this ffmpeg build cannot write H.264",
                   "Install a full ffmpeg build.\n" + install + "\n"
                   "A minimal or static build without --enable-libx264 will not work.")
        else:
            report("FAIL", "ffmpeg encoder " + name, "missing from this build",
                   "Install a full ffmpeg build.\n" + install)

    rc, out, err = run([ff, "-hide_banner", "-h", "muxer=mp4"], 20)
    if "Muxer mp4" in (out or "") + (err or ""):
        report("PASS", "ffmpeg mp4 muxer")
    else:
        report("FAIL", "ffmpeg mp4 muxer", "cannot write .mp4 files", "Install a full ffmpeg build.")

    rc, out, err = run([ff, "-hide_banner", "-filters"], 30)
    have = set()
    for line in (out or "").splitlines():
        # Rows look like " TS overlay  VV->V  Overlay ...". The flag column is 2 or 3 characters
        # wide depending on the build, so split on whitespace and skip the legend rows ("T.. = ...").
        tokens = line.split()
        if len(tokens) >= 3 and re.match(r"^[TSC.|]+$", tokens[0]) and tokens[1] != "=":
            have.add(tokens[1])
    if not have:
        report("FAIL", "ffmpeg filters", "could not read the filter list: " + tail(err),
               "Reinstall ffmpeg.")
    else:
        install_full = ("Install a full ffmpeg build.\n" + install)
        missing = [f for f in REQUIRED_FILTERS if f not in have]
        if missing:
            # One line per missing filter, each saying what stops working. A single
            # "missing: a, b, c" line is what this used to print and it told nobody
            # whether their build was unusable or just missing a feature they never use.
            for name in missing:
                report("FAIL", "ffmpeg filter " + name, "missing from this build. Without "
                       "it, " + FILTER_WHY[name], install_full)
        else:
            report("PASS", "ffmpeg filters",
                   "all %d the kit needs are present (of %d in this build)"
                   % (len(REQUIRED_FILTERS), len(have)))
        absent_opt = [f for f in OPTIONAL_FILTERS if f not in have]
        if absent_opt:
            for name in absent_opt:
                report("WARN", "ffmpeg filter " + name,
                       "missing. It is needed only by " + FILTER_WHY[name],
                       install_full)
        else:
            report("PASS", "ffmpeg filters for the skin pass",
                   "%s all present" % ", ".join(OPTIONAL_FILTERS))
        absent = [f for f in TEXT_FILTERS if f not in have]
        present = [f for f in TEXT_FILTERS if f in have]
        report("INFO", "ffmpeg text filters",
               "absent: %s | present: %s | the kit draws text with Pillow and uses none of them"
               % (", ".join(absent) or "none", ", ".join(present) or "none"))
    return ff


# --------------------------------------------------------------------------- Python with Pillow

def venv_python(venv_dir):
    for rel in (("bin", "python"), ("Scripts", "python.exe")):
        p = os.path.join(venv_dir, *rel)
        if os.path.exists(p):
            return p
    return None


PROBE_SNIPPET = (
    "import json,sys\n"
    "d={'py':list(sys.version_info[:3])}\n"
    "try:\n"
    "    import PIL\n"
    "    from PIL import features\n"
    "    d['pillow']=PIL.__version__\n"
    "    d['freetype']=bool(features.check('freetype2'))\n"
    "except Exception as e:\n"
    "    d['pillow_error']=repr(e)\n"
    "print(json.dumps(d))\n"
)


def make_venv_fix(rel):
    return ("%s -m venv %s   (use a Python %d.%d or newer)\n%s -m pip install -r requirements.txt\n"
            "or run the setup script that came with the kit."
            % (PYCMD, rel, MIN_PY[0], MIN_PY[1], os.path.join(rel, "Scripts" if IS_WINDOWS else "bin", "python")))


def probe_python(py):
    rc, out, err = run([py, "-c", PROBE_SNIPPET], 60)
    if rc is None or rc != 0:
        return None, tail(err) or "no output"
    try:
        return json.loads(out.strip().splitlines()[-1]), ""
    except (ValueError, IndexError):
        return None, "unreadable probe output: " + tail(out)


def judge_pillow(info, py, fix_prefix):
    pv = tuple(info["py"])
    shown = "%d.%d.%d" % pv
    if pv[:2] >= MIN_PY:
        report("PASS", "Python with Pillow", "%s runs Python %s" % (py, shown))
    else:
        report("FAIL", "Python with Pillow", "%s runs Python %s, need %d.%d or newer" % (py, shown, MIN_PY[0], MIN_PY[1]),
               fix_prefix)
    if "pillow_error" in info:
        report("FAIL", "Pillow installed", info["pillow_error"],
               "%s -m pip install -r requirements.txt" % py)
        return False
    report("PASS", "Pillow installed", "Pillow " + info["pillow"])
    if info.get("freetype"):
        report("PASS", "Pillow FreeType support", "text can be drawn")
        return True
    report("FAIL", "Pillow FreeType support",
           "this Pillow was built without FreeType, so it cannot draw text",
           "%s -m pip install --force-reinstall --no-cache-dir pillow" % py)
    return False


def find_python(venv_dir, venv_given):
    """Returns the python to use, or None. Prefers the kit's .venv, falls back to this Python."""
    rel = os.path.relpath(venv_dir)
    if rel.startswith(".."):
        rel = venv_dir
    fix_prefix = "Recreate it with a newer Python:\n" + make_venv_fix(rel)
    py = venv_python(venv_dir) if os.path.isdir(venv_dir) else None
    if py:
        info, why = probe_python(py)
        if info is None:
            report("FAIL", "Python with Pillow",
                   "%s will not run (%s). A .venv copied from another computer points at a Python "
                   "that is not here." % (py, why),
                   "Delete the .venv folder and make a new one:\n" + make_venv_fix(rel))
            return None
        return py if judge_pillow(info, py, fix_prefix) else None
    if venv_given:
        report("FAIL", "Python with Pillow", "%s does not exist or has no python in it" % venv_dir,
               make_venv_fix(rel))
        return None
    info, why = probe_python(sys.executable)
    if info is not None and "pillow_error" not in info:
        report("INFO", "kit .venv", "none found, using the Python running this check instead")
        return sys.executable if judge_pillow(info, sys.executable, fix_prefix) else None
    report("FAIL", "Python with Pillow",
           "no .venv folder in the kit, and the Python running this check does not have Pillow",
           make_venv_fix(rel))
    report("SKIP", "Pillow FreeType support", "no Pillow")
    return None


FONT_SNIPPET = (
    "import sys\n"
    "sys.path.insert(0, %r)\n"
    "import make_clip\n"
    "print(make_clip.pick_font(%r))\n"
)


def check_font(py, brand_arg):
    font_hint = None
    if brand_arg:
        try:
            with open(brand_arg, encoding="utf-8-sig") as fh:
                font_hint = json.load(fh).get("font")
        except (OSError, ValueError) as exc:
            report("FAIL", "brand file", "%s could not be read (%s)" % (brand_arg, exc),
                   "Check the path, and that the file is valid JSON.")
            return
        if font_hint and not os.path.isabs(font_hint):
            cand = os.path.join(os.path.dirname(os.path.abspath(brand_arg)), font_hint)
            if os.path.exists(cand):
                font_hint = cand
    rc, out, err = run([py, "-c", FONT_SNIPPET % (HERE, font_hint)], 30)
    got = out.strip().splitlines()[-1] if out.strip() else ""
    if rc == 0 and got:
        if font_hint and got != font_hint:
            report("WARN", "brand font", "%s was not found, a fallback would be used: %s" % (font_hint, got),
                   'Set "font" in your brand file to a real .ttf or .otf file.')
        else:
            report("PASS", "usable font", ("brand font loads: " if font_hint else "found: ") + got)
    else:
        report("FAIL", "usable font", "no font could be found on this computer",
               tail(err, 12).replace(" | ", "\n") or "Put a .ttf file in the kit folder and set \"font\" in your brand file.")


def check_scripts(py):
    snippet = "import ast,sys\nast.parse(open(sys.argv[1], encoding='utf-8').read())\n"
    bad = []
    for name in SCRIPTS:
        path = os.path.join(HERE, name)
        if not os.path.exists(path):
            bad.append(name + " (missing)")
            continue
        rc, out, err = run([py, "-c", snippet, path], 30)
        if rc != 0:
            bad.append("%s (%s)" % (name, tail(err, 1)))
    if bad:
        report("FAIL", "kit scripts", "; ".join(bad),
               "Re-copy the bin folder from the kit. All the scripts must sit together.")
    else:
        report("PASS", "kit scripts", "%s present and parse" % ", ".join(SCRIPTS))


# --------------------------------------------------------------------------- whisper

def check_whisper(model_arg, whisper_arg, required):
    """Returns (whisper_path, model_path) with None for whichever failed.
    Whisper is optional (only the transcription route uses it), so a miss is a WARN unless
    --require-whisper was given."""
    miss = "FAIL" if required else "WARN"
    cli = whisper_arg or os.environ.get("KIT_WHISPER_CLI") or shutil.which("whisper-cli")
    cli_ok = None
    if not cli or not (os.path.isabs(cli) and os.path.exists(cli) or shutil.which(cli)):
        report(miss, "whisper-cli on PATH", "not found (optional: only needed to transcribe your own recordings)",
               "macOS: brew install whisper.cpp\n"
               "Windows and Linux: download or build whisper.cpp and put the whisper-cli program on PATH.\n"
               "Then check it with: whisper-cli --help")
    else:
        rc, out, err = run([cli, "--help"], 30)
        text = (out or "") + (err or "")
        if rc is None:
            report(miss, "whisper-cli on PATH", "found at %s but will not run: %s" % (cli, tail(err, 1)),
                   "Reinstall it. On macOS: brew reinstall whisper.cpp")
        elif "usage" in text.lower() or rc == 0:
            report("PASS", "whisper-cli on PATH", cli)
            cli_ok = cli
        else:
            report(miss, "whisper-cli on PATH", "ran but did not print usage: " + tail(text, 2),
                   "Reinstall it. On macOS: brew reinstall whisper.cpp")

    model = model_arg or os.environ.get("KIT_WHISPER_MODEL") or os.path.join(KIT, "models", "ggml-base.en.bin")
    model_ok = None
    fix = ("Download a whisper.cpp ggml model file and save it there. English only: ggml-base.en.bin\n"
           "(about 148 MB). Source: the ggerganov/whisper.cpp page on huggingface.co.\n"
           "Or point at one you already have: --model /path/to/ggml-base.en.bin")
    if not os.path.isfile(model):
        report(miss, "whisper model file", "not found: " + model + " (optional, same as above)", fix)
    else:
        size = os.path.getsize(model)
        with open(model, "rb") as fh:
            head = fh.read(4)
        mb = "%.0f MB" % (size / 1e6) if size >= 1e6 else "%d bytes" % size
        if size < MODEL_MIN_BYTES:
            report(miss, "whisper model file",
                   "%s is only %s, a real model is over 70 MB. The download was cut short or it saved an error page."
                   % (model, mb), fix)
        elif head != GGML_MAGIC:
            report(miss, "whisper model file",
                   "%s (%s) does not start with the ggml header, found %r" % (model, mb, head),
                   "It is not a whisper.cpp ggml model. " + fix)
        else:
            note = ""
            if ".en" not in os.path.basename(model):
                note = "  (multilingual model: slower, and the caption tools assume English)"
            report("PASS", "whisper model file", "%s  %s, ggml header ok%s" % (model, mb, note))
            model_ok = model
    return cli_ok, model_ok


# --------------------------------------------------------------------------- the model URL
#
# The 148 MB model download had never been exercised. Only the REFUSAL path had: it prints
# the size and the URL and exits without fetching, and every test pointed at a model that
# already existed. So nobody knew whether the URL still served the file, or whether the
# size transcribe.py claims is still the size on the other end.
#
# This asks, without downloading: one HEAD request, no body. It reads the URL and the byte
# count out of bin/transcribe.py rather than restating them, because a second copy of a
# number is a second thing to get wrong. If the network cannot answer, it SKIPS and says
# how to check by hand. An offline machine is not a broken machine.

HEAD_TIMEOUT = 25
STATUS_LINE = re.compile(r"^\s*HTTP/[\d.]+\s+(\d{3})", re.M)
LENGTH_LINE = re.compile(r"^\s*(content-length|x-linked-size)\s*:\s*(\d+)", re.M | re.I)


def transcribe_constants():
    """MODEL_URL and MODEL_BYTES as bin/transcribe.py itself states them.

    Read out of the source rather than imported: this file is standard library only and
    runs before anything is installed, and importing a sibling script to read two
    constants is a lot of machinery for two constants.
    """
    import ast
    path = os.path.join(HERE, "transcribe.py")
    url, size = None, None
    try:
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
    except (OSError, SyntaxError, ValueError):
        return None, None
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                continue
            if target.id == "MODEL_URL" and isinstance(value, str):
                url = value
            elif target.id == "MODEL_BYTES" and isinstance(value, int):
                size = value
    return url, size


def head_request(url):
    """(status, bytes, how, note). status is None when the question could not be asked.

    curl first, because curl is what transcribe.py uses for the download itself: if curl
    cannot reach the URL, neither will the download, whatever Python thinks.
    """
    curl = shutil.which("curl")
    if curl:
        rc, out, err = run([curl, "-sSIL", "--max-time", str(HEAD_TIMEOUT), url],
                           HEAD_TIMEOUT + 10)
        if rc == 0 and out:
            codes = STATUS_LINE.findall(out)
            lengths = LENGTH_LINE.findall(out)
            size = int(lengths[-1][1]) if lengths else None
            return (int(codes[-1]) if codes else None), size, "curl HEAD", ""
        return None, None, "curl HEAD", tail(err or out, 2) or "curl exited %s" % rc

    wget = shutil.which("wget")
    if wget:
        rc, out, err = run([wget, "--spider", "--server-response", "--tries=1",
                            "--timeout=%d" % HEAD_TIMEOUT, url], HEAD_TIMEOUT + 10)
        text = (err or "") + (out or "")       # wget writes its headers to stderr
        codes = STATUS_LINE.findall(text)
        lengths = LENGTH_LINE.findall(text)
        if codes:
            return int(codes[-1]), (int(lengths[-1][1]) if lengths else None), \
                "wget --spider", ""
        return None, None, "wget --spider", tail(text, 2) or "wget exited %s" % rc

    try:
        import urllib.request
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=HEAD_TIMEOUT) as resp:
            size = resp.headers.get("Content-Length") or resp.headers.get("x-linked-size")
            return int(getattr(resp, "status", 200) or 200), \
                (int(size) if size and size.isdigit() else None), "python HEAD", ""
    except Exception as exc:                   # noqa: BLE001  any network fault is a SKIP
        return None, None, "python HEAD", "%s: %s" % (type(exc).__name__, exc)


def check_model_url(model_present, required, offline, force):
    """Is the model still where transcribe.py says it is, and still the size it claims?"""
    name = "whisper model download URL"
    url, claimed = transcribe_constants()
    if not url:
        report("WARN", name, "could not read MODEL_URL out of bin/transcribe.py",
               "Re-copy bin/transcribe.py from the kit.")
        return
    byhand = "Check it by hand with:  curl -sIL %s | head -1" % url
    if offline:
        report("SKIP", name, "--offline was given, so nothing was asked of the network")
        return
    if model_present and not force:
        report("SKIP", name, "the model is already on this machine, so nothing needs "
                             "downloading. --check-model-url asks anyway")
        return

    status, size, how, note = head_request(url)
    if status is None:
        report("SKIP", name, "could not be checked from here (%s: %s). Nothing is wrong "
                             "with the kit if this machine is offline." % (how, note),
               byhand)
        return
    if status >= 400:
        report("FAIL" if required else "WARN", name,
               "%s answered HTTP %d, so the download would fail" % (url, status),
               "The model has moved. Fetch ggml-base.en.bin by hand from the\n"
               "ggerganov/whisper.cpp page on huggingface.co, save it as\n"
               "models/ggml-base.en.bin, and run this check again.")
        return
    if size is None:
        report("WARN", name, "reachable (HTTP %d by %s) but the server did not say how "
                             "big the file is" % (status, how),
               "Nothing is broken. The download will run, it just cannot be sized first.")
        return
    shown = "%.0f MB" % (size / 1e6)
    if claimed and size != claimed:
        report("WARN", name,
               "reachable, but it is %d bytes (%s) and transcribe.py claims %d. Nothing "
               "was downloaded." % (size, shown, claimed),
               "The file on the other end changed. The download still works; the size it\n"
               "prints first is now wrong. MODEL_BYTES in bin/transcribe.py needs updating\n"
               "to %d." % size)
        return
    report("PASS", name, "reachable, %s, %d bytes, which is what transcribe.py claims. "
                         "Checked with a %s, nothing was downloaded." % (shown, size, how))


# --------------------------------------------------------------------------- real runs

def probe_video(ffprobe, path):
    rc, out, err = run([ffprobe, "-v", "error", "-show_entries",
                        "stream=codec_type,codec_name,profile,pix_fmt,width,height,"
                        "r_frame_rate,sample_rate,channels,color_transfer,color_primaries",
                        "-of", "json", path], 30)
    if rc != 0:
        return None
    try:
        return json.loads(out).get("streams", [])
    except ValueError:
        return None


INK_SNIPPET = (
    "import sys\n"
    "from PIL import Image\n"
    "im = Image.open(sys.argv[1]).convert('RGB')\n"
    "w, h = im.size\n"
    "bg = im.getpixel((8, 8))\n"
    "px = im.load()\n"
    "n = 0\n"
    "for y in range(0, h, 2):\n"
    "    for x in range(0, w, 2):\n"
    "        p = px[x, y]\n"
    "        if abs(p[0]-bg[0]) + abs(p[1]-bg[1]) + abs(p[2]-bg[2]) > 150:\n"
    "            n += 1\n"
    "print(n)\n"
)


def ink_pixels(py, ffmpeg, video, tmp, at):
    """Pull one frame and count the pixels that differ strongly from the background corner.
    A video whose text silently failed to draw has almost none."""
    png = os.path.join(tmp, "frame-%s.png" % str(at).replace(".", "_"))
    rc, out, err = run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-ss", str(at), "-i", video,
                        "-frames:v", "1", png], 60)
    if rc != 0 or not os.path.exists(png):
        return None
    rc, out, err = run([py, "-c", INK_SNIPPET, png], 60)
    try:
        return int(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None


MEAN_SNIPPET = (
    "import sys\n"
    "from PIL import Image\n"
    "im = Image.open(sys.argv[1]).convert('RGB')\n"
    "w, h = im.size\n"
    "px = im.load()\n"
    "r = g = b = n = 0\n"
    # The top two thirds only: the caption band is in the lower third and its white type
    # would pull the average towards grey.
    "for y in range(0, (h * 2) // 3, 8):\n"
    "    for x in range(0, w, 8):\n"
    "        p = px[x, y]\n"
    "        r += p[0]; g += p[1]; b += p[2]; n += 1\n"
    "print('%d %d %d' % (r // n, g // n, b // n))\n"
)


def media_duration(ffprobe, path):
    rc, out, _err = run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                         "-of", "default=nw=1:nk=1", path], 30)
    try:
        return float((out or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None


def frame_tint(py, ffmpeg, video, tmp, at, tag):
    """The average colour of one frame's top two thirds, as (r, g, b)."""
    png = os.path.join(tmp, "tint-%s.png" % tag)
    rc, _out, _err = run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-ss", str(at),
                          "-i", video, "-frames:v", "1", png], 60)
    if rc != 0 or not os.path.exists(png):
        return None
    rc, out, _err = run([py, "-c", MEAN_SNIPPET, png], 60)
    try:
        return [int(v) for v in out.strip().splitlines()[-1].split()]
    except (ValueError, IndexError):
        return None


# The real renderer, run for real. Until this existed, kit_check parsed assemble_clip.py and
# never executed it, so a thin ffmpeg build passed preflight and failed at the buyer's first
# render. It added 3 seconds to this check, measured on 2026-10-08, and proves five things:
#
#   1. the two stage render completes and writes a file with bytes in it
#   2. the file is as long as the cut list said, to a tenth of a second
#   3. it comes out in the delivery format, 1080x1920 h264 with 48 kHz aac
#   4. the colour fix fires: the source is tagged HLG the way an iPhone tags it, and the
#      output has to come back bt709
#   5. EDIT ORDER, which is the one thing the whole kit exists to do. The source is red for
#      its first half and blue for its second. The cut list asks for the blue half FIRST.
#      If the finished clip opens red, the renderer put the segments back in tape order,
#      which is the exact fault that forced six finished videos to be rebuilt.
ASSEMBLE_SECONDS = 2.0          # the finished test clip
ASSEMBLE_STYLE = {"name": "kit_check", "font": None, "text_color": "#FFFFFF",
                  "accent": "#FFFFFF", "fade_ms": 120, "color_fix": "auto",
                  "grade": {"enabled": False}, "skin": {"enabled": False},
                  "export": {"video_bitrate": "4M", "intermediate_crf": 20}}


def assemble_probe(ffmpeg, ffprobe, py, tmp):
    out_dir = os.path.join(tmp, "assembled")
    out = os.path.join(out_dir, "assemble-check.mp4")
    src = os.path.join(tmp, "two-tone.mp4")

    # Two flat colours, four seconds, with the HDR tags an iPhone writes. setparams is used
    # to tag it because output flags do not take, which is the finding recorded in
    # assemble_clip.py's own comment and was checked again here on 2026-10-08.
    rc, _out, err = run([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=red:size=720x1280:rate=30",
        "-f", "lavfi", "-i", "color=c=blue:size=720x1280:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=48000",
        "-filter_complex",
        "[0:v]trim=duration=2,setpts=PTS-STARTPTS[a];"
        "[1:v]trim=duration=2,setpts=PTS-STARTPTS[b];"
        "[a][b]concat=n=2:v=1:a=0,"
        "setparams=color_primaries=bt2020:color_trc=arib-std-b67:colorspace=bt2020nc[v]",
        "-map", "[v]", "-map", "2:a", "-t", "4",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", src], 120)
    if rc != 0 or not os.path.exists(src):
        report("SKIP", "test render: assemble_clip.py",
               "could not build the two tone test source: " + tail(err, 2))
        return

    style_path = os.path.join(tmp, "assemble-style.json")
    with open(style_path, "w") as fh:
        json.dump(ASSEMBLE_STYLE, fh)
    cuts = {"source": src, "out_dir": out_dir, "times": "clip", "keep_audio": False,
            "pieces": [{"piece": "kitcheck", "filename": "assemble-check",
                        "duration": ASSEMBLE_SECONDS,
                        "segments": [{"start": 2.6, "end": 3.6,
                                      "note": "the second half of the tape, playing FIRST"},
                                     {"start": 0.4, "end": 1.4,
                                      "note": "the first half of the tape, playing second"}],
                        "cards": [{"text": "captions burn in", "start": 0.2, "end": 1.6}]}]}
    cuts_path = os.path.join(tmp, "assemble-cuts.json")
    with open(cuts_path, "w") as fh:
        json.dump(cuts, fh)

    rc, sout, err = run([py, os.path.join(HERE, "assemble_clip.py"), cuts_path,
                         "--style", style_path], 300, cwd=tmp)
    size = os.path.getsize(out) if os.path.exists(out) else 0
    if rc != 0 or not size:
        report("FAIL", "test render: assemble_clip.py",
               ("wrote nothing" if rc == 0 else "exited %s" % rc) + ": " + tail(err or sout, 6),
               "Read the error above. This is the renderer the whole kit ends with: a\n"
               "missing concat, setparams or fade filter, or a Pillow without FreeType,\n"
               "stops it. Run it by hand on specs/example-edit.json to see the full output.")
        return

    dur = media_duration(ffprobe, out) if ffprobe else None
    streams = probe_video(ffprobe, out) if ffprobe else None
    v = next((s for s in (streams or []) if s.get("codec_type") == "video"), None)
    a = next((s for s in (streams or []) if s.get("codec_type") == "audio"), None)
    if dur is None or abs(dur - ASSEMBLE_SECONDS) > 0.1:
        report("FAIL", "test render: assemble_clip.py",
               "the cut list asked for %.2fs and the file is %s"
               % (ASSEMBLE_SECONDS, "unreadable" if dur is None else "%.2fs" % dur),
               "The segments were trimmed or padded. Report this with the cut list.")
    elif not (v and v.get("codec_name") == "h264"
              and (v.get("width"), v.get("height")) == (1080, 1920)
              and v.get("r_frame_rate") == "30/1"
              and a and a.get("codec_name") == "aac" and str(a.get("sample_rate")) == "48000"):
        report("FAIL", "test render: assemble_clip.py",
               "rendered %.2fs but not in the delivery format: video=%s audio=%s" % (dur, v, a),
               "Expected h264 1080x1920 30fps with aac at 48000 Hz.")
    else:
        report("PASS", "test render: assemble_clip.py",
               "2 out of order segments and 1 card became %.2fs of 1080x1920 h264, "
               "%.2f MB" % (dur, size / 1e6))

    # The colour fix. The source claims HLG, so the output must not.
    if not v:
        report("SKIP", "assemble_clip.py colour fix", "could not read the output's streams")
    elif v.get("color_transfer") == "bt709" and v.get("color_primaries") == "bt709":
        report("PASS", "assemble_clip.py colour fix",
               "source tagged arib-std-b67 / bt2020 came out bt709 / bt709")
    else:
        report("FAIL", "assemble_clip.py colour fix",
               "the output still reads %s / %s, so an HLG source stays tagged HDR"
               % (v.get("color_transfer"), v.get("color_primaries")),
               "setparams did not fire. Check \"color_fix\" in the style file is \"auto\" "
               "or \"on\", and that this ffmpeg has the setparams filter.")

    # Edit order, which is the point of the tool.
    first = frame_tint(py, ffmpeg, out, tmp, 0.3, "first")
    second = frame_tint(py, ffmpeg, out, tmp, ASSEMBLE_SECONDS - 0.3, "second")
    if not first or not second:
        report("SKIP", "assemble_clip.py plays EDIT order, not tape order",
               "could not pull frames to look at")
    elif first[2] > first[0] and second[0] > second[2]:
        report("PASS", "assemble_clip.py plays EDIT order, not tape order",
               "the clip opens on tape second 2.6 and closes on tape second 0.4, "
               "as the cut list asked")
    else:
        report("FAIL", "assemble_clip.py plays EDIT order, not tape order",
               "the cut list put the LATER half of the tape first and the render did not: "
               "the opening frame reads rgb%s and the closing frame rgb%s" % (first, second),
               "The segments came out in tape order. That is the fault that forced six\n"
               "finished videos to be rebuilt, and it is what this tool exists to prevent.\n"
               "Do not render a batch until this passes.")


def render_probe(label, spec, tmp, py, ffmpeg, ffprobe, name, at):
    spec_path = os.path.join(tmp, name + ".json")
    with open(spec_path, "w") as fh:
        json.dump(spec, fh)
    rc, out, err = run([py, os.path.join(HERE, "make_clip.py"), spec_path], 180, cwd=tmp)
    if rc != 0 or not os.path.exists(spec["out"]):
        report("FAIL", "test render: " + label, tail(err or out, 6),
               "Read the error above. Common causes: no usable font, Pillow without FreeType, or an ffmpeg missing a filter.")
        return
    st = probe_video(ffprobe, spec["out"]) if ffprobe else None
    v = next((s for s in (st or []) if s.get("codec_type") == "video"), None)
    if not (v and v.get("codec_name") == "h264" and v.get("profile") == "High"
            and v.get("pix_fmt") == "yuv420p" and (v.get("width"), v.get("height")) == (1080, 1920)
            and v.get("r_frame_rate") == "30/1"):
        report("FAIL", "test render: " + label, "rendered but the file is not the delivery format: %s" % v,
               "Expected h264 High yuv420p 1080x1920 30fps. Check the ffmpeg build.")
        return
    report("PASS", "test render: " + label,
           "h264 High, yuv420p, 1080x1920, 30fps, %.2f MB" % (os.path.getsize(spec["out"]) / 1e6))
    n = ink_pixels(py, ffmpeg, spec["out"], tmp, at)
    if n is None:
        report("SKIP", "text drew in the frame: " + label, "could not pull a frame to look at")
    elif n > 400:
        report("PASS", "text drew in the frame: " + label, "%d text pixels found in a frame at %ss" % (n, at))
    else:
        report("FAIL", "text drew in the frame: " + label,
               "only %d text pixels in a frame at %ss, so the captions did not draw" % (n, at),
               "The video was made but is blank. Check Pillow FreeType support and the font above.")


def smoke(ffmpeg, py, whisper, model, brand_arg):
    ffprobe = shutil.which("ffprobe")
    tmp = tempfile.mkdtemp(prefix="kitcheck-")
    try:
        # 1. make_clip.py with no brand at all: the neutral defaults must still render
        render_probe("make_clip.py, no brand file",
                     {"out": os.path.join(tmp, "plain.mp4"),
                      "cards": [{"text": "Kit check", "start": 0.0, "end": 0.9},
                                {"text": "passes", "start": 0.9, "end": 1.8, "accent": ["passes"]}]},
                     tmp, py, ffmpeg, ffprobe, "plain", 0.45)

        # 2. make_clip.py with a brand file: the example one, or the user's own
        brand = brand_arg or os.path.join(KIT, "specs", "example-brand.json")
        if os.path.isfile(brand):
            render_probe("make_clip.py, brand file " + os.path.basename(brand),
                         {"brand": os.path.abspath(brand), "out": os.path.join(tmp, "branded.mp4"),
                          "cards": [{"text": "Your brand", "start": 0.0, "end": 0.9},
                                    {"text": "renders", "start": 0.9, "end": 1.8, "accent": ["renders"]}]},
                         tmp, py, ffmpeg, ffprobe, "branded", 0.45)
        else:
            report("SKIP", "test render: brand file", "no brand file at " + brand)

        # 3. a source clip with picture and sound, made by ffmpeg itself
        src = os.path.join(tmp, "source.mp4")
        rc, out, err = run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                            "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30",
                            "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=48000",
                            "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", src], 120)
        if rc != 0:
            report("SKIP", "test render: caption_video.py", "could not make a test source: " + tail(err, 1))
        else:
            cspec = {"source": src, "out": os.path.join(tmp, "captioned.mp4"),
                     "cards": [{"text": "Captions burn in", "start": 0.3, "end": 2.2}]}
            cpath = os.path.join(tmp, "captioned.json")
            with open(cpath, "w") as fh:
                json.dump(cspec, fh)
            rc, out, err = run([py, os.path.join(HERE, "caption_video.py"), cpath], 180, cwd=tmp)
            if rc != 0 or not os.path.exists(cspec["out"]):
                report("FAIL", "test render: caption_video.py", tail(err or out, 6),
                       "Read the error above. This path needs the crop, loudnorm and aresample filters.")
            else:
                st = probe_video(ffprobe, cspec["out"]) if ffprobe else None
                v = next((s for s in (st or []) if s.get("codec_type") == "video"), None)
                a = next((s for s in (st or []) if s.get("codec_type") == "audio"), None)
                good = (v and v.get("codec_name") == "h264" and (v.get("width"), v.get("height")) == (1080, 1920)
                        and a and a.get("codec_name") == "aac" and str(a.get("sample_rate")) == "48000")
                if good:
                    report("PASS", "test render: caption_video.py",
                           "1280x720 source became 1080x1920 h264 with aac 48000 Hz audio")
                else:
                    report("FAIL", "test render: caption_video.py",
                           "rendered but wrong format: video=%s audio=%s" % (v, a),
                           "Check the ffmpeg build against the filters listed above.")

        # 3b. assemble_clip.py, for real. It was in the SCRIPTS list and never run.
        assemble_probe(ffmpeg, ffprobe, py, tmp)

        # 4. pick_pulls.py on the sample transcript
        fixture = None
        for cand in (os.path.join(KIT, "specs", "sample-transcript.srt"),
                     os.path.join(KIT, "fixtures", "fake-podcast-ep.srt")):
            if os.path.exists(cand):
                fixture = cand
                break
        if not fixture:
            report("SKIP", "test run: pick_pulls.py", "no sample transcript in specs/ or fixtures/")
        else:
            rc, out, err = run([py, os.path.join(HERE, "pick_pulls.py"), fixture, "-n", "1"], 60)
            try:
                pulls = json.loads(out).get("pulls", []) if rc == 0 else None
            except ValueError:
                pulls = None
            if pulls:
                p = pulls[0]
                report("PASS", "test run: pick_pulls.py",
                       "returned a pull of %.0f seconds from the sample transcript" % p.get("duration", 0))
            else:
                report("FAIL", "test run: pick_pulls.py", tail(err or out) or "returned no pulls",
                       "Run it by hand: %s bin/pick_pulls.py %s" % (PYCMD, fixture))

        # 5. cards_from_srt.py turns that pull into a spec caption_video.py can read
        if not fixture or not pulls:
            report("SKIP", "test run: cards_from_srt.py", "no sample transcript, or no pull to cut up")
        else:
            pull = pulls[0]
            rc, out, err = run([py, os.path.join(HERE, "cards_from_srt.py"), fixture,
                                "--start", str(pull["start"]), "--end", str(pull["end"]),
                                "--source", src, "--print"], 60)
            try:
                spec = json.loads(out) if rc == 0 else None
            except ValueError:
                spec = None
            cards = (spec or {}).get("cards") or []
            trim = (spec or {}).get("trim") or {}
            if not cards:
                report("FAIL", "test run: cards_from_srt.py", tail(err or out) or "wrote no cards",
                       "Run it by hand: %s bin/cards_from_srt.py %s --start %s --end %s --print"
                       % (PYCMD, fixture, pull["start"], pull["end"]))
            else:
                loose = [c for c in cards
                         if c["start"] < trim.get("start", 0) - 0.01
                         or c["end"] > trim.get("end", 0) + 0.01
                         or c["end"] <= c["start"]]
                longest = max(len(c["text"].split()) for c in cards)
                if loose:
                    report("FAIL", "test run: cards_from_srt.py",
                           "%d card(s) fall outside the trim or end before they start" % len(loose),
                           "caption_video.py would drop or clamp them. Report this with the transcript.")
                else:
                    report("PASS", "test run: cards_from_srt.py",
                           "%d cards, at most %d words each, all inside the %.0fs pull"
                           % (len(cards), longest, trim.get("end", 0) - trim.get("start", 0)))

        # 5b. plan_clips.py builds a clip out of non-adjacent moments, and check_dupes.py
        #     catches two clips that share tape. Both are text only, so they cost nothing to run.
        if not fixture:
            report("SKIP", "test run: plan_clips.py", "no sample transcript")
        else:
            cuts = os.path.join(tmp, "assembled.json")
            rc, out, err = run([py, os.path.join(HERE, "plan_clips.py"), fixture,
                                "-n", "2", "--min", "20", "--max", "150", "--out", cuts], 90)
            built = None
            if os.path.exists(cuts):
                try:
                    built = json.load(open(cuts, encoding="utf-8")).get("pieces")
                except ValueError:
                    built = None
            if not built:
                report("WARN", "test run: plan_clips.py",
                       tail(err or out) or "built no clip from the sample transcript",
                       "The sample may be too short or too much on one subject. Run it by hand: "
                       "%s bin/plan_clips.py %s -n 2 --min 20" % (PYCMD, fixture))
            else:
                multi = [b for b in built if len(b.get("segments") or []) > 1]
                nonlin = 0
                for b in built:
                    segs = b.get("segments") or []
                    if any(segs[k + 1]["start"] < segs[k]["start"] for k in range(len(segs) - 1)):
                        nonlin += 1
                if not multi:
                    report("FAIL", "test run: plan_clips.py",
                           "every clip came back as a single segment, so nothing was assembled",
                           "That is pick_pulls.py's job, not this one. Report it with the transcript.")
                else:
                    report("PASS", "test run: plan_clips.py",
                           "%d clip(s), %d with several segments, %d in a non-tape order"
                           % (len(built), len(multi), nonlin))
                # check_dupes must pass on this list, because one run never spends a moment twice
                rc, out, err = run([py, os.path.join(HERE, "check_dupes.py"), cuts], 60)
                if rc != 0:
                    report("FAIL", "test run: check_dupes.py",
                           "two clips from one plan_clips.py run share tape, which cannot happen "
                           "if a moment is spent once", tail(out))
                else:
                    # and it must FAIL when the same clip is handed to it twice
                    twice = os.path.join(tmp, "duplicated.json")
                    one = dict(built[0])
                    other = dict(built[0])
                    other["filename"] = (one.get("filename") or "clip") + "-copy"
                    json.dump({"pieces": [one, other]}, open(twice, "w", encoding="utf-8"))
                    rc2, out2, _e2 = run([py, os.path.join(HERE, "check_dupes.py"), twice], 60)
                    if rc2 == 1 and "OVERLAP" in out2:
                        report("PASS", "test run: check_dupes.py",
                               "passed a clean cut list and exited 1 on a duplicated pair")
                    else:
                        report("FAIL", "test run: check_dupes.py",
                               "did not fail on two identical clips (exit %d)" % rc2,
                               "A gate that cannot fail is not a gate. Report this.")

        # 5c. name_clip.py. Text only, so it costs nothing, and it guards the three things
        #     a filename has to get right: it is a usable name at all, a thousands comma
        #     does not become two words, a date does not reach the name, and two clips
        #     that say the same thing still come out as two different files.
        twins = os.path.join(tmp, "twins.json")
        said = ("Do you want to make $400,000 a year? Back in January 2024 somebody told "
                "me they wanted that and said in the same breath it was impossible.")
        json.dump({"pieces": [{"piece": "N1", "segments": [{"role": "hook", "text": said}]},
                              {"piece": "N2", "segments": [{"role": "hook", "text": said}]}]},
                  open(twins, "w", encoding="utf-8"))
        rc, out, err = run([py, os.path.join(HERE, "name_clip.py"), twins, "--json"], 60)
        try:
            names = [r["after"] for r in json.loads(out)["names"]] if rc == 0 else []
        except (ValueError, KeyError):
            names = []
        if len(names) != 2:
            report("FAIL", "test run: name_clip.py", tail(err or out) or "named nothing",
                   "Run it by hand: %s bin/name_clip.py %s" % (PYCMD, twins))
        else:
            faults = []
            for n in names:
                if not GOOD_NAME.match(n):
                    faults.append("%r is not a usable filename" % n)
                if "-000" in n:
                    faults.append("%r split a thousands comma into its own word" % n)
                for bad in ("january", "2024"):
                    if bad in n:
                        faults.append("%r carries a date" % n)
            if names[0] == names[1]:
                faults.append("both clips were named %r, so one would overwrite the other"
                              % names[0])
            if faults:
                report("FAIL", "test run: name_clip.py", "; ".join(faults[:3]),
                       "A filename is the first thing a buyer sees. Report this with the "
                       "transcript.")
            else:
                report("PASS", "test run: name_clip.py",
                       "two clips saying the identical thing came out as %s and %s, no "
                       "date and no split number" % (names[0], names[1]))

        # 6. cards_from_srt.py survives the things real speech does
        awk = os.path.join(KIT, "fixtures", "awkward")
        files = sorted(glob.glob(os.path.join(awk, "*.srt"))) if os.path.isdir(awk) else []
        if not files:
            report("SKIP", "cards_from_srt.py on awkward transcripts", "no fixtures/awkward folder")
        else:
            bad, checked = [], 0
            for f in files:
                name = os.path.basename(f)
                rc, out, err = run([py, os.path.join(HERE, "cards_from_srt.py"), f,
                                    "--start", "0", "--end", "99999",
                                    "--source", "x.mp4", "--print"], 60)
                if name == "all-filler.srt":
                    # the right answer here is a refusal with a reason, not cards
                    if rc == 0:
                        bad.append("%s: wrote cards for a window of pure filler" % name)
                    continue
                checked += 1
                try:
                    spec = json.loads(out) if rc == 0 else None
                except ValueError:
                    spec = None
                if not spec or not spec.get("cards"):
                    bad.append("%s: %s" % (name, tail(err or out, 1) or "no cards"))
                    continue
                # the bug this fixture exists for: a speaker's name reaching the screen, or one
                # card carrying the words of two people
                for banned in FORBIDDEN_IN_CARDS.get(name, ()):
                    if any(banned in c["text"] for c in spec["cards"]):
                        bad.append("%s: %r reached a caption card" % (name, banned))
                trim, prev = spec.get("trim") or {}, None
                for i, c in enumerate(spec["cards"]):
                    why = None
                    if c["end"] <= c["start"]:
                        why = "card %d ends before it starts" % i
                    elif c["start"] < trim.get("start", 0) - 0.01 or c["end"] > trim.get("end", 0) + 0.01:
                        why = "card %d outside the trim" % i
                    elif len(c["text"].split()) > 4:
                        why = "card %d has %d words" % (i, len(c["text"].split()))
                    elif c["end"] - c["start"] > 3.01:
                        why = "card %d held %.2fs" % (i, c["end"] - c["start"])
                    elif not c["text"].strip():
                        why = "card %d is empty" % i
                    elif prev is not None and c["start"] < prev - 0.01:
                        why = "card %d overlaps the one before" % i
                    if why:
                        bad.append("%s: %s" % (name, why))
                        break
                    prev = c["end"]
            if bad:
                report("FAIL", "cards_from_srt.py on awkward transcripts", "; ".join(bad[:3]),
                       "Read fixtures/awkward/README.md for what each file is meant to prove.")
            else:
                report("PASS", "cards_from_srt.py on awkward transcripts",
                       "%d awkward transcripts gave usable cards, and pure filler was refused" % checked)

        # 7. whisper-cli loads the model and transcribes a file
        if not (whisper and model):
            report("SKIP", "test run: whisper-cli with the model", "whisper-cli or the model not available (optional)")
        else:
            wav = os.path.join(tmp, "a.wav")
            rc, out, err = run([ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                                "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav], 60)
            if rc != 0:
                report("SKIP", "test run: whisper-cli with the model", "could not make a test wav: " + tail(err, 1))
            else:
                rc, out, err = run([whisper, "-m", model, "-f", wav, "-nt", "-np"], 180)
                if rc == 0:
                    report("PASS", "test run: whisper-cli with the model",
                           "loaded %s and ran on a 3 second tone (no speech, so no words expected)"
                           % os.path.basename(model))
                else:
                    report("FAIL", "test run: whisper-cli with the model", tail(err or out),
                           "The model file may be corrupt. Download it again and re-run this check.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Preflight for the content line. Exit 0 when everything passes.")
    ap.add_argument("--quick", action="store_true", help="skip the test renders and the whisper run")
    ap.add_argument("--model", help="path to the whisper ggml model (default models/ggml-base.en.bin in the kit, "
                                    "or env KIT_WHISPER_MODEL)")
    ap.add_argument("--whisper", help="path to whisper-cli (default: found on PATH, or env KIT_WHISPER_CLI)")
    ap.add_argument("--require-whisper", action="store_true",
                    help="treat a missing whisper-cli or model as a FAIL instead of a WARN")
    ap.add_argument("--venv", help="virtual environment folder (default: .venv in the kit, else this Python)")
    ap.add_argument("--brand", help="also check this brand file: its font resolves and it renders")
    ap.add_argument("--offline", action="store_true",
                    help="ask nothing of the network at all (the model URL check is skipped)")
    ap.add_argument("--check-model-url", action="store_true",
                    help="HEAD the model URL even when the model is already downloaded")
    args = ap.parse_args()

    print("kit_check  content line at %s" % KIT)
    print("")
    check_python()
    ffmpeg = check_ffmpeg()
    py = find_python(args.venv or os.path.join(KIT, ".venv"), bool(args.venv))
    if py:
        check_font(py, args.brand)
        check_scripts(py)
    else:
        report("SKIP", "font and scripts", "need a Python with Pillow first")
    whisper, model = check_whisper(args.model, args.whisper, args.require_whisper)
    check_model_url(bool(model), args.require_whisper, args.offline, args.check_model_url)

    if args.quick:
        report("SKIP", "test renders and whisper run", "--quick was given")
    elif ffmpeg and py:
        smoke(ffmpeg, py, whisper, model, args.brand)
    else:
        report("SKIP", "test renders and whisper run", "need ffmpeg and a Python with Pillow first")

    fails = STATUSES.count("FAIL")
    warns = STATUSES.count("WARN")
    print("")
    print("%d passed, %d failed, %d warnings, %d skipped"
          % (STATUSES.count("PASS"), fails, warns, STATUSES.count("SKIP")))
    if fails:
        print("NOT READY. Fix each FAIL above, then run this again.")
        sys.exit(1)
    print("READY." + (" Read the WARN lines first." if warns else ""))
    sys.exit(0)


if __name__ == "__main__":
    main()
