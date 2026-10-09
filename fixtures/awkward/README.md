# Awkward transcripts

Eight short transcripts of things real speech does and clean samples do not. `kit_check.py` runs
`cards_from_srt.py` over all of them and checks the cards that come back are usable: inside the
trim, ending after they start, never more than four words, never held longer than three seconds,
never overlapping each other, never empty.

They are hand-written, not recorded. They exist because the kit had only ever been run against one
clean sample transcript, and clean samples hide exactly the failures that matter on a real recording.

| File | What it is | What should happen |
|---|---|---|
| `pause-midsentence.srt` | a four second silence in the middle of a sentence | the silence becomes a real gap between cards, not a card held across it |
| `stutter.srt` | "I I I think the- the the problem" | kept as said, and the run is reported. `--collapse-stutters` drops the false starts |
| `crosstalk.srt` | two people over each other, with `>> ANNA:` labels and overlapping cue times | names never reach the screen, no card spans a change of speaker, the overlap is reported |
| `no-punctuation.srt` | one long cue, no full stops at all | cards still break on the word cap, so nothing runs off the screen |
| `all-filler.srt` | nothing but "um, uh, you know, I mean" | exits 1 and says why, rather than writing empty cards |
| `bad-times.srt` | a zero length cue and a backwards cue | the bad cues are dropped, the good ones survive |
| `junk-cues.srt` | `[MUSIC]`, `(applause)`, and a word too long for one line | tags never become captions |
| `long-hold.srt` | one word, then nine seconds of nothing | the card is capped at three seconds and the silence stays silent |

If you change `cards_from_srt.py`, run `kit_check.py` and read this check before you trust it.
