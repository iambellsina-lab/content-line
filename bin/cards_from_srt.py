#!/usr/bin/env python3
"""cards_from_srt.py: a transcript plus a chosen moment to a ready caption_video.py spec.

    python3 bin/cards_from_srt.py transcript.srt --start 64 --end 94.5 --source footage/take.mp4
    python3 bin/cards_from_srt.py transcript.srt --pulls pulls.json --pull 1 --source footage/take.mp4
    python3 bin/cards_from_srt.py transcript.srt --start 64 --end 94.5 --print     # stdout, writes nothing

This is the step that used to be done by hand. pick_pulls.py says WHICH 35 to 75 seconds to use;
caption_video.py burns cards onto the footage; nothing joined the two. Now this does: it cuts the
words of the chosen window into two to four word cards, times each one, picks at most one accent
word per card, and writes the spec caption_video.py reads.

Standard library only. No Pillow, no ffmpeg, no network, no account. Runs on Python 3.8 or newer
(on Windows write `python` for `python3`). It reads a transcript and writes one JSON file. It
never touches your footage.

INPUT
    The same transcript formats pick_pulls.py takes: SRT, VTT, or JSON
    [{"start": 12.4, "end": 15.9, "text": "..."}, ...], including a Whisper {"segments": [...]}
    wrapper. Parsing is pick_pulls.py's own, imported, so the two always agree about the words.

    The window comes from either --start/--end in seconds, or --pulls with --pull N to take the
    Nth pull straight out of a pick_pulls.py run.

OUTPUT
    One spec file, by default specs/<source stem>-cards.json, with brand, source, out, trim and
    cards. Card times are seconds in the SOURCE recording, which is what caption_video.py expects:
    it subtracts the trim start itself. A relative "out" in that spec resolves next to the spec
    file, so the video lands in the kit's own out folder and not wherever you happened to stand.

TIMING, AND HOW MUCH TO TRUST IT
    A normal SRT only timestamps a cue of several words. Word times inside a cue are interpolated
    by character count, so a card boundary can sit up to about a second from the real word. The
    report says "interpolated". For times that match the mouth, transcribe one word per cue:

        whisper-cli -m models/ggml-base.en.bin -f audio.wav -ml 1 --output-srt --output-file words

    Then this script reports "word-level" and uses the real times. Either way, watch the result
    before anyone else does. Where the footage disagrees with the file, the footage wins.

MORE THAN ONE PERSON TALKING
    A cue that opens "ANNA:" or ">> SPEAKER_1:" is naming who is speaking. That name never becomes
    a caption, and no card is carried across a change of speaker, so one card cannot read as one
    person saying both halves of an exchange. Cues that overlap in time mean people talking over
    each other: the script says how many and how often, because card times there are guesses.

    Stutters and restarts ("I I I think", "the- the the problem") are kept as said and reported.
    Verbatim is the default. --collapse-stutters drops the false starts, at the cost of also
    flattening a deliberate "very very", which is why it is not on by default.

WHAT IT WILL NOT DO
    It does not choose the moment (that is pick_pulls.py, or you with the waveform open). It does
    not write new words: every card is the speaker's own words in their own order, minus filler.
    It does not judge whether a line earns the screen. It does not render anything.

HOW IT BEHAVES WHEN THE TRANSCRIPT IS UGLY
    fixtures/awkward/ holds eight short transcripts of things real speech does: a four second
    silence mid-sentence, a stutter, two people over each other, no punctuation at all, nothing but
    filler, broken cue times, music tags, a word held for nine seconds. kit_check.py runs all of
    them and checks the cards that come back are usable. Read that folder's README before trusting
    a change to this file.
"""
import argparse
import copy
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pick_pulls as pp                                     # noqa: E402  (same folder, stdlib only)

KIT_ROOT = Path(__file__).resolve().parent.parent

MIN_WORDS, MAX_WORDS = 2, 4         # short-form practice: a card is read in one glance
SENTENCE_GAP = 0.45                 # silence this long is a break whatever the punctuation says
HOLD_GAP = 0.50                     # a gap smaller than this is closed, so captions do not flicker
MIN_CARD = 0.55                     # no card flashes for less than this if there is room to hold it
MAX_CARD = 3.00                     # a card held longer than this has stopped tracking the speech

# Dropped from the on-screen text by default. The audio still says them; a caption that prints
# every "um" is harder to read and nobody writes them on purpose.
FILLER_WORDS = {"um", "umm", "ummm", "uh", "uhh", "uhhh", "uhm", "er", "erm", "hmm", "hmmm",
                "mm", "mmm", "mhm", "mmhmm", "uh-huh", "mm-hmm"}
FILLER_PAIRS = {("you", "know"), ("i", "mean")}
# "like," with a comma only. Bare "like" is a real word ("looks like this") and stays.
HEDGE_WORDS = {"basically", "literally", "actually", "honestly"}        # only with --strip-hedges
HEDGE_PAIRS = {("kind", "of"), ("sort", "of"), ("i", "guess")}          # only with --strip-hedges

# A cue that opens "ANNA:" or ">> SPEAKER_1:" is naming who is talking. That name is not a caption,
# and the words either side of it belong to two different people.
SPEAKER_LABEL_TOKEN = re.compile(r"^[>\-]*\s*(?:SPEAKER[ _]?\d+|[A-Z][A-Za-z0-9_']*):$")
STUTTER_GAP = 0.60          # a repeat further apart than this is more likely to be deliberate

TERMINAL = re.compile(r"[.?!]+[\"')\]”’]*$")
SOFT_END = re.compile(r"[,;:\u2014-]+[\"')\]”’]*$")
HAS_DIGIT = re.compile(r"\d")
# Words that carry the turn in a line. Accenting one of these is the reason to accent at all.
STRONG = re.compile(
    r"^(?:never|always|nothing|everything|everyone|nobody|none|only|every|all|most|worst|best|"
    r"first|last|free|real|wrong|right|stop|start|instead|until|unless|but|because|problem|"
    r"truth|point|secret|mistake|reason|why|how|what|everything|anything|twice|double|half)$"
)
STOPWORDS = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "is", "it", "that",
             "this", "was", "for", "with", "as", "be", "are", "you", "your", "i", "my", "we",
             "they", "he", "she", "do", "did", "so", "if", "then", "than", "but", "not", "no",
             "can", "will", "just", "have", "has", "had", "been", "would", "could", "should",
             "there", "here", "what", "when", "who", "out", "up", "one", "me", "them", "him"}


def who():
    return Path(sys.argv[0]).name or "cards_from_srt"


def die(msg):
    sys.exit("%s: %s" % (who(), msg))


def note(msg):
    print("%s: %s" % (who(), msg), file=sys.stderr)


def bare(tok):
    """A word with the punctuation taken off, lowercased, for matching."""
    return tok.lower().strip(".,!?;:'\"()[]’“”\u2014-")


# ---------------------------------------------------------------- the window

def window_from_pulls(path, rank):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    pulls = data.get("pulls") if isinstance(data, dict) else data
    if not pulls:
        die("%s has no pulls in it. Run pick_pulls.py --out %s first." % (path, path))
    by_rank = {int(p.get("rank", i + 1)): p for i, p in enumerate(pulls)}
    if rank not in by_rank:
        die("there is no pull %d in %s. It holds %s." %
            (rank, path, ", ".join(str(r) for r in sorted(by_rank))))
    p = by_rank[rank]
    return float(p["start"]), float(p["end"]), p


def words_in_window(words, start, end):
    """A word belongs to the window when its middle does, so no word is half in and half out."""
    return [w for w in words if start <= (w["t0"] + w["t1"]) / 2.0 <= end]


# ---------------------------------------------------------------- speakers and stutters

def mark_speakers(words):
    """Take the speaker's name off the screen, and remember where the talking changed hands.

    Without this a card can run straight through a change of speaker ("that nobody BEN:"), which
    reads as one person saying both halves. The name itself is never a caption.
    """
    out, names, pending = [], 0, False
    for w in words:
        if w.get("cue_first") and SPEAKER_LABEL_TOKEN.match(w["t"]):
            names += 1
            pending = True
            continue
        w = dict(w)
        if pending or w.get("turn"):
            w["turn_start"] = True          # group_cards must not carry a card across this
        pending = False
        out.append(w)
    return out, names


def find_repeats(words):
    """Immediate word repeats: a stutter, or a restart ("the- the the problem")."""
    hits = []
    for i in range(1, len(words)):
        a, b = bare(words[i - 1]["t"]).rstrip("-"), bare(words[i]["t"]).rstrip("-")
        if a and a == b and (words[i]["t0"] - words[i - 1]["t1"]) < STUTTER_GAP:
            hits.append(i)
    return hits


def collapse_repeats(words, hits):
    """Keep the last try, drop the false starts. Opt-in, because this removes the speaker's words.

    It cannot tell a stutter from a deliberate repeat, so "very very" collapses too. That is the
    cost of the flag, and why it is off unless asked for.
    """
    drop, removed = set(i - 1 for i in hits), []
    for i in sorted(drop):
        removed.append(words[i]["t"])
    return [w for i, w in enumerate(words) if i not in drop], removed


# ---------------------------------------------------------------- filler

def strip_filler(words, hedges):
    """Take the filler off the screen. The audio still says it; a caption that prints every "um"
    is harder to read and nobody writes them on purpose.

    Two details that matter. A full stop belonging to a dropped word moves back onto the word
    before it, or the sentence loses its end. And a word dropped from the START of a sentence
    leaves the next word lowercase in the middle of a card ("Um, so today..." -> "so today..."),
    so that word is capitalised. Case is the only thing ever changed; no word is added, replaced
    or reordered.
    """
    singles = set(FILLER_WORDS) | (HEDGE_WORDS if hedges else set())
    pairs = set(FILLER_PAIRS) | (HEDGE_PAIRS if hedges else set())
    kept, dropped, cap_next, i = [], [], False, 0
    while i < len(words):
        tok = words[i]["t"]
        a, b = bare(tok), bare(words[i + 1]["t"]) if i + 1 < len(words) else ""
        # "like," with a comma is filler; "like" without one is the real word. pick_pulls.py
        # draws the same line, so the two scripts agree about what counts as filler.
        comma_like = a == "like" and tok.rstrip("\u201d\u2019\"')").endswith(",")
        take = 2 if (a, b) in pairs else 1 if (a in singles or comma_like) else 0
        if take:
            at_sentence_start = (not kept) or bool(TERMINAL.search(kept[-1]["t"]))
            tail = words[i + take - 1]["t"]
            dropped.append(" ".join(w["t"] for w in words[i:i + take]))
            end = TERMINAL.search(tail)
            if end and kept:
                kept[-1] = dict(kept[-1], t=kept[-1]["t"] + end.group(0))
            elif at_sentence_start or end:
                cap_next = True
            i += take
            continue
        if cap_next and tok[:1].islower() and tok == tok.lower():
            words[i] = dict(words[i], t=tok[:1].upper() + tok[1:])
        cap_next = False
        kept.append(words[i])
        i += 1
    return kept, dropped


# ---------------------------------------------------------------- grouping

def group_cards(words, min_words, max_words):
    """Cut the word stream into cards. Returns [(words, hard_break_after)]."""
    groups, cur = [], []
    for idx, w in enumerate(words):
        cur.append(w)
        nxt = words[idx + 1] if idx + 1 < len(words) else None
        ends_sentence = bool(TERMINAL.search(w["t"]))
        gap = (nxt["t0"] - w["t1"]) if nxt else 0.0
        turn_next = bool(nxt and nxt.get("turn_start"))
        hard = ends_sentence or gap > SENTENCE_GAP or turn_next or nxt is None
        soft = bool(SOFT_END.search(w["t"])) and len(cur) >= min_words
        if hard or soft or len(cur) >= max_words:
            groups.append([list(cur), hard])
            cur = []
    if cur:
        groups.append([list(cur), True])

    # A single word alone on screen reads as a mistake unless a sentence really ended there.
    # Fold it back into the card before it when that card has room and nothing hard divides them.
    merged = []
    for g, hard in groups:
        if (merged and len(g) == 1 and not merged[-1][1]
                and len(merged[-1][0]) + 1 <= max_words):
            merged[-1][0].extend(g)
            merged[-1][1] = hard
        else:
            merged.append([g, hard])

    # An orphan that survived the fold is a sentence's last word stranded because the card before
    # it was already full ("...I was so busy." -> 4 words, then "busy."). Folding cannot help, so
    # rebalance instead: hand one word forward and read 3 + 2 rather than 4 + 1.
    for i in range(1, len(merged)):
        prev_words, prev_hard = merged[i - 1]
        g, _ = merged[i]
        if len(g) == 1 and not prev_hard and len(prev_words) > min_words:
            merged[i - 1][0] = prev_words[:-1]
            merged[i][0] = [prev_words[-1]] + g
    return merged


def time_cards(groups, w_start, w_end):
    """First word in, last word out, then close the flicker-sized gaps and hold the short cards."""
    cards = []
    for g, hard in groups:
        cards.append({"words": g, "hard": hard,
                      "start": max(w_start, g[0]["t0"]), "end": min(w_end, g[-1]["t1"])})
    for i, c in enumerate(cards):
        nxt_start = cards[i + 1]["start"] if i + 1 < len(cards) else w_end
        if nxt_start - c["end"] <= HOLD_GAP:
            c["end"] = nxt_start                    # no blank frame between two cards of one breath
        if c["end"] - c["start"] < MIN_CARD:
            c["end"] = min(nxt_start, c["start"] + MIN_CARD)
        if c["end"] - c["start"] > MAX_CARD:
            c["end"] = c["start"] + MAX_CARD        # let the picture breathe instead of holding stale text
        if c["end"] <= c["start"]:
            c["end"] = min(nxt_start, c["start"] + 0.2)
    return [c for c in cards if c["end"] > c["start"]]


# ---------------------------------------------------------------- accent

def accent_for(card_words, threshold):
    best, best_score = None, 0.0
    for w in card_words:
        b = bare(w["t"])
        if not b or b in STOPWORDS:
            continue
        score = 0.0
        if HAS_DIGIT.search(b):
            score = 3.0
        elif STRONG.match(b):
            score = 2.0
        elif len(b) >= 8:
            score = 1.5
        elif len(b) >= 6:
            score = 1.0
        if score > best_score:
            best, best_score = b, score
    return best if best_score >= threshold else None


# ---------------------------------------------------------------- report

def overlapping_cues(cues, start, end):
    """Cues that overlap in time mean two people talking over each other, or a tool that guessed."""
    n = 0
    for a, b in zip(cues, cues[1:]):
        if b["start"] < a["end"] - 0.10 and b["end"] > start and a["start"] < end:
            n += 1
    return n


def timing_kind(cues):
    """One word per cue means the times are real. Several words means they were interpolated."""
    if not cues:
        return "unknown"
    short = sum(1 for c in cues if len(pp.clean_cue_text(c["text"]).split()) <= 2)
    return "word-level" if short / float(len(cues)) > 0.8 else "interpolated"


def build(args):
    cues = pp.load_cues(args.transcript)
    words = pp.build_words(cues)
    if not words:
        die("no words found in %s." % args.transcript)

    pull = None
    if args.pulls:
        w_start, w_end, pull = window_from_pulls(args.pulls, args.pull)
    else:
        if args.start is None or args.end is None:
            die("give me a window: --start 64 --end 94.5, or --pulls pulls.json --pull 1.")
        w_start, w_end = float(args.start), float(args.end)
    if w_end <= w_start:
        die("the window ends before it starts: start %s, end %s." % (w_start, w_end))

    picked = words_in_window(words, w_start, w_end)
    if not picked:
        last = words[-1]["t1"]
        die("no words between %.2fs and %.2fs. The transcript runs to %.2fs." % (w_start, w_end, last))

    picked, names = mark_speakers(picked)
    if not picked:
        die("that window holds nothing but speaker names.")
    repeats = find_repeats(picked)
    restarts = []
    if repeats and args.collapse_stutters:
        picked, restarts = collapse_repeats(picked, repeats)

    kept, dropped = ([w for w in picked], []) if args.keep_filler else strip_filler(picked, args.strip_hedges)
    if not kept:
        die("every word in that window was filler. Nothing left to put on screen.")

    groups = group_cards(kept, args.min_words, args.max_words)
    cards = time_cards(groups, w_start, w_end)

    threshold = 1.0 if args.accent_loose else 2.0
    out_cards, accents = [], 0
    for c in cards:
        text = " ".join(w["t"] for w in c["words"]).strip()
        card = {"text": text, "start": round(c["start"], 2), "end": round(c["end"], 2)}
        if not args.no_accent:
            a = accent_for(c["words"], threshold)
            if a:
                card["accent"] = [a]
                accents += 1
        out_cards.append(card)

    return {
        "window": (w_start, w_end), "cards": out_cards, "cues": cues, "pull": pull,
        "dropped": dropped, "accents": accents, "timing": timing_kind(cues),
        "words_in": len(picked), "words_out": len(kept),
        "names": names, "repeats": len(repeats), "restarts": restarts,
        "overlap": overlapping_cues(cues, w_start, w_end),
    }


def fill_cut_list(args):
    """Fill every piece's cards in a plan_clips.py cut list, in place.

    A piece is several non-adjacent moments. Each segment gets its own pass over the
    transcript and the cards are concatenated in EDIT order, which is the order the
    renderer plays them. Times stay in RECORDING seconds and the file is marked
    "times": "source", so bin/assemble_clip.py and bin/caption_check.py both map them
    through the segment list rather than each tool guessing a different base.
    """
    path = Path(args.cuts)
    try:
        spec = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        die("no such cut list: %s" % path)
    except json.JSONDecodeError as e:
        die("%s is not readable JSON: %s" % (path, e))
    pieces = spec.get("pieces") if isinstance(spec, dict) else spec
    if not isinstance(pieces, list) or not pieces:
        die("%s carries no 'pieces'. bin/plan_clips.py writes the shape this reads." % path)

    out_path = Path(args.out) if args.out else path
    if out_path.exists() and out_path != path and not args.force:
        die("%s already exists. Pass --force to overwrite it." % out_path)

    total, filled = 0, 0
    for piece in pieces:
        segs = [s for s in piece.get("segments", [])
                if isinstance(s, dict) and s.get("start") is not None and s.get("end") is not None]
        if not segs:
            note("%s has no segments, skipped." % piece.get("piece", "a piece"))
            continue
        cards, kept_any = [], False
        for i, seg in enumerate(segs, 1):
            sub = copy.copy(args)
            sub.start, sub.end, sub.pulls = float(seg["start"]), float(seg["end"]), None
            try:
                r = build(sub)
            except SystemExit:
                note("%s segment %d (%.2f to %.2f) produced no cards. The renderer will play "
                     "it with no text on it." % (piece.get("piece", "?"), i,
                                                 float(seg["start"]), float(seg["end"])))
                continue
            cards.extend(r["cards"])
            kept_any = True
        piece["cards"] = cards
        total += len(cards)
        filled += 1 if kept_any else 0
        note("%-4s %2d segments -> %3d cards" % (piece.get("piece", "?"), len(segs), len(cards)))

    if isinstance(spec, dict):
        spec["times"] = "source"
        spec["_card_times"] = ("Card times are seconds in the recording. assemble_clip.py maps "
                               "them through the segment list, and caption_check.py reads this "
                               "same field. Do not renumber them by hand.")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(spec, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    note("wrote %s: %d cards across %d pieces, times marked source." % (out_path, total, filled))
    note("Read them before you render. Next: python3 bin/caption_check.py %s --transcript %s"
         % (out_path, args.transcript))
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Turn a transcript and a chosen window into a caption_video.py spec.")
    ap.add_argument("transcript", help="SRT, VTT or JSON file, or - for stdin")
    ap.add_argument("--start", type=float, help="window start, seconds in the recording")
    ap.add_argument("--end", type=float, help="window end, seconds in the recording")
    ap.add_argument("--pulls", help="a pick_pulls.py JSON file to take the window from")
    ap.add_argument("--cuts", help="a bin/plan_clips.py cut list. Fills every piece's cards from "
                                   "every one of its segments and writes the file back, instead "
                                   "of making one single-window spec")
    ap.add_argument("--pull", type=int, default=1, help="which pull in that file, by rank (default 1)")
    ap.add_argument("--source", default="footage/your-recording.mp4",
                    help="the video the captions go on, as the spec should name it")
    ap.add_argument("--brand", default="example-brand.json",
                    help="brand file the spec names (default example-brand.json, next to the spec)")
    ap.add_argument("--out", help="where to write the spec (default specs/<source stem>-cards.json)")
    ap.add_argument("--video", help="the finished video path the spec asks for "
                                    "(default ../out/<source stem>-pull.mp4, relative to the spec)")
    ap.add_argument("--print", dest="to_stdout", action="store_true",
                    help="print the spec and write nothing")
    ap.add_argument("--min-words", type=int, default=MIN_WORDS, dest="min_words")
    ap.add_argument("--max-words", type=int, default=MAX_WORDS, dest="max_words")
    ap.add_argument("--keep-filler", action="store_true", help="leave um, uh and you know on screen")
    ap.add_argument("--strip-hedges", action="store_true",
                    help="also drop kind of, sort of, i guess, basically, literally, actually, honestly")
    ap.add_argument("--collapse-stutters", action="store_true", dest="collapse_stutters",
                    help="drop the false starts in a repeat (\"I I I think\" -> \"I think\"). "
                         "Off by default: it removes words the speaker said, and it cannot tell a "
                         "stutter from a deliberate \"very very\"")
    ap.add_argument("--no-accent", action="store_true", help="no highlighted word on any card")
    ap.add_argument("--accent-loose", action="store_true",
                    help="highlight a long word too, not only a number or a turn word")
    ap.add_argument("--focus-x", type=float, default=0.5, dest="focus_x",
                    help="which part of a wide frame survives the vertical crop (default 0.5)")
    ap.add_argument("--force", action="store_true", help="overwrite the spec file if it exists")
    args = ap.parse_args()

    if args.min_words < 1 or args.max_words < args.min_words:
        die("--min-words must be 1 or more and not greater than --max-words.")
    if args.max_words > 8:
        note("--max-words %d is a lot for one glance. Short form reads two to four."
             % args.max_words)

    if args.cuts:
        return fill_cut_list(args)

    r = build(args)
    w_start, w_end = r["window"]
    stem = Path(args.source).stem or "pull"

    spec_path = Path(args.out) if args.out else KIT_ROOT / "specs" / ("%s-cards.json" % stem)
    spec_dir = spec_path.resolve().parent
    if args.video:
        video = args.video
    else:
        want = KIT_ROOT / "out" / ("%s-pull.mp4" % stem)
        try:
            video = os.path.relpath(str(want), str(spec_dir))
        except ValueError:                                   # different drive on Windows
            video = str(want)

    source = args.source
    if not Path(source).is_absolute():
        p = Path(source)
        if not (p.exists() or (spec_dir / p).exists()):
            note("the source %s is not there yet, from here or from next to the spec. The spec "
                 "will still be written; put the file in place before you render." % source)

    spec = {
        "_made_by": "cards_from_srt.py from %s" % Path(args.transcript).name,
        "_timing": ("times are %s. interpolated means a boundary can sit up to about a second from "
                    "the real word: transcribe with -ml 1 for word-level times." % r["timing"]),
        "_check": "python3 bin/caption_video.py %s, then look at the result before anyone else does."
                  % (spec_path.name if args.out or not args.to_stdout else "this-spec.json"),
        "brand": args.brand,
        "source": source,
        "out": video,
        "trim": {"start": round(w_start, 2), "end": round(w_end, 2)},
        "focus_x": args.focus_x,
        "cards": r["cards"],
    }
    if r["pull"] is not None:
        spec["_pull"] = "pull %s of %s, score %s: %s" % (
            r["pull"].get("rank"), Path(args.pulls).name, r["pull"].get("score"),
            r["pull"].get("why_text", "")[:200])

    body = json.dumps(spec, indent=2, ensure_ascii=False)
    if args.to_stdout:
        print(body)
    else:
        if spec_path.exists() and not args.force:
            die("%s already exists. Pass --force to overwrite it, or --out to write somewhere else."
                % spec_path)
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(body + "\n", encoding="utf-8")

    durs = [c["end"] - c["start"] for c in r["cards"]]
    counts = [len(c["text"].split()) for c in r["cards"]]
    gaps = sum(1 for i in range(len(r["cards"]) - 1)
               if r["cards"][i + 1]["start"] - r["cards"][i]["end"] > 0.01)
    note("%d cards over %.2fs (%.2f to %.2f). %d to %d words a card, %.1f average. "
         "On screen %.2fs to %.2fs. %d gaps where nobody is speaking."
         % (len(r["cards"]), w_end - w_start, w_start, w_end, min(counts), max(counts),
            sum(counts) / float(len(counts)), min(durs), max(durs), gaps))
    note("times are %s. %d words in, %d on screen, %d filler dropped%s. %d cards carry an accent."
         % (r["timing"], r["words_in"], r["words_out"], len(r["dropped"]),
            (": " + ", ".join(r["dropped"][:6]) + ("..." if len(r["dropped"]) > 6 else ""))
            if r["dropped"] else "", r["accents"]))
    if not args.to_stdout:
        note("wrote %s. Render it with: python3 bin/caption_video.py %s"
             % (spec_path, spec_path))
    # Everything the script noticed but cannot judge. Silence here would be the dangerous kind.
    if r["names"]:
        note("%d speaker name(s) taken off the screen, and no card is carried across a change of "
             "speaker. Check the pull is one person talking: a clip that cuts between two voices "
             "needs the other half of the exchange to make sense." % r["names"])
    if r["overlap"]:
        note("%d place(s) where cues overlap in time. That is two people talking over each other, "
             "or a transcriber guessing. Card times in those places are not reliable: open the "
             "waveform there before you trust them." % r["overlap"])
    if r["restarts"]:
        note("%d false start(s) dropped: %s. The speaker said them."
             % (len(r["restarts"]), ", ".join(r["restarts"][:6])))
    elif r["repeats"]:
        note("%d immediate word repeat(s) in this window, kept as said (\"I I I think\"). Verbatim "
             "is the default. Pass --collapse-stutters to drop the false starts." % r["repeats"])
    note("Read the cards before you render. These are the speaker's words, cut and timed by a "
         "script that cannot hear them.")


if __name__ == "__main__":
    main()
