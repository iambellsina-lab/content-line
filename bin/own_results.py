#!/usr/bin/env python3
"""own_results.py: turn YOUR OWN posted results into something the calibrator can read.

WHY THIS EXISTS. `yt_probe.py` measures what wins in a niche by reading other
people's public view counts. `niche_calibrate.py` turns that into a profile the
clipper executes. Between them the line is calibrated entirely on strangers: a
clip of yours that doubled your usual saves changes nothing about what gets cut
next week, because nothing carries that fact back. This is the return wire.

It writes the same block shape `niche_calibrate.py` already reads, so the two
need no changes to talk:

    [{"query": "...", "results": [{"title": ..., "views": ..., ...}, ...]}]

WHAT IT CAN AND CANNOT KNOW, which matters more here than usual.

  It CAN know, because these are your own posts and the platform reports them:
  views, shares, saves, interactions, and the three second view rate, which is
  the closest measurement anyone has to "did the hook hold".

  It CANNOT know whether the caption is the hook. On a reel the spoken or
  on-screen opening is the hook, and the caption is a separate piece of writing
  underneath it. So what this calibrates today is CAPTION shape against
  performance. That is a real signal and it is not the same signal as the one
  `hook_curate.py` picks. The honest join is engine-made clips: when a post was
  produced by `run_line.py`, its chosen hook is in that run's `run.json` and can
  be matched to this post by id. Until posts come out of the line, pass
  --source caption and read the result as being about captions.

Usage:
    # 1. a session fetches the numbers (Metricool analytics, any brand)
    # 2. save that response as JSON, then:
    python3 bin/own_results.py rows.json \
        --metrics IGRE01,IGRE03,IGRE23,IGRE21,IGRE12,IGRE26,IGRE27,IGRE28,IGRE09 \
        --label "my reels" --format short \
        --out research/own-reels.json

    python3 bin/own_results.py rows.json --metrics ... --label ... --print

The --metrics list must be the field ids IN THE ORDER THEY WERE REQUESTED,
because the response is positional rows with no column names of its own.

Standard library only. Makes no network call and holds no credential: fetching
is the caller's job, which keeps the secret out of this file and out of the kit.
"""
import argparse
import json
import re
import sys
from pathlib import Path

# Metricool field ids are network + connector + index. Only the meaning matters
# here, so the map is by the trailing role rather than by network: IGRE03 and
# IGPO03 are both the post's text, TTPO-style ids follow the same shape.
ROLE = {
    "01": "date", "02": "date", "03": "title", "04": "id", "06": "url",
    "07": "type",
}
# The ones that differ per connector, by full id.
EXPLICIT = {
    "IGRE23": "views", "IGRE21": "shares", "IGRE12": "saved",
    "IGRE26": "duration_s", "IGRE27": "retention", "IGRE28": "view_rate",
    "IGRE09": "interactions", "IGRE11": "reach", "IGRE10": "likes",
    "IGPO28": "views", "IGPO27": "shares", "IGPO15": "saved",
    "IGPO12": "interactions", "IGPO14": "reach", "IGPO13": "likes",
    "IGPO29": "follows", "IGPO07": "type", "IGPO03": "title", "IGPO01": "date",
}


def role_of(field_id):
    fid = field_id.strip().upper()
    if fid in EXPLICIT:
        return EXPLICIT[fid]
    return ROLE.get(fid[-2:], fid.lower())


def num(v):
    """Metricool sends numbers as strings, and absent as null."""
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f == int(f) else f


def has_sentence(title):
    """Does this caption contain words, or is it only emoji and hashtags?

    A caption of "🤡" carries no shape to learn from. Counting these is the
    difference between an honest sample size and a flattering one.
    """
    words = re.findall(r"[A-Za-z']{2,}", re.sub(r"#\w+", " ", title or ""))
    return len(words) >= 3


def convert(payload, metrics, label, fmt, source, rank_by="views"):
    cols = [role_of(m) for m in metrics]
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        sys.exit("that file has no 'rows' list in it")

    results, skipped = [], 0
    for raw in rows:
        rec = dict(zip(cols, raw))
        title = (rec.get("title") or "").strip()
        views = num(rec.get("views"))
        if views is None or not title:
            skipped += 1
            continue
        rank_val = views
        if rank_by != "views":
            rv = num(rec.get(rank_by))
            if rv is None:
                skipped += 1
                continue
            rank_val = rv
        out = {
            # The calibrator ranks on "views" and nothing else, so whatever you
            # chose to rank by goes in that slot and the true reach is kept
            # beside it under views_actual. Ranking on view_rate asks "what held
            # them", ranking on views asks "what reached them". Those are
            # different questions and the hook only controls the first.
            "title": title,
            "views": rank_val,
            "views_actual": views,
            "ranked_by": rank_by,
            "id": rec.get("id") or rec.get("url") or "%s::%s" % (rec.get("date"), title[:40]),
            "format": fmt,
            "mine": True,
            "hook_source": source,
            "has_sentence": has_sentence(title),
        }
        for k in ("date", "shares", "saved", "interactions", "reach",
                  "likes", "follows", "retention", "view_rate", "duration_s"):
            if k in rec:
                v = rec[k] if k == "date" else num(rec[k])
                if v is not None:
                    out[k] = v
        results.append(out)
    return [{"query": label, "results": results}], skipped


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rows", help="JSON file holding the analytics response")
    ap.add_argument("--metrics", required=True,
                    help="field ids in the order they were requested, comma separated")
    ap.add_argument("--label", required=True, help="what this set is, e.g. 'my reels'")
    ap.add_argument("--format", default="short", dest="fmt",
                    help="'short' for reels, tiktok and shorts; anything else for feed")
    ap.add_argument("--source", default="caption", choices=["caption", "engine-hook"],
                    help="what the title field actually holds. Default caption.")
    ap.add_argument("--rank-by", default="views", dest="rank_by",
                    choices=["views", "view_rate", "shares", "saved", "interactions"],
                    help="which number decides a winner. views is reach, view_rate is "
                         "the three second hold and is the one a hook actually controls.")
    ap.add_argument("--out", help="where to write it")
    ap.add_argument("--print", action="store_true", dest="show",
                    help="print the JSON instead of writing it")
    a = ap.parse_args()

    payload = json.loads(Path(a.rows).read_text())
    metrics = [m for m in a.metrics.split(",") if m.strip()]
    blocks, skipped = convert(payload, metrics, a.label, a.fmt, a.source, a.rank_by)
    rs = blocks[0]["results"]

    if not rs:
        sys.exit("nothing usable: every row was missing a title or a view count")

    views = sorted(r["views_actual"] for r in rs)
    sentences = sum(1 for r in rs if r["has_sentence"])
    rated = [r["view_rate"] for r in rs if r.get("view_rate") is not None]

    print("  %d posts kept, %d skipped for a missing title or view count" % (len(rs), skipped))
    print("  views: %d low, %d median, %d high" % (views[0], views[len(views) // 2], views[-1]))
    print("  %d of %d carry an actual sentence. The rest are emoji or tags and"
          % (sentences, len(rs)))
    print("    teach a caption shape nothing.")
    if rated:
        rated.sort()
        print("  three second view rate on %d of them: %.1f%% median" % (len(rated), rated[len(rated) // 2]))
    if a.rank_by != "views":
        print("  RANKED BY %s, so 'views' in the output file holds that number and the"
              % a.rank_by)
        print("    real reach is under views_actual.")
    if a.source == "caption":
        print("  NOTE: titles here are CAPTIONS, which are not the hook the viewer hears.")
    # niche_calibrate refuses to recommend below 25. Say so before it does.
    if len(rs) < 25:
        print("  SAMPLE IS THIN: %d is under the 25 the calibrator needs before it will"
              % len(rs))
        print("    recommend anything. It will report and withhold, which is correct.")

    text = json.dumps(blocks, indent=2, ensure_ascii=False)
    if a.show or not a.out:
        print()
        print(text)
    else:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(text + "\n")
        print("  wrote %s" % a.out)


if __name__ == "__main__":
    main()
