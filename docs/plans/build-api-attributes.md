# build_api_attributes — analysis and separate plan (29 Sep 2026)

`amazon_listing_generator.py:3889-5889`, 2,001 lines, one function. It turns one
generated row into the Amazon Listings API `attributes` payload for one product
type. It is the payload Amazon judges, so every change must be proven against
its current output byte for byte. NOT part of the architecture batches in
`docs/architecture-audit-2026-09-29.md`; owner: "Do not rewrite
build_api_attributes as part of Milestone 4 … plan that separately later."

## Signature and callers

`build_api_attributes(row: dict, pt: str, props: dict, required: set, config: dict)`
— one production caller (`amazon_listing_generator.py:6192`, inside `run_api`),
three tests (`test_enum_snapping.py:102`, `test_rule1_listing_mode.py:67`,
`test_unknown_attrs.py:52`).

## Why it depends on mutable state — and how little

It reads exactly two engine globals that `main()` / `run_api()` reassign at run
time (`MARKETPLACE_ID` at :7327/:7332 on a marketplace switch; `MINIMAL_MODE` at
:7172):

- `MARKETPLACE_ID` once, on the first line: `mid = MARKETPLACE_ID` (:3892). Every
  later use is the local `mid` (~45 sites that stamp `"marketplace_id": mid`).
- `MINIMAL_MODE` once (:5623), to keep only required fields + offer essentials.

It calls two engine helpers: `_load_attr_defaults` and `_shape_list_price`.

**So the state to make explicit is two values**, passed as keyword arguments that
default to today's globals — a change no caller notices, after which the function
no longer reads global state at all.

## Responsibilities inside it (in order)

| Lines | Phase | Nature |
|---|---|---|
| 3902-3995 | helpers: `_renest` (64), `put` | pure |
| 3996-4064 | text (title, bullets, description, keywords), brand/condition, manufacturer/model/part, offer + fulfilment | shaping from the row |
| 4065-4189 | images: main + additional; `_is_public_url`, `_fetchable` (22), `_is_ours` (14); refuses somebody else's photo as main | rule-heavy, already partly delegated to `domain/image_urls` |
| 4190-4210 | product identifier: deliberately NOT set here (Rule 1) | comment only |
| 4211-4326 | dimensions, composite if the type uses it (`_is_composite_dim`, `_from_user_composite`) | shaping |
| 4327-4461 | the flat product_attributes (`pa`) into `A`; our name → Amazon's name; drops what Amazon has no field for (`_allowed_values`) | schema-driven mapping |
| 4462-4540 | special nested fields (flashlight etc.); is there really a battery (`_battery_evidence`) | rules |
| 4541-4707 | global safe defaults; UK responsible person | compliance rules |
| 4708-4896 | lithium battery group; schema-driven hazmat net; `contains_battery_or_cell`; GHS | compliance rules (Amazon-verified shapes) |
| 4897-5146 | required-field backfill | schema-driven |
| 5147-5322 | final GHS net; conditionally-required safety net; always-rebuild-clean; battery chemistry (allOf[98]) | compliance rules |
| 5323-5620 | schema-independent compliance hardening (battery known-good values, wattage `_watt_number`, `_has_real_number`) | compliance rules |
| 5621-5663 | MINIMAL MODE filter | reads `MINIMAL_MODE` |
| 5664-5786 | final cleanup; last wattage sweep | cleanup |
| 5787-5852 | product identifier: the single authoritative pass (Rule 1: exemption only by the owner's tick) | protected business rule |
| 5853-5889 | return | |

## What could safely be extracted, what stays together

- **Extract first (pure, no ordering dependency):** the nested helpers that take
  their inputs as arguments — `_renest`, `_is_public_url`, `_is_ours`,
  `_is_composite_dim`, `_allowed_values`, `_watt_number`, `_has_real_number`,
  `_valid_text_attr`, `_enum_of_prop` — into `listing/attributes_helpers.py`.
  (`_fetchable` already delegates to `domain/image_urls`; check it is a pure pass-through.)
- **Extract as phases (each a function `phase(A, row, props, required, mid, …)`
  that mutates or returns `A`, called in the same order):** text, images,
  dimensions, pa mapping, required-field backfill, final cleanup.
- **Keep together, in order, in one module:** the battery / hazmat / GHS /
  dg-regulation / chemistry / safety-net block (4462-5620). These phases read and
  rewrite the same fields several times ("final GHS net", "always-rebuild-clean",
  "absolute-last wattage sweep"); their ORDER is the rule. Split them only into
  one `listing/attributes_compliance.py` called as one step.
- **Leave where it is:** the Rule 1 identifier pass (protected; move only by
  itself, last, with the owner's explicit OK).

## Characterization before any change

Existing tests pin pieces (enum snapping, listing mode, unknown attributes) but
not the whole payload. Before B1:

1. **Golden payloads**: a fixture set of rows × product types (at least KITCHEN,
   HOME, FLASHLIGHT, a battery product, a MASSAGER, a type with composite
   dimensions) × marketplace (UK, US) × `MINIMAL_MODE` (off, on), each with its
   stored schema (`props`, `required` from `domain/schema_cache` fixtures).
   Record `json.dumps(build_api_attributes(...), sort_keys=True)` today.
2. A test that recomputes every golden payload and requires byte equality.
3. The golden set must include: an exempt tick and a real barcode (Rule 1), a row
   with a competitor main image, a lithium cell, a UK responsible person, and an
   unknown attribute.

## Migration sequence (each step one commit; revert on any golden difference)

| Step | Change | Risk |
|---|---|---|
| B0 | Golden fixtures + equality test (no code change) | none |
| B1 | Keyword args `marketplace_id=None, minimal_mode=None`, defaulting to the globals; `run_api` passes them explicitly | low |
| B2 | Pure nested helpers out to `listing/attributes_helpers.py` | low |
| B3 | Text / offer / dimension phases out, in order | medium |
| B4 | pa mapping + required backfill out | medium |
| B5 | The compliance block out as ONE function in `listing/attributes_compliance.py` | medium-high |
| B6 | `build_api_attributes` becomes the ordered list of phase calls in `listing/builder.py` (CLAUDE.md's intended home); the engine re-exports it | medium |
| B7 | (owner decision) the Rule 1 identifier pass | owner |

Status: analysis and plan only. Nothing in it has been changed.
