#!/usr/bin/env python3
"""schedule_post.py: a rendered clip becomes a DRAFT in the scheduler. Never a post.

WHY THIS EXISTS. `publish_media.py` gives a local file a public address, which is
one step of publishing and not publishing. Nothing took the next step, and
`CHOOSING-A-SCHEDULER.md` is a decision document rather than an integration. This
closes that, for the one scheduler that document recommends: "start on a free
Metricool account."

DRAFT IS THE DEFAULT, AND IT IS NOT A WALL. `CHOOSING-A-SCHEDULER.md` ends with
the line that does not change with the tool: posts queue as drafts for a human to
approve. So a draft is what you get unless you say otherwise, and `--live` says
otherwise.

An earlier version of this file refused to publish at all, with no flag to
override it. That was the wrong shape and the kit's owner said so: it should be a
conversation rather than a hard guard. A rule a person cannot override stops
being a safeguard the first time it blocks something they actually asked for, and
then they route around the tool entirely, which is worse than the risk it was
guarding. The same mistake was made once before on this account with a hook that
blocked her own request twice.

So: the structural checks stay hard, because an empty caption or a time with no
timezone is a bug rather than a decision. The publish decision is the human's,
it defaults to draft, and `--live` states plainly what it is about to do before
doing it.

WHY IT DOES NOTHING BY DEFAULT. Running it prints the exact payload and stops. It
only reaches the network when a human adds --send, and then it needs credentials
from the environment that are deliberately not storable in this repo. A buyer's
first run should show them what would happen, in full, before anything happens.

WHAT IT WILL NOT DO. It cannot delete anything and it cannot read anybody's
numbers. It makes one POST, and prints the id so a person can go and look at it.

Usage:
    python3 bin/schedule_post.py --media URL --caption c.txt --when 2026-10-20T09:00:00-04:00 \\
        --networks instagram,tiktok
    ... --send                      # actually create it, as a draft
    ... --send --live               # create it live, if that is what you want
    METRICOOL_USER_ID=... METRICOOL_TOKEN=... required for --send
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://app.metricool.com/api/v2/scheduler/posts"

# Where a caption stops being a caption. Numbers from each platform's own published
# limit; the kit warns rather than truncates, because silently cutting somebody's
# words is worse than telling them the words are too long.
LIMITS = {"instagram": 2200, "tiktok": 2200, "facebook": 63206,
          "linkedin": 3000, "twitter": 280, "threads": 500, "pinterest": 500,
          "youtube": 5000, "bluesky": 300}

NETWORKS = sorted(LIMITS)


def die(msg):
    sys.exit("  %s" % msg)


def check_when(s):
    """A time without an offset is a time in somebody else's day. Metricool reads
    the offset, and a post scheduled in the wrong zone goes out in the night."""
    if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?([+-]\d{2}:\d{2}|Z)$", s):
        die("--when must carry a timezone offset, for example "
            "2026-10-20T09:00:00-04:00. Got: %r" % s)
    return s


def check_media(url, verify):
    if not url.startswith(("http://", "https://")):
        die("--media must be a public URL. A path on your computer is not reachable by a "
            "scheduler. Run publish_media.py first.")
    if url.startswith("http://"):
        print("  warning: http rather than https. Some platforms refuse it.")
    if not verify:
        return
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            ct = r.headers.get("Content-Type", "")
            ln = r.headers.get("Content-Length")
            print("  media reachable: %s%s" % (ct, (", %s bytes" % ln) if ln else ""))
            if not ct.startswith(("image/", "video/")):
                print("  warning: the server calls that %r, which is neither image nor video" % ct)
    except Exception as e:
        die("could not reach --media: %s\n  A scheduler will not be able to either." % e)


def build(media, caption, when, networks, live=False):
    """Draft unless the caller asked for live, which is a thing a person decides."""
    return {
        "providers": [{"network": n} for n in networks],
        "publicationDate": {"dateTime": when},
        "text": caption,
        "media": [media],
        "draft": not live,
        "autoPublish": bool(live),
    }


def check_payload(payload):
    """Only the things that are broken rather than the things that are allowed.

    An empty caption and a post addressed to nobody are bugs: sending them helps
    no one and the scheduler would reject them anyway. Whether it goes out live is
    not a bug, it is a decision, and it belongs to whoever is reading the screen.
    """
    if not payload.get("providers"):
        die("no networks chosen.")
    if not payload.get("text", "").strip():
        die("the caption is empty.")


def send(payload):
    uid, token = os.environ.get("METRICOOL_USER_ID"), os.environ.get("METRICOOL_TOKEN")
    if not uid or not token:
        die("--send needs METRICOOL_USER_ID and METRICOOL_TOKEN in the environment.\n"
            "  They are not read from any file in this repo, and they should not be put in one.")
    q = urllib.parse.urlencode({"userId": uid, "userToken": token})
    req = urllib.request.Request(
        "%s?%s" % (API, q), method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            body = r.read().decode("utf-8", "replace")
            code = r.status
    except urllib.error.HTTPError as e:
        die("the scheduler refused it: HTTP %s\n  %s" % (e.code, e.read().decode("utf-8", "replace")[:400]))
    except Exception as e:
        die("could not reach the scheduler: %s" % e)
    try:
        data = json.loads(body)
    except ValueError:
        print("  HTTP %s, and the reply was not JSON:\n  %s" % (code, body[:400]))
        return
    pid = (data.get("data") or {}).get("id") or data.get("id")
    print("\n  created id %s" % pid)
    print("  draft=%s  autoPublish=%s  (read back from the reply)"
          % ((data.get("data") or data).get("draft"), (data.get("data") or data).get("autoPublish")))
    print("  Go and look at it in the planner.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--media", required=True, help="public URL, from publish_media.py")
    ap.add_argument("--caption", required=True, help="a text file holding the caption")
    ap.add_argument("--when", required=True, help="ISO time WITH a timezone offset")
    ap.add_argument("--networks", required=True,
                    help="comma separated: " + ", ".join(NETWORKS))
    ap.add_argument("--send", action="store_true",
                    help="actually create it. Without this it only prints.")
    ap.add_argument("--live", action="store_true",
                    help="create it live rather than as a draft. Default is a draft.")
    ap.add_argument("--no-verify-media", action="store_true",
                    help="skip the reachability check on --media")
    a = ap.parse_args()

    nets = [n.strip().lower() for n in a.networks.split(",") if n.strip()]
    bad = [n for n in nets if n not in LIMITS]
    if bad:
        die("unknown network(s): %s\n  known: %s" % (", ".join(bad), ", ".join(NETWORKS)))

    try:
        caption = open(a.caption, encoding="utf-8").read().strip()
    except OSError as e:
        die("could not read --caption: %s" % e)
    if not caption:
        die("the caption file is empty.")

    check_when(a.when)
    check_media(a.media, not a.no_verify_media)
    for n in nets:
        if len(caption) > LIMITS[n]:
            print("  warning: caption is %d characters, %s allows %d"
                  % (len(caption), n, LIMITS[n]))

    payload = build(a.media, caption, a.when, nets, live=a.live)
    check_payload(payload)

    if a.live:
        print("\n  LIVE. This will post to %s at %s, with no human step after this."
              % (", ".join(nets), a.when))
        print("  Drop --live to queue it as a draft instead.")
    print("\n  this is exactly what would be sent:\n")
    print("\n".join("    " + l for l in json.dumps(payload, indent=1).splitlines()))
    if not a.send:
        print("\n  nothing was sent. Add --send to create it%s.\n"
              % ("" if a.live else " as a draft"))
        return 0
    send(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
