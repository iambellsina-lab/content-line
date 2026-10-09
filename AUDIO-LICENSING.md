# Where the audio can legally come from

**Read this before putting music on anything.** Researched 2026-10-02 against the platforms' own licence
pages. Every quote below came off a live page that day.

**This file ships with no audio in it, on purpose. See section 5.**

---

## 1. Trending sound does not transfer between platforms. At all

**The benefit lives in the platform's audio OBJECT, not in the waveform.**

On TikTok a trending sound is a sound page: a shared identifier grouping every video using it, powering
the "use this sound" button and feeding trend surfacing. That object is TikTok-internal.

Bake that audio into an exported MP4 and upload it to Instagram, and Instagram sees **original audio
belonging to your account**. No sound page, no catalogue link, no trend cohort, nothing inherited.

**And you forfeit it on TikTok too**, because the sound was never attached through TikTok's own picker.

So "grab the trending sound from TikTok and put it on the Instagram post" gives you **zero** of the
benefit on either platform, plus the copyright exposure. It is the worst available option.

---

## 2. Downloadable is not portable. This is the trap that catches everyone

A platform's creator library hands you a real file, so it feels like a normal music library. **The
licence still dies at that platform's edge.**

**Meta Sound Collection**, from `facebook.com/sound/collection/terms`:

> The grant covers "content you create, upload, and distribute on the Meta Company Products" and then:
> **"You may not perform, distribute, make available or otherwise use the SC Audio Content separately
> from the Meta Company Products."**

So Instagram, Facebook and Threads are inside it. **TikTok and Pinterest are outside it.** One exported
file sent to five destinations is licensed on three and unlicensed on two.

**TikTok Commercial Music Library**, from its own terms:

> **"You are not permitted to make available, distribute, or perform the Commercial Sounds separately
> from the videos into which you have incorporated the Commercial Sound."**

The words sublicense, transfer, assign and resell appear nowhere on that page.

**YouTube Audio Library**: "copyright-safe" is a **YouTube-only** promise. It means Content ID will not
claim the track **on YouTube**. It says nothing about Instagram, TikTok, Facebook or Pinterest, each of
which runs its own audio matching. The licence governing the download is shown only inside the
signed-in library, so read it in-product and screenshot it with the date before relying on it.

**Three YouTube things share nearly the same name.** The downloadable **Audio Library** (gives a file),
the in-app **Shorts Audio Library** (trending picker, no file), and **Creator Music** (per-video
marketplace, YouTube uploads only, explicitly non-transferable). Only the first gives you anything.

---

## 3. Two account traps on TikTok

- **A TikTok Business account LOSES the general music library.** *"Businesses cannot use the general
  music library for commercial usage."* People switch to Business for the analytics and are surprised
  the trending catalogue disappears from their picker.
- **A personal account does not launder commercial content.** The non-commercial limit attaches to the
  **video's purpose**, not the account type. If the video promotes a business, the general library is
  not available to it whatever the account says.

---

## 4. Meta's music rules target the faceless text-card format specifically

From `facebook.com/legal/music_guidelines`, and this is the one that should change behaviour:

> **"Recorded audio should not be the primary purpose of the content."**
> Greater music density makes content **"more likely... limited"**.
> Content must not **"create a music listening experience"**.
> It **"may be blocked, muted or removed"**.

**A silent text frame with a music bed is exactly that shape.** There is no footage, no speech and no
action, so the music IS the audio purpose. The format most tempted to borrow a track is the format
those rules describe.

---

## 5. For a kit sold to other people: ship no audio files

**Every licence in this landscape is personal to the subscriber or to whoever accepted the terms, and
not one of them grants sublicensing.** Meta's bars distributing the audio separately from Meta products.
TikTok's bars distributing the sounds separately from your own videos. YouTube's download licence is
behind a login and permits nothing verifiable about redistribution.

**So bundling music into a product sold to third parties is the single highest-risk act in this whole
workflow and the least supported by anything checkable.** Ship the kit with no audio and have each buyer
source their own. That one decision separates a defensible product from a recall.

---

## 6. What to actually use

**Best for a faceless or educational brand: your own voice.** It is the only audio layer you own. No
platform boundary, so one master legitimately goes to all five destinations. It sidesteps every rule in
section 4, because speech is not a music listening experience. And it is the only audio you could ever
license onward to someone else.

On macOS, free, no install:

```bash
say -v Daniel -o voice.aiff "the line you want read"
python3 bin/add_audio.py clip.mp4 voice.aiff -o out.mp4
```

**Best free music: a CC0 or verified public domain library you assemble yourself.** It is the only free
option that covers all five destinations, because the grant comes from the artist rather than from a
platform. Creative Commons BY 4.0 permits copying and redistributing "in any medium or format for any
purpose, even commercially", conditioned on attribution. **Check the licence and version per track.**

**Best paid: Soundstripe Pro, and the tier matters.** Personal and Pro both start at $9.99/mo. Personal's
own description says "personal or commercial use" while the feature table beside it marks commercial use
and client work **"Not included"**. Pro says "Cleared for client and commercial projects". **That
contradiction on the live pricing page is the easiest way to pay and still be uncovered.**

---

## The one-line version

**Use your own voice. If you need music, use CC0 or a paid licence that covers every platform. Never
bake in a trending sound, because it carries none of the benefit and all of the risk. Never ship audio
files inside a product.**
