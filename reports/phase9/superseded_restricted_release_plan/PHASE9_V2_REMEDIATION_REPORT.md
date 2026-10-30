# Phase 9 V2 Remediation Report

## 1. Verdict on the V2 brief (ChatGPT's suggestions)

**Right, and important.** V1 was not safe to call "ready". It contained source-derived outcomes in the documents, an inferred price map and dataset names/codes in the cleaner, hard-coded expected hashes/rows/accounts in the pipeline and SQL, and validation baselines that restated data results. My V1 scan looked for raw rows and obvious identifiers and so missed derived content. The brief's central rule, "no raw rows ≠ approved", is correct.

**Issues in the brief itself (for your judgement).**
1. It asks for a file named `APPROVED_PUBLIC_FILE_INVENTORY_V2.csv` while forbidding any "approved" label for files. I kept the file name and put no approval in it.
2. "Externalise or exclude" understates the cost: externalised values are still *named* in code and SQL (column names, section labels, scale multipliers). That reveals schema structure. I flagged it as owner item O-3 rather than pretending it is gone.
3. It lets me keep "780 / 774 / 1 / 1 / 4 / 43". Those are QA process counts and are not reproducible from the public repo; the README says so.
4. It cannot fix the real blocker: the old repo is public and the raw CSV is in `main`.

## 2. What I did, by brief section

| Section | Result |
|---|---|
| 2 Source of truth | Hashes, sizes, ZIP integrity, duplicates and the conflicting loose raw CSV recorded (`APPROVED_SOURCE_VERSION_REPORT.md`, `V1_V2_FILE_CHANGE_REGISTER.csv`) |
| 3 Deep review | 49-entry `PUBLIC_DATA_DERIVED_CONTENT_REGISTER.csv`, no sensitive values reproduced |
| 4 Docs | All 13 docs rewritten methodology-only; README rewritten |
| 5–9 Code/SQL | Constants moved to a private config (fails closed, no defaults); SQL baselines → structural checks; cleaner, Excel generator and report writers **excluded**; generic cleaning toolkit and synthetic Excel demo added; dashboard text neutralised |
| 10 Security | New report, inventory (no approvals), exclusions, with V1's conclusion corrected |
| 11 Modification register | Done; no byte-identical claims except four files that are |
| 12 Environment | Fresh venv, Python 3.13.16, `pip check` clean, 74 tests pass; described as a fixture/unit suite; `.gitignore` hardened and tested in a scratch copy |
| 13 Licence | README states no licence selected, default copyright, GitHub ToS view/fork, no data licence, no protection claim |
| 14 README | First-person and AI-assistance transparency kept; 13 communication points covered; no badges |
| 15 Scan | Done with allowlist and stated limits |
| 17 Gate | Stopped; blockers listed |

## 3. Costs and honest trade-offs

- **Less proof.** Two SQL validation scripts lost independent baselines; they now recount from the same table. The public cannot re-run anything data-dependent.
- **Less demonstration.** The cleaner, workbook generator and report writers are gone; the generic replacements are small and independently written, not the real thing.
- **Unverified equivalence.** I did not run the modified pipeline on the real data in this phase, so I cannot claim the V2 code reproduces the approved outputs.
- **Residual exposure** is listed in the security report (section 5).

## 4. Errors I made during this phase (and fixed)

A hard-coded 32-account constant that my regex missed (found by the SQL smoke test); a parser that accepted a malformed thousands pattern; a wrong test expectation; a dropped test case; and a leftover dashboard hypothesis string and one SQL comment found only by the final scan.

## 5. Not done, by design

No commit, no push, no repository created, Chrome not used, old repo visibility untouched, no licence added.
