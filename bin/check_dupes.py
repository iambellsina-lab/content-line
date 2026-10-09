#!/usr/bin/env python3
"""check_dupes.py: do any two of these clips use the same tape? Exits 1 if they do.

    python3 bin/check_dupes.py cuts.json
    python3 bin/check_dupes.py work/*.json --threshold 1.0
    python3 bin/check_dupes.py work/            # every .json in the folder
    python3 bin/check_dupes.py cuts.json --json

WHY THIS EXISTS
    Six finished reels came out of one 26 minute recording. Two PAIRS of them turned out to share
    more than fifty seconds of the same tape each, and two of them ended on the identical closing
    line. Nobody saw it until the files were rendered, and by then the only fix was to rebuild.

    Finding it from the cut lists is arithmetic. It takes a fraction of a second and it has to
    happen BEFORE the render, which is the expensive part. So this runs as a gate, not a report:
    it exits non-zero when it finds an overlap, so a build script stops.

    Overlap is not always wrong. A deliberate callback across two clips is a choice. The point is
    that it should be a choice, made with the number in front of you.

WHAT COUNTS AS USED TAPE
    Three cut list shapes are understood, because this kit has produced all three.

    1. {"pieces": [{"segments": [{"start", "end"}, ...]}]}      the non-linear shape
    2. [{"start", "end", "internal_cuts": [[a, b], ...]}]       span minus the removed ranges
    3. {"pulls": [{"start", "end"}]}                            pick_pulls.py output

    The collection may sit under "pieces", "built", "clips", "cuts" or "pulls", and may be a list
    or a dict keyed by piece id. All of those have come out of this kit at some point.

    For shape 2 the internal_cuts are the ranges REMOVED from the span, so used tape is the span
    with those ranges taken out. That is checked against the arithmetic in the file: if the stated
    duration matches span minus internal_cuts, the reading is right, and the check says so.

WHAT IT REPORTS
    For every pair over the threshold: total shared seconds, how many separate shared ranges, the
    largest one with timecodes, and whether BOTH clips end inside shared tape, which is the
    identical-ending case and the one a viewer notices first.
"""
import argparse
import glob
import json
import os
import sys

THRESHOLD = 1.0          # seconds. Under this is rounding, not duplication.
TAIL_WINDOW = 3.0        # the last few seconds of a clip, where an identical close shows up


def timecode(sec):
    m, s = divmod(max(0.0, sec), 60)
    h, m = divmod(int(m), 60)
    return "%d:%02d:%04.1f" % (h, m, s) if h else "%02d:%04.1f" % (m, s)


def merge(ranges):
    out = []
    for a, b in sorted(ranges):
        if b <= a:
            continue
        if out and a <= out[-1][1] + 1e-9:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [tuple(r) for r in out]


def subtract(span, holes):
    a, b = span
    kept, cur = [], a
    for ha, hb in merge(holes):
        if hb <= cur or ha >= b:
            continue
        if ha > cur:
            kept.append((cur, min(ha, b)))
        cur = max(cur, hb)
        if cur >= b:
            break
    if cur < b:
        kept.append((cur, b))
    return merge(kept)


def intersect(a_ranges, b_ranges):
    out, i, j = [], 0, 0
    while i < len(a_ranges) and j < len(b_ranges):
        lo = max(a_ranges[i][0], b_ranges[j][0])
        hi = min(a_ranges[i][1], b_ranges[j][1])
        if hi > lo:
            out.append((lo, hi))
        if a_ranges[i][1] < b_ranges[j][1]:
            i += 1
        else:
            j += 1
    return out


def total(ranges):
    return sum(b - a for a, b in ranges)


def clips_from(path, notes):
    """Every clip in one file, as a name plus the source ranges it actually uses."""
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    base = os.path.basename(path)
    rows = []
    items, kind = None, "list"
    if isinstance(data, list):
        items = [(None, x) for x in data]
    elif isinstance(data, dict):
        for key in ("pieces", "built", "clips", "cuts", "pulls"):
            got = data.get(key)
            if isinstance(got, list):
                items, kind = [(None, x) for x in got], key
                break
            if isinstance(got, dict):
                items, kind = list(got.items()), key
                break
    if items is None:
        notes.append("%s: no pieces, built, clips, cuts or pulls collection in this file, skipped."
                     % base)
        return rows
    for k, (key, it) in enumerate(items, 1):
        if not isinstance(it, dict):
            continue
        name = (it.get("filename") or it.get("piece") or it.get("id") or key
                or ("%s #%d" % (kind, it.get("rank", k))))
        if key and it.get("filename"):
            name = "%s %s" % (key, it["filename"])
        segs = it.get("segments")
        if isinstance(segs, list) and segs:
            used = merge([(float(s["start"]), float(s["end"])) for s in segs
                          if s.get("start") is not None and s.get("end") is not None])
            shape = "%d segments" % len(segs)
        elif it.get("start") is not None and it.get("end") is not None:
            span = (float(it["start"]), float(it["end"]))
            holes = [(float(a), float(b)) for a, b in (it.get("internal_cuts") or [])]
            used = subtract(span, holes) if holes else [span]
            shape = "span minus %d removed ranges" % len(holes) if holes else "one span"
            stated = it.get("duration")
            if holes and stated is not None and abs(total(used) - float(stated)) > 0.2:
                if abs(float(stated) - (span[1] - span[0])) <= 0.2:
                    notes.append("%s / %s: its own duration field holds the SPAN (%.2f), not the "
                                 "finished length. The tape it uses is still %.2fs and the overlap "
                                 "numbers below are right."
                                 % (base, name, float(stated), total(used)))
                else:
                    notes.append("%s / %s: internal_cuts read as REMOVED gives %.2fs, the span is "
                                 "%.2fs, and the file says duration %.2f. None of the three agree, "
                                 "so this clip's overlaps are not trustworthy."
                                 % (base, name, total(used), span[1] - span[0], float(stated)))
        else:
            notes.append("%s / %s: no segments and no start and end, skipped." % (base, name))
            continue
        if not used:
            notes.append("%s / %s: uses no tape at all." % (base, name))
            continue
        rows.append({"file": base, "path": path, "name": str(name), "used": used,
                     "seconds": total(used), "shape": shape,
                     "last_end": max(b for _a, b in used)})
    return rows


def expand(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            out += sorted(glob.glob(os.path.join(p, "*.json")))
        else:
            out += sorted(glob.glob(p)) or [p]
    seen, uniq = set(), []
    for p in out:
        rp = os.path.realpath(p)
        if rp not in seen:
            seen.add(rp)
            uniq.append(p)
    return uniq


def main():
    ap = argparse.ArgumentParser(description="Report any pair of clips that share source tape.")
    ap.add_argument("cutlists", nargs="+", help="cut list JSON files, globs, or folders")
    ap.add_argument("--threshold", type=float, default=THRESHOLD,
                    help="report a pair sharing more than this many seconds (default 1.0)")
    ap.add_argument("--json", action="store_true", dest="as_json", help="machine readable output")
    ap.add_argument("--quiet", action="store_true", help="print nothing, just set the exit code")
    a = ap.parse_args()

    notes, clips = [], []
    for path in expand(a.cutlists):
        if not os.path.isfile(path):
            notes.append("%s: no such file." % path)
            continue
        try:
            clips += clips_from(path, notes)
        except (ValueError, KeyError, TypeError) as e:
            notes.append("%s: could not be read as a cut list (%s)." % (os.path.basename(path), e))

    findings = []
    for x in range(len(clips)):
        for y in range(x + 1, len(clips)):
            p, q = clips[x], clips[y]
            shared = intersect(p["used"], q["used"])
            secs = total(shared)
            if secs <= a.threshold:
                continue
            biggest = max(shared, key=lambda r: r[1] - r[0])
            tail_p = any(b > p["last_end"] - TAIL_WINDOW for _a, b in shared)
            tail_q = any(b > q["last_end"] - TAIL_WINDOW for _a, b in shared)
            findings.append({
                "a": "%s / %s" % (p["file"], p["name"]),
                "b": "%s / %s" % (q["file"], q["name"]),
                "shared_seconds": round(secs, 2),
                "shared_ranges": len(shared),
                "share_of_a": round(100.0 * secs / p["seconds"], 1),
                "share_of_b": round(100.0 * secs / q["seconds"], 1),
                "largest": [round(biggest[0], 2), round(biggest[1], 2)],
                "largest_tc": "%s to %s" % (timecode(biggest[0]), timecode(biggest[1])),
                "same_ending": bool(tail_p and tail_q),
            })
    findings.sort(key=lambda f: -f["shared_seconds"])

    if a.as_json:
        print(json.dumps({"clips_checked": len(clips), "pairs_compared":
                          len(clips) * (len(clips) - 1) // 2,
                          "threshold_seconds": a.threshold, "notes": notes,
                          "findings": findings}, indent=1))
    elif not a.quiet:
        print("check_dupes: %d clips, %d pairs compared, threshold %.2fs"
              % (len(clips), len(clips) * (len(clips) - 1) // 2, a.threshold))
        for c in clips:
            print("  %-46s %6.2fs of tape  (%s)" % (c["file"] + " / " + c["name"],
                                                    c["seconds"], c["shape"]))
        for n in notes:
            print("  note: %s" % n)
        if not findings:
            print("PASS: no pair shares more than %.2fs." % a.threshold)
        for f in findings:
            print()
            print("OVERLAP %.2fs shared  (%.0f%% of the first, %.0f%% of the second)"
                  % (f["shared_seconds"], f["share_of_a"], f["share_of_b"]))
            print("  %s" % f["a"])
            print("  %s" % f["b"])
            print("  %d shared range(s), largest %s" % (f["shared_ranges"], f["largest_tc"]))
            if f["same_ending"]:
                print("  BOTH CLIPS END INSIDE SHARED TAPE. Two clips finishing on the same line "
                      "is the thing a viewer notices first.")
        if findings:
            print()
            print("FAIL: %d pair(s) over the threshold. Change one of each pair before rendering, "
                  "or decide the callback is deliberate." % len(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
