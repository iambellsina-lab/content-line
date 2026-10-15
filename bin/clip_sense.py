#!/usr/bin/env python3
"""clip_sense.py: would this clip make sense to somebody who heard none of the rest?

WHY THIS EXISTS. `caption_check.py` reads the captions the way a stranger scrolling
past would. `hear_joins.py` plays the cuts so a person hears them. Both check
craft, and a clip can pass both while being incomprehensible, because the thing
neither of them asks is whether the thirty seconds stands up alone.

That is the failure of every automatic clipper: it finds a moment with good energy
in the middle of an argument, cuts it out, and ships something that opens "and
that's exactly why I stopped doing it" about a thing nobody watching has heard of.

WHAT IT CAN AND CANNOT KNOW. It reads words. It cannot hear tone, see a face, or
know that a pause carried the joke. So it reports faults it can point at, each
quoting the sentence that caused it, and it never claims a clip is good. The
strongest thing it says is that it found nothing wrong, which is a different and
much weaker claim.

It must be able to fail a clip that every other check passes. A tool that only
agrees with the other tools is decoration.

Usage:
    python3 bin/clip_sense.py clip.srt
    python3 bin/clip_sense.py pulls.json --pull 2
    python3 bin/clip_sense.py clip.srt --json
"""
import argparse
import json
import re
import sys
from pathlib import Path

# A clip that opens on one of these MAY be answering something the viewer never
# heard. Only may: a connective on its own proves nothing.
#
# The first version of this rule was too blunt and the test caught it. pick_pulls
# ranked "So what was the moment you knew something had to change?" as the best
# moment in a real transcript, score 91.2, and this file rejected it outright for
# starting with "So". That sentence is entirely self-contained. Spoken English
# begins half its sentences with a connective and means nothing by it.
#
# What actually signals a mid-argument cut is a connective followed by something
# that cannot stand up alone: "and that's exactly why", "so anyway", "but it was".
# So the connective is stripped and what remains is judged on its own.
SOFT_CONNECTIVE = re.compile(
    r"^\s*(so|and|but|because|anyway|anyways|also|plus|however|therefore|thus|then|"
    r"again|now|well|right|okay|ok)\b[,\s]*", re.I)

# These are continuations whatever follows them. There is no self-contained
# sentence that starts "that's exactly why".
HARD_CONTINUATION = re.compile(
    r"^\s*(and |so |but )?(that'?s (exactly )?(why|what|how|when|where)|"
    r"which is why|that is why|this is why|which means|that means|"
    r"it'?s (exactly )?(why|what)|hence|ergo)\b", re.I)

# A pronoun with nothing before it to point at. "They never tell you that" opens on
# a they the viewer cannot resolve, and the clip is about a group nobody named.
ORPHAN_PRONOUN = re.compile(
    r"^\s*(he|she|it|they|them|him|her|his|hers|their|theirs|this|that|these|those|"
    r"one|both|such)\b", re.I)

# Things that only mean something inside the full recording.
INTERNAL_REFERENCE = re.compile(
    r"\b(as i (said|mentioned)|like i said|earlier|a minute ago|before the break|"
    r"back to|going back|as we discussed|in the last (episode|video|part)|"
    r"we talked about|i told you|coming up|in a (second|minute|moment)|stay tuned|"
    r"next (week|episode|time)|last (week|episode|time))\b", re.I)

# A clip wants a turn in it: a moment where the thought changes direction. Without
# one it is a statement held for forty seconds, and nobody stays.
TURN = re.compile(
    r"\b(but|however|except|instead|actually|turns out|the problem is|here'?s the thing|"
    r"until|then one day|and then|the truth is|what changed|what nobody|"  # slop-lint: allow
    r"most people|everyone thinks|i used to|i thought)\b", re.I)

# Something has to be at risk, or there is no reason to keep watching.
STAKES = re.compile(
    r"\b(cost|lost|lose|losing|broke|failed|failing|fail|quit|quitting|debt|afraid|"
    r"scared|wrong|mistake|ruin|destroyed|nearly|almost|worst|hardest|hurt|"
    r"resent|divorce|burn(ed|t)? out|rock bottom|gave up)\b", re.I)

# An ending that stops rather than lands.
UNFINISHED_TAIL = re.compile(r"(,|;|:|\band\b|\bbut\b|\bso\b|\bbecause\b|\bwhich\b|\bthat\b)\s*$", re.I)

FILLER_ONLY = re.compile(r"^\s*(um+|uh+|er+|ah+|yeah|right|okay|ok|so|well|like|you know)[\s,.]*$", re.I)


def parse_srt(text):
    """Cues out of an SRT. Deliberately forgiving: a transcript from a phone is
    rarely well formed, and refusing to read it helps nobody."""
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [l for l in block.splitlines() if l.strip()]
        if not lines:
            continue
        body = [l for l in lines if "-->" not in l and not re.fullmatch(r"\d+", l.strip())]
        times = [l for l in lines if "-->" in l]
        if not body:
            continue
        start = end = None
        if times:
            m = re.findall(r"(\d+):(\d+):(\d+)[,.](\d+)", times[0])
            if len(m) == 2:
                start, end = [int(h) * 3600 + int(mi) * 60 + int(s) + int(ms) / 1000
                              for h, mi, s, ms in m]
        out.append({"text": " ".join(body).strip(), "start": start, "end": end})
    return out


def sentences(cues):
    joined = " ".join(c["text"] for c in cues)
    joined = re.sub(r"\s+", " ", joined).strip()
    parts = re.split(r"(?<=[.!?])\s+", joined)
    return [p.strip() for p in parts if p.strip()]


def check(sents, seconds=None):
    """Every fault names the sentence that caused it. A fault nobody can point at
    is an opinion."""
    faults, notes = [], []
    if not sents:
        return [{"fault": "empty", "severity": "fatal",
                 "why": "no words in this clip", "evidence": ""}], []

    first, last = sents[0], sents[-1]
    body = " ".join(sents)
    words = re.findall(r"[A-Za-z']+", body)

    # --- the opening ------------------------------------------------------
    if HARD_CONTINUATION.match(first):
        faults.append({"fault": "opens mid argument", "severity": "fatal",
                       "why": "the opening line continues a thought the viewer never heard",
                       "evidence": first[:110]})
    else:
        # strip a conversational connective and judge what is actually left
        stripped = SOFT_CONNECTIVE.sub("", first).strip()
        had_connective = stripped != first.strip()
        stands_alone = bool(re.match(r"^(who|what|why|when|where|how|which|can|could|should|"
                                     r"do|does|did|is|are|was|were|if|most|every|nobody|"
                                     r"everyone|here|there'?s a|the|a|an|my|our|i |we )",
                                     stripped, re.I)) or stripped.endswith("?")
        if ORPHAN_PRONOUN.match(stripped):
            faults.append({"fault": "opens on an unresolved pronoun", "severity": "fatal",
                           "why": "the clip opens pointing at something it never names",
                           "evidence": first[:110]})
        elif had_connective and not stands_alone:
            faults.append({"fault": "opens mid argument", "severity": "serious",
                           "why": "opens on a connective and what follows does not stand up "
                                  "on its own",
                           "evidence": first[:110]})
    if FILLER_ONLY.match(first):
        faults.append({"fault": "opens on filler", "severity": "serious",
                       "why": "the first thing heard carries nothing",
                       "evidence": first[:110]})
    if len(re.findall(r"[A-Za-z']+", first)) > 34:
        faults.append({"fault": "opening sentence is long", "severity": "minor",
                       "why": "%d words before the first full stop" %
                              len(re.findall(r"[A-Za-z']+", first)),
                       "evidence": first[:110]})

    # --- references out of the clip ---------------------------------------
    for s in sents:
        m = INTERNAL_REFERENCE.search(s)
        if m:
            faults.append({"fault": "refers to the rest of the recording",
                           "severity": "serious",
                           "why": '"%s" points at something outside this clip' % m.group(0),
                           "evidence": s[:110]})
            break

    # --- the ending -------------------------------------------------------
    if UNFINISHED_TAIL.search(last.rstrip(".!?")) or not re.search(r"[.!?]$", last):
        faults.append({"fault": "ends mid sentence", "severity": "fatal",
                       "why": "the last line stops rather than finishes",
                       "evidence": last[-110:]})
    if FILLER_ONLY.match(last):
        faults.append({"fault": "ends on filler", "severity": "serious",
                       "why": "the last thing heard carries nothing",
                       "evidence": last[:110]})

    # --- is there a reason to stay ----------------------------------------
    if not TURN.search(body):
        faults.append({"fault": "no turn", "severity": "serious",
                       "why": "nothing in here changes direction, so it is one statement held "
                              "for the whole clip",
                       "evidence": ""})
    if not STAKES.search(body):
        faults.append({"fault": "nothing at stake", "severity": "minor",
                       "why": "no cost, risk or loss is named anywhere in it",
                       "evidence": ""})

    # --- shape ------------------------------------------------------------
    if len(sents) < 3:
        faults.append({"fault": "too few sentences", "severity": "serious",
                       "why": "%d sentence(s): not enough for a thought to develop" % len(sents),
                       "evidence": ""})
    if seconds and len(words) and seconds > 0:
        wpm = len(words) / (seconds / 60.0)
        if wpm < 95:
            notes.append("slow for speech at %d words a minute: check the tape is not mostly silence"
                         % wpm)
        elif wpm > 210:
            notes.append("fast at %d words a minute: check nothing was cut out of the middle" % wpm)
    return faults, notes


def verdict(faults):
    fatal = [f for f in faults if f["severity"] == "fatal"]
    serious = [f for f in faults if f["severity"] == "serious"]
    if fatal:
        return "DO NOT CUT", 2
    if len(serious) >= 2:
        return "NEEDS A HUMAN", 1
    if serious:
        return "USABLE, WITH ONE PROBLEM", 0
    return "NOTHING FOUND WRONG", 0


def load(path, pull):
    p = Path(path)
    raw = p.read_text(encoding="utf-8", errors="replace")
    if p.suffix.lower() == ".json" or raw.lstrip().startswith("{"):
        data = json.loads(raw)
        pulls = data.get("pulls", data if isinstance(data, list) else [])
        if not pulls:
            sys.exit("no pulls in %s" % path)
        idx = (pull - 1) if pull else 0
        if idx >= len(pulls):
            sys.exit("asked for pull %d, file has %d" % (pull, len(pulls)))
        pl = pulls[idx]
        text = pl.get("text") or pl.get("full_text") or pl.get("opening_sentence", "")
        secs = pl.get("duration") or (pl.get("end", 0) - pl.get("start", 0) or None)
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()], secs
    cues = parse_srt(raw)
    secs = None
    timed = [c for c in cues if c["start"] is not None]
    if timed:
        secs = timed[-1]["end"] - timed[0]["start"]
    return sentences(cues), secs


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clip", help="an SRT of one clip, or a pick_pulls.py JSON")
    ap.add_argument("--pull", type=int, help="which pull from a JSON, 1 based")
    ap.add_argument("--json", action="store_true", help="machine readable")
    a = ap.parse_args()

    sents, secs = load(a.clip, a.pull)
    faults, notes = check(sents, secs)
    word, code = verdict(faults)

    if a.json:
        print(json.dumps({"verdict": word, "faults": faults, "notes": notes,
                          "sentences": len(sents), "seconds": secs}, indent=1))
        return code

    print("\n  %s" % word)
    print("  %d sentences%s" % (len(sents), ", %.1fs" % secs if secs else ""))
    if not faults:
        print("\n  Nothing found wrong. That is not the same as good: this reads words, "
              "so it cannot hear tone or see a face.")
    for f in faults:
        print("\n  [%s] %s" % (f["severity"].upper(), f["fault"]))
        print("    %s" % f["why"])
        if f["evidence"]:
            print('    "%s"' % f["evidence"])
    for n in notes:
        print("\n  note: %s" % n)
    print()
    return code


if __name__ == "__main__":
    sys.exit(main())
