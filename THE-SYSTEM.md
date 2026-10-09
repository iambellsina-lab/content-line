# The system, end to end

**Read this to understand how the pieces fit. Read `BRAND-INTAKE.md` to actually start.**

Architecture settled 2026-10-02. Three tools, and each has one job.

---

## The three layers

```
   CLAUDE                    GOHIGHLEVEL                  METRICOOL
   the engine                the spine                    optional
   ──────────                ───────────                  ────────
   researches the niche      holds the client             per-post numbers
   edits the footage         holds the money              reach, saves, shares
   writes the captions       publishes the post           watch time, retention
   renders the files         captures the lead            view rate
                             tracks the pipeline
                             reports the revenue
```

**GoHighLevel is the spine** because it is the only one of the three that knows whether a post produced
money. It holds the contact, the pipeline, the deal value and the calendar. A scheduler cannot tell you
that. A renderer certainly cannot.

**Claude is the engine** because it is the only one that can look at what is winning in a niche and
rebuild that shape with the client's own footage. That is the part no tool does.

**Metricool is optional and should usually be taken.** It is free on its lowest tier and its MCP works
there. It adds the per-post layer GoHighLevel does not have: which individual post travelled, how many
saved it, how long people watched. **More data means better decisions, and better decisions mean more
sales.** It is not required for the system to run. It is required for the system to improve.

---

## The loop

```
  1. The client uploads footage to a synced folder
                    │
  2. The engine reads the NICHE PROFILE  ───────────  specs/niche-profile.json
     (what is winning right now, and in what shape)    refreshed every 30 days
                    │
  3. It edits their footage into that shape
     captions, grade, loudness, aspect, length
                    │
  4. The post goes out, with its OWN TRACKED LINK
                    │
  5. The link lands in GoHighLevel as a contact,
     carrying which post sent them
                    │
  6. That contact moves through the pipeline
     to a booked call, a sale, a deal value
                    │
  7. The loop closes: THIS POST PRODUCED THIS MONEY
                    │
  8. Which decides what gets made next
```

**Step 4 is the one everybody skips, and it is the one that makes the difference between a content
system and a content hobby.** A single "link in bio" across every post makes steps 5 to 7 impossible.
Each post needs its own destination or nothing downstream can be measured.

---

## What each buyer must define before anything is made

The intake asks these. **Without them the system optimises for views, which is not what anyone is
paying for.**

1. **What is the money event?** A booked appointment, a purchase, a call held, a form filled. It differs
   per business and the system cannot guess.
2. **What is one of those usefully valued at?** Not to the penny. Enough to know whether 10 leads beats
   1,000 views.
3. **Where does the money event happen?** A calendar, a checkout, a phone call.
4. **How would you know it came from a post?** If the honest answer is "I would not", that is the first
   thing to fix, before any content is made.

---

## What is settled, and what is not

**Settled:**
- GoHighLevel is the spine. The client, the money and the publishing live there.
- Claude is the engine. Research, editing, rendering, captions.
- Metricool is an optional measurement layer, free at the tier that matters.
- Clients sit in their own sub-account and connect their own social accounts, so nobody else's access
  tokens are ever held by the agency.
- The kit ships with no audio files. See `AUDIO-LICENSING.md`.

**Not settled, and being researched:**
- **What actually predicts revenue rather than attention.** The honest state today is that this kit's
  research skill ranks on views, saves and shares, which are attention metrics. They will reliably
  identify a popular account that sells nothing. That is a known defect and it is being worked on.
- **How accurate social attribution really is** once platforms strip referrers and conversations happen
  in direct messages where nothing is tracked. Expect the answer to be "partial", and expect any
  supplier claiming total attribution to be selling something.

---

## Where to start

1. `BRAND-INTAKE.md`, fifteen minutes, once per client. **The front door.**
2. `CHOOSING-A-SCHEDULER.md`, if the publishing decision is not already made.
3. `DELIVERY-MODEL.md`, if the question is how a buyer receives this.
4. `AUDIO-LICENSING.md` before putting music on anything.
5. `setup.sh`, which checks every tool and names what is missing.

**Everything in the kit runs locally and costs nothing per use.** The rendering, the transcription, the
niche measurement. The only recurring costs are the tools a business was already paying for.
