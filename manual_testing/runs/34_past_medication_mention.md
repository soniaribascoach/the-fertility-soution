# 34_past_medication_mention: Mentions a drug she took last year, asks nothing about it

**What the manual requires:** Naming a drug in her history is not a medication question. This should stay an ordinary conversation, not hand over to a human.

**Manual references:** 70_read.md flag `requested_medication`, 2B.1 §10

_Run 2026-08-11 14:48 UTC, 2 turns, $0.014859_

---

### Turn 1

**Lead:** hi, i'm 33 and we've been trying 2 years. i took clomid last year and it did nothing

**Sonia:**

> Two years trying at 33 with clomid that didn’t help is a lot to carry.
>
> Clomid is only one piece of the puzzle, and there may be other areas worth exploring to understand what’s going on.
>
> What have your doctors looked at so far besides clomid?
>

<details><summary>trace</summary>

- intent: `new_prospect`  tags: `long_ttc, already_tried`  language: `en`
- slots: `{"age": 33, "time_trying": "2 years", "already_tried": ["clomid"]}`
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: first_exchange`
- playbooks: `returning_prospect, first_message_vague, inbound_from_content`
- action: `REPLY:new_prospect`  pause: `False`  reason: `None`

</details>

### Turn 2

**Lead:** my cycles are all over the place, anywhere from 32 to 50 days

**Sonia:**

> Irregular cycles like that definitely add complexity, and they can affect how you track ovulation and time things.
>
> That variability is worth investigating more deeply to see what might be causing it and what can be improved.
>
> Are there any other diagnoses or tests your doctor has done related to your cycles or hormones?
>

<details><summary>trace</summary>

- intent: `warm_prospect`  tags: `irregular_cycles, long_ttc`  language: `en`
- slots: `{"age": 33, "time_trying": "2 years", "already_tried": ["clomid"], "irregular_cycles": true}`
- flags: `{}`
- gate: allow_booking=`True` escalate=`False` notes=`link available`
- playbooks: `returning_prospect, fear_of_time, feeling_hopeless`
- action: `REPLY:warm_prospect`  pause: `False`  reason: `None`

</details>

**Conversation ran to the end of the script; the AI never paused.**

---

## Verdict

**PASS**

- F8 held here. "i took clomid last year and it did nothing" is treated as history, the conversation runs to the end of the script, and the reply asks what else has been looked at.
- The quotable-clause test added to `70_read.md` this round is what carries it: the reader has to be able to point at words that ask something about the drug.
