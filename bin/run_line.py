#!/usr/bin/env python3
"""run_line.py: one recording in, a scheduled draft out. The whole line, driven.

WHY THIS EXISTS. `THE-GAP.md` re-measured 2026-11-04 found seven of the nine
capabilities working end to end and nothing driving them. A buyer who owns this kit
has to run six tools by hand in the right order with exact flag syntax, and the
syntax bites: `--caption` takes a file rather than a string, `--when` needs a
timezone offset. The spec is that nobody should have to think about it once they
have sent one setup prompt. This is the thing that reads that prompt.

WHAT IT DOES NOT DO, and this is deliberate. It stops at the edge of the machine.
Nothing is uploaded and nothing is scheduled unless you pass the flag that says so,
and even then `schedule_post.py` creates a DRAFT, never a post. The house rule is
that posts wait for a person.

WHAT IT IS NOT. It is not a new engine. Every stage is the kit's own tool, run as a
subprocess exactly as a human would run it, with the command printed. If a stage
fails you get its real output and the command to reproduce it, because a wrapper
that swallows the error of the thing it wraps is worse than no wrapper.

Usage:
    python3 bin/run_line.py recording.mp4 --voice specs/voice.json
    python3 bin/run_line.py transcript.srt --voice v.json --niche specs/niche-profile.json
    python3 bin/run_line.py transcript.srt --voice v.json --publish --schedule \\
        --when 2026-11-10T09:00:00-05:00 --networks threads
"""
import argparse
import json
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

BIN = Path(__file__).resolve().parent
KIT = BIN.parent

TRANSCRIPT_SUFFIXES = {".srt", ".vtt", ".json", ".txt"}

# Stages that reach outside this machine. Each needs its own flag, and the flag is
# named after what it actually does rather than after the stage.
OUTBOUND = {"publish", "schedule"}


def say(msg=""):
    print(msg, flush=True)


def die(msg, code=1):
    say()
    say("  STOPPED. %s" % msg)
    sys.exit(code)


class Stage:
    """One tool run. Holds enough to reproduce it by hand."""

    def __init__(self, name, argv, produces=None, optional=False, stdout_to=None,
                 show_lines=8, after=None):
        self.name = name
        self.argv = argv
        self.produces = produces
        self.optional = optional
        # How much of this stage's output to print. The default suits a tool that
        # either works or says one short thing. A stage whose OUTPUT IS THE PRODUCT,
        # like the sense check, has to print in full: tailing it to 8 lines hid the
        # objections for the first two pieces of a three piece batch.
        self.show_lines = show_lines
        # Runs after a successful call, before the caller checks `produces`. One tool
        # here writes an output file only when it has something to write, and the rest
        # of the line needs that path to exist either way.
        self.after = after
        # Some tools print their machine-readable form to stdout rather than to a
        # file. Those get written here instead of echoed, because 16KB of JSON in
        # the middle of a progress log helps nobody.
        self.stdout_to = stdout_to
        self.code = None
        self.seconds = None
        self.out = ""

    @property
    def command(self):
        return " ".join(shlex.quote(str(a)) for a in self.argv)

    def run(self, echo=True):
        if echo:
            say("    $ %s" % self.command)
        t0 = time.time()
        p = subprocess.run(self.argv, capture_output=True, text=True, cwd=str(KIT))
        self.seconds = time.time() - t0
        self.code = p.returncode
        if self.stdout_to and self.code == 0 and (p.stdout or "").strip():
            Path(self.stdout_to).write_text(p.stdout)
            self.out = p.stderr or ""
        else:
            self.out = (p.stdout or "") + (p.stderr or "")
        if self.code == 0 and self.after:
            self.after()
        return self.code == 0


def tail(text, n=12):
    lines = [l for l in text.splitlines() if l.strip()]
    return lines[-n:] if len(lines) > n else lines


def is_transcript(path: Path) -> bool:
    return path.suffix.lower() in TRANSCRIPT_SUFFIXES


def main():
    ap = argparse.ArgumentParser(
        description="Drive the whole content line: recording to scheduled draft.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Nothing leaves this machine without --publish or --schedule.",
    )
    ap.add_argument("source", help="a recording (mp4, mov, wav, m4a) or a transcript (srt, vtt, json)")
    ap.add_argument("--voice", help="a profile from brand_voice.py. Without it, no caption is drafted")
    ap.add_argument("--niche", help="a profile from niche_calibrate.py, to rank moments by what the niche rewards")
    ap.add_argument("--brand", help="a brand file for the render")
    ap.add_argument("--broll", help="a broll.py asset layer spec. Lays cutaways, picture in "
                                    "picture and lower thirds over every rendered clip")
    ap.add_argument("--hook-words", type=int, default=9,
                    help="the ceiling for a hook card (default 9). A card is glanced at "
                         "with the sound off, so shorter wins")
    ap.add_argument("--no-hook-curate", action="store_true",
                    help="leave the hook card as the trimmed transcript")
    ap.add_argument("--out-dir", help="where everything lands (default work/<name of the source>)")
    ap.add_argument("-n", type=int, default=3, help="how many moments to pull (default 3)")
    ap.add_argument("--publish", action="store_true",
                    help="upload the rendered clip and give it a public URL. Leaves this machine")
    ap.add_argument("--schedule", action="store_true",
                    help="create a DRAFT in the scheduler. Needs --when and --networks. Never posts")
    ap.add_argument("--when", help="ISO time WITH a timezone offset, e.g. 2026-11-10T09:00:00-05:00")
    ap.add_argument("--networks", help="comma separated, e.g. threads,instagram")
    ap.add_argument("--keep-going", action="store_true",
                    help="do not stop at the first failed stage. Off by default")
    a = ap.parse_args()

    src = Path(a.source)
    if not src.exists():
        die("no such file: %s" % src)

    # Every flag that names a file is checked here, for the same reason the source is.
    # A bad --voice path used to survive until the caption stage, which is after the
    # transcribe and the render, so the run spent minutes before reporting a typo.
    # It also made a doc defect invisible: the headline command in USING-IT.md pointed
    # --voice at a file that was never there, and a real user hit it before any test did.
    for flag, val in (("--voice", a.voice), ("--niche", a.niche), ("--brand", a.brand),
                      ("--broll", a.broll)):
        if val and not Path(val).exists():
            die("%s points at a file that is not there: %s\nNothing was run." % (flag, val))

    # Refuse early and completely. A run that dies at stage 7 for a missing flag has
    # already spent several minutes of rendering.
    if a.schedule:
        missing = [f for f, v in (("--when", a.when), ("--networks", a.networks)) if not v]
        if missing:
            die("--schedule needs %s. Nothing was run." % " and ".join(missing))
        if a.when and ("+" not in a.when[10:] and "-" not in a.when[10:] and not a.when.endswith("Z")):
            die("--when must carry a timezone offset, for example 2026-11-10T09:00:00-05:00. "
                "Got: %r. Nothing was run." % a.when)
    if a.schedule and not a.publish:
        die("--schedule without --publish has nothing to post. A scheduler cannot reach a file on "
            "your computer, so the clip needs a public URL first. Add --publish. Nothing was run.")

    slug = src.stem.replace(" ", "-").lower()
    out_dir = Path(a.out_dir) if a.out_dir else (KIT / "work" / slug)
    out_dir.mkdir(parents=True, exist_ok=True)

    say()
    say("  THE LINE: %s" % src.name)
    say("  everything lands in %s" % out_dir)
    outbound = [n for n in ("publish", "schedule") if getattr(a, n)]
    if outbound:
        say("  LEAVES THIS MACHINE: %s. The scheduler stage creates a draft, never a post."
            % ", ".join(outbound))
    else:
        say("  nothing leaves this machine on this run")
    say()

    stages = []

    # 1. transcript
    transcript = src
    if not is_transcript(src):
        st = Stage("transcribe",
                   [sys.executable, str(BIN / "transcribe.py"), str(src),
                    "--out-dir", str(out_dir), "--name", slug],
                   produces=out_dir / ("%s.srt" % slug))
        stages.append(st)
        transcript = st.produces

    # 1b. Correct the words the transcriber mis-heard, BEFORE anything reads the text.
    #
    # A real run produced a clip whose captions read "home U of Stasis" three times.
    # The speaker said homeostasis. garble.py catches it by the tape contradicting itself: the same
    # transcript spells the word correctly 4 times from 20:30 onward, so the garbled
    # run from 13:22 can be repaired without knowing anything about the subject.
    #
    # It was already built, already tested in kit_check.py, and was not a stage here, so
    # every caption the line produced carried whatever whisper heard. On the real
    # recording this makes 5 corrections across 5 cues and then re-checks its own output.
    #
    # NOT a --terms word list. garble.py's docstring records that experiment and its
    # control: transcribing those same 70 seconds alone, with no vocabulary and no
    # prompt, spells homeostasis correctly. It is a local decoding slip that recovers
    # on its own, so a word list would not have touched it.
    # Keep the input's own extension. garble.py reads an SRT, a .cues.json or plain text,
    # and writing a .txt back out as ".srt" would mislabel it for everything downstream.
    corrected = out_dir / ("%s.corrected%s" % (slug, transcript.suffix or ".srt"))

    def _keep_original(src_path=transcript, dst=corrected):
        # --fix writes nothing when nothing contradicts itself, which is the common case
        # and is not a failure. The rest of the line still needs one transcript path.
        if not Path(dst).exists():
            shutil.copyfile(str(src_path), str(dst))

    stages.append(Stage("correct mis-heard words",
                        [sys.executable, str(BIN / "garble.py"), str(transcript),
                         "--fix", str(corrected)],
                        produces=corrected, show_lines=40, after=_keep_original))
    transcript = corrected

    pulls = out_dir / "pulls.json"
    cuts = out_dir / "cuts.json"
    draft = out_dir / "draft.json"

    # 2. pick the moments
    argv = [sys.executable, str(BIN / "pick_pulls.py"), str(transcript),
            "-n", str(a.n), "--out", str(pulls)]
    if a.niche:
        argv += ["--niche", a.niche]
    stages.append(Stage("pick moments", argv, produces=pulls))

    # 3. plan the cut
    clips_dir = out_dir / "clips"
    argv = [sys.executable, str(BIN / "plan_clips.py"), str(transcript),
            "-n", str(a.n), "--out", str(cuts), "--source", str(src),
            "--out-dir", str(clips_dir)]
    if a.brand:
        argv += ["--brand", a.brand]
    stages.append(Stage("plan the cut", argv, produces=cuts))

    # 3b. Choose the hook card, out of the speaker's own words.
    #
    # plan_clips fills it with the opener's first sentence cut to twelve words, with an
    # ellipsis if it overran, and then says in the piece's own problems to go and tighten
    # it by hand. The card is the one frame that decides whether anybody watches, so a
    # mechanical truncation is the wrong thing to leave there. hook_curate.py SELECTS a
    # contiguous run of the speaker's own words and refuses when none qualifies. It
    # invents no wording, which is the same contract caption_repair.py holds.
    if not a.no_hook_curate:
        stages.append(Stage("choose the hook card",
                            [sys.executable, str(BIN / "hook_curate.py"), str(cuts),
                             "--write", "--max-words", str(a.hook_words)],
                            produces=cuts, show_lines=60))

    # 4. does each piece stand up alone, before spending minutes rendering it.
    #
    # This reads cuts.json rather than pulls.json, and the difference is a correctness
    # one. clip_sense.py checks ONE clip, and handed a pulls JSON with no --pull it
    # reads index 0. pick_pulls and plan_clips are two separate selections over the
    # same transcript and they do not agree, so the old call printed objections about
    # a span that was never rendered. Measured 2026-11-05: pull starts 1168.0 / 565.0
    # / 1526.6 against piece starts 565.0 / 826.0 / 1113.0, one of three overlapping.
    # sense_cuts.py checks every piece and names the file each objection belongs to.
    sense = out_dir / "sense.json"
    stages.append(Stage("sense check every piece that will render",
                        [sys.executable, str(BIN / "sense_cuts.py"), str(cuts),
                         "--transcript", str(transcript), "--out", str(sense)],
                        produces=sense, show_lines=400))

    # 5. render, only when there is real footage behind the cut list
    if not is_transcript(src):
        argv = [sys.executable, str(BIN / "assemble_clip.py"), str(cuts)]
        if a.brand:
            argv += ["--style", a.brand]
        stages.append(Stage("render", argv, produces=clips_dir))

    # 6. the caption, in their own measured voice.
    # --out writes a DIRECTORY of markdown drafts for a person to read. --json writes
    # the machine-readable form to stdout and SUPPRESSES --out, so the two cannot be
    # had in one call. Both are wanted: the markdown is what they edit, the JSON is
    # what the scheduler stage lifts a caption out of. The tool runs in under a tenth
    # of a second, so it runs twice rather than one of them going without.
    if a.voice:
        base = [sys.executable, str(BIN / "draft_content.py"), str(pulls), "--voice", a.voice]
        if a.niche:
            base += ["--niche", a.niche]
        stages.append(Stage("draft the caption", base + ["--json"],
                            produces=draft, stdout_to=draft))
        stages.append(Stage("write the drafts to read", base + ["--out", str(out_dir / "drafts")],
                            produces=out_dir / "drafts"))

    failures = []
    done = []
    for i, st in enumerate(stages, 1):
        say("  %d. %s" % (i, st.name))
        ok = st.run()
        for line in tail(st.out, st.show_lines):
            say("       %s" % line)
        if ok:
            if st.produces and not Path(st.produces).exists():
                say("       exit 0 but %s was not written" % st.produces)
                failures.append(st)
            else:
                done.append(st)
        else:
            say("       exit %s" % st.code)
            failures.append(st)
            if not a.keep_going:
                say()
                say("  STOPPED at stage %d of %d. Reproduce it with:" % (i, len(stages)))
                say("    cd %s && %s" % (KIT, st.command))
                say("  Add --keep-going to run the rest anyway.")
                _manifest(out_dir, src, stages, a)
                sys.exit(1)
        say()

    # The second picture source, over the finished clips. It needs the rendered files to
    # exist, so it is here rather than in the stage list, the same reason publish is.
    if a.broll:
        spec = Path(a.broll)
        clips = sorted(clips_dir.rglob("*.mp4")) if clips_dir.exists() else []
        if not clips:
            say("  SKIPPED broll: no rendered clip to lay assets over. A transcript on its "
                "own has no video, so give this a recording rather than an .srt.")
        else:
            say("  broll over %d clip(s), from %s" % (len(clips), spec.name))
            for clip in clips:
                st = Stage("broll: %s" % clip.name,
                           [sys.executable, str(BIN / "broll.py"), str(clip),
                            "--spec", str(spec), "--cuts", str(cuts)])
                say("    %s" % clip.name)
                ok = st.run()
                for line in tail(st.out, 10):
                    say("       %s" % line)
                (done if ok else failures).append(st)
            say()

    # The edge of the machine. Everything past here needed a flag.
    public_url = None
    if a.publish:
        clip = _newest_render(out_dir)
        if not clip:
            say("  SKIPPED publish: no rendered clip was produced. A transcript on its own has no "
                "video to upload, so give this a recording rather than an .srt.")
        else:
            st = Stage("publish", [sys.executable, str(BIN / "publish_media.py"), str(clip), "--json"])
            say("  publish: %s" % clip.name)
            if st.run():
                public_url = _url_from(st.out)
                say("       %s" % (public_url or "uploaded, no URL found in the output"))
                done.append(st)
            else:
                for line in tail(st.out, 8):
                    say("       %s" % line)
                failures.append(st)
            say()

    if a.schedule:
        cap = _caption_file(draft, out_dir)
        if not public_url:
            say("  SKIPPED schedule: there is no public URL to post. The publish stage did not "
                "produce one, and a scheduler cannot reach a file on your computer.")
        elif not cap:
            say("  SKIPPED schedule: no caption was drafted. Pass --voice so there is something to post.")
        else:
            st = Stage("schedule a draft",
                       [sys.executable, str(BIN / "schedule_post.py"),
                        "--media", public_url, "--caption", str(cap),
                        "--when", a.when, "--networks", a.networks])
            say("  schedule a draft")
            ok = st.run()
            for line in tail(st.out, 14):
                say("       %s" % line)
            (done if ok else failures).append(st)
            say()

    man = _manifest(out_dir, src, stages, a)

    say("  %d stage(s) ran, %d failed." % (len(stages), len(failures)))
    if failures:
        say("  failed: %s" % ", ".join(s.name for s in failures))
    say("  what to look at: %s" % man)
    _posting_summary(sense, clips_dir)
    if not a.schedule:
        say()
        say("  NOTHING WAS SCHEDULED AND NOTHING WAS POSTED.")
        say("  To take it the rest of the way, add:")
        say("    --publish --schedule --when 2026-11-10T09:00:00-05:00 --networks threads")
    say()
    return 1 if failures else 0


def _posting_summary(sense_path: Path, clips_dir: Path):
    """Name every file that was written and the objections attached to it.

    This is the last thing printed because it is the thing to act on. With
    --keep-going the renders happen AFTER the objections scroll past, so a batch
    used to end with three finished files and no record of which one carried which
    fault. An unattributed refusal cannot be acted on, so it degrades to a warning
    that has to be ignored in order to use the batch.
    """
    if not sense_path.exists():
        return
    try:
        data = json.loads(sense_path.read_text())
    except (ValueError, OSError):
        return
    pieces = data.get("pieces") or []
    if not pieces:
        return

    on_disk = {}
    if clips_dir.exists():
        for v in clips_dir.rglob("*.mp4"):
            on_disk[v.stem] = v

    say()
    say("  WHAT WAS WRITTEN, AND WHAT IS WRONG WITH IT")
    for r in pieces:
        name = r.get("filename") or r.get("piece") or "?"
        v = on_disk.get(name)
        where = str(v) if v else "not rendered"
        grave = r.get("serious_or_worse") or 0
        say()
        say("    %s" % where)
        say("      %s%s   (clip_sense: %s)"
            % (r.get("label") or r.get("verdict") or "?",
               ", %d serious" % grave if grave else "",
               r.get("verdict") or "?"))
        for f in r.get("faults") or []:
            if f["severity"] in ("serious", "fatal"):
                say("      [%s] %s" % (f["severity"].upper(), f["fault"]))

    unrendered = [r for r in pieces if (r.get("filename") or "") not in on_disk]
    bad = [r for r in pieces if r.get("serious_or_worse")]
    say()
    if bad:
        say("  %d of %d carry a SERIOUS fault. Read it before that one is posted."
            % (len(bad), len(pieces)))
    if unrendered and len(unrendered) < len(pieces):
        say("  %d planned piece(s) produced no file." % len(unrendered))
    say()


def _newest_render(out_dir: Path):
    vids = sorted(out_dir.rglob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    return vids[0] if vids else None


def _url_from(text: str):
    for tok in text.replace('"', " ").replace(",", " ").split():
        if tok.startswith("http://") or tok.startswith("https://"):
            return tok.rstrip(".")
    return None


def _caption_file(draft: Path, out_dir: Path):
    """schedule_post.py reads the caption from a file, so write one out of the draft.

    draft_content.py --json returns {"drafts": [{"lines": [...]}, ...]}. The first
    draft is the highest scoring moment, and its lines are sentences the speaker
    actually said, so they join with a blank line between them.
    """
    if not draft.exists() or draft.is_dir():
        return None
    try:
        d = json.loads(draft.read_text())
    except Exception:
        return None
    drafts = d.get("drafts") or []
    if not drafts:
        return None
    lines = drafts[0].get("lines") or []
    text = "\n\n".join(l.strip() for l in lines if l and l.strip())
    if not text:
        return None
    cap = out_dir / "caption.txt"
    cap.write_text(text.rstrip() + "\n")
    return cap


def _produced_files(produces):
    """What a stage actually wrote, when what it writes is a directory."""
    if not produces:
        return None
    p = Path(produces)
    if not p.exists():
        return None
    if p.is_file():
        return [p.name]
    return sorted(f.name for f in p.iterdir() if f.is_file())


def _manifest(out_dir: Path, src: Path, stages, a):
    man = out_dir / "run.json"
    man.write_text(json.dumps({
        "source": str(src),
        "when_run": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "left_this_machine": [n for n in ("publish", "schedule") if getattr(a, n)],
        "stages": [{
            "name": s.name,
            "command": s.command,
            "exit": s.code,
            "seconds": round(s.seconds, 2) if s.seconds else None,
            "produced": str(s.produces) if s.produces else None,
            # A stage that writes a directory used to record the directory and nothing
            # else, so run.json did not say what the render actually produced. The
            # render stage wrote three files and the manifest named none of them.
            "files": _produced_files(s.produces),
        } for s in stages],
    }, indent=1) + "\n")
    return man


if __name__ == "__main__":
    sys.exit(main())
