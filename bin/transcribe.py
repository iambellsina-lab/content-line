#!/usr/bin/env python3
"""transcribe.py: any media file to a timestamped transcript, free and local.

    python3 bin/transcribe.py recording.mov
    python3 bin/transcribe.py podcast.mp3 --out-dir work/
    python3 bin/transcribe.py long.mov --duration 120        # first two minutes only, for a spot check
    python3 bin/transcribe.py long.mov --force               # redo it even if a transcript is already there

WHAT IT NEEDS
    ffmpeg          to pull the audio out of the container
    whisper-cli     from whisper.cpp (brew install whisper.cpp on a Mac)
    a model file    models/ggml-base.en.bin inside this kit, about 148 MB

    No network at run time, no account, no per-minute charge. The model is downloaded once.
    This script never reads a model from outside the kit unless you pass --model yourself,
    so the kit stays liftable: nothing here points at one person's machine.

WHAT IT WRITES, next to the source file or into --out-dir
    NAME.srt        the transcript every other script in this kit reads
    NAME.cues.json  the same cues as [{"start", "end", "text"}], for anything that wants JSON
    NAME.txt        a reading copy: timecode, absolute seconds, and the silences marked

    The silences are the part worth reading. A gap longer than --gap-mark seconds is where a
    thought ended, and those are the only honest places to start and finish a clip.

THE PUNCTUATION TRAP, measured on this machine 2026-10-08 and the reason for the default prompt
    Transcribing from 109 seconds into a recording, with no initial prompt, came back with no
    punctuation and no capitals at all: "stop calling your income goal a vision what even oh".
    The same audio with a short punctuated initial prompt came back as "Stop calling your income
    goal a vision. A vision is simply something that is imaginary." Same model, same file.

    Whisper decodes in the style of its context, and starting mid-recording gives it none. Every
    script downstream of this one depends on sentence punctuation: without it pick_pulls.py falls
    back to guessing sentence edges from pauses and says so in its own caveats. So a neutral
    punctuated prompt goes in by default. It mentions nothing about any subject, so it cannot put
    words in anybody's mouth, and --no-prompt turns it off.

EFFICIENCY, because an hour of audio is the normal case here
    It skips the work when NAME.srt already exists and is newer than the source. Pass --force
    to redo it. The audio extraction goes to a temporary 16 kHz mono WAV and is deleted after,
    unless you pass --keep-wav. It prints the realtime factor at the end so you know what an
    hour will cost you next time.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MODEL = os.path.join(KIT, "models", "ggml-base.en.bin")
MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin"
MODEL_BYTES = 147964211          # measured on the file this kit was built against
MODEL_MAGIC = b"lmgg"            # ggml files start with this
WHISPER_NAMES = ["whisper-cli", "whisper-cpp", "main"]
WHISPER_DIRS = ["/opt/homebrew/bin", "/usr/local/bin",
                os.path.join(KIT, "vendor", "whisper.cpp"),
                os.path.join(KIT, "vendor", "whisper.cpp", "build", "bin")]
SAMPLE_RATE = 16000


def die(msg, fix=None):
    print("transcribe: " + msg, file=sys.stderr)
    if fix:
        print("            " + fix, file=sys.stderr)
    sys.exit(2)


def find_tool(names, dirs, override=None):
    if override:
        if os.path.isfile(override) and os.access(override, os.X_OK):
            return override
        die("--whisper %s is not an executable file." % override)
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    for d in dirs:
        for n in names:
            p = os.path.join(d, n)
            if os.path.isfile(p) and os.access(p, os.X_OK):
                return p
    return None


def human_mb(n):
    return "%.0f MB (%.0f MiB)" % (n / 1000000.0, n / 1048576.0)


def check_model(path, allow_download):
    """Never download without saying what and how big first, and never without being asked."""
    if os.path.isfile(path) and os.path.getsize(path) > 1000000:
        with open(path, "rb") as f:
            if f.read(4) != MODEL_MAGIC:
                die("%s does not look like a ggml model (wrong file header)." % path,
                    "Delete it and run this again with --download.")
        return path
    print("transcribe: the transcription model is not in this kit yet.", file=sys.stderr)
    print("            file:  models/ggml-base.en.bin", file=sys.stderr)
    print("            size:  about %s" % human_mb(MODEL_BYTES), file=sys.stderr)
    print("            from:  %s" % MODEL_URL, file=sys.stderr)
    print("            once:  it is downloaded one time and then costs nothing.", file=sys.stderr)
    if not allow_download:
        die("nothing was downloaded, because you did not ask for it.",
            "Run this again with --download, or: bash setup.sh --with-model")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    print("transcribe: downloading about %s ..." % human_mb(MODEL_BYTES), file=sys.stderr)
    getter = shutil.which("curl") or shutil.which("wget")
    if not getter:
        die("neither curl nor wget is on this machine.",
            "Download %s by hand and save it as %s" % (MODEL_URL, path))
    cmd = ([getter, "-L", "--fail", "-o", tmp, MODEL_URL] if getter.endswith("curl")
           else [getter, "-O", tmp, MODEL_URL])
    if subprocess.run(cmd).returncode != 0 or not os.path.isfile(tmp):
        die("the download did not finish.", "Get %s by hand and save it as %s" % (MODEL_URL, path))
    with open(tmp, "rb") as f:
        if f.read(4) != MODEL_MAGIC:
            os.remove(tmp)
            die("what came back is not a ggml model file.", "Try the download again, or fetch it by hand.")
    os.replace(tmp, path)
    print("transcribe: model saved, %s" % human_mb(os.path.getsize(path)), file=sys.stderr)
    return path


def media_seconds(ffprobe, src):
    r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", src], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def probe_channels(ffmpeg, src):
    """How many audio channels the source really has, for the stereo diarisation check."""
    probe = ffmpeg[:-6] + "ffprobe" if ffmpeg.endswith("ffmpeg") else "ffprobe"
    r = subprocess.run([probe, "-v", "error", "-select_streams", "a:0",
                        "-show_entries", "stream=channels", "-of", "csv=p=0", src],
                       capture_output=True, text=True)
    try:
        return int(r.stdout.strip().splitlines()[0])
    except (ValueError, IndexError):
        return 0


def extract_audio(ffmpeg, src, wav, offset, duration, channels=1):
    args = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
    if offset:
        args += ["-ss", "%.3f" % offset]
    args += ["-i", src]
    if duration:
        args += ["-t", "%.3f" % duration]
    args += ["-vn", "-sn", "-dn", "-ac", str(channels), "-ar", str(SAMPLE_RATE),
             "-c:a", "pcm_s16le", wav]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode or not os.path.isfile(wav):
        die("ffmpeg could not get audio out of that file.", r.stderr.strip()[-400:])


PUNCT_PROMPT = ("Here is a transcript with full punctuation. Hello, this is a sentence. "
                "Is this a question? Yes, it is.")
NON_SPEECH = re.compile(r"^\s*[\[(][^\])]*[\])]\s*$")

# whisper.cpp writes its channel diarisation as "(speaker 0) the words". Every other script
# in this kit already understands the broadcast form "SPEAKER_0:", and none of them
# understand the parenthesised one, so a label left as written gets cut into a caption card
# and burned into the video. Normalised here, once, at the only place it is produced.
WHISPER_SPEAKER = re.compile(r"\(\s*speaker\s*(\d+)\s*\)\s*", re.I)


def normalise_speakers(cues):
    """(speaker 0) -> SPEAKER_0: at the front of a cue, and dropped mid-cue.

    A label in the middle of a cue means whisper changed its mind inside one block of text.
    The label is removed there rather than moved, because the cue's own times give no honest
    place to split it. Returns the cues and how many labels it saw.
    """
    seen = 0
    for c in cues:
        t = c["text"]
        if not WHISPER_SPEAKER.search(t):
            continue
        seen += 1
        lead = WHISPER_SPEAKER.match(t.lstrip())
        who = lead.group(1) if lead else None
        t = WHISPER_SPEAKER.sub(" ", t).strip()
        c["text"] = (f"SPEAKER_{who}: {t}" if who else t)
    return cues, seen


def run_whisper(whisper, model, wav, prefix, threads, max_len, prompt, diarize=False):
    args = [whisper, "-m", model, "-f", wav, "-of", prefix,
            "-osrt", "-oj", "-l", "en", "-pp", "-sns"]
    if diarize:
        # whisper.cpp's --diarize is CHANNEL separation, not voice recognition: it reads
        # which side of a stereo file is louder and labels the cue (speaker 0) or
        # (speaker 1). It is right when each person was recorded to their own track, which
        # is how most remote podcasts are captured, and it is noise on a single room mic,
        # which is why extract_audio downmixes to mono unless this is asked for.
        args += ["-di"]
    if max_len:
        args += ["-ml", str(max_len), "-sow"]
    if prompt:
        args += ["--prompt", prompt]
    if threads:
        args += ["-t", str(threads)]
    r = subprocess.run(args)
    if r.returncode:
        die("whisper-cli exited %d." % r.returncode, "Run the same command by hand to see why.")


def tc_to_sec(s):
    sec = 0.0
    for part in s.replace(",", ".").split(":"):
        sec = sec * 60 + float(part)
    return sec


def read_srt(path, offset):
    cues = []
    pat = re.compile(r"([\d:.,]+)\s*-->\s*([\d:.,]+)")
    with open(path, encoding="utf-8") as f:
        blocks = re.split(r"\n\s*\n", f.read().replace("\r\n", "\n").strip())
    for b in blocks:
        lines = b.split("\n")
        for k, ln in enumerate(lines):
            m = pat.search(ln)
            if m:
                cues.append({"start": round(tc_to_sec(m.group(1)) + offset, 3),
                             "end": round(tc_to_sec(m.group(2)) + offset, 3),
                             "text": " ".join(x.strip() for x in lines[k + 1:] if x.strip())})
                break
    return cues


def srt_tc(sec):
    h, rem = divmod(max(0.0, sec), 3600)
    m, s = divmod(rem, 60)
    return "%02d:%02d:%06.3f" % (int(h), int(m), s)


def write_srt(cues, path):
    with open(path, "w", encoding="utf-8") as f:
        for i, c in enumerate(cues, 1):
            f.write("%d\n%s --> %s\n%s\n\n"
                    % (i, srt_tc(c["start"]).replace(".", ","),
                       srt_tc(c["end"]).replace(".", ","), c["text"]))


def short_tc(sec):
    m, s = divmod(max(0.0, sec), 60)
    return "%02d:%05.2f" % (int(m), s)


def write_reading_copy(cues, path, gap_mark):
    """The format a person reads to plan cuts: timecode, absolute seconds, silences marked."""
    with open(path, "w", encoding="utf-8") as f:
        prev_end = None
        for c in cues:
            gap = None if prev_end is None else c["start"] - prev_end
            note = "   <<< GAP %.1fs" % gap if gap is not None and gap >= gap_mark else ""
            f.write("[%s -> %s] (%.2f-%.2f)%s\n%s\n"
                    % (short_tc(c["start"]), short_tc(c["end"]),
                       c["start"], c["end"], note, c["text"]))
            prev_end = c["end"]


def main():
    ap = argparse.ArgumentParser(description="Transcribe any media file locally with whisper.cpp.")
    ap.add_argument("media", help="any file ffmpeg can open: mov, mp4, mp3, m4a, wav")
    ap.add_argument("--diarize", action="store_true",
                    help="two speakers, each on their own stereo channel. Keeps both channels "
                         "and labels every cue (speaker 0) or (speaker 1). This is CHANNEL "
                         "separation, not voice recognition: it is right for a remote podcast "
                         "recorded to separate tracks and wrong for one room mic")
    ap.add_argument("--out-dir", help="where to write the transcript (default: beside the source)")
    ap.add_argument("--name", help="base name for the outputs (default: the source file's name)")
    ap.add_argument("--model", default=os.environ.get("CONTENT_LINE_MODEL") or DEFAULT_MODEL,
                    help="model file (default: models/ggml-base.en.bin inside this kit)")
    ap.add_argument("--download", action="store_true",
                    help="allow the model download if it is missing (it tells you the size first)")
    ap.add_argument("--whisper", help="path to whisper-cli, if it is not on your PATH")
    ap.add_argument("--threads", type=int, default=0, help="threads for whisper (default: its own)")
    ap.add_argument("--max-len", type=int, default=90,
                    help="longest cue in characters, split on a word (default 90, 0 for whisper's "
                         "own paragraphs). Short cues make every start time more accurate")
    ap.add_argument("--prompt", help="initial prompt for whisper, replacing the punctuation one")
    ap.add_argument("--no-prompt", action="store_true",
                    help="send no initial prompt. Read the note in this file before you do")
    ap.add_argument("--offset", type=float, default=0.0, help="start this many seconds into the file")
    ap.add_argument("--duration", type=float, default=0.0, help="only this many seconds (0 = all of it)")
    ap.add_argument("--gap-mark", type=float, default=1.5,
                    help="mark a silence this long or longer in the reading copy (default 1.5)")
    ap.add_argument("--keep-wav", action="store_true", help="keep the extracted 16 kHz mono WAV")
    ap.add_argument("--force", action="store_true", help="transcribe again even if the SRT is current")
    a = ap.parse_args()

    if not os.path.isfile(a.media):
        die("no such file: %s" % a.media)
    ffmpeg = find_tool(["ffmpeg"], WHISPER_DIRS)
    ffprobe = find_tool(["ffprobe"], WHISPER_DIRS)
    if not ffmpeg:
        die("ffmpeg is not installed.", "On a Mac: brew install ffmpeg")
    whisper = find_tool(WHISPER_NAMES, WHISPER_DIRS, a.whisper)
    if not whisper:
        die("whisper-cli is not installed.",
            "On a Mac: brew install whisper.cpp . Elsewhere: build it from "
            "https://github.com/ggml-org/whisper.cpp and put whisper-cli on your PATH.")

    out_dir = a.out_dir or os.path.dirname(os.path.abspath(a.media))
    os.makedirs(out_dir, exist_ok=True)
    name = a.name or os.path.splitext(os.path.basename(a.media))[0]
    srt_path = os.path.join(out_dir, name + ".srt")
    json_path = os.path.join(out_dir, name + ".cues.json")
    read_path = os.path.join(out_dir, name + ".txt")

    if (not a.force and os.path.isfile(srt_path)
            and os.path.getmtime(srt_path) >= os.path.getmtime(a.media)):
        print("transcribe: %s is already there and newer than the source. Nothing to do."
              % os.path.basename(srt_path))
        print("            Pass --force to transcribe it again.")
        return 0

    model = check_model(a.model, a.download)
    total = media_seconds(ffprobe, a.media) if ffprobe else None
    span = a.duration or ((total - a.offset) if total else None)
    print("transcribe: %s" % os.path.basename(a.media))
    print("            whisper: %s" % whisper)
    print("            model:   %s" % model)
    if span:
        print("            audio:   %.0f seconds (%.0f min) from %.0fs" % (span, span / 60.0, a.offset))

    work = tempfile.mkdtemp(prefix="transcribe-")
    wav = os.path.join(work, name + ".wav")
    prefix = os.path.join(work, name)
    t0 = time.time()
    try:
        channels = 1
        if a.diarize:
            have = probe_channels(ffmpeg, a.media)
            if have < 2:
                die("--diarize needs two audio channels, and %s has %s."
                    % (os.path.basename(a.media), have or "none ffprobe could read"),
                    "Channel diarisation reads which side is louder. One mono track holds "
                    "no such information. Transcribe each speaker's own file instead, or "
                    "drop --diarize and label the speakers yourself.")
            channels = 2
        extract_audio(ffmpeg, a.media, wav, a.offset, a.duration, channels)
        prompt = "" if a.no_prompt else (a.prompt or PUNCT_PROMPT)
        run_whisper(whisper, model, wav, prefix, a.threads, a.max_len, prompt, a.diarize)
        if not os.path.isfile(prefix + ".srt"):
            die("whisper wrote no SRT.", "Check the output above for its own error.")
        cues = read_srt(prefix + ".srt", a.offset)
        cues = [c for c in cues if c["end"] > c["start"]
                and c["text"].strip() and not NON_SPEECH.match(c["text"])]
        cues, labelled = normalise_speakers(cues)
        if not cues:
            die("the transcript came back empty. Is there speech in that file?")
        write_srt(cues, srt_path)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(cues, f, indent=1, ensure_ascii=False)
            f.write("\n")
        write_reading_copy(cues, read_path, a.gap_mark)
        if a.keep_wav:
            kept = os.path.join(out_dir, name + ".16k.wav")
            shutil.move(wav, kept)
            print("            wav:     %s" % kept)
    finally:
        if os.path.isdir(work):
            shutil.rmtree(work, ignore_errors=True)

    took = time.time() - t0
    words = sum(len(c["text"].split()) for c in cues)
    spoken = cues[-1]["end"] - cues[0]["start"]
    print("            %d cues, %d words, %.0fs of tape" % (len(cues), words, spoken))
    print("            took %.0fs" % took
          + (", %.1fx realtime" % (spoken / took) if took > 0 else ""))
    print("            %s" % srt_path)
    print("            %s" % json_path)
    print("            %s" % read_path)
    if a.diarize:
        print("            %d cue(s) carry a speaker label, written as SPEAKER_0: and "
              "SPEAKER_1: so the rest of the kit reads them." % labelled)
        print("            The label is per CUE, so a cue that straddles a turn gets one "
              "label and is wrong for part of it. Shorter cues tighten that: measured on a "
              "two track file whose turn changed at 12.0s, the default 90 character cap put "
              "the change at 6.78s and --max-len 40 put it at 8.83s. Neither is the real "
              "boundary. Open the waveform before you trust a turn to the second.")

    marks = sum(1 for c in cues if c["text"].rstrip()[-1:] in ".?!")
    if marks < max(1, len(cues) // 8):
        print("            WARNING: almost no sentence punctuation came back (%d cues of %d end on "
              ". ? or !). Everything downstream guesses sentence edges from pauses instead, which "
              "is worse. Try it again without --no-prompt." % (marks, len(cues)))
    print("next:       python3 bin/pick_pulls.py %s -n 8" % srt_path)
    print("            python3 bin/plan_clips.py %s -n 6 --out cuts.json" % srt_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
