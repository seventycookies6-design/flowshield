# FlowShield — legal exposure checklist

**This is not legal advice, and nothing here makes FlowShield lawsuit-proof.**
Anyone can sue anyone. What this document does is list the ways consumer
software and its website actually get sued, fined or forced to refund, check
FlowShield against each one, and say plainly what is done, what is missing and
what only a lawyer or the owner can decide. Reviewed against the code, the site
and the Stripe setup on **17 September 2026**.

Two facts shape everything below:

- **Nothing is live yet.** Stripe is in test mode, so there are no real
  customers, no real money and no real personal data. Every gap here is cheap
  to fix now and expensive to fix after the first sale.
- **The most dangerous risk in this product is not privacy or payments.** It is
  that **FlowShield closes running programs**, and someone will lose unsaved
  work. Most of the legal work below exists to make that risk understood and
  agreed to before it happens.

## How to use this

Run through **every** section before each of these:

1. Publishing a release (`tools/build_release.ps1`).
2. Publishing the site (`tools/publish_site.ps1`).
3. Turning on live Stripe keys.
4. Adding any feature that collects, sends or stores anything new.

`CLAUDE.md` makes this a rule for every agent. Some items are checked
automatically by tier 5 tests (marked **automated**), so a regression fails CI
rather than reaching a customer.

Status key: **OK** = done and verified · **GAP** = must fix before launch ·
**OWNER** = needs Keenan's decision, money, or a professional.

---

## 1. Who is selling this (trader identity)

| # | Item | Status |
| --- | --- | --- |
| 1.1 | A named legal seller (person or company) with an address on the site | **GAP / OWNER** — `legal.html` still says `[operator name]`, `[registered address]`, `[support email]`, and `support.html` says `[support email]` |
| 1.2 | Same identity on the Stripe receipt and checkout page | **GAP / OWNER** — Stripe business profile is still incomplete; checkout has shown "Focus Unlock sandbox" |
| 1.3 | Decide whether to trade as yourself or form an LLC | **OWNER** |

**Why it matters.** EU and UK consumer law requires the trader's identity and
address to be given before the purchase, and US states' deceptive-practice laws
treat a hidden seller badly. Selling without it is also the fastest way for a
chargeback to be decided against you.

**What "good" looks like:** a real name or company, a real postal address (a
registered-agent or virtual address is fine for a sole trader who doesn't want
their home address public), and one support email that a person reads.

**Trading as yourself works legally, but it means personal liability.** An LLC
(a few hundred dollars) is the usual way an indie developer keeps a customer's
claim away from their own savings. That is a judgement call about how much
money is at stake, not something I can decide.

---

## 2. Getting the terms agreed (this is the big one)

| # | Item | Status |
| --- | --- | --- |
| 2.1 | Terms, privacy and refund policy exist and are readable | **OK** — `Website/legal.html`, linked from every page footer (tier 5 checks the links) |
| 2.2 | The customer actively agrees before buying | **OK** — Stripe Checkout requires the terms box (`consent_collection`), with custom wording naming the closing-programs risk; Stripe stores the agreement with the payment. If the Stripe account has no terms-of-service URL yet, the sale still completes without the box and `/health` reports `termsConsent.working: false` — **OWNER: set that URL in Stripe → Settings → Checkout** |
| 2.3 | The customer agrees before the software can close anything | **OK** — a gate over every page on first launch: what FlowShield closes, links to the terms and privacy policy, and **I understand and agree**. No sprint can start until it's accepted, enforced in the view model, not only by the overlay |
| 2.4 | A record of who agreed, to which version, and when | **OK** — `TermsAcceptedVersion` and `TermsAcceptedUtc` in the encrypted settings, saved before the gate closes; shown on the Settings page |
| 2.5 | Terms are versioned and dated | **OK, automated** — `LegalTerms.Version` and the legal page carry the same version; a tier 1 test keeps them equal, and bumping the version re-asks everyone |

**Why it matters.** Disclaimers only protect you if the customer agreed to
them. Courts routinely enforce "clickwrap" (a box you tick or a button that
says you agree, next to a visible link) and routinely refuse "browsewrap" (a
link in the footer nobody had to look at). FlowShield was browsewrap until
#108, which means the liability limit in the terms now rests on something a
customer actually did.

**What's left here:** the Stripe account needs a terms-of-service URL
(`https://seventycookies6-design.github.io/flowshield/legal.html#terms`) set in
**Settings → Checkout**, or the consent box is skipped. `/health` says which.

**When the terms change materially:** bump `LegalTerms.Version`, update the
version line on `legal.html`, and everyone is asked again — that is what keeps
each recorded acceptance tied to wording the person actually saw.

---

## 3. What the product claims (advertising accuracy)

| # | Item | Status |
| --- | --- | --- |
| 3.1 | No feature is advertised that the build doesn't have | **OK, automated** — tier 5 `TestWebsiteClaimsMatchTheApp`, plus the changelog/limits tests added in #90 and #102 |
| 3.2 | "No analytics, telemetry, tracking pixels or advertising" is true | **OK** — no analytics anywhere in `Website/` or the app; worth an automated guard |
| 3.3 | "We never see or store your card details" is true | **OK** — Stripe Checkout only; the server stores ids, not cards |
| 3.4 | "Plus sales tax where it applies, shown at checkout" is true | **OK** — the sentence is gone; the pricing card says "The price you see is the price you pay." Stripe Tax is still off, and tier 5 fails if either side changes without the other |
| 3.5 | Competitor comparisons are accurate and dated | **OK for now** — the site names no competitor; `LAUNCH_FEATURE_CHECKLIST.md` requires re-checking a source before any claim (F24's "$30–$60 a year" line is unnamed and safe) |
| 3.6 | Screenshots show the real product | **OK** — the screenshots and the recording are captures of the shipped build with invented sample data, labelled as such on the page (F27, #139); tier 5 pins the claim |
| 3.7 | No fake reviews, fake testimonials or invented user counts | **OK** — none on the site. **Never add any**: the FTC's 2024 rule makes fake reviews individually finable |

**Why it matters.** This is the most common way a small software business gets
into trouble: not a lawsuit, but a deceptive-advertising complaint, a
chargeback, or an app store/payment processor closing the account. FTC Act
penalties run to about **$53,000 per violation**.

---

## 4. Refunds, cancellation and EU/UK withdrawal

| # | Item | Status |
| --- | --- | --- |
| 4.1 | A refund policy on the site, before purchase | **OK** — 14 days, no reason needed |
| 4.2 | Refunds are actually honoured and revoke the licence | **OK** — `charge.refunded` webhook plus a PaymentIntent re-check in `/validate` |
| 4.3 | No subscription traps (nothing auto-renews) | **OK** — one-time purchase; no auto-renewal law applies |
| 4.4 | EU/UK 14-day withdrawal right is honoured | **Partly** — the policy says the statutory right applies, which is right, and the 14-day refund matches it |
| 4.5 | Withdrawal waiver for instant access | **GAP** — EU rules let you ask the buyer to agree that supply begins immediately and they lose the withdrawal right. FlowShield doesn't ask, so a buyer keeps the full right. That's safe but costly; if you'd rather have the waiver, it goes in the checkout consent from 2.2 |
| 4.6 | Refund requests reach a person | **GAP / OWNER** — depends on the support email in 1.1 |

---

## 5. Privacy and data protection

| # | Item | Status |
| --- | --- | --- |
| 5.1 | A privacy policy that matches the code | **Mostly OK** — but see 5.2 |
| 5.2 | Every piece of personal data is disclosed | **OK** — the policy discloses the device identifier (a one-way hash of a Windows installation id) and the device name (`MachineName (UserName)`, which often contains a real name), and the site's FAQ says the same |
| 5.3 | Blocklists, sessions and journals stay local | **OK** — DPAPI-encrypted in `%APPDATA%`, never uploaded; tier 3 proves the file is encrypted |
| 5.4 | Access, correction and deletion requests answered | **Partly** — the policy promises 30 days; there's no process or tooling yet. F23 ("Your data") covers the app side |
| 5.5 | Named subprocessors | **OK** — the policy names Stripe, Inc., Render Services, Inc. and Resend (Plus Five Five, Inc.) with their roles; tier 5 checks all three are there |
| 5.6 | Retention periods | **OK** — the policy gives periods: the licence record while the licence exists plus 7 years for tax and accounting, device rows removed on deactivation, payment records under Stripe's own retention |
| 5.7 | EU representative (GDPR Article 27) | **OWNER** — required for a non-EU seller that targets EU consumers. Services cost roughly €200–500/year. The alternative is to **not sell to the EU**, which is a business decision, not a technical one |
| 5.8 | Cookie/consent banner | **OK, and don't add one** — the site sets no cookies; it stores only a theme choice in `localStorage`, which is a user preference, not tracking |
| 5.9 | Data breach plan | **GAP** — no documented steps. Minimum: who is told, in what order, within 72 hours for EU data |

**The device name is the sharpest edge here.** "KEENAN-PC (Keenan)" is personal
data under GDPR. Options, cheapest first: stop sending the name and show the
customer a shortened device id instead; or let the customer rename a device;
or disclose it plainly in the policy. I'd do the first.

---

## 6. Children

| # | Item | Status |
| --- | --- | --- |
| 6.1 | Not directed at under-13s | **OK** — the product is a paid Windows focus timer, marketed to students and gamers |
| 6.2 | No knowing collection of under-13 data | **OK** — email plus a device id, only at purchase |
| 6.3 | Terms state a minimum age | **OK** — the terms say "You must be at least 13 years old to buy or use FlowShield, or older if your country sets a higher age for agreeing to online services on your own"; tier 5 checks it |
| 6.4 | Marketing never targets children | **OWNER** — this is about where you advertise. Anything aimed at parents buying it *for* a child changes the analysis, and would also be a false claim today (see 9.3) |

COPPA penalties are about **$53,000 per violation**, so the cheap move is to
stay clearly outside it.

---

## 7. Accessibility

| # | Item | Status |
| --- | --- | --- |
| 7.1 | Website meets WCAG 2.1 AA | **Partly** — roadmap 6.7 (#73) did a pass; no audit since |
| 7.2 | App is keyboard-navigable with screen-reader names | **Partly** — every control has an AutomationId and most have names (F21 covers the rest) |
| 7.3 | Contrast passes AA | **GAP** — `DESIGN_SYSTEM.md` §2 lists failing tokens; assigned to Miles |
| 7.4 | Never install an accessibility "overlay" widget | **OK** — none. They attract lawsuits rather than preventing them |

**Why it matters.** Over 5,000 digital accessibility lawsuits were filed in
2025, and small sites are targeted precisely because they're easy. A one-page
marketing site with a checkout is exactly the profile. This is a real,
mundane, high-probability risk — higher than most of the exotic ones.

---

## 8. Intellectual property

| # | Item | Status |
| --- | --- | --- |
| 8.1 | The name "FlowShield" cleared against existing trademarks | **GAP / OWNER** — never searched. Do a USPTO search (free) before spending on branding; a lawyer's clearance search is a few hundred dollars. Renaming after launch costs far more |
| 8.2 | Third-party open-source notices shipped with the app | **GAP** — no `THIRD-PARTY-NOTICES.txt` anywhere. The app ships Velopack, `System.Security.Cryptography.ProtectedData` and a self-contained .NET runtime; the server ships express, better-sqlite3, stripe, nodemailer, cors. MIT and Apache both require the copyright line and licence text to travel with the binary |
| 8.3 | Fonts licensed for web use | **OK** — the site self-hosts Inter (`Website/fonts/InterVariable.woff2`) under the SIL Open Font License; the licence text ships alongside it at `Website/fonts/OFL.txt`. No third-party font host (Google Fonts, previously Syne and Source Sans 3) is used or contacted anymore (#147/B1) |
| 8.4 | Icons and images are ours or licensed | **OK** — the shield mark and tray icons were drawn for this project; no stock assets |
| 8.5 | Competitor names used fairly | **OK** — the app's blocklist names apps (Steam, Discord) descriptively, which is nominative fair use, and the site names none |
| 8.6 | No competitor's code or copy was reused | **OK** |

---

## 9. Payments, tax and the "it closed my work" problem

| # | Item | Status |
| --- | --- | --- |
| 9.1 | PCI handled by Stripe, never by us | **OK** — Stripe Checkout; no card data touches the server |
| 9.2 | Sales tax and VAT | **GAP / OWNER** — see 3.4. As your own merchant of record with Stripe you owe VAT on EU sales from the first euro (no threshold for non-EU sellers) and US state sales tax once a state's threshold is met. Two honest options: turn on Stripe Tax and register where required, or sell through a merchant of record (Paddle, Lemon Squeezy, FastSpring) that takes that liability. At $4.99 the second is usually the sane one |
| 9.3 | No claim that FlowShield is parental-control or enforcement software | **OK today, watch it** — it has no admin rights, no password lock and no website blocking, so any "stop your kid gaming" claim would be false and is also the most likely source of an angry-customer complaint |
| 9.4 | Data-loss risk disclosed before it can happen | **OK** — the terms gate states it in the first line a new user sees, and Stripe's consent box repeats it at checkout |
| 9.5 | The blocker stays timid | **OK, automated** — `CriticalProcesses` is never closed, no admin rights, no drivers, no hosts-file edits; tier 5 guards it |
| 9.6 | The site is hosted somewhere whose terms allow selling | **GAP, before the first sale** — GitHub Pages' terms say it is "not intended for or allowed to be used as a free web-hosting service to run your online business, e-commerce site, or any other website that is primarily directed at either facilitating commercial transactions". The site has a Buy button, a checkout and a post-purchase page. Harmless while Stripe is in test mode, and the site is offline for the beta (#165); it moves host in the go-live batch (#166), and everything that points at the Pages URL moves with it — including the terms URL in 2.2 |

---

## 10. Email

| # | Item | Status |
| --- | --- | --- |
| 10.1 | Licence emails are transactional, not marketing | **OK** — the key, activation steps, support link |
| 10.2 | A real sender address | **GAP** — `EMAIL_FROM` defaults to `onboarding@resend.dev` |
| 10.3 | Physical address and unsubscribe in any marketing email | **Not yet needed** — the moment you send one promotional email, CAN-SPAM's rules apply to it |
| 10.4 | Never email customers because they bought | **OWNER** — a purchase is not consent to marketing in the EU or UK |

---

## 11. Security (a breach is the fastest route to a claim)

| # | Item | Status |
| --- | --- | --- |
| 11.1 | Customer data never in git | **OK, verified** — `*.db`, logs and `.stripe_keys.json` are ignored and have never been committed |
| 11.2 | Secrets only in the host's environment | **OK** — Render env vars; nothing in the repo |
| 11.3 | TLS everywhere | **OK** — Render terminates TLS; the app talks HTTPS |
| 11.4 | Rate limiting and webhook signature checks | **OK** — `ratelimit.js`; Stripe signature verified |
| 11.5 | Licence database backed up | **GAP / OWNER** — SQLite on a Render disk with no documented backup. Losing it means every customer loses their licence, which is a refund event for all of them |
| 11.6 | Dependency updates | **Partly** — no automated scanning; GitHub's Dependabot is free and would cover both `Server/` and NuGet |

---

## 12. Marketing and influencers

| # | Item | Status |
| --- | --- | --- |
| 12.1 | Paid creators disclose the partnership clearly | **GAP until used** — the FTC holds the **brand** liable too. Any outreach message must require "#ad" or "paid partnership" in the post itself, not buried in hashtags |
| 12.2 | Creators don't repeat claims the product can't back | **GAP until used** — give each creator a one-page "what you may and may not say" |
| 12.3 | Affiliate commissions disclosed | **Not applicable yet** — no affiliate system |

---

## 13. What I recommend doing, in order

**Before the first real sale (blocking):**

1. Fill in the operator name, address and support email (1.1, 4.6, 10.2).
2. ~~Terms acceptance at checkout and in the app~~ — done in #108. Still needs
   the terms-of-service URL set on the Stripe account (2.2).
3. Decide merchant-of-record versus Stripe Tax (9.2). ~~The sales-tax
   sentence~~ was removed in #107.
4. ~~Disclose the device identifier and device name~~ — done in #107.
5. Ship `THIRD-PARTY-NOTICES.txt` with the app and the server (8.2).
6. ~~Minimum age, subprocessors, retention periods~~ — done in #107.
7. Search the USPTO for "FlowShield" (8.1).
8. Move the site off GitHub Pages to a host whose terms allow selling (9.6),
   in the go-live batch (#166).

**Soon after:**

9. Licence database backups (11.5) and Dependabot (11.6).
10. Accessibility pass to WCAG 2.1 AA on the site and the app (7.1–7.3).
11. A written data-request and breach procedure (5.4, 5.9).
12. GDPR EU representative, or a decision not to sell into the EU (5.7).

**Owner decisions only a person can make:** the legal entity, the EU
representative, merchant of record, trademark clearance, and whether a lawyer
reviews the terms before live keys. The first four cost money; the last one is
the one I'd not skip, because §6 of the terms is what stands between you and a
claim for lost work.

---

## 14. What is checked automatically

These fail CI, so they can't regress quietly:

- Site claims match the shipped app (tier 5, `TestWebsiteClaimsMatchTheApp`).
- The changelog's numbers match the code (tier 5).
- Legal, support and changelog pages are linked from every footer (tier 5).
- The blocker never closes protected processes, needs no admin rights (tier 5).
- Settings are encrypted on disk and no blocklist name appears in plaintext
  (tier 3).
- **New:** no `[placeholder]` remains on a customer-facing page (tier 5).
- **New:** the privacy policy names every kind of data the client actually
  sends to the server (tier 5).
- **New:** the terms gate sits above every other panel, records the version and
  time before it closes, and no sprint can start until it's accepted (tier 5),
  proved on screen by invoking the covered Start button (tier 3).
- **New:** the app's terms version matches the version on the legal page
  (tier 1), and checkout asks the buyer to agree (tier 1).

Anything else on this list is a human check. Do it at the four moments listed
at the top.
