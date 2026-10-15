#!/usr/bin/env python3
"""brand_voice.py: measure how somebody actually writes, out of what they already wrote.

WHY THIS EXISTS. `BRAND-INTAKE.md` is a fifteen minute questionnaire, and a
questionnaire answers a different question than the one asked. Ask a person to
describe their voice and they describe the voice they admire. Their last two
hundred captions contain the real one, already written down, already in public.
Bella, 2026-10-15, on this gap: understand the brand voice from their own posts.
So this reads a folder of their captions or their transcripts and counts things.

WHAT IT COUNTS. Sentence length and its spread, contraction rate, question and
exclamation rate, the words they open sentences with, the way they land the last
sentence of a piece, the words they use more often than ordinary English does,
profanity, emoji, and how much they write per caption. Every figure arrives with
the number of sentences, samples or words behind it, because a 40% question rate
means one thing over 300 sentences and nothing at all over five.

WHAT IT CANNOT KNOW. Whether any of this worked. Nothing here has seen a view
count, a save or a reply, so the profile describes a habit and makes no claim
that the habit sells. It also cannot read tone: sarcasm, warmth and contempt all
count as sentences. Three of the measures lean on a hand written word list
(common English frequency, profanity, imperative verbs), which makes them
approximate by construction, and each one says so where it is reported. It emits
no adjectives at all, on purpose: an adjective is a reading rather than a count.

Usage:
    python3 bin/brand_voice.py samples/ --out specs/voice-profile.json
    python3 bin/brand_voice.py samples/                  # print only
    python3 bin/brand_voice.py posts/ transcripts/ --split blank
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

SUFFIXES = (".txt", ".md", ".srt")

# Twenty is the floor for emitting anything. Below it the openings measure is the
# one that breaks first: a person with four captions appears to open every post
# with the same word, when what happened is that they wrote four captions.
MIN_SAMPLES = 20

# Floors per measure, under which the figure is reported and flagged thin rather
# than suppressed. A reader can see 6 contraction opportunities and judge it.
THIN_SENTENCES = 40
THIN_WORDS = 400
THIN_OPPORTUNITIES = 10

# How many separate samples a word has to appear in before it counts as a habit.
# One caption that says "accountability" nine times is one caption.
MIN_SAMPLES_PER_WORD = 3

WORD = re.compile(r"[a-z][a-z'\-]*")
# A sentence ends on terminal punctuation, and ALSO on a line break. Captions are
# written in lines and routinely carry no full stops at all, so splitting on
# punctuation alone reads a nine line caption as one 120 word sentence, which
# then lands in the median and drags it. Found on real Instagram exports.
SENTENCE_SPLIT = re.compile(r"(?<=[.!?\u2026])[ \t]+|[\r\n]+")
TERMINAL = re.compile(r"([.!?\u2026]+)[\"')\]]*$")

HASHTAG = re.compile(r"#\w+")
MENTION = re.compile(r"@[\w.]+")
URL = re.compile(r"https?://\S+|www\.\S+")

# Emoji, plus the pictographic dingbats and arrows that sit outside the emoji
# blocks. Variation selectors, zero width joiners and skin tones are stripped
# before counting so one emoji counts once instead of three times.
EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u2190-\u21FF\u2122\u3030]")
EMOJI_GLUE = re.compile("[\uFE00-\uFE0F\u200D\U0001F3FB-\U0001F3FF]")

# Contractions, by explicit form. A regex for apostrophe-s would count every
# possessive ("Bella's book") as a contraction and report 90% on somebody who
# writes "do not" throughout.
CONTRACTION = re.compile(
    r"\b(?:\w+n't"
    r"|(?:i|you|we|they|he|she|it|that|there|here|what|who|how|let)"
    r"'(?:s|re|ve|ll|d|m)"
    r"|y'all|ain't|gonna|gotta|wanna)\b", re.I)
# The same meanings written out. Rate is contractions over the two together, so
# the figure answers: given the chance to contract, how often do they take it.
LONG_FORM = re.compile(
    r"\b(?:do not|does not|did not|is not|are not|was not|were not|cannot"
    r"|can not|could not|would not|should not|will not|have not|has not"
    r"|had not|it is|that is|there is|here is|i am|you are|we are|they are"
    r"|he is|she is|let us|i have|i will|i would|you will|we will|going to)\b",
    re.I)

# Shapes a sentence can open with. The names match `niche_calibrate.py` on
# purpose, so a voice profile and a niche profile can be read side by side and
# the overlap is visible: if the niche rewards opening on a number and this
# person never does, that is the finding.
OPENING_SHAPES = {
    "question":     re.compile(r"^(how|what|why|when|where|who|which|can|should|is|are|do|does|did|if)\b", re.I),
    "number":       re.compile(r"^\W*(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b", re.I),
    "imperative":   re.compile(r"^(stop|start|never|always|don'?t|do not|avoid|try|watch|listen|read|build|make|get|go|take|tell|ask|look|save|share|follow|remember|think about|notice)\b", re.I),
    "first_person": re.compile(r"^(i|i'?m|i'?ve|i'?d|i'?ll|we|we'?re|my|our|me)\b", re.I),
    "you":          re.compile(r"^(you|you'?re|you'?ve|your|yours)\b", re.I),
    "conjunction":  re.compile(r"^(and|but|so|because|or|yet|which)\b", re.I),
}

WH_WORD = re.compile(r"^(how|what|why|when|where|who|which)\b", re.I)

# Verbs that start an instruction. Hand listed, so a closing command phrased with
# a verb outside this list reads as a statement. The count is a floor.
IMPERATIVE_CLOSE = re.compile(
    r"^(stop|start|go|get|do|don'?t|never|always|try|make|take|tell|ask|look"
    r"|listen|watch|read|write|build|send|save|follow|share|comment|drop|book"
    r"|click|tap|join|remember|keep|let|give|pick|choose|say|put|use|call|dm"
    r"|message|subscribe|sign|grab|check|bring|find|open|close|run|wait|come)\b",
    re.I)
# Enough of a verb vocabulary to tell "the whole thing collapsed" from "every
# single time". A closing with no word from this list and very few words is
# counted as a fragment. Without a parser that is a heuristic, and it is reported
# as fragment_like for that reason.
VERBISH = set("""is are was were am be been being do does did done have has had
get got go goes going went come came take took taken make made makes say says
said see saw seen know knew known think thought want wanted need needed feel
felt give gave look looks looked tell told ask asked try tried keep kept put
find found works work worked happen happened happens means meant will would can
could should may might must let lets stop stops stopped start started matters
mattered counts counted costs cost pays paid sells sold buys bought wins won
lose lost loses built build builds show showed shown becomes became""".split())

# Counted, never masked. A person who swears in half their captions and gets a
# clean draft back notices immediately, and the fix costs them a rewrite.
PROFANITY = re.compile(
    r"\b(fuck\w*|shit\w*|bullshit|shitty|ass|asses|asshole\w*|arse\w*|bitch\w*"
    r"|bastard\w*|damn|damned|goddamn\w*|dammit|hell|crap\w*|piss\w*|dick\w*"
    r"|cock|prick|cunt\w*|twat\w*|wank\w*|bollocks|bloody|slut\w*|whore\w*"
    r"|screwed|freaking|frickin\w*|fricking|f\*+k\w*|s\*+t)\b", re.I)

# Occurrences per million words in ordinary written English, rounded hard and
# entered by hand from published frequency lists. Rough on purpose: a verbal tic
# shows up at five or twenty times ordinary usage, so a 30% error in the
# reference moves nothing that gets reported. Words outside this table get no
# lift figure at all, because inventing a denominator for them would turn every
# topic noun into a finding. They are reported as repetition instead.
PER_MILLION = {
    "the": 49000, "to": 24000, "and": 23000, "of": 20000, "a": 19000,
    "in": 15000, "i": 12000, "is": 9500, "it": 9000, "that": 9000,
    "you": 7500, "for": 7000, "was": 6000, "with": 5500, "on": 5200,
    "as": 4500, "have": 4000, "but": 3800, "be": 3600, "they": 3200,
    "are": 3200, "this": 3000, "not": 2900, "at": 2800, "we": 2700,
    "he": 2600, "from": 2300, "so": 2200, "or": 2000, "all": 1800,
    "my": 1800, "do": 1700, "what": 1600, "if": 1500, "had": 1500,
    "me": 1400, "no": 1300, "one": 1300, "his": 1300, "when": 1250,
    "your": 1200, "has": 1200, "there": 1150, "their": 1150, "about": 1100,
    "which": 1050, "out": 1050, "up": 1000, "can": 1000, "like": 1000,
    "she": 1000, "were": 1000, "just": 950, "her": 900, "them": 900,
    "know": 900, "would": 900, "get": 850, "been": 600, "more": 700,
    "time": 750, "now": 700, "how": 700, "then": 600, "will": 650,
    "think": 650, "see": 620, "people": 600, "good": 560, "want": 550,
    "very": 520, "go": 520, "who": 500, "him": 500, "did": 500,
    "say": 350, "said": 800, "than": 500, "make": 500, "because": 480,
    "even": 480, "way": 470, "much": 450, "only": 420, "where": 420,
    "really": 430, "work": 400, "our": 400, "year": 400, "could": 400,
    "here": 400, "right": 380, "back": 370, "after": 330, "many": 350,
    "years": 350, "take": 350, "need": 340, "thing": 330, "also": 320,
    "most": 320, "should": 320, "still": 320, "day": 310, "every": 300,
    "look": 300, "feel": 280, "new": 280, "why": 300, "us": 300,
    "too": 300, "before": 300, "come": 300, "being": 300, "something": 300,
    "first": 270, "things": 260, "love": 250, "give": 250, "may": 250,
    "great": 250, "better": 240, "never": 240, "always": 230, "little": 230,
    "while": 280, "life": 280, "world": 300, "home": 250, "each": 200,
    "again": 220, "doing": 220, "put": 220, "does": 220, "nothing": 220,
    "took": 200, "find": 200, "found": 200, "same": 200, "having": 200,
    "might": 200, "anything": 180, "everything": 180, "best": 180,
    "money": 180, "few": 180, "less": 180, "lot": 180, "must": 180,
    "tell": 180, "actually": 180, "hard": 150, "help": 170, "start": 170,
    "own": 150, "let": 150, "keep": 150, "show": 150, "told": 160,
    "try": 150, "free": 150, "today": 150, "family": 150, "business": 150,
    "maybe": 150, "whole": 130, "ask": 130, "trying": 120, "thinking": 60,
    "getting": 150, "looking": 120, "making": 120, "going": 500,
    "someone": 120, "everyone": 100, "nobody": 50, "week": 120,
    "days": 120, "job": 120, "team": 100, "gave": 120, "probably": 120,
    "yesterday": 60, "tomorrow": 60, "stop": 120, "easy": 90,
    "simple": 60, "super": 60, "kids": 60, "crazy": 50, "absolutely": 50,
    "huge": 40, "amazing": 40, "totally": 40, "literally": 40, "post": 40,
    "offer": 40, "basically": 35, "awesome": 25, "honestly": 25,
    "content": 25, "brand": 25, "clients": 25, "client": 20,
}


def strip_srt(text):
    """Cue text, joined. Timestamps, indexes and markup removed.

    Cues break mid sentence, so the text is joined with spaces and sentence
    splitting happens afterwards on the joined string. Splitting per cue would
    report a median sentence of six words for every transcript ever made.
    """
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.isdigit() or "-->" in s:
            continue
        out.append(re.sub(r"<[^>]+>", "", s))
    return " ".join(out)


def clean_text(text):
    """Markdown furniture off, links off, the words left alone."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)   # keep link text
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^\s{0,3}>\s?", "", text, flags=re.M)
    text = re.sub(r"^\s{0,3}[-*+]\s+", "", text, flags=re.M)
    text = re.sub(r"^\s{0,3}\d+[.)]\s+", "", text, flags=re.M)
    text = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", text)
    # Horizontal rules are left standing on purpose. `--split rule` needs them,
    # and stripping them here is what made that mode silently find one sample in
    # a file of 25 captions. A rule that survives into the other modes carries no
    # words, so it reaches no measure.
    return text


def samples_from(paths, split):
    """Every readable sample, with the file it came from.

    A sample is one piece with its own opening and its own ending, because the
    openings and closings measures mean nothing across a merged pile. By default
    one file is one sample. `--split rule` cuts a file on horizontal rules and
    `--split blank` on blank lines, which is how people paste a batch of
    captions into a single document.
    """
    files = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            files += [f for f in sorted(path.rglob("*"))
                      if f.suffix.lower() in SUFFIXES and not f.name.startswith((".", "_"))]
        elif path.exists():
            files.append(path)
        else:
            print("  skipped, no such path: %s" % p, file=sys.stderr)

    out = []
    for f in sorted(set(files)):
        try:
            raw = f.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            print("  skipped, unreadable: %s (%s)" % (f, e), file=sys.stderr)
            continue
        raw = raw.replace("\u2019", "'").replace("\u2018", "'")
        raw = raw.replace("\u201c", '"').replace("\u201d", '"')
        if f.suffix.lower() == ".srt":
            # A transcript is continuous speech. It has one opening and one
            # ending however it is split, so splitting is refused here.
            chunks, kind = [strip_srt(raw)], "transcript"
        else:
            body, kind = clean_text(raw), "written"
            if split == "rule":
                chunks = re.split(r"(?m)^\s*(?:[-=*_]\s*){3,}\s*$", body)
            elif split == "blank":
                chunks = re.split(r"\n\s*\n", body)
            else:
                chunks = [body]
        for i, c in enumerate(chunks, 1):
            # Hashtags, handles and URLs do not count toward the floor, so a block
            # of nothing but hashtags is dropped here instead of arriving at the
            # measures as a sample with no sentence in it.
            if len(words_of(c)) < 3:
                continue
            out.append({"source": str(f), "ord": i, "kind": kind, "text": c.strip()})
    return out


def sentences_of(text):
    """(sentence, terminal punctuation or '') for each sentence."""
    out = []
    for raw in SENTENCE_SPLIT.split(text):
        s = raw.strip()
        s = URL.sub(" ", s)
        s = HASHTAG.sub(" ", s)          # a hashtag block is not a sentence
        s = MENTION.sub(" ", s)
        s = EMOJI_GLUE.sub("", s)
        s = EMOJI.sub(" ", s).strip()
        if not WORD.findall(s.lower()):
            continue
        m = TERMINAL.search(s)
        out.append((s, m.group(1) if m else ""))
    return out


def words_of(text):
    text = URL.sub(" ", HASHTAG.sub(" ", MENTION.sub(" ", text)))
    return WORD.findall(text.lower())


def quantiles(xs):
    xs = sorted(xs)
    if not xs:
        return {}

    def at(q):
        if len(xs) == 1:
            return xs[0]
        i = q * (len(xs) - 1)
        lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
        return round(xs[lo] + (xs[hi] - xs[lo]) * (i - lo), 1)

    return {"min": xs[0], "p10": at(0.10), "p25": at(0.25), "median": at(0.50),
            "p75": at(0.75), "p90": at(0.90), "max": xs[-1]}


def first_word(sentence):
    m = WORD.search(sentence.lower())
    return m.group(0) if m else ""


def classify_close(sentence, terminal):
    """How the last sentence of a piece lands.

    One class each, decided in this order: a question mark wins, then an opening
    imperative verb, then shortness with no verb in it. Everything else is a
    statement. The fragment test is a heuristic without a parser, which is why it
    is named fragment_like wherever it is reported.
    """
    if "?" in terminal:
        return "question"
    if IMPERATIVE_CLOSE.match(sentence.strip()):
        return "command"
    ws = words_of(sentence)
    has_verb = any(w in VERBISH for w in ws)
    if (not terminal and len(ws) <= 6) or (not has_verb and len(ws) <= 5):
        return "fragment_like"
    return "statement"


def over_used(word_counts, doc_counts, total_words, top=14):
    """Words used more often than ordinary English uses them.

    Lift is this person's rate over the reference rate, both per million. Only
    words present in the reference table get a lift, and only words that turned
    up in three or more separate samples get reported at all.
    """
    lifted, repeated = [], []
    per_million = 1_000_000 / max(1, total_words)
    for w, n in word_counts.items():
        if doc_counts[w] < MIN_SAMPLES_PER_WORD or n < 4:
            continue
        ref = PER_MILLION.get(w)
        if ref:
            lifted.append({"word": w, "uses": n, "in_samples": doc_counts[w],
                           "lift": round((n * per_million) / ref, 1)})
        else:
            repeated.append({"word": w, "uses": n, "in_samples": doc_counts[w]})
    lifted.sort(key=lambda d: -d["lift"])
    repeated.sort(key=lambda d: (-d["in_samples"], -d["uses"]))
    return lifted[:top], repeated[:top]


def build(samples, split):
    sent_lengths, openers, shape_counts = [], Counter(), Counter()
    closings, close_first = Counter(), Counter()
    questions = exclamations = unpunctuated = n_sentences = 0
    contractions = long_forms = 0
    emoji_total, emoji_samples = 0, 0
    emoji_kinds = Counter()
    profane_hits, profane_samples = 0, 0
    profane_words = Counter()
    hashtags = mentions = links = 0
    word_counts, doc_counts = Counter(), Counter()
    words_per_sample, words_per_para = [], []
    per_source = Counter()
    first_person = second_person = plural_person = 0
    total_words = 0

    for s in samples:
        per_source[s["source"]] += 1
        text = s["text"]
        hashtags += len(HASHTAG.findall(text))
        mentions += len(MENTION.findall(text))
        links += len(URL.findall(text))

        stripped = EMOJI_GLUE.sub("", text)
        found = EMOJI.findall(stripped)
        if found:
            emoji_samples += 1
            emoji_total += len(found)
            emoji_kinds.update(found)

        ws = words_of(text)
        total_words += len(ws)
        words_per_sample.append(len(ws))
        word_counts.update(ws)
        doc_counts.update(set(ws))
        first_person += sum(1 for w in ws if w in ("i", "me", "my", "mine", "myself"))
        plural_person += sum(1 for w in ws if w in ("we", "us", "our", "ours"))
        second_person += sum(1 for w in ws if w in ("you", "your", "yours", "yourself"))

        contractions += len(CONTRACTION.findall(text))
        long_forms += len(LONG_FORM.findall(text))

        hits = PROFANITY.findall(text)
        if hits:
            profane_samples += 1
            profane_hits += len(hits)
            profane_words.update(h.lower() for h in hits)

        if s["kind"] == "written":
            for para in re.split(r"\n\s*\n", text):
                n = len(words_of(para))
                if n:
                    words_per_para.append(n)

        sents = sentences_of(text)
        n_sentences += len(sents)
        for i, (sent, term) in enumerate(sents):
            sent_lengths.append(len(words_of(sent)))
            w = first_word(sent)
            if w:
                openers[w] += 1
            if "?" in term:
                questions += 1
            if "!" in term:
                exclamations += 1
            if not term:
                unpunctuated += 1
            if i == 0:
                head = sent.strip()
                for name, rx in OPENING_SHAPES.items():
                    if not rx.match(head):
                        continue
                    # "Do not do this." opens on an auxiliary and asks nothing.
                    # A title gets away with counting that as a question shape,
                    # and `niche_calibrate.py` does, because a title has no
                    # punctuation to go on. A sentence has. So an auxiliary
                    # opening needs the question mark, while a wh word counts on
                    # its own. Found on a fixture of 20 flat instructions that
                    # came back reading 100% question.
                    if name == "question" and "?" not in term and not WH_WORD.match(head):
                        continue
                    shape_counts[name] += 1
        if sents:
            last, term = sents[-1]
            closings[classify_close(last, term)] += 1
            close_first[first_word(last)] += 1

    lifted, repeated = over_used(word_counts, doc_counts, total_words)
    opportunities = contractions + long_forms
    n = len(samples)

    def rate(hits, denom):
        return round(hits / denom, 3) if denom else None

    return {
        "built_from": {
            "samples": n,
            "files": len(per_source),
            "words": total_words,
            "sentences": n_sentences,
            "split": split,
            "sample_means": "one sample is one piece with its own opening and ending",
            "samples_per_file": dict(sorted(per_source.items())),
        },
        "caveat": ("Counts only. Nothing here has seen a view, a save or a reply, so this "
                   "describes a habit and claims nothing about what the habit earns. Tone is "
                   "unreadable by counting. The English frequency table, the profanity list and "
                   "the imperative verb list are hand written, so figures resting on them are "
                   "approximate and are flagged where they are reported."),
        "sentence_length_words": dict(quantiles(sent_lengths),
                                      n=n_sentences, n_of="sentences",
                                      under_8=rate(sum(1 for x in sent_lengths if x < 8), n_sentences),
                                      over_25=rate(sum(1 for x in sent_lengths if x > 25), n_sentences),
                                      thin=n_sentences < THIN_SENTENCES),
        "contractions": {
            "contracted": contractions,
            "written_out": long_forms,
            "rate_when_possible": rate(contractions, opportunities),
            "n": opportunities, "n_of": "chances to contract",
            "thin": opportunities < THIN_OPPORTUNITIES,
            "how": "explicit form list, so possessives are excluded",
        },
        "punctuation": {
            "question_rate": rate(questions, n_sentences),
            "questions": questions,
            "exclamation_rate": rate(exclamations, n_sentences),
            "exclamations": exclamations,
            "unpunctuated_sentences": unpunctuated,
            "n": n_sentences, "n_of": "sentences",
        },
        "openings": {
            "commonest_first_words": [{"word": w, "count": c} for w, c in openers.most_common(15)],
            "distinct_first_words": len(openers),
            "n": n_sentences, "n_of": "sentences",
            "first_sentence_shapes": [{"shape": k, "samples": v, "rate": rate(v, n)}
                                      for k, v in shape_counts.most_common()],
            "shapes_n": n, "shapes_n_of": "samples, first sentence only",
        },
        "closings": {
            "classes": [{"lands_on": k, "count": v, "rate": rate(v, n)}
                        for k, v in closings.most_common()],
            "commonest_last_sentence_first_word": [{"word": w, "count": c}
                                                   for w, c in close_first.most_common(8) if w],
            "n": sum(closings.values()), "n_of": "samples with a readable last sentence",
            "how": "question mark, then an opening imperative verb, then short with no verb. "
                   "fragment_like is a heuristic without a parser and reads as a floor",
        },
        "over_used_vs_ordinary_english": {
            "words": lifted,
            "n": total_words, "n_of": "words",
            "reference": "hand entered frequency table, %d words, rounded" % len(PER_MILLION),
            "how": "lift is their rate over the reference rate, both per million. "
                   "Reported only for words appearing in %d or more samples" % MIN_SAMPLES_PER_WORD,
        },
        "repeated_without_a_reference": {
            "words": repeated,
            "n": total_words, "n_of": "words",
            "how": "outside the frequency table, so these carry a count and no lift. "
                   "Mostly their subject matter",
        },
        "profanity": {
            "present": profane_hits > 0,
            "uses": profane_hits,
            "samples_containing": profane_samples,
            "share_of_samples": rate(profane_samples, n),
            "per_1000_words": round(profane_hits * 1000 / total_words, 2) if total_words else None,
            "words": [{"word": w, "count": c} for w, c in profane_words.most_common()],
            "n": n, "n_of": "samples",
            "how": "word list, uncensored and unranked by severity. Mild and strong count alike",
        },
        "emoji": {
            "present": emoji_total > 0,
            "uses": emoji_total,
            "samples_containing": emoji_samples,
            "share_of_samples": rate(emoji_samples, n),
            "per_sample": round(emoji_total / n, 2) if n else None,
            "commonest": [{"emoji": e, "count": c} for e, c in emoji_kinds.most_common(10)],
            "n": n, "n_of": "samples",
        },
        "length_per_piece": {
            "words_per_sample": dict(quantiles(words_per_sample), n=n, n_of="samples"),
            "words_per_paragraph": dict(quantiles(words_per_para),
                                        n=len(words_per_para), n_of="paragraphs",
                                        note="written samples only, transcripts have no paragraphs"),
            "hashtags_per_sample": round(hashtags / n, 2) if n else None,
            "mentions_per_sample": round(mentions / n, 2) if n else None,
            "links_total": links,
        },
        "who_they_talk_about": {
            "i_me_my": first_person,
            "we_us_our": plural_person,
            "you_your": second_person,
            "per_1000_words": {
                "i_me_my": round(first_person * 1000 / total_words, 1) if total_words else None,
                "we_us_our": round(plural_person * 1000 / total_words, 1) if total_words else None,
                "you_your": round(second_person * 1000 / total_words, 1) if total_words else None,
            },
            "n": total_words, "n_of": "words",
        },
        "thin_overall": total_words < THIN_WORDS,
    }


def refuse(samples, split):
    """Say the count, say the floor, say what closes the gap, write nothing."""
    per_source = Counter(s["source"] for s in samples)
    print("\nREFUSED. %d samples found, and %d is the floor." % (len(samples), MIN_SAMPLES))
    if per_source:
        print("\n  what it found")
        for src, c in sorted(per_source.items()):
            print("    %-56s %d" % (src[-56:], c))
    else:
        print("\n  Nothing readable. It reads %s, skipping dotfiles and anything"
              % ", ".join(SUFFIXES))
        print("  starting with an underscore, and ignores pieces under 3 words.")
    print("\n  what it needs: %d more. A sample is one piece with its own opening and"
          % (MIN_SAMPLES - len(samples)))
    print("  ending: one caption, one post, one email, one transcript.")
    print("  Options, cheapest first:")
    print("    --split blank   one file holding many captions, separated by blank lines")
    print("    --split rule    one file, captions separated by a line of --- or ===")
    print("    add files       their last 20 captions, pasted one per .txt file")
    print("\n  Why the floor. Over 8 captions a person appears to open every piece with")
    print("  the same word. Over 20 that reading starts to survive the next 20, and the")
    print("  openings measure is the one that breaks first. A profile emitted here would")
    print("  read as a measurement while being an accident of %d posts.\n" % len(samples))


def report(p):
    b = p["built_from"]
    print("\n%d samples from %d files, %d words, %d sentences (split: %s)"
          % (b["samples"], b["files"], b["words"], b["sentences"], b["split"]))
    if p["thin_overall"]:
        print("  THIN. Under %d words in total, so read every rate below as a hint."
              % THIN_WORDS)

    s = p["sentence_length_words"]
    print("\n  SENTENCE LENGTH, words (n=%d sentences)" % s["n"])
    print("    median %s   middle half %s to %s   range %s to %s"
          % (s["median"], s["p25"], s["p75"], s["min"], s["max"]))
    print("    %.0f%% under 8 words, %.0f%% over 25"
          % (s["under_8"] * 100, s["over_25"] * 100))
    if s["thin"]:
        print("    thin, under %d sentences" % THIN_SENTENCES)

    c = p["contractions"]
    if c["rate_when_possible"] is None:
        print("\n  CONTRACTIONS: no chance to contract appeared in the text")
    else:
        print("\n  CONTRACTIONS  %.0f%% of the time (%d contracted, %d written out)"
              % (c["rate_when_possible"] * 100, c["contracted"], c["written_out"]))
        if c["thin"]:
            print("    thin, %d chances in total" % c["n"])

    q = p["punctuation"]
    print("\n  PUNCTUATION (n=%d sentences)" % q["n"])
    print("    questions %.0f%% (%d)   exclamations %.0f%% (%d)   no end mark at all: %d"
          % (q["question_rate"] * 100, q["questions"],
             q["exclamation_rate"] * 100, q["exclamations"],
             q["unpunctuated_sentences"]))

    o = p["openings"]
    print("\n  OPENINGS, first word of a sentence (n=%d sentences, %d distinct)"
          % (o["n"], o["distinct_first_words"]))
    print("    " + "  ".join("%s(%d)" % (w["word"], w["count"])
                             for w in o["commonest_first_words"][:10]))
    shapes = o["first_sentence_shapes"]
    print("    first sentence of a piece, by shape (n=%d samples): %s"
          % (o["shapes_n"],
             ", ".join("%s %d" % (x["shape"], x["samples"]) for x in shapes) or "none matched"))

    cl = p["closings"]
    print("\n  CLOSINGS, last sentence of a piece (n=%d samples)" % cl["n"])
    for x in cl["classes"]:
        print("    %-14s %3d  %.0f%%" % (x["lands_on"], x["count"], x["rate"] * 100))

    ou = p["over_used_vs_ordinary_english"]
    print("\n  OVER USED against ordinary English, lift on a %d word reference table"
          % len(PER_MILLION))
    if ou["words"]:
        for w in ou["words"][:10]:
            print("    %-14s %4.1fx   %d uses across %d samples"
                  % (w["word"], w["lift"], w["uses"], w["in_samples"]))
    else:
        print("    nothing cleared %d samples and 4 uses" % MIN_SAMPLES_PER_WORD)
    rep = p["repeated_without_a_reference"]["words"]
    print("    outside the table, so counted and not lifted: " +
          (", ".join("%s(%d)" % (w["word"], w["uses"]) for w in rep[:10]) or "none"))

    pr = p["profanity"]
    if pr["present"]:
        print("\n  PROFANITY  yes. %d uses, in %d of %d samples, %.2f per 1000 words"
              % (pr["uses"], pr["samples_containing"], pr["n"], pr["per_1000_words"]))
        print("    " + ", ".join("%s(%d)" % (w["word"], w["count"]) for w in pr["words"][:10]))
    else:
        print("\n  PROFANITY  none in %d samples, by the built in word list" % pr["n"])

    e = p["emoji"]
    if e["present"]:
        print("\n  EMOJI  %d uses, in %d of %d samples, %.2f per sample: %s"
              % (e["uses"], e["samples_containing"], e["n"], e["per_sample"],
                 " ".join(x["emoji"] for x in e["commonest"][:8])))
    else:
        print("\n  EMOJI  none in %d samples" % e["n"])

    L = p["length_per_piece"]
    ws, wp = L["words_per_sample"], L["words_per_paragraph"]
    print("\n  LENGTH  median %s words per sample (n=%d), %s to %s in the middle half"
          % (ws["median"], ws["n"], ws["p25"], ws["p75"]))
    if wp.get("median") is not None:
        print("    median %s words per paragraph (n=%d paragraphs, written samples only)"
              % (wp["median"], wp["n"]))
    print("    hashtags %s per sample, mentions %s per sample, %d links in total"
          % (L["hashtags_per_sample"], L["mentions_per_sample"], L["links_total"]))

    w = p["who_they_talk_about"]["per_1000_words"]
    print("\n  WHO THEY TALK ABOUT, per 1000 words: i/me/my %s   we/us/our %s   you/your %s"
          % (w["i_me_my"], w["we_us_our"], w["you_your"]))

    top_close = max(p["closings"]["classes"], key=lambda x: x["count"])["lands_on"] \
        if p["closings"]["classes"] else "nothing readable"
    opens = ", ".join(x["word"] for x in o["commonest_first_words"][:3]) or "nothing repeated"
    tics = ", ".join(x["word"] for x in ou["words"][:3]) or "nothing over used"
    print("\n  So: sentences of about %s words, contracting %s, questions in %.0f%% of them."
          % (s["median"],
             "%.0f%% of the time" % (c["rate_when_possible"] * 100)
             if c["rate_when_possible"] is not None else "at a rate this text cannot show",
             q["question_rate"] * 100))
    print("      Sentences open on %s. A piece lands on a %s. Tics: %s."
          % (opens, top_close, tics))
    print("      %s %s\n"
          % ("Swears, %d times in %d samples." % (pr["uses"], pr["n"]) if pr["present"]
             else "No profanity in this sample.",
             "Emoji %.2f per sample." % e["per_sample"] if e["present"] else "No emoji."))
    print("  A habit is all this measures. Whether it earns anything is unmeasured here,")
    print("  and reading tone off counts is impossible, so check it against a post you")
    print("  know worked before drafting in it.\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+",
                    help="folders or files of their own writing (%s)" % ", ".join(SUFFIXES))
    ap.add_argument("--split", choices=("file", "rule", "blank"), default="rule",
                    help="what counts as one sample. file: one file is one sample. "
                         "rule: cut on a line of --- or === (default). "
                         "blank: cut on blank lines. Transcripts are never cut")
    ap.add_argument("--out", help="write the profile here, usually specs/voice-profile.json")
    a = ap.parse_args()

    samples = samples_from(a.paths, a.split)
    if len(samples) < MIN_SAMPLES:
        refuse(samples, a.split)
        sys.exit(2)

    profile = build(samples, a.split)
    report(profile)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(profile, indent=1, ensure_ascii=False))
        print("  wrote %s" % a.out)


if __name__ == "__main__":
    main()
