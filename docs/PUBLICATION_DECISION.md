# Publication Decision (Phase 9)

**Date:** 30 October 2026 · **Decided by:** the project owner · **Supersedes:** the restricted-release plan prepared earlier in Phase 9 (kept in [`reports/phase9/superseded_restricted_release_plan/`](../reports/phase9/superseded_restricted_release_plan/)).

## The decision

The owner decided to publish the **complete** NovaBridge project in this repository, including the raw and cleaned datasets, all Python code, SQL, Excel workbooks, the dashboard, tests, QA evidence and documentation. He states that he created the project and its dataset for portfolio and learning purposes and that the dataset is synthetic.

## What this means

| Topic | Position |
|---|---|
| Dataset | Published (raw and cleaned), GZIP-compressed, byte-identical after decompression. |
| Provenance and synthetic status | **Owner-stated, not independently verified.** No generator, seed, creation date or licence record exists ([`DATA_PROVENANCE.md`](DATA_PROVENANCE.md)). |
| Personal data check | The data contains 8 person-like owner names (initial + surname) and 8 generic system user IDs. No email address, phone number or URL was found. They are treated as fictional because the group is fictional; that is not proven. |
| Licence | **None.** No open-source licence and no `LICENSE` file. Default copyright applies. The repository must not be described as open-source licensed. |
| Hosting | The dashboard is a downloadable standalone file; it is **not** hosted online. |
| History | The raw CSV was committed uncompressed in Stage 0 (commit `1d601c0`). History was **not** rewritten, so that uncompressed blob (about 52 MB) remains in git history; the tip of `main` carries only the compressed copy. |

## Statements in older documents

Documents written before this decision keep their original wording as the historical record. In particular, Phase 8 documents that call the release *blocked*, *draft* or *not approved* describe the Phase 8 state. Each Phase 8 document received an updated status banner at publication; no calculation, figure or finding was changed (see [`reports/phase9/DOCUMENT_EDIT_REGISTER.csv`](../reports/phase9/DOCUMENT_EDIT_REGISTER.csv)).

## Open items that this decision does not close

* Provenance and redistribution rights of the dataset (owner-stated only).
* Windows, clean-machine (beyond one fresh Linux virtual environment), native Microsoft Excel, other browsers, assistive technology and printer testing.
* Sandbox build paths remain in two QC files and in Phase 7 logs (no personal path).
* Unresolved accounting conventions listed in [`ASSUMPTIONS_LIMITATIONS_AND_RISKS.md`](ASSUMPTIONS_LIMITATIONS_AND_RISKS.md).
