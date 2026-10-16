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

THE MIS-HEARD WORD, added 2026-10-15 after it got through. Every check in here is
structural, so a sentence can pass all of them while containing a word the
transcriber invented. It happened on the first real run: a clip reading "when
you're outside of home U of Stasis" came back NOTHING FOUND WRONG, because that
sentence opens cleanly, finishes, and carries a turn. The speaker said
homeostasis.

So `garble.py` reads the whole transcript, finds the places it spells the same
word two different ways, and this flags any clip sitting on one of them. It is
serious rather than fatal: the moment is usually still the right moment, and what
it needs is a person fixing one word, not the clip thrown away.

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

import garble

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
#
# The second group was added 2026-10-15 after the first end to end run on real
# tape. Twenty nine minutes of a live class produced six moments and this file
# passed all six, while one of them contained "Thank you for listening. If you
# made it through this whole video, sorry for the double look, I just thought it
# would be best to record two versions of this." Four separate tells that the clip
# is a piece of something longer, and none of them matched.
#
# The lesson is the obvious one: the first list was written by imagining what a
# speaker might say. The second was written by reading what one actually said.
INTERNAL_REFERENCE = re.compile(
    r"\b(as i (said|mentioned)|like i said|earlier|a minute ago|before the break|"
    r"back to|going back|as we discussed|in the last (episode|video|part)|"
    r"we talked about|i told you|coming up|in a (second|minute|moment)|stay tuned|"
    r"next (week|episode|time)|last (week|episode|time)"
    # session furniture: the speaker talking about the recording or the session
    r"|thank(s| you) for (listening|watching|joining)|if you made it (through|this far)"
    r"|this (whole |entire )?(video|recording|session|call|class|training)"
    r"|record(ing|ed)? (two|2|another|a second) version"
    r"|we('re| are) (closing out|wrapping up|out of time|almost done)"
    r"|i(''|')?ll leave you with|leave you with this"
    r"|welcome (to|back to) (week|day|session|part|module)"
    r"|\bworkbooks?\b|\bworksheets?\b|\bhandouts?\b|the slides"
    r"|lock in with me|stick with me|stay with me|follow along"
    r"|as we go through (this|it)|let'?s dive (in|into)"
    r"|last (session|class|call)|next (session|class|call)"
    r"|that(''|')?s your homework|for homework"
    r"|see you (next|then)|before we (go|finish|wrap)"
    r")\b", re.I)

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

# A placeholder the speaker says out loud while teaching: "came from XYZ background", "but
# Bella, XYZ, XYZ, no". It stands in for an example they did not bother to invent, which is fine
# in a room and unreadable in a caption. Measured over 708 sentences from five transcripts: 3
# hits, all three genuine, no false positives. Narrow on purpose. The looser idea this replaced,
# flagging a sentence that ends on a dangling verb or preposition, was measured on the same 708
# and threw 27 hits that were almost all ordinary English ("the world needs you to", "it is what
# it is"), so it was not added. A check that cries wolf gets switched off.
PLACEHOLDER = re.compile(r"\b(x\.?\s?y\.?\s?z|blah\s*blah|yada\s*yada|dot\s+dot\s+dot|"
                         r"so\s+on\s+and\s+so\s+forth|insert\s+\w+\s+here)\b", re.I)

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


def check(sents, seconds=None, suspects=None):
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
    # "that" and "so" end sentences perfectly well: "Nobody understands that.", "I think so."
    # Stripping the full stop and then seeing a trailing "that" flagged 26 of 643 real
    # sentences across four transcripts, every one of them finished, and nothing genuine. So
    # when the speaker put a full stop there, those two are allowed; the rest of the list
    # cannot close a sentence whatever punctuation follows.
    finished = bool(re.search(r"[.!?]$", last))
    stem = last.rstrip(".!?")
    cut_off = bool(UNFINISHED_TAIL.search(stem)) and not (
        finished and re.search(r"\b(that|so)\s*$", stem, re.I))
    if cut_off or not finished:
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
    # --- the words themselves --------------------------------------------
    for sent in sents:
        m = PLACEHOLDER.search(sent)
        if m:
            faults.append({"fault": "says a placeholder out loud", "severity": "serious",
                           "why": "%r stands in for an example that was never given. It passes "
                                  "in a live room and reads as a mistake in a caption"
                                  % m.group(0),
                           "evidence": sent[:110]})
            break


    # Structural checks cannot hear a wrong word. These come from garble.py, which found them
    # by catching the transcript spelling the same word two different ways.
    by_word = {}
    for sus in (suspects or []):
        if sus["heard"].lower() in body.lower():
            by_word.setdefault(sus["probably"], []).append(sus)
    for right, group in sorted(by_word.items()):
        heard = sorted({g["heard"] for g in group})
        faults.append({"fault": "may contain a mis-heard word", "severity": "serious",
                       "why": "the transcript writes %s here and %r %d time(s) elsewhere, so "
                              "one of them is wrong. Check the tape and fix the word before "
                              "this becomes a caption"
                              % (" and ".join(repr(h) for h in heard), right,
                                 group[0]["used_elsewhere"]),
                       "evidence": heard[0]})

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
        return ([s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()], secs,
                data.get("source"))
    cues = parse_srt(raw)
    secs = None
    timed = [c for c in cues if c["start"] is not None]
    if timed:
        secs = timed[-1]["end"] - timed[0]["start"]
    return sentences(cues), secs, str(p)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clip", help="an SRT of one clip, or a pick_pulls.py JSON")
    ap.add_argument("--pull", type=int, help="which pull from a JSON, 1 based")
    ap.add_argument("--json", action="store_true", help="machine readable")
    ap.add_argument("--transcript", help="the full transcript, for the mis-heard word check. "
                                         "A pick_pulls JSON names its own, so this is only "
                                         "needed when checking a bare SRT of one clip")
    ap.add_argument("--no-word-check", action="store_true",
                    help="skip the mis-heard word check")
    a = ap.parse_args()

    sents, secs, source = load(a.clip, a.pull)

    # The mis-heard word check needs the WHOLE transcript, because the signal is the tape
    # contradicting itself. One clip in isolation has nothing to contradict.
    suspects, word_check = [], None
    full = a.transcript or source
    if not a.no_word_check and full and Path(full).is_file():
        suspects = garble.find(garble.words_with_times(full))
        word_check = full
    faults, notes = check(sents, secs, suspects)
    if not a.no_word_check and not word_check:
        notes.append("no transcript to check the words against, so a mis-heard word would not "
                     "be caught here. Pass --transcript to turn that check on")
    word, code = verdict(faults)

    if a.json:
        print(json.dumps({"verdict": word, "faults": faults, "notes": notes,
                          "sentences": len(sents), "seconds": secs,
                          "word_check": word_check}, indent=1))
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
