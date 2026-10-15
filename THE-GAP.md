# What this kit is, against what it is meant to be

**Written 2026-10-15** from reading every script, skill and spec in the repo, after Bella described
what the kit should actually do:

> "a buisness once they have claude, google drive, and social media integrated on ghl to put in their
> buisness links and files, you understand the brand voice and niche, you do market research on what
> is preforming and them you make conetnet in that style for this persons brand and post it and
> automate posting so they do not have to think about it once they send you an initial prompt...
> full on social media and marketing. if they should send emails, an email list for them, if they
> have long form content you have capablities to cut it in a top tier way clipping feature needs to
> be suberb matching market reasearch findings and also a snese filter that the videos make sense and
> are engaing"

## The honest summary

**The kit is an excellent video workshop and not yet a marketing system.** Everything between "here
is an hour of tape" and "here is a finished, captioned, graded, correctly named vertical clip" is
built, tested and good. Almost nothing on either side of that is.

Nine capabilities are described above. **Three are substantially built, two are half built, four do
not exist.**

## The map

| # | What she described | State | What is actually there |
|---|---|---|---|
| 1 | Integrations: Claude, Drive, social, GHL | **missing** | `drive-intake` is a skill, which is instructions rather than code. No GoHighLevel anything. No social account connection |
| 2 | Understand their brand voice and niche | **half** | `BRAND-INTAKE.md` is a fifteen minute questionnaire a human fills in, and `specs/niche-profile.example.json` is its shape. Nothing reads their existing posts and derives the voice |
| 3 | Market research on what is performing | **half** | `yt_probe.py` measures real YouTube numbers for search terms, and the `niche-research` skill describes the method. YouTube only. Nothing for Instagram or TikTok, and the findings do not reach any other part of the kit |
| 4 | Make content in that style for their brand | **missing** | `make_clip.py` renders a spec. A human writes the spec. No generation |
| 5 | Post it, and automate posting | **missing** | `publish_media.py` gives a local file a public URL, which is one necessary step. `CHOOSING-A-SCHEDULER.md` is a decision document. No scheduler is wired to anything |
| 6 | Email, and an email list | **missing** | Nothing. Not a file, not a stub |
| 7 | Clipping that matches market research | **half, and it is the important one** | `pick_pulls.py` finds and scores 35 to 75 second moments. **The kit's own ROADMAP says the scores "look like predictions and are not."** So the clipping is good and the choosing is guesswork |
| 8 | A sense filter: it makes sense and is engaging | **half** | `caption_check.py` reads captions the way a stranger would, and `hear_joins.py` exports the joins so a person hears the cuts. Both check craft. Neither asks whether the clip is any good |
| 9 | Fast, and does not cook the machine | **done 2026-10-15** | Hardware encoding. 2.9x faster, 9.3x less CPU, measured on `grade.py` over 30s of 1080p |

## What is genuinely strong, and should not be rebuilt

Naming these because a rewrite would throw them away:

- **The transcript to clip chain.** `transcribe.py`, `pick_pulls.py`, `plan_clips.py`,
  `assemble_clip.py`. Local, free, no per render cost, and it plays edit order rather than tape order.
- **Caption craft.** `caption_check.py` and `caption_repair.py` are 2,800 lines between them and they
  read a card the way a stranger scrolling past would.
- **Everything is a JSON cut list, never a baked video.** The ROADMAP calls this out as the property
  to protect, and it is right. Changing an edit means editing a line and re-rendering.
- **`kit_check.py`** tells a stranger's computer whether it can run any of this, before they waste an
  hour finding out.

## The order to fill them

Judged on what unblocks the most and what fails first for a real buyer.

**1. Make the scores real (gap 7).** The kit already picks moments and already measures YouTube. They
have never been connected. Until a score means something, every downstream automation is confidently
posting the wrong thirty seconds. This is also the one the ROADMAP already admits to.

**2. The sense filter (gap 8).** A clip that is technically perfect and makes no sense on its own is
the failure mode of every automated clipper on the market. This is the difference between the kit and
a commodity.

**3. Brand voice from their own posts (gap 2).** The questionnaire is a decent fallback and a bad
front door. The method already exists in the brain's own `brand-voice` skill: harvest the voice from
what they already wrote, never invent it.

**4. Publishing (gap 5).** `publish_media.py` is half the job. The other half is one scheduler, chosen
and wired, with drafts rather than live posts.

**5. Generation (gap 4)** and **6. Email (gap 6)**, which both depend on 2 and 3 being honest.

**7. The integrations (gap 1)** last, because they are plumbing and they change per buyer.

## The thing to be careful about

**Every one of gaps 4, 5 and 6 can post or send on a buyer's behalf.** The house rule that covers it
already exists and is not optional: drafts, never live, and nothing leaves without a human yes. A
marketing kit that posts by itself on day one is a kit that posts something wrong on day two, under
somebody else's name.
