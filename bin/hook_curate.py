#!/usr/bin/env python3
"""hook_curate.py: choose the hook card, out of the speaker's own words.

WHY THIS EXISTS. `plan_clips.py` fills the pinned hook card with
`first_sentence(seed["text"])`: the opener's first sentence, cut to twelve words,
with an ellipsis stuck on the end if it overran. It then apologises for it in the
piece's own problems list:

    The pinned hook card is the transcript's own words, trimmed. Tighten it by
    hand: a hook card is read with the sound off.

So the one frame that decides whether anybody watches was a mechanical truncation,
and the tool told you to go and fix it yourself. The owner's verdict on the
output was "you just added captions can you add visuals can you make it
interesting". This is the type half of that.

WHAT IT DOES NOT DO, and this is the whole design. **It writes nothing.** Every
card it proposes is a contiguous run of the speaker's own words, in their order,
taken from the opening segment. That is the same contract `caption_repair.py`
holds: "This script invents no wording." A hook card that paraphrases is a claim
the speaker never made, pinned to the top of the frame for four seconds, and no
amount of better copy is a good enough reason to put words in somebody's mouth.

So this CHOOSES. Twelve words truncated mid-clause and seven words that finish a
thought are both in the transcript. Only one of them reads with the sound off.

HOW IT CHOOSES. Candidates are whole sentences and clause spans from the opening
segment. Each is judged on signals the kit already computes:

  pick_pulls.analyse_sentence   numbers, you, contrast, filler, question, ack
  pick_pulls.OPENER_BAD         opens on a connective that points backwards
  pick_pulls.stands_as_question a connective opener that still works as a question
  clip_sense.check              refuses anything with a SERIOUS fault, so a card
                                cannot refer to the rest of the recording

Brevity is scored, because a card is glanced at rather than read. A question
scores well, a number scores well, "you" scores well, filler is punished, and
anything that opens on a pronoun is refused outright, because "That is the part
nobody tells you" names nothing when it is the first thing on screen.

IT REFUSES. If no span qualifies, it says so, leaves the existing card alone and
records why in the piece's problems. A weak card chosen silently is worse than a
truncation somebody has been told to go and fix.
"""

import argparse
import json
import re
import sys
from pathlib import Path

import clip_sense
import pick_pulls as pp

# A card is read in a glance, with the sound off, usually at arm's length. Seven
# words is the target and nine is the ceiling. The old truncation allowed twelve,
# which is a sentence rather than a card.
TARGET_WORDS = 7
MAX_WORDS = 9
MIN_WORDS = 3

# A card opening on one of these names nothing. Mid clip a pronoun can point at the
# previous line; on the first frame there is no previous line.
# PARITY IS THE RULE HERE. This list carried "her" and not "his", so a card opening
# "Her team doubled the price" was refused and "His team doubled the price" was chosen,
# on the one frame that decides whether anybody watches. It also missed "their" and
# "theirs", which is the same bug again now the kit says "they" for the speaker. The set
# below is clip_sense.ORPHAN_PRONOUN's, plus "its". kit_check 6e holds it to parity.
PRONOUN_OPEN = re.compile(
    r"^[\"'“‘(]*(?:its|it|that|this|these|those|theirs|their|they|them|"
    r"he|she|him|hers|her|his|there|then|which|who)\b", re.I)

# Faults clip_sense raises that are still faults when the text is one card. The ones
# left out are about a CLIP: "no turn", "nothing at stake", "too few sentences" and
# "opening sentence is long" cannot be satisfied by a card and are not its job.
CARD_FAULTS = {
    "empty",
    # "ends mid sentence" is deliberately NOT here. A card is a line on screen rather
    # than a sentence, and "If you cannot name those three hours" works as one. Having
    # it in this set refused every clause that lacked a full stop, which left only
    # whole sentences and tail fragments that happened to end on one: on the fixture it
    # refused that candidate and kept "you have a second worry." instead. The genuinely
    # broken endings, a card trailing off on "of" or "the", are caught by DANGLING_END.
    "ends on filler",
    "may contain a mis-heard word",
    "opens mid argument",
    "opens on a dangling connective",
    "opens on an unresolved pronoun",
    "opens on filler",
    "refers to the rest of the recording",
    "says a placeholder out loud",
}

CLAUSE_SPLIT = re.compile(r"\s*[,;:\u2014]\s*|\s+(?:and|but|so|because|or)\s+", re.I)
TRAILING_JUNK = re.compile(r"[\s,;:\u2014-]+$")
# A card may not end on a word that is still reaching for the next one.
DANGLING_END = re.compile(
    r"\b(?:a|an|the|my|your|our|their|his|its|of|to|for|with|in|on|at|by|from|as|"
    r"and|but|or|so|because|that|which|is|are|was|were|be|been|being|do|does|did|"
    r"have|has|had|will|would|can|could|should|than|then|if|when|what)$", re.I)


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.?!])\s+", (text or "").strip()) if s.strip()]


def candidates(text):
    """Contiguous runs of the speaker's own words, in their order. Nothing reordered.

    Each comes back with whether it STARTS A SENTENCE, which is scored below. A span
    taken from the middle of a sentence usually leans on the words before it, and on a
    card there are no words before it. On the two piece fixture the first version of
    this picked "you have a second worry." over "If you cannot name those three hours",
    and the one it picked is the back half of "you do not have a second offer, you have
    a second worry". Alone it asserts something slightly odd, and nothing else in this
    file catches that: it opens on "you" and ends on a full stop, both fine.
    """
    out = []
    for sent in sentences(text)[:3]:
        out.append((sent, True))
        parts = [p for p in CLAUSE_SPLIT.split(sent) if p and p.strip()]
        for i, part in enumerate(parts):
            out.append((part, i == 0))
        # Leading spans that stop at a clause boundary, so a long opener can still
        # give up a short card without being cut mid thought. These all start the
        # sentence by construction.
        run = ""
        for part in parts:
            run = (run + " " + part).strip() if run else part
            out.append((run, True))
    seen, uniq = set(), []
    for c, starts in out:
        c = TRAILING_JUNK.sub("", c.strip())
        if not c:
            continue
        key = c.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append((c, starts))
    return uniq


def judge(card, max_words=MAX_WORDS, starts_sentence=True):
    """Score a candidate, or refuse it with a reason. Higher is better."""
    words = card.split()
    n = len(words)
    if n < MIN_WORDS:
        return None, "only %d word(s)" % n
    if n > max_words:
        return None, ("%d words, and the ceiling for a card is %d. Raise it with "
                      "--max-words if you want longer cards" % (n, max_words))
    if PRONOUN_OPEN.match(card):
        return None, 'opens on "%s", which names nothing on the first frame' % words[0]
    if DANGLING_END.search(card):
        return None, 'ends on "%s", so the thought is still reaching' % words[-1]

    s = pp.analyse_sentence({"text": card})
    if s["is_ack"]:
        return None, "it is an acknowledgement rather than a statement"
    if s["filler"]:
        return None, "it carries filler"
    if pp.OPENER_BAD.match(card) and not pp.stands_as_question(card):
        return None, 'opens on "%s", which points back at unheard words' % words[0]

    # The kit's own sense check, filtered to the faults that mean something about a
    # CARD. clip_sense judges a CLIP, and a clip has to carry a turn and more than one
    # sentence. A five word card has neither by definition, so the first version of
    # this refused every candidate it was given, including "So what do you actually
    # want?" over "too few sentences". The faults below are the ones that are still
    # true of one line on screen.
    faults, _ = clip_sense.check([card])
    grave = [f for f in faults
             if f["severity"] in ("serious", "fatal") and f["fault"] in CARD_FAULTS]
    if grave:
        return None, "the sense check calls it %s" % grave[0]["fault"]

    score = 0.0
    if s["is_question"]:
        score += 8
    if s["numbers"]:
        score += 6
    if s["you"]:
        score += 3
    if s["contrast"]:
        score += 3
    if s["names"]:
        score += 1
    # Brevity, scored rather than merely capped. A card is glanced at.
    score += max(0.0, (TARGET_WORDS - abs(n - TARGET_WORDS))) * 1.2
    if card.rstrip().endswith((".", "?", "!")):
        score += 2                      # it finishes, rather than stopping
    if starts_sentence:
        score += 5                      # see candidates(): a mid sentence span leans back
    return score, "%d words%s%s%s%s%s" % (
        n,
        ", a question" if s["is_question"] else "",
        ", names a number" if s["numbers"] else "",
        ", speaks to you" if s["you"] else "",
        ", carries a contrast" if s["contrast"] else "",
        "" if starts_sentence else ", and it starts mid sentence")


def curate(text, max_words=MAX_WORDS):
    """The best card from this text, or None and every reason it found."""
    best, best_score, best_why, refused = None, None, "", []
    for c, starts in candidates(text):
        score, why = judge(c, max_words, starts)
        if score is None:
            refused.append((c, why))
            continue
        if best_score is None or score > best_score:
            best, best_score, best_why = c, score, why
    return best, best_score, best_why, refused


def main():
    ap = argparse.ArgumentParser(
        description="Choose each piece's hook card from the speaker's own words.")
    ap.add_argument("cuts", help="a plan_clips.py cut list (cuts.json)")
    ap.add_argument("--write", action="store_true",
                    help="update the cut list in place. Without it, nothing is changed")
    ap.add_argument("--out", help="write the updated cut list here instead of in place")
    ap.add_argument("--max-words", type=int, default=MAX_WORDS,
                    help="the ceiling for a card (default %d). A card is glanced at with "
                         "the sound off, so shorter wins" % MAX_WORDS)
    ap.add_argument("--json", action="store_true", dest="as_json", help="machine readable")
    a = ap.parse_args()
    if a.max_words < MIN_WORDS:
        sys.exit("--max-words has to be at least %d" % MIN_WORDS)

    path = Path(a.cuts)
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    pieces = data.get("pieces") or data.get("clips") or []
    if not pieces:
        sys.exit("no pieces in %s" % a.cuts)

    results = []
    for piece in pieces:
        segs = piece.get("segments") or []
        opener = (segs[0].get("text") if segs else "") or ""
        was = ((piece.get("hook") or {}).get("text") or "").strip()
        card, score, why, refused = curate(opener, a.max_words)
        results.append({"piece": piece.get("piece"), "filename": piece.get("filename"),
                        "was": was, "now": card, "score": score, "why": why,
                        "refused": len(refused),
                        "first_refusals": [{"card": c, "why": w} for c, w in refused[:3]]})
        if card and a.write:
            piece.setdefault("hook", {})["text"] = card
        elif not card and a.write:
            piece.setdefault("problems", []).append(
                "no hook card could be cut from this opener out of the speaker's own "
                "words inside %d words. The card is still the trimmed transcript. "
                "Shorten the opener by hand, raise --max-words, or pick a different "
                "moment." % a.max_words)

    if a.write:
        out = Path(a.out) if a.out else path
        out.write_text(json.dumps(data, indent=1) + "\n")

    if a.as_json:
        print(json.dumps({"cuts": str(path), "pieces": results}, indent=1))
        return 0

    for r in results:
        print()
        print("  %s  %s" % (r["piece"], r["filename"] or ""))
        print("    was:  %s" % (r["was"] or "(none)"))
        if r["now"]:
            print("    now:  %s" % r["now"])
            print("    why:  %s" % r["why"])
        else:
            print("    now:  REFUSED, the card is unchanged")
            for f in r["first_refusals"]:
                print("          %r: %s" % (f["card"][:48], f["why"]))
    kept = sum(1 for r in results if r["now"])
    print()
    print("  %d of %d piece(s) got a card chosen from the speaker's own words."
          % (kept, len(results)))
    if not a.write:
        print("  Nothing was changed. Pass --write to update the cut list.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
