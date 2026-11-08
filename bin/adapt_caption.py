#!/usr/bin/env python3
"""adapt_caption.py: one caption in, one shaped caption per place it lands.

WHY THIS EXISTS. `schedule_post.py` takes a single --caption file and sends the
identical text to every network in the post. So the same words go to Instagram,
where a link does nothing and ten tags are normal, and to Pinterest, which reads
the description as search text and does not care about tags at all, and to
Threads, which cuts at 500 characters. One of those places gets a caption that
fits and the rest get a hand-me-down.

WHAT IT DOES AND DOES NOT DO, which is the important part.

  It CUTS, REORDERS, and MOVES. It trims to the limit at a sentence boundary, it
  drops hashtags past the count a network rewards, it turns a URL into "link in
  bio" where links are dead, it lifts the first real sentence out from behind a
  tag block so the fold shows words.

  It NEVER WRITES A NEW SENTENCE. Every word it emits was in the caption you
  gave it. That is the same rule `draft_content.py` works under: "Every line is
  a sentence they already said. Nothing here was written for them." A tool that
  quietly rewrites a person's words in their own voice is a tool they cannot
  check, so this one does not.

  It CANNOT KNOW whether any of this performs better. The rules file holds
  platform limits and conventions, which are facts about the product, and says
  nothing about what wins. When you have your own posted numbers per network,
  `own_results.py` is the thing that measures that, and these rules should then
  be corrected against it rather than trusted.

Usage:
    python3 bin/adapt_caption.py caption.txt --networks instagram,threads,pinterest
    python3 bin/adapt_caption.py caption.txt --networks instagram,tiktok \
        --rules specs/platforms.json --out-dir out/captions
    python3 bin/adapt_caption.py caption.txt --networks threads --show

Writes one .txt per network, ready to hand straight to schedule_post.py, and
prints what it changed for each one so nothing happens silently.

Standard library only. No network call, no credential.
"""
import argparse
import json
import re
import sys
from pathlib import Path

HASHTAG = re.compile(r"#\w+")
URL = re.compile(r"https?://\S+")
MENTION = re.compile(r"@[\w.]+")
# Where a sentence may end. Splitting naively on a full stop destroys real
# captions: "tr. W. W. Westcott 1887" became five paragraphs the first time this
# ran. So a stop only counts when the word before it is more than one letter and
# is not a known abbreviation, and a line break always counts.
ABBREV = {"tr", "ed", "vol", "no", "pp", "p", "st", "mr", "mrs", "ms", "dr",
          "prof", "etc", "eg", "ie", "vs", "jr", "sr", "approx", "inc", "ltd",
          "co", "fig", "al", "cf", "ca"}


def boundaries(text):
    """Offsets where the text may be cut without landing mid thought."""
    out = []
    for m in re.finditer(r"\n{2,}|\n|(?<=[.!?\u2026])(?=\s)", text):
        i = m.start()
        if m.group().startswith("\n"):
            out.append(i)
            continue
        # text[:i] ends AT the stop. Using i + 1 includes the following space, so the
        # pattern below never matched and every abbreviation was a legal cut point.
        # kit_check 6f is what caught that, by asking for the cuts rather than trusting
        # the code that makes them.
        word = re.search(r"([A-Za-z'\u2019]+)[.!?\u2026]$", text[:i])
        if word:
            w = word.group(1).lower()
            if len(w) == 1 or w in ABBREV:
                continue
        out.append(i)
    out.append(len(text))
    return sorted(set(out))

DEFAULTS = {"limit": 2200, "lead": 125, "max_hashtags": 5,
            "links": "inline", "mentions": "keep", "bio_phrase": "link in bio"}


def load_rules(path):
    if path:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    else:
        here = Path(__file__).resolve().parent.parent / "specs" / "platforms.example.json"
        if not here.exists():
            return {}, dict(DEFAULTS)
        data = json.loads(here.read_text(encoding="utf-8"))
    base = dict(DEFAULTS)
    base.update(data.get("defaults") or {})
    return data.get("networks") or {}, base


def rules_for(net, networks, base):
    r = dict(base)
    r.update(networks.get(net) or {})
    return r


def leading_tag_block(text):
    """The run of hashtags and handles the caption opens with, if any.

    Returns (block, rest). A caption that opens with a tag wall spends the whole
    visible fold on tags, so the block moves to the bottom. Nothing is rewritten:
    the same characters come out, in a different order.
    """
    m = re.match(r"^((?:[#@][\w.]+[ \t]*)+)(?:\n+|$)", text)
    if not m:
        return "", text
    return m.group(1).strip(), text[m.end():].lstrip()


def strip_tags(text, keep):
    """Drop hashtags past `keep`, earliest kept, and tidy the whitespace."""
    seen = 0
    out = []
    for tok in re.split(r"(\s+)", text):
        if HASHTAG.fullmatch(tok.strip()):
            seen += 1
            if seen > keep:
                continue
        out.append(tok)
    return re.sub(r"[ \t]{2,}", " ", "".join(out)).strip()


def handle_links(text, mode, bio_phrase):
    if mode == "inline":
        return text, 0
    found = URL.findall(text)
    if not found:
        return text, 0
    if mode == "strip":
        return re.sub(r"\s*" + URL.pattern + r"\s*", " ", text).strip(), len(found)
    # "bio": the URL is dead where it is, so say where it lives instead. The
    # phrase is from the rules file, which means it is the owner's words.
    out = URL.sub(bio_phrase, text, count=1)
    out = URL.sub("", out)
    return re.sub(r"[ \t]{2,}", " ", out).strip(), len(found)


def opens_with_words(text):
    """Does the caption start with words rather than with a tag wall?"""
    head = text.lstrip()
    return bool(head) and not re.match(r"^[#@][\w.]+", head)


def trim(text, limit):
    """Cut to the limit at a real boundary, keeping the original formatting.

    The old version rebuilt the text by joining sentences with blank lines,
    which reflowed captions that were never too long in the first place. This
    slices the original instead, so what comes back is a prefix of what went in.
    """
    if len(text) <= limit:
        return text, False
    fits = [b for b in boundaries(text) if b <= limit]
    if not fits or max(fits) == 0:
        cut = text[:limit].rsplit(" ", 1)[0]
        return cut.rstrip(" ,;:"), True
    return text[:max(fits)].rstrip(), True


def adapt(text, r):
    notes = []
    out = text.strip()

    if r.get("mentions") == "strip":
        n = len(MENTION.findall(out))
        if n:
            out = re.sub(r"\s*" + MENTION.pattern + r"\s*", " ", out).strip()
            notes.append("removed %d handle(s), they do nothing here" % n)

    keep_tags = int(r.get("max_hashtags", 5))
    before = len(HASHTAG.findall(out))
    if before > keep_tags:
        out = strip_tags(out, keep_tags)
        notes.append("cut hashtags from %d to %d" % (before, keep_tags))

    out, moved_links = handle_links(out, r.get("links", "inline"), r.get("bio_phrase", DEFAULTS["bio_phrase"]))
    if moved_links and r.get("links") == "bio":
        notes.append("link is not clickable here, so it reads '%s'" % r.get("bio_phrase", DEFAULTS["bio_phrase"]))
    elif moved_links and r.get("links") == "strip":
        notes.append("removed %d link(s)" % moved_links)

    if not opens_with_words(out):
        block, rest = leading_tag_block(out)
        if block and rest:
            out = rest.rstrip() + "\n\n" + block
            notes.append("moved the opening tags to the bottom so the fold shows words")
        else:
            notes.append("WARNING: this caption opens with tags and has nothing else to lead with")

    limit = int(r.get("limit", 2200))
    links_before = len(URL.findall(out))
    out, cut = trim(out, limit)
    if cut:
        notes.append("trimmed to %d characters at a sentence end" % limit)
        if links_before and not URL.findall(out) and r.get("links") == "inline":
            notes.append("WARNING: the trim cut the link off. Shorten the caption or put the "
                         "link earlier.")

    # Say what actually came out. The trim runs last and can take the tags the
    # step above just decided to keep, and a note that stops at the intention
    # rather than the result is how a report starts lying.
    final_tags = len(HASHTAG.findall(out))
    intended = min(before, keep_tags)
    if intended and final_tags < intended:
        notes.append("the trim then took %d of those, so %d tag(s) actually go out"
                     % (intended - final_tags, final_tags))

    if not notes:
        notes.append("fits as written, nothing changed")
    return out.strip(), notes


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("caption", help="a text file holding the caption")
    ap.add_argument("--networks", required=True, help="comma separated, e.g. instagram,threads")
    ap.add_argument("--rules", help="a platforms.json. Defaults to the example in specs/")
    ap.add_argument("--out-dir", dest="out_dir", help="where the per network files go")
    ap.add_argument("--show", action="store_true", help="print the captions instead of writing them")
    a = ap.parse_args()

    text = Path(a.caption).read_text(encoding="utf-8").strip()
    if not text:
        sys.exit("that caption file is empty")
    networks, base = load_rules(a.rules)
    nets = [n.strip().lower() for n in a.networks.split(",") if n.strip()]
    if not nets:
        sys.exit("no networks given")

    unknown = [n for n in nets if n not in networks]
    if unknown:
        print("  no rules for %s, so the defaults are used for %s"
              % (", ".join(unknown), "it" if len(unknown) == 1 else "them"))

    print("  source caption: %d characters, %d hashtag(s), %d link(s)"
          % (len(text), len(HASHTAG.findall(text)), len(URL.findall(text))))
    print("  platform limits come from a file and platforms change them. Check anything")
    print("    marked verify before trusting it.")
    print()

    out_dir = Path(a.out_dir) if a.out_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    for net in nets:
        r = rules_for(net, networks, base)
        body, notes = adapt(text, r)
        print("  %s  %d characters" % (net.upper(), len(body)))
        for n in notes:
            print("     - %s" % n)
        if r.get("confidence", "").lower().startswith("verify"):
            print("     - these rules are marked VERIFY in the rules file")
        if a.show or not out_dir:
            print()
            for line in body.splitlines():
                print("     | %s" % line)
        else:
            p = out_dir / ("caption-%s.txt" % net)
            p.write_text(body + "\n", encoding="utf-8")
            print("     wrote %s" % p)
            print("     schedule it: python3 bin/schedule_post.py MEDIA --caption %s --networks %s"
                  % (p, net))
        print()


if __name__ == "__main__":
    main()
