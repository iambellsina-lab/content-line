# What this kit is, against what it is meant to be

**Re-measured 2026-11-04 by running every capability. The previous version of this file was written
2026-10-15 and was wrong about six of the nine.** It is kept at `superseded/THE-GAP-2026-10-15.md`.

**How this was measured.** Each capability was run against real input and its raw output read. A file
with the right name counted for nothing. Three states only: **works end to end**, **exists and is
broken**, **does not exist**.

## The spec

A business connects Claude, Google Drive and its social accounts to GoHighLevel, then hands over its
own links and files. From those the kit learns the brand voice and the niche, measures what is already
performing in that niche, writes content in that voice, posts it, and keeps posting on a schedule, so
that after one setup prompt nobody has to think about it again. **The whole of social media and
marketing, which is a larger job than cutting clips.**

## The honest summary

**The old file scored three built, two half, four missing. The real count today is seven working, one
partial, one open.** Six capabilities it called missing or half now run end to end, and the kit's own
check script reports `34 passed, 0 failed, 0 warnings, 1 skipped. READY.`

**The chain the spec describes runs.** Voice from their posts, niche from measured video, a caption in that
voice, and a scheduled draft. What it does not yet do is run as one command, and the research signal
reaches the clip scorer as a nudge rather than as a ranking.

## The map

| # | What the spec described | State | Measured 2026-11-04 |
|---|---|---|---|
| 1 | Integrations: Claude, Drive, social, GHL | **partial** | `schedule_post.py` is a real scheduler integration and was run. Drive is `drive-intake`, a skill and not code. **No GoHighLevel anything**, confirmed by grep over `bin/` |
| 2 | Understand their brand voice and niche | **works** | `brand_voice.py` read 39 real samples out of their Threads posts and wrote a 7,320 byte profile. **It refuses under 20 samples and explains the floor**: a profile from 2 posts "would read as a measurement while being an accident" |
| 3 | Market research on what is performing | **works** | Three real niches on disk: `aoyl` 175 videos / 39 winners, `business` 179 / 41, `couples` 116 / 24. `niche_calibrate.py` turns each into a profile. **YouTube only.** Nothing for Instagram or TikTok |
| 4 | Make content in that style for their brand | **works** | `draft_content.py` built a caption from a real pull using the voice and niche profiles, then graded its own output `sense check: NEEDS A HUMAN` with three serious reasons and named where it drifts from the measured voice |
| 5 | Post it, and automate posting | **works, to draft** | `schedule_post.py` built the exact payload with `"draft": true, "autoPublish": false` and sent nothing without `--send`. It refuses a local file path, correctly, because a scheduler cannot reach one. **Unattended posting is absent by design**, which matches the house rule that posts stay drafts |
| 6 | Email, and an email list | **works** | `email_sequence.py` wrote 8 files from one offer spec, 7 emails plus `sequence.json`, each with its purpose stated, 7 holes marked for a human, 2 flagged for a check before sending. It states plainly that nothing was sent and it has no login |
| 7 | Clipping that matches market research | **open, and it is the important one** | **The bridge exists and fires.** `pick_pulls.py --niche` imports hook shapes from `niche_calibrate.py`, prints `ranking by question, measured on 175 videos`, and cites `opens like a question, which wins 1.38x more often in this niche`. **Its effect was 1.5 points on a score of 91**, moving one pull from 74.1 to 75.6 and changing nothing about which clips were chosen. The base thresholds are still, in the ROADMAP's own words at `pick_pulls.py:719`, "hand-set on one fixture, not calibrated" |
| 8 | A sense filter: it makes sense and is engaging | **works** | `clip_sense.py` asks whether thirty seconds stands up alone. `kit_check.py` proves it fails when it should: it refused a clip reading "home U of Stasis" and named the transcript it checked against |
| 9 | Fast, and does not cook the machine | **works, measured 2026-10-15** | Hardware encoding. 2.9x faster, 9.3x less CPU on `grade.py` over 30s of 1080p |

## What the research actually supports, which is less than it looks

`niche_calibrate.py` requires both lift and enough winners before it recommends a shape, and that
guard is doing real work:

| niche | winners | recommends |
|---|---|---|
| `aoyl` | 39 | `question`, lift 1.38 on 16 winners |
| `business` | 41 | `number`, lift 1.35 on 12 winners |
| `couples` | 24 | **nothing.** Its highest lift is 4.03 and it rests on 2 winners |

**The couples profile is the one that matters to the Life First Method and it has no usable signal.**
Run with it, `pick_pulls.py` prints `supports no hook shape, ranking unchanged` and the output is
byte-identical to running with no profile at all. That is the tool being honest rather than failing.

## The two breaks that are left

**1. The research reaches the scorer as a nudge.** A 1.38x measured lift becomes about 1.5 points on a
91 point scale, so a shape the niche actually rewards cannot outrank a window the hand-set rules like.
**Raising that weight without evidence would be inventing a calibration**, which is the exact fault the
ROADMAP names. What closes it honestly is performance data from posts that actually ran, and the kit
has never had any.

**2. Nothing drives the chain. CLOSED 2026-11-04 by `bin/run_line.py`.** Every piece works and a buyer has to run six tools by hand with exact
flag syntax. While measuring this, two invocations failed on syntax alone: `--caption` takes a file
rather than a string, and `--when` needs a timezone offset. **A weapon they can hand to a business is
one command**, and that is the shortest path from what exists today to what the spec described.

## What is genuinely strong, and should not be rebuilt

The transcript to clip chain, local and free with no per render cost: `transcribe.py`, `pick_pulls.py`,
`plan_clips.py`, `assemble_clip.py`. Caption craft: `caption_check.py` and `caption_repair.py`, which
read a card the way a stranger scrolling past would. And the honesty running through all of it. Four
separate tools refused bad input during this measurement and each said why.


## What closed break 2, added 2026-11-04

`bin/run_line.py` drives the whole line: transcript or recording in, a scheduled draft out. Every
stage is the kit's own tool run as a subprocess with its command printed, so a failure hands back the
real output and the line to reproduce it. A wrapper that swallows the error of the thing it wraps is
worse than no wrapper.

**It stops at the edge of the machine.** Nothing uploads and nothing schedules without the flag that
says so, and `schedule_post.py` still creates a draft rather than a post. A run with no outbound flag
ends by stating plainly that nothing was scheduled and nothing was posted.

**It refuses before it spends time.** Measured on the sample transcript, all three guards fire with
nothing run: `--schedule` with no `--when`, a `--when` carrying no timezone, and `--schedule` without
`--publish`. A runner that renders for four minutes and then reports a malformed flag has wasted the
time it exists to save.

**Measured end to end**, 5 stages, 0 failures: pick moments with the niche ranking applied, plan the
cut, sense check, the caption as JSON, the drafts as markdown. `kit_check.py` now reports
`36 passed, 0 failed, 0 warnings, 1 skipped. READY.`

**One defect found while building it, and one in the check that was meant to catch it.**
`draft_content.py --out` writes a directory and `--json` suppresses `--out`, so the two cannot be had
in one call. The runner calls it twice, which costs under a fifth of a second. Then the new check was
tested by deleting the guard it names: **it stayed green**, because a different guard was refusing the
run and the check could not tell them apart. It now asserts the timezone message specifically, and
deleting the guard turns it red.
## Why the research barely moves anything, measured 2026-11-04

A peer session reported that no generator reads a performance number and that nothing opens the niche
files. **Both greps were run again here and both are artifacts of the grep.** They searched for the
literal filename pattern `niche-.*\.json`, and the path arrives as a command line argument:

- `draft_content.py:298` reads `prof = json.loads(Path(a.niche).read_text())`
- `pick_pulls.py:401` defines `load_niche(path)`
- `views` or `winner` appear in `caption_check.py`, `pick_pulls.py`, `niche_calibrate.py`, `yt_probe.py`

**The loop is connected. The real problem is what the research measures.**

`load_niche` takes exactly one thing from a profile: the hook shapes marked `recommend`. The profile
also carries `duration_seconds`, and feeding that in would be wrong, because of what is in it:

| niche | median_winning_longform | median_winning_short |
|---|---|---|
| aoyl | 551.5s | **None** |
| business | 1180s | **None** |
| couples | 789.5s | **None** |

**`yt_probe.py` measures YouTube long-form and this kit makes 30 to 60 second vertical clips.** The
one signal that crosses that gap is the shape of an opening line, and it crosses weakly, which is the
1.5 points measured above. Every length number in the file describes videos ten to twenty times longer
than anything the kit produces. YouTube does not report Shorts durations at all, so
`median_winning_short` is `None` in all three.

**So "make the research reach production" is already done and it was never the blocker. The blocker is
that the research looks at a different surface than the one being published to.** Closing it means
measuring short vertical video, which is Reels, TikTok and Shorts, rather than YouTube titles and view
counts. That is a new measurement path, not a wiring fix, and nothing in the kit does it today.

## Where the time goes, measured 2026-11-04 on a real video

**The complaint this section answers.** One video went in, three hours went by, the machine ran hot,
and what came back was captions burned onto the original instead of clips.

**The kit chain is not where that went.** `run_line.py` over a real 80.1 second 1080x1920 video, all
seven stages:

| stage | seconds |
|---|---|
| transcribe | 2.23 |
| pick moments | 0.05 |
| plan the cut | 0.05 |
| sense check | 0.04 |
| **render** | **14.66** |
| draft the caption | 0.05 |
| write the drafts to read | 0.04 |
| **total** | **17.12** |

Output: a 46.2 second clip, 58.7 MB, on the hardware encoder.

**The overheating has a named cause and it is outside this kit.** `Studio/bin/grade.py:234` hardcodes
`libx264 -profile:v high -preset medium -b:v 12M`, which is software H.264 on the CPU. The kit moved
off that on 2026-10-14. Measured here on the same 30 seconds of 1080x1920:

| path | wall | CPU | output |
|---|---|---|---|
| software, what `Studio/bin/grade.py` runs | 12.59s | **105.13s** | 43.8 MB |
| hardware, what the kit runs | 4.32s | 6.25s | 44.2 MB |
| hardware at a sane 6 Mbps | 4.12s | 6.24s | 22.6 MB |

**16.8 times the CPU for the same picture.** That is a machine running hot.

**It still does not add up to three hours, and saying it did would be a guess.** One software pass over
the entire `Studio/review/batch2` set, 6 files and 704 seconds of video, costs 4.9 minutes of wall
clock and 41 minutes of CPU. Reaching three hours of wall clock would take 36 such passes. **Something
other than encoding spent that time, and the run that did it was not found from here.** The encoder
defect is real and should be fixed on its own. It is not the whole answer.

**One more thing the numbers show.** Every rendered file measured sits near 11 to 12 Mbps:
`price-the-life-then-divide-the-number.mp4` is 232 MB for 155 seconds. No platform keeps that. At 6
Mbps the same clip is half the size and encodes no slower.
