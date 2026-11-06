# What to connect, in what order, and what the kit does without it

**Written 2026-10-15.** `THE-GAP.md` puts the integrations last of the seven jobs it lists, "because
they are plumbing and they change per buyer". This page is that item. It names what a buyer connects,
what each connection buys them, and what the kit still does if they connect none of it.

**Nothing on this page is required to use the kit.** Every tool in `bin/` takes a file path and writes
a file. No script asks for a social account, a CRM login, a cloud-storage account or an API key. A
buyer who connects nothing drags a recording into `inbox/` and gets finished captioned vertical clips
in `out/` and staged copies in `review/`. The connections below make that loop easier to feed and
possible to measure. None of them make the clips.

---

## What is wired today, and what is a person doing a step

**Wired** means there is code in `bin/` that does it. Everything else is a human step, or Claude doing
it inside a session, which is a different thing from an integration.

### Wired

| Step | Tool | Reaches the network? |
|---|---|---|
| Media to a timestamped transcript | `transcribe.py`, calling local `whisper-cli` | No, once `models/ggml-base.en.bin` is on disk. It comes down once, about 148 MB, from `setup.sh --with-model` or `transcribe.py --download` |
| Transcript to candidate moments and cut lists | `pick_pulls.py`, `plan_clips.py` | No |
| Measure what is winning on YouTube for a set of search terms | `yt_probe.py` | **Yes.** A plain HTTP read of public search results. No sign-in, no key, no account |
| Turn that measurement into a profile the clipper uses | `niche_calibrate.py`, then `pick_pulls.py --niche` | No |
| Cut lists to caption cards, and reading those cards cold | `cards_from_srt.py`, `caption_check.py`, `caption_repair.py` | No |
| Render, crop, grade, loudness, b-roll, carousels, naming, the dupe gate | `assemble_clip.py`, `caption_video.py`, `make_clip.py`, `grade.py`, `broll.py`, `carousel_render.py`, `add_audio.py`, `name_clip.py`, `check_dupes.py` | No |
| Export the joins so a person hears the cuts | `hear_joins.py` | No |
| Whether this computer can run any of it | `kit_check.py` | One HEAD request for the model URL. `--offline` skips it and says so |
| Give a finished local file a public web address | `publish_media.py` | **Yes.** A git push to a public GitHub repository the buyer owns |

### Not wired, and done by hand

| Step the vision names | What happens today | What would change it |
|---|---|---|
| Footage and documents out of Google Drive | A synced desktop folder is read as an ordinary path, or files are dragged into `inbox/`. `skills/drive-intake/SKILL.md` describes the routes in detail. There is no Drive client code in this repo | A synced folder needs none. See the Drive section below |
| A draft sitting in a scheduler | Nothing. `CHOOSING-A-SCHEDULER.md` is a decision document | `TODO.md` item 3, `bin/schedule_post.py` |
| Anything at all in GoHighLevel | Nothing. The name appears in seven documents in this repo and in zero lines of code | No item on `TODO.md` covers it |
| A voice profile taken from their own posts | `bin/brand_voice.py` landed on 2026-10-15 and answers `--help`. It reads a folder of local caption or transcript files, so it needs no account and connects to nothing. `BRAND-INTAKE.md`'s questionnaire stays as the fallback | Already moving. `TODO.md` item 2 |
| Caption and hook drafts | A human writes the spec, or Claude writes one in a session | `TODO.md` item 4, `bin/draft_content.py` |
| Email, and an email list | Nothing. No file and no stub | `TODO.md` item 5, `bin/email_sequence.py` |
| Per-post numbers coming back | Read by hand in the scheduler, or through a connector in a Claude session. Nothing in `bin/` reads analytics | Nothing written |
| A tracked link per post | `THE-SYSTEM.md` step 4 requires one and no code makes them | Nothing written |

**`publish_media.py` is the row to be precise about, because its name oversells it.** It copies the
files you name into a local clone of a public GitHub repository you own, commits only those files,
pushes, and prints one `raw.githubusercontent.com` address per file. That is one necessary step of
publishing, because schedulers take media as a URL rather than as a file on your disk. It creates no
post, touches no social account, and schedules nothing. It needs git already signed in on that machine,
it needs the repository to be public for the address to open, and its own header says the obvious
thing out loud: anything you put in a public repository is public.

---

## With nothing connected at all

**This is the section to be unmistakable about**, because a buyer who reads the vision in `THE-GAP.md`
can come away believing the accounts are the product.

A buyer with no Drive, no scheduler, no CRM and no assistant can do all of this today:

1. `bash setup.sh`, then `python3 bin/kit_check.py`. It reports whether this computer can run the kit
   before an hour is spent finding out. On one machine on 2026-10-08, `kit_check.py --offline` printed
   30 passed, 0 failed, 0 warnings, 1 skipped, READY.
2. Drag a recording into `inbox/`.
3. Run the six steps in `README.md`'s chain table: `transcribe.py`, `plan_clips.py --brief`,
   `check_dupes.py`, `cards_from_srt.py --cuts`, `caption_check.py`, `assemble_clip.py`.
4. Finished 1080x1920 clips land in `out/`. Staged copies and a `notes.md` land in `review/<slug>/`.
5. Open the app on a phone and post one.

Nothing in that list costs money per use, and nothing in it needs an internet connection once ffmpeg,
Python and the speech model are on the machine. `CHOOSING-A-SCHEDULER.md` calls the no-scheduler route
a legitimate choice that costs nothing, and `skills/drive-intake/SKILL.md` calls staging in `review/`
a complete workflow.

**What a buyer gives up by connecting nothing**, stated plainly so the trade is visible:

- They move every file by hand, and they remember to.
- No numbers come back, so the test loop in `skills/social-engine/SKILL.md` has nothing to read and
  next week's decision gets made on taste.
- Nobody can say which clip produced a customer.
- Captions, hooks and post copy are theirs to write. The kit cuts and renders. It drafts no prose.

---

## The order to connect, if a buyer connects anything

**0. Nothing, for the first recording.** Prove the kit runs on this machine and make one real clip
from one real tape. If the chain fails here, no account fixes it, and every later step assumes
finished clips exist.

**1. The footage route.** First, because every step after it needs a file on disk.

**2. A scheduler, read-only at first.** Connect it, keep posting by hand for a fortnight, and read
what it reports. `CHOOSING-A-SCHEDULER.md`'s short version: start on a free Metricool account and
change later if a reason appears.

**3. The CRM, once there is a money event to attribute.** `THE-SYSTEM.md` makes GoHighLevel the spine
because it is the only one of the three tools that knows whether a post produced money. Connecting it
before anything has been posted measures an empty pipeline.

**Claude sits at step 0** and is how most people drive the chain, so it is the operator rather than an
integration. It is covered below because the rule about what it may and may not decide matters more
than any of the plumbing.

**One warning carried over from `CHOOSING-A-SCHEDULER.md`: do not buy a CRM in order to schedule
posts.** The pricing in `DELIVERY-MODEL.md` is why. GoHighLevel is $97/mo for 3 sub-accounts, $297/mo
for unlimited, and $497/mo before SaaS Mode exists at all.

---

## Google Drive, or any synced cloud

**What it is for: getting footage and documents that already exist onto the machine the kit runs on.**
That is the whole job. No part of the kit reads from a cloud by itself, and no part needs to.

`skills/drive-intake/SKILL.md` already describes three routes, best first.

**1. A synced cloud folder, best for most people.** Install the desktop client for whatever cloud they
already pay for and their cloud becomes an ordinary folder on disk. Phone uploads appear on the machine
on their own, nothing uploads twice, and nothing is downloaded by hand.

| Client | Where it mounts |
|---|---|
| Google Drive for Desktop | macOS `~/Library/CloudStorage/GoogleDrive-<their-email>/My Drive`. Windows a new drive letter, usually `G:\My Drive` |
| Dropbox | macOS `~/Dropbox` or `~/Library/CloudStorage/Dropbox`. Windows `%USERPROFILE%\Dropbox` |
| iCloud Drive | macOS `~/Library/Mobile Documents/com~apple~CloudDocs` |

Google Drive for Desktop is free and separate from any paid Workspace plan. The skill file carries the
download address and four rules that have each bitten somebody: listing a synced folder is free and
opening a file is not, because these clients stream and files are placeholders until read; treat the
folder as read-only, because anything created or renamed there syncs to every device, so renders go to
`out/` and `review/`; copy a large file to `work/<slug>/` once before repeated passes, and check free
disk space first; and `ls ~/Library/CloudStorage/` proves which account is mounted, because the folder
name carries the signed-in address.

**The failure that reads as a broken install:** a synced folder never includes "Shared with me".
Google Drive syncs `My Drive` and `Shared drives` only, and Dropbox and iCloud behave the same way with
folders the user has not accepted into their own tree. Footage a collaborator shared is invisible to
`ls` while being plainly visible on the web. The fix is one step the user takes on the web, adding a
shortcut to that folder inside their own `My Drive`. Check this before telling anyone their footage is
missing.

**2. A plain local folder.** They drag files into `inbox/`, or AirDrop from a phone straight into it.
Always works, installs nothing, and relies on them remembering.

**3. A cloud connector, for listing and for text only.** A connector can search an account and read
documents, which makes it the right tool for a brand document, a voice note or an offer write-up.
**Never pull media through one.** Connectors return file bytes as base64 through the conversation, and
a 16 MB video is roughly 22 million characters, which no session can hold. List with the connector,
read bytes from disk.

The values `drive-intake` needs are `{{INTAKE_FOLDER}}` (default `inbox/`),
`{{CLOUD_INTAKE_FOLDER_ID}}` (prefer the full path to a synced folder over a cloud id, because a path
can be read directly), `{{CLOUD_CONNECTOR}}`, `{{OWN_ACCOUNT_EMAIL}}` and `{{WEEKLY_POST_COUNT}}`
(default 9). The skill's own rule stands: do not process anyone else's footage unless the user names
it in chat.

**Without it.** Files go into `inbox/` by hand and nothing changes downstream. No script in `bin/`
knows or asks where a file came from. Every one of them takes a path.

---

## Social accounts

**What the kit needs is a scheduler. It does not need access to the platforms themselves, and asking
for that access would be a mistake.** Three reasons, all of them already recorded elsewhere in the
repo.

**The kit renders finished files and hands them over.** `CHOOSING-A-SCHEDULER.md` opens by saying it
does not care which scheduler is used, and that stays true: the handover point is a finished MP4 plus
caption text.

**Direct platform access means holding somebody else's tokens.** `DELIVERY-MODEL.md`'s central finding
is the sub-account boundary: each buyer connects their own social accounts inside their own
sub-account, so the seller never holds anyone else's access tokens, never files Meta App Review, never
does Business Verification and never becomes a multi-tenant platform operator. Proven on a live
account on 2026-10-02: a sub-account reporting `"saasMode": "not_activated"` had 8 social accounts
connected and working across two brands.

**A scheduler has a draft state, and a platform API call does not have to.** The rule that does not
change with the tool, quoted from `CHOOSING-A-SCHEDULER.md`: posts queue as drafts for a human to
approve. Check for a draft or review state before trusting a tool, whatever its marketing says.

### Which scheduler

Already decided and measured on 2026-10-02 in `CHOOSING-A-SCHEDULER.md`. Read that rather than
re-deciding it here. The summary, so this page is not misleading on its own:

| | Where it wins |
|---|---|
| A dedicated scheduler such as Metricool | Measurement. Non-follower reach, saves, shares, average and total watch time, retention and view rate past 3 seconds. GoHighLevel reports none of them. Also format features: Instagram Trial Reels, and an audio configuration block |
| A CRM planner such as GoHighLevel's | A named approver, with `draft` and `in_review` statuses and an approval tab, which is the better mechanism when two people run a brand. Bulk CSV at 90 posts a file. One database holding the post and the contact it created |
| Nothing | Costs nothing, needs no account, and the kit supports it as a first-class route |

`social-engine`'s rule is that non-follower reach is the number, so a planner that does not report it
cannot run the loop the kit is built around. The hybrid is usually the real answer: publish where it
suits, and keep a free Metricool account connected read-only for the numbers.

Two values go into `skills/social-engine/SKILL.md` once chosen: `{{SCHEDULER}}`, or `none`, and
`{{SCHEDULER_BRAND_ID}}`.

**Where `publish_media.py` fits.** Schedulers take media as a public URL, so a buyer using one needs
that bridge, and it is the only reason to set up the media repository. A buyer posting from their phone
needs no public address and can skip the repository entirely.

**Without it.** `review/<slug>/` holds the finished MP4s, the caption text and a `notes.md` saying what
was checked. The buyer posts by hand. Every craft gate still runs, and nothing about the clips is
worse. What is missing is the queue and the numbers.

---

## GoHighLevel

**What it is for in this picture: the contact and the money event.** The posting question is separate
and is answered in `CHOOSING-A-SCHEDULER.md`.

`THE-SYSTEM.md` already argues the case, and it is the argument to keep in front of a buyer who thinks
a scheduler is enough: GoHighLevel is the spine because it is the only one of the three tools that
knows whether a post produced money. It holds the contact, the pipeline, the deal value and the
calendar. A scheduler cannot tell you that. A renderer certainly cannot.

The loop it closes, from `THE-SYSTEM.md`:

| Step | What happens | Who does it today |
|---|---|---|
| 4 | The post goes out carrying its own tracked link | A person. No code makes these links |
| 5 | The link lands in the CRM as a contact, carrying which post sent them | The CRM, if a form or calendar is wired to it |
| 6 | That contact moves through a pipeline to a booked call, a sale, a deal value | A person, in the CRM |
| 7 | The loop closes: this post produced this money | A person reading the pipeline |
| 8 | Which decides what gets made next | `niche-engine`, and a human |

**Step 4 is the one everybody skips and the one that makes the difference.** A single link in bio
across every post makes steps 5 to 7 impossible. Each post needs its own destination or nothing
downstream can be measured.

**Connect it in this order:** a sub-account for the buyer, their own socials connected inside it, a
form or calendar as the destination the tracked links point at, and a pipeline whose stages include
the money event. `DELIVERY-MODEL.md` has the two facts that save money and pain here. A sub-account
does not need SaaS Mode to exist, to have a Social Planner or to connect its own socials. And never
convert a working sub-account to SaaS Mode, because it then only has the features enabled in the
assigned tier, and an unassigned payment method leaves a lockout screen in front of the user.

**The cost of this one is not the subscription.** `gohighlevel.com/terms-of-service` Section 2 makes
the reseller fully liable to their customers and solely responsible for resolving all customer
disputes, and forbids directing customers to contact HighLevel for any reason, support included.
Read `DELIVERY-MODEL.md` before becoming anybody's support desk. Usage charges also hit the agency
card first, and rebilling recovers that cost rather than avoiding it.

**The honest state of the code: there is none.** Nothing in this repo reads from or writes to
GoHighLevel. Every step above happens in the GoHighLevel interface, done by a person, or through a
connector inside a Claude session. No `TODO.md` item covers building it, and `THE-GAP.md`'s reasoning
is that this plumbing differs per buyer, so a document serves better than code that assumes one setup.

**Without it.** The kit makes clips and the buyer posts them. What is lost is the only loop that can
say which clip earned anything, which leaves the system optimising for attention. `WHAT-PRODUCES-MONEY.md`
is about exactly that failure. A buyer with no CRM can still answer the four questions `THE-SYSTEM.md`
asks before anything is made, on paper: what is the money event, what is one of those usefully valued
at, where does it happen, and how would you know it came from a post. If the honest answer to the
fourth is "I would not", that is the first thing to fix, before any content is made. Asking every new
customer where they found you is partial attribution, and partial is what to expect anyway: platforms
strip referrers and conversations happen in direct messages where nothing is tracked.

---

## Claude, or any assistant

**What it adds.** It drives the chain. `README.md`'s own line is that the fastest way to use the kit
is to open the folder in Claude Code and say what you want, and that running the commands by hand works
identically. The six folders in `skills/` are the method it loads: `clip-factory`, `drive-intake`,
`video-cut`, `social-engine`, `niche-research` and `niche-engine`.

Four things it does that no script in `bin/` can:

- **Judgement a tool cannot reach.** Whether a pull makes sense to somebody who never heard the rest
  of the tape. Whether frame 0 would stop a thumb. What `cards_from_srt.py`'s warnings mean for this
  particular recording, where two speakers overlap or cues disagree.
- **Prose.** Post copy, a `notes.md`, a caption rewrite proposal for a human to accept or reject.
- **Reading the frames.** `drive-intake`'s verification loop requires somebody to look at a contact
  sheet, frame 0, the first and last caption and the 7-second mark. An assistant can look.
- **Filling in the per-buyer values** the skills carry as `{{PLACEHOLDERS}}`.

**What it must never be trusted with: a number.** `TODO.md` binds every item in this kit with the rule
already: every number a tool reports must be traceable to something counted, and a tool with thin data
says so rather than guessing. The same rule applies to the assistant, and harder, because a model's
guess reads exactly like a measurement to a buyer.

| Number | The only acceptable source |
|---|---|
| Duration, codec, profile, pixel format, fps, audio line | `ffprobe` on the finished file, quoted raw |
| Loudness and peak | `ffmpeg ... -af ebur128`, read out of the Summary block at the bottom |
| View counts, durations, upload ages in a niche | `yt_probe.py`, reading `ytInitialData` out of a YouTube search page |
| Hook lift, winner rate, sample size | `niche_calibrate.py`, which declines to recommend below 25 videos in a sample or 6 winners in a bucket |
| A clip's score and why it scored | `pick_pulls.py`, which prints the reason behind every point |
| Render cost | The wall clock of an actual run. `STATUS.md` 2026-10-08 measured 8.8x realtime across two clips, against the 1.2x `README.md` claims |

So: a model may write prose and may never decide a number. If a view count, a retention figure, a lift
or a render time did not come out of one of those six rows, it does not go in front of a buyer.

**Two more limits on the assistant.** It posts nothing, sends nothing and charges nothing without a
human yes in the conversation, which is `TODO.md`'s binding rule and `social-engine`'s Part 4 default.
And it reads text through a connector and never media, for the base64 reason in the Drive section.

**Without it.** Run the commands. `README.md` says by hand works identically, every tool answers
`--help`, and the ones that make decisions print the reason for each one: `pick_pulls.py` gives a
reason per point, `caption_check.py` prints findings, `broll.py` names the cards a cutaway would cover
before it encodes anything. What a buyer loses is the prose and the judgement calls, which become
their own work rather than their own problem.

---

## The rule that covers all four

`THE-GAP.md` closes on this and it is the right place to end here too. Every integration on this page
can post or send on a buyer's behalf. Drafts, and nothing leaves without a human yes. A marketing kit
that posts by itself on day one is a kit that posts something wrong on day two, under somebody else's
name.
