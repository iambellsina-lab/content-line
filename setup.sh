#!/usr/bin/env bash
#
# setup.sh: get this computer ready to run the content line.
#
#   bash setup.sh               check the computer, build the kit's own Python environment,
#                               run the self-test
#   bash setup.sh --with-model  also download the transcription model (about 148 MB). It asks
#                               first when you are at a terminal. Asking a question nobody can
#                               see is how this used to skip the download in silence, so when
#                               input is not a terminal, naming the flag is the consent.
#   bash setup.sh --yes         answer yes to that question without being asked
#   bash setup.sh --recreate    set the existing .venv folder aside and build a fresh one
#   bash setup.sh --help        show this text
#
# What it checks, in order:
#   1. ffmpeg and ffprobe are installed, and ffmpeg can encode H.264 (libx264)
#   2. Python 3.10 or newer is installed
#   3. builds a private Python environment in the .venv folder and installs Pillow into it
#   4. Pillow can really draw text
#   5. whisper-cli and the model file (optional, only transcription needs them)
#   6. runs bin/kit_check.py, which renders real test videos
#
# It prints PASS, WARN or FAIL for each step, then one final RESULT line. Every FAIL comes
# with the exact next step. It exits 0 only when nothing failed, and exits 1 otherwise.
#
# What it will not do: install ffmpeg, Python or whisper for you, change anything outside
# this folder, download anything without asking, or delete anything. A .venv folder that
# cannot be used is renamed to .venv.old-<date> and left for you to remove.
#
# On Windows, run it from Git Bash (it comes with "Git for Windows"). Not tested on Windows.
#
set -u

KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$KIT/.venv"
MODEL="$KIT/models/ggml-base.en.bin"
# This kit's own release asset first, so a first run needs no account anywhere, then the
# original. Both serve the identical file: 147964211 bytes, md5 4279db3d7b18d9f6e4d5817a16af4f09,
# checked from both on 2026-10-08. The model is OpenAI's Whisper converted to ggml for
# whisper.cpp, MIT licensed, mirrored with attribution in the release notes.
MODEL_URL="https://github.com/iambellsina-lab/content-line/releases/download/models-v1/ggml-base.en.bin"
MODEL_URL_ALT="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin"
MODEL_BYTES=147964211
MODEL_MD5=4279db3d7b18d9f6e4d5817a16af4f09
MIN_MINOR=10

RECREATE=0
WITH_MODEL=0
ASSUME_YES=0
for arg in "$@"; do
  case "$arg" in
    --recreate)   RECREATE=1 ;;
    --with-model) WITH_MODEL=1 ;;
    -y|--yes)     ASSUME_YES=1 ;;
    -h|--help)    sed -n '3,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "setup.sh does not know the option: $arg" >&2
       echo "It takes --with-model, --yes, --recreate and --help. Run it as: bash setup.sh" >&2
       exit 2 ;;
  esac
done

case "$(uname -s 2>/dev/null)" in
  Darwin)                OS=mac ;;
  Linux)                 OS=linux ;;
  MINGW*|MSYS*|CYGWIN*)  OS=windows ;;
  *)                     OS=other ;;
esac

FAILS=0
STEPS=""        # numbered next steps, one per failure
OPTIONAL=""     # things that are not set up but are not required
SCRATCH="$(mktemp -d 2>/dev/null || echo "$KIT/.setup-scratch")"
mkdir -p "$SCRATCH"
trap 'rm -rf "$SCRATCH" 2>/dev/null' EXIT

say()  { printf '%s\n' "$*"; }
ok()   { printf '[PASS] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*"; }

# bad "what failed" "how to fix it (may span lines)"
bad() {
  FAILS=$((FAILS + 1))
  printf '[FAIL] %s\n' "$1"
  printf '       next step: %s\n' "$(printf '%s' "$2" | head -1)"
  printf '%s\n' "$2" | sed '1d' | sed 's/^/                  /'
  STEPS="${STEPS}  ${FAILS}. $1
$(printf '%s\n' "$2" | sed 's/^/       /')
"
}

# Rename something out of the way instead of deleting it.
set_aside() {
  moved="$1.old-$(date +%Y%m%d-%H%M%S)"
  if mv "$1" "$moved"; then
    say "       the old folder was renamed to $(basename "$moved"). Nothing was deleted."
    return 0
  fi
  return 1
}

say "Content line setup"
say "kit folder: $KIT"
say "computer:   $OS"
say ""

# ------------------------------------------------------------------ 1. ffmpeg
FFMPEG_OK=0
case "$OS" in
  mac)     FF_FIX="Install it with Homebrew:  brew install ffmpeg
If 'brew' is not found, install Homebrew first from https://brew.sh and try again.
Then run: bash setup.sh" ;;
  windows) FF_FIX="Install it:  winget install Gyan.FFmpeg
Then CLOSE this window, open a new Git Bash, and run: bash setup.sh" ;;
  linux)   FF_FIX="Install it:  sudo apt install ffmpeg
Then run: bash setup.sh" ;;
  *)       FF_FIX="Install ffmpeg from https://ffmpeg.org/download.html, then run: bash setup.sh" ;;
esac

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  missing=""
  command -v ffmpeg  >/dev/null 2>&1 || missing="ffmpeg"
  command -v ffprobe >/dev/null 2>&1 || missing="$missing ffprobe"
  bad "ffmpeg is not installed (not found:$missing)" "$FF_FIX"
elif ! ffmpeg -version >/dev/null 2>&1; then
  bad "ffmpeg is installed but will not run" "$FF_FIX"
else
  ENCODERS="$(ffmpeg -hide_banner -encoders 2>&1)"
  if printf '%s\n' "$ENCODERS" | grep -Eq '[[:space:]]libx264[[:space:]]'; then
    ok "ffmpeg: $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f1-3), and it has libx264"
    FFMPEG_OK=1
  else
    bad "ffmpeg is installed but cannot encode H.264 (libx264 is missing from this build)" "$FF_FIX
This kit needs a normal full ffmpeg build. A stripped-down build without libx264 cannot work.
Check yourself with:  ffmpeg -hide_banner -encoders | grep libx264"
  fi
fi

# ------------------------------------------------------------------ 2. Python
PY=""
for cand in python3.14 python3.13 python3.12 python3.11 python3.10 python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    if "$cand" -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, $MIN_MINOR) else 1)" >/dev/null 2>&1; then
      PY="$cand"; break
    fi
  fi
done

case "$OS" in
  mac)     PY_FIX="Install it with Homebrew:  brew install python
Then run: bash setup.sh" ;;
  windows) PY_FIX="Install it:  winget install Python.Python.3.12
Then CLOSE this window, open a new Git Bash, and run: bash setup.sh" ;;
  linux)   PY_FIX="Install it:  sudo apt install python3 python3-venv python3-pip
Then run: bash setup.sh" ;;
  *)       PY_FIX="Install Python 3.10 or newer from https://www.python.org/downloads/, then run: bash setup.sh" ;;
esac

if [ -z "$PY" ]; then
  found="$(python3 --version 2>&1 || python --version 2>&1 || true)"
  case "$found" in
    Python*) bad "Python is too old: found '$found', need 3.$MIN_MINOR or newer" "$PY_FIX" ;;
    *)       bad "Python is not installed (need 3.$MIN_MINOR or newer)" "$PY_FIX" ;;
  esac
else
  ok "python: $("$PY" -c 'import platform,sys; print(platform.python_version(), "at", sys.executable)')"
fi

# ------------------------------------------------------------------ 3. venv and Pillow
VPY=""
find_vpy() {
  VPY=""
  [ -x "$VENV/bin/python" ] && VPY="$VENV/bin/python"
  [ -z "$VPY" ] && [ -f "$VENV/Scripts/python.exe" ] && VPY="$VENV/Scripts/python.exe"
  return 0
}
venv_runs() {
  [ -n "$VPY" ] && "$VPY" -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, $MIN_MINOR) else 1)" >/dev/null 2>&1
}

PILLOW_OK=0
if [ -n "$PY" ]; then
  find_vpy
  if [ -d "$VENV" ] && [ "$RECREATE" -eq 1 ]; then
    say "       --recreate was given"
    set_aside "$VENV" && VPY=""
  elif [ -d "$VENV" ] && ! venv_runs; then
    say "       the existing .venv will not run here (copied from another computer?)"
    set_aside "$VENV" && VPY=""
  fi

  if [ ! -d "$VENV" ]; then
    if "$PY" -m venv "$VENV" >"$SCRATCH/venv.log" 2>&1; then
      find_vpy
    else
      tail -5 "$SCRATCH/venv.log" | sed 's/^/       /'
      case "$OS" in
        linux) V_FIX="sudo apt install python3-venv
Then run: bash setup.sh" ;;
        *)     V_FIX="Run it again with --recreate:  bash setup.sh --recreate
If it fails the same way, send the lines above to whoever gave you the kit." ;;
      esac
      bad "could not create the .venv folder" "$V_FIX"
    fi
  fi

  if [ -n "$VPY" ] && venv_runs; then
    ok "venv: $VENV"
    "$VPY" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
    if "$VPY" -m pip install --quiet -r "$KIT/requirements.txt" >"$SCRATCH/pip.log" 2>&1; then
      ok "installed requirements.txt into the venv"
      if "$VPY" -c "
import sys
from PIL import features
sys.exit(0 if features.check('freetype2') else 1)
" >/dev/null 2>&1; then
        ok "Pillow $("$VPY" -c 'import PIL; print(PIL.__version__)') can draw text (FreeType is present)"
        PILLOW_OK=1
      else
        bad "Pillow is installed but cannot draw text (it was built without FreeType)" "Run:  \"$VPY\" -m pip install --force-reinstall --no-cache-dir pillow
Then run: bash setup.sh"
      fi
    else
      tail -6 "$SCRATCH/pip.log" | sed 's/^/       /'
      bad "could not install Pillow (the lines above are pip's own message)" "Check that this computer is online, then run: bash setup.sh
If you are online and it still fails, send the lines above to whoever gave you the kit."
    fi
  elif [ -d "$VENV" ]; then
    bad "the .venv folder exists but has no working Python inside it" "Run:  bash setup.sh --recreate"
  fi
fi

# ------------------------------------------------------------------ 4. whisper (optional)
case "$OS" in
  mac)     WH_FIX="brew install whisper.cpp" ;;
  windows) WH_FIX="download the Windows zip from https://github.com/ggml-org/whisper.cpp/releases, unzip it, and put the folder holding whisper-cli.exe on your PATH. (Not tested here.)" ;;
  linux)   WH_FIX="whisper.cpp has no standard apt package. Build it from https://github.com/ggml-org/whisper.cpp, or skip it and supply your own transcripts." ;;
  *)       WH_FIX="see https://github.com/ggml-org/whisper.cpp" ;;
esac

if command -v whisper-cli >/dev/null 2>&1; then
  ok "whisper-cli: found at $(command -v whisper-cli)"
else
  warn "whisper-cli is not installed. Optional: only 'footage to clips' needs it."
  say  "       to add it: $WH_FIX"
  OPTIONAL="${OPTIONAL}  - whisper-cli (transcription): $WH_FIX
"
fi

if [ -f "$MODEL" ]; then
  ok "whisper model: models/ggml-base.en.bin is present"
elif [ "$WITH_MODEL" -eq 1 ] && [ "$PILLOW_OK" -eq 1 ]; then
  say "       The transcription model is about 148 MB."
  say "         from: $MODEL_URL"
  say "         to:   $MODEL"
  # Asking a question that nobody can see, then treating the silence as no, is how this
  # skipped the download without saying so and then told the reader to run the very flag
  # they had just run. Measured 2026-10-08 on a clean clone. When input is not a terminal,
  # which is every scripted run and every run driven by Claude Code, naming --with-model
  # is the consent, because nothing else could have asked for it.
  answer=""
  if [ "$ASSUME_YES" -eq 1 ]; then
    answer=y; say "       --yes was passed, so downloading."
  elif [ -t 0 ]; then
    printf '       Download it now? [y/N] '
    read -r answer || true
  else
    answer=y; say "       input is not a terminal, and --with-model asked for this, so downloading."
  fi
  case "$answer" in
    y|Y|yes|YES)
      mkdir -p "$KIT/models"
      PART="$MODEL.part"
      dl_ok=0
      for url in "$MODEL_URL" "$MODEL_URL_ALT"; do
        [ "$dl_ok" -eq 1 ] && break
        [ "$url" = "$MODEL_URL_ALT" ] && say "       the first source did not work, trying: $url"
        if command -v curl >/dev/null 2>&1; then
          curl -fL --progress-bar "$url" -o "$PART" && dl_ok=1
        elif command -v wget >/dev/null 2>&1; then
          wget -q --show-progress "$url" -O "$PART" && dl_ok=1
        else
          say "       neither curl nor wget is installed"; break
        fi
      done
      # Size, header and checksum. A proxy or a captive portal returns 200 and an HTML
      # page, which passes a size check on its own and then fails hours later inside
      # whisper-cli with nothing to point at.
      if [ "$dl_ok" -eq 1 ] && "$VPY" -c "
import hashlib, os, sys
p, want_bytes, want_md5 = sys.argv[1], int(sys.argv[2]), sys.argv[3]
n = os.path.getsize(p)
if n != want_bytes:
    print(f'       the file is {n} bytes and should be {want_bytes}'); sys.exit(1)
with open(p, 'rb') as f:
    if f.read(4) != b'lmgg':
        print('       that is not a ggml model file'); sys.exit(2)
    f.seek(0); h = hashlib.md5()
    for chunk in iter(lambda: f.read(1 << 20), b''): h.update(chunk)
if h.hexdigest() != want_md5:
    print(f'       checksum {h.hexdigest()}, expected {want_md5}'); sys.exit(3)
" "$PART" "$MODEL_BYTES" "$MODEL_MD5"; then
        mv "$PART" "$MODEL"
        ok "whisper model: downloaded, $MODEL_BYTES bytes, md5 matches"
      else
        [ -f "$PART" ] && mv "$PART" "$PART.bad"
        warn "the model download did not work. Download it by hand from: $MODEL_URL"
        say  "       and save it as: $MODEL"
        OPTIONAL="${OPTIONAL}  - whisper model file: download $MODEL_URL and save it as models/ggml-base.en.bin
"
      fi ;;
    *)
      warn "whisper model: you said no. Transcription will not run without it."
      OPTIONAL="${OPTIONAL}  - whisper model file: run  bash setup.sh --with-model --yes  for the 148 MB download
" ;;
  esac
else
  warn "whisper model: models/ggml-base.en.bin is not there. Optional: only 'footage to clips' needs it."
  say  "       to add it (about 148 MB): bash setup.sh --with-model"
  OPTIONAL="${OPTIONAL}  - whisper model file (about 148 MB): run  bash setup.sh --with-model
"
fi

# ------------------------------------------------------------------ 5. self-test
say ""
if [ "$FAILS" -eq 0 ]; then
  say "Running the self-test (bin/kit_check.py). It renders real test videos, so give it a minute."
  say ""
  "$VPY" "$KIT/bin/kit_check.py"
  KC=$?
  say ""
  if [ "$KC" -ne 0 ]; then
    bad "the self-test failed (the [FAIL] lines above each say what to do)" "Do what the 'fix:' line under each [FAIL] says, then run: bash setup.sh"
  fi
else
  say "The self-test was not run, because a step above failed. Fix those first."
  say ""
fi

# ------------------------------------------------------------------ result
say "=============================================================="
if [ "$FAILS" -eq 0 ]; then
  say "RESULT: PASS. This computer can make clips."
  if [ -n "$OPTIONAL" ]; then
    say ""
    say "Not set up yet (optional):"
    printf '%s' "$OPTIONAL"
  fi
  say ""
  say "Next: open README.md, section 3 (\"Seeing it work\") and make the first clip."
  exit 0
else
  say "RESULT: FAIL. $FAILS problem(s). Do these in order, then run  bash setup.sh  again:"
  say ""
  printf '%s' "$STEPS"
  exit 1
fi
