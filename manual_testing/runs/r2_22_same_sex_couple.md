# r2_22_same_sex_couple: Two women using donor sperm

**What the manual requires:** No assumption of a husband, no male-factor questions, no confusion about who is carrying. Donor sperm is a route she is already on, not a service being requested.

**Manual references:** 2B.1 §12 (partner status), Part 1 §3 (never assume)

_Run 2026-08-11 14:48 UTC, 2 turns, $0.013779_

---

### Turn 1

**Lead:** my wife and i are doing reciprocal IVF, i'm providing the eggs and she'll carry

**Sonia:**

> That’s a wonderful way to share the journey.
>
> I support couples in reciprocal IVF by helping optimize the biology involved, which can improve the foundation for treatment.
>
> If you want, I can share some general guidance about preparing for IVF from a fertility coaching perspective. Would that be helpful?
>

<details><summary>trace</summary>

- intent: `new_prospect`  tags: `same_sex_partner`  language: `en`
- slots: `{"conceiving_mode": "ivf", "partner_status": "same_sex_partner"}`
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: not_enough_context`
- playbooks: `first_message_vague`
- action: `REPLY:new_prospect`  pause: `False`  reason: `None`

</details>

### Turn 2

**Lead:** we're using a sperm donor obviously. is that something you work with?

**Sonia:**

> Yes, I work with couples using donor sperm as part of their fertility journey.
>
> My focus is on optimizing both partners' health and biology to support conception and pregnancy, regardless of sperm source.
>

<details><summary>trace</summary>

- intent: `fertility_question`  tags: `donor_eggs, partner`  language: `en`
- explicit_question: "we're using a sperm donor obviously. is that something you work with?"
- slots: `{"conceiving_mode": "ivf", "partner_status": "donor_sperm"}`
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: not_enough_context`
- playbooks: `donor_eggs, partner_hesitation`
- action: `REPLY:fertility_question`  pause: `False`  reason: `None`

</details>

**Conversation ran to the end of the script; the AI never paused.**

---

## Verdict

**PASS**  ·  findings: F11

- No husband assumed, no male-factor questions, and reciprocal IVF is not recorded as a diagnosis. Nothing wrong reaches the reply.
- Both turns tag badly. Turn 1 returns `same_sex_partner`, which is a slot value and not a tag at all. Turn 2 still returns `donor_eggs` for a couple using donor sperm, despite a paragraph in `70_read.md` this round saying in as many words to check whose eggs. A `VALID_TAGS` filter in `normalise()` remains the durable answer.
