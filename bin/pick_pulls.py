#!/usr/bin/env python3
"""pick_pulls.py: find the 35 to 75 second moments in a transcript that suit short form.

    python3 bin/pick_pulls.py transcript.srt            # top 5, JSON on stdout
    python3 bin/pick_pulls.py transcript.json -n 8 --min 35 --max 75
    python3 bin/pick_pulls.py transcript.srt --out pulls.json
    cat transcript.srt | python3 bin/pick_pulls.py -     # stdin

Standard library only. Needs no Pillow, no ffmpeg, no network, costs nothing. Runs on any Python 3.8 or newer
(on Windows write `python` for `python3`).

INPUT
    SRT (what Descript, Whisper and most transcription tools emit), VTT (same parser), or JSON:
    [{"start": 12.4, "end": 15.9, "text": "..."}, ...]  seconds as numbers or "HH:MM:SS.mmm".
    A Whisper-style {"segments": [...]} wrapper is accepted too. Also the bracket format
    whisper.cpp prints and bin/transcribe.py writes as its reading copy:
    [01:24.64 -> 01:26.52] (84.64-86.52)   <<< GAP 14.6s  then the line of speech.

OUTPUT
    JSON: {"source", "caveats", "stats", "pulls": [...]}. Each pull carries start, end, duration,
    the opening sentence, the full text, a score, and WHY it scored: a list of
    {signal, points, evidence} plus a one-line why_text. The why matters more than the score. The
    score is only comparable inside one file, it is not a calibrated probability of performing.

THE RULES IT IMPLEMENTS (common short-form practice)
    1. A pull is 35 to 75 seconds and holds one complete thought with a beginning.
       Windows are built from whole sentences and only end on a finished sentence.
    2. Never start mid-sentence. A window can only start at a sentence boundary. Starts that open
       on a dangling connective ("And so", "But", "Yeah") are skipped because the earlier start is
       already a candidate. After scoring, a one-sentence lead-in is added if the sentence before
       was spoken without a pause (the "start one sentence earlier than feels right" rule).
       Every pull is then checked again by a second, independent test on the raw word stream,
       and dropped with a warning if it fails.
    3. Pull where the speaker changes ENERGY.   <-- THIS IS THE PART TEXT CANNOT DO.

WHAT TEXT CANNOT MEASURE, STATED PLAINLY
    Energy lives in the waveform: loudness after a pause, pace, pitch, a laugh, a voice dropping to
    a near whisper. A transcript contains none of it. This script scores TOPIC STRUCTURE and
    approximates energy with three weak proxies: the silence before the opening line (from cue
    gaps), sentence-length rhythm (a short punchy line after long ones), and exclamation marks.
    Treat the output as a shortlist of places to LOOK, then open the waveform at each start and
    confirm there is a loud bit after a pause. Where the audio disagrees, the audio wins.

SIGNALS, each from text alone
    hook (opening line is a question, has a number, addresses "you", is short), question then
    answer inside the window, concrete numbers and names, contrast or reversal words (but, until,
    turns out, the problem is, that's when), direct address (you, your), a strong closing line,
    sentence completeness and no long silence inside, energy proxies, plus a penalty for filler
    (um, uh, you know, kind of, I mean, one-word acknowledgements) and a small bonus for 45 to 60 s.

TIMING
    SRT only gives cue-level times. Where a sentence boundary falls inside a cue the time is
    interpolated by character count, so such a start can be off by up to about a second. The field
    start_estimated says when that happened. Snap to the real word start in the audio.
"""
import argparse
import json
import re
import statistics
import sys

MIN_DUR, MAX_DUR = 35.0, 75.0
SWEET_LO, SWEET_HI = 45.0, 60.0
LONG_GAP_BREAK = 1.5        # a silence this long between cues is treated as a sentence boundary
INNER_GAP_PENALTY = 1.8     # silence inside a window longer than this costs points
INNER_GAP_REJECT = 4.0      # silence inside a window longer than this rejects the window
LEAD_IN_MAX_GAP = 1.0       # add the previous sentence only if it was said with less pause than this
LEAD_IN_MAX_LEN = 12.0
WEAK_PUNCT_RATIO = 1 / 60   # fewer terminal marks than this per word means "no usable punctuation"

# ---------------------------------------------------------------- word lists

NUMWORDS = {
    "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
    "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty",
    "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety", "hundred", "thousand",
    "million", "billion", "percent", "dollars", "double", "triple", "half",
}
CONTRAST = [
    (re.compile(r"\bbut\b(?!\s+yeah)"), "but"),
    (re.compile(r"\buntil\b"), "until"),
    (re.compile(r"\bturns out\b"), "turns out"),
    (re.compile(r"\bthe (?:problem|catch|truth|trick|real \w+|actual \w+|thing) (?:is|was)\b"), "the problem is"),
    (re.compile(r"\bexcept\b"), "except"),
    (re.compile(r"\binstead\b"), "instead"),
    (re.compile(r"\bactually\b"), "actually"),
    (re.compile(r"\bhowever\b"), "however"),
    (re.compile(r"\bin fact\b"), "in fact"),
    (re.compile(r"\bthat'?s when\b"), "that's when"),
    (re.compile(r"\bhere'?s the thing\b"), "here's the thing"),
    (re.compile(r"\bi (?:realized|realised|didn'?t realize|didn'?t realise)\b"), "I realized"),
    (re.compile(r"\b(?:wasn'?t|isn'?t|not)\b[^.?!]{0,50}\b(?:it was|it is|it'?s|but)\b"), "not X, it is Y"),
]
YOU = re.compile(r"\b(?:you|your|yours|yourself|you'?re|you'?ve|you'?ll|you'?d)\b")
YOU_KNOW = re.compile(r"\byou know\b")
FILLER = re.compile(
    r"\b(?:um+|uh+|uhm+|er|erm|hmm+|mm+-?hmm+|you know|kind of|sort of|i mean|basically|literally|"
    r"i guess|or whatever|and stuff|and things|and yeah|so yeah|like,)\b"
)
ACK_SENTENCE = re.compile(
    r"^(?:yeah|yes|yep|right|okay|ok|alright|sure|mm+-?hmm+|mm+|uh-huh|exactly|totally|true|cool|"
    r"nice|great|wow|oh|ah|thanks|thank you|yeah yeah|no)\W*$"
)
OPENER_BAD = re.compile(
    r"^[\"'“‘(]*(?:and|but|because|so|which|or|plus|then|anyway|anyways|yeah|right|okay|ok|alright|"
    r"well|mm+|uh|um|oh|that'?s why|that'?s what|which is why)\b(?:[ ,]|$)",
    re.I,
)
CLOSE_STRONG = re.compile(
    r"\b(?:never|always|nothing|everything|only|real|the point|that'?s (?:the|why|what|how)|"
    r"is not|isn'?t|is a|is the|means|not a|not the|none of|all of)\b"
)
CLOSE_WEAK = re.compile(
    r"^(?:so )?(?:yeah|anyway|anyways|okay|alright|right|whatever|thank you|thanks|you know|"
    r"i don'?t know|um|uh)\b|(?:stuff|things|or whatever|you know|and yeah|i guess|and so on)\W*$"
)
PROMO = re.compile(
    r"\b(?:sponsor|sponsored|brought to you by|use the code|promo code|show notes|leave a review|"
    r"subscribe|like and subscribe|thanks for listening|thank you all for listening|welcome back|"
    r"see you next (?:week|time)|link in (?:the )?(?:bio|description))\b"
)
ANAPHOR = re.compile(r"^[\"'“‘(]*(?:it|that|this|these|those|they|he|she|there|then|which|the next)\b", re.I)
ABBREV = {"mr.", "mrs.", "ms.", "dr.", "st.", "vs.", "e.g.", "i.e.", "etc.", "a.m.", "p.m.", "u.s.",
          "no.", "inc.", "jr.", "sr.", "prof."}
NAME_STOP = {"I", "I'm", "I'll", "I've", "I'd", "OK", "Okay", "Yeah", "Yes", "No", "So", "And", "But",
             "Um", "Uh", "Oh", "Well", "Right", "Alright"}
TERMINAL = re.compile(r"[.?!]+[\"')\]”’]*$")
SPEAKER_LABEL = re.compile(r"^(?:>>\s*|-\s+|(?:SPEAKER[ _]?\d+|[A-Z]{2,}(?: [A-Z]{2,})?)\s*:\s*)")


# ---------------------------------------------------------------- parsing

def tc_to_sec(s):
    s = s.strip().replace(",", ".")
    parts = s.split(":")
    sec = 0.0
    for p in parts:
        sec = sec * 60 + float(p)
    return sec


def clean_cue_text(t):
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"\{\\[^}]*\}", "", t)
    t = re.sub(r"\[[^\]]{0,30}\]|\((?:music|laughs?|laughter|applause|inaudible)[^)]*\)", " ", t, flags=re.I)
    return t


def parse_srt(text):
    cues = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n").strip())
    pat = re.compile(r"(\d+:\d{2}:\d{2}[.,]\d+|\d{1,2}:\d{2}[.,]\d+)\s*-->\s*(\d+:\d{2}:\d{2}[.,]\d+|\d{1,2}:\d{2}[.,]\d+)")
    for b in blocks:
        lines = b.split("\n")
        for k, ln in enumerate(lines):
            m = pat.search(ln)
            if m:
                body = "\n".join(lines[k + 1:])
                cues.append({"start": tc_to_sec(m.group(1)), "end": tc_to_sec(m.group(2)), "text": body})
                break
    return cues


def parse_json(text):
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("segments") or data.get("cues") or data.get("transcript") or []
    cues = []
    for row in data:
        s = row.get("start", row.get("start_time"))
        e = row.get("end", row.get("end_time"))
        t = row.get("text", "")
        if s is None or e is None:
            continue
        s = tc_to_sec(s) if isinstance(s, str) else float(s)
        e = tc_to_sec(e) if isinstance(e, str) else float(e)
        cues.append({"start": s, "end": e, "text": t})
    return cues


BRACKET_HEAD = re.compile(
    r"^\s*\[\s*(\d{1,2}:\d{2}(?::\d{2})?[.,]\d+|\d{1,2}:\d{2}(?::\d{2})?)\s*-{1,3}>\s*"
    r"(\d{1,2}:\d{2}(?::\d{2})?[.,]\d+|\d{1,2}:\d{2}(?::\d{2})?)\s*\]")
BRACKET_SECONDS = re.compile(r"^\s*\(\s*[\d.]+\s*-\s*[\d.]+\s*\)")
BRACKET_NOTE = re.compile(r"\s*<<<.*$")


def parse_bracket(text):
    """whisper.cpp's own console format, and the reading copy transcribe.py writes.

        [00:01:24.640 --> 00:01:26.520]   text on the same line
        [01:24.64 -> 01:26.52] (84.64-86.52)   <<< GAP 14.6s
        text on the next line

    One line or two, with or without the absolute-seconds note and the gap marker.
    """
    cues = []
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        m = BRACKET_HEAD.match(raw_line)
        if m:
            rest = raw_line[m.end():]
            rest = BRACKET_SECONDS.sub("", rest)
            rest = BRACKET_NOTE.sub("", rest).strip()
            cues.append({"start": tc_to_sec(m.group(1)), "end": tc_to_sec(m.group(2)),
                         "text": rest})
        elif cues and raw_line.strip():
            # a body line belonging to the cue above it
            cues[-1]["text"] = (cues[-1]["text"] + " " + raw_line.strip()).strip()
    return cues


def load_cues(path):
    raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8-sig").read()
    stripped = raw.lstrip()
    if not stripped:
        sys.exit("pick_pulls: the transcript file is empty.")
    # Note: "" in "[{" is True in Python, so the emptiness check must come
    # first or an empty file takes the JSON branch and dies in the decoder.
    # The bracket check has to come before the JSON one: a JSON array also
    # opens with "[", so the two are told apart by what follows it.
    if BRACKET_HEAD.match(stripped):
        cues = parse_bracket(raw)
    else:
        cues = parse_json(raw) if stripped[0] in "[{" else parse_srt(raw)
    cues = [c for c in cues if c["end"] > c["start"]]
    cues.sort(key=lambda c: c["start"])
    if not cues:
        sys.exit("pick_pulls: no cues found. Expected SRT, VTT or JSON [{start, end, text}].")
    return cues


# ---------------------------------------------------------------- words and sentences

def build_words(cues):
    """One record per word, with a time interpolated by character count inside its cue."""
    words = []
    for ci, c in enumerate(cues):
        text = clean_cue_text(c["text"])
        lines = [ln for ln in text.split("\n") if ln.strip()]
        toks, turn_marks = [], []
        for ln in lines:
            ln = ln.strip()
            m = SPEAKER_LABEL.match(ln)
            if m:
                ln = ln[m.end():].strip()
                turn_marks.append(len(toks))
            toks.extend(ln.split())
        if not toks:
            continue
        weights = [len(t) + 1 for t in toks]
        total = float(sum(weights))
        dur = c["end"] - c["start"]
        acc = 0.0
        for wi, (t, w) in enumerate(zip(toks, weights)):
            t0 = c["start"] + dur * acc / total
            acc += w
            t1 = c["start"] + dur * acc / total
            words.append({"t": t, "t0": t0, "t1": t1, "cue": ci, "cue_first": wi == 0,
                          "turn": wi in turn_marks})
    return words


def punctuation_ratio(words):
    if not words:
        return 0.0
    return sum(1 for w in words if TERMINAL.search(w["t"])) / len(words)


def is_terminal(word, nxt):
    t = word["t"]
    if not TERMINAL.search(t):
        return False
    if t.lower() in ABBREV:
        return False
    if re.search(r"[?!][\"')\]”’]*$", t):
        return True
    if nxt is None:
        return True
    return bool(re.match(r"[\"'“‘(\[]*[A-Z0-9]", nxt["t"]))


def split_sentences(words, punct_mode):
    """Cut the word stream into sentences. Returns sentence dicts with word index ranges."""
    n = len(words)
    cuts = []  # (index of last word in sentence, why)
    for i, w in enumerate(words):
        nxt = words[i + 1] if i + 1 < n else None
        if nxt is None:
            cuts.append((i, "end"))
            continue
        gap = nxt["t0"] - w["t1"] if nxt["cue"] != w["cue"] else 0.0
        if nxt["turn"]:
            cuts.append((i, "turn"))
        elif punct_mode and is_terminal(w, nxt):
            cuts.append((i, "punct"))
        elif nxt["cue"] != w["cue"] and gap >= (LONG_GAP_BREAK if punct_mode else 0.6):
            cuts.append((i, "pause"))
    sents, lo = [], 0
    for hi, why in cuts:
        seg = words[lo:hi + 1]
        text = " ".join(x["t"] for x in seg)
        has_punct = bool(TERMINAL.search(seg[-1]["t"]))
        sents.append({
            "lo": lo, "hi": hi, "text": text,
            "start": seg[0]["t0"], "end": seg[-1]["t1"],
            "clean_end": has_punct or why in ("turn", "end") or (not punct_mode and why == "pause"),
            "start_estimated": not seg[0]["cue_first"],
        })
        lo = hi + 1
    for k, s in enumerate(sents):
        if k == 0:
            s["start_boundary"] = "file_start"
        else:
            p = sents[k - 1]
            prev_w, first_w = words[p["hi"]], words[s["lo"]]
            if TERMINAL.search(prev_w["t"]):
                s["start_boundary"] = "punctuation"
            elif first_w["turn"]:
                s["start_boundary"] = "speaker_turn"
            else:
                s["start_boundary"] = "pause"
    return sents


# ---------------------------------------------------------------- per-sentence features

def analyse_sentence(s):
    text = s["text"]
    low = text.lower()
    toks = re.findall(r"[A-Za-z0-9'’\-\.,$%]+", text)
    s["n_words"] = len(text.split())
    s["is_question"] = text.rstrip("\"')”’ ").endswith("?") and s["n_words"] >= 4
    nums = []
    for tk in toks:
        bare = tk.strip(".,'’").lower()
        if re.search(r"\d", bare):
            nums.append(tk.strip(".,"))
            continue
        for part in bare.split("-"):
            if part in NUMWORDS:
                nums.append(bare)
                break
    s["numbers"] = nums
    names, prev_cap = [], False
    for k, tk in enumerate(text.split()):
        bare = tk.strip(".,?!;:\"'()“”‘’")
        cap = bool(bare) and bare[0].isupper() and bare not in NAME_STOP and not bare.isupper()
        cap = cap and k > 0 and len(bare) > 1
        if cap and not prev_cap:
            names.append(bare)
        elif cap and prev_cap and names:
            names[-1] += " " + bare
        prev_cap = cap
    s["names"] = names
    hits = []
    for rx, label in CONTRAST:
        if rx.search(low):
            hits.append(label)
    s["contrast"] = hits
    s["you"] = len(YOU.findall(low)) - 0
    s["filler"] = len(FILLER.findall(low))
    s["is_ack"] = bool(ACK_SENTENCE.match(low.strip())) or (s["n_words"] <= 2 and not s["is_question"])
    if s["is_ack"]:
        s["filler"] += 1
    s["exclaims"] = text.count("!")
    s["promo"] = bool(PROMO.search(low))
    # "So what was the moment you knew?" is a fine opener. "So I made one rule." is not.
    s["bad_opener"] = (bool(OPENER_BAD.match(text)) and not s["is_question"]) or s["is_ack"]
    # a sentence that carries nothing: no specifics, no contrast, no address, no question
    s["dead"] = s["is_ack"] or s["filler"] > 0 or s["promo"] or (
        s["n_words"] <= 4 and not (s["numbers"] or s["names"] or s["contrast"] or s["you"] or s["is_question"]
                                   or CLOSE_STRONG.search(low)))
    return s


def timecode(sec):
    m, s = divmod(sec, 60)
    h, m = divmod(int(m), 60)
    return f"{h:d}:{m:02d}:{s:04.1f}" if h else f"{m:02d}:{s:04.1f}"


def snip(t, n=60):
    t = t.strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + "..."


# ---------------------------------------------------------------- scoring

def score_window(sents, i, j):
    """Score sentences i..j inclusive. Returns (score, reasons list, flags dict)."""
    W = sents[i:j + 1]
    t0, t1 = W[0]["start"], W[-1]["end"]
    dur = t1 - t0
    nwords = sum(s["n_words"] for s in W)
    reasons = []

    def add(signal, pts, evidence):
        if pts:
            reasons.append({"signal": signal, "points": round(pts, 1), "evidence": evidence})

    first, last = W[0], W[-1]

    # 1 hook
    hp, hev = 0.0, []
    if first["is_question"]:
        hp += 8; hev.append("opens on a question")
    if first["numbers"]:
        hp += 4; hev.append("number in the opener (%s)" % first["numbers"][0])
    if first["you"]:
        hp += 3; hev.append("addresses the viewer")
    if first["contrast"]:
        hp += 3; hev.append("contrast in the opener")
    if first["n_words"] <= 16 and hp:
        hp += 3; hev.append("short, %d words" % first["n_words"])
    add("hook", min(15.0, hp), "; ".join(hev))

    # 2 question then answer
    qpos = None
    for k, s in enumerate(W):
        if s["is_question"] and k < len(W) - 2:
            # the answer must be substance: within the next 4 sentences, at least 20 words from
            # non-question sentences, with at most one filler token among them
            nxt = [x for x in W[k + 1:k + 5] if not x["is_question"]]
            if sum(x["n_words"] for x in nxt) >= 20 and sum(x["filler"] for x in nxt) <= 1 \
                    and not s["promo"]:
                qpos = k
                break
    if qpos is not None:
        early = qpos <= max(1, len(W) // 3)
        add("question_then_answer", 14.0 if early else 8.0,
            'asks "%s" and answers it inside the clip' % snip(W[qpos]["text"], 50))

    # 3 concrete numbers and names
    nums = [x for s in W for x in s["numbers"]]
    names = [x for s in W for x in s["names"]]
    cp = min(16.0, 3.0 * len(nums) + 1.5 * len(names))
    if cp:
        ev = []
        if nums:
            ev.append("%d number(s): %s" % (len(nums), ", ".join(nums[:4])))
        if names:
            ev.append("%d name(s): %s" % (len(names), ", ".join(names[:4])))
        add("concrete_specifics", cp, "; ".join(ev))

    # 4 contrast or reversal, and where it lands
    hits = []
    for k, s in enumerate(W):
        for h in s["contrast"]:
            frac = ((s["start"] - t0) / dur) if dur else 0
            hits.append((h, frac))
    if hits:
        p = 5.0 + 3.0 * (min(len(hits), 4) - 1)
        late = [h for h in hits if h[1] >= 0.4]
        if late:
            p += 3.0
        labels = []
        for h, _ in hits:
            if h not in labels:
                labels.append(h)
        ev = "%d marker(s): %s" % (len(hits), ", ".join('"%s"' % l for l in labels[:4]))
        if late:
            ev += "; one lands %d%% of the way in, where the turn belongs" % round(100 * late[0][1])
        add("contrast_or_reversal", min(16.0, p), ev)

    # 5 direct address
    you = sum(s["you"] for s in W) - len(YOU_KNOW.findall(" ".join(s["text"].lower() for s in W)))
    rate = 100.0 * max(you, 0) / max(nwords, 1)
    add("direct_address", min(8.0, rate * 0.8),
        "%d you/your in %d words (%.1f per 100)" % (max(you, 0), nwords, rate))

    # 6 closing line
    cl, cev = 0.0, []
    llow = last["text"].lower()
    if CLOSE_WEAK.search(llow):
        cl -= 10.0; cev.append('weak close: "%s"' % snip(last["text"], 45))
    else:
        if last["n_words"] <= 14:
            cl += 4; cev.append("short closing line, %d words" % last["n_words"])
        if last["n_words"] <= 8:
            cl += 3
        if CLOSE_STRONG.search(llow):
            cl += 4; cev.append("states a conclusion")
        if last["is_question"]:
            cl += 2; cev.append("closes on a question")
        if last["n_words"] > 30:
            cl -= 3; cev.append("long rambling close")
    if cl:
        add("closing_line", max(min(cl, 14.0), -10.0), '%s ("%s")' % ("; ".join(cev), snip(last["text"], 45)))

    # 7 completeness and internal silence
    gaps = [W[k + 1]["start"] - W[k]["end"] for k in range(len(W) - 1)]
    big = [g for g in gaps if g > INNER_GAP_PENALTY]
    comp = 0.0
    cev = []
    if all(s["clean_end"] for s in W):
        comp += 5; cev.append("every sentence finishes")
    if not big:
        comp += 3; cev.append("no silence over %.1fs inside" % INNER_GAP_PENALTY)
    avg_len = nwords / len(W)
    if 6 <= avg_len <= 24:
        comp += 2; cev.append("sentences average %.0f words" % avg_len)
    add("completeness", comp, "; ".join(cev))
    if big:
        add("internal_silence", -4.0 * len(big), "%d gap(s) over %.1fs, longest %.1fs, may be two thoughts"
            % (len(big), INNER_GAP_PENALTY, max(big)))

    # 8 energy proxies
    ep, eev = 0.0, []
    prev_gap = None
    if i > 0:
        prev_gap = first["start"] - sents[i - 1]["end"]
        if prev_gap >= 1.5:
            ep += 6; eev.append("%.1fs of silence before the opener" % prev_gap)
        elif prev_gap >= 0.8:
            ep += 4; eev.append("%.1fs pause before the opener" % prev_gap)
    shifts = sum(1 for k in range(1, len(W)) if W[k]["n_words"] <= 6 and W[k - 1]["n_words"] >= 15)
    if shifts:
        ep += min(3.0, 1.5 * shifts); eev.append("%d short line(s) after a long one" % shifts)
    ex = sum(s["exclaims"] for s in W)
    if ex:
        ep += min(2.0, float(ex)); eev.append("%d exclamation mark(s)" % ex)
    add("energy_proxy", min(8.0, ep), "; ".join(eev) + " (text proxy only, confirm in the waveform)")

    # 8b does the thought actually stop here? Silence after the last sentence is the proxy.
    if j + 1 < len(sents):
        nx = sents[j + 1]
        gap_after = nx["start"] - last["end"]
        if gap_after >= 1.0:
            add("clean_exit", 5.0, "%.1fs of silence after the last line, the speaker stopped" % gap_after)
        elif gap_after >= 0.6:
            add("clean_exit", 2.0, "%.1fs pause after the last line" % gap_after)
        elif gap_after < 0.3 and nx["n_words"] <= 12 and not nx["dead"]:
            add("clean_exit", -5.0, 'the next line follows with no pause ("%s"), the thought may not be finished'
                % snip(nx["text"], 40))

    # 9 filler
    fill = sum(s["filler"] for s in W)
    frate = 100.0 * fill / max(nwords, 1)
    if fill:
        add("filler", -min(25.0, 2.0 * frate), "%d filler token(s), %.1f per 100 words" % (fill, frate))

    # 9b dead weight at the edges, and promo or housekeeping anywhere
    dead_lead = sum(1 for x in W[:3] if x["dead"])
    dead_tail = sum(1 for x in W[-2:] if x["dead"])
    if dead_lead or dead_tail:
        add("dead_weight_at_edges", -3.0 * (dead_lead + dead_tail),
            "%d of the first 3 and %d of the last 2 sentences carry nothing (acknowledgement, filler, promo or "
            "small talk), so the cut could start later or end earlier" % (dead_lead, dead_tail))
    promo = [x for x in W if x["promo"]]
    if promo:
        add("promo_or_housekeeping", -min(20.0, 10.0 * len(promo)),
            'sponsor, review or sign-off language: "%s"' % snip(promo[0]["text"], 50))

    # 10 duration shape
    if SWEET_LO <= dur <= SWEET_HI:
        add("duration", 4.0, "%.0fs, inside the 45 to 60 second sweet spot" % dur)
    else:
        add("duration", 2.0, "%.0fs, inside the allowed 35 to 75" % dur)

    score = sum(r["points"] for r in reasons)
    return score, reasons, {"duration": dur, "prev_gap": prev_gap, "words": nwords}


def candidate_windows(sents, lo_d, hi_d):
    """Best end for every legal start. Starts are sentence starts only."""
    out = []
    for i, si in enumerate(sents):
        if si["bad_opener"] and i > 0:
            continue
        best = None
        for j in range(i, len(sents)):
            dur = sents[j]["end"] - si["start"]
            if j > i and sents[j]["start"] - sents[j - 1]["end"] > INNER_GAP_REJECT:
                break
            if dur > hi_d:
                break
            if dur < lo_d or not sents[j]["clean_end"]:
                continue
            sc, why, meta = score_window(sents, i, j)
            cand = (sc, -dur, i, j, why, meta)
            if best is None or cand[:2] > best[:2]:
                best = cand
        if best:
            out.append(best)
    return out


# ---------------------------------------------------------------- independent start check

def starts_clean(words, sent):
    """Second test, on raw words, not on the sentence list that built the window."""
    lo = sent["lo"]
    if lo == 0:
        return True, "first word of the file"
    prev, cur = words[lo - 1], words[lo]
    if TERMINAL.search(prev["t"]) and prev["t"].lower() not in ABBREV:
        return True, 'previous word "%s" ends a sentence' % prev["t"]
    if cur["turn"]:
        return True, "speaker turn"
    gap = cur["t0"] - prev["t1"]
    if cur["cue"] != prev["cue"] and gap >= 0.6:
        return True, "%.1fs pause before it" % gap
    return False, 'previous word "%s" does not end a sentence' % prev["t"]


# ---------------------------------------------------------------- selection

def percentile(sorted_vals, v):
    if not sorted_vals:
        return None
    return round(100.0 * sum(1 for x in sorted_vals if x <= v) / len(sorted_vals))


def pick(sents, words, n, lo_d, hi_d, overlap, lead_in):
    cands = candidate_windows(sents, lo_d, hi_d)
    all_scores = sorted(c[0] for c in cands)
    cands.sort(key=lambda c: (-c[0], -c[1]))
    chosen, warnings = [], []
    for sc, negdur, i, j, why, meta in cands:
        if len(chosen) >= n:
            break
        ws, we = sents[i]["start"], sents[j]["end"]
        if any(min(we, c["end"]) - max(ws, c["start"]) > overlap for c in chosen):
            continue
        core_i = i
        lead_note = None
        # lead-in only when the opener leans on something said before it ("It was...", "That is why...").
        # An opener that is a question or carries its own hook starts a thought by itself.
        if lead_in and i > 0 and ANAPHOR.match(sents[i]["text"]) and not sents[i]["is_question"]:
            p = sents[i - 1]
            gap = sents[i]["start"] - p["end"]
            plen = p["end"] - p["start"]
            fits = (we - p["start"]) <= hi_d
            clear = not any(min(we, c["end"]) - max(p["start"], c["start"]) > overlap for c in chosen)
            if gap < LEAD_IN_MAX_GAP and plen <= LEAD_IN_MAX_LEN and p["clean_end"] and fits and clear \
                    and not p["is_ack"] and p["filler"] == 0 and not p["promo"] \
                    and not p["bad_opener"]:
                i = i - 1
                ws = sents[i]["start"]
                lead_note = "added the sentence before (%.1fs of pause), per 'start one sentence earlier'" % gap
        first = sents[i]
        ok, how = starts_clean(words, first)
        if not ok:
            warnings.append("dropped a window at %s: %s" % (timecode(first["start"]), how))
            continue
        text = " ".join(s["text"] for s in sents[i:j + 1])
        reasons = sorted(why, key=lambda r: -abs(r["points"]))
        pos = [r for r in reasons if r["points"] > 0]
        neg = [r for r in reasons if r["points"] < 0]
        why_text = "; ".join("%s (%+.0f): %s" % (r["signal"], r["points"], r["evidence"]) for r in pos[:4])
        if neg:
            why_text += ". Against: " + "; ".join("%s (%+.0f): %s" % (r["signal"], r["points"], r["evidence"])
                                                  for r in neg)
        item = {
            "start": round(ws, 2),
            "end": round(we, 2),
            "duration": round(we - ws, 2),
            "start_tc": timecode(ws),
            "end_tc": timecode(we),
            "opening_sentence": first["text"],
            "text": text,
            "score": round(sc, 1),
            "strength": "strong" if sc >= 50 else "usable" if sc >= 35 else "weak",
            "score_percentile_in_file": percentile(all_scores, sc),
            "why_text": why_text,
            "why": reasons,
            "start_boundary": first["start_boundary"],
            "start_check": how,
            "start_estimated": first["start_estimated"],
            "core_start": round(sents[core_i]["start"], 2),
            "sentences": j - i + 1,
        }
        if lead_note:
            item["lead_in"] = lead_note
        if i > 0:
            pv = sents[i - 1]
            item["sentence_before"] = {"text": pv["text"], "gap_seconds": round(first["start"] - pv["end"], 2),
                                       "note": "if the opening feels abrupt in the audio, start here instead"}
        chosen.append({"start": ws, "end": we, "item": item})
    for rank, c in enumerate(chosen, 1):
        c["item"] = {"rank": rank, **c["item"]}
    return [c["item"] for c in chosen], warnings, len(cands)


def main():
    ap = argparse.ArgumentParser(description="Pick 35 to 75 second short-form pulls from a transcript.")
    ap.add_argument("transcript", help="SRT, VTT, JSON or bracket-format file, or - for stdin")
    ap.add_argument("-n", type=int, default=5, help="how many pulls to return (default 5)")
    ap.add_argument("--min", type=float, default=MIN_DUR, dest="lo", help="minimum seconds (default 35)")
    ap.add_argument("--max", type=float, default=MAX_DUR, dest="hi", help="maximum seconds (default 75)")
    ap.add_argument("--overlap", type=float, default=0.0, help="seconds two pulls may overlap (default 0)")
    ap.add_argument("--lead-in", type=int, choices=[0, 1], default=1,
                    help="1 (default) adds the previous sentence when it was said without a pause")
    ap.add_argument("--out", help="also write the JSON here")
    a = ap.parse_args()

    cues = load_cues(a.transcript)
    words = build_words(cues)
    ratio = punctuation_ratio(words)
    punct_mode = ratio >= WEAK_PUNCT_RATIO
    sents = [analyse_sentence(s) for s in split_sentences(words, punct_mode)]

    caveats = [
        "Text cannot measure energy. Energy proxies here are silence before the opener, sentence rhythm and "
        "exclamation marks. Open the waveform at each start and confirm a loud bit after a pause.",
        "Scores compare windows inside this one file only. They are not calibrated against views or retention.",
        "Where a sentence starts inside an SRT cue the time is interpolated, up to about a second off "
        "(see start_estimated).",
    ]
    if not punct_mode:
        caveats.insert(0, "This transcript has almost no sentence punctuation (%.1f terminal marks per 100 words). "
                          "Sentence boundaries were guessed from pauses, so starts and ends are less reliable."
                       % (100 * ratio))

    pulls, warnings, n_cand = pick(sents, words, a.n, a.lo, a.hi, a.overlap, bool(a.lead_in))
    weak = [p for p in pulls if p["strength"] == "weak"]
    if weak:
        warnings.append("%d of %d pulls are labelled weak (score under 35). They are only here because -n asked "
                        "for %d. Do not cut them unless nothing else exists. The strong/usable thresholds are "
                        "hand-set on one fixture, not calibrated." % (len(weak), len(pulls), a.n))
    if not pulls:
        warnings.append("No window of %g to %g seconds survived. The transcript may be shorter than the minimum, "
                        "or have a silence over %.0fs in every stretch." % (a.lo, a.hi, INNER_GAP_REJECT))
    result = {
        "source": a.transcript,
        "caveats": caveats,
        "warnings": warnings,
        "stats": {
            "cues": len(cues),
            "words": len(words),
            "sentences": len(sents),
            "transcript_seconds": round(cues[-1]["end"] - cues[0]["start"], 1),
            "punctuation_mode": "punctuation" if punct_mode else "pause_fallback",
            "candidate_windows_scored": n_cand,
            "median_sentence_words": statistics.median([s["n_words"] for s in sents]) if sents else 0,
        },
        "pulls": pulls,
    }
    out = json.dumps(result, indent=2, ensure_ascii=False)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(out + "\n")
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # Windows consoles default to a narrow code page
    except Exception:                               # noqa: BLE001
        pass
    print(out)


if __name__ == "__main__":
    main()
