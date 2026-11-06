# The one command

One long recording in, vertical clips out, with a reason attached to each one.

**Substitute your own file for the path below.** The kit ships no video, so this
block cannot run until you point it at a recording of your own. Keep the quotes:
a path with spaces in it breaks without them.

```bash
cd /path/to/content-line && .venv/bin/python bin/run_line.py "/full/path/to/your-recording.mp4" --niche specs/niche-business.json -n 3
```

A relative path works too, if you are already in the kit folder.

That is: take this video, use this niche, give me clips. It transcribes, repairs
the words the transcriber mis-heard, picks the moments, plans the cuts, sense
checks every piece it is about to render, and renders vertical clips.
**Nothing leaves the machine.** Nothing is posted and nothing is scheduled
unless you add `--publish` or `--schedule`, and even then `schedule_post.py`
writes a draft.

Everything lands in `work/<name of the source>/`, and the finished clips in
`work/<name of the source>/clips/`.

## The seven stages

| | |
|---|---|
| 1. transcribe | `transcribe.py`. Cached: on every later run over the same file it returns in under a second |
| 2. correct mis-heard words | `garble.py --fix`. See below. This is the stage most kits do not have |
| 3. pick moments | `pick_pulls.py` |
| 4. plan the cut | `plan_clips.py`. Builds the edit order |
| 5. choose the hook card | `hook_curate.py`. See below. `--no-hook-curate` leaves it alone |
| 6. sense check every piece | `sense_cuts.py`. Checks what is about to render, by filename |
| 7. render | `assemble_clip.py`. Carries the slow push |

`STOPPED at stage N of M` takes M from the stages the flags built, so the number
moves. Adding `--voice` adds two stages and makes it nine. Handing it a
transcript instead of a video drops the transcribe and the render.

`--broll <spec>` adds a pass after the render, over every clip it produced.

## What it costs, measured

Verified 2026-11-05 end to end on a real 28.5 minute 1920x1080 recording, 476 MB.
Three clips asked for, three produced. **91.59 seconds of wall clock**, from a raw
file with no transcript to three finished vertical clips.

| stage | |
|---|---|
| transcribe | 37.07s |
| correct mis-heard words | 1.5s |
| pick moments | 0.14s |
| plan the cut | 0.10s |
| sense check, all three pieces | 1.82s |
| render, all three clips | 51.24s |
| **total** | **91.59s** |

**The transcribe is paid once per file**, so a second pass over the same recording
costs about 53 seconds rather than 91. The three clips came out 1080x1920, h264,
on the hardware encoder, at 57.65s, 46.56s and 59.14s.

The first clip takes its opener from 09:25 and its close from 16:32, seven minutes
apart. **It plays edit order rather than tape order**, which is the part of this kit
that is genuinely hard and already built.

## Stage 2, the one that is easy to skip

A transcriber mis-hears uncommon words. On the test recording it heard
`home U of Stasis` where the speaker said `homeostasis`, four times in forty
seconds, and spelled it correctly eight times later in the same file.

**That is detectable without knowing anything about the subject**, because the
transcript contradicts itself. `garble.py` finds the contradiction and `--fix`
writes the correction into the cue that holds it. On the test file: 5 corrections
across 5 cues, then it re-checks its own output and reports that nothing
contradicts itself any more.

This runs **before** anything reads the text, so the moment picker, the cut
planner and the captions all see the repaired words. Until 2026-11-05 it was built
and was not a stage here, and a clip went out with `home U of Stasis` burned into
its captions three times.

It is **not** a vocabulary list. `garble.py`'s own docstring records that
experiment and its control: transcribing those same 70 seconds alone, with no
vocabulary and no prompt, spells the word correctly. It is a local decoding slip
that recovers on its own, so a word list would not have touched it.

## It objects per clip, and names the file

Stage 5 checks **every piece that is about to render** and names the file each
objection belongs to:

```
  A2  important-financially-cover-emergency-life-beyond-financially
  NEEDS A FIX, 1 serious, 46.56s   (clip_sense: USABLE, WITH ONE PROBLEM)
    [SERIOUS] no turn
```

**Two labels, and they answer different questions.** The first answers "may this be
posted" and comes from the faults found. `clip_sense`'s own verdict, in brackets,
answers "may this be cut" and is its existing calibration, printed unchanged.

The run then ends with the list again against the files on disk, because the
renders finish after the objections have scrolled past:

```
  WHAT WAS WRITTEN, AND WHAT IS WRONG WITH IT
    .../clips/actually-looking-tuesday-looking-shrunk-workbook-actually.mp4
      NEEDS A FIX, 1 serious   (clip_sense: USABLE, WITH ONE PROBLEM)
      [SERIOUS] refers to the rest of the recording
  3 of 3 carry a SERIOUS fault. Read it before that one is posted.
```

It also prints the planner's own objections per piece, which say things like
*"segment 4 starts inside a transcript cue, so 1521.94 is interpolated and can be
about a second out. Snap it to the waveform."*

### A clip may not open on a connective

A clip that opens on **Or, And, But, Because, Also, Then** or **So** points at
something the viewer has not heard, and at position 1 there is no earlier join to
listen to, so no amount of checking the tape repairs it. That is a fatal fault and
the opener has to change.

A clip did ship with this fault before 2026-11-05. It opened on *"Or you had a
stimulant, right?"* and the alcohol example that "Or" refers to played two
segments later, which made the clip unfollowable. It was excused in two places:
the planner switched the connective warning off for the hook, and the picker
forgave a connective whenever the line ended in a question mark, which a tag
question does.

**A connective-led question that stands on its own is still a good opener.** "So
what do you actually want?" is fine, because an interrogative is left once the
"So" is removed. "Or you had a stimulant, right?" is a statement with a tag on it.
That distinction is the rule, and both halves of it are checked in `kit_check.py`.

### The closing segment gets measured

The last segment is the most prominent position in the clip, so the planner reports
how far it sits from the body and how well it links to it:

```
the closing segment sits 256 seconds (23:29.0) past the end of the body and
links to it at 0.24. Read it against the rest: a close that far away can land
as a different subject.
```

**That is a measurement rather than a refusal.** A close seven minutes from the
body can still be the right close, so the number is reported and the judgement
stays with you.

## The picture moves now

Every clip used to be a static crop of one camera with captions burned over it.
There is a **slow push** on the speaker across the whole clip, on by default, and
it needs no footage and nothing sourced.

```json
"motion": {"enabled": true, "amount": 0.08}
```

`amount` is how much tighter it ends than it started, so 0.08 is eight per cent
across the clip. Small on purpose: past about 0.15 it reads as a camera move
rather than as drift, and it softens the picture, because the push is an upscale
of a frame already fitted to 1080x1920. Put `motion` in your style file to change
it or to switch it off. `focus_x` and `focus_y` aim it, the same two numbers the
static crop uses.

**Measured rather than asserted.** The same clip rendered twice, once with the
push and once without, compared frame by frame as a mean absolute pixel
difference:

```
t=0.3s    0.43      the two renders agree, which is encoder noise
t=10s     2.43
t=25s     4.85
t=40s    10.89
t=55s    16.72      a full push apart
```

They start identical and diverge steadily, which is what a zoom from 1.00 to 1.08
looks like. On a synthetic source, a 200x200 white box with nothing moving in it,
the predicted window at 3.8 seconds is 238x238 = 56644 pixels against 56646
measured.

**It has to be `zoompan` rather than the `zoom` setting.** ffmpeg evaluates
`crop`'s width and height once when it starts and `scale` cannot animate at all,
so that pair can only hold a FIXED zoom however it is written. The push also sits
in the picture stage, before the captions are burned, so the picture moves while
the words hold still.

## The hook card is chosen, out of your own words

The pinned card used to be the opener's first sentence cut to twelve words with an
ellipsis stuck on the end, and the planner told you to go and tighten it by hand.
`hook_curate.py` chooses instead:

```
A2  important-financially-cover-emergency-life-beyond-financially
    was:  What's important to you?
    now:  Can you financially cover any emergency in your life?
    why:  9 words, a question, speaks to you
```

**It writes nothing.** Every card is a contiguous run of your own words, in your
order, taken from the opening segment. That is the same contract
`caption_repair.py` holds. A card that paraphrases is a claim you never made,
pinned to the top of the frame for four seconds.

So it selects. Candidates are whole sentences and clause spans, scored on signals
the kit already computes: a question scores, a number scores, speaking to the
viewer scores, filler is punished, and a span starting mid sentence is marked down
because it usually leans on the words before it, which a card does not have.
Anything opening on a pronoun is refused, because "That is the part nobody tells
you" names nothing when it is the first thing on screen.

**It refuses.** When no span qualifies it says so, leaves the existing card alone
and records why in that piece's problems:

```
A3  dream-version-every-single-day-without-fail
    was:  What does the dream version of you do every single day without...
    now:  REFUSED, the card is unchanged
          'What does the dream version of you do every sing': 13 words, and the
          ceiling for a card is 9. Raise it with --max-words if you want longer cards
```

That one is a good hook that is simply long. `--hook-words 13` takes it, and the
card becomes the whole question with no ellipsis. Nine is the default because a
card is glanced at with the sound off.

## Assets, when you have them

`--broll <spec>` runs `bin/broll.py` over every clip the line produced, laying on
full-frame cutaways, picture in picture, lower thirds, dissolves, cover crops and
audio ducking. `specs/example-broll.json` documents the format. With no spec the
pass does not run, and the clips are the pushed talking head with captions.

Nothing here reads a Drive folder or picks assets for you yet.

## The niche profile

Two exist already:

- `specs/niche-business.json`, measured on 179 videos
- `specs/niche-couples.json`, which honestly reports that **no shape in its
  sample is measured on enough videos to steer anything**, so it will not try

To make one for a new niche, measure first and then distill:

```bash
.venv/bin/python bin/yt_probe.py "your search" --out research/niche-yours.json
```

```bash
.venv/bin/python bin/niche_calibrate.py research/niche-yours.json --out specs/niche-yours.json
```

### The profile steers the ranking, and it does not pick the hook

On the test recording all three chosen openers were questions, and
`niche-business.json` rates the `question` opener at lift 0.74 with
`recommend: false`. **The profile was applied and the questions still won.** Both
penalties fired, from that run's own `pulls.json`:

```
hand set hook points cut 26% because this niche's winners use the question opener less
Against: niche_shape (-5)
```

The real constraint is supply. `number` is the only opener that profile rewards,
at lift 1.35, and that recording contained none. A profile can only re-rank the
moments the tape actually holds.

## The voice profile, and why it is not in the command above

`--voice` is optional. Leave it off and no caption is drafted, which is why the
command at the top does not carry it. The clips still render.

`specs/voice.sample.json` is a TEST FIXTURE, built from 24 made-up captions, and
it says so inside its own file. It exists so the caption stages can be tested
without a real profile. **A caption drafted against it will not sound like you**,
so it has no place in a run whose output you intend to post.

Build a real one from a folder of your own writing, captions or transcripts, at
least twenty pieces:

```bash
.venv/bin/python bin/brand_voice.py ~/path/to/your-captions/ --split blank --out specs/voice.json
```

It will refuse to emit a profile if you give it too little, and say why. That
refusal is deliberate. Once `specs/voice.json` exists, add `--voice
specs/voice.json` to the command and the captions come with the clips.

## The one thing that will stop you

`plan_clips.py` builds a 45 to 150 second clip, so **the source has to be long
form**. Pointed at a 50 second file it correctly reports that no clip can be
built from it. Podcasts, intensives, webinars, long talks: those are the input.
A finished short clip is not.

## Files these flags point at

Every one of these is checked before any stage runs. A path that is not there
stops the run immediately and nothing is spent.

| flag | what it takes |
|---|---|
| `source` | any video or audio file, or an `.srt` / `.vtt` / `.txt` transcript |
| `--voice` | a `brand_voice.py` profile. Optional. Without it, no caption |
| `--niche` | a `niche_calibrate.py` profile |
| `--brand` | a brand spec, for the card look |
| `-n` | how many moments to pull, default 3 |
| `--keep-going` | render even when the sense check objects |
| `--publish` `--schedule` `--when` `--networks` | reach outside this machine, each behind its own flag |

## What this does not do yet

**No assets are sourced for you.** `--broll` lays on whatever a spec points at,
and writing that spec is still a manual job. Nothing reads a Drive folder, and
nothing chooses an image or a clip on your behalf.

**A refused hook card stays a truncation.** When no span in the opener qualifies,
the card is left as the trimmed transcript with its ellipsis, and the piece's
problems say so. Raising `--hook-words` or choosing a different moment are the two
ways out, and both are yours to make.

**One calibration question is open.** A clip with one serious fault is
`USABLE, WITH ONE PROBLEM` and the line renders it. Two stops the line. Whether a
batch where every piece carries one serious fault should stop before rendering is
a judgement about your tolerance, and it has not been made.
