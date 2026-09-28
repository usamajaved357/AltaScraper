# tests_support — a test reads a feature, not a file

Milestone 4 (owner-approved 28 Sep 2026) splits the big files by feature, moving
code word for word. About 280 tests read those files **as text** by their old
path (`open("dashboard.py").read()`, `fs.readFileSync("static/js/listings.js")`,
a dozen local `read()` helpers). Editing each of them risked quietly dropping a
check, so none of them was edited.

Instead:

- `features.json` lists, for each original, every file that now makes up that
  feature, in page load order (the original first for Python). A list holding
  only the original changes nothing.
- `run_tests.py` puts this folder on `PYTHONPATH` and adds
  `--require tests_support/feature_read.js` to `NODE_OPTIONS`, in every test
  process and every process a test starts.
- `sitecustomize.py` (Python) and `feature_read.js` (Node) then make a **text
  read** of a split original return the whole feature joined. Other files,
  writes and binary reads are untouched. The app never loads any of this.

So after a move, "the code says X" tests still find X wherever it now lives.

**When you split a file:** add the new file to its feature's list, at its load
position. `test_feature_sources.py` checks every listed file exists and is
really loaded (JS/CSS linked from `templates/dashboard.html`, Python imported by
the original).

**Running one test by hand** without run_tests.py skips the hook; use
`py -3.11 run_tests.py <name>`.

**A test that is about individual files** (which file defines a name, file
sizes, one file per feature) must read raw bytes -- `open(p, "rb")` /
`fs.readFileSync(p)` -- so it sees each file on its own, not a feature.
`test_global_name_clashes.py` does. The hook also turns `\r\n` into `\n` for a
Python text read, exactly as `open()` in text mode would.
