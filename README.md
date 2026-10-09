# The content line

**In:** one long recording. A 26 minute single take, an hour of podcast, a recorded webinar.
**Out:** finished vertical clips, 1080x1920, captions burned in, ready for Reels, TikTok and Shorts.

Everything runs on your own computer, offline, free. Nothing here posts, schedules, uploads or
spends money. You drive it by talking to Claude Code opened inside this folder, or by running the
commands yourself.

---

## Getting it, and the first fifteen minutes

```bash
git clone https://github.com/iambellsina-lab/content-line.git
cd content-line
./setup.sh
```

`setup.sh` checks the four free things this needs and names whatever is missing. Nothing in it
reaches the network except the one model download, which asks first and prints its size.

Then, in order, and the order matters:

1. **`SETUP.md`** once, start to finish. It is the install, the look, and the honest list of what
   does not work yet.
2. **`BRAND-INTAKE.md`**, fifteen minutes. Skip it and every clip comes out competent and generic.
3. **`BEFORE-YOU-CUT.md`**, the three questions, for each recording. This is the step that pays for
   itself, and the README explains below why.

Fastest way to drive it: open this folder in Claude Code and say what you want. `skills/` holds the
instructions that teach it the method. Running the commands by hand works identically.

---

## The chain, in order

Answer the three questions first. Then five commands.

| | What | Command | What it costs |
|---|---|---|---|
| **0** | **Answer the three questions** | `BEFORE-YOU-CUT.md`, into `specs/mybrief.json` | ten minutes, and it is the one step that pays for itself |
| 1 | Tape to transcript | `bin/transcribe.py` | free, local, about 60x realtime |
| 2 | Transcript to cut lists | `bin/plan_clips.py --brief` | under a second |
| 3 | The gate, before any encode | `bin/check_dupes.py` | instant, exits 1 on an overlap |
| 4 | Cut lists to caption cards | `bin/cards_from_srt.py --cuts` | instant |
| 5 | Read every card cold | `bin/caption_check.py` | instant, and it is not a gate |
| 6 | Cut lists to finished clips | `bin/assemble_clip.py` | about 1.2x realtime per clip |

Step 0 is not paperwork. On the first real batch through this method, every expensive correction
traced back to one of those three questions going unasked: a whole cut list built in the wrong order
and thrown away, a length band nobody had agreed to, and six things that must never appear found
after the cuts already existed. `BEFORE-YOU-CUT.md` has the three and why each one bites.

---

## A worked example, run on this machine on 2026-10-08

Seven minutes of a real single take, in. Four finished captioned clips, out. Every command below was
run, in this order, and the numbers are what it printed.

```
# 1. tape -> transcript.  7s for 7 minutes of tape, 62.9x realtime
.venv/bin/python bin/transcribe.py work/longform-test.MOV --out-dir work/ --name rl
    -> 57 cues, 652 words, work/rl.srt  work/rl.cues.json  work/rl.txt

# 2. transcript -> cut lists, with the three answers already in hand
.venv/bin/python bin/plan_clips.py work/rl.srt -n 4 --brief work/readme-brief.json \
    --source work/longform-test.MOV --out-dir out/rl \
    --brand specs/example-edit-style.json --keep-audio --out work/rl-cuts.json --print
    -> brief read: order edit, length 30 to 120s, 0 forbidden, 0 moments dropped
    -> 4 clips: 31.44s, 37.50s, 32.71s, 41.89s

# 3. the gate
.venv/bin/python bin/check_dupes.py work/rl-cuts.json
    -> 4 clips, 6 pairs compared. PASS: no pair shares more than 1.00s.  exit 0

# 4. cut lists -> caption cards, every segment of every piece in one pass
.venv/bin/python bin/cards_from_srt.py work/rl.srt --cuts work/rl-cuts.json
    -> A1 25 cards, A2 19, A3 24, A4 11. 79 across 4 pieces, times marked source.

# 5. read every card cold
.venv/bin/python bin/caption_check.py work/rl-cuts.json --transcript work/rl.srt
    -> 68 findings: 39 blockers, 21 to review, 8 notes. 0 cards unmatched.

# 6. look at the arithmetic before spending the encode
.venv/bin/python bin/assemble_clip.py work/rl-cuts.json --dry-run
    -> 4 pieces, 31.44s to 41.89s, no two pieces share any footage

# 7. render
.venv/bin/python bin/assemble_clip.py work/rl-cuts.json --style specs/example-edit-style.json
    -> 4 files, 5m05s wall clock for 143.6s of finished video
```

**Verified after the render, not assumed:** all four files came back at 1080x1920, within 0.03
seconds of their planned duration, tagged `bt709/bt709/bt709` with AAC audio at 48 kHz. The source
reads `arib-std-b67 / bt2020`, so the colour fix fired on all four. `work/readme-brief.json` is the
three answers for this run: edit order, 30 to 120 seconds, nothing forbidden.

---

## The four things this does that a simple cutter does not

**1. It assembles in edit order, not tape order.** People circle. The sharpest version of a point
arrives twenty minutes after the story that proves it, and the line that should open the clip gets
said near the end. `plan_clips.py` puts the opener first wherever it was said, a closing line last
wherever it was said, and leaves the middle in tape order because that is where the reasoning lives.
`assemble_clip.py` plays the segments in list order. The first batch through this method was cut in
spoken order and all six videos were rebuilt.

**2. It fixes the colour.** iPhone HLG footage renders with wrong colour tags: the picture is right
and the file still says HDR, so it looks correct on a laptop and wrong on a phone. `color_fix:
"auto"` retags to bt709 with `setparams` when the source claims HDR, and leaves ordinary footage
alone. Three other approaches were measured and failed; the comment in `bin/assemble_clip.py`
records all of them. **The `setparams` route is also the portable one:** the `zscale` filter that
every tone-mapping recipe on the internet uses is absent from the stock Homebrew ffmpeg on this
machine, checked on 2026-10-08.

**3. It refuses to let two clips share tape.** Two pairs of finished reels once shared over fifty
seconds each and ended on the identical closing line. Nobody saw it until the files existed, and by
then the only fix was a rebuild. `check_dupes.py` finds it from the cut lists by arithmetic and
exits 1, so a build script stops before spending the encode.

**4. It reads every caption card the way a stranger would.** Scrolling, sound off, mid-card.
`caption_check.py` compares each card against the clause it came from and flags the shapes that
invert a speaker: a dropped negation, a dropped condition, a stranded "and", an unattributed line,
a known mishearing. It is **not a gate** and says so in its own output. Somebody still watches every
card muted, once.

---

## Two more things to know

**`--keep-audio` is the flag to think about.** The kit normalises to -14 LUFS by default. Pass
`--keep-audio`, or set `"keep_audio": true` in the cut list, for footage whose audio was already
processed, which is most podcast audio and anything mixed in a phone's own editor. Normalising
already-processed audio flattens it.

**Card times are in recording seconds, and the file says so.** `cards_from_srt.py --cuts` writes
`"times": "source"` into the cut list. `assemble_clip.py` maps them through the segment list, and
`caption_check.py` reads the same field. Do not renumber them by hand.

---

## What to read next

| File | What it holds |
|---|---|
| `BEFORE-YOU-CUT.md` | **The three questions.** Answer them before anything |
| `SETUP.md` | Install, the brand file, image hosting, and the full list of what does not work yet |
| `LONGFORM.md` | **The podcast case.** An hour of two people talking, down to clips |
| `LONG-FORM-INTAKE.md` | What each planning tool measures, with the numbers |
| `BRAND-INTAKE.md` | Six questions that give the clips a look instead of a default |
| `THE-SYSTEM.md` | The three layers and the loop, if you want the shape before you start |
| `skills/` | The instructions that teach Claude the method |
| `specs/` | Example brief, brand, style and cut list files to copy and change |

## What does not work yet, in one place

The full list is in `SETUP.md` section 6. The four that matter most for long form:

- **Nothing here has heard the audio.** Every segment order is a guess about meaning made from text.
  Energy lives in the waveform: loudness after a pause, pace, a laugh, a voice dropping. Where the
  audio disagrees with the plan, the audio wins. Listen to every join before rendering a batch.
- **The filenames the planner writes are machine-stitched and ugly.** The run above produced
  `make-400-000-year-somebody-tell-make.mp4`. Rename them. `the_argument` in a cut list is a stitch
  of first sentences, not a written argument, and the file says so.
- **Two speakers are not handled.** `plan_clips.py` scores moments as if one person is talking.
  `LONGFORM.md` says what to do about that and it is partly hand work.
- **One size.** Everything is 1080x1920 at 30fps. No square, no 4 by 5, nothing wider than tall.
