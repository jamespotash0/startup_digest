#!/usr/bin/env python3
"""Enrichment's pure functions, and the two gates its output drives.

`us_only_reject` and `off_sector_reject` are the highest-consequence code in the
repo: they delete companies from the funding digest, and a wrong deletion is
completely invisible — you just never hear about the company. Both are pure
functions of the enrich dict, so they can be pinned exactly.

The email guessers matter for a different reason: their output is what cold
outreach gets sent to. A wrong pattern doesn't error, it just bounces.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import enrich as E                    # noqa: E402
import funding_digest as F            # noqa: E402
from harness import case, check, equal, main   # noqa: E402


# --------------------------------------------------------------- the geo gate
@case
def test_us_variants_all_survive_the_geo_gate():
    for c in ["United States", "USA", "US", "U.S.", "U.S.A.", "America",
              "united states", "  United States  "]:
        equal(F.us_only_reject({"hq_country": c}), "", f"{c!r} should be kept")


@case
def test_foreign_hq_is_rejected():
    for c in ["United Kingdom", "India", "Germany", "Canada", "Israel"]:
        check(F.us_only_reject({"hq_country": c, "hq_city": "X"}),
              f"{c!r} should be rejected")


@case
def test_unknown_hq_fails_open():
    """A failed lookup is not evidence of being foreign. This is the single most
    consequential branch in the file: flipping it to fail-closed would silently
    delete every company the researcher couldn't resolve."""
    equal(F.us_only_reject({}), "")
    equal(F.us_only_reject({"hq_country": ""}), "")
    equal(F.us_only_reject({"hq_country": "   "}), "")


# ------------------------------------------------------------ the sector gate
@case
def test_kept_sectors_survive():
    for c in sorted(F.KEEP_CATEGORIES):
        equal(F.off_sector_reject({"category": c}), "", f"{c!r} should be kept")


@case
def test_off_sectors_are_rejected():
    for c in ["biotech/pharma", "hardware/devices", "space/aerospace/defense",
              "energy/climate", "materials/manufacturing", "consumer goods"]:
        check(F.off_sector_reject({"category": c}), f"{c!r} should be rejected")


@case
def test_unknown_sector_fails_open():
    equal(F.off_sector_reject({}), "")
    equal(F.off_sector_reject({"category": ""}), "")


@case
def test_every_kept_category_is_a_real_category():
    """KEEP_CATEGORIES lives in funding_digest, CATEGORIES in enrich. A typo in
    either silently drops a whole sector, because the gate compares strings."""
    unknown = F.KEEP_CATEGORIES - set(E.CATEGORIES)
    check(not unknown, f"KEEP_CATEGORIES names sectors enrich never emits: {unknown}")


# ------------------------------------------------------------- email guessing
@case
def test_guess_emails_is_ranked_most_likely_first():
    got = E.guess_emails("acme.ai", "Jane Smith")
    equal(got, ["jane@acme.ai", "jane.smith@acme.ai", "jsmith@acme.ai",
                "smith@acme.ai"])


@case
def test_guess_emails_handles_one_word_and_messy_names():
    equal(E.guess_emails("acme.ai", "Cher"), ["cher@acme.ai"])
    check("jean-luc@acme.ai" in E.guess_emails("acme.ai", "Jean-Luc Picard")[0:1]
          or E.guess_emails("acme.ai", "Jean-Luc Picard")[0].startswith("jean"),
          E.guess_emails("acme.ai", "Jean-Luc Picard"))
    equal(E.guess_emails("acme.ai", ""), [])
    equal(E.guess_emails("", "Jane Smith"), [])


@case
def test_pattern_to_email_fills_every_placeholder_form():
    equal(E.pattern_to_email("{first}", "Jane", "Smith", "acme.ai"), "jane@acme.ai")
    equal(E.pattern_to_email("{first}.{last}", "Jane", "Smith", "acme.ai"),
          "jane.smith@acme.ai")
    equal(E.pattern_to_email("{f}{last}", "Jane", "Smith", "acme.ai"), "jsmith@acme.ai")


@case
def test_pattern_to_email_refuses_a_half_filled_address():
    """An unresolved placeholder must yield "" — never 'jane.{last}@acme.ai',
    which would go out in a real email."""
    equal(E.pattern_to_email("{first}.{last}", "Jane", "", "acme.ai"), "")
    equal(E.pattern_to_email("{middle}", "Jane", "Smith", "acme.ai"), "")
    equal(E.pattern_to_email("", "Jane", "Smith", "acme.ai"), "")


# ------------------------------------------------------- model output parsing
@case
def test_parse_json_survives_the_ways_models_wrap_output():
    want = {"domain": "acme.ai"}
    for text in ['{"domain":"acme.ai"}',
                 '```json\n{"domain":"acme.ai"}\n```',
                 'Here is the result:\n{"domain":"acme.ai"}\nHope that helps!',
                 '  \n {"domain":"acme.ai"} \n ']:
        equal(E._parse_json(text), want, f"failed on {text!r}")


@case
def test_parse_json_returns_empty_rather_than_raising():
    for text in ["", None, "no json here", "{broken", "[1,2,3]"]:
        equal(E._parse_json(text), {}, f"failed on {text!r}")


# --------------------------------------------------- company name from a title
@case
def test_guess_company_pulls_the_name_off_a_real_headline():
    equal(F.guess_company("Acme AI raises $12M Series A - TechCrunch"), "Acme AI")
    equal(F.guess_company("Exclusive: Foo Corp secures $5M seed"), "Foo Corp")
    equal(F.guess_company("Bar Inc. closed a $30M round"), "Bar Inc.")


@case
def test_headlines_that_are_not_a_raise_never_reach_enrichment():
    """The stale enrich_cache entries were headline fragments, not companies:
    'the ai compute gap: enterprises are buying infrastructure'. Each one cost a
    web-search call to research a company that does not exist. is_funding is the
    gate that has to stop them before guess_company ever runs."""
    for t in ["The AI compute gap: enterprises are buying infrastructure they can't use",
              "Agentic orchestration: enterprise AI organizations have a decision to make",
              "Thinking Machines open sources first multimodal language model",
              "Daily funding roundup - March 3",
              "10 startups that raised this week",
              "Resilience I Fund closes at $200M"]:
        check(not F.is_funding(t, ""), f"{t!r} should not count as a raise")


# ------------------------------------- what the geo gate is allowed to affect






if __name__ == "__main__":
    main("enrich")


@case
def test_a_failed_lookup_is_retried_but_not_forever():
    """ai_lookup returns None when the CALL failed and {} when it researched and
    found nothing. Conflating them cached a well-formed record of empty strings,
    so one transient 401 meant the company was never researched again and both
    gates failed open for it permanently."""
    import tempfile
    real_lookup, real_email = E.ai_lookup, E.find_email
    cwd = os.getcwd()
    try:
        os.chdir(tempfile.mkdtemp())
        E.find_email = lambda d, f: ("", "", [])
        E.ai_lookup = lambda c: None                       # the call errors
        seen = []
        for _ in range(E.LOOKUP_MAX_ATTEMPTS + 1):
            seen.append(E.enrich("Flaky Co").get("retry"))
        check(seen[0] is True, "a first failure should be retried")
        check(seen[-1] is False,
              f"gave up never — a dead company would cost a call every run: {seen}")
        equal(sum(1 for s in seen if s), E.LOOKUP_MAX_ATTEMPTS - 1)

        # ...but "asked, genuinely nothing there" is cached the first time.
        calls = []
        E.ai_lookup = lambda c: calls.append(c) or {}
        E.enrich("Obscure Co")
        E.enrich("Obscure Co")
        equal(len(calls), 1, "a no-data answer should not be looked up twice")
    finally:
        E.ai_lookup, E.find_email = real_lookup, real_email
        os.chdir(cwd)


@case
def test_descriptive_prefixes_do_not_split_one_company_into_three():
    """A real run enriched "Agon", "UK defense AI startup Agon" and "Defense AI
    startup Agon" as three companies — three paid lookups for one raise. The
    dedupe key is the guessed name, so a description in front of it defeats
    dedupe entirely."""
    same = ["UK defense AI startup Agon raises $30M",
            "Defense AI startup Agon raises $30M",
            "Agon raises $30M"]
    keys = {F.company_key(F.guess_company(t)) for t in same}
    equal(len(keys), 1, f"one company read as {len(keys)}: {keys}")
    equal(keys.pop(), "agon")


@case
def test_stripping_descriptors_never_empties_a_name():
    """A company genuinely called "Startup" has to survive the peeling."""
    for headline, want in [("Startup raises $1M", "startup"),
                           ("Ramp raises $150M Series D", "ramp"),
                           ("Indian fintech startup Jupiter raises $12M", "jupiter")]:
        got = F.company_key(F.guess_company(headline))
        check(got, f"{headline!r} produced an empty company key")
        equal(got, want, headline)
