---
name: refactor-move
description: Faithful-move procedure for restructuring AltaScraper code (CLAUDE.md Rules 7 and 10) - move code without rewriting it, prove behaviour is identical, keep import surfaces working. Use only when the owner has approved a specific refactor; never as a side effect of another task.
---

# refactor-move

**Problem it solves:** "moves" that silently change behaviour, circular imports
into the engine, and deleted functions nobody noticed.

**Modifies files:** yes, but only moves (plus the import that re-exposes the
moved name). No logic changes in the same commit.

## Inputs
The owner-approved scope: which functions/routes/files move where, and why.

## Procedure
1. **Approval check:** a refactor is a behaviour risk; confirm the owner
   approved this exact scope (CLAUDE.md Rule 7). Log it in current-work.md.
2. **Dependency scan:** for each function, list the module-level names it reads
   (AST walk). A function that reads the mutable `MARKETPLACE_ID`,
   `MINIMAL_MODE` or other runtime-reassigned engine globals must NOT be moved
   by import (the import binds once and goes stale) — stop and report.
   Importing `amazon_listing_generator` from a new module loads a second copy
   (it runs as `__main__`): never do it.
3. **Move verbatim:** cut the exact source (`ast.get_source_segment`), paste
   into the target module, replace the original `def` with an import of the
   moved name so every caller still resolves. Route moves use the existing
   register-injection pattern (docs/architecture.md section 2).
4. **Prove identity:**
   - AST identity: `ast.dump` of the moved function equals the original at the
     base commit.
   - Import surface: `old_module.fn is new_module.fn`.
   - Behaviour: run a set of inputs through the old (exec'd from the base
     commit's source) and new versions; results equal.
5. **Scope check:** `scope_check.py` will list the moved names as REMOVED from
   the source file: expected, explain each with its new location.
6. `verify-change` (full suite). Boot the app and hit safe GET routes if routes
   moved (never routes that start work, like `/run/*` or `/miles/run`).
7. Root shims: do not add logic to them; delete one only when nothing imports
   the bare name (search first) and the owner agreed.

## Output
What moved (from -> to), the three identity proofs, scope-check output, test
results.

## Persist afterwards
docs/architecture.md (new locations); docs/decisions.md if the owner decided
something about the structure.
