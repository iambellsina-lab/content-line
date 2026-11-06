#!/usr/bin/env python3
"""garble.py: find words the transcriber mis-heard, by catching the tape contradicting itself.

WHY THIS EXISTS, and the failure that produced it. On 2026-10-15 the whole kit was run end to
end on a real 29 minute lesson. Six candidate moments came out, `clip_sense.py` judged them, one
passed clean, and that clean one read "When you're outside of home U of Stasis, maybe your
arousal state is up here". The speaker said homeostasis. Whisper heard three common words
instead of one uncommon one, four times between 13:22 and 14:00.

Nothing in the kit could see it. "home U of Stasis" is grammatical English: it opens cleanly,
it finishes its sentence, it carries a turn. Every structural check a sense filter can make, it
passes. So a caption reading "home U of Stasis" was one step away from being staged, and the
only reason it was not is that a human read the sentence out loud.

WHAT WAS ACTUALLY WRONG, because the first diagnosis was wrong and cost two rebuilds. The guess
was missing vocabulary, and the fix was going to be a --terms flag feeding whisper a word list.
The control disproved it: transcribing that same 70 seconds on its own, with no vocabulary and
no prompt, spells homeostasis correctly. And in the full run the word is garbled four times from
13:22, then spelled correctly four times from 20:30 onward. Same word, same speaker, same file,
same model. It is a local decoding slip that reinforces itself through whisper's carried context
for about forty seconds and then recovers. A word list would not have touched it.

That recovery is what makes this detectable. The transcript holds both spellings, so it
contradicts itself, and the contradiction can be found without knowing anything about the
subject, without a vocabulary list, and without a bigger model.

HOW IT WORKS. Every run of 2 to 4 adjacent words is joined with the spaces removed and compared
against every long word the transcript uses more than once. "home U of Stasis" becomes
"homeuofstasis", which is a 0.92 match for "homeostasis", a word this tape uses four times
elsewhere. That alone flags 263 spans on this file and is useless, because any long word plus a
short neighbour matches the long word: "unfortunately I" scores 0.96 against "unfortunately".

The discriminator is that the joined span must beat every single word inside it. "unfortunately
I" is dropped because "unfortunately" on its own already scores 1.00, so joining added nothing.
"home U of Stasis" is kept because no word in it comes close to "homeostasis" alone and the
join is what creates the match. With that one rule the 263 become 3.

WHAT THE THRESHOLDS REST ON, stated plainly because it is one tape. At MIN_RATIO 0.80 the three
survivors were the two real garbles at 0.92 and 0.91 and one false positive at 0.82, "your use
of" offered as "yourself", which is grammatical and almost certainly what was said. So the floor
sits at 0.85, above that false positive and below both real ones. That is a threshold fitted to
a single recording. It will want revisiting the first time this is run on tape of a different
kind, and the numbers are written here so the next person can see what it was fitted to rather
than guessing.

THE CUE BOUNDARY, and why --fix exists. The first manual repair of this file failed. A plain
find and replace for "home U of Stasis" changed three of the four places and silently missed the
fourth, because that one straddles a subtitle boundary: "home U" ends cue 142 at 13:28 and "of
Stasis" opens cue 143. The detector joins words across cues, so it sees the phrase; a text editor
does not. Anybody fixing these by hand will hit the same thing and believe they are finished.

So --fix does it properly. It writes the correct word into the cue holding the start of the span
and removes the leftover words from the cues that follow, which is the only repair that works
when a word has been split across a subtitle break.

WHAT IT CANNOT DO. It only catches a mis-hearing whose correct spelling appears somewhere else
in the same transcript. A word garbled every single time it is spoken leaves nothing to
contradict, and this will say nothing about it. It is a net with a known hole, not a guarantee,
and the hole is the reason a human still reads a caption before it goes anywhere.

Usage:
    python3 bin/garble.py transcript.srt
    python3 bin/garble.py transcript.cues.json --json
"""
import argparse
import difflib
import json
import re
import sys
from pathlib import Path

WORD = re.compile(r"[A-Za-z']+")

MIN_RATIO = 0.85     # the floor a joined span must clear. See the note above on what it is fitted to.
MIN_GAIN = 0.15      # how far the join must beat the best single word in it
MIN_LEN = 8          # shorter joins are too easy to match by accident
MIN_USES = 2         # the correct spelling has to be used more than once to be the likely one
MAX_SPAN = 4         # how many adjacent words to try joining
LEN_SLACK = 4        # skip comparisons where the lengths cannot plausibly line up


SRT_TIME = re.compile(r"(\d\d):(\d\d):(\d\d)[,.](\d+)\s*-->")


def read_cues(path):
    """Return [{"start", "text", "head"}] for an SRT or cues JSON.

    `head` is whatever precedes the text in an SRT (the index line and the timing line), kept
    verbatim so --fix can write the file back without reformatting anything it did not change.
    """
    p = Path(path)
    raw = p.read_text(encoding="utf-8", errors="replace")
    if p.suffix.lower() == ".json" or raw.lstrip().startswith(("{", "[")):
        data = json.loads(raw)
        cues = data if isinstance(data, list) else (data.get("cues") or data.get("pulls") or [])
        return [{"start": c.get("start"), "text": c.get("text", ""), "head": None} for c in cues]

    out, head, text, start = [], [], [], None
    def flush():
        if text or head:
            out.append({"start": start, "text": " ".join(text), "head": "\n".join(head)})
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.isdigit() and not text:
            if head and text:
                flush()
                head, text = [], []
            head.append(line)
            continue
        if SRT_TIME.search(stripped):
            if text:
                flush()
                head, text, start = [h for h in [] ], [], None
            m = SRT_TIME.search(stripped)
            h, mi, sec, ms = (int(x) for x in m.groups())
            start = h * 3600 + mi * 60 + sec + ms / 1000.0
            head.append(line)
            continue
        if not stripped:
            if text:
                flush()
                head, text, start = [], [], None
            continue
        text.append(stripped)
    flush()
    return [c for c in out if c["text"]]


def words_from_cues(cues):
    """[(word, start, cue_index, char_start, char_end)] across the whole transcript."""
    out = []
    for i, c in enumerate(cues):
        for m in WORD.finditer(c["text"]):
            out.append((m.group(0), c["start"], i, m.start(), m.end()))
    return out


def words_with_times(path):
    """Return [(word, seconds_or_None)], which is all `find` needs."""
    return [(w, t) for w, t, _, _, _ in words_from_cues(read_cues(path))]


def apply_fix(cues, words, suspects):
    """Write each correction in, including where a word was split across a cue boundary.

    The cue holding the start of the span gets the correct word. Any cues after it have their
    leftover span words cut out. Edits are applied back to front so earlier offsets stay valid.
    """
    edits = []   # (cue_index, char_start, char_end, replacement)
    for sus in suspects:
        i, n = sus["i"], sus["n"]
        span = words[i:i + n]
        by_cue = {}
        for w, _, ci, cs, ce in span:
            lo, hi = by_cue.get(ci, (cs, ce))
            by_cue[ci] = (min(lo, cs), max(hi, ce))
        first = span[0][2]
        for ci, (lo, hi) in by_cue.items():
            edits.append((ci, lo, hi, sus["probably"] if ci == first else ""))
    changed = set()
    for ci, lo, hi, rep in sorted(edits, key=lambda e: (-e[0], -e[1])):
        t = cues[ci]["text"]
        cues[ci]["text"] = t[:lo] + rep + t[hi:]
        changed.add(ci)
    for ci in changed:
        cues[ci]["text"] = re.sub(r"\s+([,.?!])", r"\1",
                                  re.sub(r"\s{2,}", " ", cues[ci]["text"])).strip()
    return len(changed)


def write_srt(cues, path):
    out = []
    for c in cues:
        if c["head"] is None:
            raise ValueError("this transcript did not come from an SRT, so it cannot be written "
                             "back as one")
        out.append("%s\n%s\n" % (c["head"], c["text"]))
    Path(path).write_text("\n".join(out), encoding="utf-8")


def find(words):
    """The suspects, worst first. `words` is [(word, seconds, ...)]: anything from
    words_with_times or words_from_cues."""
    words = [(w[0], w[1]) for w in words]
    lower = [w.lower() for w, _ in words]
    uses = {}
    for w in lower:
        uses[w] = uses.get(w, 0) + 1
    # the candidate correct spellings: long words this transcript actually uses more than once
    candidates = sorted(w for w, n in uses.items() if len(w) >= MIN_LEN and n >= MIN_USES)
    if not candidates:
        return []

    ratio = lambda a, b: difflib.SequenceMatcher(None, a, b).ratio()
    found = []
    for n in range(2, MAX_SPAN + 1):
        for i in range(len(words) - n):
            span = words[i:i + n]
            joined = "".join(w.lower() for w, _ in span)
            if len(joined) < MIN_LEN:
                continue
            for cand in candidates:
                if abs(len(joined) - len(cand)) > LEN_SLACK:
                    continue
                r = ratio(joined, cand)
                if r < MIN_RATIO or joined == cand:
                    continue
                # the join has to be what creates the match, not a long word with a neighbour
                best_single = max(ratio(w.lower(), cand) for w, _ in span)
                if r <= best_single + MIN_GAIN:
                    continue
                found.append({"heard": " ".join(w for w, _ in span),
                              "probably": cand,
                              "ratio": round(r, 3),
                              "at": span[0][1],
                              "i": i, "n": n,
                              "used_elsewhere": uses[cand]})
    # Strongest first, then keep only spans that do not overlap one already kept.
    #
    # This was keyed on (timecode, text) and that was wrong: both garbles inside cue 142 carry
    # that cue's start time, so the two collapsed into one finding, and --fix repaired the first
    # and left the second sitting there looking fixed. A position is unique; a timecode is not.
    # Dropping overlaps at the same time means no two corrections can land on the same words.
    kept = []
    for f in sorted(found, key=lambda f: (-f["ratio"], f["i"])):
        lo, hi = f["i"], f["i"] + f["n"]
        if any(lo < k["i"] + k["n"] and k["i"] < hi for k in kept):
            continue
        kept.append(f)
    return sorted(kept, key=lambda f: f["i"])


def tc(seconds):
    if seconds is None:
        return "  --:--"
    return "%6s" % ("%d:%04.1f" % (seconds // 60, seconds % 60))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript", help="an SRT, a .cues.json, or plain text")
    ap.add_argument("--json", action="store_true", help="machine readable")
    ap.add_argument("--fix", metavar="OUT",
                    help="write a corrected SRT here. It handles a word split across a cue "
                         "boundary, which a find and replace does not")
    a = ap.parse_args()

    cues = read_cues(a.transcript)
    words = words_from_cues(cues)
    if not words:
        sys.exit("no words in %s" % a.transcript)
    suspects = find(words)

    if a.json:
        print(json.dumps({"words": len(words), "suspects": suspects}, indent=1))
        return 1 if suspects else 0

    print("\n  %d words read" % len(words))
    if not suspects:
        print("\n  Nothing contradicts itself. That is not the same as correct: this only finds a\n"
              "  mis-hearing whose right spelling appears somewhere else in the same transcript.\n")
        return 0
    print("\n  %d suspected mis-hearing(s). The tape spells it both ways, so one of them is wrong.\n"
          % len(suspects))
    straddle = [f for f in suspects
                if len({w[2] for w in words[f["i"]:f["i"] + f["n"]]}) > 1]
    for f in suspects:
        cross = len({w[2] for w in words[f["i"]:f["i"] + f["n"]]}) > 1
        print("  %s  heard %r%s" % (tc(f["at"]), f["heard"],
                                    "   (split across a cue break)" if cross else ""))
        print("          probably %r, which this transcript uses %d time(s) elsewhere  [%.2f]"
              % (f["probably"], f["used_elsewhere"], f["ratio"]))

    if a.fix:
        n = apply_fix(cues, words, suspects)
        try:
            write_srt(cues, a.fix)
        except ValueError as exc:
            sys.exit("  %s" % exc)
        left = find(words_from_cues(read_cues(a.fix)))
        print("\n  Wrote %s: %d correction(s) across %d cue(s)." % (a.fix, len(suspects), n))
        if left:
            print("  %d still flagged, so read them yourself before trusting this." % len(left))
            return 1
        print("  Re-checked the file it wrote, and nothing contradicts itself in it now.\n")
        return 0

    if straddle:
        print("\n  %d of these is split across a cue break, so a find and replace in an editor\n"
              "  will miss it and look like it worked. Use --fix." % len(straddle))
    print("\n  Fix these in the transcript before anything downstream reads it. A caption is the\n"
          "  last place you want to find out.\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
