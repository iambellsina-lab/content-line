# The upgrade, in order, with nothing left implicit

**Written 2026-10-15.** This is the working list for turning the kit from a video workshop into the
marketing system described in `THE-GAP.md`. Each item says what done looks like, so work can continue
across sessions without re-deciding anything.

**Rules that bind every item.** Drafts, never live: nothing posts, sends or charges without a human
yes. Every number a tool reports must be traceable to something counted, and a tool with thin data
says so rather than guessing. No em dashes. Never the words deserve, worthy or worth. One file per  <!-- slop-lint: allow -->
tool, shared helpers in `kit_common.py`. Run `python3 bin/kit_check.py` before claiming anything runs.

---

## 1. The sense filter · `bin/clip_sense.py` · DONE 2026-10-15

**The problem.** `caption_check.py` reads the captions and `hear_joins.py` plays the cuts. Both check
craft. Neither asks the only question that matters: does this clip make sense on its own to somebody
who has never heard the rest of the recording, and is there a reason to keep watching?

**Done when** a clip's transcript goes in and a verdict comes out naming specific faults: it opens on
a pronoun with no referent, it answers a question the viewer never heard, it ends mid-argument, it
has no turn, nothing is at stake. Each fault cites the sentence that caused it. **It must be able to
fail a technically perfect clip**, or it is decoration.

## 2. Brand voice from their own posts · `bin/brand_voice.py` · DONE 2026-10-15

**The problem.** `BRAND-INTAKE.md` is a fifteen minute questionnaire. A questionnaire returns what
somebody thinks their voice is. Their posts contain what it actually is.

**Done when** a folder of their existing captions or transcripts produces a voice profile: sentence
length distribution, the words they genuinely over-use against ordinary English, how they open, how
they close, whether they swear, contraction rate, question rate, emoji rate. **Measured, never
adjectives.** It writes `specs/voice-profile.json` and refuses on fewer than 20 samples.

## 3. Publishing · `bin/schedule_post.py` · DONE 2026-10-15

**The problem.** `publish_media.py` gives a file a public URL. Nothing takes the next step, and
`CHOOSING-A-SCHEDULER.md` is a decision document rather than an integration.

**Built.** Metricool, which is what `CHOOSING-A-SCHEDULER.md` already recommends. A draft is the
default and `--live` is the override. It prints the exact payload and sends nothing until `--send`,
and credentials come from the environment rather than from any file in this repo.

**The shape was corrected mid-build.** The first version refused to publish at all, with no flag.
Bella: *"it should only be a conversation not a ahrd gaurd."* A rule a person cannot override stops
being a safeguard the first time it blocks something they actually asked for, and the same mistake
was made once before on this account with a hook that blocked her own request twice. Structural
faults still refuse, because an empty caption and a time with no timezone are bugs rather than
decisions.

## 4. Generation · `bin/draft_content.py`

**The problem.** `make_clip.py` renders a spec that a human wrote.

**Done when** a voice profile from item 2 plus a niche profile from `niche_calibrate.py` produces
caption and hook drafts in that person's measured voice, shaped by what the niche rewards. Drafts for
a human to approve. It must show which voice and niche findings drove each choice.

## 5. Email · `bin/email_sequence.py` · DONE 2026-10-15

**The problem.** Nothing exists.

**Done when** a product or offer plus a voice profile produces a drafted sequence as plain files, with
subject lines, send-day spacing and a stated purpose per email. **It writes files and never touches a
sending platform.** Connecting it to one is a separate, later, explicit decision.

## 6. Integrations · `INTEGRATIONS.md` · DONE 2026-10-15

**The problem.** Claude, Drive, social accounts and GoHighLevel are named in the vision and absent
from the repo.

**Done when** `INTEGRATIONS.md` says exactly what a buyer connects, in what order, what each one is
for, and what the kit does without it. Plumbing changes per buyer, so the document is the deliverable
and any code is an example rather than a dependency.

---

## Already closed

| | What changed | Proof |
|---|---|---|
| Speed and heat | Hardware encoding, chosen once in `kit_common.py` | `grade.py` on 30s of 1080p: 16.29s wall and 136.82s CPU, down to 5.70s and 14.65s |
| Clip scores were guesswork | `niche_calibrate.py` joins measured research to `pick_pulls --niche` | 179 video niche recommends opening on a number at 1.35x lift; a 116 video niche refuses and says so |

## Known open from the old ROADMAP, still true

A full frame cutaway covers the captions underneath it. Nothing has heard the audio where the cut
decision is made. It has never been run on an hour of tape. The planner does not know that two people
are two people. Five shipped tools reach a buyer with no proof they run.
