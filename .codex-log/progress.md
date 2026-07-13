# Progress log

### 2026-07-13 20:10

- Objective: implement the supervised-learning validation and calibration gaps.
- Spec: `specs/2026-07-13-spatial-validation-calibration.md`.
- Files touched: spec, ADR and workflow logs only.
- Validation: inspected the v4 training pipeline and the 290,443-row local
  curated table.
- Result: confirmed 59,944 ES/FR/IT land rows, 935 observed positive cells,
  276 spatial 100 km groups and substantial feature missingness.
- Next step: add testable spatial-validation and calibration helpers.


### 2026-07-13 21:08

- Objective: complete the spatially nested v5 benchmark and fail-closed probability contract.
- Spec: `specs/2026-07-13-spatial-validation-calibration.md`.
- Files touched: spatial helpers/tests, `scripts/train_spatial_benchmark.py`, v5 evidence artifacts, README and methodology.
- Validation: 11 helper tests, 3 benchmark tests, quick end-to-end smoke, then full 4 outer x 3 inner spatial benchmark on 38,972 FR/IT cells and a locked Spain transfer run.
- Result: Random Forest led FR/IT nested AP (0.0939) but failed Spain transfer (AP 0.004855, AUC 0.6543, top-250 1); calibration is blocked, 12/31 features exceed 20 pp missingness shift and four required features are entirely absent in Spain. No app promotion.
- Next step: full repository suite, artifact checks and independent read-only audit.


### 2026-07-13 21:30

- Objective: resolve the independent adversarial audit FAIL before promotion or publication.
- Spec: `specs/2026-07-13-spatial-validation-calibration.md`.
- Findings accepted: canonical Spain cohort mismatch, country-prefixed block leakage, preprocessing selected outside inner CV, weak promotion gate and stacking scope mismatch.
- Fixes implemented: `is_spain` cohorts, coordinate-only blocks, missing indicators inside candidate/inner CV, stratified-bootstrap AP gate, mandatory independent confirmation and stacking formally deferred.
- Validation: 18 focused tests passed; corrected 2x2 quick smoke completed. Full corrected 4x3 run is in progress.
- Next step: regenerate all evidence, update reported numbers and rerun both test environments.


### 2026-07-13 21:50

- Objective: close the corrected v5 benchmark after independent re-audit.
- Spec: `specs/2026-07-13-spatial-validation-calibration.md` (complete).
- Validation: corrected full 4x3 nested run; 21 model/artifact tests; 46 app tests; `git diff --check`; same adversarial reviewer rechecked all prior findings.
- Result: all former P1/P2 findings resolved; final verdict PASS WITH CAVEATS. Random Forest nested AP 0.094265, Spain AP 0.015725, AUC 0.659526, top-250 2; v5 remains rejected and app stays on v49.
- Caveats: weak negatives, 26 Spanish positives, historically reused Spain anchor and 12/31 features with >20 pp missingness shift (four at 99.03% missing in Spain).
- Next step: commit and push the reproducible evidence; future model work must first harmonize Spanish livestock/manure coverage or obtain independent adjudicated outcomes.


### 2026-07-13 22:05

- Objective: add a defensible detailed PDF report for each selected point/cell.
- Spec: `specs/2026-07-13-point-report-export.md`.
- Discovery: the app already had a one-page snapshot PDF; the new export will
  remain separate and backwards compatible.
- Contract: report screening evidence and unresolved gates, never inferred
  compliance, viability, permission or connection capacity.
- Implementation: added a pure semantic report contract, four-section PDF
  renderer, safe filename helper and a third export button in Streamlit.
- Validation: visual review of all four pages; real 5 km and 1 km snapshot
  generation; 52 app tests and 21 model/artifact tests passed; `git diff
  --check` clean.
- Result: complete and ready to publish. The v49 score and model artifacts were
  not modified.

