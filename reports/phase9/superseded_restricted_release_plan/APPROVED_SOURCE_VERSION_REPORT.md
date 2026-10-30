# Approved Source Version Report (Phase 9 V2)

Release: `NovaBridge_FPA_Public_Release_V2_NOT_PUBLISHED` · Status: **not published**

## 1. Hierarchy applied

| Order | Source of truth for | Selected file | Why |
|---|---|---|---|
| 1 | Phases 1–6 | `NovaBridge_FPA_All_Phases_1-6_Master.zip` and its manifests | Approved master archive |
| 2 | Phase 7 | `Phase7_QA_Package.zip` and `PHASE7_QA_REPORT.md` | Approved QA package and report |
| 3 | Phase 8 | `NovaBridge_Phase8_Final_Documentation_Package.zip` | The **final corrected** package; an earlier draft package (`NovaBridge_Phase8_Documentation_Package.zip`) is superseded and not used |
| 4 | Phase 9 V1 | `NovaBridge_FPA_Public_Release_READY_NOT_PUBLISHED.zip`, `NovaBridge_Phase9_Reports.zip` | Starting candidate only; not authoritative |

No file was chosen by modification date alone; each was identified by name, size and SHA-256 and cross-checked against the manifests where one exists.

## 2. Verified archives (Downloads folder, read-only)

| File | Bytes | SHA-256 | ZIP integrity |
|---|---:|---|---|
| NovaBridge_FPA_All_Phases_1-6_Master.zip | 130,046,157 | e4291b78c15ca7db438f1123aa9ddd0473f4a12a070dd95e13022a31c50ac4f0 | testzip OK |
| Phase7_QA_Package.zip | 4,483,919 | 2f08840d038c155ba2da6826f4576c345160a8bd730a8f10878cf2608ca509cb | testzip OK |
| PHASE7_QA_REPORT.md | 23,055 | 2e7f8f956314e17f0f8b1acdb483b23da7413e6bb88a0ec3198d58a18fa12a6e | n/a |
| NovaBridge_Phase8_Final_Documentation_Package.zip | 102,671 | 0a9a5406e9bcd2664d476c2f87e432c00088920bd2b1a8fa15f0af6c108a76c2 | testzip OK |
| NovaBridge_FPA_Public_Release_READY_NOT_PUBLISHED.zip (V1) | 409,892 | 01ae187d528888405ebd49155da33b5416f3731c34e6cb0110e54405f0b33cc5 | unchanged, not reopened for writing |
| NovaBridge_Phase9_Reports.zip (V1 reports) | 21,193 | a7aa957471b382487b22d346c32bb6af57733b843ed655c71727b411e414feed | unchanged |
| Phase4_Complete_Package_v3.zip / Phase5_Package_v3.zip / Phase6_Package_v2.zip | see device | ddb39b2c… / e84421f1… / fda3c448… | component packages found inside/alongside the master; not used as separate sources |

## 3. Duplicates and superseded items

| Item | Finding | Handling |
|---|---|---|
| Loose raw CSV in Downloads with the approved raw file's name | Its SHA-256 (`845b78d8…`, 51,675,512 bytes) **differs** from the approved raw file's hash (`a0e6eddd…`, 51,938,535 bytes) | Not used. The approved raw file inside the master archive is the reference. This is the open housekeeping item recorded in the Phase 7 issue log |
| Phase 8 draft package | Earlier draft, superseded by the final package | Not used |
| Component packages (Phase 4/5/6) | Overlap with the master | Master used |

## 4. How V2 traces to the approved source

For every source file in V2 `src/`, `sql/` and `tests/`, `V1_V2_FILE_CHANGE_REGISTER.csv` records the V1 hash, the V2 hash and the hash of the corresponding approved master copy. Byte-identical to the approved master: `sql/phase4/02_grain_and_overview.sql`, `sql/phase4/05_forecast_error.sql`, `src/phase6_style.css`, `tests/conftest.py`. Every other public file was **modified** or is **new**; none is claimed to be byte-identical. Each modification is described in `PUBLIC_SOURCE_MODIFICATION_REGISTER.md`.

## 5. Not verified here

- The contents of the Phase 4/5/6 component packages against the master were not diffed in this phase.
- The approved master was not independently re-validated against its own manifests beyond ZIP integrity and the hash of the archive itself.
