# Setup, and everything you supply

**`README.md` is the working page: what goes in, what comes out, and the chain.** This file is the
install, the look, the hosting and the full list of what does not work yet. Read it once, then go
back to the README.

## 0. Before anything: the brand intake

**Open `BRAND-INTAKE.md` and fill it in. Fifteen minutes, once.**

Without it every post this makes will be competent and generic, which is worse than nothing because
it looks like effort. It is six questions, and then a list of places to point at instead of
describing yourself. Most of a brand is measured, not answered.

## 1. What to install first

Four things, all free. Install them once. `setup.sh` (section 2) checks every one and tells you what
is missing.

| What | Why | Needed for |
|---|---|---|
| **ffmpeg**, a build that includes **libx264** | Makes the video files | Everything |
| **Python 3.10 or newer** | Runs the kit's tools | Everything |
| **whisper-cli** plus one **model file** | Turns your speech into text, on your computer | Only "footage to clips" |
| **git** and **gh** (GitHub's command line tool) | Puts images online so a scheduler can read them | Only section 6 |
| **Google Drive for Desktop** | Makes your Drive a normal folder on your computer, so Claude reads your footage at full speed | Only if you keep footage in Drive |

### Mac

Open the Terminal app (press Command and Space, type Terminal, press Return). If you have never
installed Homebrew, install it first with the one line from the front page of https://brew.sh. Then:

```
brew install ffmpeg python whisper.cpp gh
```

### Windows

Windows is untested (see section 6). The kit's setup script needs **Git Bash**, which comes with
Git for Windows. Open PowerShell and run these one at a time:

```
winget install Git.Git
winget install Gyan.FFmpeg
winget install Python.Python.3.12
winget install GitHub.cli
```

Then close PowerShell and open **Git Bash** from the Start menu. Use Git Bash for everything below.
Transcription on Windows is manual: download the Windows zip from
https://github.com/ggml-org/whisper.cpp/releases, unzip it, and put the folder that holds
`whisper-cli.exe` on your PATH. Skip this if you do not need transcription.

### Linux

```
sudo apt install ffmpeg python3 python3-venv python3-pip git gh
```

whisper.cpp has no standard package on Linux. Build it from https://github.com/ggml-org/whisper.cpp
or skip transcription.

### Before you put music on anything, read AUDIO-LICENSING.md

The short version, because this one costs people real money. **A trending sound baked into a video file
carries none of the trending benefit on any platform**, because that benefit lives in the platform's own
audio object rather than in the waveform. **A platform's creator library gives you a real file whose
licence still dies at that platform's edge**, so one export sent to five destinations can be licensed on
three and unlicensed on two. And **no licence on offer anywhere allows you to ship audio files inside a
product you sell**, which is why this kit contains none.

Use your own voice. `bin/add_audio.py` and your system's text-to-speech are enough, and for an
educational or faceless brand it beats every music option.

### If you keep your footage in Google Drive

Install **Google Drive for Desktop** (free, from google.com/drive/download). It turns your Drive into
an ordinary folder on your computer.

**Without it, Claude cannot use your footage at all.** A Drive connector hands Claude a file's bytes
through the chat itself, and a 16 MB video is about 22 million characters. Even a 107 KB photo costs
roughly 40,000 tokens. With Drive for Desktop the same file is just a path, read instantly, free.

Measured on 2026-10-01, on a real install: a 16 MB phone video read straight off the mounted folder
in 2.1 seconds, with no download step of any kind.

**Three things to know once it is running.**

- **Your Drive is now a real folder, so treat it as read only.** Anything saved, renamed or deleted
  in there syncs to your actual Drive, on every device you own. The kit writes finished clips to
  `out/` and `review/`, never back into your Drive, and you should keep it that way.
- **Choose "Stream files", not "Mirror files", when it asks.** Stream leaves files in the cloud and
  fetches each one when something opens it. Mirror downloads your entire Drive onto the computer,
  which can fill a disk.
- **The folder name tells you which account you are signed in to.** On a Mac it is
  `~/Library/CloudStorage/GoogleDrive-your@email.com`, so you can always check.

If you would rather not install it, drag files into the kit's `inbox/` folder by hand instead. That
works exactly as well. The folder is the route either way.

### Check ffmpeg really has libx264

Many ffmpeg builds are stripped down. This one line tells you:

```
ffmpeg -hide_banner -encoders | grep libx264
```

On Windows in Git Bash that works the same. You must see a line containing `libx264`, like this
real one from a Mac:

```
 V....D libx264              libx264 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10 (codec h264)
```

If you see nothing, your ffmpeg cannot make the videos. Install a full build with the commands
above. You do not need text drawing in ffmpeg (`drawtext`, `libass`): the kit draws all captions
itself.

### Check Python

```
python3 --version
```

On Windows, write `python --version`. It must say 3.10 or higher.

### The transcription model

whisper-cli needs a model file, which is a separate download. The kit uses `ggml-base.en.bin`:
**about 148 MB**, English only, free, downloaded once. `setup.sh --with-model` fetches it for you
after asking.

**What breaks if you skip whisper and the model:** "footage to clips" cannot transcribe your
recordings, so it cannot find the best moments. Everything else still works: clips from words,
carousels, captions you write yourself. If you already have a transcript (an `.srt` or `.vtt` file
from another tool), you can hand that to Claude instead and skip whisper completely.

---

## 2. Install

1. **Get the kit folder.** However it reached you, a shared Drive folder or a zip, put it
   somewhere you will find again, for example `Documents/content-line`. From a Drive folder: open
   it, click the folder name at the top, choose **Download**, and Drive gives you the zip.
   Keep the folders inside exactly as they are: `bin`, `skills` and `specs` have to stay next to
   `setup.sh` or nothing will find anything.
2. **Open a terminal inside that folder.**
   - Mac: open Terminal, type `cd ` (with a space), drag the folder from Finder into the window,
     press Return.
   - Windows: open the folder in File Explorer, right click empty space, choose **Open Git Bash here**.
3. **Run the setup script:**
   ```
   bash setup.sh
   ```
   To get the transcription model in the same go, run `bash setup.sh --with-model` instead. It tells
   you the size and asks y or n before it downloads anything.
4. **Read the last lines.** They say one of two things.
   - `RESULT: PASS. This computer can make clips.` You are done with setup.
   - `RESULT: FAIL.` Under it is a numbered list. Each item says exactly what to run. Do them in
     order, then run `bash setup.sh` again. Repeat until it says PASS.
   `[WARN]` lines about whisper are fine if you are not doing "footage to clips" yet.
5. **Give Claude the skills.** The skills are the instructions that teach Claude how to use the
   tools. Copy them to where Claude Code looks. In the same terminal:
   ```
   mkdir -p .claude/skills
   cp -R skills/clip-factory skills/drive-intake skills/niche-research skills/social-engine skills/video-cut .claude/skills/
   ```
6. **Fill in the blanks in the skills.** The skills ship with twenty one placeholders written like
   `{{SCHEDULER}}` and `{{BRAND_HANDLE}}`. They are deliberately blank because they are yours, not
   anyone else's. Until you fill them, Claude will read the placeholder as if it were a real answer.

   The fastest way is to let Claude do it. Start Claude in this folder and say:

   > Go through every skill in .claude/skills and show me each {{PLACEHOLDER}}, one at a time, with
   > what it is for. Ask me for the value and fill it in.

   To see them yourself first:
   ```
   grep -rho "{{[A-Z_]*}}" .claude/skills | sort -u
   ```
   The ones that matter most are `{{SCHEDULER}}` (whatever you post with, for example Metricool or
   Buffer), `{{BRAND_HANDLE}}`, and the three brand colours. The rest can wait until you hit them.

7. **Start Claude Code in this folder.** Type `claude` in the same terminal (or open this folder in
   the Claude desktop app's Code tab). To confirm it sees the skills, ask: *"Which skills do you
   have in this folder?"* You should see clip-factory, drive-intake, niche-research, social-engine and video-cut.

### What `setup.sh` checks

1. ffmpeg and ffprobe are installed, and ffmpeg can encode H.264 (libx264).
2. Python 3.10 or newer is installed.
3. It builds a private Python environment in a `.venv` folder inside the kit and installs Pillow
   (the picture library that draws the captions) into it. Nothing is installed system-wide.
4. Pillow can really draw text.
5. whisper-cli and the model file (optional, shown as a warning if missing).
6. It runs `bin/kit_check.py`, which makes real test videos, including one with text, and counts the
   text in a frame so a silently blank video would be caught.

It never installs ffmpeg, Python or whisper for you, never deletes anything, and never downloads
anything without asking. It exits with an error if anything required failed.

### Seeing it work

Make the example clip with your own eyes before anything else:

```
.venv/bin/python bin/make_clip.py specs/example-clip.json
```

On Windows: `.venv\Scripts\python.exe bin\make_clip.py specs\example-clip.json`.
It prints `out/example-clip.mp4` and a size. Open that file (Mac: `open out/example-clip.mp4`,
Windows: `start out/example-clip.mp4`). You should see short captions in white on a dark blue
background, with one word in teal. That is the proof the machine works.

---

## 3. What you supply

The kit ships with **no look**. Without a brand file you get plain white text on dark grey. The
look is yours to make.

### Your brand file

1. Copy `specs/example-brand.json` to `specs/mybrand.json`. (Any name works. Use the same name when
   you talk to Claude.)
2. Open it in any text editor (Notepad, TextEdit set to plain text, VS Code). Change the values.
   Lines starting with an underscore are notes and are ignored. Keep the quote marks and commas.
3. Check your look right away. The brand file renders on its own as a preview:
   ```
   .venv/bin/python bin/make_clip.py specs/mybrand.json
   ```
   Open `out/brand-preview.mp4`. Change a value, run it again, look again.
4. If you get an error about the file, it names the line and column of the typo. It is nearly
   always a missing comma or quote mark.

**Fields that matter most** (these are your look):

| Field | What to put |
|---|---|
| `font` | Your brand typeface as a `.ttf` or `.otf` file. Make a folder called `fonts` in the kit, put the file in it, and write `"fonts/YourFont-Bold.ttf"`. Leave `null` and the kit uses the best bold font your computer has, which is a stand-in, not your typeface. |
| `text_color` | The caption colour, like `"#FFFFFF"`. |
| `accent` | The one highlighted word per card, like `"#2EC4B6"`. |
| `background` | A `gradient` (top colour in `from`, bottom in `to`), a `solid` colour, or an `image` from your own file. |

**Fields that are useful but secondary:**

| Field | What it does |
|---|---|
| `handle` | Small footer text on carousel slides, like `"@yourhandle"`. |
| `max_lines`, `max_lines_stills`, `cover_lines` | How many lines a card, a slide and the first slide may use. |
| `caption_position`, `caption_nudge` | Where captions sit when they go over your own footage: `lower`, `center` or `upper`, plus a pixel nudge. |

**Cosmetic, leave alone until the rest feels right:** `name`, `shadow` (on or off, how soft),
`line_height`.

Tell Claude which file is yours once: *"My brand file is specs/mybrand.json. Use it for everything."*

### Your own voice notes

Create a plain text file, for example `voice.md`, that says how you talk, the words you never use
and the claims you will not make. Then tell Claude: *"Read voice.md before you write any caption,
hook or post, and follow it."* The kit has no voice rules of its own (section 5).

### Your own accounts

- **To host images** (only if a scheduler needs a link): a GitHub account. See section 4.
- **To queue posts for review:** a scheduler you already use, such as Metricool or the GoHighLevel
  social planner, connected to Claude. This is optional. With none, finished clips and caption text
  stay in `review/` and you post by hand. The first time, Claude will ask for your scheduler's
  details, one value at a time, and nothing is invented.
- **Credentials stay with you.** Never paste a password or token into the chat. If something needs a
  login (for example `gh auth login` in section 4), you do that step yourself in your own terminal.

---

## 4. Hosting images

Schedulers such as Metricool read a post's picture from a **public web address**, not from a file on
your computer. `bin/publish_media.py` solves that: it copies your images into a GitHub repository
that you own and prints a public link for each. Do this once.

1. Sign in to GitHub from your terminal (this opens your browser, and you log in yourself):
   ```
   gh auth login
   ```
2. Make a public repository and clone it. Run this **next to** the kit folder, not inside it (for
   example in `Documents`):
   ```
   gh repo create content-media --public --add-readme --clone
   ```
   That creates `github.com/<your-username>/content-media` and a folder called `content-media`.
3. In the kit folder, copy the settings file and point it at that clone:
   ```
   cp specs/media-repo.example.json media-repo.json
   ```
   Open `media-repo.json` and change `local_clone` to the full path of the `content-media` folder.
   You can delete the `owner`, `repo` and `branch` lines. The script reads them from the clone.
4. See what it would do first (this changes nothing):
   ```
   .venv/bin/python bin/publish_media.py out/some-slide.png --dry-run
   ```
5. Do it for real:
   ```
   .venv/bin/python bin/publish_media.py out/some-slide.png
   ```
   It prints a line like
   `https://raw.githubusercontent.com/<you>/content-media/main/media/2026-10-01/some-slide.png`.
   Open that link in a browser to confirm the picture loads. That link is what a scheduler uses.

**Everything in a public repository is public.** Only publish pictures you are ready for the world
to see. Safe to run twice: files already there are skipped.

You can also just tell Claude: *"Host these slides with publish_media.py and give me the links."*

---

## 5. What is deliberately not included

The kit was built from one working system. Two parts of that system are personal, so they are
**not** here, on purpose:

- **The author's taste gate (`no-slop`).** The rules for what counts as bad writing and what is
  allowed to ship are one person's taste. Handing them to you would pass an opinion off as a fact.
- **The author's voice rules (`brand-voice`).** How somebody else writes and talks is theirs. You
  write your own (section 3).

Also removed: every account, folder id, board id and connector id of hers, and the two businesses'
specific material. What remains is the craft: how a short video is built and cut, which numbers
predict growth, and how to test one change at a time.

One rule is kept as a default you can change: **posts stay drafted, not auto-published,
until you have real numbers that justify more automation.** If you want a different rule, tell
Claude and have it write the change into your notes with the date.

---

## 6. What does not work yet

Plainly, so nothing surprises you.

- **Only one computer has ever run this.** It was built and tested on one Mac. It has never run on
  Windows, on Linux, or on a second Mac. The setup script and the tools are written for all three,
  but "should work" is not "works". If something fails on your machine, copy the `[FAIL]` lines
  and send them to whoever gave you the kit.
- **Caption cards are cut by a script now, but the script cannot hear.** `bin/cards_from_srt.py`
  turns a transcript and a chosen moment into the timed two to four word cards, so the middle of
  door 2 is no longer hand work. What it cannot judge is whether a line earns the screen, or where
  the emphasis really falls. Read the cards before you render, every time.
- **Card times from an ordinary transcript are approximate.** A normal `.srt` timestamps a cue of
  several words, so a card boundary is interpolated and can sit up to about a second from the real
  word. Transcribe with `-ml 1` (one word per cue) for times that match the mouth. The script says
  which kind it used.
- **The full chain has not been run on real speech.** Transcript to picked moments to a card spec
  to a finished captioned 1080x1920 file has been run end to end from this copy of the kit, but on
  a synthetic test video, not on a real recording of a person talking. Your first real recording is
  the first real test.
- **What has been tested is how it behaves when the transcript is ugly.** `fixtures/awkward/` holds
  eight transcripts of things real speech does: a four second silence mid-sentence, a stutter, two
  people over each other with speaker labels, no punctuation at all, nothing but filler, broken cue
  times, music tags, a word held for nine seconds. `setup.sh` runs all of them every time. They
  prove the cards stay usable and that the script says what it noticed. They do not prove the
  captions read well, which only your eyes on your own footage can do.
- **The skills have never been used by a Claude session on another computer.** The copy command in
  section 3 works, but whether your Claude picks the skills up the way the author's does is untested.
  The "Which skills do you have" question in step 6 is how to find out.
- **Image hosting has never pushed to a real GitHub repository.** Every step before the push was
  tested, and the error messages were checked. Your first real run is the first real test, which is
  why section 6 starts with `--dry-run`.
- **Scheduler hookup is untested on your accounts.** Nothing here has been run against your
  Metricool or GoHighLevel setup. The review-before-publish route differs by plan and has to be
  tried with one throwaway draft before you rely on it.
- **One size.** Everything is 1080 by 1920. There is no square or 4 by 5 carousel size yet.
  Loudness, frame rate and safe zones are fixed numbers inside the tools.
- **English only.** The transcription model is English, and the moment-picker's word lists are
  English. Its default clip length (35 to 75 seconds) is one person's short-form
  rule, not a law. `BEFORE-YOU-CUT.md` is where you replace it with your own.
- **A look made of text.** Captions, gradients, solid colours or one background picture. There is
  no motion graphics, no b-roll, no voice generation, no thumbnails, no titles, no uploading.
- **Research is reading, not an API.** The `niche-research` skill does find out what is working,
  by opening real accounts in a browser and reading their captions and engagement. But it is Claude
  looking, twenty to forty accounts in a sitting, not thousands. There is no live trend feed here,
  because no free one exists. You still bring the account list.
- **Fonts.** Without your own font file, the kit uses a stand-in. It will look fine and will not
  look like your brand.
- **Windows transcription is a manual setup.** Linux too. The Mac is one command.

### If something goes wrong

- `bash: setup.sh: No such file or directory`: your terminal is not in the kit folder. Repeat
  install step 2.
- Errors that mention `\r` or `bad interpreter` on Windows: the file got Windows line endings. Run
  `sed -i 's/\r$//' setup.sh` and try again.
- A command on Windows says `python3` is not found: write `python` instead.
- Anything else: run `bash setup.sh` again and read the `next step` lines. Then send whoever gave you the kit the
  `[FAIL]` lines.

### What is in this folder

| Folder or file | What it is |
|---|---|
| `BRAND-INTAKE.md` | **Start here.** Six questions and a list of things to point at, once |
| `setup.sh` | The setup and check script |
| `LONG-FORM-INTAKE.md` | An hour of tape to a batch of clips: the four commands and what each measures |
| `bin/` | The tools Claude runs. You do not need to open these |
| `skills/` | The instructions that teach Claude the method |
| `specs/` | Example brand and content files to copy and change |
| `requirements.txt` | The one Python library the kit uses (Pillow) |
| `inbox/`, `out/`, `review/`, `work/` | Made as needed: your footage, finished clips, drafts for your approval, scratch |
