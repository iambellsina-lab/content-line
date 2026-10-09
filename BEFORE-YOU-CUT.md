# Before you cut: the three questions

**Answer these before a single clip is planned.** Ten minutes here, once per recording. On the first
real batch through this method, every expensive correction traced back to one of the three going
unasked, and the three together cost roughly a third of the whole run.

Copy `specs/example-brief.json` to `specs/mybrief.json`, answer it, and pass it in:

```
.venv/bin/python bin/plan_clips.py work/recording.srt --brief specs/mybrief.json -n 8
```

The planner reads it. The length band and the forbidden list are not advice, they are applied:
forbidden tape and forbidden phrases never reach a moment, and the length band comes from you rather
than from a default. It prints what it read and how many moments it dropped before assembling
anything.

---

## Question 1. In the order they said it, or assembled for the argument?

**Ask the person whose face is in the video, or watch five minutes of the tape yourself.**

| Their answer | `"order"` | The tool |
|---|---|---|
| They circle. The point arrives long after the story that proves it | `"edit"` | `bin/plan_clips.py` |
| They make a point once and finish it | `"spoken"` | `bin/pick_pulls.py`, then `bin/assemble_clip.py` |

**What it cost to skip.** The first cut list preferred one continuous run per piece, which is the
`spoken` answer, nobody having asked. The speaker's verdict: *"not every video is telling a complete
story."* That whole planning run was thrown away and so was the first render of seven videos.

A brief that says `"spoken"` makes `plan_clips.py` stop and point at `pick_pulls.py` rather than
quietly assembling something it was told not to.

**The tell, if you cannot ask.** Open the transcript's reading copy, the `.txt` that
`transcribe.py` writes, and look at the marked silences. If the same subject comes back after two
or three gaps, they circle.

---

## Question 2. How long should these be?

**Ask the same person. Not the niche research.**

A 30 to 50 second band taken from someone else's account cut the most concrete image in a 26 minute
recording, a mug chosen in the morning for coffee, and labelled it a removal for length. The
speaker's actual position: *"Even if our videos are over the suggested time, that's okay."* The
rebuilt pieces ran 62 to 155 seconds.

```json
"length": {"min": 45, "max": 150}
```

Leave either one out to keep the planner's own default, which is 45 to 150. A podcast wants a looser
band than a single take, usually 60 to 180, because there is more material and the subjects sit
further apart.

---

## Question 3. What must never appear?

**This is the one people skip, and it is the only one of the three that cannot be fixed after
rendering.** Six forbidden stretches were once found by a sweep AFTER the cuts existed, including a
remark about a body, a named relative, and material the speaker says on camera is *"not a very PC
for me to say online."* Found before planning they cost nothing. Found late they forced two pieces
to be re-cut.

Ask for all five:

- anything about a named person who has not agreed to be in it
- anything about a body, theirs or anybody else's
- anything they would not want quoted back at them in a comment section
- anything under an agreement with a client, an employer or a platform
- anything they flagged on camera at the time, which is usually the clearest signal in the tape

Two shapes, mix them freely:

```json
"forbidden": [
  {"start": 612.0, "end": 661.5, "why": "the stretch about her mother, who did not agree to be in it"},
  {"phrase": "my accountant said", "why": "a claim about money that cannot be stood behind"}
]
```

A **range** is seconds of the recording, and any moment touching it is dropped. A **phrase** is
matched case-insensitively anywhere in a moment's text. Both are reported before assembly:

```
plan_clips: brief specs/mybrief.json: order edit, length 30 to 120s,
            1 forbidden range(s) and 1 phrase(s). 30 moment(s) dropped before assembly.
```

**How to find the ranges fast.** Read `work/NAME.txt`, the reading copy, not the `.srt`. It carries
timecode, absolute seconds and the silences marked, so a forbidden stretch is two numbers you can
read straight off the page.

---

## The fourth thing, which is not a question

**Put the caption rule in the brief, not in the third round.** Four rounds went into captions on
that first batch, about 2.1 million tokens, and nearly every defect was one failure repeated: a card
that inverts the speaker when read alone with the sound off.

> Her line: *"There is not one thing that I want to be tamed from."*
> The card: **"i want to be tamed from"**

So the rule, which belongs in the first caption brief every time:

> **Every card must survive alone, muted, read by a stranger who scrolls past mid-card.** If it
> needs the audio or the previous card to be safe, it is not safe. Where a fragment cannot be made
> whole inside the word ceiling, cut the card and let the audio carry it. Air is always safe. A
> wrong card is not.

Three more, all learned the hard way:

- **Never caption from a transcript without reading it.** Whisper produced "Belia" for a name,
  "couch" for coach, "world piece" for world peace. Caption what was MEANT. Keep your own
  mishearings in a copy of `fixtures/transcription-errors.json` so the checker knows them.
- **Never repeat the pinned hook as a card.** It fired on six of seven pieces.
- **Watch for stranded attributions.** When somebody voices their own brain or their spirit, an
  unattributed card reads as an instruction to the viewer. "please stop growing" is her brain
  talking, not her.

`bin/caption_check.py` fires on all of these mechanically. It is not a gate and says so. It compares
strings; it cannot see a card that should not be there at all, a line that needed a card and has
none, or a word added that was never said. Half the defects in the batch it was built from were of
exactly those kinds.

---

## The order to work in

1. **Answer the three.** Free.
2. **Transcribe.** Local, free.
3. **One planning pass**, with the brief already in hand.
4. **Duplication check** across every pair. Mechanical, cheap, before any render.
5. **One caption pass** with the alone-and-muted rule already in the brief.
6. **`--dry-run`**, then render.

That is one planning run instead of two and one render pass instead of two, and the questions are
free.
