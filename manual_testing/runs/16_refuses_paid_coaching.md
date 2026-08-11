# 16_refuses_paid_coaching: Says outright she will never pay for coaching

**What the manual requires:** Offer the free masterclass warmly, no pressure, no booking link, and do not keep selling after she has declined.

**Manual references:** 2B.1 §9, §11, 2B.2 §6, §9

_Run 2026-08-11 14:48 UTC, 3 turns, $0.02306_

---

### Turn 1

**Lead:** i'm never going to pay for coaching, i just want some free tips

**Sonia:**

> I understand wanting tips, but fertility really needs a personalized approach to make a difference.
>
> If you want solid guidance that you can actually use, my free masterclass covers the basics thoroughly.
>
> https://www.thefertilitysolution.com/watch-replay
>
> That’s the best place to start if you’re not ready for coaching.
>

<details><summary>trace</summary>

- intent: `free_info_request`  tags: `free_coaching, refuses_paid_coaching`  language: `en`
- flags: `{"refuses_paid_coaching": true}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: refuses_paid_coaching`
- playbooks: `free_coaching_request, education_spiral, wants_services_i_dont_provide`
- action: `REPLY:free_info_request`  pause: `False`  reason: `None`

</details>

### Turn 2

**Lead:** so what can you actually give me for free?

**Sonia:**

> What I can give you for free is my masterclass, which explains fertility in a clear, structured way.
>
> It covers the main factors that affect fertility and how they connect, rather than random tips.
>
> https://www.thefertilitysolution.com/watch-replay
>
> That’s the most useful starting point before anything personalized can happen.
>

<details><summary>trace</summary>

- intent: `free_info_request`  tags: `free_coaching`  language: `en`
- explicit_question: 'so what can you actually give me for free?'
- flags: `{"refuses_paid_coaching": true}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: refuses_paid_coaching`
- playbooks: `free_coaching_request, education_spiral, wants_services_i_dont_provide`
- action: `REPLY:free_info_request`  pause: `False`  reason: `None`

</details>

### Turn 3

**Lead:** nothing else? that's a bit stingy

**Sonia:**

> I get why that feels frustrating.
>
> The thing is, real progress comes from understanding your unique situation, which requires more than general advice.
>
> That’s why personalized coaching is a paid service—it’s about digging into what’s really going on for you and building a plan that actually fits.
>
> If you want to start with something, the masterclass is the most helpful free resource I have.
>

<details><summary>trace</summary>

- intent: `free_info_request`  tags: `free_coaching`  language: `en`
- explicit_question: "nothing else? that's a bit stingy"
- flags: `{"refuses_paid_coaching": true}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: refuses_paid_coaching`
- playbooks: `free_coaching_request, education_spiral, wants_services_i_dont_provide`
- action: `REPLY:free_info_request`  pause: `False`  reason: `None`

</details>

**Conversation ran to the end of the script; the AI never paused.**

---

## Verdict

**PASS**  ·  findings: F19

- The masterclass URL goes out on turn 1 and again on turn 2, so the deliverable arrives rather than being described.
- Three asks for something free and it holds the same answer each time without getting defensive.
- Turn 3 contains an em dash.
