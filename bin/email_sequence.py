#!/usr/bin/env python3
"""email_sequence.py: draft an email sequence as files, and leave the sending to a human.

WHY THIS EXISTS. `THE-GAP.md` scores email as the one capability in this kit with
absolutely nothing behind it: no file and no stub. A buyer who has a product and a list
still has to write five emails from a blank page, and that blank page is where most of
them stop. This writes the first draft of the whole sequence, with the spacing decided
and the purpose of each email stated, so the work left over is rewriting sentences
instead of inventing a structure.

IT WRITES FILES AND IT CANNOT SEND. There is no mail client in here, no outbound call of
any kind, no API key, no platform login, and no flag that turns sending on. That is a
deliberate limit and not an unfinished feature. A marketing kit that can send is a kit
that sends something wrong under somebody else's name: the wrong segment, last month's
price, a placeholder nobody filled in, at 4am. Wiring this to a sending platform is a
separate decision, made once, in the open, by the person whose name is on the email.
`TODO.md` item 5 says the same, and the house rule above it says drafts and a human yes.

WHAT IT CANNOT KNOW. It has the offer spec and nothing else. It does not know what a
customer actually said, what the refund terms are, which link works, what the first step
inside the product feels like, or how the sender writes when nobody is watching. So it
invents none of that. Wherever a result, a name, a number or a link belongs, it writes a
visible [FILL: ...] hole and counts the holes at the end. A draft with eleven holes is
doing its job: it has named the eleven sentences only the sender can write.

The register is plain and slightly flat on purpose. The measured voice is a separate tool
that does not exist yet (`TODO.md` item 2, `bin/brand_voice.py`), so until it does, read
every draft aloud and put your own sentences in. These are a structure and a first pass.

THE DEFAULT LENGTHS, and the reasoning for each. `welcome` is five, because a low ticket
buyer's attention runs out quickly and the whole job is getting the product used once.
`nurture` is six, because the problem has to be named before the offer can be made, and
the offer has to be made more than once before anybody acts on it. `launch` is seven,
spread either side of the open date, because a launch has a run up, an open and a close,
and the close does most of the selling. These counts are an editorial starting point.
Nothing in this repo has measured them. The moment a buyer has their own open and reply
figures, those figures replace these. `--emails N` trims any sequence from the end, and
the order is deliberate so that trimming loses the least.

Usage:
    python3 bin/email_sequence.py --offer specs/example-offer.json --shape welcome --out drafts/
    python3 bin/email_sequence.py --offer specs/example-offer.json --shape launch --out drafts/ --emails 4
"""
import argparse
import json
import re
import sys
import textwrap
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

GENERATOR = "bin/email_sequence.py"

# Written literally into the drafts. Mail platforms each use their own token, so the
# human swaps it once. Kept as a constant because it appears in every opening line.
TOKEN = "{{first_name}}"

UNSENT = ("**UNSENT AND UNAPPROVED DRAFT.** No sending platform has seen this file, and the "
          "tool that wrote it has no way to send anything. Read it, rewrite it in your own "
          "words, fill every hole, then send it yourself.")

HOLE = re.compile(r"\[FILL:\s*(.+?)\]", re.S)

# Dashes are written as escapes rather than characters because this source file has to
# pass BRAIN/bin/slop-lint.py too, and the linter is right to flag a literal one.
EM_DASH = "\u2014"
EN_DASH = "\u2013"
_DASH_RUN = re.compile(r"\s*[%s%s]\s*" % (EM_DASH, EN_DASH))
_DASH_BETWEEN_DIGITS = re.compile(r"(?<=\d)\s*[%s%s]\s*(?=\d)" % (EM_DASH, EN_DASH))


def die(msg):
    sys.exit("email_sequence.py: %s" % msg)


def plain(value):
    """Spec text with this kit's own writing rules applied to it.

    A buyer's offer spec will contain an em dash sooner or later, and a draft that
    carries one through fails the linter that every file leaving this machine has to
    pass. Fixing it at the boundary means the rule holds for text the tool did not
    write, which matters because the spec is the one input a stranger controls.
    """
    s = str(value).strip()
    s = _DASH_BETWEEN_DIGITS.sub(" to ", s)
    s = _DASH_RUN.sub(", ", s)
    return re.sub(r"\s+", " ", s)


def fill(hint):
    return "[FILL: %s]" % hint


def para(*blocks):
    """Join paragraphs with a blank line, wrapping prose and leaving lists alone."""
    out = []
    for b in blocks:
        if not b:
            continue
        b = b.rstrip()
        if "\n" in b or b.lstrip().startswith("- "):
            out.append(b)
        else:
            # break_long_words and break_on_hyphens both off, because the first run of
            # this split https://example.com/desk-reset/the-three-minute-fix across two
            # lines at the hyphen and handed a buyer a dead link.
            out.append(textwrap.fill(b, width=88, break_long_words=False,
                                     break_on_hyphens=False))
    return "\n\n".join(out)


def bullets(items, hint):
    return "\n".join("- %s" % i for i in items) if items else fill(hint)


def holes(text):
    return [re.sub(r"\s+", " ", m.group(1)).strip() for m in HOLE.finditer(text)]


def sentence(s):
    """A spec fragment, punctuated so that it can end a sentence.

    Buyers answer a spec in fragments: "watch the Start Here video, once". Dropped
    straight into a draft that reads as a missing full stop, and the first run of this
    tool produced five of them. A hole keeps its bracket and gets nothing added.
    """
    s = s.rstrip()
    if not s or s.endswith(("]", ".", "!", "?", ":", ";", '"')):
        return s
    return s + "."


def upfirst(s):
    """Capitalise a spec fragment that has ended up starting a paragraph."""
    return (s[:1].upper() + s[1:]) if s[:1].islower() else s


def head(value, limit, hint):
    """The first sentence of a spec value when it fits a subject line, or a hole.

    A subject cut off mid clause is the first thing the reader sees, and it reads as a
    bug. An early run of this put "The Desk Reset: Ten minutes a day that takes the" in
    front of a buyer. Asking the sender for a short version is the better failure.
    """
    s = plain(value)
    if s.startswith("[FILL:"):
        return fill(hint)
    first = re.split(r"(?<=[.!?])\s", s)[0].rstrip(".")
    return first if len(first) <= limit else fill(hint)


def quote(value, limit, hint):
    """A subject line that quotes the reader back to themselves, or a hole."""
    s = head(value, limit, hint)
    return s if s.startswith("[FILL:") else '"%s"' % s


def trim(s, limit):
    return s if len(s) <= limit else s[:limit - 3].rstrip() + "..."


def parse_date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def date_words(d):
    # %-d is not portable, so the day number is assembled by hand.
    return "%s %d %s" % (d.strftime("%A"), d.day, d.strftime("%B"))


class Offer:
    """The offer spec, with every read going through one place.

    Two reasons it is a class. Missing fields have to become visible holes rather than
    empty strings or the word None, and every value has to pass through plain() on the
    way out. Doing that at each use site is how one of them gets forgotten.
    """

    def __init__(self, data, path):
        self.data = data
        self.path = path

    def raw(self, dotted, default=None):
        cur = self.data
        for part in dotted.split("."):
            if not isinstance(cur, dict):
                return default
            cur = cur.get(part)
            if cur is None:
                return default
        return cur

    def say(self, dotted, hint):
        v = self.raw(dotted)
        if v is None or (isinstance(v, (str, list, dict)) and not v):
            return fill(hint)
        return plain(v)

    def listy(self, dotted):
        v = self.raw(dotted)
        if not isinstance(v, list):
            return []
        return [plain(x) for x in v if str(x).strip()]

    def first(self, dotted, hint):
        """The first item of a list field, or a hole.

        Objections and proof arrive as lists because a buyer has several. One email
        answers one objection, so the rest stay in the spec for the sender to rotate in.
        """
        items = self.listy(dotted)
        return items[0] if items else fill(hint)

    # The fields read often enough to earn a short name.
    @property
    def name(self):
        return self.say("name", "the name of the offer")

    @property
    def promise(self):
        return sentence(self.say("promise", "one sentence on what they end up with"))

    @property
    def short_audience(self):
        """The audience in two or three words, for a subject line or a mid sentence.

        A separate field because no tool can shorten a phrase like "people who sit at a
        desk for eight hours and have stopped expecting their shoulders to feel normal"
        without wrecking it. Cutting it to four words gave "Most people who sit at I
        talk to describe the same thing", which is how this field came to exist.
        """
        return self.say("audience_short", "your audience in two or three words")

    @property
    def audience(self):
        return self.say("audience", "who this is for, in their own words")

    @property
    def sender(self):
        return self.say("sender.name", "your name, as you sign off")

    @property
    def price(self):
        v = self.raw("price")
        return ("It costs %s." % plain(v)) if v else fill("the price, written the way the checkout writes it")

    @property
    def link(self):
        return self.say("links.product", "the checkout or product link")


@dataclass
class Draft:
    """One email. `day` is an offset from the shape's anchor and can be negative."""
    day: int
    slug: str
    purpose: str
    subject: str
    subject_alt: str
    body: str
    caution: str = ""


def welcome(o):
    """Five emails from the day of purchase.

    The sequence is built around consumption rather than thanks. A buyer who opens the
    product once keeps it and buys again, and a buyer who never opens it refunds and
    leaves. So three of the five push toward the first step, one asks for a sentence
    back, and only the last one sells anything.
    """
    first_step = o.say("first_step", "the single first thing a new buyer should do inside the product")
    access_where = o.say("access.where", "the login page or link where they get in")
    access_how = o.say("access.how", "how they get in: the password, the code, where the email came from")
    stall = o.say("stall", "the one place inside the product where people most often stop")
    next_name = o.say("next_step.name", "the name of the next thing you sell")
    # A placeholder in the first subject line is the one hole most senders will miss,
    # because the body is where the eye goes. When the next product has no name in the
    # spec, the subject falls back to one that works without it.
    knows_next = not next_name.startswith("[FILL:")

    return [
        Draft(
            day=0,
            slug="you-are-in",
            purpose="Get them through the door on the day they paid, while they still care.",
            subject="You are in: %s" % o.name,
            subject_alt="Your access to %s, inside" % o.name,
            body=para(
                "%s, your payment went through and %s is open to you." % (TOKEN, o.name),
                "Where to go: %s" % access_where,
                "How to get in: %s" % access_how,
                "Before you close this tab, do one thing: %s" % sentence(first_step),
                "That is the whole first step. The rest of it can wait until tomorrow.",
                "If the link does not work, hit reply and say so.",
                o.sender,
            ),
        ),
        Draft(
            day=1,
            slug="did-you-get-in",
            purpose="Get the first real use. The day after buying is when people mean to start and then do not.",
            subject="Did you get in?",
            subject_alt="One step, then you can close the laptop",
            body=para(
                "Yesterday you picked up %s. This is the nudge." % o.name,
                "The first step again, in case that email got buried: %s" % sentence(first_step),
                access_where,
                "If something stopped you, tell me what it was. Two words is enough. Broken "
                "link, no time, no idea where to start. I can fix the first one and help with "
                "the other two.",
                o.sender,
            ),
        ),
        Draft(
            day=3,
            slug="where-people-stall",
            purpose="Name the place people quit, a day or two before they quit there.",
            subject="The part people get stuck on",
            subject_alt="The place most people stop",
            body=para(
                "There is one place inside %s where people stop: %s" % (o.name, sentence(stall)),
                fill("what to do about it, in two or three sentences. You know this answer "
                     "better than any tool does"),
                "If you are already past it, ignore me and carry on.",
                o.sender,
            ),
        ),
        Draft(
            day=7,
            slug="a-week-in",
            purpose="Ask for one sentence. A real buyer's own words beat a survey, and they are the first draft of your next sales page.",
            subject="A week in: what happened?",
            subject_alt="Can I ask you one thing?",
            body=para(
                "It has been a week since you picked up %s." % o.name,
                "One question, and one line back is plenty: what has changed, if anything?",
                "I ask because the answers decide what gets built next, and because the "
                "sentence you write back is usually sharper than anything I would write about "
                "this myself.",
                o.sender,
                "P.S. If nothing has changed because you have not started, that is a useful "
                "answer too. Say so and I will send you the shortest way in.",
            ),
        ),
        Draft(
            day=14,
            slug="what-comes-next",
            purpose="Offer the next thing once, to the people who actually used the first one.",
            caution="Send this only to buyers who opened the product. Selling step two to "
                    "somebody who never opened step one is how a list learns to ignore you. "
                    "If you cannot segment on that yet, cut this email.",
            subject=("%s, if %s worked for you" % (next_name, o.name) if knows_next
                     else "What comes after %s" % o.name),
            subject_alt=("What comes after %s" % o.name if knows_next
                         else fill("a sharper one: the name of the next thing you sell")),
            body=para(
                "Two weeks ago you bought %s. If it did what it said it would, there is a next "
                "step: %s." % (o.name, next_name),
                sentence(o.say("next_step.promise", "one sentence on what the next thing does for them")),
                sentence(o.say("next_step.price", "the price of the next thing")),
                o.say("next_step.link", "the link to the next thing"),
                "If %s did not do what it said, reply and tell me. %s"
                % (o.name, fill("your refund terms in one sentence, or delete this line")),
                o.sender,
            ),
        ),
    ]


def nurture(o):
    """Six emails from the day they signed up and did not buy.

    The order is the argument. Deliver the free thing, name the problem, show it
    happening to somebody specific, answer the objection out loud, then state the offer
    plainly and once. The sixth exists so the people who are never buying can leave
    cleanly, because a smaller list that wants to hear from you costs less to mail.
    """
    free_thing = o.say("free_thing", "the thing they signed up to get")
    free_link = o.say("links.free_thing", "the link or attachment for the free thing")
    objection = o.first("objections", "the objection you hear most often, in their words")

    return [
        Draft(
            day=0,
            slug="here-is-the-thing-you-asked-for",
            purpose="Deliver what they signed up for inside a minute, and ask nothing of them.",
            subject="Here is %s" % free_thing,
            subject_alt="%s, as promised" % upfirst(free_thing),
            body=para(
                "%s, here is %s: %s" % (TOKEN, free_thing, free_link),
                "That is the whole email. Nothing else to click.",
                "Over the next two weeks I will send you a handful of emails on the same "
                "subject. If that is nothing you want, the unsubscribe link at the bottom "
                "works and I will hold no grudge about it.",
                o.sender,
            ),
        ),
        Draft(
            day=2,
            slug="the-problem",
            purpose="Name the problem in their own words, so they can tell this list is about them.",
            subject="What most %s run into" % o.short_audience,
            subject_alt=fill("a sharper one: the problem itself, in six words or fewer"),
            body=para(
                "Most %s I talk to describe the same thing." % o.short_audience,
                fill("the problem in their own words. Lift a real sentence out of a real "
                     "conversation and quote it. A paraphrase reads like a paraphrase"),
                fill("your read on what is actually going on underneath it, three sentences"),
                "What I think the fix looks like: %s" % o.promise,
                "More on that in a couple of days.",
                o.sender,
            ),
        ),
        Draft(
            day=4,
            slug="a-worked-example",
            purpose="Show the problem happening to somebody specific. A worked case does the arguing for you.",
            subject="A worked example",
            subject_alt=fill("a sharper one: the example in six words, along the lines of "
                             "'the call that cost Dana a client'"),
            body=para(
                "One specific case, because the general version of this argument convinces "
                "nobody.",
                fill("one real example, about 150 words. Who, what they tried, what happened, "
                     "what it cost them. Change the name if you have to. Do not make it up: an "
                     "invented example reads as invented, and the people who spot it are the "
                     "ones who would have bought"),
                "What that case has in common with most %s: %s"
                % (o.short_audience, fill("one sentence")),
                o.sender,
            ),
        ),
        Draft(
            day=7,
            slug="the-objection",
            purpose="Answer the thing that stops people, three days before the email that asks for money.",
            subject=quote(objection, 58, "the objection in their words, short enough for a subject line"),
            subject_alt="The straight answer to that",
            body=para(
                "The most common thing I hear about %s is this: %s" % (o.name, sentence(objection)),
                "The straight answer: %s"
                % fill("your answer. Where the objection is sometimes right, say when it is "
                       "right. Pretending otherwise costs you the sale and the trust"),
                o.sender,
            ),
        ),
        Draft(
            day=10,
            slug="the-offer",
            purpose="State the offer once, in full, with the price and the link. People who want it have to be able to buy it.",
            caution="This is the first email in the sequence that asks for money. Open the "
                    "link yourself, in a browser you are not logged into, and check the price "
                    "on the page matches the price in this email.",
            subject="What %s is, and what it costs" % o.name,
            subject_alt="%s: %s" % (o.name, head(o.promise, 46,
                                    "a sharper one: the promise in eight words")),
            body=para(
                "I have been writing about the same problem for a week. Here is the thing I "
                "built for it.",
                "%s. %s" % (o.name, o.promise),
                "What is in it:",
                bullets(o.listy("deliverables"),
                        "list what they actually get, one line each"),
                "Who it is for: %s" % sentence(o.audience),
                "Who should skip it: %s" % sentence(o.say("not_for", "who this is wrong for")),
                o.price,
                o.link,
                "Reply with questions and I will answer them.",
                o.sender,
            ),
        ),
        Draft(
            day=14,
            slug="last-word",
            purpose="Close the sequence and let the people who are never buying leave cleanly.",
            subject="Last one about %s" % o.name,
            subject_alt="I will stop talking about this now",
            body=para(
                "This is the last email in this run about %s." % o.name,
                "Short version: %s %s %s" % (o.promise, o.price, o.link),
                "If it is wrong for you, nothing happens next and that is fine. You stay on "
                "the list for %s and you can leave any time with the link at the bottom."
                % fill("what you actually send from here, and how often"),
                o.sender,
            ),
        ),
    ]


def launch(o):
    """Seven emails around an open date, so day zero is the day the doors open.

    Days here are negative before the open, which is the only honest way to describe a
    launch: the dates are fixed in advance and the list has to be warmed before them.
    The close does most of the selling, so the last three emails all point at it.
    """
    opens = parse_date(o.raw("opens_on"))
    closes = parse_date(o.raw("closes_on"))
    open_day = date_words(opens) if opens else fill("the date it opens")
    close_day = date_words(closes) if closes else fill("the date it closes")
    objection = o.first("objections", "the objection you hear most often, in their words")
    deliverables = bullets(o.listy("deliverables"), "list what they get, one line each")

    return [
        Draft(
            day=-7,
            slug="save-the-date",
            purpose="Put the date in front of them before any selling starts, so the open day is expected.",
            subject="%s opens %s" % (o.name, open_day),
            subject_alt="Something opening on %s" % open_day,
            body=para(
                "%s, on %s I am opening %s." % (TOKEN, open_day, o.name),
                o.promise,
                "Nothing to do today. I am telling you now so it is no surprise, and so you "
                "can decide in your own time instead of against a deadline.",
                "Who it is for: %s" % sentence(o.audience),
                "If this is nothing you want to hear about, the unsubscribe link works and I "
                "will hold no grudge.",
                o.sender,
            ),
        ),
        Draft(
            day=-3,
            slug="the-problem",
            purpose="Make the case for the problem while nothing is yet for sale.",
            subject="Before %s opens, the problem" % o.name,
            subject_alt=fill("a sharper one: the problem itself, in six words or fewer"),
            body=para(
                "%s opens on %s. Before then, the problem it is built against."
                % (o.name, open_day),
                fill("the problem, about 150 words, with one specific case inside it. The "
                     "version of this that works names somebody and what it cost them"),
                "That is what %s is for. %s" % (o.name, o.promise),
                o.sender,
            ),
        ),
        Draft(
            day=-1,
            slug="tomorrow",
            purpose="Last email before the doors open. Put the time, the price and the exclusions here so tomorrow's email can be two lines.",
            subject="Tomorrow: %s" % o.name,
            subject_alt="%s opens tomorrow" % o.name,
            body=para(
                "%s opens tomorrow, %s, at %s"
                % (o.name, open_day,
                   fill("the time, with the time zone spelled out. People in other zones will ask")),
                "Everything about it is here, so tomorrow's email can be short.",
                deliverables,
                o.price,
                "It closes on %s." % close_day,
                "Who should skip it: %s" % sentence(o.say("not_for", "who this is wrong for")),
                o.sender,
            ),
        ),
        Draft(
            day=0,
            slug="open",
            purpose="The doors are open. This email has one job and should stay short.",
            caution="Click the buy link yourself before this goes out, from a browser you are "
                    "not logged into, and put a card through it if your platform has a test "
                    "mode. An open email with a broken checkout is the most expensive email "
                    "in the sequence.",
            subject="%s is open" % o.name,
            subject_alt="Doors are open: %s" % o.name,
            body=para(
                "%s is open. %s" % (o.name, o.link),
                o.promise,
                "%s It closes on %s." % (o.price, close_day),
                o.sender,
            ),
        ),
        Draft(
            day=2,
            slug="the-objection",
            purpose="Answer the thing stopping the people who read the open email and did not buy.",
            subject=quote(objection, 58, "the objection in their words, short enough for a subject line"),
            subject_alt="The question I keep getting about %s" % o.name,
            body=para(
                "%s has been open two days and the same question keeps coming in: %s"
                % (o.name, sentence(objection)),
                "Straight answer: %s"
                % fill("your answer. Where the objection is fair, say that it is fair"),
                "It closes on %s. %s" % (close_day, o.link),
                o.sender,
            ),
        ),
        Draft(
            day=4,
            slug="who-should-skip-it",
            purpose="Say out loud who should not buy. It costs a few sales and prevents the refunds, and the people who stay trust the next launch.",
            subject="Who %s is wrong for" % o.name,
            subject_alt="Do not buy this if",
            body=para(
                "%s closes on %s. Before it does, who should skip it." % (o.name, close_day),
                upfirst(sentence(o.say("not_for", "who this is wrong for"))),
                fill("anything else that makes this the wrong purchase. Be specific enough "
                     "that somebody recognises themselves and closes the tab"),
                "If none of that is you: %s" % o.link,
                o.sender,
            ),
        ),
        Draft(
            day=6,
            slug="last-call",
            purpose="Last call on the closing day. Most of a launch lands here, and the only reason it works is that the deadline is real.",
            caution="Send this only if the thing genuinely closes. A deadline that passes "
                    "without closing teaches your list to ignore the next one, and they do.",
            subject="%s closes tonight" % o.name,
            subject_alt="Last call: %s" % o.name,
            body=para(
                "%s closes tonight at %s"
                % (o.name, fill("the time, with the time zone spelled out")),
                o.promise,
                o.price,
                o.link,
                "After tonight: %s"
                % fill("what actually happens. Does it reopen, and when? Say which"),
                o.sender,
            ),
        ),
    ]


SHAPES = {
    "welcome": {
        "build": welcome,
        "anchor": "the day they bought",
        "reader": "somebody who has just bought a low ticket product",
    },
    "nurture": {
        "build": nurture,
        "anchor": "the day they signed up",
        "reader": "somebody who signed up and has not bought",
    },
    "launch": {
        "build": launch,
        "anchor": "the day it opens, so a negative day is before the open",
        "reader": "a list being warmed for something opening on a date",
    },
}

REQUIRED = ("name", "promise", "audience")


def load_offer(path):
    p = Path(path)
    if not p.exists():
        die("no offer spec at %s. Copy specs/example-offer.json and edit it." % p)
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        die("%s is not valid JSON: %s" % (p, e))
    if not isinstance(data, dict):
        die("%s should be a JSON object with a name, a promise and an audience." % p)
    missing = [k for k in REQUIRED if not str(data.get(k) or "").strip()]
    if missing:
        die("%s is missing %s. Those are among the only three fields with no sensible "
            "hole, because without them every subject line in the sequence would be a "
            "placeholder. Everything else can be left out."
            % (p, " and ".join(missing)))
    return Offer(data, str(p))


def anchor_date(shape, offer):
    """The real calendar date day zero lands on, when the spec knows it.

    Only launch has one, because an open date is a fact in the spec. A purchase or a
    signup happens whenever the person does it, so those stay relative.
    """
    if shape == "launch":
        return parse_date(offer.raw("opens_on"))
    return None


def cell(s):
    """A pipe inside a markdown table cell ends the cell. Subject lines contain pipes."""
    return plain(s).replace("|", r"\|")


def render_md(n, total, d, shape, today, zero):
    when = "day %d, counted from %s" % (d.day, SHAPES[shape]["anchor"])
    if zero:
        when += " (%s)" % date_words(zero + timedelta(days=d.day))
    found = holes(d.body) + holes(d.subject) + holes(d.subject_alt)

    lines = [
        "<!-- UNSENT DRAFT written by %s on %s. Nothing has sent this. -->" % (GENERATOR, today),
        "",
        "# Email %d of %d, %s sequence" % (n, total, shape),
        "",
        "> %s" % UNSENT,
        "",
        "| | |",
        "|---|---|",
        "| **Sends** | %s |" % cell(when),
        "| **This email is for** | %s |" % cell(d.purpose),
        "| **Subject** | %s |" % cell(d.subject),
        "| **Subject, alternative** | %s |" % cell(d.subject_alt),
        "",
    ]
    if d.caution:
        lines += ["## Check this first", "", textwrap.fill(plain(d.caution), width=88), ""]
    lines += ["## Body", "", d.body, "", "## Before you send", ""]
    plural = "" if len(found) == 1 else "s"
    many = "one" if len(found) == 1 else str(len(found))
    checks = ["Swap `%s` for whatever token your platform uses." % TOKEN,
              "Read the body aloud once. Anything you would not say out loud, cut.",
              "Check every link by clicking it."]
    if found:
        checks.append("Fill the %s hole%s listed below." % (many, plural))
    checks.append("This file stays a draft until you paste it into a platform yourself.")
    lines += ["- %s" % c for c in checks] + [""]
    if found:
        lines += ["### The %s hole%s" % (many, plural), "",
                  "Nothing else in this draft claims anything that was not already in your "
                  "offer spec. These are the sentences only you can write.", ""]
        lines += ["- %s" % h for h in found] + [""]
    return "\n".join(lines), found


def write_sequence(drafts, offer, shape, out, today):
    out.mkdir(parents=True, exist_ok=True)
    zero = anchor_date(shape, offer)
    index, total_holes = [], 0
    for i, d in enumerate(drafts, 1):
        text, found = render_md(i, len(drafts), d, shape, today, zero)
        fname = "%02d-day%s-%s.md" % (i, ("minus%d" % -d.day) if d.day < 0 else d.day, d.slug)
        (out / fname).write_text(text)
        total_holes += len(found)
        index.append({
            "n": i,
            "file": fname,
            "day": d.day,
            "send_date": str(zero + timedelta(days=d.day)) if zero else None,
            "for": plain(d.purpose),
            "subject": plain(d.subject),
            "subject_alt": plain(d.subject_alt),
            "caution": plain(d.caution) if d.caution else None,
            "words": len(re.findall(r"[\w'-]+", d.body)),
            "holes": found,
        })

    meta = {
        "_unsent": ("Every file beside this one is an unsent, unapproved draft. The tool that "
                    "wrote them cannot send mail, has no platform credentials and makes no "
                    "outbound calls. Sending is a human act performed somewhere else."),
        "_help": ("An index of the drafts in this folder, in send order. Edit the markdown "
                  "files, keep this file as the record of what was generated and when. "
                  "Regenerating overwrites the markdown, so it demands --force once the "
                  "folder has drafts in it."),
        "generated_by": GENERATOR,
        "generated_on": str(today),
        "shape": shape,
        "written_for": SHAPES[shape]["reader"],
        "day_zero_is": SHAPES[shape]["anchor"],
        "day_zero_date": str(zero) if zero else None,
        "offer": {"name": plain(offer.name), "spec": offer.path},
        "emails": index,
        "holes_to_fill": total_holes,
        "approved": False,
        "sent": False,
    }
    (out / "sequence.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False) + "\n")
    return meta


def report(meta, out):
    print("\n%s sequence, %d emails, for %s"
          % (meta["shape"], len(meta["emails"]), meta["written_for"]))
    print("  day zero is %s" % meta["day_zero_is"])
    if meta["day_zero_date"]:
        print("  which the spec dates at %s" % meta["day_zero_date"])
    print("")
    for e in meta["emails"]:
        flag = "!" if e["caution"] else " "
        print("  %s %2d  day %-4s %3d words  %2d to fill  %s"
              % (flag, e["n"], e["day"], e["words"], len(e["holes"]),
                 trim(e["subject"], 52)))
        print("        for: %s" % e["for"])
    cautions = [e for e in meta["emails"] if e["caution"]]
    if cautions:
        one = len(cautions) == 1
        print("\n  %d email%s %s a check to do before sending, marked ! above."
              % (len(cautions), "" if one else "s", "carries" if one else "carry"))
    print("\n  %d holes to fill across the sequence. Every one of them is a sentence only you "
          "can write." % meta["holes_to_fill"])
    print("  wrote %d files into %s" % (len(meta["emails"]) + 1, out))
    print("\n  NOTHING WAS SENT. This tool has no way to send mail and no platform login. "
          "These are files on your disk.\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offer", required=True, help="the offer spec JSON, see specs/example-offer.json")
    ap.add_argument("--shape", required=True, choices=sorted(SHAPES),
                    help="welcome: they just bought. nurture: they signed up and did not buy. "
                         "launch: a thing opens on a date")
    ap.add_argument("--out", required=True, help="folder to write the drafts into")
    ap.add_argument("--emails", type=int, help="keep only the first N of the sequence")
    ap.add_argument("--force", action="store_true",
                    help="overwrite drafts already in the output folder")
    a = ap.parse_args()

    offer = load_offer(a.offer)
    out = Path(a.out)
    existing = sorted(out.glob("*.md")) if out.is_dir() else []
    if existing and not a.force:
        # These files are meant to be edited by hand. Silently replacing somebody's
        # rewritten copy with a fresh draft is the one unrecoverable thing this tool
        # could do to a day's work.
        die("%s already holds %d draft%s. Move them, or pass --force to replace them."
            % (out, len(existing), "" if len(existing) == 1 else "s"))

    drafts = SHAPES[a.shape]["build"](offer)
    if a.emails is not None:
        if a.emails < 1:
            die("--emails has to be at least 1")
        if a.emails > len(drafts):
            print("  only %d emails in the %s shape, so --emails %d gives you all of them"
                  % (len(drafts), a.shape, a.emails))
        drafts = drafts[:a.emails]

    meta = write_sequence(drafts, offer, a.shape, out, date.today())
    report(meta, out)


if __name__ == "__main__":
    main()
