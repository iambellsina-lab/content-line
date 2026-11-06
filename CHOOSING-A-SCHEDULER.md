# Choosing where your posts go out

This kit does not care which scheduler you use. It renders finished files and hands them over. But the
choice has consequences that are not obvious from a pricing page, so here is what was measured on
2026-10-02 by actually using both.

**If you want the short version: start on a free Metricool account. Change later if a reason appears.**

---

## The three shapes this can take

| | |
|---|---|
| **A dedicated social scheduler** | Metricool, and others. Built for publishing and measurement |
| **A CRM with a social planner** | GoHighLevel, and others. Built for the business around the post |
| **Nothing** | The kit leaves finished clips and caption text in `review/`. You post by hand. **This is a legitimate choice** and costs nothing |

---

## What actually separates them

Measured against GoHighLevel and Metricool specifically. The shape of the difference generalises.

### A dedicated scheduler usually wins on measurement

This is the one that matters most, because **the whole test loop in this kit depends on numbers coming
back.** Checked on 2026-10-02:

| Metric | GoHighLevel | Metricool |
|---|---|---|
| Non-follower reach | **No** | Yes |
| Saves, shares | **No** | Yes |
| Average and total watch time | **No** | Yes |
| Retention %, view rate past 3 seconds | **No** | Yes |

GoHighLevel's full Instagram set is Posts, Impressions, Likes, Comments, Followers, Reach, Engagement
and demographics. Nothing about whether a video held attention.

**`social-engine`'s rule is that non-follower reach is the number.** A planner that does not report it
cannot run the loop this kit is built around.

### A dedicated scheduler usually wins on format features

Two that mattered in testing:

- **Instagram Trial Reels**, which show a reel to non-followers only so a version can be tested before
  the main feed is spent on it. Metricool exposes it. GoHighLevel's post type enum is exactly
  `post`, `story`, `reel`. **Note: Instagram requires 1,000 followers for trial reels**, so this is a
  later concern, not a first-week one.
- **Attaching audio.** Metricool has an audio configuration block. GoHighLevel has no audio field
  anywhere in its create-post schema.

### A CRM planner usually wins on approval and volume

Genuinely better, not consolation:

- **A named approver.** GoHighLevel's post status accepts `draft` AND `in_review`, with an approver
  field and an approval tab where that person can view, approve, reject or edit. **If two people run the
  brand, this is the better mechanism.**
- **Bulk CSV**, 90 posts per file, API driven. For scheduling a month in one pass, this beats scheduling
  one at a time.
- **One database.** The post and the contact it creates live together, with no sync.

---

## How to decide, in three questions

1. **Will anyone other than you approve posts?** If yes, a CRM planner's named-approver flow earns its keep. If no, it is a feature you will never open.
2. **Are you going to read your numbers and change what you make?** If yes, you need non-follower reach
   and retention, and most CRM planners do not have them. If you are honestly not going to look, this
   does not matter and the cheaper option wins.
3. **Are you already paying for a CRM?** If yes, its planner costs nothing extra and is a reasonable
   place to start. If no, do not buy one to schedule posts. That is a very expensive scheduler.

---

## The hybrid, which is usually the real answer

**Publish where it suits. Read numbers where the numbers are.**

Nothing stops a scheduler staying connected read-only for analytics while posts go out elsewhere.
Metricool's MCP works on its free tier, so that arrangement can cost nothing and keeps the one thing the
test loop depends on.

---

## What the kit needs from you either way

Fill these in `social-engine`:

- `{{SCHEDULER}}`, which one you chose, or `none`
- `{{SCHEDULER_BRAND_ID}}`, your profile id inside it

**And one rule that does not change with the tool: posts queue as drafts for a human to approve.**
A planner whose only route publishes immediately is not a review gate, whatever its marketing says.
Check for a draft or review state before trusting one.
