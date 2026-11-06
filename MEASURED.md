# What was measured, and what it showed

Every number here came from running the code on real input and reading the raw
output. Nothing is estimated unless it says so. Where a figure belongs to a
particular date it carries that date, because a measurement is evidence about the
day it was taken.

Machine for all of it: an Apple M4, 10 cores.

---

## 1. The render chain takes about fifteen seconds

A run that was believed to have taken three hours was reconstructed stage by
stage from the specs it left behind. The source: **14.235 seconds**, stored
1080x1920 with a `-90` display matrix, HEVC, 16 MB. The card spec: 8 caption
cards.

| stage | what it does | wall |
|---|---|---|
| 1. audio extract | ffmpeg, to 16 kHz mono wav | **0.07s** |
| 2. transcribe | whisper.cpp `base.en`, on Metal | **0.64s** |
| 3. card render | Pillow, 8 cards at 1080x1920 RGBA | **2.84s** |
| 4. composite and encode | ffmpeg, 8 overlays, libx264 | **11.3s** |
| | **total** | **about 15 seconds** |

The reconstruction produced 21.51 MB against the 21,522,092 bytes of the
surviving original, so this is the same run rather than a lookalike.

**Nothing in the chain can take three hours on a 14 second clip.** The per-card
timings in that run's spec file are hand-authored to a tenth of a second, which
is the signature of an authoring loop rather than a compute loop. **The hours
went into deciding what the clip should say.** No encoder change addresses that,
and this is why `run_line.py` exists: the decisions it can make without being
asked are the hours.

## 2. The heat was real, and the cause was a comment that was wrong

Stage 4 burned **97.79 seconds of user CPU** to produce 14 seconds of video.
Across ten cores that is sustained full load, and sustained full load is what
spins the fans.

Two causes, both measured, both fixed:

| variant | wall | user CPU |
|---|---|---|
| as it ran: libx264 preset medium, every card looped over the whole clip | 11.3s | 97.8s |
| hardware encoder, identical filter graph | 7.0s | 43.5s |
| hardware encoder, each card trimmed to its own window | 3.4s | 18.6s |

Verified equivalent at **SSIM 0.984472** between the original output and the
fixed one, and every caption checked frame by frame at each of the eight card
windows and at both of its edges.

**The part that stings.** `ffmpeg -version`, read live, showed the build
configured with `--enable-videotoolbox`, and `ffmpeg -encoders` listed
`h264_videotoolbox`. **The hardware encoder had been there the whole time.**
Every encoder call hardcoded software x264 on the strength of a comment at the
top of the renderer claiming the local ffmpeg carried only `--enable-libx264`.
That comment was false, and nobody had checked it against the binary.

**A file's own header comment is not evidence.** This is the second time that
exact lesson has been paid for in this repo: a module once claimed in its header
that two named tests imported it, and neither did.

**The second half is worse, and it is the transferable one.** The same encoder
fix had already been made, three weeks earlier, in one of the two trees that
share this code. The benchmark is still written in `bin/kit_common.py`:

    libx264 -preset medium -crf 18    wall 4.56s    CPU 33.97s
    h264_videotoolbox -b:v 12M        wall 4.12s    CPU  3.02s

The other tree never got it, the video that caused the complaint went through
that tree, and three weeks later the same complaint arrived again. **A fix
applied to one copy of a thing is not applied.**

After both fixes, the same clip start to finish: **4.12s wall and 19.19s CPU**,
against 14.16s and 97.79s. Caption output unchanged.

**An estimate, labelled as one.** 31 rendered outputs survived from that period,
1,854 MB in total. At the 12 Mbit/s they were written at, that is roughly 1,236
seconds of finished video, and at the measured 6.87 CPU-seconds per second of
video, **about 2.4 CPU-hours across the batch.** That is arithmetic from two
measured numbers and is not itself a measurement.

## 3. One warning was already correct, and nobody read it

The tool reported that the source was 1920x1080 once autorotated, so filling a
1080x1920 frame would enlarge it 1.78x and crop away most of the picture. That
warning was accurate. The soft, over-cropped output everyone complained about was
a horizontal source being forced into a vertical frame, exactly as predicted.
**The tool told the truth into a log nobody opened**, which is why stage output
that carries an objection now prints in full instead of being tailed to 8 lines.

---

## 4. The research loop was connected, and inert

A reasonable reading of `grep -n "niche-.*\.json"` across the two generators
returns nothing, and the conclusion drawn from that was that no generator reads
research. **The grep was accurate and the conclusion was wrong.** Both generators
already accepted a `--niche` profile and already imported the hook patterns. The
filename does not appear because the profile arrives as a command line argument.

What running it showed instead: **a 179-video profile loaded, announced itself on
stderr, and changed not one score.** `niche_shape` appeared **zero times** in the
output.

Three faults made it inert, and each is now pinned by a test:

1. **It could praise but never warn.** Both consumers kept only shapes marked
   `recommend`. In the business profile, `question` measures at lift **0.74**,
   meaning winners in that niche use question openers *less* than everyone else.
   That finding was discarded on load, while a hand-set rule went on awarding
   +8 for a question opener. **The guess outvoted the measurement and the output
   never mentioned it.**
2. **The measured signal was capped at 6 points** against hand-set signals
   running to 16 and 14. Even a direct hit could not move a ranking.
3. **The matcher read titles and the clipper reads speech.** The hook patterns
   are anchored at `^`. `"So what was the moment you knew?"` matched no shape at
   all, because of the word "So". Titles do not open with discourse markers and
   speech constantly does, so **the most common opener in real footage was
   invisible to the one part of the kit that reads research.** The file had
   already been bitten by this once in the other direction: its `number` pattern
   carries a comment about transcripts writing "Three" where titles write "3".

### What changed

`niche_calibrate.py` gained `strip_discourse`, `match_hook`, `load_profile` and
`shape_verdict`. **One loader and one matcher, shared by the producer and both
consumers**, so the two ends cannot drift apart again. Every measured shape is
kept, with a confidence derived from how many videos actually used it, and a
shape the niche punishes now subtracts points. Thin evidence still moves almost
nothing: a lift of 3.0 observed on a single video scores **0.30 points**, which
is the producer's own stated ethic enforced at the far end. When measurement
contradicts a hand-set guess, the guess is damped, and the output says so in
words a reader can check.

### The proof

Same transcript, same code, three research inputs:

| window opener | no research | punishes question openers | rewards them |
|---|---|---|---|
| `"So what was the moment..."` | 92.3 | **83.5** | **99.9** |
| `"Three things killed..."` | 76.4 | **82.8** | 64.8 |

**16.4 points of swing on one window, in opposite directions, from research
alone.** The two profiles no longer select the same clips: one cuts from 10.5s,
the other from 23.5s.

And the caption drafter, same source, two profiles:

- the one that punishes question openers writes *"The second was Tuesday
  meetings. Ninety minutes, every week, for a year."*
- the one that rewards them writes *"Why did it take us eleven months to see
  that?"*

The first avoided a question opener because its winners avoid questions. That is
the loop closing.

### What stops it going quiet again

`bin/test_niche_loop.py`, **27 checks**, all passing. It asserts that a punishing
profile lowers a score and a rewarding one raises it, that `niche_shape` actually
appears in the output, that two profiles select different clips and write
different openers, that thin evidence stays weak, and that **a run with no
profile is identical to before**, so nothing regressed for anyone already using
the kit. The check that would have caught the original fault is one line:
`niche_shape` present in the output at all.

---

## 5. The sense check was examining a clip that was never rendered

This one is the most useful finding in the file, because the guard looked like it
was working.

A run halted before rendering and printed objections, including one about a
speaker saying `"XYZ"` out loud as a placeholder. That looked like the quality
gate doing its job. It was not.

`run_line.py` called `clip_sense.py` on `pulls.json`, and `clip_sense` checks
**one** clip: its loader reads `idx = (pull - 1) if pull else 0`, and no `--pull`
was passed. **So a three clip batch had one clip checked.**

Worse, the one it checked was not in the output. `pick_pulls` and `plan_clips`
are two separate selections over the same transcript, contiguous 35 to 75 seconds
against assembled 45 to 150 across segments, and the renderer renders
`plan_clips`' list. Measured on a real 28.5 minute recording:

    pull  first starts      1168.0    565.0   1526.6
    piece first segments     565.0    826.0   1113.0

**One of three overlaps.** The line printed objections about a 38 second span
that no rendered piece begins at, and the three files it actually wrote went
unchecked.

Checking the right clips turned up three serious faults, one per rendered clip.
The one that justifies the whole exercise: the transcriber wrote **`'home U of Stasis'`**
where the speaker said **`homeostasis`**, and spelled it correctly four times
elsewhere in the same transcript. **It occurs three times in that clip and lands
on four caption cards**, because cards are split at four words and the phrase
straddles the boundaries: `essentially home U of` then `Stasis is baseline.`

A human did catch this once, on 2026-10-15, by reading the sentence out loud,
and that is why `garble.py` exists at all. What had never happened is the kit
catching it: the structural checks all pass, because `home U of Stasis` is
grammatical English that opens cleanly and finishes its sentence. Until
2026-11-05 `garble.py` was not a stage in the line, so the one tool that could
see it never ran.

**Reproducing a number is not the same as reproducing the claim about it.** Both
runs were real. The conclusion drawn from them was wrong.

### What changed

`bin/sense_cuts.py` reads the cut list, checks **every** piece through
`clip_sense.check`, and names the file each objection belongs to. It also
surfaces the per-piece `problems` that `plan_clips.py` was already writing into
`cuts.json` and nothing was reading. Alongside it: mis-heard words are repaired
before any text is read rather than after, and a clip is refused when it opens
on a backward-pointing connective **that does not stand on its own as a
question**, after a real run produced one opening on a dangling `"Or"` whose
referent played two segments later.

That second clause carries the whole rule. `"Or you had a stimulant, right?"` is
a statement wearing a tag question and is refused. `"So what do you actually
want?"` opens with a word from the same list, leaves an interrogative once the
`"So"` is removed, and is allowed. A rule without that distinction kills a good
opener, so `kit_check.py` checks both halves.

---

## What is still true and unfixed

- **`pick_pulls.py` scores are not calibrated against views.** They look like
  predictions and they are rankings. One of the ten signals is now measured. The
  other nine are hand set.
- **A niche profile can honestly support nothing.** The couples profile in
  `specs/` reports that no shape in its sample rests on a thick enough
  observation count, and refuses to recommend. That is the correct answer and it
  means some niches get no steer until there is more research behind them.
- **The research measures a different surface than the one being published to.**
  Profiles are built from YouTube titles, view counts and durations, where
  winning videos run 551 to 1180 seconds. The kit publishes 30 to 60 second
  verticals. Opening shapes appear to survive that gap. Length guidance does not,
  and `median_winning_short` is `None` in every profile shipped here.
- **Nothing here measures retention, thumbnails, posting time, or how large the
  channel already was.** Every profile carries that caveat in its own `caveat`
  field, and it is a direction rather than a prediction.
- **No voice profile ships with this kit.** `specs/voice.sample.json` is labelled
  a test fixture in its own `_what` field and is nobody's real voice. Captions
  drafted against it will not sound like anyone. Build a real one with
  `bin/brand_voice.py` over at least twenty pieces of your own writing, and it
  will refuse to emit a profile if you give it less.
