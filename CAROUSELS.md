# Carousels

**In:** a brand file and a carousel file, both JSON.
**Out:** finished PNG slides at 1080x1350, the Instagram portrait carousel size, plus a contact
sheet so a human can read the whole set in one image.

Runs on your own computer, offline, free. It needs Pillow and nothing else. **Nothing here posts,
schedules, uploads or spends money.** It writes files to a folder and stops.

```bash
.venv/bin/python bin/carousel_render.py --brand specs/carousel-brand.example.json \
    --carousel specs/my-carousel.json --out-dir out/my-carousel
```

---

## The one thing this does that a text-on-a-card script does not

**It checks its own work, and it checks it by looking at the pixels.**

Every slide is drawn in two layers. A background layer carries the flat colour and any full bleed
panel. An ink layer, transparent, carries every pixel of type and every rule. After the slide is
drawn, the ink layer's alpha channel is measured with `getbbox()`, and that bounding box is
compared with the four margins. It is the real extent of the ink as rasterised, not a prediction
from font metrics. If it crosses a margin the slide is a failure and the run exits non zero.

This exists because a return code proves a file was written and nothing more. This account has
shipped a zero byte file reported as success and captions that landed on a chin, both on a clean
exit. Open the PNG. The renderer does the equivalent for you on every slide, every run.

It is not a substitute for reading the slides. It caught nothing on the run that produced the
first real set; **opening the images caught three defects on that same run**, all recorded in the
code comments: a hairline under the source line instead of above it, an attribution orphaned
below the question instead of under the quote, and tracked small caps drawing every full stop at
cap height so that an initialism like "T.H.I.S." came out as floating dots. Every exit code in that run
was zero. Build the contact sheet and read it.

---

## It refuses rather than crashing

Each of these prints what is wrong, which slide, and what to change, and exits 1:

| It refuses when | Because |
|---|---|
| a font file is missing or will not load | checked for every font before a single pixel is drawn, so a wrong path is one message at the start, not a traceback halfway through a batch |
| a slide has no `text` | a slide with nothing to read is not a slide |
| text will not fit even shrunk to half size | usually one unbreakable word, or a URL. It says which element and how many pixels over |
| a colour fails its contrast threshold | these get read on a phone |
| a theme or role is not in the brand file | a slide in the wrong brand is a real error, so it will not guess or fall back to the first one |
| the rule is told to follow an element the slide does not carry | silently dropping it would hide the mistake |
| a written PNG is under 1000 bytes | a near empty file is a failure however the save call returned |

**A batch that fails partway leaves the slides it already wrote.** The run exits non zero, so you
know not to use them, but they are on disk. Re-render after fixing, do not post from a failed run.

---

## Contrast

Ratios are WCAG 2.1 relative luminance. The default threshold is 4.5, the normal text rule. An
element may declare its own `"min_contrast"`, and 3.0 is the WCAG allowance for large text and for
graphical objects such as a rule.

That setting is the honest way to use a brand colour that is too light for body copy. Plenty of
real brand palettes do not clear 4.5 on white: a mid teal lands near 3.2 and a mid violet near
3.7. The wrong answer is to darken the client's colour quietly until a number passes. The right
answer is to use it at display size, where 3.0 is the standard, set `"min_contrast": 3.0` on that
element so the decision is written down, and keep every small line in something that clears 4.5.

---

## The two files

### The brand file

`specs/carousel-brand.example.json` is a commented, deliberately neutral starting point: black on
white, one grey accent, system fonts, nobody's identity. Copy it and change the values. Every
colour, font, margin, size, gap and line height the renderer uses comes from it. Nothing is
hardwired to any one client, which is the whole point of the file.

It holds `size`, a `fonts` block mapping logical names to real files on this machine, and a
`themes` block. **A brand may hold more than one theme.** That matters when a client is genuinely
two brands that must not touch: name them, make each carousel say which one it belongs to, and the
renderer refuses a theme it does not know rather than picking one.

Inside a theme: a `palette`, a `margin`, the page furniture (`footer`, `counter`, `swipe`), and
`roles`.

### Roles are what make a cover not look like a body slide

A slide names its role and the role styles it. `cover`, `body` and `final` are the usual three and
the names are yours; add a `quote` role wherever a client is quoted often. A role sets
its own background colour, its own text box, and the styling for each element it allows.

The elements stack in this fixed order down the page:

```
label     a short glyph or number, usually large and in the accent
text      the main line. Required
attrib    a source line, usually small caps with tracking
question  a medium line, for the question a final slide asks
cta       the call to action
```

Every one except `text` is optional. A role styles the ones it wants. **A slide that carries an
element its role does not style is refused**, which is how a `question` on a body slide gets
caught instead of silently vanishing.

`gap_before` is the space above an element and is ignored on whichever one happens to be first.
`px_min` is a floor the shrink to fit will not go under. `rule` draws one hairline, at the bottom
by default or directly under a named element with `"after": "text"`, which is where it belongs on
a quotation slide.

### How the fitting works

One scale factor drives every element on the slide. Each element wraps at the box width, honouring
any line breaks the copy already carries, and the whole set shrinks together until the block fits
the box. Shrinking only the headline is what lets a headline and a body drift apart until they
look like two different designs; shrinking together keeps the hierarchy the brand file asked for
at every size.

**This is the lesson the renderer was lifted from.** `Studio/bin/ort_design_render.py` records a
real failure in its own comments: a long title drew as one line, ran off both edges, and the body
was positioned from the first title line, so a three line title sat on top of its own body. Here
every element wraps, the block shrinks as a unit, and the layout is built from measured heights
rather than fixed offsets, so that shape of failure cannot recur. Prove it on your own brand file:

```bash
.venv/bin/python bin/carousel_render.py --brand YOURS.json --selftest out/selftest
```

That renders deliberately overlong text, in every theme the file holds, through every role, and
reports the clearance on each edge.

### The carousel file

```json
{
  "theme": "neutral",
  "slug": "my-carousel",
  "slides": [
    {"role": "cover", "text": "One claim, legible in two seconds."},
    {"role": "body",  "label": "1", "text": "A point.", "attrib": "A SOURCE"},
    {"role": "final", "text": "The takeaway.", "question": "A question?", "cta": "Do the thing."}
  ]
}
```

`\n` in any text is kept as a hard line break and the renderer wraps further from there.

---

## Fonts

Use fonts that exist on the machine you are rendering on. macOS keeps its own in
`/System/Library/Fonts/` and `/System/Library/Fonts/Supplemental/`. `index` picks the face inside
a `.ttc` collection, which holds several weights in one file; a `.ttf` has only index 0.

To see what a collection actually contains:

```bash
.venv/bin/python -c "from PIL import ImageFont; \
  [print(i, ImageFont.truetype('/System/Library/Fonts/Avenir Next.ttc', 40, index=i).getname()) \
   for i in range(12)]"
```

**If a client's real fonts are not installed, write the substitution into the brand file instead
of hiding it.** A set rendered in a stand-in face is off brand, and whoever looks at it next needs
to know that before they send it to the client.

---

## Contact sheets

Always build one, and always read it before anything leaves the machine.

```bash
# from folders or from an explicit list of PNGs
.venv/bin/python bin/carousel_render.py --contact-sheet out/SHEET.png --cols 10 out/my-carousel
```

The sheet is also the fastest check that two themes have not bled into each other: if each theme's
footer wordmark differs, a mis-themed slide stands out at thumbnail size without reading a word.

`--report OUT.json` writes the per slide measurements: role, scale, ink bounding box, clearance on
each edge, line counts, final pixel sizes and every contrast ratio tested.

---

## What it does not do

No images, no photographs, no logos, no gradients, no shadows. Flat colour, type and a hairline
rule. A brand that needs a logo on every slide needs that adding; the `panels` key is the hook it
would hang on and it is documented in the example file.
