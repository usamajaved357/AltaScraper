# Lessons -- bug classes and their permanent prevention

BUG -> LESSON -> PREVENTION (owner, 29 Sep 2026). This is NOT a second bug
tracker: each bug is still recorded where it always was (docs/known-issues.md,
the fix commit, its regression test). This file holds only the CLASSES --
patterns that more than one bug has shown -- and what now stops the class, so
a future feature applies the lesson without anyone remembering it.

HOW IT IS USED
1. Fixing a meaningful bug: record it in docs/known-issues.md with symptom,
   root cause, affected feature, evidence, fix and verification; add a
   regression test where practical (test_lessons_register.py requires a FIXED
   entry dated from 29 Sep 2026 on to name one, or a browser check).
2. Ask: "one bug, or a broader pattern?" If an existing class below fits, add
   the bug to its Evidence. A NEW class needs evidence of more than one bug --
   no rule per individual bug.
3. When the evidence supports it, turn the class into a prevention: an
   architecture-guard rule (tools/arch_rules.py), an automated check, a
   reusable test, a reviewer checklist item, a build-feature rule or a doc rule.
4. Building a feature: read "Applies when" below; every class that applies
   gets its prevention used (and the change-reviewer checks it).

Every class names only evidence that exists (commits, known-issues entries);
test_lessons_register.py checks each named prevention file exists and each
rule named is a real guard rule. Status: PREVENTED (a check catches the class),
PARTIAL (a check catches part of it; the gap is written down),
DOCUMENTED (tests per instance only -- no class check yet).

---

## L-open-account-fallback
- Pattern: code acts on the server's ONE open account (whichever tab switched last) instead of the account the request or job names -- one company's data or action lands on another's.
- Evidence: cd767fc (handling time recorded on the open account); 943fb60, deb7329, b0a9c6d (preview queue, image batch, ASIN monitor with no account); 50eea56 (tracking routes); known-issues "Fixed on the development branch" batch 2 (two-tab crossings).
- Prevention: test_account_scope_audit.py, test_guard_every_account.py, test_id_or_open.py, test_jobs_name_their_account.py, test_loops_pin_account.py, test_architecture_guard.py (rule background-open-account), tools/browser_smoke.py
- Status: PARTIAL -- routes still hold 47 capped open-account reads (the ceiling only goes down); known-issues #4 (runs that name no account) is open.
- Applies when: a feature reads or writes one account's data, starts a job, or adds a route.

## L-stale-state-after-switch
- Pattern: after an account switch the browser keeps, or paints late, the previous account's data.
- Evidence: 3131451 (two caches crossed accounts); 32e1cb0 (product picker); f3c5d02 (product page stayed open); known-issues Suspected #5.
- Prevention: test_switch_drops_old_replies.js, test_frontend_review_fixes.js, tools/browser_smoke.py
- Status: PARTIAL -- a NEW account-keyed browser cache not registered in screenstate's reset fails no test; browser_smoke (the broad check) is not in run_tests.py; the Sales double marker has no recorded root cause.
- Applies when: a screen keeps account data in browser memory.

## L-code-vs-data-folder
- Pattern: data written or read beside the CODE instead of beside the settings (CONFIG_PATH) -- fine locally, lost or unseen on the server (/app vs /data).
- Evidence: dfaf0dd (generator and sp_diagnose used a bare config.json); 50eea56 (run heartbeat written in the code folder, read from the data folder).
- Prevention: test_architecture_guard.py (rule config-path-literal), test_run_status_location.py, test_subprocess_config_path.py
- Status: PARTIAL -- a data path built from `__file__` is not detected.
- Applies when: a feature writes a file, or starts a process that does.

## L-silent-failure
- Pattern: an exception swallowed around a write, so a failure looks like success for weeks.
- Evidence: 41136a8 (record_action raised TypeError, swallowed: no manual price was ever recorded); 7458fa4 (three "who did it" lookups that could only answer ""); known-issues batches 8-9 (/submit/precheck never fired).
- Prevention: test_architecture_guard.py (rule swallowed-write-failure), test_price_apply_refuses.py, test_who_labels.py
- Status: PARTIAL -- 66 legacy swallowed writes are baselined (they only shrink); failures swallowed around non-write calls are not detected.
- Applies when: a feature catches an exception around a write.

## L-duplicate-drift
- Pattern: the same concept written in several places; one copy is fixed or extended and the others silently disagree (Rule 12).
- Evidence: d8900e4 (image push lacked the marketplace selector another copy had); 981a8cc (four getOrderItems reads, one paged); aef65ba (five price sends); e0583f7 (identical scope resolvers).
- Prevention: test_architecture_guard.py (rule duplicate-function), test_order_items_one_read.py, test_price_send_one_place.py, test_one_anthropic_constructor.py, test_scope_shared_resolvers.py, test_global_name_clashes.py
- Status: PARTIAL -- identical bodies are caught; drifted near-copies are not (known-issues lists the open ones).
- Applies when: a feature needs a concept that may already exist (search first -- Rule 12).

## L-dead-permission-rule
- Pattern: a permission rule that reads like protection but is never consulted -- the guard lets a GET read through on the feature's view level before RULES.
- Evidence: master audit C4 (GET /run/api_submit open to a view-only user, fixed in Milestone 2); ef83115 (/run/stack's "edit" not enforced until it was treated as work).
- Prevention: test_guard_rules_effective.py
- Status: PREVENTED -- every route x method with a declared permission that a view-only user passes must be listed with a reason, or it fails.
- Applies when: a feature adds a route or a RULES entry, especially a GET that does work.

## L-payload-regression
- Pattern: a change to what the app sends Amazon alters a listing's payload (Rule 1 / Rule 4).
- Evidence: known-issues Rule 1 history (automatic GTIN exemption); d8900e4 (image PATCH shape).
- Prevention: test_build_api_attributes_golden.py, test_rule1_holds.py, test_rule1_listing_mode.py, test_defaults_carry_no_identity.py
- Status: PARTIAL -- new-listing payloads are byte-pinned; live PATCH shapes (images, /optimize/push) are not.
- Applies when: a feature touches anything sent to Amazon (and it goes to listing-payload-guardian).

## L-money-safety
- Pattern: a price or money figure accepted or computed without the one shared rule.
- Evidence: 41136a8 (price apply accepted 0, negative, NaN); a0d07ba (unanswered VAT saved as 0%); 1c9c620 (money landing lost); known-issues "Profit screens disagreed".
- Prevention: test_price_apply_refuses.py, test_price_send_one_place.py, test_vat_unanswered_survives.js, test_profit_agreement.py
- Status: PARTIAL -- /optimize/push writes a price outside the shared rule (known-issues "Price writes").
- Applies when: a feature reads, computes or writes a price or money figure.

## L-silent-format-assumption
- Pattern: an unstated assumption about a format or default (case of a SKU, a missing ASIN, a default product type) silently gives a wrong answer.
- Evidence: 1c9c620 (same SKU in two cases across Amazon APIs); 0d1d5c8 (queued row lost its ASIN, drafts defaulted to HOME); fd15fac (catalogue-match error read as a bad value).
- Prevention: test_cogs.py, test_queued_row_keeps_asin.py, test_catalogue_conflict.py
- Status: DOCUMENTED -- tests per instance; no class check.
- Applies when: a feature matches, parses or defaults a value from Amazon or a sheet.

## L-authorization
- Pattern: a permission added or checked in only one place, or a record written before a permission existed.
- Evidence: 28a06a5 (a later permission read as "denied"); known-issues Suspected #1 (a lister could submit).
- Prevention: test_guard_every_account.py, test_permission_versioning.py, test_no_esc_in_handlers.js, test_guard_rules_effective.py
- Status: PREVENTED
- Applies when: a feature adds a permission, a route, or an inline handler.

## L-undefined-name
- Pattern: code that refers to a name defined nowhere, found only when that path runs.
- Evidence: known-issues Suspected #2 (_state_account never defined).
- Prevention: test_no_undefined_names.py, test_no_undefined_js_calls.js
- Status: PREVENTED -- for names; not for attributes or keyword arguments (see L-silent-failure's 41136a8).
- Applies when: always (every run of the suite).
