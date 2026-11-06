#!/usr/bin/env python3
"""Measure what is actually winning on YouTube for a set of search terms.

Why this exists: Instagram and TikTok gate search behind a login and hide view counts from
logged-out visitors, so a niche cannot be measured there without signing in as the user, which this
kit never does. YouTube does not. Its search results embed a JSON blob called ytInitialData that
carries exact view counts, durations, channels and upload ages, and a plain HTTP fetch gets it.

So YouTube is the free, honest measuring stick for a niche. The shapes that win there (how a title
opens, how long a thing runs, what gets watched) carry over to reels and short video, which is where
most of this kit's output goes.

Usage:
    python3 bin/yt_probe.py "query one" "query two" ...
    python3 bin/yt_probe.py --file queries.txt --out research/niche.json
    python3 bin/yt_probe.py --shorts "query"     # restrict to Shorts

Reads only. Logs in to nothing. Follows, likes and subscribes to nothing.
"""
import argparse, json, re, sys, time, urllib.parse, urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
SHORTS_FILTER = "EgIYAQ%3D%3D"       # YouTube's own "Shorts" search filter


def fetch(query, shorts=False, timeout=25):
    """Fetch a results page.

    Two routes on purpose. Many Python installs, the python.org macOS build especially, ship without
    a usable CA bundle and raise CERTIFICATE_VERIFY_FAILED on any https call. curl uses the system
    trust store and works where that build does not, so it is the fallback rather than an error.
    Verification is never disabled.
    """
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
    if shorts:
        url += "&sp=" + SHORTS_FILTER
    headers = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
    try:
        ctx = None
        try:
            import certifi, ssl
            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        import subprocess
        out = subprocess.run(
            ["curl", "-sL", "--max-time", str(timeout), "-A", UA,
             "-H", "Accept-Language: en-US,en;q=0.9", url],
            capture_output=True)
        if out.returncode != 0 or not out.stdout:
            raise RuntimeError("both urllib and curl failed for: " + query)
        return out.stdout.decode("utf-8", "replace")


def initial_data(html):
    m = re.search(r"var ytInitialData\s*=\s*(\{.*?\});</script>", html, re.S)
    if not m:
        m = re.search(r'window\["ytInitialData"\]\s*=\s*(\{.*?\});', html, re.S)
    return json.loads(m.group(1)) if m else None


def views_to_int(s):
    """'10,746 views' -> 10746. 'No views' -> 0. '1.2M views' -> 1200000."""
    if not s:
        return None
    s = s.replace(" ", " ").strip()
    if s.lower().startswith("no views"):
        return 0
    m = re.match(r"([\d.,]+)\s*([KMB])?", s)
    if not m:
        return None
    n = float(m.group(1).replace(",", ""))
    return int(n * {"K": 1e3, "M": 1e6, "B": 1e9}.get(m.group(2) or "", 1))


def dur_to_sec(s):
    if not s:
        return None
    parts = [int(p) for p in s.split(":") if p.isdigit()]
    if not parts:
        return None
    sec = 0
    for p in parts:
        sec = sec * 60 + p
    return sec


def harvest(node, out):
    """Walk the blob. Both long videos and Shorts, each tagged with its format."""
    if isinstance(node, dict):
        if "videoRenderer" in node:
            v = node["videoRenderer"]
            title = "".join(r.get("text", "") for r in v.get("title", {}).get("runs", []))
            vc = v.get("viewCountText", {})
            views = vc.get("simpleText") or "".join(r.get("text", "") for r in vc.get("runs", []))
            out.append({
                "format": "long",
                "title": title,
                "channel": (v.get("ownerText", {}).get("runs") or [{}])[0].get("text"),
                "views": views_to_int(views),
                "views_raw": views,
                "duration": v.get("lengthText", {}).get("simpleText"),
                "duration_s": dur_to_sec(v.get("lengthText", {}).get("simpleText")),
                "age": v.get("publishedTimeText", {}).get("simpleText"),
                "id": v.get("videoId"),
            })
        for key in ("reelItemRenderer", "shortsLockupViewModel"):
            if key in node:
                v = node[key]
                if key == "reelItemRenderer":
                    title = v.get("headline", {}).get("simpleText")
                    views = v.get("viewCountText", {}).get("simpleText")
                    vid = v.get("videoId")
                else:
                    title = (v.get("overlayMetadata", {}).get("primaryText", {}) or {}).get("content")
                    views = (v.get("overlayMetadata", {}).get("secondaryText", {}) or {}).get("content")
                    vid = (v.get("onTap", {}).get("innertubeCommand", {})
                           .get("reelWatchEndpoint", {}) or {}).get("videoId")
                out.append({
                    "format": "short", "title": title, "channel": None,
                    "views": views_to_int(views), "views_raw": views,
                    "duration": None, "duration_s": None, "age": None, "id": vid,
                })
        for x in node.values():
            harvest(x, out)
    elif isinstance(node, list):
        for x in node:
            harvest(x, out)
    return out


def probe(query, shorts=False):
    data = initial_data(fetch(query, shorts))
    if not data:
        return {"query": query, "error": "ytInitialData not found", "results": []}
    rows = harvest(data, [])
    seen, uniq = set(), []
    for r in rows:
        k = r.get("id") or r.get("title")
        if k and k not in seen:
            seen.add(k)
            uniq.append(r)
    return {"query": query, "shorts_filter": shorts, "results": uniq}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("queries", nargs="*")
    ap.add_argument("--file", help="one query per line")
    ap.add_argument("--out", help="write JSON here")
    ap.add_argument("--shorts", action="store_true", help="restrict to Shorts")
    ap.add_argument("--sleep", type=float, default=1.5, help="seconds between queries, be polite")
    a = ap.parse_args()

    qs = list(a.queries)
    if a.file:
        qs += [l.strip() for l in open(a.file) if l.strip() and not l.startswith("#")]
    if not qs:
        ap.error("give at least one query, or --file")

    out = []
    for i, q in enumerate(qs):
        try:
            r = probe(q, a.shorts)
        except Exception as e:
            r = {"query": q, "error": repr(e), "results": []}
        out.append(r)
        vals = [x["views"] for x in r["results"] if x.get("views") is not None]
        vals.sort()
        med = vals[len(vals) // 2] if vals else None
        top = max(vals) if vals else None
        print(f"{q[:46]:<48} n={len(r['results']):>3}  median={med if med is not None else '-':>8}"
              f"  top={top if top is not None else '-':>9}", file=sys.stderr)
        if i < len(qs) - 1:
            time.sleep(a.sleep)

    blob = json.dumps(out, ensure_ascii=False, indent=1)
    if a.out:
        open(a.out, "w").write(blob)
        print(f"\nwrote {a.out}", file=sys.stderr)
    else:
        print(blob)


if __name__ == "__main__":
    main()
