# What this kit needs, in order

**Rewritten 2026-10-08, late.** The first version of this file was written in the morning, before
five large scripts landed. It then told readers the kit could not do things it already does, which
on a public repo is the most expensive kind of stale. Every line below was checked against the code
on the date in its row.

**What the kit does today, proven by a clean clone plus one command on 2026-10-08:**
`30 passed, 0 failed, 0 warnings, 1 skipped` and `RESULT: PASS. This computer can make clips.`
A recording goes in, finished captioned vertical clips come out, free and local.

---

## Closed since the morning version

Five of the original nine. Each row says what proves it, not that somebody intended to do it.

| Was | Now | The proof |
|---|---|---|
| **1. Nothing has heard the audio** | **Narrowed, not closed.** `hear_joins.py` exports only the joins, two seconds either side, so a person hears the cuts rather than the clips. It skips boundaries where the tape runs straight through, because those are not cuts | On the real six piece batch: 53 segment boundaries, 20 of them continuous tape, 33 actual cuts. Content proved independently of hearing it, by cutting a source whose loudness rises with its own timestamp and recovering each exported second's origin from its measured volume: 13.50 / 40.30 / 43.69 / 25.43 against a cut list saying 13.5 / 40.5 / 43.5 / 25.5 |
| **4. The checker finds 39 blockers and nobody fixes them** | `caption_repair.py` ships, 1,629 lines. It proposes the three repair moves rather than rewriting silently | Present, parse checked by `kit_check.py`. **The before and after blocker count has not been measured**, so treat the size of the improvement as unknown |
| **5. The auto-generated filenames are unusable** | `name_clip.py` ships, 900 lines | `make-400-000-year-somebody-tell-make` became `make-400k-a-year`. Two clips saying the identical thing came out as `make-400k-a-year` and `400k-a-year`, with no date and no split number |
| **7. `kit_check` does not render with the new assembler** | It renders with it, and checks the result | `[PASS] test render: assemble_clip.py  2 out of order segments and 1 card became 2.00s of 1080x1920 h264`, plus `[PASS] assemble_clip.py plays EDIT order, not tape order` and `[PASS] assemble_clip.py colour fix  source tagged arib-std-b67 / bt2020 came out bt709 / bt709` |
| **8. The model download has never been exercised** | It runs, from this repo's own release, and is checked on size, header and checksum | Downloaded anonymously with no account: 147,964,211 bytes, md5 `4279db3d7b18d9f6e4d5817a16af4f09`, identical to the local copy. **It also used to download nothing at all when no human was at the keyboard**, which was every scripted run. Fixed the same day |

**And the claim this file led with is gone.** The morning version said: "anything with a second
picture source. No b-roll, no graphics over the speaker, no cutaways, no screen recordings, no
animation. It is a single-camera clip engine." `broll.py` ships, 1,068 lines: a full frame cutaway,
a picture in picture with nine anchor positions, and a lower third. It even names the caption cards a
full cutaway would cover, which is how the defect below was found rather than shipped blind.

---

## Still open, in the order they bite

### 1. A full frame cutaway covers the captions underneath it

**This is the one to fix first, because it is the only item here that makes a wrong video rather
than a missing feature.** Recorded in `STATUS.md` from a real 180 second run. Captions are burned
into the picture by ffmpeg during assembly, then b-roll is laid on top, so the cutaway hides them.
Both cannot be right in that order.

`broll.py` warns which cards a cutaway would cover, so nobody is surprised. That is mitigation, not
a fix.

**The fix is a renderer that composites both layers in one pass with real stacking order.** That is
being built as a separate kit on HeyGen's HyperFrames, where layering is CSS `z-index` and the
caption layer simply sits above the b-roll layer. Not finished at the time of writing.

### 2. Nothing has heard the audio where the DECISION is made

The listen step closed the human half. The machine half is open: `plan_clips.py` still chooses every
segment order from text alone. A join that reads cleanly on the page can still sound like a cut, and
a cut can still land mid word because nothing checks where the silences are.

**The fix, cheapest first:** measure silence on the source with ffmpeg and snap every cut point to
the nearest one; flag a join where loudness jumps across it; only then consider scoring moments on
energy rather than words.

### 3. It has only been run on short tape, never on an hour

7 minutes produced 128 candidate moments. An hour produces roughly 1,100, and the pairwise subject
matching is O(n squared), so an hour is nearer 70 times the work rather than 8. **Untested at that
size, and nobody has measured the curve.**

*Pieces: build synthetic transcripts at 7, 15, 30, 60 and 90 minutes, time it, find the quadratic
loop, then window or pre-filter the comparison. Any cap must log what it dropped, because a silent
cap is forbidden in this kit.*

### 4. The planner does not know that two people are two people

Checked today: `plan_clips.py` mentions a speaker only in its prose and in a comment about somebody
correcting themselves. **There is no speaker field and no speaker decision anywhere in it.** It can
produce a clip that spans a question and its answer without noticing. For a two person podcast that
is the normal case.

Diarisation was only ever proved on a two track file built from one voice on both channels, which is
the test that cannot fail.

*Pieces: parse the labels the transcript already carries, keep a speaker per cue, refuse to cross a
speaker boundary unless the exchange stays whole. Then test on two real voices.*

### 5. The scores look like predictions and are not

The thresholds sit at `bin/pick_pulls.py:64` to `:69` and were hand set on one fixture, tuned on one
person's recording. **In its favour, the tool already says so in its own output**, at
`bin/pick_pulls.py:719`: "The strong/usable thresholds are hand-set on one fixture, not calibrated."

*The fix is honesty rather than code: present a rank rather than a score anywhere a reader could
mistake the number for a probability of performing well.*

### 6. Five shipped tools reach a buyer with no proof they run

`kit_check.py` parse checks `caption_check.py`, `caption_repair.py`, `hear_joins.py` and `broll.py`,
and says out loud that a parse check is not a smoke run. It does not mention `add_audio.py` at all.
So about 5,000 lines of tooling arrive with nothing demonstrating it works on the recipient's
machine.

*Pieces: one smoke run each inside `kit_check.py`, on the fixtures that already ship.*

### 7. `LONG-FORM-INTAKE.md` still has no renderer section

Confirmed today: no renderer heading in the file. Two agents were writing the same folder and one
stopped rather than collide. The gap is real and it is a doc edit.

---

## Reachable, and not started

**Automatic b-roll suggestions.** The transcript is already timestamped and scored. A mention of "a
gym membership" is a cue for an asset at that second. The planner could emit the cue list even
without supplying the asset.

**Motion graphics.** Captions are static PNGs drawn with Pillow. Animating them inside this kit
means rendering frame sequences, which Pillow can do, and the design work is the real cost. **The
HyperFrames kit makes this mostly moot**, because there an animated caption is HTML and GSAP, and
the renderer seeks every frame in headless Chrome. Start with two moves, a word that snaps on and a
line that wipes, and stop there.

**Animated metaphors** are illustration work. No script produces them. This kit can hold and place
them; somebody has to make them.

**Shallow depth of field and the office look** are camera and room, not edit.

---

## The order to build in

1. **The cutaway and caption collision.** The only open item that ships a wrong video.
2. **Snap cuts to silence.** Cheap, mechanical, and it fixes cuts landing mid word.
3. **A smoke run for the five untested tools.** Unglamorous, and it is where a first run fails.
4. **Speakers**, if a podcast is actually on the list. Skip it if not.
5. **An hour of real tape.** Find out what breaks before a buyer does.
6. **The doc fixes**, items 5 and 7 above. An afternoon, and they stop the kit misdescribing itself.

**The interface with a tab to upload and a library of edits sits on top of all of this and should be
built last.** Every edit is already a JSON cut list rather than a baked video, which is what makes
that interface possible: opening an edit means reading a file, changing one means editing a line and
re-rendering. That property is already there and it is the thing to protect.
