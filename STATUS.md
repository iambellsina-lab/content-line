# Status, 2026-10-08

**The whole chain now runs end to end with b-roll and the picture really does change, but a
full-frame cutaway covers the captions that are already burned in underneath it, so the second
picture source and the caption layer cannot both be right until `assemble_clip.py` composites them
in one pass.**

Everything below was run just now, on a 180 second trim of `work/longform-test.MOV`, 1080x1920 HEVC
10-bit tagged `arib-std-b67 / bt2020`. Working files are under `work/br8/`, finished clips under
`work/br8/out/br8/`.

## What works, with the evidence

| Step | Command | What it printed |
|---|---|---|
| transcribe | `bin/transcribe.py work/br8/src.MOV` | 27 cues, 374 words, 163s of tape, 21s |
| plan | `bin/plan_clips.py --brief --keep-audio -n 2` | 2 clips, 43.71s and 41.94s, 4 moments dropped by one forbidden phrase |
| name | `bin/name_clip.py --brief --write` | `make-400-000-year-somebody-tell-make` became `make-400k-a-year` |
| gate | `bin/check_dupes.py` | 2 clips, 1 pair, PASS, exit 0 |
| cards | `bin/cards_from_srt.py --cuts` | 55 cards across 2 pieces, times marked source |
| check | `bin/caption_check.py --json` | 57 findings: 30 blockers, 19 to review, 8 notes, 0 cards unmatched |
| repair | `bin/caption_repair.py --findings --out` | 30 blockers down to 10. 4 rewrites, 10 cuts, 10 holds |
| listen | `bin/hear_joins.py --json` | 5 joins, 2 files, 24.73s to listen to, each measured against its plan |
| assemble | `bin/assemble_clip.py --style` | 2 files, 1080x1920, bt709, AAC 48 kHz, both within 0.03s of plan |
| b-roll | `bin/broll.py --cuts --piece A1 --frames` | same 43.733333s, 3 layers, 52.5s |
| preflight | `bin/kit_check.py --offline` | 30 passed, 0 failed, 0 warnings, 1 skipped. READY |

**The repair step earns its place.** It caught two real mishearings nobody had flagged by hand:
`Belia` to `Bella`, and `couch is what you have to sell` to `coach`, which is the difference between
a sofa and a coaching sale in a video about selling coaching.

**I pulled five frames out of the b-roll render and looked at every one.**

- **12.0s, inside the full-frame cutaway.** The picture is entirely the cutaway, a red to navy
  gradient, mean colour `6e2a29` against `b0abaa` at the same second before the pass. The speaker is
  gone and so is the caption `financial goal?` that sat there. `broll.py` named that card, and two
  others, in a warning before it encoded anything.
- **22.0s, inside the picture in picture.** The inset sits top-centre, the speaker is visible below
  it, and the caption `When you start to` is intact in its usual place. A pip does not fight the
  captions.
- **5.0s, inside the lower third.** The band sits across her mouth and covers the top line of the
  two-line card `to make $400,000 a`.
- **8.0s and 30.0s, outside every window.** Unchanged picture, captions in place.

**Measured rather than assumed on the b-roll pass:** output duration identical to the frame
(43.733333s both), audio stream MD5 identical before and after (`92448bcb…`), so `audio: "silent"`
really is a stream copy, and PSNR over ten seconds outside every layer window is 51.8 dB on luma,
which is the cost of the second H.264 generation.

**The refusal paths work.** `bin/broll.py --spec specs/example-broll.json` as it ships names all
three missing assets, encodes nothing and exits 1. `bin/kit_check.py --offline` skips the model URL
check and says so.

## What does not work

1. **A full-frame cutaway hides burned-in captions.** `broll.py` is a separate pass over a finished
   clip, so the captions are already in the picture. It warns and names the cards, which is the
   right behaviour for a tool that cannot fix it, and the fix belongs in `assemble_clip.py`.
2. **The lower third default puts the band over the speaker's face.** `specs/example-broll.json`
   ships `bottom_pct: 0.30`, which in a 1920-tall frame is y 1152 to 1344, and the caption band on
   this render ran y 1203 to 1420. The spec's own comment says 0.30 "lifts it clear of a caption
   band sitting 500 pixels up". On this render it did not. `broll.py`'s coverage warning only fires
   for full-frame layers, so nothing warned.
3. **Render cost is nothing like the figure in `README.md`.** Two clips, 85.7 seconds of finished
   video, 12 minutes 31 seconds of wall clock, which is 8.8x realtime. `README.md` says "about 1.2x
   realtime per clip". One clip alone took 534.4s for 43.7s of output. The b-roll pass, by contrast,
   ran at 1.2x.
4. **Transcription is also slower than the README claims.** whisper's own timing block printed
   19.2 seconds of internal time for 163 seconds of tape, so 8.5x realtime, against the 62.9x in the
   worked example. That gap is inside whisper, not in file reading.
5. **Nobody has heard the joins.** `hear_joins.py` wrote the files and measured them. I cannot play
   audio, so the one step the whole roadmap calls the biggest gap is still waiting on a person with
   ears. The files are `work/br8/joins/a1-joins.m4a` and `a2-joins.m4a`, 25 seconds in total.
6. **`hear_joins.py --only` matches the piece label, not the filename.** `--only A1` works.
   `--only make-400k-a-year`, which is the name `name_clip.py` just gave the clip and the obvious
   thing to type, matched nothing and exported nothing. Its own help says "clips whose name contains
   this".
7. **`hear_joins.py` prints the wrong words at an exact cue boundary.** A cut landing on a cue edge,
   17.06s and 112.80s in this run, shows the later cue on both sides, so the table said "before" and
   "after" were the same line. The audio it exported is cut at the right place; only the words
   printed are wrong.
8. **`caption_repair.py` turned an order into a question.** It rewrote `Stop saying your number` as
   `Stop saying your number?`, reasoning that "her line asks it rather than ordering it". Her line
   was `Stop saying your number is impossible. What number, Bella?`. The question mark came from the
   next sentence.
9. **`caption_repair.py` cut 8 of 24 cards on one piece**, and said so loudly. That removed every
   caption across a nine second run of continuous speech. Fewer blockers, more silence on screen.
10. **`assemble_clip.py` warns about a key `caption_repair.py` writes.** `warning: ignored unknown
    key(s) in the spec: caption_repair`. Harmless, and it reads like an error on a buyer's first run.
11. **`--out-dir` resolves against the cut list, not the shell.** `--out-dir out/br8` put the clips
    in `work/br8/out/br8/`. Not wrong, and not what the command looked like it said.
12. **`name_clip.py` is not wired into `plan_clips.py`.** It has to be run as its own step, which is
    how this run used it.

## The next three, in order

1. **Teach `assemble_clip.py` to take an asset layer**, composited before the caption PNGs, in the
   same generation. It removes problem 1 and problem 2 together, kills a whole H.264 generation, and
   it is the same `overlay` call the renderer already makes 30 times per clip. Until this lands, a
   cutaway and a caption cannot share a second.
2. **Measure the render and then make it cheaper.** 8.8x realtime on a 311 MB 10-bit source is the
   number a buyer meets on their first batch, and the README promises 1.2x. Find out whether the
   cost is the HEVC seek, the 10-bit decode or the layer count, fix `README.md` either way, and
   decide whether an intermediate proxy belongs in the chain.
3. **Close the small holes while they are cheap:** wire `name_clip.py` into `plan_clips.py`, make
   `--only` match the filename, fix the boundary-inclusive cue lookup, drop the question mark rule
   in the repairer, and put a real listen of those five joins in front of a person.

`ROADMAP.md` puts "an hour of real tape and two real speakers" next. That still stands, and it
should come after item 1 above, because an hour of tape at 8.8x realtime is most of a working day.

## One change made outside my own file

`bin/kit_check.py` had four chain scripts missing from its `SCRIPTS` list, so `caption_check.py`,
`caption_repair.py`, `hear_joins.py` and `broll.py` were never even parse checked in preflight. The
owner of that file asked for the names once they settled. I added the four, with a comment saying it
is a parse check and no smoke run is claimed. Re-ran `bin/kit_check.py --offline --quick`:
15 passed, 0 failed. READY.
