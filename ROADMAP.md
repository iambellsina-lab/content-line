# What this kit needs, in order

**Written 2026-10-08.** Two questions answered here: what makes the kit pristine, and what it takes to
edit like the video Bella sent. Nothing below is a guess about effort; each item names its pieces.

**What the kit does today, proven end to end on 2026-10-08:** a recording goes in, finished captioned
vertical clips come out, free and local. 7 minutes transcribed in 7 seconds. Four clips planned, checked
for duplication, captioned, caption-checked and rendered.

**What it cannot do today:** anything with a second picture source. No b-roll, no graphics over the
speaker, no cutaways, no screen recordings, no animation. It is a single-camera clip engine.

---

## Part 1. The nine things between here and pristine

Ordered by what breaks first in a buyer's hands. Every one of these was named by the agent that built the
thing, not found later by a reviewer.

### 1. Nothing has heard the audio. This is the biggest one.

Every clip boundary and every join is a guess about meaning made from a text transcript. A join that reads
cleanly on the page can still sound like a cut. Nobody has listened to a single join in anything this kit
has produced.

**The fix is not more cleverness, it is a listen step.** The planner should export its joins as a short
audio file, two seconds either side of each cut, so a human hears only the joins rather than the whole
clip. Ten joins is twenty seconds of listening.

*Pieces: a join-export script, and a line in the workflow that says do not render until you have heard
them.*

### 2. It has only been run on 7 minutes, never on an hour

7 minutes produced 128 candidate moments. An hour would produce roughly 1,100, and the pairwise subject
matching is O(n squared), so that is not 8 times the work, it is nearer 70. Untested at that size.

*Pieces: run it on a real hour, measure, then fix whatever falls over.*

### 3. The planner does not know speakers exist

It scores moments as if one person is talking. It can produce a clip that spans a question and its answer
without noticing it has done so. For a two-person podcast that is not an edge case, it is the normal case.

Diarisation was proved on a two-track file built from one voice on both channels, which is the test that
cannot fail. It has never run on two actual people.

*Pieces: speaker awareness in the planner, then a real two-person recording to test on.*

### 4. The caption checker found 39 blockers and nobody fixed them

That is the checker working. But the kit currently has no repair step, so a buyer gets 39 problems and no
path. The repair logic exists; it was done by hand on this batch over three rounds.

*Pieces: turn the three repair moves (add the governing clause, rewrite inside the ceiling, cut the card)
into a script that proposes fixes rather than only finding faults.*

### 5. The auto-generated filenames are unusable

A real run produced `make-400-000-year-somebody-tell-make.mp4`.

*Pieces: one function. Small, and it is the first thing a buyer sees.*

### 6. The scores are not calibrated

`plan_clips` inherits `pick_pulls`' scoring, whose own docstring says the thresholds are hand-set on one
fixture and are not a probability of performing well. The constants were tuned on one person's recording.

**Say so in the product.** A score that looks like a prediction and is not is worse than no score.

### 7. `kit_check` does not render with the new assembler

It parses the file but never runs it, so a broken ffmpeg build passes preflight and fails at the first
real render.

### 8. The model download has never been exercised

The refusal path works: it prints the size and the URL and exits without fetching. The actual 148 MB
download has never run, because every test pointed at a model that already existed.

### 9. `LONG-FORM-INTAKE.md` has no section for the renderer

Two agents were writing the same folder and one stopped rather than collide. The gap is real.

---

## Part 2. Editing like the video she sent

The reference uses: text overlays and motion graphics synced to narration, close-ups of handwritten notes,
document mock-ups, screen recordings, live event footage, animated metaphors, and fast jump cuts between
all of it.

**Here is the honest shape of that gap.** The kit composites caption PNGs over video at a timecode. **A
cutaway is the same mechanism with a different asset.** That is the good news and it is why this is
reachable rather than a rewrite.

### Reachable now, because the machinery already exists

**B-roll and cutaways.** Insert or overlay a second video or image for a time range. The renderer already
layers PNGs at timecodes; this is the same call with a video input. Full-frame cutaway, picture in
picture, or a lower-third card.
*Pieces: an asset list in the spec, a layer type in the renderer, a rule for what the audio does under a
cutaway.*

**Document and screen-recording inserts.** The same feature. The difference is only the asset.

**Jump cuts between sources.** Already there. `assemble_clip` concatenates segments in edit order; it just
has one source today.

**Automatic b-roll suggestions.** The transcript is already timestamped and scored. When she says "a gym
membership", that is a cue for an asset at that second. The planner can emit the cue list even when it
cannot supply the asset.
*Pieces: a keyword-to-asset map, and a cue list in the plan output.*

### Harder, and it should be said plainly

**Motion graphics.** Captions are rendered as static PNGs with Pillow. Animating means rendering a frame
sequence, which Pillow can do, but the design work is the real cost: a bad motion graphic is worse than
none. Start with two moves, a word that snaps on and a line that wipes, and stop there.

**Animated metaphors**, the dumbbell and the shredder in that video, are illustration and animation work.
**This is not an engineering gap, it is a design one**, and no script produces them. The kit can hold and
place them. Somebody has to make them.

**Shallow depth of field and the office look** are camera and room, not edit.

### What that video actually is

It is a multi-track edit with an asset library behind it. The kit is a clip engine. **Adding a second
picture source is the whole difference**, and it is one feature, not a rebuild.

---

## Part 3. The order to build in

1. **The listen step** (Part 1, item 1). Until joins are heard, everything else is polish on an unverified
   edit.
2. **Filenames and the caption repair step** (items 5 and 4). Both small, both are the buyer's first
   impression.
3. **B-roll and cutaways** (Part 2). The single biggest jump in what the output looks like, and the
   machinery is already there.
4. **An hour of real tape, and two real speakers** (items 2 and 3). Find out what breaks before a buyer
   does.
5. **Preflight and the download path** (items 7 and 8). Unglamorous, and it is where a first run fails.
6. **Motion, two moves only** (Part 2). Last, because it is the easiest thing to do badly.

**The interface Bella described, a tab to upload and a library of edits she can open and change, sits on
top of all of this and should be built last.** Every edit is already a JSON cut list rather than a baked
video, which is what makes that interface possible at all: opening an edit means reading a file, and
changing one means editing a line and re-rendering. That property is already there and it is the thing to
protect.
