#!/usr/bin/env python3
"""plan_clips.py: build a clip out of SEVERAL moments that are nowhere near each other.

    python3 bin/plan_clips.py transcript.srt -n 6 --out cuts.json
    python3 bin/plan_clips.py podcast.srt -n 10 --min 60 --max 180 --source footage/ep12.mov
    python3 bin/plan_clips.py transcript.txt --out cuts.json --print

    Then:  python3 bin/check_dupes.py cuts.json      # before spending an encode
           python3 bin/assemble_clip.py cuts.json    # the renderer, which plays list order

WHY THIS EXISTS, and it is not a theory
    bin/pick_pulls.py finds the best CONTIGUOUS 35 to 75 seconds. That is the right tool when a
    speaker makes a point once, in order, and finishes it. Most people do not. They circle: the
    sharpest version of a point arrives twenty minutes after the story that proves it, and the
    line that should open the clip is said near the end, when they finally know what they meant.

    Cut that in spoken order and it is incoherent. The first real batch run through this kit was
    edited in spoken order, the six videos did not hold, and all of them were rebuilt with the
    segments reordered. So the order has to be IMPOSED, not filtered. This script decides the
    order. bin/assemble_clip.py is what then renders it.

WHAT IT DOES
    1. Breaks the transcript into MOMENTS: short runs of whole sentences that start cleanly and
       end on a finished sentence. Each moment is scored by pick_pulls' own nine signals, which
       this script imports rather than reimplements.
    2. Groups moments by what they are ABOUT, from the words they share, weighted so a rare word
       (a number, a name, "yacht") counts far more than a common one, and with two guards: one
       word in common is a coincidence rather than a subject, and two takes of the same line are
       one moment rather than two.
    3. Assembles each clip as: the strongest self-contained opener, then the related moments IN
       TAPE ORDER, then a closing line. Any of them may come from anywhere in the recording.
    4. Writes a cut list the renderer in this kit reads without anything being retyped.

OUTPUT
    A spec for bin/assemble_clip.py: source, out_dir, keep_audio, then pieces. Each piece carries
    filename, duration, segments and problems. Each segment is {"start", "end", "text", "role",
    "note", "why"} in absolute source seconds, with role one of hook, body, close.

    The segments are IN EDIT ORDER. That is the whole point: the renderer plays them in the order
    the list gives, not in the order they were said. "source_order" beside them is the same
    segments in tape order, so a reviewer can see exactly what moved.

    Caption cards come out as an empty list. bin/cards_from_srt.py makes those from the same
    transcript, because caption timing is its own job and four rounds went into getting it right.

WHAT IT CANNOT DO, said plainly
    It has never heard the audio. It does not know whether a join sounds like a join, whether her
    voice drops at the end of a body segment, or whether the room tone changes between minute 3
    and minute 19. Every join in the output is a GUESS about meaning made from text. Listen to
    each one before you render six of them.

    It also cannot tell that a body segment opening on "that" or "it" has lost whatever the
    pronoun pointed at. It flags those in the piece's "problems" list. Read that list first.
"""
import argparse
import datetime
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pick_pulls as pp     # noqa: E402  the scorer this script extends

MOMENT_MIN, MOMENT_MAX = 2.0, 26.0
HOOK_MAX = 14.0
CLIP_MIN, CLIP_MAX = 45.0, 150.0
MAX_SEGMENTS = 12
LINK_WEIGHT = 0.65          # how much "about the same thing" counts against "good on its own"
MIN_LINK = 0.08             # below this two moments are treated as unrelated
MIN_SHARED = 2              # one word in common is a coincidence, not a subject
MAX_DOMINANCE = 0.6         # no single word may carry more than this much of the match
MAX_ECHO = 0.72             # two moments this alike are two takes of one line, not two moments
CONTAIN_ECHO = 0.78         # or this much of the shorter one is already inside the longer one
RUN_SENTENCES = 4           # a moment is at most this many consecutive sentences
HOOK_CARD_WORDS = 12        # the pinned hook card is trimmed to this many words

# A speaker correcting themselves mid-sentence. Fine inside a clip, fatal as the first line.
RESTART = re.compile(r"\b(?:sorry|scratch that|let me (?:try|start|rephrase)|hold on|wait,|"
                     r"what i mean|i mean|what was i|where was i|anyway)\b", re.I)

STOP = set("""a about above after again against all also am an and any are aren't as at be because been
before being below between both but by can cannot could couldn't did didn't do does doesn't doing don't
down during each few for from further had hadn't has hasn't have haven't having he her here hers herself
him himself his how i i'm i've if in into is isn't it it's its itself just like me more most my myself no
nor not now of off on once only or other ought our ours ourselves out over own really same she should
shouldn't so some such than that that's the their theirs them themselves then there there's these they
this those through to too under until up very was wasn't we were weren't what what's when where which
while who whom why will with won't would wouldn't you your yours yourself yourselves get got go going
gonna know think thing things say said says saying want wants right okay ok yeah yes one two""".split())
WORD = re.compile(r"[a-z0-9][a-z0-9'’\-]*")


def terms(text):
    """Content words, with numbers kept whole because a number is the strongest hook there is."""
    out = {}
    for tok in WORD.findall(text.lower()):
        tok = tok.strip("'’-")
        if len(tok) < 4 and not any(c.isdigit() for c in tok):
            continue
        if tok in STOP:
            continue
        out[tok] = out.get(tok, 0) + 1
    return out


def slug(text, backup="", words=7):
    def bits_of(s):
        # Apostrophes come out of the token, not just off its ends: a filename with a quote in it
        # is legal and a nuisance in every shell that then has to handle it.
        out = []
        for w in WORD.findall(s.lower()):
            if w.strip("'’-") in STOP:
                continue
            b = w.replace("'", "").replace("’", "").strip("-")
            if b:
                out.append(b)
        return out
    bits = bits_of(text)[:words]
    if len(bits) < 3:
        seen = set(bits)
        for b in bits_of(backup):
            if b not in seen:
                bits.append(b)
                seen.add(b)
            if len(bits) >= words:
                break
    return "-".join(bits) or "clip"


def first_sentence(text, limit=HOOK_CARD_WORDS):
    bit = re.split(r"(?<=[.?!])\s+", text.strip())[0]
    words = bit.split()
    return " ".join(words[:limit]) + ("..." if len(words) > limit else "")


def build_moments(sents, words, mo_min, mo_max, run):
    """Short runs of whole sentences that a clip can safely be built out of."""
    out = []
    for i, si in enumerate(sents):
        if i > 0 and si["bad_opener"]:
            continue
        ok, how = pp.starts_clean(words, si)
        if not ok:
            continue
        for j in range(i, min(i + run, len(sents))):
            if j > i and sents[j]["start"] - sents[j - 1]["end"] > pp.INNER_GAP_REJECT:
                break
            if not sents[j]["clean_end"]:
                continue
            dur = sents[j]["end"] - si["start"]
            if dur < mo_min:
                continue
            if dur > mo_max:
                break
            score, why, _meta = pp.score_window(sents, i, j)
            # score_window's duration signal is written for a 35 to 75 second pull and says so in
            # its evidence string. A 9 second moment is not that, so the term is replaced rather
            # than left to make a claim that is not true of this window.
            why = [r for r in why if r["signal"] != "duration"]
            score = sum(r["points"] for r in why)
            text = " ".join(s["text"] for s in sents[i:j + 1])
            out.append({
                "i": i, "j": j, "start": si["start"], "end": sents[j]["end"], "dur": dur,
                "text": text, "score": score, "why": why, "start_check": how,
                "terms": terms(text),
                "anaphor": bool(pp.ANAPHOR.match(si["text"])),
                "connective": bool(pp.OPENER_BAD.match(si["text"])),
                "restart": bool(RESTART.search(text)),
                "filler": sum(s["filler"] for s in sents[i:j + 1]),
                "question_open": si["is_question"],
                "numbers": sum(len(s["numbers"]) for s in sents[i:j + 1]),
                "you": sum(s["you"] for s in sents[i:j + 1]),
                "close_strong": bool(pp.CLOSE_STRONG.search(sents[j]["text"].lower())),
                "terminal": bool(pp.TERMINAL.search(sents[j]["text"])),
                "start_estimated": si["start_estimated"],
            })
    return out


def _die(msg):
    print(f"plan_clips: {msg}", file=sys.stderr)
    raise SystemExit(2)


# ---------------------------------------------------------------- the brief

def load_brief(path):
    """The three answers, read before any clip is cut.

    Order, length and forbidden are the three questions that cost the first real batch
    roughly a third of its spend, every one of them because nobody asked before building.
    Asking is free. This makes the answers mechanical instead of advisory: the forbidden
    ranges and phrases never reach a moment, and the length band comes from the person
    rather than from a default.
    """
    try:
        b = json.loads(open(path, encoding="utf-8-sig").read())
    except FileNotFoundError:
        _die(f"no such brief: {path}. Copy specs/example-brief.json and answer the three.")
    except json.JSONDecodeError as e:
        _die(f"{path} is not readable JSON: {e}")
    if not isinstance(b, dict):
        _die(f"{path} should be a JSON object. specs/example-brief.json is the shape.")

    order = str(b.get("order", "edit")).strip().lower()
    if order not in ("edit", "spoken"):
        _die(f'{path}: "order" is "edit" or "spoken", not "{order}". '
            '"edit" assembles for the argument, "spoken" keeps tape order.')

    ln = b.get("length") or {}
    lo = ln.get("min")
    hi = ln.get("max")
    if lo is not None and hi is not None and float(hi) <= float(lo):
        _die(f'{path}: length.max ({hi}) is not longer than length.min ({lo}).')

    ranges, phrases = [], []
    for item in (b.get("forbidden") or []):
        if isinstance(item, dict) and item.get("start") is not None and item.get("end") is not None:
            a0, b0 = float(item["start"]), float(item["end"])
            if b0 <= a0:
                _die(f'{path}: a forbidden range ends before it starts: {a0} to {b0}.')
            ranges.append({"start": a0, "end": b0, "why": str(item.get("why", ""))})
        elif isinstance(item, dict) and item.get("phrase"):
            phrases.append({"phrase": str(item["phrase"]).lower(),
                            "why": str(item.get("why", ""))})
        elif isinstance(item, str):
            phrases.append({"phrase": item.lower(), "why": ""})
        else:
            _die(f'{path}: a forbidden entry is {{"start","end","why"}} or {{"phrase","why"}}, '
                f'not {item!r}.')
    return {"order": order, "lo": lo, "hi": hi, "ranges": ranges, "phrases": phrases,
            "notes": b.get("notes", ""), "path": str(path)}


def apply_forbidden(moments, brief):
    """Drop every moment that touches forbidden tape or says a forbidden phrase.

    Dropped here, before assembly, it costs nothing. Found after the cuts exist it forces
    a re-cut, which is what happened the first time.
    """
    if not brief or (not brief["ranges"] and not brief["phrases"]):
        return moments, []
    kept, dropped = [], []
    for m in moments:
        hit = None
        for r in brief["ranges"]:
            if m["start"] < r["end"] and m["end"] > r["start"]:
                hit = (f"overlaps forbidden tape {pp.timecode(r['start'])} to {pp.timecode(r['end'])}"
                       + (f": {r['why']}" if r["why"] else ""))
                break
        if hit is None:
            low = m["text"].lower()
            for ph in brief["phrases"]:
                if ph["phrase"] in low:
                    hit = (f'says the forbidden phrase "{ph["phrase"]}"'
                           + (f": {ph['why']}" if ph["why"] else ""))
                    break
        (dropped if hit else kept).append(m)
        if hit:
            m["forbidden_why"] = hit
    return kept, dropped


def idf_weights(moments):
    n = len(moments) or 1
    df = {}
    for m in moments:
        for t in m["terms"]:
            df[t] = df.get(t, 0) + 1
    return {t: math.log(1.0 + n / float(c)) for t, c in df.items()}


def vec(term_counts, idf):
    return {t: (1.0 + math.log(c)) * idf.get(t, 1.0) for t, c in term_counts.items()}


def match(a, b):
    """Cosine, plus the two numbers that say whether the match means anything.

    Returns (similarity, shared term count, share of the match carried by its biggest term).
    A rhetorical habit produces a high cosine off one repeated word: six sentences that all
    open "Stop ..." look related and are not. So a caller can insist on more than one shared
    word and on no single word carrying the whole match.
    """
    if not a or not b:
        return 0.0, 0, 1.0
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    parts = [v * big[t] for t, v in small.items() if t in big]
    dot = sum(parts)
    if dot <= 0:
        return 0.0, 0, 1.0
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    sim = dot / (na * nb) if na and nb else 0.0
    return sim, len(parts), max(parts) / dot


def cosine(a, b):
    return match(a, b)[0]


def containment(a, b):
    """How much of the SMALLER of two moments is already inside the larger one.

    Cosine misses an echo of unequal length: "You have to take your unseriousness so seriously"
    sits entirely inside the longer take of the same line and still only scores about 0.55,
    because the longer one carries words the short one does not. Containment catches it.
    """
    if not a or not b:
        return 0.0
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    dot = sum(v * big[t] for t, v in small.items() if t in big)
    base = sum(v * v for v in small.values())
    return dot / base if base else 0.0


def overlaps(a, b, slack=0.0):
    return min(a["end"], b["end"]) - max(a["start"], b["start"]) > slack


def hook_bonus(m):
    """What makes an opener able to stand alone with the sound off."""
    b = 0.0
    if m["question_open"]:
        b += 8
    if m["numbers"]:
        b += 4
    if m["you"]:
        b += 3
    if m["anaphor"]:
        b -= 25
    if m["restart"]:
        b -= 25
    if m["filler"]:
        b -= 10 * m["filler"]
    if m["dur"] > HOOK_MAX:
        b -= 10
    return b


def assemble(moments, idf, n_pieces, lo, hi, max_segs, link_w, min_link,
             min_shared=MIN_SHARED, max_dom=MAX_DOMINANCE, max_echo=MAX_ECHO):
    """Grow each clip from its opener outwards, taking the related moments wherever they are."""
    for m in moments:
        m["vec"] = vec(m["terms"], idf)
        m["hook_fit"] = m["score"] + hook_bonus(m)
    scores = [m["score"] for m in moments] or [0.0]
    lo_s, hi_s = min(scores), max(scores)
    rng = (hi_s - lo_s) or 1.0
    for m in moments:
        m["score_norm"] = (m["score"] - lo_s) / rng

    used = []           # every moment already spent, so two clips can never share tape
    pieces = []
    seeds = sorted(moments, key=lambda m: -m["hook_fit"])
    for seed in seeds:
        if len(pieces) >= n_pieces:
            break
        if (seed["anaphor"] or seed["restart"] or seed["filler"]
                or seed["dur"] > HOOK_MAX or seed["hook_fit"] <= 0):
            continue
        if any(overlaps(seed, u) for u in used):
            continue
        chosen = [seed]
        pv = dict(seed["vec"])
        total = seed["dur"]
        while total < lo and len(chosen) < max_segs:
            best, best_val, best_sim = None, 0.0, 0.0
            for m in moments:
                if m["dur"] + total > hi:
                    continue
                if any(overlaps(m, c) for c in chosen) or any(overlaps(m, u) for u in used):
                    continue
                sim, shared, dom = match(pv, m["vec"])
                if sim < min_link or shared < min_shared or dom > max_dom:
                    continue
                # Two takes of the same line are not two moments. She says the hook three times
                # and the third is the keeper; putting all three in one clip is the defect.
                if any(cosine(m["vec"], c["vec"]) > max_echo
                       or (min(len(m["terms"]), len(c["terms"])) >= 3
                           and containment(m["vec"], c["vec"]) > CONTAIN_ECHO)
                       for c in chosen):
                    continue
                val = link_w * sim + (1.0 - link_w) * m["score_norm"]
                if val > best_val:
                    best, best_val, best_sim = m, val, sim
            if best is None:
                break
            best = dict(best)
            best["link"] = best_sim
            chosen.append(best)
            for t, v in best["vec"].items():
                pv[t] = pv.get(t, 0.0) + v
            total += best["dur"]
        if total < lo:
            continue

        # Order is imposed here, and this is the whole reason the script exists.
        # Opener first wherever it was said. A closing line last wherever it was said.
        # Everything between stays in tape order, because that is where her own reasoning is.
        body = sorted(chosen[1:], key=lambda m: m["start"])
        close = None
        usable = [m for m in body if m["terminal"] and not m["restart"]]
        finishers = [m for m in usable if m["close_strong"]] or usable
        if finishers:
            # A closing line lands. It does not ask, and it is not the speaker backtracking.
            close = max(finishers, key=lambda m: (m["close_strong"],
                                                  not m["text"].rstrip().endswith("?"),
                                                  m["score"]))
            body = [m for m in body if m is not close]
        ordered = [seed] + body + ([close] if close else [])

        segments, problems = [], []
        for k, m in enumerate(ordered):
            role = "hook" if k == 0 else ("close" if close is not None and m is close else "body")
            top = sorted(m["why"], key=lambda r: -r["points"])[:2]
            why = "score %.0f; " % m["score"] + "; ".join(r["evidence"] for r in top)
            if role == "hook":
                why = ("opener: %s. " % m["start_check"]) + why
            else:
                why += "; shares the subject with the opener (link %.2f)" % m.get("link", 0.0)
            segments.append({"start": round(m["start"], 2), "end": round(m["end"], 2),
                             "note": "%s, from %s" % (role, pp.timecode(m["start"])),
                             "role": role, "text": m["text"], "why": why})
            if role != "hook" and m["anaphor"]:
                problems.append('segment %d opens on a pronoun ("%s"). Moved out of its place in '
                                "the tape, that pronoun may now point at nothing. Hear this join or "
                                "start the segment one sentence earlier."
                                % (k + 1, m["text"].split()[0]))
            if role != "hook" and m["connective"]:
                problems.append('segment %d opens on a connective ("%s"), which joins it to '
                                "whatever came before it on tape. That is no longer what plays "
                                "before it." % (k + 1, m["text"].split()[0].strip(",")))
            if role != "hook" and m["restart"]:
                problems.append("segment %d contains the speaker correcting themselves. Check it "
                                "does not read as a mistake once the surrounding tape is gone."
                                % (k + 1))
            if not m["terminal"]:
                problems.append("segment %d does not end on a full stop in the transcript, so the "
                                "thought may run past the cut. Hear it." % (k + 1))
            if m["start_estimated"]:
                problems.append("segment %d starts inside a transcript cue, so %.2f is interpolated "
                                "and can be about a second out. Snap it to the waveform."
                                % (k + 1, m["start"]))
            used.append(m)

        dur = sum(s["end"] - s["start"] for s in segments)
        order_note = ("opener from %s, close from %s, %d body segments in tape order"
                      % (pp.timecode(ordered[0]["start"]),
                         pp.timecode(close["start"]) if close else "none",
                         len(body)))
        problems.insert(0, "No join in this clip has been heard. plan_clips.py reads text only. "
                           "Listen to all %d joins before rendering." % max(0, len(segments) - 1))
        problems.append("The pinned hook card is the transcript's own words, trimmed. Tighten it "
                        "by hand: a hook card is read with the sound off.")
        pieces.append({
            "piece": "A%d" % (len(pieces) + 1),
            "filename": slug(seed["text"], " ".join(m["text"] for m in body)),
            "the_argument": " ".join(first_sentence(m["text"], 40) for m in ordered),
            "duration": round(dur, 2),
            "hook": {"text": first_sentence(seed["text"]), "hold": 4.0},
            "segments": segments,
            "cards": [],
            "edit_order_note": order_note,
            "source_order": [[round(m["start"], 2), round(m["end"], 2)]
                             for m in sorted(ordered, key=lambda x: x["start"])],
            "problems": problems,
        })
    return pieces


def main():
    ap = argparse.ArgumentParser(
        description="Plan clips from several non-adjacent moments in one long recording.")
    ap.add_argument("transcript", help="SRT, VTT, JSON or bracket-format file, or - for stdin")
    ap.add_argument("-n", type=int, default=6, help="how many clips to try for (default 6)")
    ap.add_argument("--min", type=float, default=CLIP_MIN, dest="lo",
                    help="shortest finished clip in seconds (default 45)")
    ap.add_argument("--max", type=float, default=CLIP_MAX, dest="hi",
                    help="longest finished clip in seconds (default 150)")
    ap.add_argument("--segments-max", type=int, default=MAX_SEGMENTS,
                    help="most segments in one clip (default 12)")
    ap.add_argument("--moment-min", type=float, default=MOMENT_MIN,
                    help="shortest usable moment (default 2)")
    ap.add_argument("--moment-max", type=float, default=MOMENT_MAX,
                    help="longest usable moment (default 26)")
    ap.add_argument("--run", type=int, default=RUN_SENTENCES,
                    help="most consecutive sentences in one moment (default 4)")
    ap.add_argument("--link", type=float, default=LINK_WEIGHT,
                    help="0 to 1: how much subject match counts against a moment's own score")
    ap.add_argument("--min-link", type=float, default=MIN_LINK,
                    help="below this, two moments count as unrelated (default 0.08)")
    ap.add_argument("--min-shared", type=int, default=MIN_SHARED,
                    help="distinct words two moments must share to count as related (default 2)")
    ap.add_argument("--max-dominance", type=float, default=MAX_DOMINANCE,
                    help="most of a match one single word may carry (default 0.6)")
    ap.add_argument("--max-echo", type=float, default=MAX_ECHO,
                    help="above this two moments are two takes of one line, so only one is used "
                         "(default 0.72)")
    ap.add_argument("--brief", help="the three answers, from specs/example-brief.json: order, "
                                    "length and what must never appear. Its length band and its "
                                    "forbidden list override the flags above")
    ap.add_argument("--source", help="the long recording the times refer to, written into the spec")
    ap.add_argument("--out-dir", help="where the renderer should put the finished pieces")
    ap.add_argument("--brand", help="a style file for the renderer, for example example-edit-style.json")
    ap.add_argument("--keep-audio", action="store_true",
                    help="tell the renderer to leave the sound exactly as recorded")
    ap.add_argument("--out", help="write the cut list here")
    ap.add_argument("--print", action="store_true", dest="show",
                    help="also print a short human summary to stderr")
    a = ap.parse_args()

    cues = pp.load_cues(a.transcript)
    words = pp.build_words(cues)
    ratio = pp.punctuation_ratio(words)
    punct_mode = ratio >= pp.WEAK_PUNCT_RATIO
    sents = [pp.analyse_sentence(s) for s in pp.split_sentences(words, punct_mode)]
    moments = build_moments(sents, words, a.moment_min, a.moment_max, a.run)

    brief = load_brief(a.brief) if a.brief else None
    forbidden_dropped = []
    if brief:
        if brief["lo"] is not None:
            a.lo = float(brief["lo"])
        if brief["hi"] is not None:
            a.hi = float(brief["hi"])
        moments, forbidden_dropped = apply_forbidden(moments, brief)
        if not moments:
            _die(f"{brief['path']}: the forbidden list rules out every moment in this recording. "
                "Nothing is left to cut.")
        print(f"plan_clips: brief {brief['path']}: order {brief['order']}, "
              f"length {a.lo:.0f} to {a.hi:.0f}s, "
              f"{len(brief['ranges'])} forbidden range(s) and {len(brief['phrases'])} phrase(s). "
              f"{len(forbidden_dropped)} moment(s) dropped before assembly.", file=sys.stderr)
        if brief["order"] == "spoken":
            print("plan_clips: the brief says SPOKEN order. This script assembles for the "
                  "argument and cannot keep tape order. Use bin/pick_pulls.py, which finds the "
                  "best continuous stretch, and render it with bin/assemble_clip.py.",
                  file=sys.stderr)
            return 2

    idf = idf_weights(moments)
    pieces = assemble(moments, idf, a.n, a.lo, a.hi, a.segments_max, a.link, a.min_link,
                      a.min_shared, a.max_dominance, a.max_echo)

    caveats = [
        "Every segment order in here was decided from text. The audio has not been heard. A join "
        "that reads cleanly can still sound like a join.",
        "Two clips in one run never share tape: a moment is spent once. Cut lists from SEPARATE "
        "runs can overlap, so run bin/check_dupes.py over all of them before you render.",
        "the_argument is a mechanical stitch of each segment's first sentence, not a written "
        "argument. Replace it with a line a person wrote.",
        "cards is empty on purpose. Run bin/cards_from_srt.py on the same transcript to fill it.",
    ]
    if not punct_mode:
        caveats.insert(0, "This transcript has almost no sentence punctuation (%.1f terminal marks per "
                          "100 words), so sentence edges were guessed from pauses and every start and "
                          "end in here is softer than it looks." % (100 * ratio))
    result = {
        "_help": "A cut list for bin/assemble_clip.py, planned by bin/plan_clips.py. Segments are "
                 "in EDIT order and the renderer plays them in that order, not in tape order.",
        "_planned_from": a.transcript,
        "_planned_by": "plan_clips.py",
        "_planned_on": datetime.date.today().isoformat(),
        "source": a.source or "PUT THE LONG RECORDING HERE",
        "out_dir": a.out_dir or "../out/planned-batch",
        "brand": a.brand,
        "times": "clip",
        "keep_audio": bool(a.keep_audio),
        "_caveats": caveats,
        "_stats": {
            "cues": len(cues),
            "words": len(words),
            "sentences": len(sents),
            "transcript_seconds": round(cues[-1]["end"] - cues[0]["start"], 1),
            "punctuation_mode": "punctuation" if punct_mode else "pause_fallback",
            "moments_built": len(moments),
            "pieces_asked_for": a.n,
            "pieces_built": len(pieces),
        },
        "pieces": pieces,
    }
    out = json.dumps(result, indent=1, ensure_ascii=False)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(out + "\n")
    if a.show or a.out:
        for p in pieces:
            print("%s  %6.2fs  %2d segments  %s" % (p["piece"], p["duration"],
                                                    len(p["segments"]), p["filename"]),
                  file=sys.stderr)
            print("        %s" % p["edit_order_note"], file=sys.stderr)
        if not pieces:
            print("plan_clips: no clip of %g to %g seconds could be built from %d moments. "
                  "Try --min lower, --min-link lower, or a longer recording."
                  % (a.lo, a.hi, len(moments)), file=sys.stderr)
    if not a.out:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:       # noqa: BLE001
            pass
        print(out)
    return 0 if pieces else 1


if __name__ == "__main__":
    sys.exit(main())
