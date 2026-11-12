#!/usr/bin/env python3
"""voiceover_tape.py: a recording of her reading becomes a tape the rest of the kit accepts.

    python3 bin/voiceover_tape.py voice/take-01.m4a
    python3 bin/voiceover_tape.py voice/take-01.m4a --out work/vo/tape.mp4
    python3 bin/voiceover_tape.py voice/take-01.wav --size 1080x1920 --fps 30
    python3 bin/voiceover_tape.py voice/take-01.m4a --dry-run

WHY THIS EXISTS. Every entry point in this kit wants a tape: transcribe.py takes
media, plan_clips.py writes a cut list against tape seconds, and to_hyperframes.py
writes one <video class="seg"> per segment. An m4a of somebody reading is not a tape,
so a reel built over b-roll had nowhere to start. This makes the one thing missing:
a video file whose picture is a flat colour and whose sound is her voice, untouched.

The picture is a placeholder and is meant never to be seen. In a b-roll reel the
cutaway layers cover the whole timeline, so what shows is the shelf and the captions.
If you ever see this colour in a finished render, a b-roll layer is missing over that
moment, and bin/broll_reel.py refuses to write a spec with a gap in it for exactly
that reason.

HER VOICE, AND THIS IS A RULE RATHER THAN A PREFERENCE. This file takes a recording
and nothing else. There is no text input, no voice model, no synthesis path in here
at all, because .claude/rules/her-hands-not-the-machine.md allows a synthetic voice
for One Red Thread and not for her own brand or the Life First Method. The way this
tool enforces that is by having no other way to make a sound: the audio in the output
is the audio you handed it.

THE VOICE IS NOT RE-ENCODED WHEN IT DOES NOT HAVE TO BE. An AAC track is stream
copied into the mp4, bit identical, with no second generation and no second loudness
pass. Anything else (wav, mp3, aiff) becomes AAC once, and the report says so.

IT ALSO WRITES THE CUT LIST, AND THAT IS NOT A CONVENIENCE. `plan_clips.py` cannot
make one for a scripted voiceover and should not be asked to. It SELECTS moments out
of long form and links them, and it refuses anything under 45 seconds. Measured on a
31.6s scripted transcript: the default run said "no clip of 45 to 150 seconds could
be built from 24 moments", `--min 25` refused the same way because the problem is the
moment linking rather than the floor, and `--min 5 --max 200` did build a piece and
it was 9.05 seconds long, which threw away 22 seconds of a script where every word
was wanted. **Selection is the wrong operation on a read script.** So this writes the
one piece itself: one segment, zero to the tape duration, nothing dropped. It already
knows the duration and the path, which is why it is the right file to do it.

WHAT IT WRITES
    NAME-tape.mp4       the tape
    NAME-cuts.json      a one piece cut list over all of it, unless --no-cuts
    and it prints the next commands, with the real paths filled in

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
# The shared encoder chooser. Hardware where the machine has it, software where it
# does not. Imported rather than copied, so there is one place this decision lives.
import kit_common as kc  # noqa: E402

AUDIO_EXT = {".m4a", ".mp3", ".wav", ".aif", ".aiff", ".flac", ".aac", ".ogg", ".opus", ".caf"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}

# AAC in an mp4 is the one case where the voice can be carried across untouched.
COPYABLE = {"aac"}


def who() -> str:
    return Path(sys.argv[0]).stem or "voiceover_tape"


def die(msg: str) -> None:
    print("%s: %s" % (who(), msg), file=sys.stderr)
    sys.exit(1)


def need(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        die("%s is not on your PATH. On a Mac: brew install ffmpeg" % tool)
    return path


def probe(ffprobe: str, path: Path) -> dict:
    cmd = [ffprobe, "-v", "error", "-print_format", "json",
           "-show_format", "-show_streams", str(path)]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if res.returncode != 0:
        lines = (res.stderr or "").strip().splitlines()
        die("ffprobe could not read %s: %s" % (path.name, lines[0] if lines else "unknown error"))
    try:
        return json.loads(res.stdout or "{}")
    except ValueError as exc:
        die("ffprobe output was not JSON: %s" % exc)
    return {}


def parse_size(text: str) -> tuple[int, int]:
    raw = str(text).lower().replace("*", "x").replace(":", "x")
    if "x" not in raw:
        die('--size wants WIDTHxHEIGHT, for example 1080x1920 (got "%s")' % text)
    w, _, h = raw.partition("x")
    try:
        width, height = int(w), int(h)
    except ValueError:
        die('--size wants two whole numbers, for example 1080x1920 (got "%s")' % text)
    if width < 16 or height < 16 or width % 2 or height % 2:
        die("--size %dx%d is not an even frame size H.264 can encode" % (width, height))
    return width, height


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="A recording of her reading becomes a tape the rest of the kit accepts.")
    ap.add_argument("audio", help="a recording: m4a, mp3, wav, aiff, flac")
    ap.add_argument("--out", help="where to write the tape (default: <name>-tape.mp4 beside it)")
    ap.add_argument("--size", default="1080x1920",
                    help="frame size of the placeholder picture (default 1080x1920)")
    ap.add_argument("--fps", type=float, default=30.0, help="frame rate (default 30)")
    ap.add_argument("--color", default="black",
                    help="the placeholder colour, any ffmpeg colour name (default black)")
    ap.add_argument("--reencode-audio", action="store_true",
                    help="encode the voice to AAC even when it could be copied untouched")
    ap.add_argument("--audio-bitrate", default="192k", help="when the voice is encoded (default 192k)")
    ap.add_argument("--cuts", help="where to write the one piece cut list "
                                   "(default: <name>-cuts.json beside the tape)")
    ap.add_argument("--no-cuts", action="store_true",
                    help="write only the tape. plan_clips.py cannot make a cut list for a "
                         "read script, so you would be writing one by hand")
    ap.add_argument("--piece", default="A1", help="the piece id in the cut list (default A1)")
    ap.add_argument("--force", action="store_true", help="overwrite the tape if it is already there")
    ap.add_argument("--dry-run", action="store_true", help="print the ffmpeg command and stop")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    args = ap.parse_args(argv)

    src = Path(args.audio).expanduser()
    if not src.is_file():
        die("%s is not a file" % src)

    ffmpeg = need("ffmpeg")
    ffprobe = need("ffprobe")
    info = probe(ffprobe, src)

    audio_stream = None
    video_stream = None
    for stream in info.get("streams") or []:
        kind = stream.get("codec_type")
        if kind == "audio" and audio_stream is None:
            audio_stream = stream
        elif kind == "video" and video_stream is None:
            video_stream = stream

    if audio_stream is None:
        die("%s has no audio stream, so there is no voice to build a tape around" % src.name)

    if video_stream is not None and src.suffix.lower() in VIDEO_EXT:
        die("%s already has a picture. The kit takes it directly:\n"
            "  python3 bin/transcribe.py %s\n"
            "This tool is only for a voice recording with no picture."
            % (src.name, src))

    duration = None
    for candidate in (audio_stream.get("duration"), (info.get("format") or {}).get("duration")):
        try:
            duration = round(float(candidate), 3)
            break
        except (TypeError, ValueError):
            continue
    if not duration or duration <= 0:
        die("ffprobe gave no usable duration for %s" % src.name)
    if duration < 2.0:
        die("%s is %.2fs long. That is not a voiceover." % (src.name, duration))

    width, height = parse_size(args.size)
    codec = (audio_stream.get("codec_name") or "").lower()
    can_copy = codec in COPYABLE and not args.reencode_audio

    out = (Path(args.out).expanduser() if args.out
           else src.with_name(src.stem + "-tape.mp4"))
    if out.exists() and not args.force and not args.dry_run:
        die("%s is already there. Pass --force to replace it." % out)

    audio_args = (["-c:a", "copy"] if can_copy
                  else ["-c:a", "aac", "-b:a", str(args.audio_bitrate), "-ar", "48000"])

    cmd = [ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-y",
           "-f", "lavfi",
           "-i", "color=c=%s:s=%dx%d:r=%s:d=%.3f"
                 % (args.color, width, height, _fps(args.fps), duration),
           "-i", str(src),
           "-map", "0:v:0", "-map", "1:a:0",
           "-pix_fmt", "yuv420p"]
    cmd += kc.video_codec(preset="veryfast")
    # A flat colour compresses to nearly nothing whatever the encoder does, so the
    # cheap preset costs no quality here and the voice is the only real payload.
    cmd += ["-b:v", "600k", "-g", "60"]
    cmd += audio_args
    cmd += ["-movflags", "+faststart", "-shortest", str(out)]

    if args.dry_run:
        print(" ".join(_quote(c) for c in cmd))
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(res.stderr.strip()[-2000:], file=sys.stderr)
        die("ffmpeg exited %d. The command above is the one to reproduce it:\n  %s"
            % (res.returncode, " ".join(_quote(c) for c in cmd)))
    if not out.exists() or out.stat().st_size == 0:
        die("ffmpeg reported success and wrote nothing to %s" % out)

    made = probe(ffprobe, out)
    made_dur = None
    for candidate in ((made.get("format") or {}).get("duration"),):
        try:
            made_dur = round(float(candidate), 3)
        except (TypeError, ValueError):
            pass
    drift = None if made_dur is None else round(made_dur - duration, 3)

    cuts_path = None
    if not args.no_cuts:
        cuts_path = (Path(args.cuts).expanduser() if args.cuts
                     else out.with_name(out.stem + "-cuts.json"))
        if cuts_path.exists() and not args.force:
            die("%s is already there. Pass --force to replace it, or --no-cuts." % cuts_path)
        # The segment runs to the duration ffprobe measured on the TAPE, which is the
        # file every later stage reads. Using the recording's duration instead would
        # leave the last fraction of a second out of the piece.
        span = made_dur if made_dur else duration
        piece = {
            "piece": str(args.piece),
            "filename": slug(out.stem),
            "duration": round(span, 3),
            "segments": [{"start": 0.0, "end": round(span, 3), "role": "body",
                          "note": "the whole voiceover. A read script is not selected from."}],
            "cards": [],
        }
        doc = {
            "_what_this_is": "A ONE PIECE cut list over a whole voiceover, written by "
                             "bin/voiceover_tape.py. plan_clips.py selects moments out of long "
                             "form and refuses anything under 45 seconds, and selection is the "
                             "wrong operation on a read script where every word is wanted.",
            "_the_hook_is_empty": "There is no hook yet, because the words are not transcribed "
                                  "when this file is written. Run bin/hook_curate.py --write on "
                                  "it after bin/cards_from_srt.py has filled the cards, and it "
                                  "chooses one out of the spoken words.",
            "source": str(out),
            "out_dir": str(out.parent / "out"),
            "times": "source",
            "keep_audio": True,
            "pieces": [piece],
        }
        cuts_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cuts_path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)
            fh.write("\n")

    report = {
        "cuts": None if cuts_path is None else str(cuts_path),
        "tape": str(out),
        "from": str(src),
        "seconds": duration,
        "tape_seconds": made_dur,
        "drift_s": drift,
        "frame": "%dx%d" % (width, height),
        "fps": args.fps,
        "voice": "copied untouched (%s)" % codec if can_copy else "encoded to AAC from %s" % codec,
        "bytes": out.stat().st_size,
    }
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print("")
    print("voiceover_tape  %s" % out)
    print("  %.2fs of voice, %dx%d placeholder picture at %s fps"
          % (duration, width, height, _fps(args.fps)))
    print("  voice: %s" % report["voice"])
    if drift is not None and abs(drift) > 0.08:
        print("  the tape is %+.3fs against the recording. Card times come off the "
              "TRANSCRIPT of this tape, so they stay in step either way." % drift)
    srt = _quote(str(out.with_suffix(".srt")))
    print("")
    if cuts_path is None:
        print("  --no-cuts, so there is no cut list. plan_clips.py cannot make one for a read")
        print("  script: it selects moments out of long form and refuses under 45 seconds.")
    else:
        print("  wrote the cut list %s: one piece, one segment, 0.00 to %.2fs, nothing dropped."
              % (cuts_path, round(made_dur or duration, 2)))
    cj = _quote(str(cuts_path)) if cuts_path else "<your cut list>"
    print("")
    print("  Next, and the paths are already filled in:")
    print("    python3 bin/transcribe.py %s" % _quote(str(out)))
    print("        it will print pick_pulls and plan_clips as ITS next step. Ignore both:")
    print("        they select moments out of long form and the cut list is already written.")
    print("    python3 bin/cards_from_srt.py %s --cuts %s" % (srt, cj))
    print("    python3 bin/hook_curate.py %s --write" % cj)
    print("        it refuses when no span in the opener qualifies, and a refusal is an answer.")
    print("    python3 bin/caption_check.py %s --transcript %s" % (cj, srt))
    print("    python3 bin/shelf_index.py <your clip folder> --out specs/shelf.json")
    print("        then LOOK at the frames and fill in label and keywords")
    print("    python3 bin/broll_reel.py %s --shelf specs/shelf.json --out specs/broll.json" % cj)
    print("")
    print("  Read the cards cold at caption_check.py. They are whisper's words rather than")
    print("  your script's, and a misheard line on screen is the one error nobody forgives.")
    print("  The placeholder colour is meant never to show: the b-roll covers all of it.")
    return 0


def slug(text: str) -> str:
    out = "".join(c if (c.isalnum() or c in "-_") else "-" for c in str(text)).strip("-").lower()
    while "--" in out:
        out = out.replace("--", "-")
    return out[:60] or "voiceover"


def _fps(value: float) -> str:
    text = ("%.3f" % float(value)).rstrip("0").rstrip(".")
    return text or "30"


def _quote(text: str) -> str:
    return text if all(c.isalnum() or c in "-_./=:," for c in text) else "'%s'" % text


if __name__ == "__main__":
    sys.exit(main())
