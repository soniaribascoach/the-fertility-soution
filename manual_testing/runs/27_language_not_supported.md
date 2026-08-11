# 27_language_not_supported: Writes in Portuguese

**What the manual requires:** Escalate rather than carry on in a language the program cannot coach in.

**Manual references:** 2A §14 (English and Spanish only), gate `language_not_supported`

_Run 2026-08-11 14:48 UTC, 1 turns, $0.002922_

---

### Turn 1

**Lead:** Oi Sonia! Tenho 35 anos e estou tentando engravidar há 2 anos, sem sucesso. Você pode me ajudar?

**Sonia:** _(no reply sent)_

<details><summary>trace</summary>

- intent: `new_prospect`  tags: `long_ttc`  language: `other`
- explicit_question: 'Você pode me ajudar?'
- slots: `{"age": 35, "time_trying": "2 anos"}`
- flags: `{"needs_human": true}`
- gate: allow_booking=`False` escalate=`True` notes=`handover: language_not_supported, silent`
- playbooks: `-`
- action: `HANDOVER:language_not_supported`  pause: `True`  reason: `language_not_supported`

</details>

**Conversation ended.** AI paused after turn 1: `language_not_supported`

---

## Verdict

**PASS**

- Portuguese is read as `other`, `needs_human` is set, and the pause reason is `language_not_supported` rather than the generic flag, so whoever picks it up knows they need Portuguese.
