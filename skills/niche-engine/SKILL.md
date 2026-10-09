---
name: niche-engine
description: The loop that joins the three other skills into one system. The user drops footage in a folder, the system knows their niche, it reads what is actually winning in that niche, rebuilds that shape with the user's own footage, and queues it. Fires on "run the engine", "do this week", "make my content", "I uploaded footage", "what should I post this week", "set up my niche", "recreate what's working". It never invents research, never copies a claim, and never posts without the user's yes unless they have switched autopost on themselves.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, WebFetch, WebSearch, SendUserFile
---

# The niche engine

**The whole product in one sentence: they upload, it studies the niche, it rebuilds what is winning with
their footage, it queues it.**

This skill owns no renderer and does no research of its own. It calls `niche-research`, `drive-intake`,
`video-cut` and `social-engine` in order and keeps the state between them. **The state is the thing that
was missing.** Research used to produce a report a human read and then forgot. Now it produces a
`niche-profile.json` the editor can execute.

## The loop

```
  specs/niche-profile.json  ←──────────────── niche-research (reads real accounts)
            │                                        ▲
            │ format to rebuild                      │ refresh when stale
            ▼                                        │
  inbox/ or the synced cloud folder ──→ drive-intake ──→ video-cut ──→ review/
            (their footage)                                              │
                                                                         ▼
                                                                  social-engine
                                                                   (queue it)
```

## Step 0, once per brand: know the niche

**Without this the system is a generic editor.** Needs three things and only the user has them:

1. **The niche in one narrow phrase.** "Chiropractic" is a category. "Chiropractic care for desk
   workers" is a niche. Make them narrow it.
2. **Five to fifteen accounts.** Theirs to name. **Never invent this list.** A guessed list produces a
   confident report about the wrong people, which is worse than no report.
3. **`BRAND-INTAKE.md` filled in**, which carries their limits and what they will never do.

Write `specs/niche-profile.json` from `specs/niche-profile.example.json`.

## Step 1: research, and turn it into something executable

Run `niche-research`. It reads real accounts and ranks on **views, shares, sends and comments, never on
follower count**, because a follower count describes an account's past and the ratio of views to
followers is what the post itself explains.

**Then do the part that is new.** For each shape that three or more outlier posts share, fill a
`winning_formats` entry. **Not a description, a build instruction:** duration range, hook type, where
the turn lands, cuts per ten seconds, caption style, grade, audio. The `execute` block maps onto the
kit's own tools, so the editor can run it without a human translating anything.

**Three posts sharing a shape is a finding. One is a coincidence.** Never write a format from one post.

**Refresh when `last_researched` is more than 30 days old.** A format that worked in spring is a
historical note by autumn.

## Step 2: their footage comes in

`drive-intake` watches the synced cloud folder or `inbox/`. Listing is free; opening a file downloads
it. For anything heavy, copy it local once and work there. **Never write back into their cloud folder.**

Transcribe locally with whisper-cli. It is free and needs nobody to click anything. **Do not use a paid
transcription connector.**

## Step 3: rebuild the shape with their footage

**This is the step people get wrong, so be exact about it.**

> **Borrow the shape. Never the claim.** Copying how a winning post is built is craft. Copying what it
> says is theft, and their claims are theirs to defend, not yours.

So: take `winning_formats[n].execute` and apply it to the user's own material. The hook type, the
length, the cut rhythm, the caption treatment, where the turn lands. **The words come from the user's
own footage and their own expertise.** If the source post says "three stretches that fix lower back
pain", the format is *a numbered list delivered to camera, turn at 60 percent, hard-cut captions*. It is
not that sentence.

**Check `never` and `claims_to_avoid` before rendering.** Regulated niches have language that cannot be
used, and a format borrowed from someone who ignores that will carry their risk onto your user. A
chiropractor cannot claim to cure. Fill that list from the user or their regulator, never from a
competitor's caption.

## Step 4: queue it

`social-engine` stages it. **Drafts by default.** A user who has deliberately switched on autopost in
their own scheduler has made that choice and it is theirs; the kit does not make it for them, and it
never flips that flag on their behalf.

## Step 5: the only part that decides anything

Research says what to try. **Their own numbers say what to keep.** Hold the format constant, move one
variable, run about twelve posts, then read it. Record the result in the profile's `test` block.

**Until twelve posts have run, everything in the profile is a hypothesis wearing a number.** Say so
when reporting, every time.

## What this never does

Never invents an account list, a view count, or a format with fewer than three posts behind it. Never
copies a sentence, a statistic or a story. Never follows, likes or comments as the user. Never signs in
on their behalf. Never claims a post is live without reading it back.

## The honest limits

- **Reading, not an API.** Twenty to forty accounts in a sitting.
- **Engagement is not reach.** Sends and likes are visible from outside. Impressions are not.
- **A pattern is not a cause.** A winning account may be carried by a face, a back catalogue or an ad
  budget, none of which is visible. Say that, then test anyway.
- **Everything is a snapshot.** Date every file.
