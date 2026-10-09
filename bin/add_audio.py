#!/usr/bin/env python3
"""Lay an audio track onto a rendered clip, normalised, without re-encoding the picture.

WHY THIS EXISTS, and the one thing to understand before using it:

Instagram's audio library is licensed, and attaching a track from it is what a scheduler like
Metricool does through an official integration. That library is NOT downloadable, so "just burn the
trending sound in" is not a thing this tool can do for you, and ripping a track to make it possible is
the part that is actually a copyright problem.

What Instagram says about audio you upload yourself (help.instagram.com/329208821595430, read
2026-10-02): "When we detect the audio you recorded or uploaded uses licensed audio, we'll
automatically change attribution from Original Audio to the artist and song title. Your reel will be
added to the audio page for that song." And: "audio tracks in your posts can become muted... While the
audio tracks of your post may be muted, your post can still be viewed."

So detection and attribution work. Supplying the file legally is your problem, not a technical one.

THREE LEGITIMATE SOURCES, in the order they are usually the right answer:

1. ORIGINAL AUDIO. A voice reading the line. Free, no rights question, no mute risk, and it becomes a
   sound other people can reuse, which is its own distribution. On macOS: say -v Daniel -o v.aiff "..."
2. MUSIC YOU HAVE LICENSED. Epidemic Sound, Artlist, or a track you own. Safe, though it will not be
   the trending sound.
3. THE TRENDING SOUND ITSELF. Attach it in the scheduler, not here.

Usage:
    python3 bin/add_audio.py clip.mp4 track.m4a -o out.mp4
    python3 bin/add_audio.py clip.mp4 voice.aiff -o out.mp4 --lufs -14
    python3 bin/add_audio.py clip.mp4 bed.mp3 -o out.mp4 --duck 0.25   # quiet bed under a voice

The video stream is copied, never re-encoded, so nothing is lost and it is fast.
"""
import argparse, json, subprocess, sys
from pathlib import Path


def probe(path, stream="a"):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", stream + ":0",
         "-show_entries", "stream=codec_name:format=duration",
         "-of", "json", str(path)], capture_output=True, text=True)
    if out.returncode != 0:
        return {}
    try:
        d = json.loads(out.stdout)
    except Exception:
        return {}
    res = {}
    if d.get("streams"):
        res["codec"] = d["streams"][0].get("codec_name")
    if d.get("format", {}).get("duration"):
        res["duration"] = float(d["format"]["duration"])
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("audio")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--lufs", type=float, default=-14.0,
                    help="integrated loudness target, default -14 which is the platform norm")
    ap.add_argument("--duck", type=float, default=None,
                    help="multiply the audio gain, e.g. 0.25 for a bed under a voice")
    ap.add_argument("--start", type=float, default=0.0, help="seconds into the track to start")
    ap.add_argument("--loop", action="store_true",
                    help="repeat the audio to fill the clip. Right for a music bed, WRONG for a voice, "
                         "which is why it is off by default: a looped voice says the line twice")
    a = ap.parse_args()

    v, s = Path(a.video), Path(a.audio)
    for p in (v, s):
        if not p.exists():
            sys.exit("missing: " + str(p))

    vid = probe(v, "v")
    if not vid.get("codec"):
        sys.exit("no video stream in " + str(v))
    vdur = vid.get("duration")
    adur = probe(s).get("duration")
    if vdur and adur and adur + 0.05 < vdur - a.start:
        if a.loop:
            print(f"note: audio is {adur:.1f}s against a {vdur:.1f}s clip, and --loop is on, "
                  f"so it will repeat.", file=sys.stderr)
        else:
            print(f"note: audio is {adur:.1f}s against a {vdur:.1f}s clip. The rest is silence. "
                  f"Pass --loop if this is a music bed.", file=sys.stderr)

    chain = []
    if a.duck is not None:
        chain.append(f"volume={a.duck}")
    chain.append(f"loudnorm=I={a.lufs}:TP=-1.0:LRA=11")
    af = ",".join(chain)

    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-i", str(v)]
    if a.loop:
        cmd += ["-stream_loop", "-1"]
    cmd += ["-ss", str(a.start), "-i", str(s)]
    # apad then -shortest gives silence after a short track instead of a truncated clip
    if not a.loop:
        af = af + ",apad"
    cmd += ["-filter:a", af,
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy",                 # picture untouched
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-shortest", "-movflags", "+faststart", str(a.out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("ffmpeg failed:\n" + r.stderr[-1500:])

    got = probe(a.out)
    gotv = probe(a.out, "v")
    print(f"wrote {a.out}")
    print(f"  video {gotv.get('codec')} copied, audio {got.get('codec')}, "
          f"{got.get('duration', 0):.2f}s, normalised to {a.lufs} LUFS")


if __name__ == "__main__":
    main()
