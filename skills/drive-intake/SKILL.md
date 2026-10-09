---
name: drive-intake
description: Turn footage the user already recorded (a phone video, a podcast episode, a coaching session, a long take) into finished captioned vertical drafts waiting for their yes. Fires on "I put a video in the folder", "there's new footage", "edit this", "cut this up", "make clips from this recording", "make something from what I uploaded", "clip the podcast", "pull the best parts", "what's new in the inbox". Boundary with clip-factory: drive-intake starts from a video or audio FILE that already exists and must be cut down. clip-factory starts from WORDS and renders text cards. If real footage supplies the picture, it is here. If cards supply the picture, it is clip-factory. Never posts, never schedules without the user's yes.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Drive intake

**They record once. The line does everything after they stop talking. Their first look is not the first look.**

This skill owns no renderer. It calls the tools in the kit's `bin/` folder and never rewrites them
(same rule as `clip-factory`). The craft numbers come from `video-cut` Parts 1 to 3. Posting belongs
to `social-engine`.

Run everything from the kit folder, the one that contains `bin/`. `KIT_PYTHON` means:

| System | `KIT_PYTHON` is |
|---|---|
| macOS or Linux | `.venv/bin/python` |
| Windows | `.venv\Scripts\python.exe` |

## Setup values this skill needs

| Placeholder | What it is | Where to get it | Default until set |
|---|---|---|---|
| `{{INTAKE_FOLDER}}` | The folder the user drops footage into | The user's choice. A local folder is the simplest. The default is `inbox/` inside the kit | `inbox/` |
| `{{CLOUD_INTAKE_FOLDER_ID}}` | Optional. A cloud folder the user also drops files into. **Prefer the full path to a SYNCED folder on disk** (see the section below) over a cloud id, because a path can be read directly and an id cannot | The mount path, for example `~/Library/CloudStorage/GoogleDrive-you@example.com/My Drive/Intake`. Only if nothing is synced, use the long id after `/folders/` in the Drive address bar | none |
| `{{CLOUD_CONNECTOR}}` | Optional. The name of the connector that can read that folder | Claude's connector settings. If none is connected, ignore the cloud route entirely | none |
| `{{OWN_ACCOUNT_EMAIL}}` | The account that owns the user's footage | The user | none. Without it, process only files the user names in chat |
| `{{WEEKLY_POST_COUNT}}` | How many posts the user publishes a week, so a sitting proposes no more than that | The user's content plan | 9 |

Never invent these. If a value is missing and it matters, ask once.

## Folders this skill uses

Create them on first use with `mkdir` (add `-p` on macOS or Linux). Do not put footage anywhere else.

| Folder | Holds |
|---|---|
| `inbox/` | Footage the user drops in. Read only. Never move, rename or delete it |
| `work/<slug>/` | Scratch for one recording: `audio.wav`, the transcript, spec files, frame sheets |
| `out/` | Finished clips |
| `review/<slug>/` | The finished clips plus `notes.md`, staged for the user's yes |
| `work/ledger.json` | One entry per processed file: name, date, outputs. Check it so a file is never cut twice |

## Getting footage onto the machine, which is the step people get wrong

Footage usually starts on a phone and the kit runs on a computer. Three routes, best first.

**1. A synced cloud folder. Best for most people.** Install the desktop client for whatever cloud the
user already pays for and their whole cloud becomes an ordinary folder on disk. Nothing uploads twice,
nothing is downloaded by hand, and phone uploads appear on the machine on their own.

| Client | Where it mounts |
|---|---|
| Google Drive for Desktop | macOS `~/Library/CloudStorage/GoogleDrive-<their-email>/My Drive`, Windows a new drive letter, usually `G:\My Drive` |
| Dropbox | macOS `~/Dropbox` or `~/Library/CloudStorage/Dropbox`, Windows `%USERPROFILE%\Dropbox` |
| iCloud Drive | macOS `~/Library/Mobile Documents/com~apple~CloudDocs` |

Google Drive for Desktop is free and separate from any paid plan. Download it at
`https://www.google.com/drive/download/`. The Workspace subscription advertised near it is a different
product and is not needed for this.

**Four rules for a synced folder, each of which has bitten someone:**

- **Listing is free, opening is not.** These clients stream: files are placeholders until read. `ls`,
  `find` and `du` cost nothing. The first real read pulls the file down.
- **Treat it as read only.** Anything created, renamed or deleted in that folder syncs to their real
  cloud, on every device. Renders go to `out/` and `review/`, never into the synced folder.
- **Copy once for heavy work.** One pass can read straight from the mount. Repeated passes over a
  large file should `cp` it to `work/<slug>/` first, so the mount is not re-serving the same bytes
  and the cache is not filling a disk that may be nearly full. Check free space before a big job.
- **Confirm the account.** On macOS the folder name carries the signed-in address, so `ls
  ~/Library/CloudStorage/` proves which account is mounted without asking.
- **A synced folder does NOT include files other people shared with the user.** Google Drive syncs
  `My Drive` and `Shared drives`, never "Shared with me". Dropbox and iCloud behave the same way with
  folders the user has not accepted into their own tree. So footage a collaborator shared is invisible
  to `ls` even though it is plainly visible on the web, and that mismatch reads as a broken install
  when nothing is broken. The fix is one step the user takes on the web: add a shortcut to the shared
  folder inside their own `My Drive`. It changes no ownership and the files become readable locally.
  **Check this before telling a user their footage is missing.**

**2. A plain local folder.** The user drags files into `inbox/` from their file manager, or AirDrops
from a phone straight into it. Always works, needs no install, needs them to remember.

**3. A cloud CONNECTOR, for listing only.** A connector can search a cloud account and read text, and
it is good for that. **Never pull media through one.** Connectors return file bytes as base64 through
the conversation, and a 16 MB video is roughly 22 million characters, which no session can hold. Even
a small photo can cost tens of thousands of tokens. List with the connector, read bytes from disk.

## Transcription is local and free. Use it.

```bash
ffmpeg -i inbox/take.mov -ar 16000 -ac 1 -c:a pcm_s16le -y work/take/audio.wav
whisper-cli -m models/ggml-base.en.bin -f work/take/audio.wav --output-srt --output-file work/take/transcript
```

On Windows the program is `whisper-cli.exe`, and paths use backslashes if the shell needs them.

Measured on one reference machine, transcription took under a second of compute per ten seconds of
speech, so a 90 minute recording takes about a minute. The `.srt` it writes is exactly what
`pick_pulls.py` reads. The model file `models/ggml-base.en.bin` is English only. It is downloaded by the
kit's setup step. If it is missing, say so and point the user at that step.

**Do not use a paid transcription connector.** Local is free, needs nobody to click anything, and
is accurate enough to pick pulls and write captions from. Spend money only if the user says yes in
chat, to that specific spend.

## The pipeline

1. **Find new media.** List `inbox/` for video or audio newer than the last ledger entry. If the
   user also set a cloud folder and a connector, list that folder too, owned by `{{OWN_ACCOUNT_EMAIL}}`
   only. The cloud route is read only: never move, rename, share or trash a file. Report the list,
   name which file you are taking, and if the user named a file, take that one.
   **Do not process anyone else's footage unless the user names it in chat.** A recording owned by a
   colleague, a client or a guest is not the user's to cut.
2. **Pull it local if it is in the cloud.** Save it under `work/<slug>/source.*`. Try a small file first.
   If a large download fails, say so and ask the user to copy it into `inbox/` by hand. Do not
   claim a pull succeeded without `ls -l` (or `dir` on Windows) and `ffprobe` on the saved file.
3. **Extract audio** with the ffmpeg line above. Run it and check the file plays with `ffprobe`.
   A source with no audio stream fails with `does not contain any stream`. Then there is nothing to
   transcribe: say so and stop. Do not invent captions.
4. **Transcribe** with the whisper line above. Open the `.srt` and read the first and last ten lines.
5. **Pick pulls.**
   ```bash
   KIT_PYTHON bin/pick_pulls.py work/<slug>/transcript.srt -n 5 --out work/<slug>/pulls.json
   ```
   **Read `--help` first. Do not guess its flags.** It prints JSON: for each pull a start, an end,
   the opening sentence, the full text, a score and the reason for the score. The rules it applies,
   from `video-cut`: 35 to 75 seconds, one complete thought, start one sentence earlier than feels
   right, pull where the speaker changes energy.
   **What text cannot tell you:** energy lives in the waveform, not the words. The script scores
   topic structure and weak proxies for energy. Treat its output as a shortlist of places to look,
   then confirm each start has a loud bit after a pause. Where the audio disagrees, the audio wins.
   Propose no more than `{{WEEKLY_POST_COUNT}}` pulls for one sitting. Give each pull a timecode,
   its first line, and one sentence on why it was chosen.
6. **Cut the cards.** Do not write them by hand.
   ```bash
   KIT_PYTHON bin/cards_from_srt.py work/<slug>/transcript.srt \
       --pulls work/<slug>/pulls.json --pull 1 \
       --source inbox/<file> --brand specs/<brand>.json \
       --out work/<slug>/pull1.json
   ```
   (`--help` first.) It cuts the chosen pull into two to four word cards, times each one from the
   transcript, drops the ums, and picks at most one accent word a card. It writes the spec that
   step 7 renders. The words are the speaker's own, in their own order: the script adds nothing.

   **Then read the cards back to the user before rendering.** The script cannot hear the recording,
   so it cannot know where the emphasis really falls or whether a line earns the screen. It reports
   whether the times are `word-level` or `interpolated`; interpolated means a boundary can sit up
   to about a second off, and `-ml 1` on the whisper line in step 4 fixes that.

   **Read its other notes out loud to the user, do not swallow them.** They are the things it
   noticed and cannot judge:
   - *speaker names taken off the screen* means more than one person is talking in this pull. Names
     never reach a card and no card spans a change of speaker, but a clip that cuts between two
     voices often needs the other half of the exchange to make sense. Say so before cutting.
   - *cues overlap in time* means people talking over each other, or the transcriber guessing. Card
     times there are not reliable. Open the waveform at those points.
   - *immediate word repeats* are stutters and restarts, kept as said. Offer
     `--collapse-stutters`, and say plainly that it drops words the speaker said and will also
     flatten a deliberate "very very". The user decides, not you.

7. **Cut and caption.**
   ```bash
   KIT_PYTHON bin/caption_video.py work/<slug>/pull1.json
   ```
   (`--help` first.) It trims, crops to vertical, burns the caption cards, normalises loudness and
   writes 1080x1920, h264 High, yuv420p, 30fps, AAC 48kHz, -14 LUFS, with captions of two to four
   words that cut in with no fade and sit inside the centre 1080 square. The caption spec is the
   same shape as the `clip-factory` one, plus:

   ```json
   {
     "source": "inbox/take.mov",
     "out": "out/take-pull1.mp4",
     "trim": {"start": 62.0, "end": 94.5},
     "times": "source",
     "caption_position": "lower",
     "focus_x": 0.5,
     "focus_y": 0.5,
     "text_color": "{{BRAND_TEXT_COLOR}}",
     "accent": "{{BRAND_ACCENT_COLOR}}",
     "font": "{{BRAND_FONT_PATH}}",
     "max_lines": 2,
     "cards": [
       {"text": "I say yes", "start": 64.0, "end": 65.1},
       {"text": "to everything.", "start": 65.1, "end": 66.4, "accent": ["everything."]}
     ]
   }
   ```

   `times` is `source` (card times are seconds in the original file) or `clip` (seconds from the
   start of the trimmed pull). `caption_position` is `lower`, `center` or `upper`. The brand
   placeholders are defined in the `clip-factory` skill. Replace them with real values or delete the
   line. **Step 6 wrote the `cards` list for you.** Edit it there if a card is wrong rather than
   retyping it here, and keep the card times in the original file's seconds. Wide recordings (a video call, a gallery of faces) can crop
   someone off or show a name tile when reframed to vertical. Choose `focus_x` per file from frames,
   not from habit.
8. **Captions come from the transcript, verbatim.** Never rewrite what the speaker said into
   something smoother. If post copy is written to go with the clip, the user's own voice notes govern
   it, and this kit ships none.
9. **Look at the frames.** The verification loop below. It cannot be skipped or summarised.
10. **Stage.** Put the finished MP4s and a `notes.md` (source file, timecodes, the transcript lines,
   what was checked) in `review/<slug>/`. Tell the user where. Update `work/ledger.json`.

## The verification loop

Run all of this for every clip, in this order.

1. `ffprobe` the file. Quote the raw codec, profile, pix_fmt, size, fps and audio line.
2. Pull a sheet and look at the image:
   `ffmpeg -loglevel error -i out/clip.mp4 -vf "fps=1/2,scale=300:-1,tile=5x4" -frames:v 1 -y work/sheet.png`
3. Pull frame 0 on its own and look at it. It must stop a thumb: no black, no logo, no mid-blink.
4. Pull a frame at the first caption, one at the last, and one near the 7-second mark. Look at each.
5. Check every caption against the transcript. A caption that says something the speaker did not say
   is a defect.
6. Check the first and last second. It must start at the start of a sentence and end on a finished one.
7. Measure the finished file, not the filter's estimate:
   `ffmpeg -hide_banner -nostats -i out/clip.mp4 -af ebur128=peak=true -f null - 2> work/loud.txt`
   Then open `work/loud.txt` and read the Summary block at the bottom. Quote `I:` (target -14 LUFS)
   and `Peak:` (ceiling -1.0). This route works the same on every system.
8. State what you cannot check. You cannot hear the clip. Say "not listened to" and give the user the
   timecode of the loudest and the quietest second to spot-check.
9. Fix what the frames show, render again, repeat. Stop when the sheet is clean.

Only then does it go to the user.

## Voice, likeness and other people on screen

- Use the user's real footage and real voice. Cutting, captioning, reframing, loudness and staging
  are fair automation.
- This kit has no synthetic voice, cloned voice, generated face or generated b-roll. Do not add one
  to rescue a bad line. If a line is bad, drop the pull.
- If the user has a written voice and likeness policy for a brand, follow it. If they do not, the
  default above stands until they say otherwise.
- **Group recordings** (a client session, a panel, a call) show other people. Before any pull that
  shows or quotes another person leaves the building, ask the user whether that person agreed to be
  used. Default to pulls where only the user speaks and only their tile is visible. If a co-host or
  partner speaks inside a pull, name them in `notes.md`.

## When something is not possible

Say it in the first line of the reply, then stage what is possible. Never swap in a worse route quietly.

- **No transcript yet.** You cannot caption and you cannot pick pulls by words. Say so and stop.
  A free fallback finds loud moments by energy only (`ffmpeg -af silencedetect` and `astats`). It
  gives candidate timecodes, not captions. Label it that way.
- **Large download fails.** Ask the user to copy the file into `inbox/`. Do not substitute a smaller
  stub recording for the one they asked for.
- **`pick_pulls.py`, `cards_from_srt.py` or `caption_video.py` missing.** Say which. The kit is incomplete. Tell the user to
  re-copy it. Do not write a one-off replacement in the chat.
- **Scheduling.** Staging in `review/` is the default and needs no account. If the user has a
  scheduler connected, `social-engine` explains the review route. Queue only after their yes.
- **Anything needing money.** Spend nothing without the user's yes.

## Before anything reaches the user

- [ ] The file was the user's own, or they named it
- [ ] Each pull is one complete thought, 35 to 75 seconds, starts and ends on a sentence boundary
- [ ] `ffprobe` raw line quoted: h264 High, yuv420p, 1080x1920, 30fps, AAC 48kHz
- [ ] The frame sheet and frame 0 were looked at, not assumed
- [ ] Every caption matches the transcript, sits inside the centre 1080 square, cuts in without a fade
- [ ] Loudness measured and quoted, with "not listened to" stated
- [ ] The voice rule was followed
- [ ] Anyone else on screen is flagged to the user
- [ ] Staged in `review/`. Not posted, not scheduled, not published
- [ ] Ledger updated
