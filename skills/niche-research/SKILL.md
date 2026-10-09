---
name: niche-research
description: Find out what is actually working in a niche by reading real accounts and their real numbers, then report the PATTERN rather than the posts. Fires on "what's working", "research the niche", "what are they posting", "competitor research", "find viral hooks", "what should I copy", "look at these accounts", "why do their posts do better". Reads only. Never follows, likes, comments, saves or posts. Never copies a claim, only a form.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, WebSearch
---

# Niche research

**Borrow the shape. Never the claims.** Copying what someone says is theft and it is also wrong, because their claims are theirs to defend. Copying how they say it is craft, and it is the only part that transfers.

## The tool, and the one mistake to avoid

**Use the BROWSER, not WebFetch.** Instagram, TikTok and Pinterest are JavaScript applications. `WebFetch` returns a page header and nothing else, which reads as "this is impossible" and is wrong. The browser renders the page and sees everything.

**Re-measured 2026-10-02, and the earlier claim here was too optimistic. Correcting it rather than leaving it.**

| Logged out, on Instagram | Readable? |
|---|---|
| A public profile: followers, following, bio, links | **Yes** |
| The grid of posts, as links | **Yes**, but the tiles carry NO numbers |
| **An individual post page: likes, comments, caption, date, format** | **Yes.** Measured: a real reel page returned `55 likes`, `2 comments` and its caption |
| **Views** | **No.** Not shown on a reel page logged out |
| **Shares and sends** | **No.** Not visible from outside at all |
| Search, explore, hashtag and topic pages | **No.** They redirect to `/accounts/login/` |

An earlier version of this file said sends were visible from outside and were "the prize". **They are not
visible.** Nor are views, and nor is search. Anything built on those will fail.

**So the workable outlier test is likes against that account's OWN median, and likes against its
follower count.** Weaker than views per reach, and still enough: a post at several times its account's
median did something the others did not, and that is the thing being studied. State the limitation every
time you report.

**Finding accounts therefore cannot happen on Instagram itself.** Search is gated. Handles have to come
from the user, or from public pages that name them (articles, Reddit threads, directories, YouTube).
Record where each handle came from. **Never sign in as the user to get past this.**

## What you need before starting

| Thing | Where it comes from |
|---|---|
| Five to fifteen accounts | The user names them. Include small accounts with outsized posts on purpose, see the next section: size is not the filter |
| The niche in one phrase | The user. Make them narrow it: "budget van conversions", not "travel" |
| Their own numbers, if any | Their scheduler's analytics. If they have never posted, say so and proceed on others' numbers only |

**Never invent the account list.** A guessed list produces a confident report about the wrong people.

## What counts as virality, and what does not

**Views, likes, comments, shares and sends. Not followers.** This changes who to look at, so read it
before picking accounts.

A follower count describes an account's history. It says nothing about whether a given post travelled.
A big account posting to its own audience is not viral, it is a mailing list. A small account whose post
went far past its own following is the algorithm choosing to distribute it, which is the thing being
studied.

**So the denominator is the finding.** A post with 400,000 views on a 3,000 follower account reached
more than a hundred times its own audience. That post is a better teacher than anything a 2 million
follower account posts, because nothing but the post itself can explain it.

| Signal | What it tells you | Rank by it? |
|---|---|---|
| **Views** | Did it travel at all | Yes, first |
| **Shares and sends** | Did someone spend their own reputation on it. The strongest signal there is | Yes |
| **Comments** | Did it make people need to reply. Argument and recognition both do this | Yes |
| **Likes** | Cheapest action available. Useful only next to the others | Weakly |
| **Followers** | The account's past. Use it ONLY as the denominator, to spot a post that escaped | Never rank by it |

**Do not filter the account list by size.** Include the small accounts with enormous posts
deliberately. They are the ones carrying a transferable lesson.

## The procedure

**1. Size the niche.** Open the platform's own tag or topic page for the phrase. Record the post count and the related searches it offers. Those searches are the platform telling you what people actually look for, in their words rather than yours.

**2. Widen the list, free.** On two or three of the named accounts, read the platform's "accounts you might like". It is a recommendation engine built on real co-following behaviour. Add anything that fits and tell the user what was added and why.

**3. Read each account.** Twenty recent posts is enough. For each one record: the caption's FIRST LINE, the format (reel, carousel, still), rough length, and the engagement numbers shown. Put it in a file, not in the chat, or it dies when the chat closes.

**4. Find the outliers, two ways.** First: a post at two times its own account's median. Second, and
stronger: a post whose views run far past that account's follower count. The second one cannot be
explained by an existing audience, so whatever is in it is the lesson. **Never rank raw numbers across
accounts.** Each account is its own baseline, and the ratio is what travels between them.

**5. Report the pattern, not the posts.** This is the whole output. For every outlier, answer:

- How does the first line open? A question, a number, a flat claim, a confession, a contradiction?
- How long before the turn lands?
- Does it tell or ask?
- Is the hook in the words, the picture, or the first frame?
- What is the shape you could fill with different content?

**Three outliers that share a shape is a finding. One is a coincidence.**

**6. Turn it into one testable brief.** "Open on a flat claim that contradicts the common advice, land the turn at about 60%, close without a call to action." That is something twelve posts can test. "Post more reels" is not.

**7. Hand it to the test loop.** The brief sets the format. `social-engine` holds the format constant and moves one variable. Research says what to try. Their own numbers say whether it worked for their audience, which is the only question that matters in the end.

## The honest limits, state them every time

- **This is reading, not an API.** Twenty to forty accounts in a sitting, not thousands. It is slow because a person is looking.
- **Logged out sees less than logged in.** Some counts are hidden, some grids truncate.
- **Engagement is not reach.** Likes and sends are visible, impressions are not. An account with a big following and low sends may be being carried by its back catalogue.
- **A pattern is not a cause.** They may be winning on the strength of a face, a back catalogue, or an ad budget none of which is visible. Say that, then test anyway.
- **Nothing here is live.** It is a snapshot of the day it was read. Date every file.

## Where it goes

Write findings to `research/<niche>-<date>.md`. Each file holds: the accounts read, the raw rows, the outliers with their numbers, the shared shapes, and the one brief. **A finding that lives only in a chat is a finding that is gone**, and research is the most expensive thing here to redo.

Re-read before the next round. Two snapshots apart show what moved, which is better than either alone.

## What this never does

Never follow, like, comment, save, share, message, or post. Never sign in on the user's behalf or type their credentials. Never copy a sentence, a statistic or a story from another account into their content. Never present someone else's claim as theirs to make.

If something can only be read while signed in, say so and let the user decide. Their account is theirs to risk, not yours.
