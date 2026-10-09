# The podcast workflow

**An hour of two people talking, down to clips.** This page is the two-speaker case specifically.
`README.md` is the chain, `LONG-FORM-INTAKE.md` is what each planning tool measures, and
`BEFORE-YOU-CUT.md` is the three questions you answer before any of it.

An hour of tape costs about two minutes of transcription and nothing in money. The expensive part is
the hour of somebody's attention it still takes at the end, and most of this page is about spending
that hour in the right place.

---

## The short version

```
# 0. answer the three questions into specs/mybrief.json      see BEFORE-YOU-CUT.md
# 1. transcribe, with the speaker labels if the tracks are separate
.venv/bin/python bin/transcribe.py work/ep12.mov --out-dir work/ --diarize --max-len 40

# 2. plan. An hour wants a looser band and more clips than a single take
.venv/bin/python bin/plan_clips.py work/ep12.srt -n 12 --brief specs/mybrief.json \
    --source work/ep12.mov --out-dir out/ep12 --brand specs/mystyle.json \
    --keep-audio --out work/ep12-cuts.json --print

# 3. the gate
.venv/bin/python bin/check_dupes.py work/ep12-cuts.json

# 4. cards for every segment of every piece
.venv/bin/python bin/cards_from_srt.py work/ep12.srt --cuts work/ep12-cuts.json

# 5. read them cold
.venv/bin/python bin/caption_check.py work/ep12-cuts.json --transcript work/ep12.srt

# 6. arithmetic, then pixels
.venv/bin/python bin/assemble_clip.py work/ep12-cuts.json --dry-run
.venv/bin/python bin/assemble_clip.py work/ep12-cuts.json --style specs/mystyle.json
```

**`--keep-audio` is on by default for podcasts in that brief**, because most podcast audio was
already processed somewhere else and the kit's own -14 LUFS pass would flatten it.

---

## What to do about two speakers

### If each person was recorded to their own track

This is how most remote podcasts are captured, and it is the only case the kit can label
automatically.

```
.venv/bin/python bin/transcribe.py work/ep12.mov --diarize --max-len 40
```

`--diarize` keeps both stereo channels instead of downmixing to mono, and whisper.cpp labels each
cue by which side is louder. `transcribe.py` rewrites the labels from whisper's own
`(speaker 0)` into `SPEAKER_0:`, which every other script in this kit already reads. Without that
rewrite the label gets cut into a caption card and burned into the video, which was the behaviour
before 2026-10-08.

**What this buys you, measured on this machine on 2026-10-08:** a speaker change becomes a clean
place to start a clip. `bin/pick_pulls.py` treats a turn as a sentence boundary, so a moment can
open on somebody starting to speak, and `bin/cards_from_srt.py` never carries one caption card
across a change of voice.

**What it does not buy you: an accurate turn boundary.** The label is per cue, so a cue that
straddles a turn gets one label and is wrong for part of it. On a constructed two-track file whose
turn changed at 12.0 seconds, the default 90 character cue cap put the change at 6.78 seconds and
`--max-len 40` put it at 8.83 seconds. Neither is the real boundary. **Use `--max-len 40` for
podcasts**, and open the waveform before trusting a turn to the second.

### If both people share one microphone

The kit cannot tell them apart, and neither can the model it ships with. `--diarize` reads which
stereo side is louder; one room mic holds no such information, and `transcribe.py` refuses rather
than producing labels that mean nothing:

```
transcribe: --diarize needs two audio channels, and ep12.mov has 1.
```

Three honest options, in the order they cost:

| | What | Cost |
|---|---|---|
| **1** | **Cut single-voice clips only.** Pick moments where the host or the guest runs for 20 seconds alone, and cut those. Most podcast clips that travel are one person finishing a thought anyway | nothing |
| **2** | **Label the turns by hand** in the `.srt`, as `SPEAKER_0:` at the front of a cue. The whole chain then behaves as if the tracks were separate | roughly ten minutes an hour, reading the reading copy |
| **3** | **Re-record to separate tracks** next time. Every remote recording tool does this and most of them default to it | one setting |

Option 1 is the right answer more often than people expect. A clip that cuts between two voices
needs the other half of the exchange to make sense, and that is usually a longer clip than the one
you wanted.

---

## Where the clip boundaries come from

Four sources, in the order the tools use them.

**1. A finished sentence.** A moment never starts or ends mid-sentence. `plan_clips.py` builds every
moment out of whole sentences with a clean start and a finished end. This is why the punctuation
matters so much, and why `transcribe.py` sends a punctuated initial prompt by default: whisper
writes in the style of whatever context it has, and starting an hour of tape with none comes back
without capitals or full stops at all.

**2. A silence.** Read `work/ep12.txt`, the reading copy, not the `.srt`. It marks every gap longer
than 1.5 seconds. **A gap longer than 1.5 seconds is where a thought ended**, and those are the only
honest places to open and close a clip. For an hour of two people, raise it: `--gap-mark 2.5` marks
only the real landings and leaves out the breath between sentences.

**3. A speaker turn**, where you have the labels. See above.

**4. The subject, which is what makes a clip out of scattered moments.** `plan_clips.py` links
moments by the words they share, weighted so a rare word counts far more than a common one. Two
guards, both of which caught a real defect in testing: a link needs at least two shared words and no
single word may carry more than 60 percent of the match, because six sentences that all open "Stop"
look related and are not; and containment catches two takes of the same line, because a speaker says
the hook three times and the third is the keeper.

**For an hour, loosen the bounds.** There is more material and the subjects sit further apart:

```
--min 60 --max 180 --segments-max 8 --moment-max 30
```

A twelve clip plan from an hour is a reasonable ask. Expect fewer back: the planner spends each
moment once, so two clips in one run never share tape, and it stops when it runs out of moments that
link.

---

## What a human still has to decide

Nothing on this page has heard the audio. This is the part no tool here replaces.

**1. Listen to every join.** A join that reads cleanly in text can still sound like a join: a breath
cut in half, two different room tones, a sentence that lands on a rising pitch and is answered by
one that starts on a falling one. Energy lives in the waveform and none of it is in a transcript.
Where the audio disagrees with the plan, the audio wins.

**2. Decide whether the argument holds.** `the_argument` in a cut list is a mechanical stitch of
each segment's first sentence, and the file says so in its own caveats. It is a starting point for a
person. If you cannot say in one sentence what the clip argues, the clip does not argue anything.

**3. Read every caption card cold.** `caption_check.py` compares strings and flags the shapes that
invert a speaker: a dropped negation, a dropped condition, a stranded "and", an unattributed line, a
known mishearing. It is explicit that it is not a gate. It cannot see a card that should not be
there at all, a line that needed a card and has none, a word added that was never said, or a subject
dropped with no negation involved. Half the defects in the batch it was built from were of exactly
those kinds. Watch every card muted, once.

**4. Decide what a guest agreed to.** A guest agreed to an episode. They did not agree to a
nineteen second clip of the part where they were being candid. That judgment is yours and it belongs
in the `forbidden` list in your brief, before anything is planned.

**5. Rename the files.** The planner's filenames are stitched from the opener's own words and they
are ugly. A real run on 2026-10-08 produced `make-400-000-year-somebody-tell-make.mp4`.

**6. Check the clip's own opening two seconds.** The planner scores an opener on nine signals from
`pick_pulls.py`, and it is right often enough to be useful. It cannot tell you whether a face
arrives mid-blink, whether the first word is swallowed, or whether the hook card and the spoken line
say the same thing twice. Those are the three things that kill a clip in the first two seconds and
all three are visible in one look.

---

## Two numbers for planning a session

**Transcription, measured on an Apple M4 on 2026-10-08:** 7 minutes of real tape took 7 seconds at
60.4x realtime. An hour is therefore about a minute, once, at no charge.

**Rendering, measured in the same session:** 143.5 seconds of finished video across four clips took
4 minutes 52 seconds of wall clock, about 1.2x realtime per clip, with captions and a colour fix on
every frame. Twelve clips from an hour at 90 seconds each is roughly 20 to 25 minutes of rendering.
Render `--dry-run` first every time: it reads the arithmetic, reports any footage two pieces share,
and encodes nothing.

**One structural warning.** A full render pass can outlive a background window and leave a file with
no `moov` atom, which looks finished and will not open. Always check the rendered duration against
the cut list after a batch rather than trusting that a file exists:

```
ffprobe -v error -show_entries format=duration -of csv=p=0 out/ep12/some-clip.mp4
```
