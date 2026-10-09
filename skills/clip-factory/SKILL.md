---
name: clip-factory
description: Turn a line of text, a content-calendar row or a voice memo into a finished captioned vertical MP4 that is ready to review, using the renderer in this kit's bin/ folder. Fires on "make a clip", "make this into a video", "turn this post into a reel", "render this", "make the video for", "caption this", "make a vertical", "make me a short", on any request to produce a video from words the user already has, and on any calendar row marked ready to film or ready to make. It never writes a new renderer, it calls the one that exists. Pair with social-engine when the finished clip is going into a queue.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Clip factory

**The renderer already exists. Do not write another one.**

Run it from the kit folder (the folder that contains `bin/`):

```bash
KIT_PYTHON bin/make_clip.py <spec.json>
```

`KIT_PYTHON` means the Python inside the kit's own virtual environment, which setup built:

| System | `KIT_PYTHON` is |
|---|---|
| macOS or Linux | `.venv/bin/python` |
| Windows | `.venv\Scripts\python.exe` |

Use that one, not the system Python, because Pillow is installed only in the kit's environment.
If the file does not exist, setup has not been run. Stop and tell the user to run the kit's setup
step first. Do not try to repair it.

The craft numbers the renderer enforces come from the `video-cut` skill. Read it for the reason
behind a number. This file is only about running the renderer.

## Setup values this skill needs

Fill these in once. Until they are filled, use the defaults in the right-hand column, and tell the
user they are defaults.

| Placeholder | What it is | Where to get it | Default until set |
|---|---|---|---|
| `{{BRAND_FONT_PATH}}` | Full path to a `.ttf` or `.otf` file | The brand's typeface file. On macOS look in Font Book, right click the font, Show in Finder. On Windows look in `C:\Windows\Fonts` | none, the renderer picks a system font |
| `{{BRAND_TEXT_COLOR}}` | Caption colour as hex, like `#FFFFFF` | The brand guide | `#FFFFFF` |
| `{{BRAND_ACCENT_COLOR}}` | The one highlight colour, as hex | The brand guide | `#E8B56B` is only a placeholder gold. Ask the user to choose |
| `{{BRAND_BG_FROM}}` and `{{BRAND_BG_TO}}` | Two hex colours for the background gradient | The brand guide | `#101014` to `#241A2B` is a neutral dark gradient |
| `{{BRAND_HANDLE}}` | Small footer text on carousel stills, such as `@yourhandle` | The user's account | none, no footer |
| `{{CONTENT_DATABASE_ID}}` | Id of the table the user plans content in. Optional | In Notion, open the database as a full page and copy the 32 character id from the address bar. In another tool, skip this and use a file | none, the user pastes the words in |
| `{{OUTPUT_FOLDER}}` | Where finished clips go | The user's choice | `out/` inside the kit folder |

Never invent a value for a placeholder. If one is missing and it matters, ask.

## Why text is drawn as pictures

This renderer exists because many ffmpeg builds cannot draw text at all. A build without `drawtext`,
`subtitles`, libass or libfreetype will fail on any approach that asks ffmpeg to write a character.
So text is rasterised with Pillow into transparent PNGs and ffmpeg lays them over the video as timed
overlays. That is a design choice, not a workaround to replace. It also makes the kit behave the same
on every operating system.

## The hard rule

**Never regenerate the renderer.** If a clip needs something `make_clip.py` cannot do, change that
file, test it, and leave it changed. Do not write a one-off script in a chat and let the fix die when
the chat closes. The next session gets the improved tool or the improvement did not happen.

## The loop, which is the whole point

The user's first look must not be the first look. Run this before anything reaches them.

1. **Write the cards.** Two to four words each. Cut hard. If the words are not good, no frame
   will save them.
2. **Render one card first.** `--check` prints the ffmpeg command without running it, and `--keep`
   leaves the PNGs where you can read them. One card tells you whether the type size, the colour and
   the safe zone are right, in about a second, before committing to the full clip.
3. **Render the clip.**
4. **Pull frames and look at them.**
   ```bash
   ffmpeg -loglevel error -i out/clip.mp4 -vf "fps=1/1.4,scale=300:-1,tile=5x2" -frames:v 1 -y sheet.png
   ```
   Then actually open and look at that image. **A clip nobody has watched has not been checked.**
   Judging video from its specifications instead of its frames is the most expensive mistake in this
   line of work.
5. **Fix what the frames show and render again.** Type drifting in size, a caption crossing the safe
   zone, an accent word that did not take, a card that sits too long. Loop until the sheet is clean.
6. **Only then show it to the user.** Give the file path, and say what you checked and what you
   could not check (you cannot hear it).

## Spec format

Only `cards` and `out` are required. A complete first spec that works:

```json
{
  "out": "out/first.mp4",
  "cards": [
    {"text": "Start small", "start": 0.0, "end": 1.2},
    {"text": "ship it.", "start": 1.2, "end": 2.4, "accent": ["ship"]}
  ]
}
```

Fuller spec, every key optional except `cards` and `out`:

```json
{
  "out": "out/clip.mp4",
  "duration": 12.0,
  "background": {"type": "gradient", "from": "{{BRAND_BG_FROM}}", "to": "{{BRAND_BG_TO}}", "motion": "hold"},
  "text_color": "{{BRAND_TEXT_COLOR}}",
  "accent": "{{BRAND_ACCENT_COLOR}}",
  "font": "{{BRAND_FONT_PATH}}",
  "audio": "inbox/voice.mp3",
  "music": "inbox/bed.mp3",
  "max_lines": 2,
  "cards": [
    {"text": "I say yes", "start": 0.0, "end": 1.1},
    {"text": "to everything", "start": 1.1, "end": 2.2, "accent": ["everything"]}
  ]
}
```

- `background.type` is `gradient`, `solid` (with `color`) or `image` (with `path`).
- `background.motion` is `hold`, `drift` or `push`.
- `audio` is a voice track the cards are timed to. `music` is ducked under it.
- Run `KIT_PYTHON bin/make_clip.py --help` for the flags. `--stills` writes one numbered PNG per card
  for carousels.
- Replace every `{{...}}` with the real value before running, or delete that line so the default applies.
  A spec that still contains a `{{` will fail. That failure is the correct behaviour.

## Reading a content-calendar row

If the user keeps a content calendar (Notion, a spreadsheet, a file), these are the fields that matter.
Rename them to match the user's own columns, and write the real names in this table once you know them.

| Field | What to do with it |
|---|---|
| On-screen text | The hook. Becomes the first two or three cards, close to verbatim |
| Talking prompt or script | The brief. Becomes the body cards, or the script the user reads into their phone |
| Source material | Often the strongest single line is in here |
| Pillar or topic | Keeps the look consistent inside a topic |
| Platforms | Instagram, TikTok and YouTube Shorts take 9:16. Check before assuming |
| Status | A "to film" row needs the user's own voice. A "to make" row can be built entirely by the machine |

**"To film" and "to make" are different jobs.** Say which one a row is before starting.

## Voice and likeness

This kit contains no synthetic voice, no cloned voice and no generated face. Every clip is text on a
background, or text on the user's own footage. Do not add one quietly because a silent clip feels
weak. If the user wants synthetic voice for a brand, that is their decision to make per brand. Ask,
and record the answer in their notes. Without a recorded answer, the default is real voice only.

## Defaults that are already decided

- **`motion` defaults to `hold`.** The craft rule is at most one push per thirty seconds, and
  push-on-everything is the loudest tell of cheap AI video. Use `drift` or `push` once, on purpose.
- **One accent word per clip carries the point.** Two accents is no accent.
- **Silent clips post, but they are the weakest thing this line makes.** Say so rather than
  pretending. A voice track under the cards is a large step up.
- **One type size across every card.** The renderer fits the largest size every card can share.
  Do not override it per card.

## When the user corrects something

Put the correction where it survives. A note in a chat dies when the chat closes.

| What they say | Where it goes |
|---|---|
| "the type is too small" | the size floor in `uniform_font()` in `bin/make_clip.py` |
| "I don't like that colour" | the setup values table in this file |
| "cards go by too fast" | `WORDS_PER_SECOND` in `bin/make_clip.py` |
| "this does not sound like me" | their own voice notes file. This kit ships none. Ask them to write one |

## Before it leaves

- [ ] The words were read aloud once and are the user's, not a smoother rewrite
- [ ] Frames pulled and actually looked at
- [ ] Captions inside the centre 1080 square
- [ ] One type size across every card
- [ ] `ffprobe` confirms h264 High, yuv420p, 1080x1920, 30fps
- [ ] The voice rule above was followed, not worked around
- [ ] Saved to the output folder. Not posted, not scheduled

**Posting is not this skill's job.** `social-engine` owns that, and nothing goes out without the
user's yes.
