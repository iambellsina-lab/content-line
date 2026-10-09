---
name: video-cut
description: Make video that holds attention. Covers short-form structure, shot grammar, cutting rhythm, captions, safe zones, loudness and export specs, and the order of operations for this kit's free local pipeline. Fires on "make a reel", "edit this video", "cut this down", "make a short", "podcast clip", "walkthrough", "b-roll", "captions", "thumbnail", "export", "what aspect ratio", "why does this feel flat". This is the craft reference the other skills lean on.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Video cut


**The edit is not where you assemble footage. The edit is where you decide what the viewer is allowed to not see.**

Most bad video is not badly shot. It is too long, cut on the wrong frames, and mixed too quietly.

---

## Part 1: structure, which decides everything else

### Short form, 15 to 60 seconds

Frame zero is the thumbnail. It is also the hook. There is no separate hook; the first frame either stops the scroll or the rest of the file never plays.

| Beat | Time | Job |
|---|---|---|
| **Frame 0** | 0.0s | The still that stops the thumb. Most interesting frame in the whole file. Never a logo, never a title card, never a face mid-blink. |
| **Hook** | 0.0 to 1.5s | One sentence or one image that creates a question. Spoken, not written. |
| **Promise** | 1.5 to 4s | What the viewer gets by staying. Concrete. "Three rooms, one camera move each." |
| **The 7-second dip** | 6 to 8s | Retention always falls here. Put the pattern interrupt exactly here: a hard cut to a different space, a sound change, or a one-second hold on stillness. |
| **Payoff beats** | 5 to 45s | One idea per beat. Each beat changes information. |
| **The turn** | last 20% | The thing they did not expect. Without it the video is a list and nobody shares a list. |
| **Close** | last 3s | One line. No "like and subscribe". Either a question or a hard stop. |

**The loop trick:** if the last frame matches the first frame, the replay is invisible and watch time doubles on platforms that auto-loop. Build for this deliberately on anything under 20 seconds.

### Long form and podcast clips

Pull clips where **the speaker changes energy**, not where the topic is most important. Energy change is what is watchable. The transcript tells you topic; the waveform tells you energy. Look for the loud bit after a pause.

A good pull is 35 to 75 seconds and contains exactly one complete thought with a beginning. Never start a clip mid-sentence to "get to the good part". Start one sentence earlier than feels right.

### Tour and walkthrough footage, which has its own grammar

Footage of a space (a venue, a studio, a home, an office) is the opposite of short-form grammar.

- **One camera move per shot.** Never a pan and a push in the same shot.
- **Slow and steady.** The move should be barely perceptible for the first half second. No ease-out at the end; let it stop flat or keep going past the cut.
- **Three to five seconds per shot.** Faster reads as a slideshow. Slower reads as a screensaver.
- **Enter every room the way a person would.** Through the doorway, not from the ceiling corner.
- **End on the view, the light, or the thing nobody else photographs.** Not the obvious room.
- **No camera lock.** A locked-off camera on an interior reads as a still photo that someone made move. The whole point is motion with intent.

---

## Part 2: cutting

### Where the cut goes

- **Cut on motion.** A door swinging, a hand leaving frame, a foot landing, a head turn. The eye is already moving and the cut disappears. Cutting on a still frame feels like a slideshow because it is one.
- **Cut before the action completes.** The viewer finishes it in their head and the pace lifts for free.
- **J-cut everything.** Bring the next shot's audio in four to eight frames before its picture. This one habit removes most of the amateur feel from any edit.
- **L-cut on dialogue.** Hold the previous speaker's audio over the new shot when the reaction matters more than the mouth.

### Rhythm

**Shot lengths must vary by at least 2x inside any sequence.** A 2-second shot next to a 5-second shot. If every shot is four seconds, the viewer's attention settles into the rhythm and then drifts off it. Lumpy holds attention.

**Per 30 seconds: one shot holds for 4+ seconds.** Everything cannot be fast or nothing is.

**One push-in per 30 seconds, maximum.** Push-in on everything is the single loudest AI-video tell. Everything else holds, pans, tracks, or is locked with motion inside the frame.

### Music

- **Music enters on a cut, never on a fade.** A fade-in under the first shot is the sound of a template.
- **Find the downbeat and put the first hard cut on it.** After that you can drift; the viewer has been told there is a grid.
- Duck music under voice by 12 to 18 dB. Not 6, which sounds like a mistake, and not muted, which sounds empty.

---

## Part 3: captions, safe zones and the specs

### Captions

- **Burned in.** Platform auto-captions are ugly and are off for many viewers.
- **Two to four words per card.** Not full sentences. The eye reads a card in one fixation.
- **Cut in on the word. No fade.** A fading caption is always 100ms late and it reads as lag.
- One font, one weight, one colour, plus a single accent colour for the one word per clip that carries the point.
- Outline or a soft shadow, always. White text on a white wall is the most common unforced error in short form.

### Safe zones

Canvas is **1080 x 1920** for vertical.

Platform UI covers different edges, and it changes. The rule that survives every platform:

> **Keep all text and anything load-bearing inside the centre 1080 x 1080 square.**

That means roughly 420px of dead space top and bottom. It looks too conservative in the editor and it is exactly right on a phone. For anything that must sit lower, stay above 500px from the bottom and 200px in from the right, where the action rail lives.

### Export

| Setting | Value |
|---|---|
| Container / codec | MP4, H.264 (High profile) |
| Resolution | 1080 x 1920 vertical, 1920 x 1080 horizontal, 1080 x 1350 for feed |
| Frame rate | 30fps delivery. Shoot 60 when you want clean speed ramps, conform to 30. |
| Bitrate | 10 to 15 Mbps for 1080p. Above 20 is wasted; platforms re-encode. |
| Audio | AAC, 48kHz, stereo, 192 kbps |
| **Loudness** | **-14 LUFS integrated, true peak -1.0 dBTP** |

**Loudness is the most commonly skipped step and it is the most audible.** A video mixed at -24 LUFS plays quiet against everything else in the feed and gets swiped. Normalise before export, every time.

---

## Part 4: the pipeline in this kit

Everything here is free and runs on the user's own machine. No account is needed to render. The
mechanics live in two other skills, so this part is the map, not the manual.

| Job | Skill and tool |
|---|---|
| Words to a captioned vertical video | `clip-factory`, `bin/make_clip.py` |
| A recording cut down to captioned pulls | `drive-intake`, using `bin/pick_pulls.py`, `bin/cards_from_srt.py` and `bin/caption_video.py` |
| Deciding what to post and what to test | `social-engine` |

### Order of operations

1. Transcript (local `whisper-cli`, free). Read it before watching the footage. It is ten times
   faster for finding pulls. **Transcript first, pick pulls from text, then watch only those
   sections.** Do not scrub an hour of footage.
2. Choose pulls from the text, then confirm the energy in the audio.
3. Rough cut to structure, no polish
4. **Watch it once with sound off.** If it holds with no audio, the picture edit is right.
5. **Listen once with the screen off.** If it holds, the audio edit is right. Claude cannot do this
   step. It must say so and hand the timecodes of the loudest and quietest second to the user.
6. Captions, burned in
7. Music, entering on a cut
8. Loudness normalise to -14 LUFS
9. Export
10. Read the words of the finished clip once more. Cut anything that sounds like a template

Optional paid tools exist for this work (hosted editors, voice generators, template design tools).
This kit does not need any of them. If the user already pays for one and wants to use it, that is
their choice, and nothing in this kit depends on it.

---

## Part 5: the checks before anything ships

- [ ] Frame 0 would stop a scroll on its own
- [ ] Hook lands inside 1.5 seconds
- [ ] Something changes at the 7-second mark
- [ ] Shot lengths vary by 2x or more
- [ ] No more than one push-in per 30 seconds
- [ ] At least one shot holds for 4 seconds
- [ ] Every cut changes information
- [ ] Music enters on a cut
- [ ] Captions inside the centre 1080 square, cutting in, not fading
- [ ] -14 LUFS, -1 dBTP
- [ ] Watched once silent, listened to once blind
- [ ] The words read aloud once and sound like the speaker, not a template

---

## The one-line version

**Cut it until it hurts, then cut the first three seconds.**
