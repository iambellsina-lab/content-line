# Long form intake: one recording in, short clips out

The rest of this kit assumes you already know which stretch of footage you want. This part is for
when you do not: an hour of podcast, a 26 minute single take, a recorded webinar. You have the tape
and no idea where the clips are.

**Answer `BEFORE-YOU-CUT.md` first.** The three questions are not paperwork: the planner reads your
answers and applies them, and skipping them is what the whole method was rebuilt to stop.

Then six commands, in order. All six are free and run on your own machine.

```
python3 bin/transcribe.py    recording.mov                       # tape -> transcript
python3 bin/plan_clips.py    recording.srt -n 8 \
                             --brief specs/mybrief.json \
                             --out cuts.json                     # transcript -> cut lists
python3 bin/check_dupes.py   cuts.json                           # the gate, before any encode
python3 bin/cards_from_srt.py recording.srt --cuts cuts.json     # cut lists -> caption cards
python3 bin/caption_check.py cuts.json --transcript recording.srt  # read every card cold
python3 bin/assemble_clip.py cuts.json                           # cut lists -> finished clips
```

`bin/pick_pulls.py` is still there and still useful: it finds the best CONTIGUOUS stretch, which is
the right answer when somebody makes a point once and finishes it. `LONGFORM.md` is the two-speaker
case.

---

## 1. transcribe.py

Pulls the audio out with ffmpeg, runs it through whisper.cpp, and writes three files:

| File | What reads it |
|---|---|
| `NAME.srt` | every other script in this kit |
| `NAME.cues.json` | anything that prefers JSON |
| `NAME.txt` | a person, planning cuts. Timecode, absolute seconds, and the silences marked |

The silences in that third file are the part to read. A gap longer than 1.5 seconds is where a
thought ended, and those are the only honest places to start and finish a clip.

**Measured on an Apple M4, 2026-10-08:** 60 seconds of a real recording took 2 seconds, about 30x
realtime. An hour of podcast is therefore about two minutes of transcription, once, at no charge.

**It downloads its own model and tells you the size first.** About 148 MB, one time. Run without
`--download` and it refuses and prints the URL, so nothing large arrives without being asked for.
Nothing in this kit points at a model on anybody else's machine.

### The punctuation trap, and why there is a default prompt

This was measured on the same file twice. Transcribing from 109 seconds into a recording with no
initial prompt came back with no punctuation and no capitals at all:

> stop calling your income goal a vision what even oh stop calling your income

The same audio, same model, with a short punctuated initial prompt:

> Stop calling your income goal a vision. A vision is simply something that is imaginary.

Whisper writes in the style of whatever context it has, and starting mid recording gives it none.
Every script after this one needs sentence punctuation: without it `pick_pulls.py` falls back to
guessing sentence edges from pauses, and says so in its own caveats.

So a neutral punctuated prompt goes in by default. It names no subject, so it cannot put words in
anybody's mouth. `--no-prompt` turns it off. If a transcript comes back unpunctuated anyway,
`transcribe.py` prints a warning rather than letting it pass quietly.

Cues are also capped at 90 characters and split on a word boundary. Without that cap whisper
returns 30 second paragraphs, and a start time inside a 30 second cue is interpolated by character
count, which can be seconds out.

---

## 2. plan_clips.py

**People do not speak in the order a clip needs.** They circle. The sharpest version of a point
arrives twenty minutes after the story that proves it, and the line that should open the clip gets
said near the end, once they finally know what they meant.

The first real batch through this kit was cut in spoken order. All six videos were incoherent and
all six were rebuilt with the segments reordered. So the order is imposed here, not filtered.

How it decides:

1. **Moments.** Short runs of whole sentences that start cleanly and end on a finished sentence.
   Each one is scored by `pick_pulls.py`'s nine signals, imported rather than rewritten.
2. **Subject.** Moments are linked by the words they share, weighted so a rare word counts far more
   than a common one. Two guards, both of which caught a real defect in testing:
   - **One word in common is a coincidence, not a subject.** Six sentences that all open "Stop ..."
     look related and are not. A link needs at least two shared words, and no single word may carry
     more than 60 percent of the match.
   - **Two takes of one line are one moment.** A speaker says the hook three times and the third is
     the keeper. Containment catches the short take sitting inside the long one, which plain cosine
     similarity misses because the longer take carries extra words.
3. **Order.** The opener first, wherever it was said. A closing line last, wherever it was said.
   Everything between stays in tape order, because that is where the speaker's own reasoning lives.
4. **Problems.** Each clip carries its own list. A body segment opening on "it" or "that" has lost
   whatever the pronoun pointed at. A segment opening on "And" or "Because" was joined to tape that
   no longer plays before it. Those get named, not silently shipped.

**Measured on a real 26 minute single take:** 351 cues, 2,705 words, 250 sentences, 554 moments
built, 6 clips planned in 0.11 seconds.

One of those six came back as the opener at 01:49, then 01:52, then 02:09, then a close at 02:12.
That is the same order a person arrived at by hand after a full rebuild, including putting "It will
always be imaginary, it will always be a vision" in front of "If your income goal is a vision".

**It has never heard the audio.** Every join is a guess about meaning made from text. The joins
that read cleanly can still sound like joins. Listen to all of them before rendering six.

---

## 3. check_dupes.py

Six finished reels came out of one recording. Two pairs shared more than fifty seconds of the same
tape each, and two of them ended on the identical closing line. Nobody saw it until the files were
rendered, and by then the only fix was to rebuild.

Finding it from the cut lists is arithmetic. **Run on the real intermediate cut list from that
batch, 2026-10-08, it reported:**

| Pair | Shared | Note |
|---|---|---|
| P6 and P5 | 56.32 s | 38 percent of one, 46 percent of the other, 4 separate ranges |
| P2 and P1 | 52.84 s | both clips end inside shared tape |
| P6 and P1 | 7.20 s | one range |

Run on the finished cut list from the same batch, after the rebuild: no pair over one second.

It exits 1 when it finds an overlap, so a build script stops before spending the encode. Overlap is
not always wrong: a callback across two clips is a choice. The point is that it should be a choice,
made with the number in front of you.

It reads three cut list shapes, because this kit has produced all three, and it checks its own
reading: if a file's stated duration disagrees with the arithmetic, it says so instead of reporting
overlap numbers it cannot stand behind.

---

## What this does not do

- **It does not hear anything.** Energy lives in the waveform: loudness after a pause, pace, a
  laugh, a voice dropping. None of that is in a transcript. Where the audio disagrees with the
  plan, the audio wins.
- **It does not write.** `the_argument` in a cut list is a mechanical stitch of first sentences.
  The pinned hook card is the transcript's own words, trimmed. Both are a starting point for a
  person, and both are labelled as such in the file.
- **It does not publish.** Nothing here posts, schedules or uploads.

## Running it on a podcast

An hour needs looser bounds than a 26 minute take, because there is more material and the subjects
are further apart:

```
python3 bin/transcribe.py episode.mov --out-dir work/ --diarize --max-len 40
python3 bin/plan_clips.py work/episode.srt -n 12 --brief specs/mybrief.json \
        --source work/episode.mov --out-dir out/ep12 --keep-audio --out work/ep12-cuts.json
python3 bin/check_dupes.py work/ep12-cuts.json
```

`--diarize` is for two people on separate tracks and `LONGFORM.md` says what it does and does not
measure. Put `"length": {"min": 60, "max": 180}` in the brief rather than on the command line, so
the answer sits with the work.

`--keep-audio` is the one flag to think about. It tells the renderer to leave the sound exactly as
recorded, with no loudness normalisation. Use it for audio that was already processed, which is
most podcast audio and anything mixed in a phone's own audio editor.
