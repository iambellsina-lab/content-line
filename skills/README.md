# Skills

Five skills that make the content line usable from inside Claude. Copy this `skills/` folder to
wherever your Claude setup reads skills from. Claude loads each one when you say something that
matches its description.

| Skill | You say | It does |
|---|---|---|
| `clip-factory` | "make a clip of this line" | Words to a finished captioned vertical video, with a frame check |
| `drive-intake` | "cut up this recording" | Transcribes locally, proposes the best pulls, captions and cuts them, stages them for your yes |
| `video-cut` | "why does this feel flat" | The craft rules: structure, cutting rhythm, captions, safe zones, loudness |
| `social-engine` | "what should I post this week" | Which numbers matter, the one-variable test loop, batching, queueing for review |
| `niche-research` | "what's working in this niche" | Reads real accounts and their real numbers in a browser, reports the SHAPE that is winning, never the claims |

## Placeholders

Every value that belongs to one person is written as `{{LIKE_THIS}}`. Each skill has a table near
the top saying what the value is and where to get it. The first time you use a skill, Claude asks
for the ones it needs. Answer once and ask Claude to write the answers into the table, so you are
not asked again.

## Folders the skills use

All inside the kit folder, created when first needed: `inbox/` (your footage), `work/` (scratch),
`out/` (finished clips), `review/` (staged for your yes).

## What is deliberately not here

`no-slop` and `brand-voice` are not part of this kit. They hold one person's taste and one person's
writing voice, and shipping them would hand those rules to you as if they were universal. They are
not. Write your own voice notes (how you talk, words you never use) and tell Claude to follow them.
`clip-factory`, `drive-intake` and `social-engine` each say where your voice notes plug in.

Nothing in these skills posts, schedules or publishes anything. Nothing spends money.

## niche-engine

**The loop that joins the others into one system, and the reason the kit is more than an editor.**

The user drops footage in a folder. The engine knows their niche, reads what is actually winning in it,
rebuilds that shape with their own footage, and queues it. Its state lives in `specs/niche-profile.json`,
which is the piece that was missing: research used to produce a report a human read and forgot, and now
it produces a format the editor can execute.

Start at `specs/niche-profile.example.json`. It cannot be filled without the user naming their niche and
their accounts, by design.

**Borrow the shape, never the claim.**
