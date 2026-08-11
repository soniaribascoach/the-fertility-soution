# r2_33_ghosted_and_returned: Comes back months later mid-thread

**What the manual requires:** She is picking up a conversation, not starting one. Everything in the seeded dossier must be treated as known.

**Manual references:** 2A §18 (memory), few_shots `returning_prospect`

_Run 2026-08-11 14:48 UTC, 1 turns, $0.007699_

---

### Turn 1

**Lead:** hey, sorry i disappeared back in march. things got hard. i'm ready to talk again

**Sonia:**

> No apology needed, and nothing’s been forgotten.
>
> Two years trying, low AMH, natural approach—that’s still where I’d pick this up.
>
> What has changed for you since March?
>

<details><summary>trace</summary>

- intent: `warm_prospect`  tags: `thinking_about_it`  language: `en`
- emotional_state: 'ready to talk'
- flags: `{}`
- gate: allow_booking=`True` escalate=`False` notes=`link available`
- playbooks: `returning_prospect, conversation_close, education_spiral`
- action: `REPLY:warm_prospect`  pause: `False`  reason: `None`

</details>

**Conversation ran to the end of the script; the AI never paused.**

---

## Verdict

**PASS**  ·  findings: F19

- F32 closed. "Two years trying, low AMH, natural approach, that's still where I'd pick this up" before a single question. She is shown she was remembered.
- Two changes did it: the reader now tags a returning lead `thinking_about_it`, and `returning_prospect` was raised to high priority so it stops losing its slot to three unrelated files that share the tag.
- Contains an em dash.
