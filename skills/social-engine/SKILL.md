---
name: social-engine
description: Build an audience with a system instead of posting and hoping. Covers which number actually predicts growth per platform, the one-variable test loop, batch production that fits a fixed weekly time budget, and how to queue drafts for review with a scheduler. Fires on "post this", "schedule", "social", "Instagram", "TikTok", "reels", "content calendar", "what should I post", "why isn't this growing", "hashtags", "best time to post", "go viral".
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Social engine

**Posting is not broadcasting. Every post is a test with one variable changed.**

An account that posts 90 times with no hypothesis has run zero experiments. An account that posts 12 times holding format constant and changing only the hook has run twelve.

## Setup values this skill needs

| Placeholder | What it is | Where to get it | Default until set |
|---|---|---|---|
| `{{WEEKLY_HOURS}}` | Hours a week the user can give to content | Ask the user. Be honest about it, the whole plan is sized to it | 3 |
| `{{POSTS_PER_WEEK}}` | Posts a week the user will make | `{{WEEKLY_HOURS}}` decides it. See Part 3 | 9 |
| `{{PLATFORMS}}` | The networks the user posts to | The user | Instagram Reels, TikTok, YouTube Shorts |
**Not sure which scheduler to use? Read `CHOOSING-A-SCHEDULER.md` first.** The short version: a
dedicated scheduler usually wins on measurement and format features, a CRM planner usually wins on
multi-person approval and bulk volume, and no scheduler at all is a legitimate choice that costs
nothing. Do not buy a CRM in order to schedule posts.

| `{{SCHEDULER}}` | The tool that queues posts: a social scheduler, a CRM with a social planner, or none | The user's own accounts. If none, drafts stay in `review/` as files and the user posts by hand | none |
| `{{SCHEDULER_BRAND_ID}}` | The id of the user's profile inside that scheduler | In the scheduler's own settings or the address bar of the profile page. Ask the user to read it out | none |
| `{{CAPTURE_FORM_URL}}` | The link posts send people to, which must capture their contact details | The user's own form or landing page | none. See the last rule in Part 4 |
| `{{OWNER_NAME}}` | Who approves drafts | The user | none |

Never invent these. If a value is missing and it matters, ask once.

---

## Part 1: the number that actually matters

Followers and likes do not predict growth. These do.

| Platform | The number | Why | Healthy |
|---|---|---|---|
| **Instagram Reels** | **Reach from non-followers**, as a share of total reach | This is literally the distribution engine reporting whether it is pushing you | Above 60% means it is distributing. Below 30% means you are talking to the people you already have. |
| | **Sends per reach** | A send is a person putting their own reputation on your post in a DM. It is the single strongest signal on the platform. | 1% of reach is good. 2%+ is a hit. |
| | Saves per reach | Signals reference value, drives the long tail | 1%+ |
| **TikTok** | **Completion rate** | The feed is a watch-time auction and completion is the bid | 50%+ on sub-20s. 30%+ on 30s+. |
| | Rewatches | Doubles effective watch time | Build loops deliberately |
| **YouTube Shorts** | **Swiped away in the first 3 seconds** | Everything downstream is gated on this | Under 30% |
| | Average view duration as % | | 70%+ on sub-30s |
| **Everywhere** | **Follows per 1,000 reached** | Converts attention into an asset. The only number that compounds. | 5 to 10 is working. Under 2 means the content performs and the account does not convert, which is a profile problem, not a content problem. |

### Two things to stop doing

- **Stop reading likes.** Likes are the cheapest action available and they correlate with almost nothing.
- **Stop optimising hashtags for reach.** On Instagram they now function closer to search and labelling than distribution. One to three accurate ones. Thirty is a 2019 tactic and it signals the account is being run by someone copying 2019 advice.

### The first-hour signal

Distribution is decided fast. The first cohort a platform shows a post to determines whether it gets a second cohort. This makes **posting time matter less than it used to and the first comment matter more**. If a post is going to be defended or explained, the explanation goes in the caption or as the first comment within two minutes, not an hour later.

---

## Part 2: the test loop

### Hold everything constant except one thing

**Format is the slowest variable to change and the most expensive to get wrong.** So:

> **One format, twelve posts, change only the hook. Then read the numbers.**

Not: three formats, four posts each, everything moving. That produces twelve data points and zero conclusions.

The order to test, cheapest first:

1. **Hook** (free to change, biggest swing). Twelve posts, same format, twelve different openings.
2. **Frame 0 / thumbnail** (free, second biggest swing)
3. **Length** (cheap). Same content at 18s and 45s.
4. **Topic** (medium). Only once a format and hook pattern is working.
5. **Format** (expensive). Only when the current format has clearly plateaued across 20+ posts.

### When to kill a format

A format is dead when **ten consecutive posts fail to beat the account median on non-follower reach.** Not three. Ten. Variance on small accounts is enormous and killing on three posts means killing on noise.

### The copy rule

**Study what is already winning in the niche and copy the pattern, then measure.** Not the content, the pattern: the structure, the length, the kind of opening, where the turn lands. Taste is a bad guide early because taste is trained on what you already like, which is by definition not new reach.

Find the niche's winners by looking at the top posts of accounts the user already follows in their
space, and write down for each: how long, how it opens, where the turn lands. That list is the
brief for the next twelve posts.

---

## Part 3: production that fits a fixed weekly budget

The real constraint is the hours the user actually has. Everything above is useless if it needs
twelve. The numbers below are sized to three hours. Scale the capture block with `{{WEEKLY_HOURS}}`,
and keep the ratios.

### The batch model

**One shoot block, one edit block, one review block. Weekly.**

| Block | Time | Output |
|---|---|---|
| **Capture** | 45 min, once | Raw material for 9 posts. One setup, one outfit, one location. Talk through nine hooks back to back without reviewing. |
| **Cut** | 60 min | 9 cuts. Claude does the first pass from the transcript (`drive-intake`); the user approves. |
| **Review and queue** | 30 min | Approve drafts, queue for the week |
| **Read** | 15 min, once weekly | Pull the numbers, decide next week's one variable |

That is 2.5 hours and it produces nine posts. The remaining 30 minutes is reply time, which matters more than a tenth post.

### The non-negotiable

**Never let the queue drop below seven scheduled posts.** The whole system fails the week something goes wrong, unless there is a buffer. Build to two weeks ahead, run on one week of buffer.

---

## Part 4: queueing, with a human gate

**Default rule: posts stay drafted, not auto-published.** The user approves every post before it
goes out, until there is enough conversion data to justify more autonomy. This is a safe default,
and the user may change it. Record any change in their notes with the date.

How that maps onto a scheduler depends on `{{SCHEDULER}}`:

- **A scheduler with a review or approval route.** Use that route, not the direct publish route.
  Name the exact call or button in this file once you have confirmed it works on the user's plan.
  Review routes are often limited to paid plans or to team accounts. Test with one throwaway draft
  and read the result before relying on it. Do not claim the review route works without that test.
- **A scheduler or CRM planner with no review gate.** Using its create-post call publishes on a
  schedule with no human check. Use it only with the user saying yes, in the same session, to that
  specific post.
- **No scheduler.** Leave the finished clip and the caption text in `review/<slug>/` and tell the
  user where they are. They post by hand. This is a complete workflow, not a lesser one.

Whatever the scheduler, these checks come first in any social session:

| Check | Why |
|---|---|
| Which networks are actually connected | Do not queue a post for a network that is not linked |
| Which metric names that network exposes | Metric names differ per network. Read the list before asking for data |
| How many posts are already queued | Below seven, say so |

Best-time-to-post data is a tiebreaker, not a strategy.

**And the rule that sits above all of it: every post that drives to a link drives to something that
captures the contact.** Send people to `{{CAPTURE_FORM_URL}}`, a form or page that stores their
details in the user's own CRM or email list. A post that drives to a link with no capture is an
advert for someone else's platform.

---

## Part 5: the weekly read, as a script

Run this once a week and report in this shape:

```
Reach:            X  (last week Y, change Z%)
Non-follower %:   X%  <- the growth number
Sends per reach:  X%
Follows / 1k:     X
Queue depth:      N posts
Best post:        [hook text] - X% non-follower reach
Worst post:       [hook text] - X%
The difference:   [one sentence on what was different about the best one]
Next variable:    [the single thing changing next week]
```

Take the numbers from the scheduler's analytics, or from each platform's own insights screen if
there is no scheduler. If a number is not available, write "not available" in that row. Do not
estimate it.

**If "the difference" cannot be stated in one sentence, the test was not controlled.** Say that instead of inventing a reason.

---

## The one-line version

**Twelve posts, one variable, then read it. Everything else is decoration.**
