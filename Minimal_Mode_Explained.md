# Minimal Mode — How It Works (and the bug that was fixed)

This explains Minimal mode in plain words: what it does, what happens in the
backend when you turn it on, why it was dropping required fields before, and what
the fix changed.

---

## What Minimal mode is for

Normally, when the app builds a listing for Amazon's API, it sends a **full** set
of attributes — the required ones plus lots of optional ones (material, colour,
special features, dimensions, and so on). The more fields you send, the more
chances there are for one of them to be malformed and cause a rejection.

**Minimal mode strips the listing down to the bare minimum** Amazon needs to
create it. You get a basic, live listing fast, then you enrich it later in Seller
Central (add the nice-to-have fields there). It's the "just get it live, I'll
polish later" button.

You turn it on with the **"Minimal mode (required fields only)"** checkbox in the
drawer, next to "Refresh Amazon values."

---

## What happens in the backend when you turn it on

1. **The checkbox sets a flag.** When you tick it and click Preview or Submit, the
   dashboard adds `&minimal=1` to the request. The backend (`/run/api` or
   `/run/api_submit`) reads that and passes `--minimal` to the generator.

2. **The generator flips a switch.** On startup the generator sees `--minimal` and
   sets a module-level flag `MINIMAL_MODE = True`.

3. **The attribute builder runs normally first.** The function that assembles all
   the fields (`build_api_attributes`) does its full job: it builds the title,
   bullets, description, price, images, the required fields, AND the conditional
   safety/battery groups Amazon needs. At this stage nothing is stripped yet.

4. **Then the minimal filter runs LAST.** Right before the attributes are
   returned, a block that only runs when `MINIMAL_MODE` is true goes through every
   field and **removes anything that isn't on the keep-list.** The keep-list is:
   - Amazon's strictly-required fields (from the live schema's `required` list)
   - the offer essentials (title, brand, description, bullets, price, quantity,
     condition, identifiers, country of origin, the main image)
   - **the conditional safety/battery groups** (this is the part the fix added —
     see below)

5. **The trimmed set is sent to Amazon.** The result is a lean payload: only what's
   needed to create the listing. A log line prints how many fields were kept vs
   removed, e.g. `Minimal mode: kept 14 of 41 fields`.

---

## The bug you hit — and why it happened

You used Minimal mode once and it **missed things that were required** — Amazon
rejected the listing for "required but missing" fields that minimal mode had
stripped out.

Here's the root cause:

There are **two kinds of required fields** on Amazon:

- **Static required fields** — these are listed in the product type's schema
  `required` list. The app always knew about these.
- **Conditional required fields** — these are NOT in the static list. Amazon only
  demands them once it detects certain content. The classic example: the moment
  Amazon sees the word "lithium" in your listing, it suddenly requires the whole
  **lithium-battery safety group** (battery details, lithium cell counts, safety
  data sheet, etc.). For a flashlight or a massager with a rechargeable battery,
  these become hard requirements — but they were never in the static `required`
  list.

The old minimal filter kept only `set(required)` — the **static** list. So it
**stripped the conditional safety/battery fields**, because they weren't in that
list. Then Amazon turned around and rejected the listing because those very fields
were now required. That's exactly the "it missed required things" problem.

---

## What the fix changed

The minimal filter now keeps an extra group of fields on purpose — the
**conditional safety/battery/compliance fields** — so they're never stripped even
though they're not in the static required list. Specifically, it preserves any of
these that the builder populated:

`battery`, `num_batteries`, `power_source_type`, `lithium_battery`,
`number_of_lithium_ion_cells`, `number_of_lithium_metal_cells`,
`contains_battery_or_cell`, `battery_installation_device_type`,
`safety_data_sheet_url`, `special_feature`, `warranty_description`,
`is_heat_sensitive`, `light_source`, `supplier_declared_material_regulation`,
`ghs`, `hazmat`, `batteries_required`, `batteries_included`.

The order also matters and is correct: the builder fills these groups **before**
the minimal filter runs, so they're present and get kept. The log line now reads
`kept N fields (required + offer essentials + safety/battery groups Amazon still
enforces)`.

---

## The honest limitation (so you're not surprised)

Minimal mode makes a **non-battery** product (a chair, a weed puller, a phone
case) go live with just the basics — that works cleanly.

But for a **battery/lithium product**, Amazon's safety rules are mandatory and
**cannot be stripped**. Minimal mode will still send the battery safety group,
because if it didn't, Amazon would reject the listing. So for those products,
"minimal" is "minimal except the safety fields Amazon legally requires." That's
not the app being stubborn — it's Amazon's hazmat/shipping rule, and there's no
way around it via the API.

So:
- **Non-battery product + Minimal mode** → tiny payload, fast live listing,
  enrich later. Works great.
- **Battery/lithium product + Minimal mode** → still lean, but the safety group
  rides along because Amazon enforces it. Also works — and now it won't get
  rejected for missing those fields, which was the bug.

---

## Quick summary

- Minimal mode = create a basic listing with only what Amazon needs, enrich later.
- Backend: a flag tells the builder to run normally, then a final filter trims
  everything except required + offer essentials + safety/battery groups.
- The bug was that the old filter only kept the *static* required list and
  stripped the *conditional* safety/battery fields, so Amazon rejected them.
- The fix keeps those conditional safety/battery fields, so minimal mode no longer
  drops things Amazon requires.
