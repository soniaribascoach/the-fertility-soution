# Client history

A condensed record of the review rounds with Sonia. It replaces the loose emails, drafts and
trackers that used to sit in the repo root.

## Timeline

**2 Sep: first stress test of brain v2 (18 points).** Memory, boundaries and crisis routing were
good. The voice was dry, the AI asked age by default, qualification overrode the conversation, the
positioning was generic, it sounded clinical, it denied that pregnancy coaching exists, it flagged
normal grief as suicidal, the links were wrong, and the price was out of date. She asked for an
architecture diagnosis before any more patching.

**Our diagnosis.** There were 2 root causes. (1) Every conversation went through one booking funnel
with age first. (2) Voice was defined by banned phrases plus one approved paragraph. Of the 18
points, 5 were our defects (1, 3, 7, 10, 12). The rest were manual reversals, facts the manual never
contained, or rules in the manual that conflict with each other.

**3 Sep: she approved it and sent manual v2.0.** Decisions:
- Classify the conversation first (terminal, direct answer, nurturing, qualification) and only run
  qualification when it is called for.
- Age is a boundary check, not a precondition.
- If asked, the AI says it is AI and offers a human. It only hands over if she says yes.
- Price range is $1,500 to $7,200.
- DHEA dosing goes to her doctor.
- AMH is not an egg quality measure.
- Social proof is "nearly 2 decades" and "700+ babies".
- Use digits for numbers.
- There are no real DM threads in her voice. The VA threads are the old copy-paste script and must
  not be used as voice training.

**12 Sep: manual v2.1** reconciled v2.0 into the brain (commit `a0339aa`). v2.1 is now the source
of truth and lives in `current_feedback/`.

**Round of 3 example conversations.** She rewrote them line by line. Her rewrites are in
`few_shots_revised/qualification`, `direct_answer` and `nurturing`.

**Round of 6 more examples** (PCOS, endo plus male factor, former client who has stopped trying,
49 with donor eggs, pregnancy, returning prospect in Spanish). She reviewed them and asked for:
- Simple, warm, direct replies. No clever or commanding lines. Not every reply needs an insight, a
  question or a closing line.
- "your doctor", not "your consultant".
- Don't keep reciting her age, treatments or years trying back to her.
- 700+ babies is an overall figure. Never use it as proof for a specific condition.
- Never invent program details, refund terms, eligibility rules, outcomes or processes.
- Treat "I booked" as her claim, not as a verified booking.
- Don't claim to remember a former client personally.

Her edits are applied in `few_shots_revised/`.

## Few-shot rebuild (in progress)

Plan:
- `few_shots_revised/` replaces `few_shots/`.
- Aim for 8 to 10 dense conversations, sent on every turn.
- Delete the selection layer (`select_playbooks`, scoring, tags).
- Keep `reader.py` and `dossier.gate` as the hard guarantees.
- Every claim has to trace back to a section of the manual or one of her emails.

9 files are written. Topics still uncovered: recurrent loss beyond the terminal case, and the
pressure conversation that ends in a handover (POI plus Hashimoto's).

## What she asked for next

Run the full 18 point regression plus the new scenarios, then send one review pack:
- the revised examples
- real generated conversations
- the result of each check
- a statement of what is live and what is still being tested
- one list of business decisions

## Open items

Waiting on Sonia (business decisions):
1. What each support level includes (section 5.2 of the manual is an empty template).
2. Refund and payment plan terms.
3. Whether a donor egg pregnancy she carries herself is in scope. The manual only excludes donor
   egg *services*.
4. Surrogacy: whether she coaches the intended mother.
5. Whether there is a real process for booking when the link fails, or only a team handoff.
6. Whether the booking form needs a pregnancy option.
7. Whether the AI will ever have former client records.
8. Whether the masterclass link should be `/apply` or `/register`. Section G says `/register` and
   her 2 Sep email says `/apply`.
9. Whether to build a real push alert on handover. Today paused conversations sit in an admin
   queue nobody is notified about, while the crisis line says "I'm telling my team".

On our side:
- Prod has not run `alembic upgrade head`, so it still quotes $14,000.
- `tests/test_brain_offline.py` still pins the old price range.
- The regression scripts in `manual_testing/` are staged for deletion. Restore them or replace them
  before the regression run.
