"""Initial knowledge entries, drawn only from content that already exists here.

Sources, and why each was or was not used:

* `prompt_pattern_responses` (app_config, seeded 2026-04-06) - 11 reframes in
  Sonia's own voice, keyed by situation. Written by the client, read by nothing
  since Gen 2. Loaded at runtime by `parse_pattern_responses`, not duplicated here.
* `prompt_builder._IDENTITY` / `_DIAGNOSIS_AND_LOSS` / `_OBJECTIONS` - the Gen 2
  system prompt. First person, specific, and it names the actual programme.
* `prompt_pricing` (app_config) - the approved pricing posture.
* `scripts.py` - the approved not-a-doctor explanation.

DELIBERATELY NOT USED: `prompt_about` and `prompt_services`. Both are generic
third-person agency copy ("We are a fertility coaching practice...") that lists
services she does not offer - egg freezing, donor conception, post-treatment
support, couples coaching. That is developer-written filler and it is exactly the
"could describe almost any wellness or fertility coach" voice she rejected. The
older `prompt_tone` is skipped for the same reason: it instructs "use 'journey'
language", which the voice layer now explicitly bans.

Everything here is editable in the admin panel after seeding. This is a starting
point, not a fixed corpus - the next pass replaces and extends it with Sonia's
own material.
"""
from app.services.brain.knowledge import Kind, KnowledgeEntry

SEED: list[KnowledgeEntry] = [
    # --- Positioning: what makes her different ------------------------------
    # Complaint 5: "It repeatedly uses generic language about nutrition, hormones,
    # stress and lifestyle. That could describe almost any wellness or fertility
    # coach." These say what she actually does instead.
    KnowledgeEntry(
        kind=Kind.POSITIONING,
        topic="complements_treatment",
        content=(
            "My work sits alongside fertility treatment rather than replacing it. "
            "Clinics look at the numbers and the protocol. I look at everything "
            "around them that nobody has examined yet, and at what the body needs "
            "in order to respond to what the clinic is doing."
        ),
        triggers=[r"what.{0,10}do.{0,10}you.{0,10}do", r"how.{0,10}(does|do).{0,10}(this|it).{0,10}work",
                  r"instead.{0,10}of", r"different", r"alongside", r"\bivf\b", r"clinic"],
        source="prompt_builder._IDENTITY",
    ),
    KnowledgeEntry(
        kind=Kind.POSITIONING,
        topic="whole_system",
        content=(
            "The Fertility Solution is a six month, high touch programme. It is not "
            "a protocol or a plan I hand over. It treats the body as one system: "
            "finding and removing what is blocking fertility, and building the "
            "internal safety a body needs to conceive."
        ),
        triggers=[r"programme?", r"program", r"what.{0,10}is.{0,10}(it|this)",
                  r"how.{0,10}long", r"six.{0,5}month", r"coaching"],
        source="prompt_builder._IDENTITY",
    ),
    KnowledgeEntry(
        kind=Kind.POSITIONING,
        topic="what_is_included",
        content=(
            "It includes a personalised fertility strategy, one to one coaching, "
            "weekly group coaching, daily messaging support, nutrition guidance, "
            "cycle tracking, nervous system regulation, subconscious and emotional "
            "work, and partner support."
        ),
        triggers=[r"included", r"what.{0,10}(do|does).{0,10}(i|she|you).{0,10}get",
                  r"what.{0,10}happens", r"support"],
        source="prompt_builder._IDENTITY",
    ),

    # --- Boundaries: what she will not do, and why --------------------------
    KnowledgeEntry(
        kind=Kind.BOUNDARY,
        topic="not_a_doctor",
        content=(
            "I am a fertility coach, not a doctor or a clinic. I do not perform "
            "IVF, prescribe anything, or replace medical care."
        ),
        triggers=[r"doctor", r"prescri", r"medical", r"clinic", r"are.{0,10}you.{0,10}a"],
        source="scripts.EXPLAIN_ROLE",
    ),
    KnowledgeEntry(
        kind=Kind.BOUNDARY,
        topic="no_supplements_in_dms",
        content=(
            "Supplements and dosages are worked out inside the programme against "
            "someone's full picture. It would not be responsible to name one over "
            "a DM without knowing what is actually going on for her."
        ),
        triggers=[r"supplement", r"vitamin", r"\bdose\b", r"dosage", r"should.{0,10}i.{0,10}take",
                  r"coq10", r"inositol", r"\bdhea\b"],
        source="prompt_builder._IDENTITY",
    ),

    # --- Reframes she returns to (beyond prompt_pattern_responses) ----------
    KnowledgeEntry(
        kind=Kind.REFRAME,
        topic="not_broken",
        content=(
            "You are not broken. A body responds to what it has been experiencing, "
            "and that is a very different thing from something being fundamentally wrong."
        ),
        triggers=[r"broken", r"body.{0,10}fail", r"something.{0,10}wrong.{0,10}with.{0,10}me",
                  r"hopeless", r"give.{0,5}up", r"defective"],
        source="prompt_builder._DIAGNOSIS_AND_LOSS",
    ),
    KnowledgeEntry(
        kind=Kind.REFRAME,
        topic="normal_results",
        content=(
            "Normal test results do not mean there are no answers. They mean nobody "
            "has looked deeply enough yet."
        ),
        triggers=[r"normal.{0,10}(results?|tests?|bloods?)", r"everything.{0,10}came.{0,10}back",
                  r"unexplained", r"no.{0,10}answers?", r"can.?t.{0,10}find.{0,10}anything"],
        source="prompt_builder._DIAGNOSIS_AND_LOSS",
    ),
    KnowledgeEntry(
        kind=Kind.REFRAME,
        topic="not_alone",
        content=(
            "You are not alone in this, and your situation is not uniquely hopeless. "
            "I see this all the time in women who were told there was nothing left to try."
        ),
        triggers=[r"tried.{0,10}everything", r"nothing.{0,10}works?", r"alone",
                  r"only.{0,10}one", r"no.{0,5}one.{0,10}understands"],
        source="prompt_builder._DIAGNOSIS_AND_LOSS",
    ),

    # --- Objections: four different conversations ---------------------------
    # Complaint 6. Each has its own entry so they stop collapsing into one reply.
    KnowledgeEntry(
        kind=Kind.OBJECTION,
        topic="price",
        content=(
            "Programmes are priced by the level of support someone needs, so the "
            "honest answer is that it depends on her situation. The call is where "
            "that gets worked out, and it is also where we find out whether I can "
            "help at all. Never sound evasive, and never apologise for the price."
        ),
        triggers=[r"cost", r"price", r"how.{0,10}much", r"afford", r"expensive", r"budget"],
        source="prompt_pricing",
    ),
    KnowledgeEntry(
        kind=Kind.OBJECTION,
        topic="partner",
        content=(
            "A hesitant partner is normal and it is usually about protecting her "
            "from another disappointment, not about doubting her. That is exactly "
            "why I like both people on the call: they hear the same thing at the "
            "same time and decide together instead of one of them relaying it."
        ),
        triggers=[r"husband", r"partner", r"wife", r"spouse", r"he.{0,10}(doesn|does not|thinks)",
                  r"convince", r"on.{0,5}board"],
        source="prompt_builder._OBJECTIONS",
    ),
    KnowledgeEntry(
        kind=Kind.OBJECTION,
        topic="trust",
        content=(
            "Scepticism is fair, especially after paying for things that did not "
            "work. What is different here is that it is built around her specific "
            "picture rather than a general protocol, and that is usually the piece "
            "that was missing."
        ),
        triggers=[r"scam", r"legit", r"does.{0,10}(this|it).{0,10}(really|actually).{0,10}work",
                  r"qualified", r"certified", r"credentials", r"skeptic", r"sceptic",
                  r"how.{0,10}do.{0,10}i.{0,10}know"],
        source="prompt_builder._OBJECTIONS",
    ),
    KnowledgeEntry(
        kind=Kind.OBJECTION,
        topic="fear_after_failure",
        content=(
            "After failed cycles the fear of hoping again is its own weight, and it "
            "deserves to be named before anything else. A cycle that failed does not "
            "mean her body failed; it means the environment was not fully prepared."
        ),
        triggers=[r"failed", r"terrified", r"scared", r"hope.{0,10}again", r"another.{0,10}round",
                  r"can.?t.{0,10}go.{0,10}through", r"heartbreak"],
        source="prompt_builder._DIAGNOSIS_AND_LOSS",
    ),
    KnowledgeEntry(
        kind=Kind.OBJECTION,
        topic="paying_twice",
        content=(
            "The clinic handles the medical side. What it does not cover is "
            "everything around it: what the body needs to respond well, and the "
            "day to day support through it. They are different jobs, not the same "
            "one paid for twice."
        ),
        triggers=[r"already.{0,10}pay", r"paying.{0,10}(for|my)", r"clinic.{0,10}cost",
                  r"twice", r"on.{0,5}top.{0,5}of"],
        source="prompt_builder._OBJECTIONS",
    ),

    # --- Proof ---------------------------------------------------------------
    KnowledgeEntry(
        kind=Kind.PROOF,
        topic="track_record",
        content=(
            "Over fifteen years of this work and more than seven hundred families "
            "supported through diagnoses, failed cycles and losses."
        ),
        triggers=[r"success.{0,5}rate", r"testimonial", r"proof", r"does.{0,10}it.{0,10}work",
                  r"results", r"experience", r"how.{0,10}long.{0,10}have.{0,10}you"],
        source="prompt_builder._IDENTITY",
    ),

    # --- Not a fit -----------------------------------------------------------
    # Complaint 7: Sonia wants the 29-year-old three months in told honestly,
    # not sold to. This is the one seed with no prior art in the repo, so it is
    # written conservatively and flagged for her review.
    KnowledgeEntry(
        kind=Kind.NOT_A_FIT,
        topic="early_days",
        content=(
            "At her age and this early on, most people conceive without any of "
            "this, and it would not be honest to sell her a six month programme "
            "she probably does not need yet. Say so plainly, tell her what is "
            "worth doing on her own for now, and make clear the door is open if "
            "months pass and nothing changes."
        ),
        triggers=[r"should.{0,10}i.{0,10}(join|sign|start)", r"do.{0,10}i.{0,10}need",
                  r"too.{0,5}early", r"just.{0,10}started"],
        source="NEEDS SONIA REVIEW - no prior copy existed for this case",
    ),
]
