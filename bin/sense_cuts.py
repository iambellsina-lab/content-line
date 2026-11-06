#!/usr/bin/env python3
"""Sense check every piece in a cut list, and name the file each objection belongs to.

WHY THIS EXISTS, and it is a correctness fix rather than a convenience.

`clip_sense.py` checks ONE clip. Handed a `pick_pulls.py` JSON with no `--pull` it
reads index 0 and nothing else (`clip_sense.py` load(): `idx = (pull - 1) if pull
else 0`). `run_line.py` used to call it exactly that way, on `pulls.json`.

`pick_pulls.py` and `plan_clips.py` are two different selections over the same
transcript. pick_pulls finds the best CONTIGUOUS 35 to 75 seconds. plan_clips
builds a multi segment 45 to 150 second piece. They do not agree, and the renderer
renders plan_clips' output. Measured on one real run, 2026-11-05:

    pull starts            1168.0   565.0   1526.6
    piece first segments    565.0   826.0   1113.0

One of three overlaps. So the line rendered three pieces and printed objections
belonging to a 38 second span at 1168.0 that was never rendered at all. The
refusal is the product of this kit, and it was describing a clip that did not
exist in the output.

WHAT THIS DOES. It reads the cut list, which is the thing that gets rendered, and
checks each piece's own words with `clip_sense.check`. Every objection carries the
filename that piece will land under. It also surfaces the per piece `problems`
that `plan_clips.py` already wrote and that nothing was reading.

EXIT CODE, matching clip_sense so the caller behaves the same way:
    2  some piece must not be cut
    1  some piece needs a human
    0  every piece is usable, with at most one problem each
"""

import argparse
import json
import sys
from pathlib import Path

import clip_sense
import garble


def pieces_of(data):
    if isinstance(data, list):
        return data
    for key in ("pieces", "clips"):
        if isinstance(data.get(key), list):
            return data[key]
    return []


def text_of(piece):
    segs = piece.get("segments") or []
    if segs:
        return " ".join((s.get("text") or "").strip() for s in segs if s.get("text"))
    return piece.get("text") or ""


def sentences(text):
    import re
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def main():
    ap = argparse.ArgumentParser(
        description="Sense check every piece in a plan_clips.py cut list, by filename.")
    ap.add_argument("cuts", help="a plan_clips.py cut list (cuts.json)")
    ap.add_argument("--transcript",
                    help="the full transcript, for the mis-heard word check. Defaults to the "
                         "cut list's own _planned_from")
    ap.add_argument("--no-word-check", action="store_true", help="skip the mis-heard word check")
    ap.add_argument("--json", action="store_true", dest="as_json", help="machine readable")
    ap.add_argument("--out", help="write the machine readable form here as well")
    a = ap.parse_args()

    data = json.loads(Path(a.cuts).read_text(encoding="utf-8", errors="replace"))
    pieces = pieces_of(data)
    if not pieces:
        sys.exit("no pieces in %s" % a.cuts)

    # The mis-heard word check needs the WHOLE transcript, because the signal is the
    # tape contradicting itself. One clip in isolation has nothing to contradict.
    suspects = []
    full = a.transcript or data.get("_planned_from")
    word_check = None
    if not a.no_word_check and full and Path(full).is_file():
        suspects = garble.find(garble.words_with_times(full))
        word_check = full

    results = []
    worst = 0
    for i, piece in enumerate(pieces, 1):
        text = text_of(piece)
        sents = sentences(text)
        faults, notes = clip_sense.check(sents, piece.get("duration"), suspects)
        word, code = clip_sense.verdict(faults)
        worst = max(worst, code)
        # The exit code is NOT a severity count. clip_sense.verdict returns 0 for
        # "USABLE, WITH ONE PROBLEM", which is one SERIOUS fault. Reading the code as
        # "nothing serious here" is how a first draft of this file came to print
        # "every objection above is a MINOR one" under three serious objections.
        grave = [f for f in faults if f["severity"] in ("serious", "fatal")]
        fatal = [f for f in faults if f["severity"] == "fatal"]
        # clip_sense's verdict answers "may this be cut". It says "USABLE, WITH ONE
        # PROBLEM" for one serious fault, which read as a contradiction two lines above a
        # footer saying every piece carries a SERIOUS fault. This label answers "may this
        # be posted", which is the question the person reading actually has. It is derived
        # from the faults rather than from a new threshold, and clip_sense's verdict is
        # printed beside it unchanged, because the thresholds are its call.
        if fatal:
            label = "DO NOT POST"
        elif grave:
            label = "NEEDS A FIX"
        else:
            label = "NOTHING SERIOUS FOUND"
        results.append({
            "label": label,
            "piece": piece.get("piece") or ("piece %d" % i),
            "filename": piece.get("filename") or "",
            "duration": piece.get("duration"),
            "verdict": word,
            "code": code,
            "faults": faults,
            "serious_or_worse": len(grave),
            "fatal": len(fatal),
            "notes": notes,
            # plan_clips.py already wrote these, scoped to this piece, and nothing read them.
            "planner_problems": piece.get("problems") or [],
        })

    payload = {"cuts": str(a.cuts), "word_check": word_check,
               "pieces": results,
               "read_before_posting": [r["filename"] for r in results
                                       if r["serious_or_worse"]],
               "do_not_cut": [r["filename"] for r in results if r["code"] >= 2]}

    if a.out:
        Path(a.out).write_text(json.dumps(payload, indent=1))

    if a.as_json:
        print(json.dumps(payload, indent=1))
        return worst

    for r in results:
        print()
        print("  %s  %s" % (r["piece"], r["filename"] or "(no filename in the cut list)"))
        bits = [r["label"]]
        if r["serious_or_worse"]:
            bits.append("%d serious%s" % (r["serious_or_worse"],
                                          ", %d fatal" % r["fatal"] if r["fatal"] else ""))
        if r["duration"]:
            bits.append("%.2fs" % r["duration"])
        print("  %s   (clip_sense: %s)" % (", ".join(bits), r["verdict"]))
        if not r["faults"]:
            print("    nothing found wrong. That is not the same as good: this reads words, "
                  "so it cannot hear tone or see a face.")
        for f in r["faults"]:
            print("    [%s] %s" % (f["severity"].upper(), f["fault"]))
            print("        %s" % f["why"])
            if f.get("evidence"):
                print('        "%s"' % f["evidence"])
        for n in r["notes"]:
            print("    note: %s" % n)
        for p in r["planner_problems"]:
            print("    planner: %s" % p)

    if not word_check:
        print()
        print("  note: no transcript to check the words against, so a mis-heard word would "
              "not be caught here. Pass --transcript to turn that check on.")

    print()
    print("  %d piece(s) checked." % len(results))
    grave = [r for r in results if r["serious_or_worse"]]
    clean = [r for r in results if not r["serious_or_worse"]]
    if grave:
        print("  DO NOT POST THESE until the objections above are dealt with:")
        for r in grave:
            print("    %s   (%s, %d serious)"
                  % (r["filename"] or r["piece"], r["label"], r["serious_or_worse"]))
    if clean:
        print("  Clean of anything serious:")
        for r in clean:
            print("    %s   (%s)" % (r["filename"] or r["piece"], r["label"]))
    if not grave:
        print("  Nothing serious in any of them. That is not the same as good: this reads "
              "words, so it cannot hear tone or see a face.")
    print()
    return worst


if __name__ == "__main__":
    sys.exit(main())
