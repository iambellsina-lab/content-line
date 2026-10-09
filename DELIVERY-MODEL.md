# How the system reaches a buyer

Three shapes. Researched 2026-10-02 against GoHighLevel's own pricing, help pages and terms of service.
Written for whoever is deciding how to sell this, not for any one business.

> **This page is about the CRM and support side of reselling. It is not the whole delivery question.**
> Two things settled later and they live in `HOSTING-AND-PACKAGING.md`:
>
> - **What shape the kit itself ships in.** Bella decided it on 2026-10-08 and `DECISIONS.md` carries it
>   as KIT-1: the buyer installs it and it runs on their machine, not hosted. That page recommends a
>   Claude Code plugin as the cheapest build of that shape, and states the case against it.
> - **How a finished clip reaches a scheduler**, which takes media by public address rather than as a
>   file. The recommendation is GitHub Releases, with the one check that still needs Bella's yes.
>
> Everything below still applies to shapes 2 and 3, and the terms-of-service finding is the part to read
> before becoming anybody's support desk.

---

## The three shapes

| | What the buyer gets | What the seller carries |
|---|---|---|
| **1. Kit only** | Files. They bring their own scheduler and their own CRM | Nothing ongoing. One-time sale |
| **2. Kit plus a sub-account** | A GoHighLevel sub-account inside the seller's agency, which they connect their own socials to | Unlimited sub-accounts on the $297 tier. **Contractual support liability** |
| **3. Kit plus SaaS Mode** | Self-serve signup, auto-provisioning, feature gating, billed by the seller's Stripe | **$497/mo Agency Pro minimum.** Everything in 2, plus billing operations |

---

## The finding that most changes the decision

**Shape 2 does not need SaaS Mode.** The thing that makes a reseller model work technically is the
**sub-account boundary**: each buyer connects their own social accounts inside their own sub-account, so
the seller never holds anyone else's tokens, never files Meta App Review, never does Business
Verification, and never becomes a multi-tenant platform operator.

SaaS Mode is a **billing and self-serve provisioning layer bolted on top of that**. Nothing in
GoHighLevel's documentation says a sub-account must be in SaaS Mode to exist, to have a Social Planner,
or to connect its own socials.

**Proven on a live account 2026-10-02:** a sub-account with `"saasMode": "not_activated"` had **8 social
accounts connected and working** across two brands.

So these are two separate decisions, and the second one is where the obligations live.

---

## The tiers, from GoHighLevel's own pricing page

| Plan | Price | Sub-accounts | SaaS Mode |
|---|---|---|---|
| Starter | $97/mo | **3** | No |
| Unlimited | $297/mo | Unlimited | **No** |
| **Agency Pro** | **$497/mo** | Unlimited | **Yes** |
| Enterprise | custom | custom | custom |

**Verify the plan before costing any of this.** "Highest tier" is not a plan name. The sub-account API
reports whether SaaS Mode is active; it does not report which agency plan sits above it. Read Agency
Settings then Billing and quote the actual plan name.

---

## The money risk, and it is smaller than it looks for this product

From GoHighLevel's pricing guide, verbatim:

> "HighLevel charges your Agency card on file. When a supported service is used, the charge is deducted
> from the Agency Wallet."
>
> "HighLevel charges the agency first through the Agency Wallet. When rebilling is enabled, the
> sub-account is then charged for the usage it generated."

**Read that twice. Every buyer's SMS, email, phone and AI usage hits the seller's card first.**
Rebilling is cost **recovery**, not cost **avoidance**. And: *"LC Services will be temporarily halted if
the Wallet goes negative."*

Rebilling without markup needs the $297 plan. **Rebilling with markup is $497 only.** The default markup
is 1.05x "to cover your Stripe charges", and the activation page warns: *"Agencies must not add their
own card here. It needs to be your client's card."*

**Why it is probably small here:** a buyer who only schedules social posts is a near-zero-usage tenant.
Social Planner posting appears in no rebillable-service list. **Why it is not zero:** the buyer gets a
whole CRM. If they discover the SMS and AI tools bundled in the tier they were sold, the first invoice
lands on the seller.

---

## The real cost is not the $497. It is the terms of service

From `gohighlevel.com/terms-of-service`, Section 2, Resale Restrictions:

> "When reselling access to the Platform, you agree that you are **fully liable to your customers** for
> their access to and use of the Platform, and you are **solely responsible for the resolution of all
> customer disputes and inquiries**."

And, same section:

> "You **may not direct your customers to contact HighLevel for any reason**, including but not limited
> to Platform support."

And Section 1:

> "You are fully responsible for the use of the Platform by your customers."

**Translated: the seller becomes the entire support desk, contractually, with no escalation path.**
A buyer whose Instagram connection expires at 11pm cannot be sent to GoHighLevel. They come to you.

**That is the decision, and it is not a money decision.** It is whether the seller has the hours and the
appetite to be somebody else's infrastructure. For anyone running this alongside another full-time
commitment, that question answers itself.

---

## One hard rule

**Never convert a working sub-account to SaaS Mode.** From GoHighLevel's own conversion page: once
switched, the sub-account *"will only have access to the features enabled in that tier"*, a plan must be
assigned, and *"If a payment method is not available when the plan is assigned, the selected plan remains
On Hold"*, which puts a lockout screen in front of the user.

Switching a sub-account that already runs live brands risks gating those brands behind a tier and losing
access to their connected social accounts. Activation is per-sub-account and opt-in, so turning SaaS
Mode on at agency level does not disturb existing sub-accounts. Converting one does.

---

## The recommendation

**Start at shape 1, and offer shape 2 by hand to the first few buyers.**

Shape 1 has no ongoing obligation and tests whether the kit is any good. Shape 2 can be done on the
$297 tier with no SaaS Mode at all, provisioned manually, which is fine at single digits of buyers and
tells you what support actually costs before you are contractually committed to it at scale.

**Shape 3 is a software business.** It is a reasonable thing to become, and it should be a decision
rather than a side effect of wanting to help people get started.
