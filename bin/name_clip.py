#!/usr/bin/env python3
"""name_clip.py: turn a planned clip into a filename somebody could search for.

    python3 bin/name_clip.py cuts.json                  # report old -> new, change nothing
    python3 bin/name_clip.py cuts.json --why            # and show the line each name came from
    python3 bin/name_clip.py cuts.json --write          # write the names into the cut list
    python3 bin/name_clip.py cuts.json --out named.json # or into a copy, leaving the original
    python3 bin/name_clip.py --text "..." --argument "..."   # one clip, no file
    python3 bin/name_clip.py cuts.json --json           # machine readable, for a build script

WHY THIS EXISTS. The run recorded in README.md on 2026-10-08 produced this, and a filename
is the first thing a buyer sees of the whole kit:

    make-400-000-year-somebody-tell-make.mp4

Four faults in seven words. "$400,000" was split into "400" and "000", because the word
regex that made the name treats a comma as a word break. "somebody tell" is transcription,
not a title. "make" appears twice. And none of it reads like a phrase a person would type
into a search box, because it never was a phrase: it was the first seven content words of
one sentence with the small words deleted, which is a telegram rather than a title.

WHAT THIS DOES DIFFERENTLY, and the first point is the whole idea

  1. It names a clip with a CONTIGUOUS RUN OF WORDS the speaker actually said, in order,
     glue words left in. "want-to-make-400k-a-year" reads; "make-400-000-year" does not.
     Dropping the small words is what destroyed the phrasing, so they stay.
  2. Every run of 3 to 7 words in the clip's own text is a candidate, and they are scored.
     Starting and ending a candidate is restricted: a name may not open on a pronoun or
     close on "and", because both read as a sentence somebody cut in half.
  3. Numbers are joined back together before anything is tokenised, then kept ONLY when the
     number is the point: money, a percentage, a magnitude of a thousand or more, or a
     number with a unit beside it. "$400,000 a year" becomes "400k-a-year". A bare "3" goes.
  4. Dates are refused outright. A filename with a month or a year in it stops being
     findable the moment the next quarter starts.
  5. Within one batch, a word that every clip shares counts for less than a word that only
     one clip has, so the names pull apart on their own instead of needing a counter.
  6. When two clips still want the same name, the second one takes its NEXT BEST phrase.
     A numeric suffix is the last resort, not the first move, and the report says when one
     was used.

WHAT IT CANNOT DO, said plainly

  It has no idea what a sentence means. It has no parts of speech, no grammar and no model;
  it is word lists, arithmetic and the shape of a phrase. It will sometimes pick the second
  best line in a clip. Read the report, and rename anything that reads wrong: --why prints
  the sentence each name was cut from so that judgment takes a second rather than a minute.

  The word lists in here are ENGLISH and they are general. Nobody's brand, niche or
  vocabulary is welded in. A project with its own words passes them in:

    python3 bin/name_clip.py cuts.json --words specs/mywords.json

    {"filler": ["ascension", "download"],      # never in a name
     "weak":   ["community"],                  # allowed inside a name, never at either end
     "keep":   ["q4", "lufs"],                 # treated as real words however short
     "openers":["unlearn"],                    # may start a name even though it is a verb
     "units":  ["retreats"],                   # a number beside it IS the point: "3-retreats"
     "dates":  ["michaelmas"]}                 # refused outright, like a month name

  And a brief's forbidden list is honoured, because a filename is published text too:

    python3 bin/name_clip.py cuts.json --brief specs/mybrief.json

IMPORTING IT. bin/plan_clips.py writes the "filename" field today with its own `slug()`.
This module is standalone and stdlib only so that it can replace that call in one line:

    import name_clip
    name_clip.name_batch([{"text": ..., "argument": ...}, ...])   # whole batch, deduped
    name_clip.name_clip(text, argument)                           # one clip, no batch

That edit belongs to whoever owns plan_clips.py. Until it is made, run this over the cut
list afterwards, which is what --write is for.
"""
import argparse
import json
import math
import os
import re
import sys
import unicodedata

# --------------------------------------------------------------------------- the word lists
#
# These are general English, not a niche vocabulary. Three classes, and the difference
# between them is where a word is allowed to sit rather than how it scores:
#
#   GLUE    the small words that hold a phrase together. Allowed inside a name, never at
#           either end. They are what makes "the-price-is-not-the-problem" readable.
#   FILLER  discourse noise. A name containing one is penalised hard, because its presence
#           is a sign the phrase is transcription rather than a title.
#   WEAK    real words that say nothing in a filename. Allowed inside, never at an end.

GLUE = set("""a an the and or but so because as of to for in into on at by with from than
then this that these those there here it its they them their he him his she her we us our
you your i me my be is am are was were been being do does did doing have has had having
will would can could should may might must not no nor if when while about over under up
down out off again just also very too only even still yet much more most some any such own
same another each every few all who whom whose what which how why where whenever on upon
onto per via amid among between across after before until since during through
thats its whats theres heres lets hes shes dont doesnt didnt isnt arent wasnt werent cant
couldnt wouldnt shouldnt wont aint ive id ill im youre youve youll youd weve theyre theyve
theyll theyd hasnt havent hadnt thatll therell itll
""".split())

FILLER = set("""um uh erm hmm uhh ahh like literally basically actually honestly obviously
totally really kinda sorta gonna wanna gotta anyway anyways whatever okay ok yeah yep yes
nope well guys folks lot lots maybe probably definitely absolutely essentially apparently
frankly anyhow whatnot etcetera etc mean meant means sort kind yada blah
""".split())
# "seriously" and "truly" are NOT in that list on purpose. They read as filler in a
# transcript and as the point in a title: "take-your-unseriousness-seriously" is a name a
# person wrote by hand for a real clip, and a filler list containing them cannot produce it.

WEAK = set("""somebody someone anybody anyone everybody everyone people person folk human
humans something anything everything nothing somewhere anywhere everywhere stuff thing
things way ways time times moment moments reason reasons part parts point points bit bits
lot item items area areas case cases
""".split())

# Verbs that carry almost no meaning in the middle of a title. They are still allowed to
# START one, because an imperative opener is exactly how a searchable phrase begins:
# "stop-asking-how", "fund-the-whole-life", "price-the-life-then-divide-the-number".
GENERIC = set("""make makes made making get gets got getting go goes going went gone say
says said saying tell tells told telling know knows knew knowing think thinks thought see
sees saw seen seeing look looks looked want wants wanted take takes took taken come comes
came give gives gave given put puts keep keeps kept let lets need needs needed try tries
tried using use uses used feel feels felt call calls called happen happens happened talk
talks talked ask asks asked asking doing done
""".split())

# A name may start with one of these even when the word is glue or a generic verb. These are
# the openings people type: a question, an instruction, or a flat negative.
OPENERS = set("""why how what who when where whether stop start quit begin never always
nobody nothing everything everyone dont doesnt cant wont isnt arent no not your my our the
every before after until unless if once make build price divide fund take ask name read
write cut keep pick choose fix kill double triple halve
""".split())

# Words that look like a date and are refused in a filename. A name with a month in it
# stops being findable the moment the next one starts.
DATE_WORDS = set("""january february march april may june july august september october
november december jan feb mar apr jun jul aug sep sept oct nov dec monday tuesday wednesday
thursday friday saturday sunday mon tue tues wed thu thur thurs fri sat sun
""".split())

# Units that make a number the point rather than a stray digit.
UNITS = set("""dollar dollars usd eur gbp pound pounds euro euros cent cents percent pct
grand figure figures k m b million millions billion billions thousand thousands hour hours
day days week weeks month months year years minute minutes second seconds mile miles pound
kg lb lbs x times fold person people client clients customer customers follower followers
sale sales call calls page pages word words step steps
""".split())

# Reserved on Windows, whatever the extension. The kit is something a buyer installs, and a
# buyer may be on Windows, so a clip is never named one of these.
WINDOWS_RESERVED = set(["con", "prn", "aux", "nul", "com0", "com1", "com2", "com3", "com4",
                        "com5", "com6", "com7", "com8", "com9", "lpt0", "lpt1", "lpt2",
                        "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9"])

# Cutting a name off before one of these splits a phrasal verb in half: "break | down",
# "give | up", "call | out". The result always reads as half a sentence.
PARTICLES = set("""down up out off away back over through along around apart aside forward
in on into onto together under ahead across by past about
""".split())

# What counts as the edge of a clause. A comma is the difference between "stop buying the
# coaching program" (an instruction, after a comma) and "take to reach" (mid thought).
CLAUSE_BREAK = ",;:.!?()\"\u2013\u2014-\n"

# Real words that still cannot END a name, because they modify something that has not
# arrived yet. "the-price-was-never" is the first half of a sentence. Any of these may
# START one, which is why this is a separate list from the glue above.
NO_END = set("""never always almost nearly fully truly barely hardly merely simply rather
quite pretty already finally suddenly instead anymore constantly purely literally mostly
largely entirely completely totally absolutely utterly
""".split())

MIN_WORDS = 3               # below this a name stops reading as a phrase
MAX_WORDS = 7               # above this nothing is gained and the shell wraps
MAX_CHARS = 56              # a comfortable column in a file listing
SWEET_LOW, SWEET_HIGH = 3, 5    # the lengths that read best, measured against hand written names
DIMINISH = (1.0, 1.0, 0.8, 0.55, 0.35, 0.25, 0.2)   # what the Nth real word in a name adds
FALLBACK = "clip"

SENTENCE_SPLIT = re.compile("(?<=[.!?])\\s+|\\s*[\\n\\r]+\\s*|\\s+[-\u2013\u2014]{1,2}\\s+")
BRACKETED = re.compile(r"\[[^\]]*\]|\([^)]*\)|<[^>]*>")
# "ANNA:", ">> BEN:", "SPEAKER_00:". A speaker label is not part of what was said and it
# must never reach a filename. The diarised spelling with an underscore and digits is the
# one bin/transcribe.py can produce.
SPEAKER_TAG = re.compile(r"(?m)^\s*(?:>>\s*)?[A-Z][A-Za-z0-9_'\-]{0,23}"
                         r"(?: [A-Z][A-Za-z'\-]{0,15})?:\s*")
TOKEN = re.compile(r"\$?\d[\d.]*%?|[a-z][a-z'’\-]*", re.I)
THOUSANDS = re.compile(r"(\d)[, \s](\d\d\d)(?!\d)")


# --------------------------------------------------------------------------- text to tokens

def ascii_fold(text):
    """Smart quotes, dashes and accents down to plain ascii. A filename crosses machines."""
    text = (text.replace("’", "'").replace("‘", "'")
                .replace("“", '"').replace("”", '"')
                .replace("\u2013", " - ").replace("\u2014", " - ").replace("\u2026", " "))
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def join_numbers(text):
    """Put "$400,000" and "400 000" back together BEFORE anything is tokenised.

    This is the bug that produced `make-400-000-year`: the tokeniser treated the comma as a
    word break, so one number became two words and both went into the name.
    """
    prev = None
    while prev != text:
        prev = text
        text = THOUSANDS.sub(r"\1\2", text)
    return text


def clean(text):
    text = ascii_fold(str(text or ""))
    text = SPEAKER_TAG.sub("", text)        # "ANNA:" is not part of what she said
    text = BRACKETED.sub(" ", text)         # "[MUSIC]", "(laughs)"
    return join_numbers(text)


class Word(object):
    """One token: where it may sit in a name, and what it counts for there.

    `opens` and `closes` are the punctuation either side of it: True when a clause starts
    or ends there. They are what tells an imperative from a verb in the middle of a
    sentence. "stop" after a comma is an instruction and a good way to begin a name;
    "take" after "actually" is the middle of a thought and a bad one.
    """

    __slots__ = ("raw", "norm", "stem", "kind", "value", "opens", "closes")

    def __init__(self, raw, norm, stem, kind, value=1.0, opens=False, closes=False):
        self.raw, self.norm, self.stem, self.kind, self.value = raw, norm, stem, kind, value
        self.opens, self.closes = opens, closes

    def __repr__(self):
        return "<%s %s %.2f>" % (self.kind, self.norm, self.value)


def stem_of(norm):
    """Crude and deliberately so: enough to notice "make" twice in one name."""
    for suffix in ("ing", "ers", "er", "ed", "es", "s"):
        if len(norm) > len(suffix) + 3 and norm.endswith(suffix):
            return norm[:-len(suffix)]
    return norm


def number_word(raw, nxt_norm, prev_norm, vocab):
    """Decide what a digit token becomes. Returns (Word, how many words it swallowed).

    "The number IS the point" is made concrete here: money, a percentage, a magnitude of a
    thousand or more, or a number with a unit standing next to it. Everything else is a
    stray digit and goes, because a stray digit in a filename is noise.

    The second return value is 1 when the word AFTER the number became part of it, as
    "percent" does in "30 percent". Without it the name comes out `30-percent-percent`,
    which is what it did until this was run.
    """
    body = raw.replace("$", "").replace("%", "")
    money = "$" in raw or nxt_norm in ("dollars", "dollar", "usd") or prev_norm == "usd"
    pct = "%" in raw or nxt_norm in ("percent", "pct")
    unit = nxt_norm in UNITS or nxt_norm in vocab["units"]
    try:
        value = float(body)
    except ValueError:
        return Word(raw, "", "", "reject"), 0
    whole = int(value) if value == int(value) else None

    # A four digit number inside living memory is a year, whatever the sentence claims.
    if whole is not None and 1900 <= whole <= 2100 and not (money or pct):
        return Word(raw, "", "", "date"), 0

    if whole is not None and whole >= 1000000 and whole % 1000000 == 0:
        shown = "%dm" % (whole // 1000000)
    elif whole is not None and whole >= 1000 and whole % 1000 == 0:
        shown = "%dk" % (whole // 1000)
    elif whole is not None:
        shown = str(whole)
    else:
        shown = ("%g" % value).replace(".", "-")

    ate = 0
    if pct:
        shown += "-percent"
        if nxt_norm in ("percent", "pct"):
            ate = 1                 # the word is now inside the number, not beside it
    elif money and nxt_norm in ("dollars", "dollar", "usd"):
        ate = 1                     # the digits already say it is money
    big = whole is not None and whole >= 1000
    if not (money or pct or unit or big):
        return Word(raw, "", "", "reject"), 0    # a bare small number is not the point
    return Word(raw, shown, shown, "number", 1.1), ate


def classify(norm, stem, raw, vocab):
    if norm in DATE_WORDS or norm in vocab["dates"]:
        return Word(raw, norm, stem, "date")
    if norm in vocab["filler"] or norm in FILLER:
        return Word(raw, norm, stem, "filler", -1.4)
    if norm in vocab["weak"] or norm in WEAK:
        return Word(raw, norm, stem, "weak", 0.15)
    if norm in GLUE and norm not in vocab["keep"]:
        return Word(raw, norm, stem, "glue", -0.04)
    if norm in GENERIC:
        return Word(raw, norm, stem, "generic", 0.3)
    if len(norm) < 3 and norm not in vocab["keep"]:
        return Word(raw, norm, stem, "reject")
    return Word(raw, norm, stem, "content", 1.0)


def tokenise(sentence, vocab):
    """One sentence into Words. A "reject" or "date" token poisons any name containing it.

    The punctuation BETWEEN the words is read here and then thrown away, which is the only
    chance to read it. A comma is the difference between an instruction and a fragment.
    """
    spans = list(TOKEN.finditer(sentence))
    norms = [m.group(0).lower().replace("'", "").replace("’", "").strip("-")
             for m in spans]
    out = []
    i = 0
    while i < len(spans):
        m, norm, raw = spans[i], norms[i], spans[i].group(0)
        if not norm:
            i += 1
            continue
        ate = 0
        if raw[0].isdigit() or raw[0] == "$":
            w, ate = number_word(raw, norms[i + 1] if i + 1 < len(norms) else "",
                                 norms[i - 1] if i else "", vocab)
        else:
            w = classify(norm, stem_of(norm), raw, vocab)
        last = i + ate                  # the token whose trailing punctuation now counts
        before = sentence[spans[i - 1].end():m.start()] if i else ""
        after = (sentence[spans[last].end():spans[last + 1].start()]
                 if last + 1 < len(spans) else sentence[spans[last].end():])
        w.opens = (i == 0) or any(ch in before for ch in CLAUSE_BREAK)
        w.closes = (last == len(spans) - 1) or any(ch in after for ch in CLAUSE_BREAK)
        out.append(w)
        i = last + 1
    return out


def sentences(text, vocab):
    """Yields (tokens, the sentence as written), so a report can quote the real line."""
    for bit in SENTENCE_SPLIT.split(clean(text)):
        bit = bit.strip()
        if not bit:
            continue
        toks = tokenise(bit, vocab)
        if toks:
            yield toks, bit


# --------------------------------------------------------------------------- candidates

def can_start(w, vocab):
    if w.kind in ("content", "number"):
        return True
    return w.norm in OPENERS or w.norm in vocab["openers"]


def can_end(w):
    # A name that ends on "and", "the" or "never" reads as a sentence cut in half.
    return w.kind in ("content", "number") and w.norm not in NO_END


class Candidate(object):
    __slots__ = ("slug", "score", "words", "source", "sentence")

    def __init__(self, slug, score, words, source, sentence):
        self.slug, self.score, self.words = slug, score, words
        self.source, self.sentence = source, sentence

    def as_dict(self):
        return {"name": self.slug, "score": round(self.score, 2),
                "from": self.source, "said": self.sentence}


def slug_of(words):
    bits = [w.norm for w in words if w.norm]
    s = "-".join(bits).lower()
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s


def score_window(window, bias, weight_of, prev=None, nxt=None):
    """What one contiguous run of words scores as a title.

    Every weight in here was set by hand and then checked against the six filenames a
    person wrote for one real batch, read on 2026-10-08. Six names is the only ground
    truth that exists for this. The number a candidate gets is a ranking inside one clip
    and nothing else: it is not calibrated, and it is not a prediction that a name is
    good. Read the report, and --why prints the line to read it against.
    """
    score = 0.0
    real = 0
    for w in window:
        if w.kind in ("content", "number"):
            # Diminishing returns, and this is the rule that stops a name being a list. Six
            # real words in a row scored a flat 1.0 each produced
            # `business-pages-ignore-meaning-substance-spirituality` out of a sentence the
            # transcriber gave no commas. A title says ONE thing. The third word of it adds
            # less than the second, and the sixth adds almost nothing.
            w8 = weight_of(w.stem) if w.kind == "content" else 1.0
            score += w.value * w8 * DIMINISH[min(real, len(DIMINISH) - 1)]
            real += 1
        else:
            score += w.value
    n = len(window)

    # A word twice in one name is the `make ... make` fault. Penalise the repeat, not the word.
    stems = {}
    for w in window:
        if w.kind in ("content", "generic", "number"):
            stems[w.stem] = stems.get(w.stem, 0) + 1
    score -= 1.6 * sum(c - 1 for c in stems.values())

    # Shape. An opener is how a searchable phrase begins, but only where a clause begins:
    # "stop" after a comma is an instruction, "take" after "actually" is mid thought.
    if window[0].opens and window[0].norm in OPENERS:
        score += 1.1
    # A clause break INSIDE the window means this is two fragments stitched together. It is
    # what produced `coaching-program-a-gym-membership` out of "a coaching program, a gym
    # membership, anything like that": every word is real and the result is a list, not a
    # phrase. Nobody types a comma into a search box.
    score -= 1.0 * sum(1 for w in window[1:] if w.opens)
    if window[-1].closes:
        score += 0.4          # the phrase ends where the speaker's clause ended
    if not window[0].opens and prev is not None and prev.kind in ("content", "number"):
        score -= 0.35         # starts inside somebody else's noun phrase
    if nxt is not None and not window[-1].closes:
        # The speaker's clause did not end here, so this is a cut mid thought. It is what
        # chose `stop-apologizing-for-wanting` over the same line with "the yacht" on the
        # end, which is the version that says anything.
        score -= 0.45
        if nxt.norm in PARTICLES:
            score -= 0.3      # "break | down": a phrasal verb cut in half as well

    if SWEET_LOW <= n <= SWEET_HIGH:
        score += 0.55
    elif n > SWEET_HIGH:
        score -= 0.42 * (n - SWEET_HIGH)

    # Connective tissue. A run of nothing but real words is a tag soup rather than a
    # phrase: `pain-grief-death-despair` is four true words and no title. A phrase a person
    # types almost always carries a small word in it. Too much glue is the other failure.
    content = sum(1 for w in window if w.kind in ("content", "number"))
    frac = float(content) / n
    if frac > 0.95 and n >= 4:
        score -= 0.7
    elif frac < 0.4:
        score -= 0.5
    return score + bias


def candidates(sources, vocab, weight_of, max_words=MAX_WORDS, max_chars=MAX_CHARS,
               forbidden=()):
    """Every readable run of words in this clip, best first, one entry per distinct name."""
    best = {}
    for text, bias, label in sources:
        for toks, said in sentences(text, vocab):
            for i in range(len(toks)):
                if not can_start(toks[i], vocab):
                    continue
                for j in range(i + MIN_WORDS - 1, min(i + max_words, len(toks))):
                    window = toks[i:j + 1]
                    if not can_end(window[-1]):
                        continue
                    if any(w.kind in ("reject", "date") for w in window):
                        continue
                    # Two real words is the floor. "start-to-break" has one, and it reads
                    # like the first half of a sentence rather than the name of anything.
                    if sum(1 for w in window if w.kind in ("content", "number")) < 2:
                        continue
                    s = slug_of(window)
                    if not s or len(s) > max_chars:
                        continue
                    if forbidden and hits_forbidden(s, forbidden):
                        continue
                    sc = score_window(window, bias, weight_of,
                                      toks[i - 1] if i else None,
                                      toks[j + 1] if j + 1 < len(toks) else None)
                    if s not in best or sc > best[s].score:
                        best[s] = Candidate(s, sc, window, label, said)
    return sorted(best.values(), key=lambda c: (-c.score, len(c.slug), c.slug))


# --------------------------------------------------------------------------- vocabulary

def load_vocab(path=None):
    """The word lists a project may add to. Nothing in the code knows anybody's niche."""
    v = {"filler": set(), "weak": set(), "keep": set(), "openers": set(),
         "dates": set(), "units": set()}
    if not path:
        return v
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    for key in list(v):
        for word in data.get(key) or []:
            v[key].add(str(word).strip().lower())
    return v


def load_forbidden(path=None):
    """Phrases from a brief that must never appear, filenames included.

    A brief's forbidden list is matched anywhere in the text by the planner, so it is
    matched anywhere here too: against the name's words AND against the name with its
    hyphens closed up, so that forbidding "400" also catches `make-400k-a-year`. Over
    blocking costs nothing, because a clip has hundreds of other phrases in it. Letting a
    forbidden thing through into a published filename costs a re-cut.
    """
    out = []
    if not path:
        return out
    with open(path, encoding="utf-8") as fh:
        brief = json.load(fh)
    for item in brief.get("forbidden") or []:
        if isinstance(item, dict) and item.get("phrase"):
            phrase = re.sub(r"[^a-z0-9]+", " ", str(item["phrase"]).lower()).strip()
            if phrase:
                out.append(phrase)
    return out


def hits_forbidden(slug, forbidden):
    words = " " + slug.replace("-", " ") + " "
    compact = slug.replace("-", "")
    for phrase in forbidden:
        if not phrase:
            continue
        if (" " + phrase + " ") in words or phrase.replace(" ", "") in compact:
            return True
    return False


def idf_weights(docs):
    """A word every clip in the batch shares counts for less than a word only one clip has.

    This is what makes the names pull apart without a counter on the end: the thing that is
    the same about all six clips is exactly the thing that cannot tell them apart.
    """
    n = len(docs)
    if n < 2:
        return lambda stem: 1.0
    df = {}
    for doc in docs:
        for stem in set(doc):
            df[stem] = df.get(stem, 0) + 1

    def weight_of(stem):
        seen = df.get(stem, 0)
        if not seen:
            return 1.0
        # 1.0 when one clip has it, down to about 0.45 when every clip does.
        return 0.45 + 0.55 * (math.log(1.0 + float(n) / seen) / math.log(1.0 + float(n)))
    return weight_of


# --------------------------------------------------------------------------- the public calls

def sources_of(text, argument="", hook="", segments=None):
    """What the namer reads, and in what order of preference.

    The hook is what the clip is about, so it is read first and scored up. `the_argument` is
    a machine stitch of first sentences and the cut list says so, so it is read last and
    scored down: useful when a clip's segments are thin, not a title on its own.
    """
    out = []
    if hook:
        out.append((hook, 1.5, "hook"))
    for seg in segments or []:
        role = str(seg.get("role") or "body")
        bias = {"hook": 1.0, "close": 0.2}.get(role, 0.0)
        if seg.get("text"):
            out.append((seg["text"], bias, "segment (%s)" % role))
    if text and not segments:
        out.append((text, 0.0, "text"))
    if argument:
        out.append((argument, -0.5, "the_argument"))
    return out


def all_text(sources):
    return " ".join(t for t, _b, _l in sources)


def rank_names(text="", argument="", hook="", segments=None, vocab=None, weight_of=None,
               forbidden=(), max_words=MAX_WORDS, max_chars=MAX_CHARS):
    """Every name this clip could have, best first. Read the top few before trusting one."""
    vocab = vocab if vocab is not None else load_vocab()
    srcs = sources_of(text, argument, hook, segments)
    if weight_of is None:
        weight_of = idf_weights([])
    return candidates(srcs, vocab, weight_of, max_words, max_chars, forbidden)


def name_clip(text="", argument="", hook="", segments=None, taken=(), vocab=None,
              weight_of=None, forbidden=(), max_words=MAX_WORDS, max_chars=MAX_CHARS):
    """One clip, one name. `taken` is the names already used in this batch."""
    picked = choose(rank_names(text, argument, hook, segments, vocab, weight_of,
                               forbidden, max_words, max_chars),
                    set(taken), text, argument, hook, segments, vocab, max_chars)
    return picked["name"]


def collides(slug, taken):
    """Two names collide when they are the same, or when one is the start of the other.

    The second case matters in a folder listing: "price-the-life" sitting beside
    "price-the-life-then-divide" reads as one file saved twice.
    """
    for other in taken:
        if slug == other or slug.startswith(other + "-") or other.startswith(slug + "-"):
            return True
    return False


def choose(ranked, taken, text="", argument="", hook="", segments=None, vocab=None,
           max_chars=MAX_CHARS):
    """Pick the best name that is not already in use, and say how hard that was.

    The order here is the point. A clash is answered by taking this clip's NEXT BEST phrase,
    because a different phrase is a better name than the same phrase with a 2 on it. Only
    when a clip has run out of phrases does it borrow its most distinctive remaining word,
    and only when that fails too does a number go on the end.
    """
    vocab = vocab if vocab is not None else load_vocab()
    for rank, cand in enumerate(ranked):
        if not collides(cand.slug, taken):
            return {"name": cand.slug, "rank": rank, "resolved": "first choice" if not rank
                    else "clash: took choice %d of %d" % (rank + 1, len(ranked)),
                    "score": round(cand.score, 2), "said": cand.sentence,
                    "from": cand.source, "suffixed": False}
    if not ranked:
        # Nothing in this clip is a phrase: all filler, or no words at all. Say so rather
        # than inventing something, and do not put a number on the only name there is.
        base, said, src = FALLBACK, "", "nothing usable in the transcript"
        if not collides(base, taken):
            return {"name": base, "rank": 0, "resolved": "no usable phrase in the clip",
                    "score": None, "said": said, "from": src, "suffixed": False}
    else:
        base, said, src = ranked[0].slug, ranked[0].sentence, ranked[0].source

    # Out of phrases. Borrow the most distinctive word this clip has that the name lacks.
    pool = []
    for src_text, _b, _l in sources_of(text, argument, hook, segments):
        for toks, _said in sentences(src_text, vocab):
            pool.extend(w.norm for w in toks if w.kind in ("content", "number"))
    have = set(base.split("-"))
    seen = set()
    for word in pool:
        if word in have or word in seen:
            continue
        seen.add(word)
        trial = (base + "-" + word)[:max_chars].strip("-")
        if not collides(trial, taken):
            return {"name": trial, "rank": 0, "resolved": "clash: added the word %r" % word,
                    "score": None, "said": said, "from": src, "suffixed": False}
    # Last resort. Exact matching only from here: a numeric suffix is the thing that is
    # supposed to make these two names differ, so the prefix rule above cannot apply to it
    # or every candidate would read as a clash with the name it is disambiguating.
    for n in range(2, 10000):
        keep = max(len(FALLBACK), max_chars - 5)
        trial = "%s-%d" % (base[:keep].strip("-"), n)
        if trial not in taken:
            return {"name": trial, "rank": 0,
                    "resolved": "clash: nothing else left, numbered", "score": None,
                    "said": said, "from": src, "suffixed": True}
    raise RuntimeError("10000 clips with the same name is not a naming problem")


def safe(slug):
    """Last gate before the name reaches a filesystem."""
    s = re.sub(r"[^a-z0-9-]+", "-", (slug or "").lower())
    s = re.sub(r"-{2,}", "-", s).strip("-.")
    if not s:
        return FALLBACK
    if s in WINDOWS_RESERVED:
        return s + "-clip"
    return s


def name_batch(pieces, vocab=None, forbidden=(), max_words=MAX_WORDS, max_chars=MAX_CHARS):
    """Name a whole batch at once, which is the only way the names can be made to differ.

    `pieces` is a list of dicts, each with any of: text, argument, hook, segments.
    Returns one result dict per piece, in the same order.
    """
    vocab = vocab if vocab is not None else load_vocab()
    srcs = [sources_of(p.get("text", ""), p.get("argument", ""), p.get("hook", ""),
                       p.get("segments")) for p in pieces]
    docs = []
    for s in srcs:
        stems = []
        for toks, _said in sentences(all_text(s), vocab):
            stems.extend(w.stem for w in toks if w.kind == "content")
        docs.append(stems)
    weight_of = idf_weights(docs)

    ranked = [candidates(s, vocab, weight_of, max_words, max_chars, forbidden) for s in srcs]

    # A clip with a clear favourite is served first, so a clip with several good options is
    # the one that gives ground. Margin is the gap between its best and its second best.
    def margin(rk):
        if not rk:
            return -1e9
        return rk[0].score - (rk[1].score if len(rk) > 1 else rk[0].score - 5.0)
    order = sorted(range(len(pieces)), key=lambda i: -margin(ranked[i]))

    out = [None] * len(pieces)
    taken = set()
    for i in order:
        p = pieces[i]
        got = choose(ranked[i], taken, p.get("text", ""), p.get("argument", ""),
                     p.get("hook", ""), p.get("segments"), vocab, max_chars)
        got["name"] = safe(got["name"])
        got["ranked"] = ranked[i]
        taken.add(got["name"])
        out[i] = got
    return out


# --------------------------------------------------------------------------- cut lists

def piece_input(piece):
    """Pull the namer's inputs out of a cut list piece, in any of the spellings in use."""
    hook = ""
    raw = piece.get("hook")
    if isinstance(raw, dict):
        hook = str(raw.get("text") or "")
    elif isinstance(raw, str):
        hook = raw
    hook = hook or str(piece.get("hook_text") or "")
    segs = [s for s in (piece.get("segments") or []) if isinstance(s, dict)]
    text = " ".join(str(s.get("text") or "") for s in segs)
    if not text:
        cards = piece.get("cards") or piece.get("caption_cards") or []
        bits = []
        for c in cards:
            if isinstance(c, dict) and c.get("text"):
                bits.append(str(c["text"]))
            elif isinstance(c, (list, tuple)) and len(c) >= 3:
                bits.append(str(c[2]))
        text = " ".join(bits)
    return {"hook": hook, "text": text, "segments": segs,
            "argument": str(piece.get("the_argument") or "")}


def pieces_of(doc):
    """A cut list is either {"pieces": [...]} or a bare list of pieces. Both are in use."""
    if isinstance(doc, dict):
        p = doc.get("pieces")
        return p if isinstance(p, list) else []
    return doc if isinstance(doc, list) else []


def main():
    ap = argparse.ArgumentParser(
        description="Give a planned clip a filename somebody could search for.",
        epilog="Nothing is written unless you pass --write or --out.")
    ap.add_argument("cuts", nargs="?", help="a cut list from bin/plan_clips.py, or - for stdin")
    ap.add_argument("--text", help="name one clip from this transcript text instead of a file")
    ap.add_argument("--argument", default="", help="the clip's argument line, with --text")
    ap.add_argument("--hook", default="", help="the clip's hook line, with --text")
    ap.add_argument("--words", help="JSON of extra word lists: filler, weak, keep, openers, "
                                    "units, dates")
    ap.add_argument("--brief", help="a brief whose forbidden phrases must not reach a filename")
    ap.add_argument("--max-words", type=int, default=MAX_WORDS,
                    help="most words in a name (default %d)" % MAX_WORDS)
    ap.add_argument("--max-chars", type=int, default=MAX_CHARS,
                    help="longest name in characters (default %d)" % MAX_CHARS)
    ap.add_argument("--why", action="store_true", help="also print the line each name came from")
    ap.add_argument("--alternatives", type=int, default=0, metavar="N",
                    help="also print the next N names each clip could have had")
    ap.add_argument("--json", action="store_true", help="print the result as JSON")
    ap.add_argument("--write", action="store_true", help="write the names into the cut list")
    ap.add_argument("--out", help="write the renamed cut list here instead of in place")
    a = ap.parse_args()

    # A cap below the floor leaves no candidate at all, and every clip silently comes out
    # called "clip". Say so instead, and hold the cap at the floor.
    if a.max_words < MIN_WORDS:
        print("name_clip: --max-words %d is below the %d a name needs to read as a phrase, "
              "using %d" % (a.max_words, MIN_WORDS, MIN_WORDS), file=sys.stderr)
        a.max_words = MIN_WORDS
    if a.max_chars < 12:
        print("name_clip: --max-chars %d is too tight for a phrase of %d words. Expect "
              "names to fall back." % (a.max_chars, MIN_WORDS), file=sys.stderr)

    try:
        vocab = load_vocab(a.words)
    except (OSError, ValueError) as exc:
        print("name_clip: could not read the word lists in %s: %s" % (a.words, exc),
              file=sys.stderr)
        return 2
    try:
        forbidden = load_forbidden(a.brief)
    except (OSError, ValueError) as exc:
        print("name_clip: could not read the brief %s: %s" % (a.brief, exc), file=sys.stderr)
        return 2

    if a.text:
        ranked = rank_names(a.text, a.argument, a.hook, None, vocab, None, forbidden,
                            a.max_words, a.max_chars)
        got = choose(ranked, set(), a.text, a.argument, a.hook, None, vocab, a.max_chars)
        got["name"] = safe(got["name"])
        if a.json:
            got["alternatives"] = [c.as_dict() for c in ranked[1:1 + a.alternatives]]
            print(json.dumps(got, indent=2))
        else:
            print(got["name"])
            if a.why:
                print("    from %s: %s" % (got["from"], got["said"]))
            for c in ranked[1:1 + a.alternatives]:
                print("    also: %-*s  %.2f" % (a.max_chars, c.slug, c.score))
        return 0

    if not a.cuts:
        ap.error("give a cut list, or --text")
    try:
        if a.cuts == "-":
            doc = json.load(sys.stdin)
        else:
            with open(a.cuts, encoding="utf-8") as fh:
                doc = json.load(fh)
    except (OSError, ValueError) as exc:
        print("name_clip: could not read the cut list %s: %s" % (a.cuts, exc), file=sys.stderr)
        return 2
    pieces = pieces_of(doc)
    if not pieces:
        print("name_clip: no pieces in %s" % a.cuts, file=sys.stderr)
        return 2

    inputs = [piece_input(p) for p in pieces]
    results = name_batch(inputs, vocab, forbidden, a.max_words, a.max_chars)
    # The runners up shown are the ones the batch itself ranked, weights and all. Ranking a
    # second time here would print a different list from the one the name came out of.
    ranked_all = [r.get("ranked") or [] for r in results] if a.alternatives else None

    rows = []
    for k, (piece, got) in enumerate(zip(pieces, results)):
        before = str(piece.get("filename") or piece.get("out") or "")
        before = os.path.basename(before)
        if before.lower().endswith(".mp4"):
            before = before[:-4]
        rows.append({"piece": piece.get("piece") or piece.get("id") or "#%d" % (k + 1),
                     "before": before, "after": got["name"], "why": got["resolved"],
                     "said": got["said"], "from": got["from"], "numbered": got["suffixed"]})

    if a.json:
        if ranked_all:
            for row, rk in zip(rows, ranked_all):
                row["alternatives"] = [c.as_dict() for c in rk
                                       if c.slug != row["after"]][:a.alternatives]
        print(json.dumps({"names": rows}, indent=2))
    else:
        wide = max([len(r["before"]) for r in rows] + [6])
        print("%-5s  %-*s  %s" % ("piece", wide, "before", "after"))
        for k, r in enumerate(rows):
            print("%-5s  %-*s  %s" % (r["piece"], wide, r["before"] or "(none)", r["after"]))
            if a.why:
                print("%s  %s, %s" % (" " * (7 + wide), r["from"], r["why"]))
                if r["said"]:
                    print("%s  said: %s" % (" " * (7 + wide), r["said"][:140]))
            if ranked_all:
                others = [c for c in ranked_all[k] if c.slug != r["after"]]
                for c in others[:a.alternatives]:
                    print("%s  also: %-44s %.2f" % (" " * (7 + wide), c.slug, c.score))
        numbered = [r["piece"] for r in rows if r["numbered"]]
        if numbered:
            print("\n%d name(s) fell back to a number: %s. Those clips had no other phrase "
                  "left. Read them and rename by hand." % (len(numbered), ", ".join(numbered)))

    if a.write or a.out:
        for piece, got in zip(pieces, results):
            piece["filename"] = got["name"]
            if isinstance(piece.get("out"), str) and piece["out"].lower().endswith(".mp4"):
                piece["out"] = os.path.join(os.path.dirname(piece["out"]), got["name"] + ".mp4")
        target = a.out or a.cuts
        if target == "-":
            print(json.dumps(doc, indent=2))
        else:
            with open(target, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            print("\nwrote %d name(s) into %s" % (len(results), target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
