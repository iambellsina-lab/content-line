#!/usr/bin/env python3
"""caption_repair.py: propose a fix for every card caption_check.py flagged. Proposals only.

    python3 bin/caption_repair.py cards.json --transcript work/t.srt --out work/proposed.json
    python3 bin/caption_repair.py cards.json --transcript work/t.srt --cuts work/cuts.json \
        --out work/proposed.json
    python3 bin/caption_repair.py cards.json --transcript work/t.srt \
        --findings work/findings.json --out work/proposed.json
    python3 bin/caption_repair.py cards.json --transcript work/t.srt --compare work/final.json
    python3 bin/caption_repair.py --selftest

WHY IT EXISTS

caption_check.py reads a card list cold and finds the cards that read wrong with the sound
off. On the first real batch it found 68 findings, 39 of them blockers, and the kit had no
next step: a buyer got a list of problems and no path. The repair logic existed, but only as
something done by hand over three rounds on one batch of six reels.

This is that hand work written down. It takes the checker's findings plus the transcript and
proposes one fix per flagged card.

IT PROPOSES. IT DOES NOT REWRITE.

Nothing is changed in place. The proposed card list goes to a new file named with --out, and
the diff prints for a person to read first. The input file is never written, and --out is
refused if it names the input.

THE THREE MOVES, in the priority order the hand pass used

    1  add the governing clause as its own earlier card, so the fragment lands with its subject
    2  rewrite the card to carry the whole thought, inside the word ceiling
    3  cut the card and let the audio carry that beat

Prefer 1 or 3. Air is always safe. A wrong card is not.

A fourth outcome is hold: no change proposed, because the words that decided the meaning are
already on screen beside the card and the reader reads the run in one breath. A fifth is
retime, which is for a card out of range or on screen over its neighbour: a timing fault, not
a meaning one.

IT CANNOT JUDGE MEANING, AND HERE IS EXACTLY WHERE THAT BITES

Every word in every proposal is her own, taken contiguously from the transcript line the card
came from. This script invents no wording. It cannot tell whether a card is true to what she
meant, which card a run of fragments is really building towards, or whether a line is one she
would want on screen at all. So where it cannot build a card out of her own words inside the
ceiling, its answer is to cut the card, and it says it refused rather than pretending it chose.

The one exception to "her own words" is the speaker label on quoted speech, "brain: ..." in
front of a line her brain is saying, and that label is only ever the noun her own sentence
uses. Where that sentence says only "it", the script refuses, because resolving "it" to a
speaker is reading, and reading is what it cannot do.

THE FAILURE THIS EXISTS TO STOP

    her line:  "There is not one thing that I want to be tamed from."
    the card:  "i want to be tamed from"

Alone and muted, that card states the opposite of the line. Note what this script does with
it, because it is the honest shape of the thing. Run on that card list on 2026-10-08 it printed
this and nothing cleverer:

    MOVE 3, cut the card and let the audio carry the beat
    refused:  move 1 cannot run: there is no 1.2s of air in front of this card to put a new
              one in. The cards either side of it are already touching
    refused:  move 2 cannot run: her words from "not" to "from" are 10 and the ceiling is 7.
              Only filler may be dropped

The hand pass merged the pair into five words instead, which is a better card than air. A cut
is not what a person would have chosen there, and it is safe, which is the trade this script is
allowed to make and a person is not.

HOW A PROPOSAL IS CHECKED BEFORE IT IS OFFERED

The checker is the arbiter, not this script's own opinion of its work. Every candidate card is
put into a copy of the piece and caption_check.py is run over the whole piece again. A
candidate is accepted only if the flagged card's own findings go down and no other card picks
up a new one. That is what stops the obvious own goal: "than the actual tangible of how" fixes
a dropped comparison by opening the card on "than", which the checker flags just as hard.

The constructive passes run until they stop making progress, before anything is cut. That
order matters and the real batch is why. Four cards in a row came out of one sentence about
incongruence; restoring "is ... than" to the second one makes the whole run read as the
sentence again, and the other three need no change at all. Repair the one card first and the
checker clears the rest by itself. Cut first and three good cards are gone.

WHAT IT WILL NOT DO

    invent a word she did not say, including a subject that is only implied
    drop anything from the middle of her line except the filler cards_from_srt.py already
      drops, so the two scripts never disagree about what filler is
    propose a card carrying two negations: a double negative read muted in two seconds is the
      hardest shape there is, and the hand pass cut one for exactly that reason
    move any segment in or out point. Captions only. The cut list is not touched
    grant a neighbouring card credit for a dropped negation. caption_check.py's own comment
      says why: the card before "i want to be tamed from" was "there is not one thing",
      touching it with no gap, and the pair still read as an inversion to four separate passes

WHERE THE NEW TIMES COME FROM, and this is the weakest number in the file

A new card from move 1 is placed by word density: her line's start and end are known from the
transcript, and a word's time inside the line is interpolated by word count. Nothing here has
heard the audio. If she pauses mid-line, the card lands early or late. Every proposal with a
new time says so in the diff, and the right next step is to listen to that join.

MEASURED, NOT ASSUMED, AND NOT TUNED UNTIL IT LOOKED BETTER

--compare takes a card list somebody has already repaired by hand and scores the proposals
against it. Both runs below are from this machine on 2026-10-08.

On the kit's own run, the four clips whose 39 blockers are the reason this file exists:
79 cards, 39 blockers on 30 of them. 30 proposals: 6 rewrites, 13 cuts, 11 holds. Reading the
proposed list back through caption_check.py leaves 12 blockers, every one of them a card held
on purpose with the words that decide it on the card beside it.

On the six reels a person repaired by hand over three rounds: 171 cards, 32 blockers on 30 of
them. 31 proposals: 1 add, 4 rewrites, 17 cuts, 9 holds. Scored against what the person
actually did:

    15 of 31 agree with the move the person made. 7 of those 15 are a card the person also
       cut or rewrote. The other 8 are a card both left alone, which is the easiest kind of
       agreement and is counted apart for that reason
    16 differ. 8 are a card this cut and the person rewrote. 6 are a card this cut and the
       person left. 1 it held and the person rewrote, 1 it rewrote and the person left
    17 proposals are refusals to build text. The person cut 3 of those same cards
    42 cards the person changed were never flagged by the checker at all, so no proposal
       exists for them. That is not this script's gap, it is the checker's, and it is the
       larger of the two

Two of the four rewrites came out word for word identical to the person's: "is far more
imperative than" and "when you're outgrowing, you're freaking depressed". The one add landed
within a tenth of a second of where the person put their own governing-clause card.

Read the shape of that honestly. Where this script and a person disagree, it is almost always
the same disagreement: it cuts and they found words. On 14 of the 16 differences the person
kept a card this would have taken off the screen. A person reading the diff gets those 14 back
in a minute, because the diff names the card, her line and the reason the text could not be
built. A person who never sees a diff at all gets 39 blockers and no path, which is where the
kit was this morning.

EXIT

    0  nothing to propose
    1  proposals printed, and written if --out was given
    2  it could not run

Standard library only. It imports the kit's own caption_check.py, cards_from_srt.py and
pick_pulls.py so that this script and the rest of the kit never disagree about the words, the
filler, or what counts as a fault.
"""
import argparse
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import caption_check as cc                                  # noqa: E402  (same folder, stdlib)
import cards_from_srt as cfs                                # noqa: E402
import pick_pulls as pp                                     # noqa: E402

# A few of caption_check.py's readers are used by name here, the ones starting with an
# underscore included. That is on purpose: a second implementation of "which key holds the
# cards" is a second thing to keep in step, and the whole point of importing the checker is
# that the two cannot disagree about what a card list is.

MIN_CARD = 1.20          # a card shorter than this is a flash, not a read
MIN_GAP = 0.15           # the air either side of a new card. Silence between cards is good
ROUNDS = 6               # constructive passes before anything is cut. It stops early when stuck
LEAD_AUX = True          # pull one copula or auxiliary in front of a rewrite when it fits
CUT_SHARE_LOUD = 0.33    # cut more than this share of a piece and the report says so loudly
PAIR_FLOOR = 0.40        # --compare only: below this, two cards are not the same card

# The only words ever dropped from the middle of her line to fit the ceiling. This is
# cards_from_srt.py's own filler list, imported rather than retyped, so the two scripts cannot
# drift apart about what filler is. Bare "like" is a real word in both and stays.
FILLER = set(cfs.FILLER_WORDS)
FILLER_PAIRS = set(cfs.FILLER_PAIRS)
HEDGES = set(cfs.HEDGE_WORDS)
HEDGE_PAIRS = set(cfs.HEDGE_PAIRS)

# caption_check.py's lead() calls these words glue when a clause opens on one. A card built
# here does not open on glue either.
COORD_GLUE = {"and", "but", "or", "so", "then", "yet"}

# Nouns a line can name as the one talking. Only these reach a speaker label, and only when her
# own sentence uses the word. "it" is deliberately absent: resolving it is reading.
SPEAKERS = {"brain", "mind", "ego", "voice", "heart", "body", "spirit", "head", "soul"}
SPEAKER_LABEL = re.compile(r"^\s*[a-z]+:\s*[\"']", re.I)
SAYS = re.compile(r"\b(say|says|said|saying|tell|tells|told|telling|think|thinks|thought|"
                  r"thinking|ask|asks|asked|asking|goes|went)\b|\bis\s+like\b|\bare\s+like\b"
                  r"|\bwas\s+like\b|\bwere\s+like\b|'?s\s+like\b|'?re\s+like\b", re.I)

MOVE_LABEL = {
    "add": "MOVE 1, add the governing clause as its own earlier card",
    "rewrite": "MOVE 2, rewrite the card to carry the whole thought",
    "cut": "MOVE 3, cut the card and let the audio carry the beat",
    "hold": "HOLD, no change proposed",
    "retime": "RETIME, a timing fault rather than a meaning one",
}
def die(msg: str):
    print(msg, file=sys.stderr)
    return SystemExit(2)


def fmt(t):
    return cc.fmt(t)


# ------------------------------------------------------------------ her words, kept as hers

def split_line(text: str):
    """Her sentence as one Word per spoken word, with the punctuation read, not thrown away.

    Three things come off each word: what goes on a card, a spelling to match on, and whether a
    clause ended there. Pure punctuation and the stumble dashes drop out of all three.

    Output words keep "$400,000" and "don't" whole, which a tokeniser that splits on
    non-letters does not: the first run through this produced "$400 000" on a card. The same
    spelling is used on both sides of every match in this file, so the card and her line cannot
    disagree about what a word is.
    """
    out = []
    for raw in str(text).split():
        w = raw
        for chars, to in ((cc.SMART_SINGLE, "'"), (cc.SMART_DOUBLE, '"')):
            for ch in chars:
                w = w.replace(ch, to)
        ends = bool(re.search(r"[,;:.!?\u2014-]+[\"')\]]*$", w))
        screen = w.strip("\"()[]{}").lstrip(".,;:!?-").rstrip(".-")
        norm = re.sub(r"[^a-z0-9$']", "", screen.lower())
        if not norm:
            continue
        out.append((screen, norm, ends))
    return out


def spell(text):
    """A card's words in the same spelling split_line uses, so the two can be matched."""
    return [n for _, n, _ in split_line(text)]


def droppable(words, i, hedges):
    """How many words at i are filler, by cards_from_srt.py's list. 0 means keep it."""
    a = words[i][1]
    b = words[i + 1][1] if i + 1 < len(words) else ""
    if (a, b) in FILLER_PAIRS or (hedges and (a, b) in HEDGE_PAIRS):
        return 2
    if a in FILLER or (hedges and a in HEDGES):
        return 1
    return 0


def fit_ceiling(words, ceiling, hedges=False, keep=()):
    """Her words trimmed to the ceiling by dropping filler only, or None if it will not fit.

    keep is a set of indexes that may never be dropped, which is how the word that decided the
    meaning survives the trim. A leading coordinator goes first: caption_check.py's own lead()
    calls those words glue, and a new card does not need to open on glue.
    """
    words = list(words)
    while words and words[0][1] in COORD_GLUE and 0 not in keep and len(words) > 2:
        words = words[1:]
        keep = {i - 1 for i in keep if i > 0}
    if len(words) <= ceiling:
        return words
    out, i = [], 0
    while i < len(words):
        n = droppable(words, i, hedges)
        if n and all((i + k) not in keep for k in range(n)):
            i += n
            continue
        out.append(words[i])
        i += 1
    return out if len(out) <= ceiling else None


def say(words, case, question=False):
    """A card's text from her words, in the case this piece already uses."""
    text = " ".join(w[0] for w in words).strip(" ,;:")
    if question and not text.endswith("?"):
        text += "?"
    if case == "lower":
        text = text.lower()
    elif case == "sentence" and text[:1].islower():
        text = text[:1].upper() + text[1:]
    return re.sub(r"\s+", " ", text)


def piece_case(piece):
    """Which case this card list is written in, so a proposal does not look pasted in."""
    firsts = [c["text"].strip()[:1] for c in piece["cards"] if c["text"].strip()]
    letters = [c for c in firsts if c.isalpha()]
    if not letters:
        return "keep"
    low = sum(1 for c in letters if c.islower())
    return "lower" if low >= 0.8 * len(letters) else "sentence"


def run_before(spelling, phrase, limit):
    """Where the last unbroken run of these words sits before limit, or None.

    "i want to" has to be the one standing in front of the card's own words, not the "to" of a
    "wanting to" fifteen words earlier. Looking for the words one at a time found that "to" and
    built a card out of half the sentence.
    """
    n = len(phrase)
    if not n:
        return None
    best = None
    for i in range(0, min(limit, len(spelling) - n + 1)):
        if spelling[i:i + n] == phrase:
            best = i
    return best


class WordClock:
    """A time for every word in the recording, interpolated inside its own cue.

    A cue is two to four seconds, so a word's time inside one is a guess from word count. It is
    the same guess the hand pass made and wrote down as its least reliable number. Nothing here
    has heard the audio.
    """

    def __init__(self, cues):
        self.words = []
        for c in cues:
            text = pp.clean_cue_text(c["text"]).strip()
            words = split_line(text)
            if not words:
                continue
            span = max(0.01, float(c["end"]) - float(c["start"]))
            step = span / len(words)
            for i, (_, norm, _) in enumerate(words):
                a = float(c["start"]) + i * step
                self.words.append((norm, a, a + step))

    def span(self, sentence, lo, hi):
        """Source start and end of words lo..hi of a sentence, by its tokens and its times."""
        toks = spell(sentence["text"])
        if not toks:
            return None
        at = self._find(toks, sentence["start"])
        if at is None:
            if sentence["end"] <= sentence["start"]:
                return None
            step = (sentence["end"] - sentence["start"]) / len(toks)
            return (sentence["start"] + lo * step, sentence["start"] + (hi + 1) * step)
        lo = max(0, min(lo, len(toks) - 1))
        hi = max(lo, min(hi, len(toks) - 1))
        return (self.words[at + lo][1], self.words[at + hi][2])

    def _find(self, toks, near):
        best, best_d = None, None
        n = len(toks)
        for i in range(len(self.words) - n + 1):
            if self.words[i][0] != toks[0]:
                continue
            if [w[0] for w in self.words[i:i + n]] != toks:
                continue
            d = abs(self.words[i][1] - near)
            if best_d is None or d < best_d:
                best, best_d = i, d
            if d < 0.5:
                break
        return best


class TimeMap:
    """Finished time to source time and back, through the segment list in edit order."""

    def __init__(self, segments):
        self.spans = []
        run = 0.0
        for s in segments or []:
            span = s["end"] - s["start"]
            if span <= 0:
                continue
            self.spans.append((s["start"], s["end"], run))
            run += span
        self.total = run

    @property
    def flat(self):
        return not self.spans

    def to_source(self, t, edge="start"):
        """Finished time back to source time. edge decides what happens on a segment join.

        A card starting exactly where one segment ends and the next begins belongs to the next
        one, and a card ending there belongs to the one before. Reading both as the earlier
        segment sent four cards back out with a start in one segment and an end in another,
        which the checker then read as four cards running past the end of the piece.
        """
        if self.flat:
            return t
        last = len(self.spans) - 1
        for i, (a, b, base) in enumerate(self.spans):
            span = b - a
            lo = base - cc.EPS if (edge == "start" or i == 0) else base + cc.EPS
            hi = base + span + cc.EPS if (edge == "end" or i == last) else base + span - cc.EPS
            if lo <= t <= hi:
                return a + (t - base)
        return None

    def to_finished(self, t):
        if self.flat:
            return t
        for a, b, base in self.spans:
            if a - cc.EPS <= t <= b + cc.EPS:
                return base + (t - a)
        return None

    def window(self, a, b):
        """A source range to a finished range, or None when any of it was cut out of the piece."""
        fa, fb = self.to_finished(a), self.to_finished(b)
        if fa is None or fb is None or fb <= fa:
            return None
        return (fa, fb)


# ------------------------------------------------------------------ finding her line

def sentence_for(piece, card, rec):
    """The transcript sentence this card came from, chosen the way caption_check.py chooses it."""
    if rec is None or card["start"] is None:
        return None
    wins = cc.source_windows(piece, card)
    if not wins:
        return None
    pool = rec.best(wins)
    scored = [(cc.overlap(card["text"], s["text"]), s) for s in pool]
    if not scored:
        return None
    score, sentence = max(scored, key=lambda x: x[0])
    return sentence if score >= cc.MATCH_MIN else None


def locate(card_text, words):
    """Where the card's words sit in her sentence, as a first and last index."""
    ct, st = spell(card_text), [n for _, n, _ in words]
    if not ct or not st:
        return None
    blocks = [b for b in difflib.SequenceMatcher(None, st, ct).get_matching_blocks() if b.size]
    if not blocks:
        return None
    return (blocks[0].a, blocks[-1].a + blocks[-1].size - 1)


def governing(kind, card, sentence_text):
    """The words in her line that decided this card's meaning and are not on the card."""
    if kind == "stranded-negation":
        words, _ = cc.governing_negations(card["text"], sentence_text)
        return [w for w in words if w not in cc.negations(card["text"])]
    if kind == "stranded-condition":
        words, _ = cc.governed(card["text"], sentence_text, cc.CONDITION)
        return words
    if kind == "stranded-comparison":
        words, _ = cc.governed(card["text"], sentence_text, cc.COMPARISON)
        return words or cc.hits(card["text"], cc.COMPARISON)
    if kind == "stranded-pair":
        pair, _ = cc.repeated_negated_phrase(sentence_text)
        return cc.toks(pair) if pair else []
    return []


def speaker_of(text):
    """The noun this text names as the one talking, or None. "it" never qualifies.

    The label on a card of quoted speech is only ever a word her own sentence used. Where the
    sentence says "it says", there is no label to be had without working out what "it" is, and
    working that out is reading.
    """
    low = cc.flat(text)
    for m in re.finditer(r"\b(" + "|".join(sorted(SPEAKERS)) + r")\b", low):
        if SAYS.search(low[m.end():m.end() + 24]):
            return m.group(1)
    return None


def attribution_shape(card, sentence, rec):
    """Which of caption_check.py's attribution branches raised this finding.

    Both the repair and the run credit ask this one function, so a card flagged for quoted
    speech is never cleared by a card beside it that only grants permission. The fixture
    catches that: "please stop growing" sits 0.8s after "you can go chase after your dreams",
    and the permission on the second says nothing about whose voice the first is.
    """
    near, prev, _ = cc.scope(card["text"], cc.clauses(sentence["text"]))
    context = near if prev is None else prev + ", " + near
    voiced = next((s for s in reversed(rec.before(sentence, cc.ATTR_LOOKBACK))
                   if cc.VOICING.search(s["text"])), None)
    if cc.VOICING.search(context):
        return ("voiced", context, context)
    if voiced is not None:
        return ("voiced", context, voiced["text"])
    if cc.PERMISSION.search(cc.flat(context)) and not cc.PERMISSION.search(card["text"]):
        return ("permission", context, cc.PERMISSION.search(cc.flat(context)).group(0))
    if sentence["text"].rstrip().endswith("?") and not card["text"].rstrip().endswith("?"):
        return ("question", context, sentence["text"])
    return (None, context, None)


def no(why):
    """A move declining, with the reason it declined, so the diff says more than "refused"."""
    return {"move": None, "refused": why}


# ------------------------------------------------------------------ running the checker

def findings_at(piece, cards, rec, errors, ceiling, levels):
    """caption_check.py run over a trial card list, filtered to the levels being repaired."""
    trial = dict(piece)
    trial["cards"] = sorted(cards, key=lambda c: (c["start"] if c["start"] is not None else 0,
                                                  c["n"]))
    found, _ = cc.check_piece(trial, rec, errors, ceiling, False)
    return [f for f in found if f["level"] in levels]


def by_card(found):
    out = {}
    for f in found:
        out.setdefault(f["card"], []).append(f)
    return out


def accepts(before, after, n):
    """Is this candidate an improvement by the checker's own reading?

    The flagged card's own findings have to go down, and no other card may pick up a new one.
    That second half is what stops a fix that strands the card beside it: "than the actual
    tangible of how" answers a dropped comparison by opening the card on "than", which the
    checker flags just as hard.
    """
    b, a = by_card(before), by_card(after)
    if len(a.get(n, [])) >= len(b.get(n, [])):
        return False
    return no_collateral(before, after, {n})


def no_collateral(before, after, ignore):
    """Did any card other than the ones named pick up a finding it did not have?"""
    b, a = by_card(before), by_card(after)
    for card in set(list(b) + list(a)):
        if card in ignore:
            continue
        if len(a.get(card, [])) > len(b.get(card, [])):
            return False
    return True


def accepts_add(before, after, n, new_n):
    """A move 1 add is judged differently, and this is the one place the checker cannot help.

    caption_check.py reads every card alone and gives a card no credit for the card before it
    when a condition or a subject was dropped. That is deliberate and it is right: a reader
    scrolling may never have seen the card before. So adding the governing clause as its own
    earlier card leaves the original card's own finding standing, and no amount of correct
    repair will clear it.

    What can be checked is that the new card is clean, that it carries the governing words, and
    that nothing else in the piece got worse. The original finding stays in the report, marked
    as answered by a new card, and a person reads the pair and decides.
    """
    a = by_card(after)
    if a.get(new_n):
        return False
    if len(a.get(n, [])) > len(by_card(before).get(n, [])):
        return False
    return no_collateral(before, after, {n, new_n})


# ------------------------------------------------------------------ the three moves

def free_air(cards, card):
    """The gap in front of this card that a new card could sit in, in finished time."""
    start = card["start"]
    if start is None:
        return None
    earlier = [c for c in cards
               if c is not card and c["end"] is not None and c["end"] <= start + cc.EPS]
    floor = max([c["end"] for c in earlier], default=0.0)
    a, b = floor + MIN_GAP, start - MIN_GAP
    if b - a < MIN_CARD:
        return None
    return (a, b)


def try_add(cards, card, kinds, sentence, clock, tmap, ceiling, case, hedges):
    """Move 1. The governing clause, placed in the air before the card, as its own card.

    This is the move the hand pass reached for first and the one that is hardest to earn. It
    needs four things at once: the governing word in front of the card's own words, a clause
    around it that stands up alone, air before the card to put it in, and that air to line up
    with when she actually said those words. On a card list already packed wall to wall, the
    third of those is usually what stops it, and the diff says which one did.
    """
    if sentence is None or clock is None:
        return no("move 1 needs the transcript to find the clause. None was given")
    words = split_line(sentence["text"])
    span = locate(card["text"], words)
    if span is None:
        return no("move 1 could not find the card's words inside her line")
    st = [n for _, n, _ in words]
    want = []
    for kind in kinds:
        want += [w for w in governing(kind, card, sentence["text"]) if w in st]
    if not want:
        return no("move 1 found no governing word of hers to make a card out of")
    idxs = [i for i, n in enumerate(st) if n in want and i < span[0]]
    if not idxs:
        return no("move 1 cannot run: the word that decides the meaning comes after the card's "
                  "own words in her line, so there is no earlier clause to put in front of it")
    g = min(idxs)
    air = free_air(cards, card)
    if air is None:
        return no(f"move 1 cannot run: there is no {MIN_CARD}s of air in front of this card to "
                  f"put a new one in. The cards either side of it are already touching")
    body = fit_ceiling(words[g:span[0]], ceiling, hedges, keep={0}) or \
        fit_ceiling(words[g:g + ceiling], ceiling, hedges, keep={0})
    if not body or len(body) < 2:
        return no("move 1 cannot run: the governing clause is one word long, which is not a card")
    text = say(body, case)
    if not cc.stands_alone(text):
        return no(f"move 1 cannot run: her clause \"{text}\" is itself a fragment, so putting "
                  f"it on its own card adds a second card that says nothing")
    last = g + len(body) - 1
    src = clock.span(sentence, g, min(last, span[0] - 1))
    win = tmap.window(*src) if src else None
    if src and win is None:
        return no("move 1 cannot run: she said those words in a part of the tape this piece "
                  "cut out, so there is nowhere in the finished piece they belong")
    a, b = air
    if win:
        a = max(a, min(win[0], b - MIN_CARD))
        b = min(b, max(win[1], a + MIN_CARD))
    if b - a < MIN_CARD:
        return no("move 1 cannot run: the air in front of the card is shorter than a card")
    return {"move": "add", "text": text, "start": round(a, 2), "end": round(b, 2),
            "card_start": card["start"], "card_end": card["end"]}


def try_rewrite(card, kinds, sentence, rec, ceiling, case, hedges, errors):
    """Move 2. Her own contiguous words, from the word that decided the meaning to the card.

    The span runs from the earlier of the governing word and the card's first word to the later
    of the governing word and the card's last word, so every word between them is hers and in
    her order. Nothing is reordered and nothing is added.
    """
    low = cc.flat(card["text"])
    for e in errors:                      # a known mishearing has one right answer: her word
        heard = cc.flat(e["heard"])
        if re.search(r"(?<![a-z0-9'])" + re.escape(heard) + r"(?![a-z0-9'])", low):
            fixed = re.sub("(?i)" + re.escape(e["heard"]), e["said"], card["text"])
            if cc.flat(fixed) != low:
                return {"move": "rewrite", "text": fixed, "start": card["start"],
                        "end": card["end"], "why": f"the transcriber misheard it. She said "
                                                   f"\"{e['said']}\""}

    if "stranded-continuation" in kinds and len(kinds) == 1:
        ct = spell(card["text"])
        if ct and ct[0] in cc.CONTINUATION:
            rest = card["text"].strip()
            rest = rest[len(rest.split()[0]):].strip().lstrip(",;: ")
            if len(spell(rest)) >= 2:
                return {"move": "rewrite", "text": say(split_line(rest), case),
                        "why": "the leading connective dropped, which is the fix "
                               "caption_check.py names itself",
                        "start": card["start"], "end": card["end"]}

    if sentence is None:
        return no("move 2 needs the transcript to know which of her words to use. None "
                  "was given")

    if "stranded-attribution" in kinds:
        p = attribution_rewrite(card, sentence, rec, ceiling, case)
        if p is not None:
            return p

    words = split_line(sentence["text"])
    span = locate(card["text"], words)
    if span is None:
        return no("move 2 could not find the card's words inside her line")
    st = [n for _, n, _ in words]
    want = []
    for kind in kinds:
        want += governing(kind, card, sentence["text"])
    idxs = [i for i, n in enumerate(st) if n in want]
    if not idxs:
        return no("move 2 found no governing word of hers to carry onto the card")
    a = min([span[0]] + idxs)
    b = max([span[1]] + idxs)
    if LEAD_AUX and a > 0 and st[a - 1] in cc.FINITE and (b - a + 2) <= ceiling:
        a -= 1                      # a predicate without its verb reads as a list, not a claim
    if b > span[1]:
        stop = right_edge(words, b, ceiling - (b - a + 1))
        if stop is None:
            return no(f"move 2 cannot run: carrying \"{st[b]}\" onto the card ends it in the "
                      f"middle of her clause, and finishing the clause needs more than the "
                      f"{ceiling} words a reader takes in one glance")
        b = stop
    keep = {i - a for i in idxs}
    body = fit_ceiling(words[a:b + 1], ceiling, hedges, keep=keep)
    if not body:
        return no(f"move 2 cannot run: her words from \"{st[a]}\" to \"{st[b]}\" are "
                  f"{b - a + 1} and the ceiling is {ceiling}. Only filler may be dropped")
    ends = b >= len(words) - 1
    text = say(body, case, question=ends and sentence["text"].rstrip().endswith("?"))
    if cc.flat(text) == cc.flat(card["text"]):
        return no("move 2 cannot run: her words make the card that is already there")
    if len(cc.negations(text)) >= 2:
        return no(f"move 2 will not offer \"{text}\": it carries two negations. A double "
                  f"negative read muted in two seconds is the hardest shape there is, and the "
                  f"hand pass cut a card for exactly that")
    return {"move": "rewrite", "text": text, "start": card["start"], "end": card["end"]}


def right_edge(words, b, room):
    """Where a span may stop on the right, or None.

    A card may end on the card's own last word, or at the end of one of her clauses. It may not
    stop in the middle of one: the first run of this script answered a dropped "doesn't" with
    "such a money shame that doesn't", which is a worse card than the one it replaced.

    The one exception is a comparison word, because a card ending on "than" advertises that it
    continues and caption_check.py checks that something follows it. That exception is the
    checker's own, written in the comment above its neighbour gap.
    """
    if words[b][2] or b >= len(words) - 1:
        return b
    if words[b][1] in cc.COMPARISON:
        return b
    for j in range(b + 1, min(len(words), b + 1 + max(0, room))):
        if words[j][2]:
            return j
    return None


def attribution_rewrite(card, sentence, rec, ceiling, case):
    """A line that is quoted, asked or permitted, given back its frame.

    The branches are caption_check.py's own attribution branches in its own order, so the
    repair answers the finding that was actually raised rather than a different one. Each uses
    only words already in her sentence: a speaker label where her line names the speaker, the
    permission phrase in front of the order, a question mark where her line asked a question.
    """
    shape, context, source = attribution_shape(card, sentence, rec)
    words = split_line(sentence["text"])
    span = locate(card["text"], words)
    st = [n for _, n, _ in words]

    if shape == "voiced":
        who = speaker_of(source)
        if who:
            return {"move": "rewrite", "text": f"{who}: \"{card['text']}\"",
                    "why": f"her line names the {who} as the one talking, so the card says so",
                    "start": card["start"], "end": card["end"]}
        return no("her line is quoted speech and names no speaker but a pronoun. Working out "
                  "who is talking is reading, which this cannot do")

    if shape == "permission" and span is not None:
        m = cc.PERMISSION.search(cc.flat(context))
        at = run_before(st, spell(m.group(0)), span[0])
        if at is None:
            return no(f"her line grants it with \"{m.group(0)}\", and those words are not in "
                      f"front of the card's own words, so they cannot be carried onto it")
        body = fit_ceiling(words[at:span[1] + 1], ceiling, keep={0})
        if not body:
            return no(f"her line grants it with \"{m.group(0)}\", and \"{m.group(0)}\" plus "
                      f"the card is {span[1] - at + 1} words against a ceiling of {ceiling}. "
                      f"Compressing her sentence is writing, which this cannot do")
        return {"move": "rewrite", "text": say(body, case),
                "why": "her line grants it rather than ordering it, so the card grants it",
                "start": card["start"], "end": card["end"]}

    if shape == "question" and span is not None:
        body = fit_ceiling(words[span[0]:span[1] + 1], ceiling)
        if body:
            return {"move": "rewrite", "text": say(body, case, question=True),
                    "why": "her line asks it rather than ordering it, so the card asks it",
                    "start": card["start"], "end": card["end"]}
        return no("her line asks it, and her words do not fit the ceiling with the question "
                  "mark on")
    return no("the card reads as an order and nothing in her line gives it another frame that "
              "her own words can carry")


def try_retime(piece, card, found):
    """A card out of range or on screen over its neighbour. Timing, not meaning."""
    dur = piece.get("duration")
    kinds = {f["kind"] for f in found}
    if not (kinds & {"out-of-range", "overlap"}):
        return None
    if card["start"] is None or card["end"] is None:
        return None
    a, b = max(0.0, card["start"]), card["end"]
    earlier = [c for c in piece["cards"]
               if c is not card and c["end"] is not None and c["start"] is not None
               and c["start"] < a]
    floor = max([c["end"] for c in earlier], default=0.0)
    a = max(a, floor + MIN_GAP) if floor > a - MIN_GAP else a
    if dur is not None:
        b = min(b, dur)
    if b - a < MIN_CARD:
        return None
    if abs(a - card["start"]) < cc.EPS and abs(b - card["end"]) < cc.EPS:
        return None
    return {"move": "retime", "text": card["text"], "start": round(a, 2), "end": round(b, 2)}


# ------------------------------------------------------------------ the run credit

def sentence_in(piece, card, rec):
    """The index of the sentence a card came from, or None."""
    s = sentence_for(piece, card, rec)
    return s["i"] if s else None


def run_credit(piece, cards, card, kinds, sentence, rec):
    """Are the words that decided the meaning already on screen beside this card?

    A run of cards whose gaps are all inside caption_check.py's neighbour gap is read in one
    breath, so a governing word anywhere in that run is in front of the reader. The real batch
    is the argument: four cards came out of one sentence about incongruence, and restoring
    "is ... than" to one of them makes the whole run read as the sentence again.

    Negation never takes this credit. The card before "i want to be tamed from" was "there is
    not one thing", touching it, and the pair still read as an inversion four times.
    """
    if "stranded-negation" in kinds or sentence is None:
        return None
    timed = sorted([c for c in cards if c["start"] is not None and c["end"] is not None],
                   key=lambda c: c["start"])
    if card not in timed:
        return None
    i = timed.index(card)
    run = [card]
    j = i
    while j > 0 and timed[j]["start"] - timed[j - 1]["end"] <= cc.NEIGHBOUR_GAP:
        run.insert(0, timed[j - 1])
        j -= 1
    j = i
    while j + 1 < len(timed) and timed[j + 1]["start"] - timed[j]["end"] <= cc.NEIGHBOUR_GAP:
        run.append(timed[j + 1])
        j += 1
    if len(run) < 2:
        return None
    # a governing word only counts when it comes off the same sentence of hers. "when you don't
    # feel safe" sits 1.6s before "you're freaking depressed" and carries a "when", but it is
    # the "when" of a different clause and it governs nothing on this card. Counting it held a
    # card the hand pass rewrote
    same = [c for c in run if c is not card
            and sentence_in(piece, c, rec) == sentence["i"]]
    others = [c["text"] for c in same]
    joined = " ".join(others)
    if not others:
        return None
    reason = (f"the words that decide it are already on the cards beside this one, inside the "
              f"run at {fmt(run[0]['start'])}-{fmt(run[-1]['end'])}s")
    for kind in kinds:
        # every finding on the card has to be answered, not just the first one. A card carrying
        # a stranded "and" AND a known mishearing was held on the strength of the "and" alone,
        # and the misheard word went to the render
        if kind == "stranded-continuation":
            if run.index(card) == 0:
                return None
            reason = ("the card it continues from is on screen beside it, "
                      f"inside the {cc.NEIGHBOUR_GAP}s a reader holds in one breath")
            continue
        if kind == "stranded-attribution":
            # the frame is on screen only if a card beside it carries the SAME frame. After
            # "you can go chase after your dreams" is repaired, "make the world a better place"
            # beside it reads as the same permission, and that is the call the hand pass made
            # on this exact pair. A speaker label does not answer a dropped permission and a
            # permission does not answer a dropped speaker
            shape, _, _ = attribution_shape(card, sentence, rec)
            if shape == "permission" and any(cc.PERMISSION.search(t) for t in others):
                continue
            if shape == "voiced" and any(SPEAKER_LABEL.match(t) for t in others):
                continue
            if shape == "question" and any(t.rstrip().endswith("?") for t in others):
                continue
            return None
        want = governing(kind, card, sentence["text"])
        if not want:
            return None
        if not set(want) & set(cc.toks(joined)):
            return None
    return reason


# ------------------------------------------------------------------ repairing one piece

def repair_piece(piece, rec, clock, errors, ceiling, levels, rounds, hedges):
    """Proposals for one piece, and the checker's reading of the list before and after."""
    tmap = TimeMap(piece.get("segments"))
    case = piece_case(piece)
    live = [dict(c) for c in piece["cards"]]
    next_n = max([c["n"] for c in live], default=0) + 1
    base = findings_at(piece, live, rec, errors, ceiling, levels)
    decided, added = {}, []

    def current():
        return [c for c in live if c["n"] not in decided or decided[c["n"]]["move"] != "cut"] \
            + [c for c in added]

    for _ in range(max(1, rounds)):
        found = findings_at(piece, current(), rec, errors, ceiling, levels)
        groups = by_card(found)
        todo = [c for c in live if c["n"] in groups and c["n"] not in decided]
        if not todo:
            break
        progress = False
        for card in sorted(todo, key=lambda c: (c["start"] if c["start"] is not None else 0)):
            mine = groups[card["n"]]
            kinds = [f["kind"] for f in mine]
            retime = try_retime(piece, card, mine)
            if retime:
                trial = [dict(c, **{"start": retime["start"], "end": retime["end"]})
                         if c["n"] == card["n"] else c for c in current()]
                after = findings_at(piece, trial, rec, errors, ceiling, levels)
                if accepts(found, after, card["n"]):
                    card["start"], card["end"] = retime["start"], retime["end"]
                    card["timed"] = True
                    progress = True
                    if not by_card(after).get(card["n"]):
                        retime["kinds"] = kinds
                        retime["findings"] = mine
                        decided[card["n"]] = retime
                    else:
                        # the times were wrong AND the words are. Fixing the times is not an
                        # answer to the words, so the card stays open for a meaning move and
                        # the proposal that lands says the times moved too
                        card["also"] = (f"its times were out of range and are corrected to "
                                        f"{fmt(retime['start'])}-{fmt(retime['end'])}s as well")
                    continue
            sentence = sentence_for(piece, card, rec)
            credit = run_credit(piece, current(), card, kinds, sentence, rec)
            if credit:
                decided[card["n"]] = {"move": "hold", "text": card["text"], "why": credit,
                                      "kinds": kinds, "findings": mine,
                                      "start": card["start"], "end": card["end"]}
                progress = True
                continue
            refusals = []
            for attempt in (
                lambda: try_add(current(), card, kinds, sentence, clock, tmap,
                                ceiling, case, hedges),
                lambda: try_rewrite(card, kinds, sentence, rec, ceiling, case, hedges,
                                    errors),
            ):
                p = attempt()
                if p is None:
                    continue
                if p.get("move") is None:
                    refusals.append(p["refused"])
                    continue
                if p["move"] == "add":
                    new = {"text": p["text"], "start": p["start"], "end": p["end"],
                           "n": next_n, "new": True, "before": card["n"]}
                    trial = current() + [new]
                else:
                    trial = [dict(c, **{"text": p["text"], "start": p["start"],
                                        "end": p["end"]})
                             if c["n"] == card["n"] else c for c in current()]
                after = findings_at(piece, trial, rec, errors, ceiling, levels)
                ok = accepts_add(found, after, card["n"], next_n) if p["move"] == "add" \
                    else accepts(found, after, card["n"])
                if not ok:
                    refusals.append(
                        f"the {'new card' if p['move'] == 'add' else 'rewrite'} "
                        f"\"{p['text']}\" does not clear the checker, so it is not offered")
                    continue
                p["kinds"] = kinds
                p["findings"] = mine
                p["sentence"] = sentence["text"] if sentence else None
                p["dropped"] = refusals
                p["also"] = card.get("also")
                decided[card["n"]] = p
                if p["move"] == "add":
                    p["answers"] = card["n"]
                    p["new_n"] = next_n
                    added.append(new)
                    next_n += 1
                else:
                    card["text"], card["start"], card["end"] = p["text"], p["start"], p["end"]
                progress = True
                break
            else:
                card["refusals"] = refusals
        if not progress:
            break

    # whatever the constructive passes could not reach is cut, and the refusal is printed
    found = findings_at(piece, current(), rec, errors, ceiling, levels)
    for card in sorted([c for c in live if c["n"] in by_card(found) and c["n"] not in decided],
                       key=lambda c: (c["start"] if c["start"] is not None else 0)):
        mine = by_card(found)[card["n"]]
        sentence = sentence_for(piece, card, rec)
        decided[card["n"]] = {
            "move": "cut", "text": card["text"], "start": card["start"], "end": card["end"],
            "kinds": [f["kind"] for f in mine], "findings": mine,
            "sentence": sentence["text"] if sentence else None,
            "also": card.get("also"),
            "refused": card.get("refusals") or
            ["no card could be built out of her own words inside the ceiling"]}

    # a card the checker stopped flagging because another card's repair answered it. Silence
    # here would leave a buyer wondering where their finding went
    still = {f["card"] for f in findings_at(piece, current(), rec, errors, ceiling, levels)}
    for card in live:
        if card["n"] in decided or card["n"] in still:
            continue
        was = [f for f in base if f["card"] == card["n"]]
        if was:
            decided[card["n"]] = {
                "move": "hold", "text": card["text"], "start": card["start"],
                "end": card["end"], "kinds": [f["kind"] for f in was], "findings": was,
                "why": "another card's repair answered this one. The checker flagged it before "
                       "and does not flag it now"}

    for card in piece.get("dropped_cards") or []:
        decided[card["n"]] = {
            "move": "cut", "text": card["text"], "start": card["start"], "end": card["end"],
            "kinds": ["outside-every-segment"], "findings": [],
            "refused": ["the card's time falls outside every segment of this piece, so it "
                        "would never appear on screen"]}

    final = current()
    remaining = findings_at(piece, final, rec, errors, ceiling, levels)
    return {"piece": piece, "decided": decided, "added": added, "cards": final,
            "before": base, "after": remaining}


# ------------------------------------------------------------------ the diff a person reads

def diff_text(results, levels, ceiling, rec):
    """The diff a person reads before any of this is accepted."""
    out = []
    w = out.append
    w("caption_repair: proposals only. Nothing has been changed in place.")
    w("")
    if rec is None:
        w("NO TRANSCRIPT GIVEN. Without her words the only repairs possible are the mechanical")
        w("ones: a card out of range, two cards at once, a known mishearing, a leading")
        w("connective. Every meaning repair needs --transcript.")
        w("")
    moves = {}
    refused = 0

    for r in results:
        piece = r["piece"]
        dec = r["decided"]
        flagged = f"{len(r['before'])} finding" + ("" if len(r["before"]) == 1 else "s")
        if not dec:
            w(f"{piece['name']}: {len(piece['cards'])} cards, {flagged} at "
              f"{'/'.join(sorted(levels))}. Nothing to propose.")
            w("")
            continue
        w(f"{piece['name']}: {len(piece['cards'])} cards in, {len(r['cards'])} proposed. "
          f"{flagged} before.")
        for n in sorted(dec, key=lambda n: (dec[n].get("start") or 0, n)):
            p = dec[n]
            moves[p["move"]] = moves.get(p["move"], 0) + 1
            if p.get("refused"):
                refused += 1
            was = piece_card_text(piece, n)
            at_a = p.get("card_start", p.get("start"))
            at_b = p.get("card_end", p.get("end"))
            w(f"  card {n} at {fmt(at_a)}-{fmt(at_b)}s: \"{was}\"")
            for f in p.get("findings") or []:
                w(f"    [{f['level']:<7}] {f['kind']}")
            if p.get("sentence"):
                w(f"    her line:  \"{p['sentence']}\"")
            w(f"    {MOVE_LABEL[p['move']]}")
            if p["move"] == "cut":
                w(f"    -  {fmt(at_a)}-{fmt(at_b)}  {was}")
                for why in p.get("refused") or []:
                    w(f"    refused:   {why}")
                w("    the audio still plays. Air is safe, a wrong card is not")
            elif p["move"] == "add":
                w(f"    +  {fmt(p['start'])}-{fmt(p['end'])}  {p['text']}")
                w(f"    =  {fmt(at_a)}-{fmt(at_b)}  {was}   (unchanged)")
                w("       NEW TIME, placed by word density. Nothing here has heard the audio")
                w("       the card's own finding stays in the list below: the checker reads")
                w("       every card alone and gives none of them credit for the one before it")
            elif p["move"] == "rewrite":
                w(f"    -  {was}")
                w(f"    +  {p['text']}   ({len(p['text'].split())} words, ceiling {ceiling})")
                if p.get("why"):
                    w(f"       {p['why']}")
            elif p["move"] == "retime":
                w(f"    ~  was {fmt(card_was(piece, n, 'start'))}-"
                  f"{fmt(card_was(piece, n, 'end'))}, now "
                  f"{fmt(p['start'])}-{fmt(p['end'])}  {was}   (text unchanged)")
            else:
                w(f"    =  {was}   (unchanged)")
                w(f"       {p['why']}")
            if p.get("also"):
                w(f"    note:      {p['also']}")
            for why in p.get("dropped") or []:
                w(f"    tried and dropped: {why}")
        cut_here = sum(1 for p in dec.values() if p["move"] == "cut")
        if piece["cards"] and cut_here > CUT_SHARE_LOUD * len(piece["cards"]):
            w(f"  LOUD: this cuts {cut_here} of {len(piece['cards'])} cards, over a third of "
              f"the piece. Read the whole list before accepting any of it")
        answered = {p.get("answers") for p in dec.values() if p["move"] == "add"}
        held = {n for n, p in dec.items() if p["move"] == "hold"}
        buckets = {"answered": [], "held": [], "left": []}
        for f in sorted(r["after"], key=lambda f: f["start"] or 0):
            where = "answered" if f["card"] in answered else \
                ("held" if f["card"] in held else "left")
            buckets[where].append(f)
        for name, head in (
            ("answered", "answered by a new card in front, and still printed by the checker "
                         "because it reads every card alone"),
            ("held", "held on purpose: the words that decide them are on the cards beside them"),
            ("left", "STILL FLAGGED AND NOT ANSWERED. Cutting a card can strand the card "
                     "beside it, and this is where that shows"),
        ):
            rows = buckets[name]
            if not rows:
                continue
            w(f"  {len(rows)} finding" + ("" if len(rows) == 1 else "s") + f" {head}:")
            for f in rows:
                w(f"    card {f['card']} \"{f['text']}\": [{f['level']}] {f['kind']}")
        w("")

    w("-" * 78)
    total = sum(len(r["decided"]) for r in results)
    order = ("add", "rewrite", "cut", "hold", "retime")
    tally = ", ".join(f"{moves[k]} {k}" for k in order if moves.get(k)) or "none"
    w(f"{total} card" + ("" if total == 1 else "s") + f" with a proposal: {tally}.")
    w(f"{refused} of them " + ("is" if refused == 1 else "are")
      + " this script refusing to build text and cutting the card instead.")
    w(f"The checker read {sum(len(r['before']) for r in results)} findings at "
      f"{'/'.join(sorted(levels))} before, and reads "
      f"{sum(len(r['after']) for r in results)} after. What remains is listed per piece above,"
      f" split into the ones a new card answers, the ones held on purpose, and the rest.")
    w("")
    w("THESE ARE PROPOSALS. Every word in them is hers, taken contiguously from the line the")
    w("card came from, and none of it has been applied to anything. This script cannot judge")
    w("meaning: it cannot tell a card true to what she meant from one that is not, so where it")
    w("could not build a card out of her own words inside the ceiling it cut the card and said")
    w("so. Read the diff. Then listen to every join a new or retimed card sits on.")
    return "\n".join(out)


def card_was(piece, n, key):
    for c in list(piece["cards"]) + list(piece.get("dropped_cards") or []):
        if c["n"] == n:
            return c.get(key)
    return None


def piece_card_text(piece, n):
    for c in list(piece["cards"]) + list(piece.get("dropped_cards") or []):
        if c["n"] == n:
            return c["text"]
    return "?"


# ------------------------------------------------------------------ writing the proposal

def locate_card_lists(raw):
    """Every card array inside the input file, in the order caption_check.py reads them.

    The proposal is written back into a copy of the input's own shape, so the file that comes
    out is the file that went in with its cards replaced. Nothing else is touched: a cut list's
    segments, its brand, its durations and its notes all survive.
    """
    blocks = None
    if isinstance(raw, dict):
        if isinstance(raw.get("pieces"), list):
            blocks = raw["pieces"]
        elif cc._cards_of(raw) is not None:
            blocks = [raw]
    elif isinstance(raw, list):
        if raw and isinstance(raw[0], dict) and cc._cards_of(raw[0]) is not None:
            blocks = raw
        elif raw:
            blocks = [{"cards": raw}]
    out = []
    for i, b in enumerate(blocks or []):
        if not isinstance(b, dict):
            continue
        for key in ("caption_cards", "cards"):
            if isinstance(b.get(key), list):
                out.append((cc._name_of(b, f"piece {i + 1}"), b, key))
                break
    return out


def write_proposal(path, in_path, results, bases, levels, ceiling):
    raw = json.loads(Path(in_path).read_text(encoding="utf-8-sig"))
    lists = {name: (block, key) for name, block, key in locate_card_lists(raw)}
    record = []
    for r in results:
        piece = r["piece"]
        if piece["name"] not in lists:
            continue
        block, key = lists[piece["name"]]
        original = block[key]
        tmap = TimeMap(piece.get("segments"))
        base = bases.get(piece["name"], "clip")
        rows = []
        for c in sorted(r["cards"], key=lambda c: (c["start"] if c["start"] is not None else 0)):
            start, end = c["start"], c["end"]
            keep = (not c.get("new")) and (not c.get("timed")) and 0 < c["n"] <= len(original)
            if keep:
                # the times this card came in with, verbatim. Converting a time out and back
                # again is a round trip that can land on the wrong side of a segment join, and
                # a card nobody retimed has no business moving at all
                src = original[c["n"] - 1]
                if isinstance(src, dict):
                    start, end = src.get("start"), src.get("end")
                elif isinstance(src, (list, tuple)) and len(src) >= 3:
                    start, end = src[0], src[1]
            elif base == "source" and not tmap.flat:
                start = tmap.to_source(start, "start") if start is not None else None
                end = tmap.to_source(end, "end") if end is not None else None
            if c.get("new"):
                rows.append({"text": c["text"], "start": round_or(start), "end": round_or(end),
                             "proposed_by": "caption_repair.py"})
                continue
            src = original[c["n"] - 1] if 0 < c["n"] <= len(original) else None
            if isinstance(src, (list, tuple)):
                rows.append([round_or(start), round_or(end), c["text"]])
            elif isinstance(src, dict):
                row = dict(src)
                row["text"] = c["text"]
                row["start"] = round_or(start)
                row["end"] = round_or(end)
                rows.append(row)
            else:
                rows.append({"text": c["text"], "start": round_or(start),
                             "end": round_or(end)})
        block[key] = rows
        for n, p in sorted(r["decided"].items()):
            record.append({"piece": piece["name"], "card": n, "move": p["move"],
                           "was": piece_card_text(piece, n), "now": p.get("text"),
                           "start": p.get("start"), "end": p.get("end"),
                           "kinds": p.get("kinds"), "why": p.get("why"),
                           "refused": p.get("refused")})
    holder = raw if isinstance(raw, dict) else {"pieces": raw}
    if not isinstance(raw, dict):
        holder = {"pieces": raw}
    holder["caption_repair"] = {
        "proposed": True,
        "levels": sorted(levels),
        "max_words": ceiling,
        "moves": record,
        "not_approved": "Every card in this file is a proposal from caption_repair.py. The "
                        "words are hers and the placements of any new card are interpolated "
                        "from word count, not heard. Read the diff, listen to the joins, then "
                        "rename this file if you accept it.",
    }
    Path(path).write_text(json.dumps(holder, indent=1, ensure_ascii=False), encoding="utf-8")


def round_or(v):
    return None if v is None else round(float(v), 2)


# ------------------------------------------------------------------ scoring against a person

def align(a, b):
    """Two card lists lined up in order, by text and by time. Needleman-Wunsch, small lists.

    The floor matters more than the gap cost. Without it, "you can't grow" at 63.62 paired with
    "when you're outgrowing, you're freaking depressed" at 64.90 because they are a second
    apart, which pushed every card after it one slot along and scored three of them against the
    wrong person's card.
    """
    GAP = -0.45

    def score(x, y):
        s = cc.similar(x["text"], y["text"])
        dt = abs((x.get("start") or 0) - (y.get("start") or 0))
        if s < PAIR_FLOOR and dt > 1.0:
            return -99.0        # two different cards near the same second are still two cards
        return s - min(dt, 8.0) / 24.0

    n, m = len(a), len(b)
    f = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        f[i][0] = f[i - 1][0] + GAP
    for j in range(1, m + 1):
        f[0][j] = f[0][j - 1] + GAP
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            f[i][j] = max(f[i - 1][j - 1] + score(a[i - 1], b[j - 1]),
                          f[i - 1][j] + GAP, f[i][j - 1] + GAP)
    i, j, pairs = n, m, []
    while i > 0 or j > 0:
        if i > 0 and j > 0 and abs(f[i][j] - (f[i - 1][j - 1]
                                              + score(a[i - 1], b[j - 1]))) < 1e-9:
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i > 0 and abs(f[i][j] - (f[i - 1][j] + GAP)) < 1e-9:
            pairs.append((i - 1, None))
            i -= 1
        else:
            pairs.append((None, j - 1))
            j -= 1
    return list(reversed(pairs))


def human_verdicts(piece, repaired):
    """What a person actually did to each card of this piece, read off their finished list."""
    mine = sorted(piece["cards"], key=lambda c: (c["start"] if c["start"] is not None else 0))
    theirs = sorted(repaired, key=lambda c: (c.get("start") or 0))
    out, extra = {}, []
    for i, j in align(mine, theirs):
        if i is None:
            extra.append(theirs[j])
            continue
        card = mine[i]
        if j is None:
            out[card["n"]] = ("cut", None)
            continue
        g = theirs[j]
        same = cc.toks(card["text"]) == cc.toks(g["text"])
        moved = abs((g.get("start") or 0) - (card["start"] or 0)) > 0.6
        out[card["n"]] = (("hold" if not moved else "retime") if same else "rewrite", g)
    return out, extra


def compare(results, repaired_path):
    """Score the proposals against a card list somebody repaired by hand."""
    data = json.loads(Path(repaired_path).read_text(encoding="utf-8-sig"))
    blocks = data.get("pieces") if isinstance(data, dict) else data
    if isinstance(data, dict) and blocks is None:
        blocks = [data]
    theirs = {}
    for i, b in enumerate(blocks or []):
        raw = cc._cards_of(b)
        if raw:
            theirs[cc._name_of(b, f"piece {i + 1}")] = cc._norm_cards(raw, f"piece {i + 1}")
    out = []
    out.append(f"caption_repair --compare {Path(repaired_path).name}: the proposals against "
               f"what a person did.")
    out.append("")
    agree = differ = acted = left = 0
    pattern = {}
    unseen = []
    refused_total = refused_agree = 0
    for r in results:
        piece = r["piece"]
        if piece["name"] not in theirs:
            out.append(f"{piece['name']}: not in {Path(repaired_path).name}. Skipped.")
            continue
        verdicts, extra = human_verdicts(piece, theirs[piece["name"]])
        out.append(f"{piece['name']}:")
        for n in sorted(r["decided"], key=lambda n: (r["decided"][n].get("start") or 0, n)):
            p = r["decided"][n]
            hv, hc = verdicts.get(n, ("hold", None))
            mine = p["move"]
            mapped = "hold" if mine == "retime" else mine
            theirs_move = "hold" if hv == "retime" else hv
            same = (mapped == theirs_move) or (mine == "add" and theirs_move in ("hold",)
                                               and near_added(p, extra))
            if p.get("refused"):
                refused_total += 1
                if theirs_move == "cut":
                    refused_agree += 1
            if same:
                agree += 1
                if mapped in ("cut", "rewrite", "add"):
                    acted += 1
                else:
                    left += 1
                tag = "AGREE "
            else:
                differ += 1
                tag = "DIFFER"
                pattern[f"{mine} / they {theirs_move}"] = \
                    pattern.get(f"{mine} / they {theirs_move}", 0) + 1
            line = f"  {tag} card {n} \"{piece_card_text(piece, n)}\": me {mine}"
            if mine in ("rewrite", "add"):
                line += f" \"{p['text']}\""
            line += f" | them {hv}"
            if hv == "rewrite" and hc:
                line += f" \"{hc['text']}\""
            out.append(line)
            if same and mine == "rewrite" and hc:
                s = cc.similar(p["text"], hc["text"])
                out.append(f"         text agreement {s:.2f}"
                           + ("  (the same words)" if cc.toks(p["text"]) == cc.toks(hc["text"])
                              else ""))
        changed_unflagged = [n for n, (hv, _) in verdicts.items()
                             if hv in ("cut", "rewrite") and n not in r["decided"]]
        for n in changed_unflagged:
            unseen.append((piece["name"], n, piece_card_text(piece, n), verdicts[n][0]))
        if extra:
            out.append(f"  they added {len(extra)} card(s) this never proposed: "
                       + "; ".join(f"\"{c['text']}\"" for c in extra[:4]))
    out.append("")
    out.append("-" * 78)
    total = agree + differ
    out.append(f"{total} proposals scored. {agree} agree with the move the person made, "
               f"{differ} differ.")
    out.append(f"Of the {agree} that agree, {acted} are a card the person also cut, rewrote or "
               f"added, and {left} are a card both left alone. Leaving a card alone is the "
               f"easiest kind of agreement and it is counted separately for that reason.")
    for k in sorted(pattern, key=lambda k: -pattern[k]):
        out.append(f"    {pattern[k]:>3}  I said {k}")
    out.append(f"{refused_total} proposals are refusals to build text. The person cut "
               f"{refused_agree} of those same cards.")
    out.append(f"{len(unseen)} cards the person changed were never flagged at all, so no "
               f"proposal exists for them:")
    for name, n, text, hv in unseen[:40]:
        out.append(f"    {name} card {n} \"{text}\" -> they {hv} it")
    if len(unseen) > 40:
        out.append(f"    and {len(unseen) - 40} more, not printed")
    out.append("")
    out.append("A move agreeing is not the same as the card being right. Where both cut, the")
    out.append("card is gone either way. Where both rewrote, the text agreement above says how")
    out.append("close the words came, and anything under 1.00 is a different card.")
    return "\n".join(out)


def near_added(p, extra):
    for c in extra:
        if abs((c.get("start") or 0) - (p.get("start") or 0)) <= 3.0:
            return True
    return False


# ------------------------------------------------------------------ self test

FIXTURE_CUES = [
    {"start": 10.0, "end": 13.0, "text": "There is not one thing that I want to be tamed from."},
    {"start": 13.0, "end": 17.0, "text": "And when you're outgrowing, you're freaking depressed."},
    {"start": 17.0, "end": 22.0, "text": "It means your incongruence with yourself is far more "
                                         "imperative than the actual tangible of how to do "
                                         "anything ever."},
    {"start": 22.0, "end": 25.0, "text": "You can go chase after your dreams."},
    {"start": 25.0, "end": 28.0, "text": "My brain says, please stop growing for the love of "
                                         "God."},
    {"start": 28.0, "end": 31.0, "text": "So stop demonizing money, and name the number."},
    {"start": 31.0, "end": 34.0, "text": "There is no shame in any of it."},
]

# Eight cards against seven of her real lines, one card per move plus the two the moves exist
# to refuse. Run this after any edit here. A repairer that proposes nothing on a real card list
# should mean the list is clean, not that the moves have gone quiet.
SELFTEST = [
    ("the real one, caught one step before rendering. It must never come back a rewrite",
     "i want to be tamed from", 10.6, 13.0, "cut"),
    ("MOVE 1: a condition dropped, with air in front of the card to put it in",
     "you're freaking depressed", 15.2, 17.0, "add"),
    ("MOVE 2: one side of a comparison, her own words reach across it inside the ceiling",
     "far more imperative", 18.4, 20.0, "rewrite"),
    ("HOLD: the same comparison, now carried by the repaired card touching this one",
     "the actual tangible of how", 20.2, 21.9, "hold"),
    ("MOVE 2: an order her line granted as permission instead",
     "go chase after your dreams", 23.0, 25.0, "rewrite"),
    ("MOVE 2: an order that her own line says her brain is saying",
     "please stop growing", 25.8, 28.0, "rewrite"),
    ("MOVE 2: a card opening on a connective, with the fix caption_check.py names itself",
     "and name the number", 29.6, 31.0, "rewrite"),
    ("RETIME: a card running past the end of the piece. Timing, not meaning",
     "no shame in any of it", 32.0, 36.0, "retime"),
]


def selftest():
    piece = {"name": "fixture", "duration": 34.0, "hook": None, "segments": None,
             "times": "clip",
             "cards": [{"text": t, "start": a, "end": b, "n": i + 1}
                       for i, (_, t, a, b, _) in enumerate(SELFTEST)]}
    rec = cc.Recording(FIXTURE_CUES)
    clock = WordClock(FIXTURE_CUES)
    r = repair_piece(piece, rec, clock, [], cc.MAX_WORDS, {"blocker"}, ROUNDS, False)
    bad = 0
    print("caption_repair --selftest")
    print("")
    for i, (what, text, _, _, want) in enumerate(SELFTEST):
        p = r["decided"].get(i + 1)
        got = p["move"] if p else "nothing proposed"
        ok = got == want
        bad += 0 if ok else 1
        print(f"  [{'ok  ' if ok else 'FAIL'}] {what}")
        print(f"         card \"{text}\" -> {got}, expected {want}")
        if p and got in ("rewrite", "add"):
            print(f"         proposal: \"{p['text']}\"")
        if p and got == "hold":
            print(f"         {p['why']}")
        for why in (p or {}).get("refused") or []:
            print(f"         refused: {why}")
    hard = r["decided"].get(1)
    if hard and hard["move"] in ("rewrite", "hold"):
        print("  [FAIL] the inversion card came back as a rewrite or a hold. Air or nothing")
        bad += 1
    print("")
    print(f"{len(SELFTEST)} cases, {len(SELFTEST) - bad} as expected, {bad} not.")
    if bad:
        print("A failure here means the moves have drifted. Read the lines above before")
        print("trusting anything this script proposes.")
    return 1 if bad else 0


# ------------------------------------------------------------------ main

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="caption_repair.py", add_help=True,
        description="Propose a fix for every caption card caption_check.py flagged. "
                    "Proposals only: nothing is rewritten in place.")
    ap.add_argument("cards", nargs="?", help="the card list caption_check.py read")
    ap.add_argument("--transcript", help="what she actually said, with times. Without it only "
                                         "the mechanical repairs are possible")
    ap.add_argument("--cuts", help="the assembly, so finished card times map back to the "
                                   "recording. Needed for a non-linear cut")
    ap.add_argument("--findings", help="caption_check.py --json output. Used to say which "
                                       "cards to repair; everything else is recomputed")
    ap.add_argument("--errors", help="a mishearing list, overriding "
                                     "fixtures/transcription-errors.json")
    ap.add_argument("--out", help="write the proposed card list here. Never the input file")
    ap.add_argument("--compare", help="a card list somebody repaired by hand, to score the "
                                      "proposals against")
    ap.add_argument("--levels", default="blocker",
                    help="which findings to repair: blocker, review, note, comma separated "
                         "(default blocker)")
    ap.add_argument("--max-words", type=int, default=cc.MAX_WORDS, dest="max_words",
                    help=f"word ceiling for one card (default {cc.MAX_WORDS})")
    ap.add_argument("--card-times", choices=("clip", "source", "auto"), default="auto",
                    help="what the card times mean, as in caption_check.py")
    ap.add_argument("--strip-hedges", action="store_true",
                    help="also drop basically/literally/actually/honestly to fit the ceiling, "
                         "as cards_from_srt.py --strip-hedges does")
    ap.add_argument("--rounds", type=int, default=ROUNDS,
                    help=f"constructive passes before anything is cut (default {ROUNDS})")
    ap.add_argument("--quiet", action="store_true", help="print the summary only")
    ap.add_argument("--selftest", action="store_true",
                    help="run the built-in cases, including the one that nearly shipped")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.cards:
        ap.print_usage()
        print("caption_repair: give it a card list, or --selftest.")
        return 2

    levels = {x.strip() for x in args.levels.split(",") if x.strip()}
    if levels - {"blocker", "review", "note"}:
        raise die(f"caption_repair: --levels takes blocker, review or note, not "
                  f"{','.join(sorted(levels - {'blocker', 'review', 'note'}))}")
    in_path = Path(args.cards)
    if args.out and Path(args.out).resolve() == in_path.resolve():
        raise die("caption_repair: --out names the input file. This proposes; it does not "
                  "overwrite. Give it a new path.")

    pieces = cc.load_pieces(in_path)
    if args.cuts:
        cuts = cc.load_cuts(Path(args.cuts))
        for p in pieces:
            if p["name"] in cuts:
                p["segments"] = cuts[p["name"]]

    bases = {}
    for p in pieces:
        base = args.card_times
        if base == "auto":
            base = (p.get("times") or "clip").lower()
        bases[p["name"]] = base
        if base == "source" and p.get("segments"):
            lost = cc.rebase_cards_to_clip(p)
            if lost:
                print(f"caption_repair: {p['name']}: {lost} card(s) sit outside every segment, "
                      f"so they would never appear. Each one is proposed for cutting.",
                      file=sys.stderr)

    rec = cc.load_recording(Path(args.transcript)) if args.transcript else None
    clock = None
    if args.transcript:
        clock = WordClock(pp.load_cues(str(args.transcript)))
    errors = cc.load_errors(args.errors)

    wanted = None
    if args.findings:
        try:
            data = json.loads(Path(args.findings).read_text(encoding="utf-8-sig"))
        except FileNotFoundError:
            raise die(f"caption_repair: no such findings file: {args.findings}")
        except json.JSONDecodeError as e:
            raise die(f"caption_repair: {args.findings} is not readable JSON: {e}")
        rows = data.get("findings") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise die(f"caption_repair: {args.findings} carries no 'findings' list. It is the "
                      f"file caption_check.py --json writes.")
        wanted = {(f.get("piece"), f.get("card")) for f in rows
                  if isinstance(f, dict) and f.get("level") in levels}

    results = []
    for p in pieces:
        if wanted is not None and not any(n == p["name"] for n, _ in wanted):
            results.append({"piece": p, "decided": {}, "added": [], "cards": p["cards"],
                            "before": [], "after": []})
            continue
        r = repair_piece(p, rec, clock, errors, args.max_words, levels, args.rounds,
                         args.strip_hedges)
        if wanted is not None:
            keep = {n for pn, n in wanted if pn == p["name"]}
            r["decided"] = {n: v for n, v in r["decided"].items() if n in keep}
        results.append(r)

    text = diff_text(results, levels, args.max_words, rec)
    if args.quiet:
        text = text.split("-" * 78, 1)[-1].strip()
    print(text)

    if args.compare:
        print("")
        print(compare(results, args.compare))

    if args.out:
        write_proposal(args.out, in_path, results, bases, levels, args.max_words)
        print("")
        print(f"proposed card list written to {args.out}. The input file is untouched.")

    return 1 if any(r["decided"] for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
