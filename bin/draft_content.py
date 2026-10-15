#!/usr/bin/env python3
"""draft_content.py: a caption built from their own words, shaped by what their niche rewards.

WHY THIS EXISTS. `make_clip.py` renders a spec that a human wrote. Nothing wrote
the spec. This does, and it is the last of the gaps in `THE-GAP.md`.

THE RULE IT OBEYS, which is the kit's own: a voice is harvested, never invented.
**This file does not write a single sentence.** Every line in every draft is a
sentence the person already said, lifted from their transcript. What it does is
choose which of their sentences opens, which follow, and which lands, using two
things that were measured rather than guessed:

    brand_voice.py       how they actually write: length, closings, who they
                         address, how often they contract
    niche_calibrate.py   which opening shapes win in their niche, by view count

That boundary is the whole design. Choosing is a job arithmetic can do honestly.
Writing is not, and a kit that invents sentences in somebody's name produces
copy that sounds like every other kit.

WHAT IT CANNOT DO. It cannot make a dull moment interesting, and it will not try.
If the transcript has no sentence that opens well, it says so and names the
closest thing it found. It also reports where the draft drifts from the measured
voice, because the draft is made of their sentences and can still end up longer,
or more formal, than they have ever been.

Usage:
    python3 bin/draft_content.py pulls.json --voice voice.json --niche niche.json
    ... --out drafts/            # write markdown files
    ... --json                   # machine readable
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from niche_calibrate import HOOKS as HOOK_RX
except Exception:
    HOOK_RX = {}
try:
    from clip_sense import check as sense_check, verdict as sense_verdict
except Exception:
    sense_check = None


def words(s):
    return re.findall(r"[A-Za-z']+", s)


def sentences_of(text):
    return [p.strip() for p in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if p.strip()]


def contraction_rate(sents):
    """Same measure brand_voice uses: contractions over chances to contract, so a
    draft and a profile can be compared without converting units."""
    blob = " ".join(sents)
    got = len(re.findall(r"\b\w+'(t|s|re|ve|ll|d|m)\b", blob, re.I))
    chances = got + len(re.findall(
        r"\b(do not|does not|did not|is not|are not|was not|were not|cannot|can not|"
        r"will not|would not|should not|could not|have not|has not|had not|it is|"
        r"that is|there is|they are|we are|you are|i am|i will|we will)\b", blob, re.I))
    return (got / chances) if chances else None, chances


def pick_opener(sents, rewarded):
    """The first line decides whether anything else is read. Prefer a sentence of
    theirs that matches a shape the niche actually rewards; fall back to the
    shortest self-contained one, because short and whole beats clever and partial.
    """
    scored = []
    for i, s in enumerate(sents):
        n = len(words(s))
        if n < 4 or n > 30:
            continue
        # a sentence that opens on a pronoun or a connective cannot lead, because
        # the thing it points at is not on screen
        if re.match(r"^\s*(he|she|it|they|them|this|that|these|those|and|but|so|because|"
                    r"which|anyway|also|then)\b", s, re.I):
            continue
        shape, lift = None, 0.0
        for name, l in rewarded.items():
            if name in HOOK_RX and HOOK_RX[name].search(s):
                if l > lift:
                    shape, lift = name, l
        # earlier sentences are likelier to be the actual start of the thought
        position = 1.0 - (i / max(1, len(sents)))
        scored.append((lift * 3 + position + (1.0 if n <= 14 else 0.0), i, s, shape, lift))
    if not scored:
        return None, None, None, 0.0
    scored.sort(key=lambda r: -r[0])
    _, i, s, shape, lift = scored[0]
    return i, s, shape, lift


def pick_closer(sents, lands_on, used):
    """Match how they actually end a piece. If they land on a statement three
    times in four, a draft that ends on a question is not their voice."""
    want = {
        "question": lambda s: s.rstrip().endswith("?"),
        "command": lambda s: re.match(r"^\s*(go|do|stop|start|write|ask|say|take|look|try|keep|"
                                      r"name|pick|make|tell|read|call|put|get|send)\b", s, re.I),
        "fragment_like": lambda s: not re.search(r"[.!?]$", s.strip()),
        "statement": lambda s: bool(re.search(r"\.$", s.strip())),
    }.get(lands_on, lambda s: True)
    for i in range(len(sents) - 1, -1, -1):
        if i in used:
            continue
        if want(sents[i]) and 3 <= len(words(sents[i])) <= 26:
            return i, sents[i]
    return None, None


def build_draft(pull, voice, rewarded):
    text = pull.get("text") or pull.get("full_text") or ""
    sents = sentences_of(text)
    if len(sents) < 3:
        return None

    sl = voice.get("sentence_length_words", {})
    target_med = sl.get("median") or 12
    per_piece = (voice.get("length_per_piece") or {}).get("words_per_sample", {})
    target_words = per_piece.get("median") or 60
    lands = ((voice.get("closings") or {}).get("classes") or [{}])[0].get("lands_on", "statement")

    oi, opener, shape, lift = pick_opener(sents, rewarded)
    if opener is None:
        return {"pull": pull, "problem": "no sentence in this moment can open a caption",
                "closest": sents[0][:120]}

    # A CONTIGUOUS RUN, STARTING AT THE OPENER. Nothing is reordered.
    #
    # The first version of this picked sentences by how near they were to the
    # person's median length and then sorted them back into index order. Reading
    # the output killed it: a draft came out as "I thought I was busy. So what was
    # the moment you knew something had to change? It was a Tuesday in March. They
    # were reflexes." Every line was theirs and the paragraph meant nothing,
    # because a transcript's sentences depend on the ones before them. "They were
    # reflexes" needs the sentence that says what they were.
    #
    # So the body runs forward from the opener and stops. Lines can be dropped out
    # of the middle when they carry nothing, which is a cut a person makes too, but
    # the order never changes.
    SKIPPABLE = re.compile(r"^\s*(um+|uh+|er+|yeah|right|okay|ok|i mean|you know|sort of|"
                           r"kind of|anyway)\b[\s,]*$", re.I)

    lines, total, used = [opener], len(words(opener)), {oi}
    for i in range(oi + 1, len(sents)):
        s = sents[i]
        n = len(words(s))
        if n < 2 or SKIPPABLE.match(s):
            continue
        if total + n > target_words * 1.35:
            break
        lines.append(s)
        total += n
        used.add(i)

    # a closer only if one of their usual endings is already sitting at the end of
    # the run. Reaching outside the run for a better last line is reordering again.
    closer = None
    if lines and len(lines) > 1:
        ci, cand = pick_closer(lines[-3:], lands, set())
        closer = cand if cand == lines[-1] else None
    if closer is None and len(lines) > 2:
        # trim a trailing line that ends mid thought rather than inventing an end
        while len(lines) > 2 and not re.search(r"[.!?]$", lines[-1].strip()):
            total -= len(words(lines.pop()))
    why = []
    if shape:
        why.append("opener matches the %s shape, which wins %.2fx more often in this niche"
                   % (shape, lift))
    else:
        why.append("no sentence here matched a shape the niche rewards, so the opener is the "
                   "shortest one of theirs that stands up alone")
    why.append("kept to about %d words because their pieces run %d words at the median"
               % (total, target_words))
    ends_right = bool(closer)
    why.append("their sentences in the order they said them, from the opener forward, "
               "because a transcript's lines depend on the ones before them")
    why.append("ends on a %s, which is how %d%% of their pieces end"
               % (lands, round(100 * ((voice.get("closings") or {}).get("classes") or [{}])[0]
                               .get("rate", 0)))
               if ends_right else
               "the run does not end the way their pieces usually do, so the last line is "
               "theirs but the ending is yours to write")
    # The source moment already has two opinions attached to it and this tool was
    # ignoring both. pick_pulls scored it, and clip_sense can read it. A draft
    # made of filler is still filler, and presenting it beside a good one as if
    # they were peers is how a kit launders a bad moment into a post.
    source = []
    score = pull.get("score")
    if score is not None and score < 35:
        source.append("the moment it came from scored %.1f, which pick_pulls calls weak" % score)
    filler = sum(1 for l in lines if re.search(
        r"\b(you know|i mean|like,|sort of|kind of|at the end of the day|"  # slop-lint: allow
        r"it is what it is|trust the process|believe in yourself)\b", l, re.I))
    if filler >= 2:
        source.append("%d of %d lines lean on filler phrases" % (filler, len(lines)))

    return {"pull": pull, "lines": lines, "why": why, "words": total,
            "opener_shape": shape, "opener_lift": lift, "source_doubts": source}


def drift(draft, voice):
    """Where the draft parts company with the measured voice. It is made of their
    sentences and can still come out longer or stiffer than they have ever been,
    because selection changes a distribution."""
    out = []
    sents = draft["lines"]
    sl = voice.get("sentence_length_words", {})
    lens = sorted(len(words(s)) for s in sents)
    med = lens[len(lens) // 2] if lens else 0
    lo, hi = sl.get("p25"), sl.get("p75")
    if lo and hi and not (lo <= med <= hi):
        out.append("sentences run %d words at the median; theirs sit between %g and %g"
                   % (med, lo, hi))
    r, chances = contraction_rate(sents)
    vr = (voice.get("contractions") or {}).get("rate_when_possible")
    if r is not None and vr is not None and chances >= 3 and abs(r - vr) > 0.3:
        out.append("contracts %d%% of the time against their usual %d%%"
                   % (round(r * 100), round(vr * 100)))
    qr = sum(1 for s in sents if s.rstrip().endswith("?")) / max(1, len(sents))
    vq = (voice.get("punctuation") or {}).get("question_rate")
    if vq is not None and qr - vq > 0.25:
        out.append("asks questions in %d%% of lines against their usual %d%%"
                   % (round(qr * 100), round(vq * 100)))
    return out


def render(d, voice, n):
    if "problem" in d:
        return ("\n  %d. SKIPPED: %s\n     closest thing in it: \"%s\"\n"
                % (n, d["problem"], d["closest"]))
    body = "\n".join("     " + l for l in d["lines"])
    head = "DRAFT"
    if d.get("source_doubts"):
        head = "DRAFT FROM A WEAK MOMENT"
    s = "\n  %d. %s, %d words\n\n%s\n" % (n, head, d["words"], body)
    if d.get("source_doubts"):
        s += "\n     this one is probably not here to be posted\n"
        for x in d["source_doubts"]:
            s += "       - %s\n" % x
    s += "\n     why it is shaped this way\n"
    for w in d["why"]:
        s += "       - %s\n" % w
    dr = drift(d, voice)
    if dr:
        s += "\n     where it drifts from their measured voice\n"
        for x in dr:
            s += "       - %s\n" % x
    if sense_check:
        faults, _ = sense_check(d["lines"])
        word, _ = sense_verdict(faults)
        s += "\n     sense check: %s" % word
        for f in faults:
            if f["severity"] in ("fatal", "serious"):
                s += "\n       [%s] %s" % (f["severity"], f["fault"])
        s += "\n"
    return s


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pulls", help="pick_pulls.py JSON: their own words")
    ap.add_argument("--voice", required=True, help="brand_voice.py profile")
    ap.add_argument("--niche", help="niche_calibrate.py profile")
    ap.add_argument("--out", help="write markdown drafts here")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    pulls = json.loads(Path(a.pulls).read_text()).get("pulls", [])
    if not pulls:
        sys.exit("  no pulls in %s" % a.pulls)
    voice = json.loads(Path(a.voice).read_text())
    rewarded = {}
    if a.niche:
        prof = json.loads(Path(a.niche).read_text())
        rewarded = {h["hook"]: h["lift"] for h in prof.get("hooks", []) if h.get("recommend")}

    drafts = [d for d in (build_draft(p, voice, rewarded) for p in pulls) if d]
    if a.json:
        print(json.dumps({"drafts": drafts, "niche_shapes_used": sorted(rewarded)}, indent=1))
        return 0

    weak = sum(1 for d in drafts if d.get("source_doubts"))
    print("\n  %d moment(s) in, %d draft(s) out%s."
          % (len(pulls), len(drafts),
             ", %d of them from moments that are probably not here to be posted" % weak if weak else ""))
    print("  Every line below is a sentence they already said. Nothing here was written for them.")
    if rewarded:
        print("  Niche shapes in play: %s" % ", ".join(sorted(rewarded)))
    else:
        print("  No niche profile, or it supported no shape, so openers were chosen on their own merit.")
    for i, d in enumerate(drafts, 1):
        print(render(d, voice, i))
    if a.out:
        out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
        for i, d in enumerate(drafts, 1):
            if "problem" in d:
                continue
            body = "\n\n".join(d["lines"])
            (out / ("draft-%02d.md" % i)).write_text(
                "<!-- UNAPPROVED DRAFT from bin/draft_content.py. Every line is a sentence the\n"
                "     speaker already said. Read it, cut it, make it yours. -->\n\n"
                "# Draft %d\n\n%s\n\n---\n\n## Why it is shaped this way\n\n%s\n"
                % (i, body, "\n".join("- " + w for w in d["why"])))
        print("  wrote %s\n" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
