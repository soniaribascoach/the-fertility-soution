# The Fertility Solution

Instagram DM AI representing Sonia Ribas. FastAPI + a three-stage brain in `app/services/`:
`reader.py` extracts facts, `dossier.py` merges them and gates what the writer may see,
`brain.py` writes the reply. Behaviour lives in `prompts/*.md` and `few_shots/*`, not in Python.

## Writing rules

**Never use em dashes (—) or en dashes (–).** Anywhere: prompts, few-shot conversations, code
comments, docstrings, UI copy, commit messages, PR bodies. Use a comma, a full stop, a colon, or
brackets instead. Rewrite the sentence if none of those fit.

This is not only style. Every `prompts/*.md` and `few_shots/*` file is model input, so a dash in
those files teaches the AI to produce them, and an em dash in an Instagram DM is one of the clearest
tells that a message was not typed by a person.

Hyphens in compound words (`whole-body`, `low-AMH`) are fine. ASCII `--` in shell flags is fine.

Two carve-outs, both for the same reason: the text is a record, not something we are writing.

- `alembic/versions/*`. Already applied, so the file is history. Do not rewrite a migration to
  satisfy a style rule.
- `manual_testing/runs/*` and `manual_testing/FINDINGS*.md`. These are captured model output. A dash
  in a transcript is evidence that the AI produced one, which is exactly what we want to see.

Everything else should be clean:

```
grep -rn "[—–]" --include="*.py" --include="*.html" --include="*.md" . \
  | grep -v "alembic/versions\|manual_testing\|current_feedback\|.venv"
```

## Where behaviour is defined

- `prompts/00-60_*.md`: the writer's system prompt, layered. `70_read.md` is the extractor.
- `few_shots/*`: complete example conversations, first message to final outcome. Selection is by
  the intent and tags the reader returns (`app/services/few_shots.py`), never by regex on her prose.
- `current_feedback/`: the Operating Manual, the source of truth for all of the above.

Prefer changing a prompt layer or a few-shot conversation over adding Python. Gates in
`dossier.py` decide what the writer is *given*; nothing inspects generated text after the fact.

## Few-shot conventions

Every scenario file needs at least one arc that does **not** end in `{{booking_link}}`.
`Playbook.render` drops booking arcs on turns that may not offer a call, and `select_playbooks`
discards anything that renders empty, so a booking-only file disappears from the majority of turns.

A counter-example teaches too. Never write the forbidden thing out in full under `DO NOT WRITE
THIS`: a dose, a food, a tip, a phrase that must not be said. It gets copied into replies. Describe
the shape of the mistake and say why no example is written down.
