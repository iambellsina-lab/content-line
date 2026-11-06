#!/usr/bin/env python3
"""test_niche_loop.py: prove the research actually reaches the ranking.

WHY THIS EXISTS. Reported 2026-11-04, of a real account's output: every post
looked the same, with no content matching and no adaptation anywhere in it, so
the system was not learning or growing. That was accurate, and the reason was
not that the wiring was missing. `pick_pulls.py` already took a
--niche profile and already imported the hook patterns. The wiring was there and
it was INERT: a profile could be loaded, announced on stderr, and change not one
score. Measured that day: `niche_shape` appeared zero times in the output of a
run that had loaded a 179 video profile.

Three separate faults made it inert, and each one is pinned by a test below:

  1. load_niche kept only shapes marked `recommend`, so a shape the niche
     PUNISHES was discarded. The profile could praise but never warn, while the
     hand set block went on awarding +8 for a question opener in a niche whose
     winners avoid questions.
  2. The measured signal was capped at 6 points, while hand set signals ran to
     16 and 14, so even a direct hit could not move a ranking.
  3. The hook patterns are anchored at ^ and were written for TITLES. Speech
     opens with "So", "Okay", "Well". "So what was the moment you knew?" matched
     no shape at all, so the most common opener in real footage was invisible to
     the one part of the kit that reads research.

A green run here does not mean the picks are good. It means the research is
reaching them. That is the thing that was broken, and this is the thing that
stops it breaking again quietly.

Run:  python3 bin/test_niche_loop.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

BIN = Path(__file__).resolve().parent
KIT = BIN.parent
sys.path.insert(0, str(BIN))

FIXTURE = KIT / "specs" / "mixed-shapes-transcript.srt"
# Synthetic fixtures, not any business's research. A regression test that leans
# on a real niche artifact breaks the day somebody re-runs the research, and it
# couples the engine to one business's taste. The engine has no house niche and
# no house look: every profile is an input, one per business.
REWARDS_QUESTION = KIT / "specs" / "niche-fixture-rewards-question.json"   # question lift 1.38
PUNISHES_QUESTION = KIT / "specs" / "niche-fixture-punishes-question.json" # question lift 0.74

FAILURES = []
CHECKS = [0]


def check(name, ok, detail=""):
    CHECKS[0] += 1
    print(("  PASS  " if ok else "  FAIL  ") + name + (("   " + detail) if detail else ""))
    if not ok:
        FAILURES.append(name)


def run_pulls(transcript, niche=None, n=4):
    out = Path(tempfile.mkstemp(suffix=".json")[1])
    cmd = [sys.executable, str(BIN / "pick_pulls.py"), str(transcript), "-n", str(n),
           "--out", str(out)]
    if niche:
        cmd += ["--niche", str(niche)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("pick_pulls failed:\n" + r.stderr[-2000:])
    return json.loads(out.read_text())


def score_at(doc, start, tol=0.6):
    for p in doc["pulls"]:
        if abs(p["start"] - start) <= tol:
            return p["score"]
    return None


def main():
    print(__doc__.strip().splitlines()[0])
    print()

    # ---------------------------------------------------------------- unit
    print("the matcher reads speech, not only titles")
    from niche_calibrate import HOOKS, match_hook, strip_discourse

    spoken = "So what was the moment you knew something had to change?"
    check("a question behind a discourse marker is still a question",
          match_hook("question", spoken),
          '"So what was the moment..."')
    check("the raw anchored pattern alone would have missed it",
          not HOOKS["question"].search(spoken),
          "which is why match_hook exists")
    check("stacked markers are stripped",
          match_hook("question", "Okay so, like, what did that cost you?"),
          strip_discourse("Okay so, like, what did that cost you?"))
    check("a title still matches unchanged",
          match_hook("question", "How To Get Your First 10 Customers"))
    check("spoken numbers match the number shape",
          match_hook("number", "Three things killed our first business."))
    check("a plain statement matches no opener shape",
          not any(match_hook(h, "The rent was four thousand a month.")
                  for h in ("question", "number", "imperative", "first_person", "you")))

    # ------------------------------------------------------- profile loading
    print("\na profile keeps what the niche punishes, not only what it rewards")
    import pick_pulls as pp

    src = pp.load_niche(PUNISHES_QUESTION)
    check("the business profile loads", bool(pp.NICHE_HOOKS))
    check("'question' survives loading although recommend is false",
          "question" in pp.NICHE_HOOKS,
          "lift %.2f" % pp.NICHE_HOOKS.get("question", {}).get("lift", -1))
    check("it is reported as punished, not silently dropped",
          "question" in src["punishes"], ", ".join(src["punishes"]))
    check("a rewarded shape is reported too",
          "number" in src["rewards"], ", ".join(src["rewards"]))

    v = pp.niche_verdict("So what was the moment you knew it had to change?")
    check("a punished opener scores negative points", v is not None and v[3] < 0,
          "%s lift %.2f -> %+.1f pts" % (v[0], v[1], v[3]) if v else "no verdict")

    pp.load_niche(REWARDS_QUESTION)
    v2 = pp.niche_verdict("So what was the moment you knew it had to change?")
    check("the same opener scores positive under a niche that rewards it",
          v2 is not None and v2[3] > 0,
          "%s lift %.2f -> %+.1f pts" % (v2[0], v2[1], v2[3]) if v2 else "no verdict")

    # thin evidence must stay weak: that ethic is the producer's own and the
    # consumer has to honour it or the kit starts asserting off nine videos.
    thin = {"built_from": {"videos": 10, "winners": 3}, "confident": False,
            "hooks": [{"hook": "question", "lift": 3.0, "winners_using_it": 1,
                       "rest_rate": 0.0, "recommend": True}]}
    tmp = Path(tempfile.mkstemp(suffix=".json")[1])
    tmp.write_text(json.dumps(thin))
    pp.load_niche(tmp)
    vt = pp.niche_verdict("What did that cost you?")
    check("a wild lift off one video barely moves anything",
          vt is not None and abs(vt[3]) < 2.0,
          "%+.2f pts from 1 winner" % vt[3] if vt else "no verdict")

    # --------------------------------------------------------- end to end
    print("\nthe same transcript ranks differently under different research")
    base = run_pulls(FIXTURE)
    biz = run_pulls(FIXTURE, PUNISHES_QUESTION)
    aoyl = run_pulls(FIXTURE, REWARDS_QUESTION)

    QUESTION_CLIP = 76.2   # window whose opener is "So what was the moment..."

    b = score_at(base, QUESTION_CLIP)
    p = score_at(biz, QUESTION_CLIP)
    r = score_at(aoyl, QUESTION_CLIP)
    check("the question clip is found in all three runs",
          None not in (b, p, r), "none %.1f  punishes %.1f  rewards %.1f" % (b or 0, p or 0, r or 0))
    check("a niche that punishes questions LOWERS it", p < b, "%.1f -> %.1f" % (b, p))
    check("a niche that rewards questions RAISES it", r > b, "%.1f -> %.1f" % (b, r))
    check("the swing is big enough to matter", (r - p) >= 8.0,
          "%.1f points between the two niches" % (r - p))

    txt = json.dumps(biz)
    check("niche_shape actually appears in the output",
          "niche_shape" in txt,
          "this is the check that would have caught the inert loop")
    check("the output says why, in words a buyer can read",
          "travels worse here" in txt or "more often" in txt)
    check("the hand set guess is damped when measurement contradicts it",
          "hand set hook points cut" in txt)

    starts_biz = sorted(round(x["start"], 1) for x in biz["pulls"])
    starts_aoyl = sorted(round(x["start"], 1) for x in aoyl["pulls"])
    check("the two niches do not choose the same clips",
          starts_biz != starts_aoyl,
          "%s  vs  %s" % (starts_biz, starts_aoyl))

    # ------------------------------------------- the other consumer: drafting
    print("\nthe caption drafter answers to the same research")
    voice = KIT / "specs" / "voice.sample.json"
    if not voice.exists():
        check("a sample voice profile exists to draft against", False,
              "expected %s" % voice)
    else:
        def drafts_for(niche):
            out = Path(tempfile.mkstemp(suffix=".json")[1])
            cmd = [sys.executable, str(BIN / "draft_content.py"), str(out_pulls),
                   "--voice", str(voice), "--json"]
            if niche:
                cmd += ["--niche", str(niche)]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                raise SystemExit("draft_content failed:\n" + r.stderr[-2000:])
            return json.loads(r.stdout)

        out_pulls = Path(tempfile.mkstemp(suffix=".json")[1])
        out_pulls.write_text(json.dumps(base))

        d_biz = drafts_for(PUNISHES_QUESTION)
        d_aoyl = drafts_for(REWARDS_QUESTION)

        check("the drafter reports what the niche punishes, not only what it rewards",
              "question" in d_biz.get("niche_punishes", []),
              ", ".join(d_biz.get("niche_punishes", [])))

        first = lambda d: [(x.get("lines") or [""])[0] for x in d["drafts"]]
        op_biz, op_aoyl = first(d_biz), first(d_aoyl)
        check("the two niches do not write the same openers", op_biz != op_aoyl,
              "%r  vs  %r" % (op_biz[-1], op_aoyl[-1]))

        q_biz = [o for o in op_biz if o and o.rstrip().endswith("?")]
        q_aoyl = [o for o in op_aoyl if o and o.rstrip().endswith("?")]
        check("a niche that punishes questions writes fewer question openers",
              len(q_biz) < len(q_aoyl), "%d vs %d" % (len(q_biz), len(q_aoyl)))

        # A punished shape must lose to a neutral one. This is the behaviour
        # that was impossible before: with only rewarded shapes loaded, a shape
        # the niche avoids scored the same as one it had never measured, so the
        # drafter had no reason to step around it.
        def chosen_shapes(d):
            return [x.get("opener_shape") for x in d["drafts"]]

        punished_biz = set(d_biz.get("niche_punishes", []))
        picked_punished = [s for s in chosen_shapes(d_biz) if s in punished_biz]
        check("the drafter does not open on a shape the niche punishes "
              "when anything else is available",
              not picked_punished,
              "chose %s, punished %s" % (chosen_shapes(d_biz), sorted(punished_biz)))

    print("\nno profile means no change (nothing regressed for existing users)")
    again = run_pulls(FIXTURE)
    check("two runs with no niche are identical",
          [x["score"] for x in again["pulls"]] == [x["score"] for x in base["pulls"]])
    check("no niche_shape signal appears without a profile",
          "niche_shape" not in json.dumps(base))

    print()
    if FAILURES:
        print("FAILED %d of %d" % (len(FAILURES), CHECKS[0]))
        for f in FAILURES:
            print("   " + f)
        return 1
    print("all %d checks passed: the research reaches the ranking." % CHECKS[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
