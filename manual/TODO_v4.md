# Manual v4.0: work list

Source of truth: `manual/The_Fertility_Solution_DM_AI_Operating_Manual_v4.0.md` (docx beside it).
References are to the manual's own numbering: lettered sections are the "Version 4 Current Business
Rules" block, numbered ones are Part 1, `2A §n`, `2B.1 §n`, `2B.2 §n`, `5.n`, appendices by letter.

Live code: `prompts_simple/*`, `few_shots/*`, `app/services/{dossier,brain,cta}.py`, `app/worker.py`.
Fix in prompts and few-shots first. Python only where a gate decides what the writer is given.

## 0. Before anything

- [x] **Review the v4 manual** (Asjad). Everything below waits on this. Mark anything you disagree
  with here before it is built.
- [x] **Reply to Sonia with the exact delivery date and time.** She asked for it in the v4 email and
  Appendix E repeats it.

## 1. Cleanup

- [x] **Remove `/apply`.** No DM stage uses it (G and 5.4 list it, only Appendix D email uses it).
  Drop `apply_link` from `app/api/admin/router.py:38` and the comment in `app/services/prompts.py:69`.
  New migration deletes the `apply_link` row. Same migration can drop the dead `price_range_es` row,
  still `$1,500 a $14,000` and read by nothing.
  Done: `d8f3b0e5a2c7` deletes `apply_link`; the settings field is gone too. `price_range_es` was
  already deleted by `r8s9t0u1v2w3`.
- [x] **Remove the manual-as-prompt option.** Delete `_manual_write_prompt`, `MANUAL_LAYER`,
  `_FACT_KEYS`, `_GATED_FACTS` and the `write_prompt == "manual"` branch in `app/services/prompts.py`.
  `LEGACY_DIR` then has no reader, so delete `prompts/` as well.
  Done. Also dropped the dead `_SAFETY_PROMPT` copy in `reader.py` and the tests that pinned the
  deleted `prompts/70_read.md`.
- [x] **Fix stale pointers.** `CLAUDE.md` says behaviour lives in `prompts/00-60_*.md` and that
  `current_feedback/` is the source of truth. Point it at `prompts_simple/` and `manual/`. Comments
  in `dossier.py` still cite `70_read.md`, `20_boundaries.md`, `60_contract.md` and "v2.1 §".

## 2. Program facts (knowledge)

- [ ] **Put the Part 5 facts in front of the writer.** New always-on section in
  `prompts_simple/knowledge.md`: 6 months for both programs, TFS 16 modules and TPS 18 with titles,
  the tier table (Full, Group, Self paced), group frequency (TFS 2 a week, TPS 1 a week), session
  format (up to 2 x 20 min a month, video or phone), unlimited texting, meal plan and daily hormone
  tracker review as Full TFS only, Facebook community, pregnancy transfer at no cost, continuation
  $600 a month (never lead with it).
  Manual: D, H, 5.1, 5.2, 5.7.
- [ ] **Delete "You have no policy on refunds, payment plans or program length"** from
  `write.md:163`. Length and payment plans are now known. Keep the general rule: anything not in
  KNOWN FACTS goes to the team. Start dates are not documented (5.7), same rule.
  Manual: 5.7, 5.10.

## 3. Positioning and voice

- [ ] **Rewrite WHAT YOU DO** (`write.md:23-33`) around DETOX, NOURISH, FLOW and the approved program
  explanation. Drop "You work alongside her medical care" and the "alongside the clinic, not instead
  of it" example. Medical scope only when her question makes it relevant.
  Manual: C, Part 1 §4 and §5, 2B.1 §2, J.
- [ ] **Vague-answer rule.** When she says it's vague: concrete topics from her concerns plus the
  support level. Never "prioritize what matters" / "connect the pieces" / "put it into practice" as
  the whole answer. Add to `write.md`, and to `turn.md` `has_other_provider`, which currently
  prescribes exactly those phrases.
  Manual: C, I, Appendix E "Positioning and vague answers".
- [ ] **Relax the banned-words list** (`write.md:255`). "Holistic", "optimize", "personalized
  approach", "whole body" are allowed when explained concretely, never as filler.
  Manual: C, 2B.2 §19, A.3.
- [ ] **Full positioning line.** "Sonia by your side every step of the way" for Full only, backed by
  the real contact it means, never for Group or Self paced.
  Manual: C.

## 4. Pricing and the paid-program warning

- [ ] **Exact tiers.** Replace the `pricing` block in `knowledge.md` (and `price_range` config) with
  Full $7,200, Group $3,800, Self paced $1,500, same for both programs. Half now and half in 30 days at
  no extra cost ($3,600 / $1,900 / $750 twice). Longer plans: team quote, usually costs more. The
  range may open a reply but never replaces a tier comparison she asked for. No discount (the Appendix
  D Black Friday offer stays out of DMs).
  Manual: H, 2B.2 §6, 5.3.
- [ ] **Remove the paid-program disclosure gate.** `paid_not_disclosed` in `dossier._booking_blocked`,
  `reason_paid_not_disclosed` in `turn.md`, the "Before any call: she must know it is paid" rule and
  its example in `write.md:79` and `:92-94`, `understands_paid_program` in `read.md:119` and in
  `dossier.render`.
  Manual: 2B.1 §11 and §15, 2B.2 §7.
- [ ] **Value objection.** Answer with curriculum depth and the support in the tier being discussed,
  not "you'd be paying to know what matters". Rewrite `write.md:96-99`.
  Manual: I.

## 5. Medical boundaries

- [ ] **AMH example.** `write.md:139-141` still refers her to the doctor in its first reply. Replace
  with the v4 pattern: validate, general education, one question. The boundary only for an actual
  prognosis or interpretation request.
  Manual: J, Part 4 "Fear about low AMH", 2B.2 §5.
- [ ] **Hormone monitoring question.** "Can you monitor my hormones" gets the Full TFS answer, not a
  refusal. Note in `write.md` WHAT YOU DON'T GIVE that this is a coaching inclusion, not the DM reading
  results.
  Manual: 2B.2 §5, 5.7.
- [ ] **Verify** metformin-without-a-request and lab requests behave as v4 says (fixed last round,
  re-check against the new wording).
  Manual: J, Part 4 "Mentioning medication".

## 6. One-word openers

- [x] **Welcome any standalone opener, not only listed keywords.** Keep the configured list as the
  fast path in `cta.py`. For an unlisted single word on an untouched conversation, let the brain run
  and give the writer a `keyword_opener` turn note with the section O welcome. Overrides stay with the
  reader: STOP, unsubscribe, a person, a price word, "yes" mid-conversation, pregnancy context.
  Manual: O, Appendix E "Keywords".
  Done differently: no list, no model. Any one-word first message gets `cta_welcome_message`
  (`brain.is_opener`). `cta.py`, the keyword list and `cta_keywords` are gone (`e9a4c1f6b3d8`).
- [x] **Welcome line.** The seeded `cta_welcome_message` asks 2 questions with 🤍. v4: "I'm so glad
  you reached out ♡ How long have you been trying to conceive?" Change it in admin settings or with a
  migration.
  Done: `e9a4c1f6b3d8` sets it; edited on the admin Welcome tab.
  Manual: O, Part 4 "Unknown keyword".

## 7. Age

- [ ] **48 and over goes to review before the link, never rejected.** In `dossier.py`: delete the
  `age_over_48` block, `_REASON_TAGS["age_over_48"]`, and the 46 to 48 `age_needs_review`. New rule:
  fertility prospect aged 48 or over, at the turn the link would open, hands over with the review
  acknowledgment. 47 triggers nothing. Not applied to a pregnant TPS prospect. Delete
  `reason_age_over_48` from `turn.md`.
  Manual: B, 2B.1 §9 and §10, 2B.2 §7, 5.7 "women over 40", Appendix E "Age thresholds".

## 8. Handoff

- [ ] **One acknowledgment on every review.** New config `handover_message_review` = "Thank you for
  sharing this with me ♡ We'll take a closer look so we can give you a thoughtful, personal
  response." Make it the default line in `HANDOVER_MESSAGES` (`dossier.py:62`) for every reason except
  `crisis` and `urgent_medical`, which keep their safety lines. Replaces the silent handovers.
  Manual: F, 2B.2 §13, Part 4 "Review acknowledgment".
- [ ] **Team destination is the ManyChat human-takeover tag** (`HUMAN_REVIEW_TAG` in `brain.py:40`).
  The team filters by it. Nothing to build for routing. For the review reason and an agreed attendance
  exception (2B.2 §13 asks for both), proposal: set a ManyChat custom field with the reason alongside
  the tag. Decide whether that is worth it or the team reads the history.
  Manual: 2B.2 §13, 5.5.
- [ ] **Verify the lifecycle.** One acknowledgment, tag added, AI silent while paused, "thanks"
  after it gets nothing, resumes only on the ManyChat resume. Routing failure: `add_tag` failing must
  leave the lead paused and logged.
  Manual: F, 2B.2 §13, Appendix E "Handoff lifecycle".
- [ ] **A request for a person hands over immediately.** No disclosure or confirmation first. A "yes"
  to the disclosure offer must read as `asked_for_human`. Check `read.md` and `safety.md`.
  Manual: F, 2B.2 §13.

## 9. Partner at booking

- [ ] **Strong encouragement with the link.** Replace `turn.md` `partner` note ("only if she has
  mentioned one") with the approved wording, both programs, same-sex couples included. Known solo:
  invite her alone.
  Manual: P, 2B.1 §12, 2B.2 §7.
- [ ] **Pushback and exceptions.** One question if she pushes back ("Do you make these decisions
  independently..."), never asked twice. Encourage a shared time first, then the exception wording if
  she decides alone or the partner truly can't attend. New reader flags for "decides independently"
  and "partner can't attend"; a dossier slot keeps the agreed exception for post-booking.
  Manual: 2B.1 §12, 2B.2 §8.
- [ ] **Donor sperm is not a relationship status.** `read.md:57` has `donor_sperm` as a
  `partner_status` value. Split it into its own fact so a partnered couple using donor sperm gets the
  partner wording.
  Manual: 2A §6, 2B.1 §12, 5.7.

## 10. Pregnancy booking

- [ ] **Same booking link for TPS.** Today she gets no link and her wanting to join is a handover
  (`wants_to_join_pregnancy_program`, the `pregnancy_program` block reason). v4: same consultation link,
  tell her to note on the form that she is pregnant and seeking pregnancy support. Remove the
  handover, open the link, update `turn.md` `pregnancy_support`.
  Manual: D, 2B.2 §7.
- [ ] **TPS facts in replies.** 6 months, 18 modules, weekly pregnancy group in Full and Group,
  private sessions and texting in Full only. `write.md:178-180` says "weekly group coaching and private
  coaching" for everyone.
  Manual: D, 5.2.

## 11. After booking

- [ ] **Booking with no email.** The worker only wakes a `qualified_link_sent` lead for a message
  with an email (`worker.py:50`), so "booked for thursday!" gets nothing and she is never asked.
  Let a booking statement through too (reader flag or a small check), same in the sandbox
  (`chat.html:536`).
  Manual: 2B.2 §8.
- [ ] **Preparation message and confirmation.** Rewrite `write.md:113-123`: ask the email if not
  given, the approved video line, the confirmation text as its own paragraph, "my team", no Natalia,
  never "masterclass" or "replay", never claim the booking is verified. Rename the `post_booking`
  block in `knowledge.md` to "Preparation video". Remind shared decision makers only if not settled;
  carry an agreed exception.
  Manual: G, 2B.2 §8, 5.4, 5.5, Appendix E "Booked call preparation".

## 12. Testimonials

- [ ] **Appendix C as approved proof.** Add the 14 documented records (name, outcome, documented
  history) to `knowledge.md`, used only when she asks about results or women like her. Facts as
  written, no causation, no prediction. Lets a PCOS question cite Anna, Camila, Katrina or Marlies
  instead of the generic "I've supported many women". Loosen `write.md:159` "Never invent a client
  story" to "only the documented ones".
  Manual: Part 1 §16, 5.9, Appendix C.

## 13. Emoji

- [ ] **Allow ♡ in Sonia's own warm lines.** `write.md:269` says emoji only if she used one, but v4's
  approved welcome, review acknowledgment and pregnancy example all carry ♡. Allow it sparingly for
  warmth, celebration and the fixed lines.
  Manual: O, F, Part 4 examples.

## 14. Few-shot contradictions

Rewrite after review. What each file contradicts:

- [ ] `qualification`: "This is a paid program, and it does require your participation" (2B.1 §11);
  price range instead of tiers (H); "I'm a coach. Not a doctor, not a clinic" as the answer to how it
  works (C, J); "rather than a medical intake" (J); partner line at the link not the approved wording
  (2B.1 §12).
- [ ] `qualification_listening`: "It runs alongside your clinic, I'm a coach, not a doctor" (J);
  "it's a paid program and it asks for real commitment" (2B.1 §11); price range (H); "not a medical
  appointment" (J, named outright); partner wording (2B.1 §12).
- [ ] `qualification_money`: price range (H); "is the bottom end watered down?" answered with "my team
  will go through what's included" when the tiers are now known (5.2, Sonia's 24 Sep point 7); partner
  wording (2B.1 §12).
- [ ] `qualification_ready`: partner wording at the link (2B.1 §12); no post-booking turn to show the
  new sequence (2B.2 §8).
- [ ] `terminal_out_of_scope`: "I only take on women up to 48" (B, 2B.1 §10). At 49 she now gets
  the review acknowledgment and a person, not a no.
- [ ] `direct_answer_pregnancy`: TPS described as private coaching for everyone (D, 5.2); ends in a
  handover where v4 sends the booking link with the form note (D, 2B.2 §7); "My team can go through
  how he can be involved" where the partner rule applies to TPS too (2B.1 §12).
- [ ] `nurturing_pcos`: "Your husband's health matters too" before she mentions a husband (2A §7,
  Appendix E "Unknown context"); "what would you do differently" without DETOX, NOURISH, FLOW (C);
  generic proof where Appendix C has PCOS stories (5.9).
- [ ] `nurturing`: "connect the different pieces, understand what should be prioritized" as the
  whole explanation (C); "what kind of thing do you look at" answered without the method (C).
- [ ] `nurturing_endo_male_factor`: "I've supported many women with it" for endometriosis, which is
  not in the approved list (Part 1 §16) and has no Appendix C record. Use the general line or nothing.
- [ ] `direct_answer`: AI disclosure paraphrased, not the approved wording (F).
- [ ] `terminal`: a former client answered by the AI while the gate hands `is_former_client` to a
  person. Not a v4 change, but the example and the gate disagree (2B.2 §11). Decide which is right.
- [ ] **Gaps, optional.** No example shows: a tier comparison, post-booking (email, video,
  confirmation), a partner pushback and exception, a TPS booking, or an unlisted one-word opener.

## 15. Regression (only when asked)

- [ ] **Appendix E run.** Every scenario with enough follow-up turns to show repeats and loops, plus
  the earlier 18 points. Per scenario: input and output transcript, pass or fail, issue, fix. For
  handoffs: the ManyChat tag, pause state changes, history visible to the team. State the deployed
  manual version (v4.0) and the delivery date.
  Manual: N, Appendix E.
