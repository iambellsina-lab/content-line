#!/usr/bin/env python3
"""caption_check.py: read a caption card list the way a stranger will, with the sound off.

    python3 bin/caption_check.py cards.json
    python3 bin/caption_check.py cards.json --transcript transcript.txt
    python3 bin/caption_check.py cards.json --transcript t.txt --cuts assembly.json
    python3 bin/caption_check.py cards.json --transcript t.txt --json findings.json
    python3 bin/caption_check.py --selftest

THIS IS NOT A GATE. Say that out loud before using it.

It cannot read. It compares the words on a card against the words the speaker said and
flags the shapes that have gone wrong before. A card can pass every check here and still
read as something the speaker never meant, because meaning lives in things no string
comparison reaches: who is on screen, what the face is doing, what the last card primed
the reader to expect. A person still has to watch every card muted, once, before anything
renders. This narrows what that person is hunting for. It does not replace them.

WHY IT EXISTS

Four rounds of caption work went into one batch of six reels. Almost every defect found
was the same failure wearing different clothes: a card that, read alone with the sound
off by somebody scrolling, says something the speaker did not mean. The worst of them was
caught one step before rendering:

    she said:  "There is not one thing that I want to be tamed from."
    the card:  "i want to be tamed from"

The word that carried the meaning was the one left off the card. Burned in, that card
says the opposite of her sentence and the opposite of the whole piece. There is no fixing
it after rendering: the text is in the pixels.

So the checks here are all one question asked seven ways. Does the card still carry the
part of the sentence that decided what it meant?

WHAT IT CHECKS

Meaning (needs a transcript; silently unavailable without one):
    stranded negation      her clause says not / never / nothing / doesn't, the card does not
    stranded condition     her clause says if / when / unless / until / because, the card drops it
    stranded comparison    her clause says than / rather / instead / versus and the card keeps one
                           side, or the card itself opens or closes on one of those words
    stranded pair          she said it twice with two endings and a negation inside the repeated
                           part, and the card shows one ending. "it's not a moral to be a
                           millionaire, and it's not a moral to be broke" with half on screen
    stranded attribution   the card reads as her instruction when the line was voiced, quoted,
                           asked as a question, or offered as permission she was granting

Mechanics (needs no transcript):
    stranded continuation  a card opening on and / but / so / that / which / because, which is
                           the back half of a sentence whose front half is not on screen
    out of range           a card starting before zero, ending past the piece, or ending first
    overlap                two cards on screen at once
    hook repeat            a card restating the pinned hook already on screen
    word ceiling           more words than the eye takes in one glance
    known mishearing       a phrase the transcriber got wrong, reaching a card. The list ships in
                           fixtures/transcription-errors.json and is seven real ones, including a
                           name misheard, "coach" heard as "couch" and "peace" heard as "piece"

HOW HARD EACH FINDING PUSHES

    blocker   it changes what the card means, or it breaks the render
    review    a shape that has gone wrong before and may be fine here. A dropped condition on
              a card that is only a fragment goes here: "art out of joy" with its "if" left off
              misleads nobody, because a fragment does not assert anything
    note      tidying

WHAT IT DOES NOT CHECK, and these are real gaps, not quibbles

    Measured against the six reels this was built from, it flagged 15 of the 20 card defects a
    four-round hand pass had recorded. The five it missed, named so nobody assumes otherwise:

      a card referring to something the edit cut, "the line i really liked" with no line
      a subject dropped where no negation, condition or comparison was involved. Three of the
        five misses are this one shape: "nothing to do with each other" dropping "they have",
        "really struggles with coming on here" dropping "my benevolent heart", "hard because we
        don't have them" dropping "they're hard conversations"
      a word on a card that she never said. "packages" was added to one card and this sees nothing

    And two of the twenty-two recorded entries were not card defects at all, so nothing that
    reads cards could ever have found them: a line that needed a card and had none, and a stale
    duration in the work order. A MISSING card is invisible here. That was a third of the real
    defect list.

    It also knows nothing about the picture: the face, the crop, the moment the card lands.

HOW IT FINDS HER LINE

Every meaning check compares a card against one sentence of the recording, so it has to
find that sentence. The transcript is reassembled into sentences with times (cue
boundaries in a machine transcript fall mid-sentence, which is why the reassembly is
needed), and then:

    with --cuts   card times are finished-reel times. The cut list gives each segment's
                  source in and out, segments play in edit order, so the finished time maps
                  back to a real source window. Sentences are looked for there first.
    without       card times are assumed to be source times, which is what a single-window
                  job spec carries.
    either way    the sentence is chosen by word overlap with the card, so a card that was
                  reworded still finds its line, and a card whose best match is weak is
                  reported as unmatched rather than guessed at.

Attribution looks two sentences further back than the card's own, because that is where
"it says," and "I'm like," live. "Please stop growing for the love of God" is her brain
talking, and the only thing that says so is two sentences earlier.

INPUT SHAPES IT ACCEPTS

    {"cards": [{"text", "start", "end"}], "hook": {"text": ...}}     a reel_cut.py job spec
    {"pieces": [...]} / [{...}, {...}]                               a batch, one entry per piece
    [{"text", "start", "end"}, ...]                                  a bare card list
    [[start, end, "text"], ...]                                      a bare card list, triples

A piece may name its cards "caption_cards" or "cards", its hook "hook_text" or
"hook": {"text"}, and itself "piece", "id", "name" or "filename".

PROVING THE CHECKS FIRE

    python3 bin/caption_check.py --selftest

    Eighteen cases. Eleven are one card against one line she really said, including the one
    that nearly shipped, and the repaired version of it, which has to come back clean. Seven
    are a fixture piece carrying one of every mechanical fault. Run this after any edit here:
    a check that finds nothing on a real card list should mean the card list is clean, not that
    the check is asleep. The mishearing check found nothing in either real card list, which is
    why the fixture carries two.

EXIT

    0  nothing found
    1  something found. Every finding prints the card, its time, her line and what is wrong
    2  it could not run: a file missing, a shape it does not understand

Standard library only, except that it imports the kit's own pick_pulls.py to read
transcripts, so this script and the rest of the kit never disagree about the words.
"""
import argparse
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pick_pulls as pp                                     # noqa: E402  (same folder, stdlib only)

KIT_ROOT = Path(__file__).resolve().parent.parent
ERRORS_FILE = KIT_ROOT / "fixtures" / "transcription-errors.json"

MAX_WORDS = 7            # a caption read in one glance. cards_from_srt.py writes 2 to 4; a
                         # hand-built card runs longer, and 7 is where the real batch topped out
EPS = 0.02               # two cards this close are touching, not overlapping
SENTENCE_GAP = 2.5       # silence this long ends a sentence whatever the punctuation says
MATCH_MIN = 0.50         # below this share of the card's words, the source line is a guess
ATTR_LOOKBACK = 2        # sentences before the card's own to search for "it says," / "I'm like,"
PAIR_MIN_NGRAM = 3       # a repeated phrase shorter than this is not a parallel construction
CLAUSE_MIN = 0.50        # below this share, the clause the card came from was not found either
NEIGHBOUR_GAP = 1.20     # a card this close is read in the same breath as the one before it

# Which checks a neighbouring card can answer for, and which it cannot. A card ending on "than"
# advertises that it continues, so the next card finishes the comparison and the reader follows.
# A card that silently drops a "not" advertises nothing, and the real batch proves the point: the
# card before "i want to be tamed from" was "there is not one thing", touching it with no gap at
# all, and the pair still read as an inversion to four separate passes. So comparison takes
# neighbour credit and negation does not.

NEGATION = {
    "not", "no", "never", "none", "nothing", "nobody", "noone", "nowhere", "neither", "nor",
    "cannot", "without", "hardly", "barely", "scarcely", "rarely", "seldom", "lack", "lacks",
    "lacking", "untrue", "unable",
}
# "stop" is deliberately NOT here. "stop buying the program" is an imperative, which the
# attribution check already reads. Counting it as a negation flagged every card downstream of
# one of her "stop ..." hooks, and she opens five of six pieces that way.
NEG_SUFFIX = re.compile(r"n't$")          # don't, doesn't, isn't, won't, wouldn't, ain't

# Only subordinators that put a condition on the clause they govern. "as", "since", "while",
# "before" and "after" were in this set on the first run and produced 51 findings on 171 cards,
# nearly all of them a card sitting in some other clause of a long reconstructed sentence.
CONDITION = {"if", "when", "whenever", "unless", "until", "because"}

COMPARISON = {"than", "rather", "instead", "versus", "vs", "compared", "opposed", "whereas"}

# A card opening on one of these is the second half of something. The first half is not on
# screen and the reader has no way to supply it. Added after reading the real batch: two of the
# six blockers the hand pass found were exactly this and none of the four stranded checks above
# reaches them. "that's" and "there's" are not here, because a contraction carries its own verb
# and stands up alone.
CONTINUATION = {"and", "but", "or", "so", "then", "yet", "that", "which", "who", "whose",
                "because", "while", "whereas"}

# A card opening on one of these reads as an order given to whoever is looking at it.
DIRECTIVE = {
    "stop", "start", "go", "do", "dont", "don't", "make", "take", "get", "keep", "give", "let",
    "ask", "say", "tell", "think", "quit", "remember", "forget", "choose", "build", "write",
    "call", "chase", "sell", "buy", "come", "show", "put", "use", "try", "look", "listen",
    "believe", "be", "have", "stay", "leave", "move", "pick", "drop", "run", "push", "pull",
    "please", "never", "always",
}

# Somebody other than the speaker is talking, or the speaker is quoting her own head.
VOICING = re.compile(
    r"\b(?:i|he|she|it|they|we|you|brain|mind|ego|voice|heart|body|spirit|everyone|people|"
    r"somebody|someone)\s+(?:was\s+|were\s+|am\s+|is\s+|are\s+)?"
    r"(?:say|says|said|saying|tell|tells|told|telling|think|thinks|thought|thinking|ask|asks|"
    r"asked|asking)\b"
    r"|\bi'?m\s+like\b|\byou'?re\s+like\b|\bthey'?re\s+like\b|\bit'?s\s+like\b"
    r"|\bgoes\s*,|\bwent\s*,", re.I)
# "want" and "wants" were in this pattern on the first run and matched her own "I want to go
# after everything that I desire", which is her, not somebody she is quoting. They are out.

# Permission or desire she is granting, which an imperative card turns into an order.
PERMISSION = re.compile(
    r"\b(?:you|we|i)\s*(?:'?(?:d|ll|re|ve))?\s*"
    r"(?:can|could|may|might|should|get\s+to|are\s+allowed\s+to|want\s+to|wanna|have\s+permission)\b"
    r"|\bdo\s+you\s+want\s+to\b|\bdo\s+you\s+need\s+to\b|\ball\s+you\s+have\s+to\b", re.I)

SMART_SINGLE = (chr(0x2018), chr(0x2019), chr(0x201B))
SMART_DOUBLE = (chr(0x201C), chr(0x201D), chr(0x201F))
LONG_DASH = (chr(0x2014), chr(0x2013), chr(0x2012), "--")

WORD = re.compile(r"[a-z0-9$']+")

FINITE = {"is", "are", "was", "were", "am", "has", "have", "had", "do", "does", "did", "can",
          "could", "will", "would", "shall", "should", "may", "might", "must", "becomes",
          "became", "gets", "got", "goes", "went", "comes", "came", "feels", "felt", "needs",
          "need", "makes", "made", "takes", "took", "wins", "win", "stays", "happens", "means",
          "says", "tells", "wants", "lives", "costs"}
SUBJECT = {"i", "you", "we", "they", "he", "she", "it", "that", "this", "there", "who", "what",
           "nothing", "everything", "nobody", "everybody", "money", "people"}
CONTRACTED = ("'s", "'re", "'m", "'ll", "'d", "'ve")
DETERMINER = {"the", "a", "an", "this", "that", "these", "those", "my", "your", "his", "her",
              "their", "our", "its", "no", "some", "every", "all"}


# ------------------------------------------------------------------ small text helpers

def die(msg: str):
    """Exit 2: it could not run. Exit 1 is reserved for having found something."""
    print(msg, file=sys.stderr)
    return SystemExit(2)


def flat(s: str) -> str:
    """One spelling of a string: ASCII quotes, no case, single spaces."""
    s = str(s)
    for ch in SMART_SINGLE:
        s = s.replace(ch, "'")
    for ch in SMART_DOUBLE:
        s = s.replace(ch, '"')
    for ch in LONG_DASH:
        s = s.replace(ch, " -- ")           # a dash is a clause boundary, so it survives as one
    return re.sub(r"\s+", " ", s).strip().lower()


def toks(s: str) -> list:
    return WORD.findall(flat(s))


def negations(s: str) -> list:
    found = []
    for t in toks(s):
        if t in NEGATION or NEG_SUFFIX.search(t):
            found.append(t)
    return found


def hits(s: str, vocab: set) -> list:
    return [t for t in toks(s) if t in vocab]


COORD = {"and", "but", "or", "so", "then", "yet", "because"}
CLAUSE_SPLIT = re.compile(r"\s*[,;:]\s*|\s+--+\s*|\s*--+\s+")


def clauses(text: str) -> list:
    """A sentence cut into the pieces a subordinator or a negation can actually govern.

    Her recorded sentences run long: "You don't have to pick-- it's not a moral to be-- like a
    millionaire, and it's not a moral to be broke" is one sentence carrying three clauses and
    two negations. A card drawn from the third clause is not made wrong by a word in the first,
    and checking it against the whole sentence is what made the first run of this script flag
    half of every card list it was given.
    """
    out = []
    for part in CLAUSE_SPLIT.split(flat(text)):
        part = part.strip()
        if not part:
            continue
        pieces, buf = [], []
        for w in part.split():
            if w in ("and", "but", "or") and len(buf) >= 3:
                pieces.append(" ".join(buf))
                buf = [w]
            else:
                buf.append(w)
        if buf:
            pieces.append(" ".join(buf))
        out += [x for x in pieces if x]
    return out or [flat(text)]


def lead(clause: str) -> str:
    """The first word of a clause that is not just glue."""
    t = toks(clause)
    i = 0
    while i < len(t) and t[i] in COORD and i < 2:
        i += 1
    return t[i] if i < len(t) else ""


def scope(card_text: str, cl: list):
    """The run of clauses the card was drawn from, and the clause just before it.

    A card can straddle a comma, so runs of one, two and three clauses are tried and the best
    word overlap wins. The clause before the run comes back separately: a subordinate clause
    attaches to the clause on its right, which is how "when you're outgrowing," reaches
    "you're freaking depressed".
    """
    best, best_i, best_n = None, 0, 1
    for n in (1, 2, 3):
        for i in range(max(1, len(cl) - n + 1)):
            window = " ".join(cl[i:i + n])
            sc = overlap(card_text, window)
            if best is None or sc > best + 1e-9:
                best, best_i, best_n = sc, i, n
    window = " ".join(cl[best_i:best_i + best_n])
    prev = cl[best_i - 1] if best_i > 0 else None
    return window, prev, (best or 0.0)


def stands_alone(text: str) -> bool:
    """Would this card be a whole sentence if it were the only thing on screen?

    This is what decides how hard to push. A fragment with a word missing is incomplete, and a
    reader can see that it is incomplete. A complete sentence with a word missing is a claim,
    and the reader has no way to know a word is gone. "art out of joy" with its "if" left off
    misleads nobody. "you're freaking depressed" with its "when" left off is a diagnosis aimed
    at whoever is looking.
    """
    t = toks(text)
    if not t:
        return False
    if t[0] in DIRECTIVE:
        return True                     # an imperative is already a whole sentence
    for i, w in enumerate(t):
        if w.endswith(CONTRACTED):
            return True
        if w in SUBJECT or w in DETERMINER:
            for nxt in t[i + 1:i + 4]:
                if nxt in FINITE or nxt.endswith(CONTRACTED):
                    return True
    return False


def governed(card_text: str, sentence_text: str, vocab: set):
    """The words from vocab that govern this card's clause but are not on the card.

    A word counts as governing when it is inside the clauses the card came from, or when it
    opens the clause immediately before them, which is where a subordinate clause sits.
    """
    cl = clauses(sentence_text)
    window, prev, _ = scope(card_text, cl)
    text = window
    if prev is not None and lead(prev) in vocab:
        text = prev + ", " + window
    on_card = set(hits(card_text, vocab))
    return [t for t in hits(text, vocab) if t not in on_card], text


def governing_negations(card_text: str, sentence_text: str):
    cl = clauses(sentence_text)
    window, prev, _ = scope(card_text, cl)
    text = window
    if prev is not None and (lead(prev) in NEGATION or NEG_SUFFIX.search(lead(prev) or "x")):
        text = prev + ", " + window
    return negations(text), text


def overlap(card: str, line: str) -> float:
    """Share of the card's words that appear in the line. 1.0 means every one."""
    ct, lt = toks(card), set(toks(line))
    if not ct:
        return 0.0
    return sum(1 for t in ct if t in lt) / len(ct)


def similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, flat(a), flat(b)).ratio()


def fmt(t) -> str:
    return "?" if t is None else f"{float(t):.2f}"


# ------------------------------------------------------------------ reading the card list

def _cards_of(obj):
    for key in ("caption_cards", "cards"):
        if isinstance(obj, dict) and isinstance(obj.get(key), list):
            return obj[key]
    return None


def _norm_cards(raw, where):
    out = []
    for i, c in enumerate(raw):
        if isinstance(c, dict):
            if "text" not in c:
                raise ValueError(f"{where} card {i + 1} has no 'text'")
            out.append({"text": str(c["text"]), "start": _num(c.get("start")),
                        "end": _num(c.get("end")), "n": i + 1})
        elif isinstance(c, (list, tuple)) and len(c) >= 3:
            out.append({"text": str(c[2]), "start": _num(c[0]), "end": _num(c[1]), "n": i + 1})
        else:
            raise ValueError(f"{where} card {i + 1} is neither an object nor a [start, end, text]")
    return out


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _hook_of(obj):
    if not isinstance(obj, dict):
        return None
    h = obj.get("hook_text")
    if isinstance(h, str) and h.strip():
        return h.strip()
    h = obj.get("hook")
    if isinstance(h, str) and h.strip():
        return h.strip()
    if isinstance(h, dict) and isinstance(h.get("text"), str) and h["text"].strip():
        return h["text"].strip()
    return None


def _name_of(obj, fallback):
    if isinstance(obj, dict):
        for key in ("piece", "id", "name", "filename"):
            v = obj.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return fallback


def _segments_of(obj):
    if not isinstance(obj, dict):
        return None
    segs = obj.get("segments")
    if not isinstance(segs, list):
        return None
    out = []
    for s in segs:
        if isinstance(s, dict) and _num(s.get("start")) is not None and _num(s.get("end")) is not None:
            out.append({"start": float(s["start"]), "end": float(s["end"]),
                        "text": str(s.get("text", ""))})
    return out or None


def load_pieces_from_object(obj):
    """One piece dict straight to the internal shape, for the built-in fixture."""
    cards = _norm_cards(_cards_of(obj), "fixture")
    return {"name": _name_of(obj, "fixture"), "duration": _num(obj.get("duration")),
            "hook": _hook_of(obj), "segments": _segments_of(obj), "cards": cards,
            "times": obj.get("times")}


def load_pieces(path: Path):
    """Any of the four shapes in the docstring, out comes a list of pieces."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise die(f"caption_check: no such file: {path}")
    except json.JSONDecodeError as e:
        raise die(f"caption_check: {path} is not readable JSON: {e}")

    blocks = None
    if isinstance(data, dict):
        if isinstance(data.get("pieces"), list):
            blocks = data["pieces"]
        elif _cards_of(data) is not None:
            blocks = [data]
    elif isinstance(data, list):
        if data and isinstance(data[0], dict) and _cards_of(data[0]) is not None:
            blocks = data
        elif data and (isinstance(data[0], (list, tuple))
                       or (isinstance(data[0], dict) and "text" in data[0])):
            blocks = [{"cards": data}]
    if blocks is None:
        raise die(f"caption_check: {path} holds no card list this understands.\n"
            "  Expected a job spec with 'cards', a batch with 'pieces', or a bare list of cards.")

    spec_times = None
    if isinstance(data, dict):
        t = data.get("times")
        if isinstance(t, str) and t.strip().lower() in ("clip", "source"):
            spec_times = t.strip().lower()

    pieces = []
    for i, b in enumerate(blocks):
        raw = _cards_of(b)
        if raw is None:
            continue
        try:
            cards = _norm_cards(raw, f"piece {i + 1}")
        except ValueError as e:
            raise die(f"caption_check: {e}")
        pieces.append({"name": _name_of(b, f"piece {i + 1}"),
                       "duration": _num(b.get("duration")),
                       "hook": _hook_of(b),
                       "segments": _segments_of(b),
                       "cards": cards,
                       "times": (b.get("times") if isinstance(b.get("times"), str)
                                 else spec_times)})
    if not pieces:
        raise die(f"caption_check: {path} has pieces but none of them carry cards.")
    return pieces


def rebase_cards_to_clip(piece):
    """Source-time cards to finished-clip times, so every later check lines up.

    cards_from_srt.py writes card times in RECORDING seconds, one window at a time.
    plan_clips.py writes segments in EDIT order. Joining the two by hand is where the
    first batch lost time, so the join happens here instead: a card whose start falls
    inside a segment is moved to where that moment actually plays in the finished piece.
    Returns the number of cards it could not place.
    """
    segs = piece.get("segments")
    if not segs:
        return 0
    spans, run = [], 0.0
    for s in segs:
        span = s["end"] - s["start"]
        if span <= 0:
            continue
        spans.append((s["start"], s["end"], run))
        run += span
    dropped = []
    for card in piece["cards"]:
        cs, ce = card.get("start"), card.get("end")
        if cs is None:
            continue
        hit = next((sp for sp in spans if sp[0] - EPS <= cs < sp[1] + EPS), None)
        if hit is None:
            dropped.append(card)
            continue
        a, b, base = hit
        card["start"] = base + (cs - a)
        if ce is not None:
            card["end"] = base + (min(ce, b) - a)
    if dropped:
        keep = [c for c in piece["cards"] if c not in dropped]
        piece["cards"] = keep
        piece["dropped_cards"] = dropped
    return len(dropped)


def load_cuts(path: Path):
    """A cut list, out comes {piece name: [segments]}. Segments carry SOURCE times."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise die(f"caption_check: no such cut list: {path}")
    except json.JSONDecodeError as e:
        raise die(f"caption_check: {path} is not readable JSON: {e}")
    blocks = data.get("pieces") if isinstance(data, dict) else data
    if isinstance(data, dict) and blocks is None:
        blocks = [data]
    if not isinstance(blocks, list):
        raise die(f"caption_check: {path} holds no segment list this understands.")
    out = {}
    for i, b in enumerate(blocks):
        segs = _segments_of(b)
        if segs:
            out[_name_of(b, f"piece {i + 1}")] = segs
    if not out:
        raise die(f"caption_check: {path} carries no 'segments' with 'start' and 'end'.\n"
            "  A cut list is [{\"piece\": ..., \"segments\": [{\"start\", \"end\", \"text\"}]}].")
    return out


# ------------------------------------------------------------------ the recording

class Recording:
    """The transcript as sentences with times, which is the unit a card is compared against."""

    def __init__(self, cues):
        self.sentences = []
        buf, start, end = [], None, None
        for c in cues:
            text = pp.clean_cue_text(c["text"]).strip()
            if not text:
                continue
            if start is not None and c["start"] - end > SENTENCE_GAP and buf:
                self._close(buf, start, end)
                buf, start = [], None
            if start is None:
                start = c["start"]
            buf.append(text)
            end = c["end"]
            if re.search(r"[.!?]['\")\]]*$", text):
                self._close(buf, start, end)
                buf, start = [], None
        if buf:
            self._close(buf, start, end)

    def _close(self, buf, start, end):
        text = re.sub(r"\s+", " ", " ".join(buf)).strip()
        if text:
            self.sentences.append({"text": text, "start": start, "end": end,
                                   "i": len(self.sentences)})

    def best(self, windows):
        """The sentence in these source windows that best matches a card, and its index."""
        pool = [s for s in self.sentences
                if any(s["end"] > a and s["start"] < b for a, b in windows)] or self.sentences
        return pool

    def before(self, sentence, n):
        i = sentence["i"]
        return self.sentences[max(0, i - n):i]


def load_recording(path: Path):
    try:
        cues = pp.load_cues(str(path))
    except SystemExit as e:
        raise die(f"caption_check: transcript unreadable. {e}")
    except FileNotFoundError:
        raise die(f"caption_check: no such transcript: {path}")
    rec = Recording(cues)
    if not rec.sentences:
        raise die(f"caption_check: {path} parsed to no sentences.")
    return rec


def source_windows(piece, card):
    """Where in the recording this card's finished time sits.

    With segments, the finished reel is the segments concatenated in EDIT order, so a
    finished time is walked back through the running total. Without them, the card's own
    times are already source times.
    """
    segs = piece.get("segments")
    cs, ce = card["start"], card["end"]
    if cs is None:
        return []
    if ce is None or ce <= cs:
        ce = cs + 0.1
    if not segs:
        return [(cs, ce)]
    out, run = [], 0.0
    for s in segs:
        span = s["end"] - s["start"]
        if span <= 0:
            continue
        fin_a, fin_b = run, run + span
        run = fin_b
        if ce <= fin_a or cs >= fin_b:
            continue
        a = s["start"] + max(0.0, cs - fin_a)
        b = s["start"] + min(span, ce - fin_a)
        out.append((a, b))
    return out or [(cs, ce)]


# ------------------------------------------------------------------ the checks

TAIL_STOP = {"a", "an", "the", "to", "be", "is", "are", "was", "of", "in", "on", "it", "it's",
             "that", "and", "or", "but", "so", "like", "just", "very", "then", "i", "you", "we"}


def longest_run(a, b):
    """How many of a's words appear in b as one unbroken run."""
    m = difflib.SequenceMatcher(None, a, b).find_longest_match(0, len(a), 0, len(b))
    return m.size


def repeated_negated_phrase(sentence_text):
    """The phrase a sentence says twice with a negation inside it, and the two endings.

    "it's not a moral to be like a millionaire, and it's not a moral to be broke" says
    "it's not a moral to be" twice and finishes it two different ways. A card showing one
    ending and not the other reverses the even-handedness of the sentence, which is the
    whole point of saying it twice.
    """
    t = toks(sentence_text)
    for n in range(min(8, len(t) // 2), PAIR_MIN_NGRAM - 1, -1):
        at = {}
        for i in range(len(t) - n + 1):
            gram = tuple(t[i:i + n])
            if gram not in at:
                at[gram] = [i]
            elif i - at[gram][-1] >= n:
                at[gram].append(i)
        for gram, idxs in at.items():
            if len(idxs) < 2:
                continue
            if not any(w in NEGATION or NEG_SUFFIX.search(w) for w in gram):
                continue
            tails = []
            for i in idxs:
                tail = [w for w in t[i + n:i + n + 5] if w not in TAIL_STOP and len(w) > 2]
                tails.append(tail[:3])
            tails = [x for x in tails if x]
            if len(tails) < 2 or len({tuple(x) for x in tails}) < 2:
                continue
            return " ".join(gram), tails
    return None, None


def check_meaning(card, sentence, rec, add, neighbours=()):
    line = sentence["text"]

    src_neg, neg_scope = governing_negations(card["text"], line)
    if src_neg and not negations(card["text"]):
        add("stranded-negation", "blocker",
            f"the clause this card came from turns on {'/'.join(sorted(set(src_neg)))} "
            f"(\"{neg_scope}\") and the card carries no negation, so read alone it can say the "
            f"opposite of what she said")

    src_cond, cond_scope = governed(card["text"], line, CONDITION)
    if src_cond:
        if stands_alone(card["text"]):
            add("stranded-condition", "blocker",
                f"her clause is conditional on '{src_cond[0]}' (\"{cond_scope}\"), the card drops "
                f"it, and the card still reads as a complete statement, so alone it states flatly "
                f"what she said only under a condition")
        else:
            add("stranded-condition", "review",
                f"her clause is conditional on '{src_cond[0]}' (\"{cond_scope}\") and the card "
                f"drops it. The card is a fragment, so it asserts nothing on its own. Read it in "
                f"sequence and decide")

    src_cmp, cmp_scope = governed(card["text"], line, COMPARISON)
    card_cmp = hits(card["text"], COMPARISON)
    before, after = neighbours if neighbours else (None, None)
    carried = [c for c in (before, after) if c and hits(c["text"], COMPARISON)]
    if src_cmp and not card_cmp and not carried:
        add("stranded-comparison", "blocker",
            f"her clause compares two things with '{src_cmp[0]}' (\"{cmp_scope}\"), the card "
            f"keeps one side, and no card beside it carries the other")
    elif card_cmp:
        ct = toks(card["text"])
        if ct and ct[0] in COMPARISON:
            add("stranded-comparison", "blocker",
                f"the card opens on '{ct[0]}', so it is half a comparison with the other half "
                f"already gone from the screen")
        elif ct and ct[-1] in COMPARISON and after is None:
            add("stranded-comparison", "blocker",
                f"the card ends on '{ct[-1]}' and no card follows within {NEIGHBOUR_GAP}s, so the "
                f"comparison it opens is never closed")

    pair, tails = repeated_negated_phrase(line)
    if pair and longest_run(toks(pair), toks(card["text"])) >= PAIR_MIN_NGRAM:
        on_card = set(toks(card["text"]))
        shown = [any(w in on_card for w in tail) for tail in tails]
        if any(shown) and not all(shown):
            add("stranded-pair", "blocker",
                f"her line says '{pair}' twice and finishes it two ways "
                f"({'; '.join(' '.join(x) for x in tails)}). The card shows one of them, so the "
                f"balance the repetition was there to carry is gone")

    ct = toks(card["text"])
    if ct and ct[0] in DIRECTIVE and not VOICING.search(card["text"]):
        window, prev, _ = scope(card["text"], clauses(line))
        near = window if prev is None else prev + ", " + window
        context = rec.before(sentence, ATTR_LOOKBACK)
        voiced = next((x for x in reversed(context) if VOICING.search(x["text"])), None)
        if VOICING.search(near):
            add("stranded-attribution", "blocker",
                f"the card reads as her own instruction and her own clause says it is voiced or "
                f"quoted speech (\"{near}\")")
        elif voiced is not None:
            add("stranded-attribution", "blocker",
                f"the card reads as her own instruction, and {fmt(voiced['start'])}s says the "
                f"line is somebody else talking: \"{voiced['text']}\"")
        elif PERMISSION.search(near) and not PERMISSION.search(card["text"]):
            add("stranded-attribution", "blocker",
                f"her clause grants permission rather than giving an order (\"{near}\") and the "
                f"card gives the order")
        elif line.rstrip().endswith("?") and not card["text"].rstrip().endswith("?"):
            add("stranded-attribution", "blocker",
                f"her line is a question (\"{line}\") and the card is an instruction")


def check_mechanics(piece, cards, hook, errors, max_words, findings, mk):
    dur = piece.get("duration")
    for card in cards:
        add = mk(card)
        if card["start"] is None or card["end"] is None:
            add("out-of-range", "blocker", "the card has no start or no end")
        else:
            if card["start"] < -EPS:
                add("out-of-range", "blocker", "the card starts before the piece does")
            if card["end"] <= card["start"] + EPS:
                add("out-of-range", "blocker", "the card ends at or before it starts")
            if dur is not None and card["end"] > dur + EPS:
                add("out-of-range", "blocker",
                    f"the card ends at {fmt(card['end'])}s, past the piece's {fmt(dur)}s")

        ct = toks(card["text"])
        if ct and ct[0] in CONTINUATION:
            rest = " ".join(ct[1:])
            if stands_alone(rest):
                add("stranded-continuation", "review",
                    f"the card opens on '{ct[0]}', which points back at a card the reader may no "
                    f"longer be looking at. What follows it is a whole sentence, so the card holds "
                    f"up. Drop the '{ct[0]}' or leave it")
            else:
                add("stranded-continuation", "blocker",
                    f"the card opens on '{ct[0]}' and what follows is not a sentence, so it is the "
                    f"back half of something whose front half is not on screen. Read alone it "
                    f"attaches to whatever the reader supplies, which is usually the reader")

        words = card["text"].split()
        if len(words) > max_words:
            add("word-ceiling", "note",
                f"{len(words)} words, over the {max_words} a reader takes in one glance")

        if hook:
            if similar(card["text"], hook) >= 0.85:
                add("hook-repeat", "note", f"the card restates the pinned hook: \"{hook}\"")
            else:
                ch, hh = set(toks(card["text"])), set(toks(hook))
                if ch and len(ch & hh) >= 4 and (ch <= hh or hh <= ch):
                    add("hook-repeat", "note",
                        f"the card is inside the pinned hook already on screen: \"{hook}\"")

        low = flat(card["text"])
        for e in errors:
            heard = flat(e["heard"])
            if re.search(r"(?<![a-z0-9'])" + re.escape(heard) + r"(?![a-z0-9'])", low):
                add("known-mishearing", "blocker",
                    f"the card carries \"{e['heard']}\", which the transcriber misheard. "
                    f"She said \"{e['said']}\"")

    timed = sorted([c for c in cards if c["start"] is not None and c["end"] is not None],
                   key=lambda c: (c["start"], c["end"]))
    for a, b in zip(timed, timed[1:]):
        if b["start"] < a["end"] - EPS:
            mk(b)("overlap", "blocker",
                  f"it comes up at {fmt(b['start'])}s while card {a['n']} "
                  f"(\"{a['text']}\") is still on screen until {fmt(a['end'])}s")


def check_piece(piece, rec, errors, max_words, strict):
    findings = []
    unmatched = []

    def mk(card):
        def add(kind, level, why, line=None):
            findings.append({"piece": piece["name"], "card": card["n"], "text": card["text"],
                             "start": card["start"], "end": card["end"],
                             "kind": kind, "level": level, "why": why, "line": line})
        return add

    check_mechanics(piece, piece["cards"], piece.get("hook"), errors, max_words, findings, mk)

    if rec is not None:
        timed = sorted([c for c in piece["cards"]
                        if c["start"] is not None and c["end"] is not None],
                       key=lambda c: c["start"])
        for card in piece["cards"]:
            wins = source_windows(piece, card)
            if not wins:
                continue
            pool = rec.best(wins)
            scored = [(overlap(card["text"], s["text"]), s) for s in pool]
            score, sentence = max(scored, key=lambda x: x[0]) if scored else (0.0, None)
            if sentence is None or score < MATCH_MIN:
                unmatched.append(dict(card, reason="no sentence in the transcript matches it"))
                continue
            _, _, clause_score = scope(card["text"], clauses(sentence["text"]))
            if clause_score < CLAUSE_MIN:
                unmatched.append(dict(card, reason=(
                    "it matches the sentence at "
                    f"{sentence['start']:.2f}s but not any one clause of it, so there is no "
                    "scope to judge a dropped word against")))
                continue
            add = mk(card)

            def tagged(kind, level, why, _add=add, _s=sentence):
                _add(kind, level, why, _s["text"])

            here = next((i for i, c in enumerate(timed) if c is card), None)
            before = after = None
            if here is not None:
                if here > 0 and card["start"] is not None and \
                        card["start"] - (timed[here - 1]["end"] or 0) <= NEIGHBOUR_GAP:
                    before = timed[here - 1]
                if here + 1 < len(timed) and card["end"] is not None and \
                        (timed[here + 1]["start"] or 0) - card["end"] <= NEIGHBOUR_GAP:
                    after = timed[here + 1]
            check_meaning(card, sentence, rec, tagged, (before, after))
            if strict:
                ct = toks(card["text"])
                TAIL = {"at", "to", "from", "of", "with", "for", "in", "on", "about", "by",
                        "and", "or", "but", "that", "than", "as", "is", "was", "are", "the", "a"}
                if ct and ct[-1] in TAIL and not card["text"].rstrip().endswith("?"):
                    tagged("dangling-tail", "note",
                           f"the card ends on '{ct[-1]}' with what it points at left off")
    return findings, unmatched


# ------------------------------------------------------------------ reporting

LEVEL_ORDER = {"blocker": 0, "review": 1, "note": 2}


def report(all_findings, unmatched, pieces, rec, strict, max_words):
    out = []
    w = out.append
    w("caption_check: reading every card as a stranger would, with the sound off.")
    w("")
    total_cards = sum(len(p["cards"]) for p in pieces)
    if rec is None:
        w("NO TRANSCRIPT GIVEN, so no meaning check ran. Only timing, the hook, the word")
        w("ceiling and the known mishearings were checked. Pass --transcript for the rest.")
        w("")

    for piece in pieces:
        f = [x for x in all_findings if x["piece"] == piece["name"]]
        um = [c for c in unmatched if c["piece"] == piece["name"]]
        head = f"{piece['name']}: {len(piece['cards'])} cards"
        if piece.get("duration") is not None:
            head += f", {fmt(piece['duration'])}s"
        head += f" | {len(f)} finding" + ("" if len(f) == 1 else "s")
        if um:
            head += f", {len(um)} card" + ("" if len(um) == 1 else "s") + " with no source line"
        w(head)
        if not f and not um:
            w("    nothing found")
        for x in sorted(f, key=lambda x: (LEVEL_ORDER.get(x["level"], 9), x["start"] or 0)):
            w(f"    [{x['level']:<7}] {x['kind']}")
            w(f"      card {x['card']} at {fmt(x['start'])}-{fmt(x['end'])}s: \"{x['text']}\"")
            if x.get("line"):
                w(f"      her line:  \"{x['line']}\"")
            w(f"      wrong:     {x['why']}")
        for c in um:
            w(f"    [unmatched] card {c['n']} at {fmt(c['start'])}-{fmt(c['end'])}s: "
              f"\"{c['text']}\"")
            w(f"      {c.get('reason', 'no match')}. No meaning check ran on it. "
              "Read this one yourself.")
        w("")

    kinds = {}
    for x in all_findings:
        kinds[x["kind"]] = kinds.get(x["kind"], 0) + 1
    blockers = sum(1 for x in all_findings if x["level"] == "blocker")
    reviews = sum(1 for x in all_findings if x["level"] == "review")
    notes = len(all_findings) - blockers - reviews
    w("-" * 78)
    w(f"{total_cards} cards across {len(pieces)} piece"
      + ("" if len(pieces) == 1 else "s")
      + f". {len(all_findings)} findings: {blockers} blocker"
      + ("" if blockers == 1 else "s") + f", {reviews} to review, {notes} note"
      + ("" if notes == 1 else "s")
      + f". {len(unmatched)} card" + ("" if len(unmatched) == 1 else "s") + " unmatched.")
    w("A blocker changes what a card means or breaks the render. Something to review is a shape")
    w("that has gone wrong before and may be fine here. A note is tidying.")
    for k in sorted(kinds, key=lambda k: -kinds[k]):
        w(f"    {kinds[k]:>4}  {k}")
    w("")
    w("THIS IS NOT A GATE. It compares strings. It does not read.")
    w("It cannot see a card that should not be there, a line that needed a card and has none,")
    w("a word added that she never said, or a subject dropped with no negation involved.")
    w("Half the defects in the batch this was built from were of exactly those kinds.")
    w("Somebody still watches every card muted, once, before anything renders.")
    if not strict:
        w("")
        w("--strict adds one more pass: cards ending on a dangling preposition. Off by default")
        w("because it is noisier than the rest.")
    return "\n".join(out)


# ------------------------------------------------------------------ self test

SELFTEST = [
    # (what it is, card text, her line, kind expected or None)
    ("the real one, caught one step before rendering",
     "i want to be tamed from",
     "There is not one thing that I want to be tamed from.", "stranded-negation"),
    ("a condition dropped",
     "you're freaking depressed",
     "And when you're outgrowing, you're freaking depressed.", "stranded-condition"),
    ("one side of a comparison",
     "far more imperative",
     "It means your incongruence with yourself is far more imperative than the actual "
     "tangible of how to do anything ever.", "stranded-comparison"),
    ("half a comparison on the card itself",
     "versus me feeding the story",
     "Versus me feeding the story of, this is a hungry person, and they're separate from me.",
     "stranded-comparison"),
    ("one half of a negated pair",
     "not a moral to be broke",
     "It's not a moral to be like a millionaire, and it's not a moral to be broke.",
     "stranded-pair"),
    ("permission turned into an order",
     "go chase after your dreams",
     "You can go chase after your dreams, and you can make the world a better place.",
     "stranded-attribution"),
    ("a question turned into an order",
     "make $400,000 a year",
     "Do you want to make $400,000 a year?", "stranded-attribution"),
    ("the whole clause kept, which is the fix",
     "when you're outgrowing, you're freaking depressed",
     "And when you're outgrowing, you're freaking depressed.", None),
    ("a negation kept",
     "nothing i'd be tamed from",
     "There is not one thing that I want to be tamed from.", None),
    ("a plain statement, nothing stranded",
     "signed up for a diet",
     "How many times have you signed up for a diet, trend, or whatever?", None),
    ("attribution carried on the card",
     "brain: please stop growing",
     "It says, OK, we figured this out. Sounds good, let's call it a day. Please stop growing.",
     None),
]


# One piece carrying one of every mechanical fault, so that a check finding nothing on a real
# card list means the card list is clean and not that the check is asleep. Every one of these is
# a fault the real batch either had or was one step away from having.
MECH_PIECE = {
    "piece": "mechanics fixture",
    "duration": 30.0,
    "hook_text": "stop telling people you're too chaotic",
    "caption_cards": [
        {"text": "stop telling people you're too chaotic", "start": 1.0, "end": 3.0},
        {"text": "a $10,000 couch is what you sell", "start": 4.0, "end": 6.0},
        {"text": "what number, Belia?", "start": 6.2, "end": 8.0},
        {"text": "this card has far too many words on it to be read in one glance",
         "start": 9.0, "end": 11.0},
        {"text": "and start asking", "start": 10.5, "end": 12.0},
        {"text": "ends before it starts", "start": 14.0, "end": 13.0},
        {"text": "past the end of the piece", "start": 29.0, "end": 41.0},
    ],
}
MECH_WANT = {
    1: {"hook-repeat"},
    2: {"known-mishearing"},
    3: {"known-mishearing"},
    4: {"word-ceiling"},
    5: {"stranded-continuation", "overlap"},
    6: {"out-of-range"},
    7: {"out-of-range"},
}


def selftest():
    passed = failed = 0
    print("MEANING, one card against one line she said\n")
    for what, card_text, line, expect in SELFTEST:
        rec = Recording([{"start": 0.0, "end": 5.0, "text": line}])
        sentence = rec.sentences[-1]
        card = {"text": card_text, "start": 0.0, "end": 2.0, "n": 1}
        got = []
        check_meaning(card, sentence, rec,
                      lambda k, lvl, why: got.append({"kind": k}))
        kinds = {g["kind"] for g in got if isinstance(g, dict) and "kind" in g}
        ok = (expect in kinds) if expect else not kinds
        print(f"  {'ok  ' if ok else 'FAIL'}  {what}")
        print(f"          card \"{card_text}\"")
        print(f"          want {expect or 'nothing'}, got {sorted(kinds) or 'nothing'}")
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)

    print("\nMECHANICS, which need no transcript\n")
    piece = load_pieces_from_object(MECH_PIECE)
    errors = load_errors(None)
    if not errors:
        print(f"  FAIL  the mishearing list at {ERRORS_FILE} is missing or empty")
        failed += 1
    findings, _ = check_piece(piece, None, errors, MAX_WORDS, False)
    by = {}
    for f in findings:
        by.setdefault(f["card"], set()).add(f["kind"])
    for n, want in MECH_WANT.items():
        got = by.get(n, set())
        ok = want <= got
        card = piece["cards"][n - 1]
        print(f"  {'ok  ' if ok else 'FAIL'}  card {n}: \"{card['text'][:52]}\"")
        print(f"          want {sorted(want)}, got {sorted(got) or 'nothing'}")
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)

    print(f"\n{passed} passed, {failed} failed")
    if not failed:
        print("\nThese pass. That still does not make this a gate. It means the checks fire.")
    return 0 if not failed else 1


# ------------------------------------------------------------------ main

def load_errors(path):
    if path is None:
        if not ERRORS_FILE.exists():
            return []
        path = ERRORS_FILE
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise die(f"caption_check: no such mishearing list: {path}")
    except json.JSONDecodeError as e:
        raise die(f"caption_check: {path} is not readable JSON: {e}")
    rows = data.get("errors") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise die(f"caption_check: {path} needs a list under 'errors'.")
    out = []
    for r in rows:
        if isinstance(r, dict) and r.get("heard"):
            out.append({"heard": str(r["heard"]), "said": str(r.get("said", "?"))})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="caption_check.py", add_help=True,
        description="Flag caption cards that read wrong alone with the sound off. Not a gate.")
    ap.add_argument("cards", nargs="?", help="the card list: a job spec, a batch, or a bare list")
    ap.add_argument("--transcript", help="what she actually said, with times. "
                                        "SRT, VTT, JSON or whisper.cpp bracket format")
    ap.add_argument("--cuts", help="the assembly, so finished card times map back to the "
                                   "recording. Needed for a non-linear cut")
    ap.add_argument("--errors", help="a mishearing list, overriding "
                                     "fixtures/transcription-errors.json")
    ap.add_argument("--max-words", type=int, default=MAX_WORDS, dest="max_words",
                    help=f"word ceiling for one card (default {MAX_WORDS})")
    ap.add_argument("--card-times", choices=("clip", "source", "auto"), default="auto",
                    help="what the card times mean. 'clip' is seconds into the finished "
                         "piece, 'source' is seconds in the recording, which is what "
                         "cards_from_srt.py writes. 'auto' (default) reads the cut list's "
                         "own \"times\" field and assumes clip when it says nothing")
    ap.add_argument("--strict", action="store_true",
                    help="also flag cards ending on a dangling preposition")
    ap.add_argument("--json", dest="json_out", help="write the findings to this file as well")
    ap.add_argument("--quiet", action="store_true", help="print the summary only")
    ap.add_argument("--selftest", action="store_true",
                    help="run the built-in cases, including the real one that nearly shipped")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.cards:
        ap.print_usage()
        print("caption_check: give it a card list, or --selftest.")
        return 2

    pieces = load_pieces(Path(args.cards))
    if args.cuts:
        cuts = load_cuts(Path(args.cuts))
        missed = []
        for p in pieces:
            if p["name"] in cuts:
                p["segments"] = cuts[p["name"]]
            elif not p.get("segments"):
                missed.append(p["name"])
        if missed:
            print(f"caption_check: the cut list names "
                  f"{', '.join(sorted(cuts)) or 'nothing'}; it has no segments for "
                  f"{', '.join(missed)}. Those cards are read as source times.", file=sys.stderr)

    for p in pieces:
        base = args.card_times
        if base == "auto":
            base = (p.get("times") or "clip").lower()
        if base == "source" and p.get("segments"):
            lost = rebase_cards_to_clip(p)
            if lost:
                print(f"caption_check: {p['name']}: {lost} card(s) sit outside every segment "
                      f"of this piece, so they would never appear on screen. Dropped from the "
                      f"check and listed in the report.", file=sys.stderr)

    rec = load_recording(Path(args.transcript)) if args.transcript else None
    errors = load_errors(args.errors)

    all_findings, unmatched = [], []
    for p in pieces:
        f, um = check_piece(p, rec, errors, args.max_words, args.strict)
        all_findings += f
        for c in um:
            c = dict(c)
            c["piece"] = p["name"]
            unmatched.append(c)

    text = report(all_findings, unmatched, pieces, rec, args.strict, args.max_words)
    if args.quiet:
        text = text.split("-" * 78, 1)[-1].strip()
    print(text)

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(
            {"cards": sum(len(p["cards"]) for p in pieces),
             "findings": all_findings,
             "unmatched": [{"piece": c["piece"], "card": c["n"], "text": c["text"],
                            "start": c["start"], "end": c["end"]} for c in unmatched],
             "not_a_gate": "This flags shapes that have gone wrong before. It does not read. "
                           "A card can pass every check here and still read wrong."},
            indent=1), encoding="utf-8")
    return 1 if all_findings else 0


if __name__ == "__main__":
    sys.exit(main())
