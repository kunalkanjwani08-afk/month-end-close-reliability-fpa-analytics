# Public Release Security Report V2

**Overall status: `REQUIRES_OWNER_DECISION`. Not approved for publication.** No file in this release carries the status "approved". A file having no raw rows is not evidence that it is safe.

## 1. Correction of the V1 report

The V1 security report concluded that the release folder was "ready" and that only the old public repository blocked publication. **That conclusion was incomplete.** V1 contained, in documents and code: source-derived outcomes and population counts; an inferred price map and entity/code references in the cleaner; hard-coded expected hashes, row counts and account numbers; and SQL validation baselines. V1 also reported two data-quality percentages as "generic". V1's scan targeted raw rows and obvious identifiers, not derived content. V2 supersedes it.

## 2. Release-status definitions

| Status | Meaning |
|---|---|
| STAGING_ONLY | Held for working use; not for publication |
| REQUIRES_REMEDIATION | A specific defect must be fixed first |
| CONDITIONAL_PUBLIC | No known source-derived content; publishable **only after** a human review of this inventory |
| OWNER_DECISION_REQUIRED | Needs an owner judgment (rights, naming, licence, or retained private structure) |

Inventory result: 40 files CONDITIONAL_PUBLIC, 6 OWNER_DECISION_REQUIRED, 0 approved. See `APPROVED_PUBLIC_FILE_INVENTORY_V2.csv` (the file name is the one the brief required; it contains no approval).

## 3. What was scanned

Every file in the V2 folder (46 files): text, comments, docstrings, constants, SQL literals, JavaScript, HTML, CSS, JSON, requirements, `.gitignore`, the Mermaid source and the SVG text, plus the PNG visually.

| Scan | Method | Result |
|---|---|---|
| Sensitive tokens | Eight owner-name strings and eight user-ID strings taken from the private data (one user-ID entry is a 1-character string that matches almost everything, so it was discarded as meaningless; the other 15 were scanned) | 0 hits for the 15 meaningful tokens |
| 64-hex hashes, `…` hash prefixes | Regex | 0 in V2 files |
| Currency amounts | Regex for currency symbol + digit | 3 hits, all code/test syntax (Excel `$B$2` reference; a parser test string) |
| Large comma numbers | Regex | Only parser examples and CSS/SVG numerics |
| Percentages | Regex, reviewed manually | Only project-convention thresholds and sensitivity constants (50% guard, 90%, 3%, 0.5%, 5%), the QA headline sentence in the README, and tolerance remarks |
| Long decimals | Regex, reviewed manually | Constants (1.4826), SQL tolerances and sensitivity thresholds, SQL arithmetic |
| Machine paths / emails / secrets | Regex | 0 (relative private paths in the dashboard builder reviewed, see 5) |
| Source-system names | Regex | 0 (matches in JS were variable names) |
| Hard-coded references | Manual grep for years, account patterns, check ids, finding ids | Only fixture years in tests and "INS-01"/phase labels as reference text in the dashboard builder (see 5) |
| Links and anchors | Script over all Markdown | 0 broken |
| Syntax | `py_compile`, `node --check`, SQL bind test on an empty schema | OK |
| Archives and extensions | Listing | No CSV, XLSX, DB, ZIP, or parquet in V2 |
| Images | PNG viewed; SVG text grep | Contains only generic box labels |

## 4. Allowlist (retained deliberately)

- QA headline counts (780 / 774 / 1 / 1 / 4 / 43), by owner instruction: they describe the QA process.
- Metric formulas and project-convention thresholds: safely demonstrable methodology.
- Invented fixture ids and years inside tests; parser example strings; the 1.4826 constant.
- Structural labels (section and account-group names, column names, the scale-scheme multipliers) inside SQL and code: they describe schema structure, not results. **CONDITIONAL**, owner item O-3.
- The project label "NovaBridge".

## 5. Remaining exposure, stated plainly

1. **Private schema is visible.** Column names, section/group labels and the scale-restoration scheme are present in SQL and code. They reveal how the extract is structured, not what it contains.
2. **Dashboard builder** (`phase6_*`) retains the private payload structure and references private relative paths (`data/`, `outputs/`) and finding labels (INS-01). It cannot run from this repository. Owner decides whether to publish it.
3. **Hard-coded constants not found by pattern may exist.** A pattern scan cannot prove the absence of derived content; a human must read the inventory.
4. **Assurance weakened.** Two SQL validation scripts no longer carry independent baselines; the V2 pipeline gates depend on an owner config.
5. **Not run end to end on real data in V2.** No equality of outputs with the approved version is established.
6. **The old public repository** (`kunalkanjwani08-afk/month-end-close-reliability-fpa-analytics`) still exposes the raw CSV in `main`, and any forks or clones may persist. Changing its visibility is the owner's manual action and was not done or attempted here.
7. **Provenance and redistribution rights** remain unverified; no licence is added.

## 6. Limits of this review

Performed by the same AI assistant that edited the files, not by an independent reviewer. Pattern scanning, a one-time visual inspection of the PNG, and a manual read of the changed documents. No external audit, no secret-scanning product, no GitHub-side check.
