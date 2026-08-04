"""Part 5 of the Operating Manual: the factual reference.

The manual is explicit that this is the single source of truth and overrides any
conflicting factual reference elsewhere in the system. That is the whole reason
these are data rather than prompt text: the running code claimed "15 years" in
`writer.py` while claiming "over 700 families" in `prompt_builder.py`, because a
fact stated in two prompts drifts.

WHERE THE MANUAL IS OUT OF DATE
-------------------------------
The manual is the source of truth for facts, but it is a document and the
business moves. `pricing_range` shipped inactive because the manual says $1,500
to $10,000 while `scripts.py` and the live config say $1,500 to $14,000, and a
figure quoted to real prospects is not something to change on a document's
say-so. The client confirmed on 2026-08-04 that **$1,500 to $14,000 is current**,
so the entry is now active with that figure and the manual's is superseded.

The price appears in two places by necessity - here for the routed brain, and
`scripts._PLACEHOLDER_DEFAULTS` for the funnel brain - so a test asserts they
agree. Two different numbers reaching two different leads is the failure mode.
"""
from app.services.brain.knowledge import Kind, KnowledgeEntry

MANUAL = "manual v1.0 Part 5"

PART5: list[KnowledgeEntry] = [
    KnowledgeEntry(
        kind=Kind.FACT,
        topic="who_i_am",
        content=(
            "I'm a fertility coach, not a doctor or a fertility clinic. I help "
            "women and couples optimize fertility from every angle through a "
            "personalized, research-backed approach, looking at the full picture "
            "including the areas that may not have been explored deeply enough."
        ),
        triggers=[r"who are you", r"what do you do", r"are you a (doctor|nurse|nutritionist)",
                  r"what.{0,10}is.{0,10}(this|the program)", r"how does.{0,10}work"],
        source=MANUAL,
    ),
    KnowledgeEntry(
        kind=Kind.FACT,
        topic="languages",
        content="I work with clients in English and Spanish.",
        triggers=[r"\bspanish\b", r"\bespanol\b", r"language", r"do you speak"],
        source=MANUAL,
    ),
    KnowledgeEntry(
        kind=Kind.FACT,
        topic="works_internationally",
        content=(
            "The coaching is remote, so where someone lives is not a barrier. The "
            "medical side stays with her own clinic wherever she is."
        ),
        triggers=[r"international", r"outside the us", r"do you work with .{0,20}(uk|europe|canada|australia)",
                  r"where are you based", r"remote", r"in person"],
        source=MANUAL,
    ),
    KnowledgeEntry(
        kind=Kind.FACT,
        topic="what_i_do_not_provide",
        content=(
            "I don't perform IVF or IUI, prescribe or manage medication, do "
            "surgery, provide donor eggs or sperm, arrange surrogacy, or give a "
            "medical diagnosis. Those belong with her clinic."
        ),
        triggers=[r"do you (do|offer|provide)", r"can you (prescribe|order|refer)",
                  r"\bsurrogacy\b", r"donor (egg|sperm)", r"tubal reversal"],
        source=MANUAL,
    ),
    KnowledgeEntry(
        kind=Kind.FACT,
        topic="paid_program",
        content=(
            "This is a paid coaching program that asks for real commitment: time, "
            "participation and financial investment. Different levels of support "
            "exist, and which one fits depends on her goals and how much support "
            "she needs."
        ),
        triggers=[r"paid", r"free", r"invest", r"cost", r"how.{0,10}much", r"payment plan"],
        source=MANUAL,
    ),
    KnowledgeEntry(
        kind=Kind.FACT,
        topic="the_call",
        content=(
            "The consultation is free, and it is where we work out whether I can "
            "genuinely help. My team runs it, and Natalia will text before the "
            "appointment to confirm."
        ),
        triggers=[r"the call", r"consultation", r"what happens", r"who will i speak",
                  r"\bnatalia\b", r"discovery call"],
        source=MANUAL,
    ),
    # RESOLVED 2026-08-04: the client confirmed $1,500 to $14,000 is current, so
    # the manual's "$1,500 to $10,000" (2B.2 section 6) is out of date and the
    # live config was right. Now active. The figure must stay identical to
    # `scripts._PLACEHOLDER_DEFAULTS["price_range"]`, or a lead can be quoted two
    # different numbers depending on which brain answers her; a test enforces it.
    KnowledgeEntry(
        kind=Kind.FACT,
        topic="pricing_range",
        content=(
            "Programs currently range from approximately $1,500 to $14,000, "
            "depending on the level of support someone needs."
        ),
        triggers=[r"how.{0,10}much", r"price", r"cost", r"range", r"ballpark"],
        source="client confirmed 2026-08-04; supersedes manual v1.0 2B.2 section 6",
    ),
]
