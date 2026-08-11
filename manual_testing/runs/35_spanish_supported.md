# 35_spanish_supported: Spanish lead, a language the program does support

**What the manual requires:** Handled normally, in Spanish. Included as the control for the Portuguese run: if this works and Portuguese also works, the language gate never fires at all.

**Manual references:** 2A §14 (English and Spanish are supported)

_Run 2026-08-11 14:48 UTC, 2 turns, $0.014661_

---

### Turn 1

**Lead:** Hola Sonia, tengo 35 años y llevo 2 años intentando quedar embarazada sin éxito. ¿Puedes ayudarme?

**Sonia:**

> Puedo ayudarte a entender mejor qué áreas de tu caso podrían seguirse explorando para aumentar tus posibilidades.
>
> Dos años intentando es tiempo suficiente para mirar más allá de lo básico y buscar qué puede optimizarse en tu salud reproductiva y general.
>
> ¿Has hecho ya alguna evaluación médica o pruebas?
>

<details><summary>trace</summary>

- intent: `new_prospect`  tags: `long_ttc`  language: `es`
- explicit_question: '¿Puedes ayudarme?'
- slots: `{"age": 35, "time_trying": "2 años"}`
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: not_enough_context`
- playbooks: `returning_prospect, unexplained_infertility_es, first_message_vague`
- action: `REPLY:new_prospect`  pause: `False`  reason: `None`

</details>

### Turn 2

**Lead:** me dijeron que tengo baja reserva ovárica

**Sonia:**

> La baja reserva ovárica es una pieza de información, pero no dice todo sobre tu fertilidad ni sobre lo que todavía puede optimizarse.
>
> Me gustaría saber qué más te han revisado o qué tratamientos, si alguno, has probado hasta ahora. Eso ayudaría a entender mejor tu situación.
>

<details><summary>trace</summary>

- intent: `new_prospect`  tags: `low_amh`  language: `es`
- slots: `{"age": 35, "time_trying": "2 años", "diagnoses": ["baja reserva ovárica"]}`
- flags: `{}`
- gate: allow_booking=`True` escalate=`False` notes=`link available`
- playbooks: `low_amh_es, low_amh`
- action: `REPLY:new_prospect`  pause: `False`  reason: `None`

</details>

**Conversation ran to the end of the script; the AI never paused.**

---

## Verdict

**PASS**

- Answered in Spanish from the Spanish conversations. The control for run 27 behaves, so the language route is discriminating rather than off.
