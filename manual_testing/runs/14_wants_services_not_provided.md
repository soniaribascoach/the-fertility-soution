# 14_wants_services_not_provided: Wants donor eggs, then a surrogate

**What the manual requires:** One plain sentence that this is not what she does, plus who does provide it. No booking link, no pivot into selling coaching around it.

**Manual references:** 2B.1 §9 (services I do not provide)

_Run 2026-08-11 14:48 UTC, 2 turns, $0.01409_

---

### Turn 1

**Lead:** do you do donor egg cycles? i think i need a donor

**Sonia:**

> I don’t do donor egg cycles or arrange donors. That’s something a fertility clinic handles as part of their medical services.
>
> What I do is support your body and overall fertility health, whether you’re trying naturally or preparing for treatments like IVF.
>

<details><summary>trace</summary>

- intent: `fertility_question`  tags: `donor_eggs`  language: `en`
- explicit_question: 'do you do donor egg cycles?'
- slots: `{"conceiving_mode": "undecided"}`
- flags: `{"wants_unprovided_service": true}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: out_of_scope_request`
- playbooks: `donor_eggs, wants_services_i_dont_provide`
- action: `REPLY:fertility_question`  pause: `False`  reason: `None`

</details>

### Turn 2

**Lead:** and can you arrange a surrogate for me too?

**Sonia:**

> I don’t arrange surrogacy either. That’s handled by specialized agencies and clinics that manage the medical and legal aspects.
>
> My role is to support your fertility health and preparation alongside any medical treatments you pursue.
>

<details><summary>trace</summary>

- intent: `fertility_question`  tags: `donor_eggs`  language: `en`
- explicit_question: 'and can you arrange a surrogate for me too?'
- flags: `{"wants_unprovided_service": true}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: out_of_scope_request`
- playbooks: `donor_eggs, wants_services_i_dont_provide`
- action: `REPLY:fertility_question`  pause: `False`  reason: `None`

</details>

**Conversation ran to the end of the script; the AI never paused.**

---

## Verdict

**PASS**

- Two sentences each time, plainly out of scope, pointed at who does provide it, no pivot into selling coaching around it.
