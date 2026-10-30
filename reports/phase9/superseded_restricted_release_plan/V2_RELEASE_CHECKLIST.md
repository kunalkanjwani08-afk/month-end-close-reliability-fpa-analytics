# V2 Release Checklist

| # | Item | Status | Note |
|---|---|---|---|
| 1 | Originals (Phase 1–8 archives, raw/cleaned data, QA evidence, Phase 8 docs, V1 candidate) unchanged | Done | Read-only use; V1 hashes recorded |
| 2 | Work confined to the V2 folder | Done | |
| 3 | No git commit, no push, no GitHub repo created, Chrome not used | Done | Scratch `git init` + `git add -n` only, in a temp copy, no commit |
| 4 | Old repository visibility changed | **Not done (owner)** | Still PUBLIC with the raw CSV in `main` |
| 5 | Licence added | **Not done (owner)** | README states no licence selected |
| 6 | Source version verification, change register | Done | |
| 7 | Data-derived content register | Done | 49 entries |
| 8 | Docs rewritten methodology-only; README rewritten | Done | Human read of all 13 docs + README required |
| 9 | Code externalised / excluded; modification register | Done | Not run on real data |
| 10 | Fresh venv, pip check, pytest | Done | 74 passed, Linux, Python 3.13.16 |
| 11 | Content-safety scan with allowlist | Done | Limits stated |
| 12 | Hash manifest | Done | Generated last |
| 13 | Release approved for publication | **No** | Owner gate |

## Owner decisions and actions (open)

| ID | Decision / action |
|---|---|
| O-1 | Make the old repository private (or delete it) manually; consider forks, clones, caches and any other copies of the raw CSV; consider whether history rewriting is needed |
| O-2 | Provide provenance and redistribution evidence for the dataset, or confirm that it is fully synthetic and owner-generated |
| O-3 | Decide whether the private schema structure (column names, section labels, scale scheme) in SQL and code may be public |
| O-4 | Confirm that "NovaBridge" is not a real organisation's name |
| O-5 | Decide whether to publish or exclude the dashboard-builder source |
| O-6 | Choose a licence (or none) |
| O-7 | Human review of `APPROVED_PUBLIC_FILE_INVENTORY_V2.csv` and every public doc |
| O-8 | Create the new repository (fresh history) only after O-1; push yourself |
