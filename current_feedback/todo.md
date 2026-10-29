# Go-live todo (Oct 28 email)

Source is `current_feedback/email_28_oct`, Sonia's testing of build `602d087` (v4.4). **§n** is
section n of her email. Earlier todos are in git history.

**Pattern:** behaviour lives in prompts and few-shots, gates in `dossier.py` decide what the writer
is given. Rebuild the writer's input before any edit. Net word count down.

## Progress

- [x] 1 Partner exception still asks for a time both can attend (fixed Oct 28, retested)
- [x] 2 "Are you Sonia or an AI? I want a human" gets no identity answer (fixed Oct 28, retested)
- [x] 3 No "Full", no levels unless she asks (small fix Oct 28; pricing contradiction to Sonia)
- [x] 4 Supplement line translated for Spanish leads (done Oct 28, retested)
- [ ] 5 Freebie automations first, AI picks up her answer (MEGAN): server done Oct 29, ManyChat next
- [ ] 6 Follower welcome (built Oct 29, trigger off), existing automations checked
- [ ] 7 Deploy, acceptance on the deployed build, Instagram evidence
- [ ] 8 Go live: allowlist off, launch time in Pacific
- [ ] 9 Manual and one consolidated reply to Sonia
- Later: TikTok financial qualification before the link, plus partner attendance or exception.

---

## 1. Partner exception still asks for a time (§3)

- **Her test, first message:** "I'm 39, trying for two years, ... he truly cannot attend any call
  because of his work. Can I attend alone?" Reply gave the exception and the link, then "Could you
  choose a time you can both attend?".
- **Root cause:** `read.md:79` set `confirmed_cannot_attend` only after Sonia asked for both, so
  her first message stayed `cannot_attend` and `partner_invite` (`turn.md:65`) asked for the
  attendance line, while `knowledge.md:114` said give the exception once she confirms. Writer did
  both. Repro Oct 28: 1 of 4 her exact reply, 4 of 4 no label on the link turn.
- **Done (Oct 28, not committed):**
  - `read.md:79`: confirmed is "truly can't attend any call", or still can't after being asked.
    +4 words.
  - Side effect found and closed: "truly can't" can now come before the link is open. The note
    would fire with no approved wording and the label would be lost. `_attendance_note`
    (`brain.py:151`) now fires only when the attendance block is open, and `attendance_told`
    remembers it was given (it used to compare with the previous turn).
- **Retest (Oct 28):** her message 3 of 3 pass (exception plus link, no second ask, label on the
  link turn, preparation keeps it). Early "truly can't" then booking 2 of 2: approved exception and
  label at the link. e32, e33, "is it ok if I come alone?" unchanged (attendance line, then
  exception). Offline tests 116 pass.
- [ ] Still open: before the link the writer answers "can I come alone?" in its own words ("Yes,
  absolutely"), and the approved exception follows at the link. Same family as "does he have to be
  on the call?". Pre-existing.

## 2. AI identity plus human request (§3)

- **Her test:** "Are you Sonia or an AI? I want to speak to a human" got only the review line.
- **Root cause (Python):** `asked_for_human` hands over (`dossier.py:48`), a handover never calls
  the writer (`brain.py:303`), so the `asked_if_ai` note (`turn.md:18`) never runs. Repro 2 of 2.
- **Done (Oct 28, not committed):** new fixed line `handover_message_ai_human`: "You're chatting
  with Sonia's AI assistant right now." plus the review line. Chosen in `dossier.gate` when she
  asks for a person and asks about AI for the first time. Migration `c7e2a9d4f1b6`, admin field,
  `regress.load_cfg`.
  - Side effect found and closed: `asked_if_ai` is sticky, so e40's "yes please" after the full
    disclosure would have repeated the identity sentence. Only a first ask counts.
- **Retest (Oct 28):** her message 2 of 2, "is this a bot? i want a real person" pass. e38, e39,
  e40 ("yes please" gets the review line only), e41 unchanged.

## 3. No "Full", no levels unless she asks (§1)

- **Ask:** say "The Fertility Solution" or "my fertility coaching program", meaning Full. Don't call
  it Full or introduce a menu of levels, unless she asks about options or brings them up.
- **Scope:** only the unprompted level talk in descriptions and booking. Pricing, the reader and the
  gate are unchanged (first gate approach reverted Oct 28).
- **Reproduced (Oct 28, 8 openers, reverted code):** 8 of 8 mentioned levels unprompted, copied from:
  - `write.md:37` "with different levels of support depending on how closely you want to work with
    me", also in few-shots `direct_answer_levels:9`, `qualification:23`, `qualification_listening:39`.
  - "In my Full program" in `write.md:43` and few-shots `qualification:17`, `nurturing:45`,
    `qualification_age_review:15`, `direct_answer_levels:13`.
  - "which level fits" in the booking line of 4 few-shots (`qualification_ready:9` and others).
  - `knowledge.md:22` "come at 3 levels", and the levels list headed by "Full:".
  - `write.md:98` "Which level fits her ... ask that once".
- **Done (Oct 28, not committed):** those phrases deleted or swapped in place, Sonia turns only, no
  lead turns changed. `knowledge.md`: the Full bullet is now "What the program includes"; Group and
  Self paced listed "only after she names one or asks whether there are other options". Words:
  `knowledge.md` -7, `write.md` -36, few-shots about -100.
- **Retest (Oct 28):** describe and "how do I book?" clean (4 of 4), "what does your program
  actually do?" clean. Named levels (e03, e04, e08) answered with Full, Group, Self paced correctly.
  "What does your program include?" 1 of 3 clean, 2 of 3 call the extras "the Full level" (no menu).
- **Contradiction, for Sonia:** her approved first price reply ("We have a few different options
  depending on how much support you'd like ... talk through the options and pricing together") and
  the range line ("$1,500 for self paced access to $7,200 ..., with a group option in between")
  introduce the levels, and manual Appendix E expects levels and all 3 prices in pricing replies.
  Those are left as approved. Draft for the reply:
  > The AI now calls it The Fertility Solution or your fertility coaching program and only brings
  > up other levels when she asks. One thing to decide: your approved first price reply ("We have a
  > few different options depending on how much support you'd like...") and the price range line
  > both introduce the levels, so pricing still mentions them. Would you like new wording for those
  > two, or should pricing stay as it is?

## 4. Supplement line in Spanish (§1)

- **Done (Oct 28, not committed):** `knowledge.md:30` "word for word in English and translated
  naturally in Spanish", same as `pricing_offer`.
- **Retest (Oct 28):** Spanish ask gets the line translated, plus the English materials notice.
  Plain ask and ask inside a longer message: word for word.
- [ ] Watch: "which supplements for low AMH?" got the approved line appended 1 of 5 (0 of 4 on
  rerun). Nothing named in any run.

## 5. Freebie automations (§2)

- **Ask:** a trigger word that matches an active freebie automation (channel and entry point) runs
  that flow, with no AI reply. Her answer to the flow's question goes to the AI, which knows the
  resource, the messages sent and the question, and doesn't restart or repeat it. No match: the AI
  handles the word as a normal opener. No duplicate keyword list on our side.
- **First case:** "AMH | Megan Guide | any reel SRC" (Instagram comment, story reply, DM triggers):
  guide offer, name, email, ActiveCampaign, "sent by email", then "how long have you been trying?".
  The answer currently assigns to Reggie Ray. "TikTok | MEGAN | AMH Freebie" is the TikTok one.
- **Priority:** ManyChat decides. Default Reply only fires when no trigger matched, and replies
  inside a flow's input step go to the flow. Nothing to build or register.
- **Done (Oct 29, not committed):** `/webhook` takes an optional `sent` (a string or a list): the
  lines the automation sent her. They are saved to her history as assistant lines with
  `ai_model="manychat"` (`AUTOMATION_SENDER`), then `last_input_text`, if any, runs a normal turn.
  With no text it only records. Automation lines are left out of the stats and of the recent
  openings other leads are compared against. Opt out, pause and `human_handover` apply as for any
  message (worker).
- [ ] ManyChat, Instagram MEGAN flow: after her answer, "If Beta Users" to an External Request
  `POST /webhook`, body `{"contact": {{subscriber_data|to_json:true}}, "last_input_text": <Last
  Text Input>, "sent": [the flow's messages, word for word]}`, else the existing Reggie step.
  `contact` because `ig_id` has no picker field; her answer only counts at the top level. Remove
  the condition at go live (§8).
- TikTok MEGAN stays as it is: TikTok doesn't reach the AI yet.
- [ ] Check overlap with the older active MEGAN story and post flows (same triggers).
- [ ] Test: MEGAN match, an unmatched word, the answer to the question. No duplicate or clashing
  messages, opt out and handover respected.

## 6. Follower welcome and post-reconnect check (§4)

- Sonia refreshed Instagram permissions; "Say hi to new followers" is available, nothing selected.
  Facebook connected, Detox To Replenish excluded, @thefertilitysolution stays disconnected.
- **Checked (Oct 29, Chrome, read only):** Default Reply, Resume AI, opt out, SUMMIT and MEGAN all
  live, no warnings. Resume AI now removes Resume AI and `human_handover` after the call. Opt out
  adds tag `opted_out`. Logs: 14 "Json mapping errors" on Default Reply, `$.reply` not found
  (20, 22, 25 Oct). Harmless: the server returns only `{"status": "ok"}`.
- [ ] Two live SUMMIT automations, "SUMMIT links" and "SUMMIT links copy". Check they target
  different reels, and read the follow-up delay.
- **Built (Oct 29):** "IG | Follower Welcome", attached to "Say hi to new followers". Beta usernames,
  then not `opted_out` and not `human_handover`, 5 minute delay, the welcome with button "Yes,
  let's chat" (tag `welcome_sent`), on tap `welcome_engaged` and the question. Ends there, so her
  answer reaches Default Reply. No reminder.
- [ ] Add an External Request with `sent` after each of the two messages (§5 shape, no
  `last_input_text`), so a one-word answer isn't read as a first message.
- [ ] Switch on its "User follows your account" trigger (still off), then test with a fresh beta
  account.

## 7. Deploy, acceptance, Instagram evidence (§3, §5)

- [ ] Commit and deploy §1 to §4 (migration `c7e2a9d4f1b6` runs on deploy). Run acceptance with
  `--remote` against the deployment so the page shows the running build (it showed `6435d45`,
  live is `602d087`).
- [ ] Add cases: her two messages, Spanish supplement, the 3 supplement cases, "what does your
  program include?", menopause and tubes (perimenopause, one tube, both preparing for IVF, both
  removed, unclear, "both" then "can you help me prepare for IVF?").
- [ ] Instagram evidence, allowlisted account, screenshots: handover received by the team, history
  kept, pause and release, queued follow-up (SUMMIT) suppressed, emergency stop and what it covers.

## 8. Go live (§5)

- Default Reply: `opted_out` stop, then "If Beta Users" (6 usernames) to AI Reply, everyone else
  "Do nothing". Live badge, but testers only.
- [ ] Confirm no other route serves the wider audience.
- [ ] After §7 is green on the deployed build, remove the beta condition from Default Reply, Resume
  AI, the Follower Welcome and the MEGAN handover.
- [ ] Send Sonia the actual launch time in Pacific.

## 9. Manual and reply (§5)

- [ ] Manual (her Google Doc) and deployed prompts: program naming, Spanish supplement line,
  identity before handover, freebie handover.
- [ ] One consolidated reply in her order: fixes with evidence, the §3 pricing question, freebie
  plan and tests, welcome, live status and the allowlist plan, launch time.
