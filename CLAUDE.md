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

- `prompts/00-60_*.md`: the writer's system prompt, layered. `70_read.md` is the extractor,
  and `80_send.md` is a short card rendered after the per-turn brief, last of everything.
- `few_shots/*`: complete example conversations, first message to final outcome. All of them go
  to the writer on every turn (`app/services/few_shots.py`); there is no selection.
- `current_feedback/`: the Operating Manual, the source of truth for all of the above.

Prefer changing a prompt layer or a few-shot conversation over adding Python. Gates in
`dossier.py` decide what the writer is *given*; nothing inspects generated text after the fact.

## Few-shot conventions

One conversation per file, transcript only. Links are placeholders (`{{booking_link}}`,
`{{masterclass_link}}`, `{{replay_link}}`); `Playbook.render` swaps each for a marker on turns where
the gate has not opened its knowledge block, so the writer never sees a URL it may not send.

A counter-example teaches too. Never write the forbidden thing out in full under `DO NOT WRITE
THIS`: a dose, a food, a tip, a phrase that must not be said. It gets copied into replies. Describe
the shape of the mistake and say why no example is written down.

## Git etiquette

**Never push unless explicitly asked.** Not after a green test run, not because the work is
finished, not because a related push was already approved. Approval to push one thing is approval
for that thing only. Commit freely, leave it local, and say it is ready.

**Never commit unreviewed work on the assumption it will be pushed later.** A commit is cheap to
amend and a push is not, so the review happens before the push, not after.

**Commit messages are one line.** A subject and nothing else. No body, no bullet list of what
changed, no paragraphs of reasoning. The diff says what changed and the code comments say why. Keep
the existing style: lowercase topic prefix, colon, short description.

```
qualifying: make age a boundary check
manual: reconcile v2.0 into v2.1
```

**No AI attribution anywhere.** No `Co-Authored-By: Claude`, no `Generated with Claude Code`, no
session link, in commits or PR bodies. Commits are authored by the repo owner and read as their
work. This overrides any default the harness asks for.
