# Design system (as it exists)

This file DESCRIBES the UI system the app already has, including its
inconsistencies, so changes reuse what is there. It does not invent a new one.

- Claude records **observed** facts here automatically.
- A **new convention** (for example "all new primary buttons use X") needs the
  owner's approval, and is then recorded in docs/decisions.md and here, marked
  **[decided]**. Nothing below is marked decided yet except where stated.

Source: the 27 Sep 2026 UI analysis, DESIGN_RULES.md (root), the
drawer-redesign-decisions memory note.

---

## 1. Principles already in force

From DESIGN_RULES.md (the owner's redesign rules):
- **Show the judgment signals, hide the plumbing.** Surface what helps judge a
  listing (status, compliance, price, image count); put rare actions (delete,
  push image, raw preview, source, hold) in a `⋯` menu.
- **Status = colour, always the same mapping:** needs review = amber, blocked =
  red, ready = green, live = neutral. One status pill per item.
- **One primary button, and it changes with state:** needs review -> Review;
  blocked -> See why (never Submit); ready -> Submit; live -> View.
- **Warnings only when real.** A clean listing shows no compliance panel.
- **Every number is real.** Never ship placeholder counts; show "unknown" rather
  than 0 when there is no data (see decisions: profit is measured).

Plus: the whole app is **dark theme only** (no light mode anywhere). Section
changes have **no transition** on purpose (removed to match Orbit).

## 2. Colour systems (four, by surface)

| Surface | Tokens | Accent | Notes |
|---|---|---|---|
| App shell, grid, most screens | `dashboard.css` `:root` (`--bg --panel --panel2 --line --ink.. --accent --ok --warn --red --radius-*`) | teal `#2dd4a8` | Legacy aliases (`--muted --green --amber --fg --text --bd --card`) are still used and must stay. `--fs-*` type scale exists but most rules use px. |
| Product page (PDP) | `--pdp-*`, scoped to `#pdp` (pdp.css) | teal `#2dd4bf` (differs from the shell teal) | favicon also uses #2dd4bf |
| Listing drawer | **literal hex, on purpose** (drawer.css, drawer_attributes.css, draftsources.css) | blue `#3b7dd4` | **[decided]** by the owner, 29 Aug 2026: the drawer keeps the design file's hex. Do not convert to tokens without asking. |
| PPC / Dr PPC | `--ppc-*` (ppc.css), `--drp-*` (drppc.css) | GitHub-dark palette; Dr PPC has a light panel and gold buttons | scoped under `.ppc-page` |

JS must not name colours (test_one_palette.py), with existing exceptions such as
chart colours in salescharts.js.

## 3. CSS load order (it carries meaning)

`dashboard.css` -> `dialog.css` -> `datatable.css` -> `genui.css` ->
`repricer.css` -> `inputupload.css` -> `genflow.css` -> `drawer.css` ->
`drawer_attributes.css` -> `draftsources.css` -> `pdp.css` -> `pdp_images.css`
-> `listrow_detailed.css` -> `listrow_edit.css` -> `revenue.css` ->
`orders_panel.css` -> `ppc.css` -> `drppc.css` -> `mobile.css` (last).

Stated dependencies (comments in dashboard.html): drawer.css overrides
`.drawer`; pdp.css must beat drawer.css; listrow_edit.css must beat
listrow_detailed.css; mobile.css must come last. A new stylesheet goes where its
overrides need it, and the reason is written in a comment beside the `<link>`.

## 4. Layer order (z-index)

App bar 20 · drawer scrim 70 · drawer 75 · PDP 78 · tile menu 85 ·
modals 90 (some inline: `#genpanel` 115, `#usersmodal` 120) · inline popover
9550 · dialogs 9600 · **toast 9800** · tooltips 9999. The PDP's layer reasoning
is written in pdp.css. (Milestone 6: the toast was at 80, so one fired from
inside a modal was hidden behind it. It is a live region, `role=status`, and a
failure is styled `.toast.err`.)
One global Escape handler (escape.js) closes the topmost open layer.

## 5. Buttons (families in use)

| Family | Look | Typical use |
|---|---|---|
| `.db-chip` (+ `.go`, `.risk`, `.primary`) | pill | most common (about 200 uses); dialog buttons |
| `button.primary` | teal fill, dark ink | main action on older screens |
| `button.ghost` | transparent | secondary |
| `button.danger` | literal `#7a1f1f` fill | destructive |
| `.mktbtn` (+ `.on`) | 8px radius | toggles/segments, sometimes actions |
| `.ib` | 30px icon button | row actions |
| `.barbtn` | app bar only | |
| `.linkbtn` | text link | inline actions |
| `.pdp-tb` (+ `.accent`, `.success`) | PDP toolbar | white text on teal (breaks the dark-ink-on-teal rule) |
| `.dw2-foot button` (+ `.primary` blue, `.success`) | drawer footer | |
| `.lr-sb-save` / `.lr-sb-cancel` | staged-edit bar | |
| `.o-btn`, `.ppc-btn`, `.drp-*-btn` | orders, PPC, Dr PPC | |
| `.tilemenu button.danger` | red text | menu items |

The primary action has at least five looks and the danger action at least four.
Until the owner picks one per role, **new UI copies the family already used on
the same screen.**

## 6. Shared helpers (reuse these)

| Helper | File | Use for |
|---|---|---|
| `toast(msg)` | listings.js | short confirmations (no error style; one slot; 1.8 s) |
| `uiAlert / uiConfirm / uiPrompt` | dialog.js | replacing native dialogs (test_no_native_dialogs.py forbids native) |
| `uiInline(anchor, o)` | dialog.js | small popover editor |
| `uiStat / uiStats / uiPanel / uiToolbar / uiSource / uiEmpty / uiCopy` | pageui.js | stat cards, panels, toolbars, provenance lines, empty states, copy |
| `esc(s)` | listings.js | HTML text escaping (escapes `& < > " '`) |
| `jsArg(s)` | users.js | **data inside an inline JS handler** |
| `dwSection / dwFold / dwFieldRow / dwTitleParts / dwEditBlock` | drawer.js | drawer and PDP field layout (shared) |
| `saveEdit / editField` | autofix.js | save-on-blur field edits (`POST /edit`) |
| `lrEditBox / lrEditStage` + save bar | listrow_edit.js | staged "Save all" edits on list rows |
| `altaSkeletonRows / Cards / Chart / Screen / Into`, `altaCountUp`, `altaStagger` | motion.js | skeleton loading, count-up, stagger |
| `screenNeedsLoad / screenLoaded` | screenstate.js | skip reloading a screen revisited within 10 min |
| `altaPoller` | poller.js | adaptive polling that backs off and pauses when hidden |
| `acctBody / acctUrl / scopeQs` | reqscope.js, scopeq.js | naming the account on every request |
| shared tables | datatable.css (`.stk-table`, `.rp-tbl`, `table.lt`) | tables |

Unused shared pieces (do not assume they work): `uiSeg` / `.segbtn`,
`.dt-tbl` / `.dt-card`.

## 7. States

- **Loading:** inline `<span class="genspin">` (defined twice in dashboard.css,
  the later teal one wins); "Loading…" text; skeletons only on the listings
  grid and Sales.
- **Errors:** `toast()` for small failures; `uiAlert` for blocking ones; inline
  red text (`color:var(--red)`) in a panel; account banners `.acctbanner`;
  PDP `.pdp-error` / `.pdp-err`. Some screens draw a load failure in `.empty`
  style (hourly.js) — a failure must not look like "no data".
- **Empty:** `.empty` (centred, muted), `.emptynote` (dashed), `uiEmpty()`
  (actionable, preferred for new screens).
- **Saving:** `.saving` -> `.saved` / `.err` classes on the field, plus a toast.
  There is no inline per-field error text.

## 8. Rendering model

- HTML strings assigned with `innerHTML`; the listings grid is redrawn in full
  by `render()` (static/js/miles_template.js); the PDP by `pdpRender()`;
  `pdpHeroRefresh()` swaps only the hero so focus survives a blur-save.
- Handlers are mostly inline `onclick="..."` strings.
- **Escaping rule:** `onclick="fn('${esc(x)}')"` is unsafe — the browser decodes
  `&#39;` back to `'` before the handler runs, so an apostrophe in a SKU breaks
  or injects. Use `onclick="fn(${jsArg(x)})"`. Many existing handlers still use
  the unsafe form (listed in docs/known-issues.md); new code must not.
- About 40 private escape copies exist (`_sEsc`, `_oEsc`, ...); most do not
  escape `'`. New code uses `esc` / `jsArg`.
- Focus/caret is preserved only in a few places (search box caret jumps to the
  end; staged edits restored by `lrEditRestore`).

## 9. Responsive

`mobile.css` loads last and is measured against Orbit at 390x844; its main
breakpoints are 860px and 520px. The sidebar is an overlay drawer at every
width (mobilenav.js, sidebar.js). Other files use their own max-widths (16
distinct values: 420-1400). Wide tables scroll inside their own box. Minimum
touch height 34px for `.mktbtn` / `.db-chip`. Honour `prefers-reduced-motion`.

## 10. Icons and fonts

Tabler Icons 3.5.0, full set, self-hosted (`static/vendor/tabler-icons`),
`<i class="ti ti-name">`. Font stack starts with Inter (not loaded; used if
installed), then the system font. Body is 14px.
