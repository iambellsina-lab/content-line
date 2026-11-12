#!/usr/bin/env python3
"""broll_reel.py: a voiceover cut list plus a labelled shelf becomes a reel of pure b-roll.

    python3 bin/broll_reel.py cuts.json --shelf specs/shelf.json --out specs/broll.json
    python3 bin/broll_reel.py cuts.json --shelf specs/shelf.json --piece A2
    python3 bin/broll_reel.py cuts.json --shelf specs/shelf.json --piece all
    python3 bin/broll_reel.py cuts.json --shelf specs/shelf.json --dry-run

    Then either renderer takes the spec this writes:
      python3 bin/broll.py out/clip.mp4 --spec specs/broll.json          (ffmpeg pass)
      to_hyperframes.py cuts.json --out DIR --broll specs/broll.json     (captions on top)

WHY THIS EXISTS. A b-roll reel is a voice track and a picture that comes off a shelf
instead of off a camera pointed at her. The kit already has every part of that: the
cutaway layer replaces the picture for its window, and in the HyperFrames path the
caption cards keep a CSS layer above it, so a full frame cutaway can never cover a
word. What was missing was the thing that decides WHICH clip goes WHERE. That is one
file, and this is it. Nothing else in the chain changes.

WHAT IT READS
    a cut list from bin/plan_clips.py, filled in by bin/cards_from_srt.py
    a shelf from bin/shelf_index.py, with the labels filled in by somebody who looked

WHAT IT WRITES
    a b-roll layer spec in the shape of specs/example-broll.json, times="edit",
    one "full" layer per beat, covering the whole piece from 0 to the end with no gap

THE WORDS DECIDE THE PICTURE, AND NOTHING HERE WRITES A WORD. A clip lands on a beat
because the beat's own spoken words match the keywords a person wrote on that clip.
There are no script templates in this file and no invented sentences, which is the
same contract draft_content.py, hook_curate.py and caption_repair.py hold: a kit that
puts sentences in somebody's mouth produces copy they cannot check.

A MATCH IS NOT A GUARANTEE, AND THE NOTES EXIST TO BE READ. A clip reaches a beat on
a word, and an ordinary word collides: a harbour shot will pair with "the shot I keep
coming back to" on the word "coming", which is right by these rules and wrong on
screen. Two things are done about it and neither is a fix. One keyword hit is needed
before a layer claims a match (a single word out of the label does not qualify, see
--min-score), and every layer carries matched_on naming the words it matched, so the
collision is visible at a glance in the spec. **Read the notes before you render.**

WHEN NOTHING MATCHES IT SAYS SO. A beat whose words hit no keyword on the shelf still
gets a picture, because a gap in the picture is a hole in the reel. It is marked
"_matched": false in the spec and counted in the report, so the fix is obvious: either
the shelf needs a clip for that idea, or that clip needs that keyword.

TIME BASIS, and getting this wrong is how a reel ends up a second out all the way
through. Cut list segments and cards are TAPE seconds. B-roll layers are FINISHED
seconds. The finished clock is the segment durations added up in list order, which is
exactly what to_hyperframes.py's build_segments does, because the renderer plays the
segments in list order rather than tape order. The hook adds no time: it is a pinned
overlay rather than a segment. bin/kit_check.py pins this mapping against a fixture.

Standard library only. It reads two JSON files and writes a third. It never touches
footage and it never encodes anything.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

EPS = 1e-6

# Beat shape. A cutaway that changes every second reads as a strobe, and one that
# sits for eight reads as a screensaver.
BEAT_TARGET = 3.0
BEAT_MAX = 5.0
BEAT_MIN = 1.2

# Silence longer than this inside one segment is a natural place to change picture.
GAP_BREAK = 0.6

# How long a frozen last frame may sit before a second clip is taken instead.
MAX_HOLD = 1.2
MAX_SPLITS = 3

# A keyword hit counts 2 and a word lifted out of the label counts 1, so the floor
# of 2.0 means one real keyword, or two words of the label. One ordinary label word on
# its own is a coincidence: it is how a shot of a harbour reaches "the shot I keep
# COMING back to", which is correct by the rules and wrong on screen.
MIN_SCORE = 2.0

STOP = set("""
a an and are as at be been but by can did do does for from had has have he her hers him his
how i if in into is it its me my not of on or our out she so than that the their them then there
these they this to too us was we were what when where which who why will with you your
just really very much more most some any all like got get go going am being does doesn
""".split())


def who() -> str:
    return Path(sys.argv[0]).stem or "broll_reel"


def die(msg: str) -> None:
    print("%s: %s" % (who(), msg), file=sys.stderr)
    sys.exit(1)


def read_json(path: Path, what: str) -> dict:
    if not path.is_file():
        die("%s is not a file (%s)" % (path, what))
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError as exc:
        die("%s is not valid JSON: %s" % (path, exc))
    return {}


def words_of(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z']{2,}", (text or "").lower()) if w not in STOP]


def matches(token: str, word: str) -> bool:
    """Loose enough for a plural, tight enough not to pair "sea" with "season"."""
    if token == word:
        return True
    if len(token) >= 4 and len(word) >= 4:
        return token.startswith(word[:4]) and (token.startswith(word) or word.startswith(token))
    return False


# ---------------------------------------------------------------------------
# the finished clock
# ---------------------------------------------------------------------------


def build_segments(piece: dict) -> tuple[list[dict], list[str]]:
    """Mirror of to_hyperframes.py build_segments. Nothing here sorts."""
    out: list[dict] = []
    problems: list[str] = []
    cursor = 0.0
    for i, seg in enumerate(piece.get("segments") or []):
        try:
            tape_in = float(seg["start"])
            tape_out = float(seg["end"])
        except (KeyError, TypeError, ValueError):
            problems.append("segment %d has no usable start/end" % (i + 1))
            continue
        dur = round(tape_out - tape_in, 6)
        if dur <= 0:
            problems.append("segment %d is %.3fs long" % (i + 1, dur))
            continue
        out.append({
            "index": len(out) + 1,
            "edit_start": round(cursor, 6),
            "edit_end": round(cursor + dur, 6),
            "tape_in": tape_in,
            "tape_out": tape_out,
            "role": seg.get("role"),
        })
        cursor += dur
    return out, problems


def map_cards(piece: dict, segments: list[dict], times: str) -> tuple[list[dict], int]:
    """Cards onto the finished clock. A card in no kept segment is dropped rather than
    slid onto the nearest one."""
    basis = (times or "source").strip().lower()
    mapped = basis not in ("edit", "finished", "clip")
    total = segments[-1]["edit_end"] if segments else 0.0
    placed: list[dict] = []
    dropped = 0
    last_index = -1
    for card in piece.get("cards") or []:
        try:
            c_in = float(card["start"])
            c_out = float(card["end"])
        except (KeyError, TypeError, ValueError):
            dropped += 1
            continue
        if c_out <= c_in:
            dropped += 1
            continue
        if not mapped:
            if c_in >= total - EPS:
                dropped += 1
                continue
            seg_index = None
            e_in, e_out = c_in, min(c_out, total)
        else:
            hits = [s for s in segments if s["tape_in"] - EPS <= c_in < s["tape_out"] - EPS]
            if not hits:
                dropped += 1
                continue
            forward = [s for s in hits if s["index"] >= last_index]
            seg = (forward or hits)[0]
            last_index = seg["index"]
            seg_index = seg["index"]
            e_in = seg["edit_start"] + (c_in - seg["tape_in"])
            e_out = min(seg["edit_start"] + (c_out - seg["tape_in"]), seg["edit_end"])
            if e_out <= e_in:
                dropped += 1
                continue
        placed.append({
            "text": (card.get("text") or "").strip(),
            "start": round(e_in, 6),
            "end": round(e_out, 6),
            "segment": seg_index,
        })
    placed.sort(key=lambda c: c["start"])
    return placed, dropped


# ---------------------------------------------------------------------------
# beats
# ---------------------------------------------------------------------------


def beats_from_cards(cards: list[dict], total: float, opts: dict) -> list[dict]:
    """Runs of cards, closed on length or on a silence. A cut always closes one."""
    beats: list[dict] = []
    run: list[dict] = []

    def close() -> None:
        if not run:
            return
        beats.append({
            "start": run[0]["start"],
            "end": run[-1]["end"],
            "text": " ".join(c["text"] for c in run if c["text"]).strip(),
            "cards": len(run),
            "segment": run[0]["segment"],
        })
        run.clear()

    for card in cards:
        if run:
            same_seg = card["segment"] == run[0]["segment"]
            gap = card["start"] - run[-1]["end"]
            span = card["end"] - run[0]["start"]
            if (not same_seg) or gap >= opts["gap"] or span > opts["beat_max"]:
                close()
        run.append(card)
        if run[-1]["end"] - run[0]["start"] >= opts["beat_target"]:
            close()
    close()

    # A last beat too short to register gets folded back rather than left as a flash.
    if len(beats) > 1 and (beats[-1]["end"] - beats[-1]["start"]) < opts["beat_min"]:
        tail = beats.pop()
        beats[-1]["end"] = tail["end"]
        beats[-1]["text"] = (beats[-1]["text"] + " " + tail["text"]).strip()
        beats[-1]["cards"] += tail["cards"]
    return beats


def beats_from_segments(segments: list[dict], opts: dict) -> list[dict]:
    """No cards at all: cut the segments themselves into beats."""
    beats = []
    for seg in segments:
        start, end = seg["edit_start"], seg["edit_end"]
        while end - start > opts["beat_max"] + EPS:
            beats.append({"start": round(start, 6), "end": round(start + opts["beat_target"], 6),
                          "text": "", "cards": 0, "segment": seg["index"]})
            start += opts["beat_target"]
        if end - start > EPS:
            beats.append({"start": round(start, 6), "end": round(end, 6),
                          "text": "", "cards": 0, "segment": seg["index"]})
    return beats


def close_the_timeline(beats: list[dict], total: float) -> list[str]:
    """Stretch the beats so they cover 0 to the end with no gap.

    Cards start after the first frame and stop before the last, so beats taken
    straight off them leave the placeholder picture showing at both ends. A hole in
    the picture is the one defect a viewer cannot miss, so the first beat is pulled
    back to zero, the last is pushed to the end, and any gap in between is closed by
    extending the beat before it. Every stretch is reported rather than done quietly.
    """
    notes: list[str] = []
    if not beats:
        return notes
    if beats[0]["start"] > EPS:
        notes.append("first beat pulled back %.2fs to cover the opening frame"
                     % beats[0]["start"])
        beats[0]["start"] = 0.0
    for i in range(len(beats) - 1):
        gap = beats[i + 1]["start"] - beats[i]["end"]
        if gap > EPS:
            beats[i]["end"] = beats[i + 1]["start"]
            if gap > 0.25:
                notes.append("%.2fs of silence after %.2fs held by the clip before it"
                             % (gap, beats[i]["start"]))
        elif gap < -EPS:
            beats[i]["end"] = beats[i + 1]["start"]
    if total - beats[-1]["end"] > EPS:
        notes.append("last beat pushed on %.2fs to reach the end of the piece"
                     % (total - beats[-1]["end"]))
        beats[-1]["end"] = round(total, 6)
    return notes


# ---------------------------------------------------------------------------
# the shelf
# ---------------------------------------------------------------------------


def load_shelf(path: Path) -> tuple[list[dict], list[str], dict]:
    """The labelled, present, usable clips, plus a count of why the rest were left out.

    One message for every reason is how a labelled shelf gets sent back to be
    labelled again. Each exclusion is counted separately and the caller says which
    one actually happened.
    """
    data = read_json(path, "the shelf from bin/shelf_index.py")
    base = path.parent
    pool: list[dict] = []
    notes: list[str] = []
    why = {"total": 0, "unreadable": 0, "marked_unusable": 0, "unlabelled": 0,
           "file_missing": 0, "no_duration": 0}
    for raw in data.get("clips") or []:
        why["total"] += 1
        if raw.get("problem"):
            why["unreadable"] += 1
            continue
        if raw.get("usable") is False:
            why["marked_unusable"] += 1
            continue
        label = (raw.get("label") or "").strip()
        if not label:
            why["unlabelled"] += 1
            continue
        rel = raw.get("path")
        if not rel:
            continue
        abs_path = Path(rel) if os.path.isabs(rel) else (base / rel)
        abs_path = abs_path.resolve()
        if not abs_path.exists():
            why["file_missing"] += 1
            notes.append("shelf names a clip that is not there: %s" % rel)
            continue
        dur = raw.get("duration_s")
        try:
            dur = float(dur)
        except (TypeError, ValueError):
            why["no_duration"] += 1
            notes.append("%s has no duration on the shelf, so it is left out" % raw.get("name"))
            continue
        tokens = [(w, 2.0) for kw in (raw.get("keywords") or []) for w in words_of(str(kw))]
        tokens += [(w, 1.0) for w in words_of(label)]
        pool.append({
            "id": raw.get("id") or abs_path.stem,
            "name": raw.get("name") or abs_path.name,
            "abs": abs_path,
            "duration": dur,
            "orientation": raw.get("orientation") or "unknown",
            "focus_x": raw.get("focus_x"),
            "focus_y": raw.get("focus_y"),
            "label": label,
            "tokens": tokens,
            "uses": 0,
            "consumed": 0.0,
        })
    return pool, notes, why


def score(clip: dict, beat_words: list[str]) -> tuple[float, list[str]]:
    """The weight of the match, and the words it matched on.

    Returning the words is the point. A match is not a guarantee that the picture
    belongs there: a single ordinary word can pair a shot of a harbour with "the shot
    I keep COMING back to", which is correct by these rules and wrong on screen. The
    only defence against that is a human reading the note, so the note names the words.
    """
    if not beat_words:
        return 0.0, []
    hit = 0.0
    seen = set()
    for token, weight in clip["tokens"]:
        if token in seen:
            continue
        for word in beat_words:
            if matches(token, word):
                hit += weight
                seen.add(token)
                break
    return hit, sorted(seen)


def pick(pool: list[dict], beat_words: list[str], previous: str | None,
         need: float) -> tuple[dict, float, list[str]]:
    """The clip whose keywords best fit these words, rotating rather than repeating."""
    best, best_key, best_raw, best_on = None, None, 0.0, []
    for clip in pool:
        raw, on = score(clip, beat_words)
        adjusted = raw - 0.6 * clip["uses"]
        if clip["id"] == previous:
            adjusted -= 10.0
        # A clip long enough for the beat is preferred over one that will freeze,
        # and only as a tie-break: a matching picture beats a convenient length.
        fits = 1 if clip["duration"] + EPS >= need else 0
        key = (round(adjusted, 4), fits, -clip["uses"], clip["duration"], clip["id"])
        if best_key is None or key > best_key:
            best, best_key, best_raw, best_on = clip, key, raw, on
    return best, (best_raw if best else 0.0), (best_on if best else [])


# ---------------------------------------------------------------------------
# layers
# ---------------------------------------------------------------------------


def layers_for_piece(piece: dict, cuts: dict, pool: list[dict], spec_dir: Path,
                     opts: dict) -> tuple[list[dict], dict]:
    pid = str(piece.get("piece") or "A1")
    segments, seg_problems = build_segments(piece)
    if not segments:
        return [], {"piece": pid, "problems": seg_problems + ["no usable segments"]}
    total = segments[-1]["edit_end"]
    cards, dropped = map_cards(piece, segments, cuts.get("times"))
    if cards:
        beats = beats_from_cards(cards, total, opts)
        source = "cards"
    else:
        beats = beats_from_segments(segments, opts)
        source = "segments"
    stretch_notes = close_the_timeline(beats, total)

    layers: list[dict] = []
    holds, splits, unmatched, horizontal = 0, 0, 0, 0
    previous = None

    for beat in beats:
        start, end = beat["start"], beat["end"]
        beat_words = words_of(beat["text"])
        splits_left = opts["max_splits"]
        first = True
        while end - start > EPS:
            need = end - start
            clip, raw, matched_on = pick(pool, beat_words, previous, need)
            if clip is None:
                break
            # Vary the in-point on a reuse, so the same clip does not open the same
            # way twice, but only where there is spare length to take it from.
            asset_start = 0.0
            spare = clip["duration"] - need
            if clip["uses"] and spare > 0.5:
                asset_start = round(min(clip["consumed"], spare), 3)
            usable = clip["duration"] - asset_start
            stop = end
            short = "hold"
            if usable + EPS < need:
                shortfall = need - usable
                if shortfall > opts["max_hold"] and splits_left > 0 and len(pool) > 1:
                    stop = round(start + usable, 6)
                    splits_left -= 1
                    splits += 1
                else:
                    holds += 1
            layer = {
                "piece": pid,
                "type": "full",
                "asset": rel_asset(clip["abs"], spec_dir),
                "start": round(start, 6),
                "end": round(stop, 6),
                "audio": "silent",
                "fit": "cover",
                "short": short,
                "long": "trim",
            }
            if asset_start:
                layer["asset_start"] = asset_start
            for axis in ("focus_x", "focus_y"):
                if isinstance(clip.get(axis), (int, float)):
                    layer[axis] = float(clip[axis])
            if raw >= opts["min_score"]:
                layer["matched_on"] = matched_on
                layer["note"] = ("%s. matched on %s, over: %s"
                                 % (clip["label"], ", ".join(matched_on) or "nothing",
                                    short_words(beat["text"])))
            else:
                layer["_matched"] = False
                layer["matched_on"] = matched_on
                if matched_on:
                    layer["note"] = ("%s. TOO WEAK TO CALL A MATCH: only %s, which scored %.1f "
                                     "under the %.1f needed. Over: %s"
                                     % (clip["label"], ", ".join(matched_on), raw,
                                        opts["min_score"], short_words(beat["text"])))
                else:
                    layer["note"] = ("%s. NO KEYWORD MATCHED these words, so this is a "
                                     "rotation pick: %s"
                                     % (clip["label"], short_words(beat["text"])))
                if first:
                    unmatched += 1
            if clip["orientation"] == "horizontal":
                horizontal += 1
            layers.append(layer)
            clip["uses"] += 1
            clip["consumed"] = round(min(clip["duration"], asset_start + (stop - start)), 3)
            previous = clip["id"]
            start = stop
            first = False

    covered = sum(l["end"] - l["start"] for l in layers)
    gaps = []
    cursor = 0.0
    for layer in sorted(layers, key=lambda l: l["start"]):
        if layer["start"] - cursor > 0.01:
            gaps.append((round(cursor, 3), round(layer["start"], 3)))
        cursor = max(cursor, layer["end"])
    if total - cursor > 0.01:
        gaps.append((round(cursor, 3), round(total, 3)))

    report = {
        "piece": pid,
        "seconds": round(total, 3),
        "beats": len(beats),
        "beats_from": source,
        "layers": len(layers),
        "covered_s": round(covered, 3),
        "gaps": gaps,
        "unmatched_beats": unmatched,
        "frozen_last_frames": holds,
        "beats_split_across_two_clips": splits,
        "horizontal_picks": horizontal,
        "cards_dropped": dropped,
        "notes": stretch_notes,
        "problems": seg_problems,
    }
    return layers, report


def short_words(text: str, n: int = 9) -> str:
    bits = (text or "").split()
    if not bits:
        return "(no words on this beat)"
    return " ".join(bits[:n]) + ("..." if len(bits) > n else "")


def rel_asset(abs_path: Path, spec_dir: Path) -> str:
    try:
        return os.path.relpath(abs_path, spec_dir)
    except ValueError:
        return str(abs_path)


SPEC_HELP = {
    "_what_this_is":
        "B-ROLL LAYERS for a reel with no camera on her, written by bin/broll_reel.py. "
        "One full frame cutaway per beat, back to back, covering the whole piece. The voice "
        "underneath is the tape; every layer is audio \"silent\" so nothing competes with it.",
    "_times":
        "start and end are FINISHED seconds, the clock you read off the player, which is what "
        "both renderers want. The cut list's own segment and card times are TAPE seconds and a "
        "different basis; this file has already done that mapping.",
    "_matched_false":
        "A layer marked \"_matched\": false got its clip by rotation rather than by meaning: "
        "nothing on the shelf had a keyword in those words. The picture is still there, because "
        "a hole is worse, and the fix is a keyword on a clip or a clip on the shelf.",
    "_editing_it":
        "This is an ordinary spec. Change an asset, nudge a start, delete a layer: both "
        "renderers read it the same. Re-running broll_reel.py overwrites it, so save a copy "
        "under another name once you have hand-tuned one.",
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="A voiceover cut list plus a labelled shelf becomes a reel of pure b-roll.")
    ap.add_argument("cuts", help="a cut list from bin/plan_clips.py")
    ap.add_argument("--shelf", required=True, help="a shelf from bin/shelf_index.py, labelled")
    ap.add_argument("--piece", default=None,
                    help="a piece id such as A1, or all. Default: the first piece in the cut list")
    ap.add_argument("--out", help="where to write the spec "
                                  "(default: specs/broll-<piece>.json beside the cut list)")
    ap.add_argument("--beat", type=float, default=BEAT_TARGET,
                    help="how long a cutaway should hold, in seconds (default %.1f)" % BEAT_TARGET)
    ap.add_argument("--beat-max", type=float, default=BEAT_MAX,
                    help="never hold one picture longer than this (default %.1f)" % BEAT_MAX)
    ap.add_argument("--beat-min", type=float, default=BEAT_MIN,
                    help="fold a tail shorter than this into the beat before it (default %.1f)"
                         % BEAT_MIN)
    ap.add_argument("--gap", type=float, default=GAP_BREAK,
                    help="silence this long changes picture (default %.1f)" % GAP_BREAK)
    ap.add_argument("--max-hold", type=float, default=MAX_HOLD,
                    help="a frozen last frame longer than this takes a second clip instead "
                         "(default %.1f)" % MAX_HOLD)
    ap.add_argument("--min-score", type=float, default=MIN_SCORE,
                    help="the match weight needed before a layer claims to be a match. A keyword "
                         "hit counts 2 and a word from the label counts 1, so the default means "
                         "one keyword or two label words (default %.1f)" % MIN_SCORE)
    ap.add_argument("--max-splits", type=int, default=MAX_SPLITS,
                    help="how many extra clips one beat may take (default %d)" % MAX_SPLITS)
    ap.add_argument("--force", action="store_true", help="overwrite the spec if it is there")
    ap.add_argument("--dry-run", action="store_true", help="report and write nothing")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    args = ap.parse_args(argv)

    if args.beat_max < args.beat:
        die("--beat-max %.2f is shorter than --beat %.2f" % (args.beat_max, args.beat))

    cuts_path = Path(args.cuts).expanduser()
    shelf_path = Path(args.shelf).expanduser()
    cuts = read_json(cuts_path, "the cut list from bin/plan_clips.py")
    pool, shelf_notes, why = load_shelf(shelf_path)

    pieces = cuts.get("pieces") or []
    if not pieces:
        die("%s has no pieces in it" % cuts_path)
    if not pool:
        lines = ["nothing usable on the shelf %s. Of %d clip(s) on it:" % (shelf_path, why["total"])]
        if why["file_missing"]:
            lines.append("  %d name a file that is not there. The paths in a shelf are relative "
                         "to the shelf file itself, so a shelf that moved needs re-indexing:"
                         % why["file_missing"])
            for note in shelf_notes[:4]:
                lines.append("      %s" % note)
            lines.append("    python3 bin/shelf_index.py <the clip folder> --out %s" % shelf_path)
        if why["unlabelled"]:
            lines.append("  %d have no label yet. shelf_index.py writes \"label\": null on "
                         "purpose, because a label needs eyes. Open the frames it extracted, "
                         "fill in label and keywords, then run this again." % why["unlabelled"])
        if why["marked_unusable"]:
            lines.append("  %d are marked \"usable\": false." % why["marked_unusable"])
        if why["unreadable"]:
            lines.append("  %d could not be read by ffprobe." % why["unreadable"])
        if why["no_duration"]:
            lines.append("  %d have no duration on the shelf." % why["no_duration"])
        die("\n".join(lines))

    want = (args.piece or str(pieces[0].get("piece") or "A1")).strip()
    if want.lower() == "all":
        chosen = pieces
    else:
        chosen = [p for p in pieces if str(p.get("piece")) == want]
        if not chosen:
            die("no piece %r in %s. It has: %s"
                % (want, cuts_path, ", ".join(str(p.get("piece")) for p in pieces)))

    opts = {
        "beat_target": args.beat, "beat_max": args.beat_max, "beat_min": args.beat_min,
        "gap": args.gap, "max_hold": args.max_hold, "max_splits": max(0, args.max_splits),
        "min_score": max(0.0, args.min_score),
    }

    written, reports, all_layers = [], [], []
    multi = len(chosen) > 1
    for piece in chosen:
        pid = str(piece.get("piece") or "A1")
        if args.out and not multi:
            out_path = Path(args.out).expanduser()
        else:
            stem = "broll-%s.json" % pid
            base = (Path(args.out).expanduser().parent if args.out
                    else cuts_path.parent)
            out_path = base / stem
        # Reset usage per piece: a clip that opened A1 should be free to open A2.
        for clip in pool:
            clip["uses"], clip["consumed"] = 0, 0.0
        layers, report = layers_for_piece(piece, cuts, pool, out_path.parent, opts)
        report["spec"] = str(out_path)
        reports.append(report)
        all_layers.extend(layers)
        if not layers:
            continue
        spec = dict(SPEC_HELP)
        spec["times"] = "edit"
        spec["defaults"] = {"audio": "silent", "asset_start": 0.0, "opacity": 1.0,
                            "fit": "cover", "focus_x": 0.5, "focus_y": 0.5,
                            "short": "hold", "long": "trim"}
        spec["built_from"] = {"cuts": str(cuts_path), "shelf": str(shelf_path),
                              "piece": pid, "beat_target_s": args.beat}
        spec["layers"] = layers
        text = json.dumps(spec, indent=2, ensure_ascii=False)
        if args.dry_run:
            continue
        if report["gaps"]:
            # A spec with a hole in the picture is not written. The report below names
            # every gap, and a file on disk is a file somebody can render by accident.
            continue
        if out_path.exists() and not args.force:
            die("%s is already there. Pass --force to replace it." % out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        written.append(str(out_path))

    unused = [c["name"] for c in pool if c["uses"] == 0]
    summary = {
        "written": written,
        "dry_run": bool(args.dry_run),
        "shelf_clips_available": len(pool),
        "shelf_clips_unused": unused,
        "shelf_problems": shelf_notes,
        "pieces": reports,
    }

    bad = any(r["gaps"] or not r["layers"] for r in reports)
    if args.json:
        print(json.dumps(summary, indent=2))
        return 1 if bad else 0

    print("")
    print("broll_reel  %s" % cuts_path)
    print("  shelf: %d labelled clip(s) from %s" % (len(pool), shelf_path))
    for note in shelf_notes[:4]:
        print("  shelf problem: %s" % note)
    for r in reports:
        print("")
        print("  %s  %.2fs  %d beat(s) from the %s, %d layer(s), %.2fs covered"
              % (r["piece"], r["seconds"], r["beats"], r["beats_from"],
                 r["layers"], r["covered_s"]))
        if r["gaps"]:
            for lo, hi in r["gaps"]:
                print("    GAP  %.2fs to %.2fs has no picture over it" % (lo, hi))
            print("    Nothing was written for %s. A spec with a hole in it is not a spec."
                  % r["piece"])
        if r["unmatched_beats"]:
            print("    %d beat(s) matched no keyword on the shelf and took a rotation pick."
                  % r["unmatched_beats"])
            print("    Those are marked \"_matched\": false in the spec.")
        if r["frozen_last_frames"]:
            print("    %d clip(s) are shorter than their beat and freeze the last frame "
                  "for the rest of it." % r["frozen_last_frames"])
        if r["beats_split_across_two_clips"]:
            print("    %d beat(s) took a second clip rather than freeze for longer than %.1fs."
                  % (r["beats_split_across_two_clips"], args.max_hold))
        if r["horizontal_picks"]:
            print("    %d layer(s) use a horizontal clip: a vertical frame crops the width off it."
                  % r["horizontal_picks"])
        if r["cards_dropped"]:
            print("    %d card(s) in the cut list fell in no kept segment and were ignored."
                  % r["cards_dropped"])
        for note in r["notes"][:4]:
            print("    %s" % note)
        for problem in r["problems"][:4]:
            print("    PROBLEM  %s" % problem)
    if unused:
        print("")
        print("  %d clip(s) on the shelf went unused: %s"
              % (len(unused), ", ".join(unused[:6]) + (" ..." if len(unused) > 6 else "")))
    print("")
    if args.dry_run:
        print("  --dry-run, so nothing was written.")
    else:
        for path in written:
            print("  wrote %s" % path)
        if written:
            print("")
            print("  Render it with captions above the picture:")
            print("    to_hyperframes.py %s --out work/reel --broll %s"
                  % (cuts_path, written[0]))
            print("  Or lay it over a finished clip with ffmpeg:")
            print("    python3 bin/broll.py <clip.mp4> --spec %s" % written[0])
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
