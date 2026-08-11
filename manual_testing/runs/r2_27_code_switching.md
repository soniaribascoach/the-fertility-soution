# r2_27_code_switching: Switches between English and Spanish mid-conversation

**What the manual requires:** Both languages are supported. Pick one and stay in it rather than mirroring the switch every turn.

**Manual references:** 2A §14, few_shots `*_es` selection

_Run 2026-08-11 14:48 UTC, 3 turns, $0.021366_

---

### Turn 1

**Lead:** hola sonia, i saw your reel about low AMH y me identifiqué mucho

**Sonia:**

> La AMH es una guía aproximada de cuántos óvulos pueden responder a una estimulación, pero no predice si vas a concebir de forma natural ni es una cuenta atrás.
>
> Lo que importa en realidad es el panorama completo, no un solo número, y a menudo hay áreas que se pueden optimizar para mejorar la fertilidad. ¿Estás intentando ahora o solo lo estás mirando?
>

<details><summary>trace</summary>

- intent: `new_prospect`  tags: `low_amh`  language: `es`
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: not_enough_context`
- playbooks: `low_amh_es, low_amh`
- action: `REPLY:new_prospect`  pause: `False`  reason: `None`

</details>

### Turn 2

**Lead:** tengo 36, llevo 2 años trying, and my last AMH was really low

**Sonia:**

> Llevar dos años intentando es un tiempo en el que ya vale la pena mirar todo el cuadro con detalle.
>
> El AMH bajo es solo una pieza del rompecabezas, pero no me dices qué más se ha explorado o qué diagnóstico tienes.
>
> ¿Has hecho otras pruebas o te han dado algún diagnóstico?
>

<details><summary>trace</summary>

- intent: `new_prospect`  tags: `low_amh`  language: `es`
- slots: `{"age": 36, "time_trying": "2 años"}`
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: not_enough_context`
- playbooks: `low_amh_es, low_amh`
- action: `REPLY:new_prospect`  pause: `False`  reason: `None`

</details>

### Turn 3

**Lead:** sorry i mix languages, is that ok?

**Sonia:**

> Sí, claro que está bien mezclar idiomas. Me adapto a lo que te sea más cómodo.
>

<details><summary>trace</summary>

- intent: `warm_prospect`  tags: `low_amh, long_ttc`  language: `es`
- explicit_question: 'sorry i mix languages, is that ok?'
- slots: `{"age": 36, "time_trying": "2 years"}`
- flags: `{}`
- gate: allow_booking=`False` escalate=`False` notes=`no link: not_enough_context`
- playbooks: `returning_prospect, low_amh_es, unexplained_infertility_es`
- action: `REPLY:warm_prospect`  pause: `False`  reason: `None`

</details>

**Conversation ran to the end of the script; the AI never paused.**

---

## Verdict

**PASS**

- Spanglish is read as Spanish on all three turns and she is not ejected. It picks Spanish and stays in it rather than mirroring the switch.
