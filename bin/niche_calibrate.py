#!/usr/bin/env python3
"""niche_calibrate.py: turn measured YouTube results into a niche profile a clipper can use.

WHY THIS EXISTS. `yt_probe.py` measures what wins in a niche. `pick_pulls.py` picks
moments out of a transcript. They have never been connected, so the kit's clip
scores are, in its own ROADMAP's words, thresholds "hand set on one fixture, not
calibrated". The requirement, stated 2026-10-15, is that clip selection should
follow measured market research instead of a hand set guess. This is the bridge.

WHAT IT CAN AND CANNOT KNOW. It reads titles, view counts and durations. From
those it can honestly measure: which opening shapes appear in the videos that got
watched, what length those videos were, and which words are over-represented among
winners. It cannot know retention, thumbnails, posting time, or whether a channel
was already big. **It reports sample sizes and refuses to assert on thin data**,
because a confident number off nine videos is how a kit starts lying to a buyer.

Usage:
    python3 bin/niche_calibrate.py research/niche.json --out specs/niche-profile.json
    python3 bin/niche_calibrate.py research/niche.json          # print only
"""
import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

# A hook shape is how a title opens. These are the openings that recur across
# short video, and each is a pattern a transcript sentence can also match, which
# is the whole point: a moment that opens like a winning title is a better pull.
HOOKS = {
    "question":    re.compile(r"^(how|what|why|when|where|who|which|can|should|is|are|do|does|did)\b", re.I),
    # Titles write "3 Things". Transcripts say "Three things". The same pattern has
    # to catch both, because niche_calibrate reads titles and pick_pulls reads
    # speech. Found by running the two against each other: a transcript opening
    # "Three things killed our first business" matched nothing at all.
    "number":      re.compile(
        r"^\W*(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b"
        r"|\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
        r"(?:things?|ways?|reasons?|rules?|signs?|steps?|mistakes?|lessons?|questions?|moves?)\b",
        re.I),
    "imperative":  re.compile(r"^(stop|start|never|always|don'?t|do not|avoid|try|watch|listen|read|build|make|get)\b", re.I),
    "first_person":re.compile(r"^(i|we|my|our|me)\b", re.I),
    "you":         re.compile(r"^(you|your|you'?re)\b", re.I),
    "contrarian":  re.compile(r"\b(nobody|no one|everyone|everybody|myth|truth|actually|really|wrong|lie|secret)\b", re.I),
    "stakes":      re.compile(r"\b(cost|lost|lose|losing|ruin|destroy|kill|fail|failed|broke|divorce|quit)\b", re.I),
}

# Speech opens with throat clearing and titles do not. "So what was the moment
# you knew?" is a question opener by any human reading, but every pattern above
# is anchored at ^, so the single word "So" hid it and the shape scored nothing.
# The kit had already been bitten by this once in the other direction (see the
# number pattern above, which had to learn that transcripts say "Three" where
# titles write "3"). This is the same bug on the other axis: the matcher reads
# titles, the clipper reads speech, and only speech has discourse markers.
#
# Stripping them before matching is what keeps the two readers looking at the
# same sentence. Applied to titles it is nearly a no-op, which is what makes it
# safe to share: the producer and the consumer must agree on what a shape is.
DISCOURSE_MARKER = re.compile(
    r"^\W*(?:so|and|but|okay|ok|well|now|yeah|yes|right|look|listen|see|like|"
    r"anyway|anyways|basically|honestly|actually|i mean|you know|um|uh|er)\b[\s,]*",
    re.I)


def strip_discourse(text, rounds=3):
    """Remove leading discourse markers so an anchored hook pattern can see the
    real opening. Several may stack: "Okay so, like, what if..."."""
    t = (text or "").lstrip()
    for _ in range(rounds):
        t2 = DISCOURSE_MARKER.sub("", t, count=1).lstrip()
        if t2 == t or not t2:
            break
        t = t2
    return t or (text or "")


def match_hook(name, text):
    """True if `text` opens with shape `name`, ignoring discourse markers.
    The one place producer and consumer both ask the question."""
    rx = HOOKS.get(name)
    if not rx or not text:
        return False
    return bool(rx.search(text) or rx.search(strip_discourse(text)))


# ---- reading a profile back ------------------------------------------------
# The consumers used to each load profiles their own way, and they drifted:
# pick_pulls and draft_content both kept only shapes marked `recommend`, so
# neither could act on a shape the niche PUNISHES, and both matched with the raw
# anchored pattern, so neither could see a question that opened with "So".
# One loader here, used by both, is what stops that happening twice.

NICHE_MAX = 12.0            # points a measured shape may move a window, either way
NICHE_FULL_EVIDENCE = 20.0  # observations of a shape before confidence reaches 1.0
NICHE_LIFT_SPAN = 0.6       # a lift this far from parity earns the full NICHE_MAX
NICHE_MIN_CONF = 0.25       # below this a shape is reported but not called for or against


def load_profile(path):
    """Read a niche_calibrate profile. Keeps EVERY measured shape, with a
    confidence derived from how many videos actually used it, so thin evidence
    stays weak without being thrown away."""
    with open(path, encoding="utf-8") as fh:
        prof = json.load(fh)
    built = prof.get("built_from", {}) or {}
    videos = built.get("videos") or 0
    rest = max(0, videos - (built.get("winners") or 0))
    confident = prof.get("confident")

    hooks = {}
    for h in prof.get("hooks", []):
        name, lift = h.get("hook"), h.get("lift")
        if not name or lift is None:
            continue
        obs = (h.get("winners_using_it") or 0) + (h.get("rest_rate") or 0.0) * rest
        conf = min(1.0, obs / NICHE_FULL_EVIDENCE)
        if confident is False:
            conf *= 0.5
        hooks[name] = {"lift": float(lift), "conf": conf,
                       "winners": h.get("winners_using_it") or 0,
                       "observations": round(obs, 1),
                       "recommended": bool(h.get("recommend"))}

    return {
        "path": str(path), "videos": videos, "confident": confident, "hooks": hooks,
        "rewards": sorted(n for n, v in hooks.items()
                          if v["lift"] > 1 and v["conf"] >= NICHE_MIN_CONF),
        "punishes": sorted(n for n, v in hooks.items()
                           if v["lift"] < 1 and v["conf"] >= NICHE_MIN_CONF),
        "using": sorted(hooks),
    }


def shape_verdict(hooks, text):
    """The most decisive measured shape `text` opens with, or None.

    Decisiveness is conf * |lift - 1|, so a shape measured often and far from
    parity beats one measured rarely or sitting at parity. Returns
    (name, lift, conf, points); points are negative for a shape the niche
    punishes, which is the half that used to be discarded."""
    if not hooks or not text:
        return None
    best = None
    for name, v in hooks.items():
        if not match_hook(name, text):
            continue
        decisive = v["conf"] * abs(v["lift"] - 1.0)
        if best is None or decisive > best[0]:
            best = (decisive, name, v)
    if best is None:
        return None
    _, name, v = best
    span = max(-NICHE_LIFT_SPAN, min(NICHE_LIFT_SPAN, v["lift"] - 1.0))
    return name, v["lift"], v["conf"], NICHE_MAX * v["conf"] * (span / NICHE_LIFT_SPAN)


STOP = set("""a an the and or but if to of in on at for with from by is are was were be been being
this that these those it its as not no so than then there here we you your our their his their they
them i me my mine he they his theirs what how why when who which do does did can could should would
will shall may might must have has had about into over under more most very just also only own same
too s t re ve ll d m o y""".split())

MIN_SAMPLE = 25          # below this, report but do not recommend
MIN_PER_BUCKET = 6       # a hook shape needs this many winners before it counts


def load(paths):
    rows, queries = [], []
    for p in paths:
        data = json.loads(Path(p).read_text())
        for block in data:
            queries.append(block.get("query", "?"))
            for r in block.get("results", []):
                if r.get("views") is None or not r.get("title"):
                    continue
                rows.append(r)
    # the same video can be returned by several queries
    seen, uniq = set(), []
    for r in rows:
        k = r.get("id") or r["title"]
        if k not in seen:
            seen.add(k); uniq.append(r)
    return uniq, queries


# Titles that are mostly hashtags, or that announce themselves as comedy, are
# entertainment riding a keyword. They win on views and teach a clipper nothing.
# Found by running this on a real niche: the top result for "couples in business"
# was a 48,000,000 view comedy short tagged #funny #comedy #couple #shorts.
NOISE = re.compile(r"#(funny|comedy|skit|prank|meme|viral|trending|fyp|shorts?|explore|dailyvlog|minivlog)",
                   re.I)


def is_noise(row):
    t = row.get("title", "")
    tags = len(re.findall(r"#\w+", t))
    words = len(re.findall(r"[A-Za-z']+", re.sub(r"#\w+", " ", t)))
    # three or more hashtags and barely any sentence left, or an explicit comedy tag
    return bool(NOISE.search(t)) or (tags >= 3 and words <= 6)


def winners_and_rest(rows):
    """Top quartile by views WITHIN each format, after dropping entertainment.

    Three mistakes this avoids, all of them found on real data rather than
    reasoned about:

    1. A short and a sixteen minute video do not share a view scale. Ranking them
       together means shorts fill the winners list by format alone, and the
       profile then tells a clipper to imitate a format it was not asked about.
    2. Comedy and hashtag spam outrank every piece of actual teaching in this
       niche. Calibrating on them produces a kit that recommends making skits.
    3. A quartile of a mixed pile is not a quartile of anything.
    """
    clean = [r for r in rows if not is_noise(r)]
    win, rest = [], []
    for fmt in ("short", "long"):
        bucket = sorted((r for r in clean if r.get("format") == fmt),
                        key=lambda r: r["views"], reverse=True)
        if not bucket:
            continue
        cut = max(1, len(bucket) // 4)
        win += bucket[:cut]
        rest += bucket[cut:]
    return win, rest


def hook_rates(rows):
    n = max(1, len(rows))
    out = {}
    for name in HOOKS:
        # match_hook, not the raw pattern, so the rate measured here and the
        # shape pick_pulls looks for in speech are the same question asked twice.
        hits = sum(1 for r in rows if match_hook(name, r["title"]))
        out[name] = {"count": hits, "rate": hits / n}
    return out


def median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2


def over_represented(win, rest, queries, top=12):
    """Words commoner among winners than among everything else. Log ratio with
    add-one smoothing, so one freak title cannot invent a trend."""
    def counts(rows):
        """Counts words, and refuses proper nouns. A single French podcast episode
        put philippe, paola, edith and leticia at the top of the first run of this,
        because names repeat inside one title and nothing was filtering them."""
        c, docs = Counter(), Counter()
        for r in rows:
            title = r["title"]
            # a word capitalised away from the start of the title is almost always a name
            proper = {m.group(0).lower() for m in re.finditer(r"(?<=[a-z,] )[A-Z][a-z]{2,}", title)}
            words = {w for w in re.findall(r"[a-z']+", title.lower())
                     if len(w) > 2 and w not in STOP and w not in proper}
            for w in words:
                docs[w] += 1          # count each word once per video, not per mention
        return docs

    # Words from the search terms appear in nearly every result because that is
    # how the results were found. Counting them as a finding is circular, and the
    # first run of this proudly reported "business" and "couple" for the queries
    # "couples in business together" and "entrepreneur couple".
    asked = {w for q in queries for w in re.findall(r"[a-z']+", q.lower()) if len(w) > 2}
    cw, cr = counts(win), counts(rest)
    for w in asked:
        cw.pop(w, None); cr.pop(w, None)
    tw, tr = max(1, sum(cw.values())), max(1, sum(cr.values()))
    scored = []
    for w, n in cw.items():
        if n < 3:            # must appear in three separate winning videos
            continue
        lift = math.log(((n + 1) / tw) / (((cr.get(w, 0)) + 1) / tr))
        scored.append((round(lift, 2), n, w))
    scored.sort(reverse=True)
    return [{"word": w, "in_winners": n, "lift": l} for l, n, w in scored[:top]]


def build(rows, queries):
    win, rest = winners_and_rest(rows)
    wr, rr = hook_rates(win), hook_rates(rest)
    hooks = []
    for name in HOOKS:
        w, r = wr[name], rr[name]
        lift = (w["rate"] + 0.01) / (r["rate"] + 0.01)
        hooks.append({
            "hook": name,
            "winners_using_it": w["count"],
            "winner_rate": round(w["rate"], 3),
            "rest_rate": round(r["rate"], 3),
            "lift": round(lift, 2),
            # a shape only earns a recommendation if enough winners actually use it
            "recommend": bool(w["count"] >= MIN_PER_BUCKET and lift >= 1.25),
        })
    hooks.sort(key=lambda h: -h["lift"])

    dropped = [r for r in rows if is_noise(r)]
    shorts = [r for r in rows if r.get("format") == "short"]
    win_dur = [r.get("duration_s") for r in win if r.get("format") != "short"]
    all_dur = [r.get("duration_s") for r in rows if r.get("format") != "short"]
    win_short_dur = [r.get("duration_s") for r in win if r.get("format") == "short"]

    return {
        "built_from": {"queries": sorted(set(queries)), "videos": len(rows),
                       "winners": len(win), "dropped_as_entertainment": len(dropped),
                       "cut": "top quartile by views, within each format, after dropping entertainment"},
        "confident": len(rows) >= MIN_SAMPLE,
        "caveat": ("Titles, view counts and durations only. Nothing here knows retention, "
                   "thumbnails, posting time, or how big the channel already was. "
                   "Treat it as a direction, never as a prediction."),
        "views": {"median_all": median([r["views"] for r in rows]),
                  "median_winners": median([r["views"] for r in win])},
        "duration_seconds": {"median_winning_longform": median(win_dur),
                             "median_winning_short": median(win_short_dur),
                             "median_all_longform": median(all_dur),
                             "shorts_in_sample": len(shorts)},
        "hooks": hooks,
        "words_that_travel": over_represented(win, rest, queries),
    }


def report(p):
    b = p["built_from"]
    print("\n%d videos across %d queries, %d winners (%s)" %
          (b["videos"], len(b["queries"]), b["winners"], b["cut"]))
    if not p["confident"]:
        print("  THIN SAMPLE, under %d videos. Read this as a hint." % MIN_SAMPLE)
    v = p["views"]
    print("  median views  all %s   winners %s" % (v["median_all"], v["median_winners"]))
    print("  dropped as entertainment: %d" % b["dropped_as_entertainment"])
    d = p["duration_seconds"]
    def secs(v):
        return ("%ss" % int(v)) if v else "not reported"
    print("  median length  winning short %s   winning long %s   (%d shorts in sample)"
          % (secs(d["median_winning_short"]), secs(d["median_winning_longform"]),
             d["shorts_in_sample"]))
    print("\n  HOOK SHAPES, winners against the rest")
    for h in p["hooks"]:
        flag = "USE" if h["recommend"] else "   "
        print("    %s %-13s %2d winners  %.0f%% vs %.0f%%  lift %.2f"
              % (flag, h["hook"], h["winners_using_it"],
                 h["winner_rate"] * 100, h["rest_rate"] * 100, h["lift"]))
    wt = p["words_that_travel"]
    print("\n  WORDS THAT TRAVEL, excluding the search terms themselves: " +
          (", ".join("%s(%d)" % (w["word"], w["in_winners"]) for w in wt) if wt
           else "none appeared in three or more winners"))
    use = [h["hook"] for h in p["hooks"] if h["recommend"]]
    shape = " or ".join(use) if use else "nothing in this sample supports a shape"
    length = ("short form near %ss" % int(d["median_winning_short"])
              if d["median_winning_short"] else
              "YouTube does not report Shorts durations, so length is unmeasured here")
    print("\n  So: open like %s. And %s.\n" % (shape, length))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("research", nargs="+", help="yt_probe.py JSON output")
    ap.add_argument("--out", help="write the profile here")
    a = ap.parse_args()
    rows, queries = load(a.research)
    if not rows:
        sys.exit("no usable rows: every result lacked a view count or a title")
    profile = build(rows, queries)
    report(profile)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(profile, indent=1, ensure_ascii=False))
        print("  wrote %s" % a.out)


if __name__ == "__main__":
    main()
