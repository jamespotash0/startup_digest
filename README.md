# Startup digest

A daily email of startups that just raised — filtered to the sectors and
geography you care about, each enriched with what the company actually sells,
where it's based, who founded it, who backed it, and a contact address.

Also writes `funded_companies.json`: the same companies in machine-readable
form, on a rolling 30-day window, for anything downstream that wants to act on
them.

One Python dependency. Runs free or near-free on GitHub Actions.

## How it works

```
RSS ──► is this a raise? ──► one row per company ──► enrich ──► gates ──► email
                                                        │                   +
                                                        └──► funded_companies.json
```

**Ingest.** Google News RSS queries built from funding language, plus TechCrunch
and VentureBeat venture feeds, over a rolling ~28h window.

**Decide what's actually a raise.** A headline needs a funding verb *and* an
amount or a named round, and must not match the look-alikes — VC funds closing
their own vehicles, acquisitions, "10 startups that raised this week" roundups,
survey reports. Most of what an RSS search for "funding" returns is not a
company raising money.

**Collapse to one company.** A round covered by five outlets becomes one entry,
so the expensive step runs once.

**Enrich.** For the top N by score, one LLM call with server-side web search
returns strict JSON: one sentence on what they sell, domain, HQ city/country,
sector, founders, investors. Cached per company. Hunter.io supplies a verified
founder address where it can, rationed against its free tier, falling back to a
pattern-guessed address labelled UNVERIFIED.

**Gate on what the research found, not the headline.** Off-sector companies
(biotech, hardware, aerospace, energy) are dropped. Non-US HQs drop out of the
*email* but still reach `funded_companies.json` — a raise is a valid datapoint
wherever it happened, it just isn't somewhere you'd send a cold email.

Both gates **fail open**: unknown is kept, because a failed lookup is not
evidence of anything.

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env          # EMAIL_USER / EMAIL_PASS / EMAIL_TO
.venv/bin/python funding_digest.py
```

With no email credentials it prints to stdout — the easiest dry run there is.

| Key | Required? | Without it |
|---|---|---|
| `EMAIL_USER` / `EMAIL_PASS` / `EMAIL_TO` | yes | prints instead of sending (`EMAIL_PASS` is a Gmail **app password**) |
| `ANTHROPIC_API_KEY` **or** `OPENAI_API_KEY` | no | headline-only digest; no company detail, and the US/sector gates fail open |
| `HUNTER_API_KEY` | no | addresses are pattern-guessed and labelled UNVERIFIED |

Either provider works — both have server-side web search, which is the actual
requirement. `llm.py` picks whichever key is set.

## Scheduling

Push, enable Actions, add the same keys as repo secrets.
`.github/workflows/startup-digest.yml` runs daily at 8am ET. State
(`enrich_cache.json`, `hunter_usage.json`, `funded_companies.json`) persists on
a `state` branch, so you never pay twice to research the same company.

## Cost

`FUNDING_ENRICH_TOP_N` is the only setting that can run up a bill — one
web-search call plus an optional Hunter lookup per company. Capped at **15 per
run** by default. `all` enriches every raise; `0` turns enrichment off entirely
and needs no LLM key at all.

A lookup whose *call* fails is retried on later runs up to
`ENRICH_MAX_ATTEMPTS` (3), then cached so a permanently unresolvable company
stops costing a call every day. A lookup that succeeds but finds nothing is
cached the first time — those are different things, and treating them the same
once meant a single transient 401 poisoned a company's cache permanently.

## Tests and evals

```bash
python tests/run.py          # no network, no keys, ~1s
python evals/eval_enrich.py  # accuracy of the enrichment step (costs API calls)
```

The eval corroborates the researcher against evidence it didn't choose: the
domain is resolved and checked for the company name, the claimed HQ against the
company's own site, the sector graded by a second model that sees only that site
text. It reports **gate impact** — how many companies a wrong answer would have
wrongly dropped — rather than per-field accuracy, since that's the only error
that costs anything.

MIT licensed, provided as is. Runs entirely on your own API keys and billing.
