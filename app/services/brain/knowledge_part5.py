"""Part 5 of the Operating Manual: the factual reference.

The manual is explicit that this is the single source of truth and overrides any
conflicting factual reference elsewhere in the system. That is the whole reason
these are data rather than prompt text: the running code claimed "15 years" in
`writer.py` while claiming "over 700 families" in `prompt_builder.py`, because a
fact stated in two prompts drifts.

WHAT IS DELIBERATELY INACTIVE
-----------------------------
`pricing_range` ships with `active=False`. The manual says $1,500 to $10,000;
`scripts.py` and the live config say $1,500 to $14,000. That figure is quoted to
real prospects, so it is not something to change on a document's say-so without
Sonia confirming which is current. The entry is in the table, visible in the
admin panel, one checkbox away from live.

Everything else here is either uncontested in the manual or a correction to
content that was already wrong.
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
    # See the module docstring: the manual and the live config disagree, and the
    # figure is quoted to prospects, so this waits for Sonia rather than shipping.
    KnowledgeEntry(
        kind=Kind.FACT,
        topic="pricing_range",
        content=(
            "Programs currently range from approximately $1,500 to $10,000, "
            "depending on the level of support."
        ),
        triggers=[r"how.{0,10}much", r"price", r"cost", r"range", r"ballpark"],
        source=f"{MANUAL} 2B.2 section 6 - CONFLICTS with live config ($14,000). "
               f"Inactive until Sonia confirms which is current.",
        active=False,
    ),
]
