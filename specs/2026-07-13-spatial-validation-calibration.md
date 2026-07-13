# Spatial validation and calibration for biomethane screening

## Context

The v49 system ranks Spanish cells for further investigation. It compares
Logistic Regression, Random Forest, Gradient Boosting and Linear SVM using
strong Spanish/French labels, medium-confidence Italian proxy labels and
low-weight unlabeled cells. The current score is explicitly not a probability.

This iteration implements the supervised-learning gaps identified from the
course material: spatial cross-validation, validation-driven hyperparameter
selection, a fail-closed calibration contract, capacity diagnostics and
missingness analysis.

## Problem

The existing benchmark trains fixed hyperparameters on FR/IT and evaluates the
transfer to Spain. It does not quantify spatial-fold stability, tune parameters
without touching Spain, fit or test a calibrator, choose a threshold outside
the Spanish test set, or explain the effect of missing values. The field named
`spain_in_sample_calibration` is an in-sample evaluation, not probability
calibration.

## Goals

1. Preserve Spain as an untouched geographic transfer test.
2. Select model and hyperparameters using grouped spatial folds in FR/IT only.
3. Audit whether probability calibration is admissible before fitting a
   calibrator. With the current weak negatives it is blocked by default.
4. Report capacity-based score cut-offs and confusion metrics as weak-label
   diagnostics, not as a binary project decision threshold.
5. Report AP, ROC AUC, confusion matrix, precision, recall, F1/F2, top-k
   capture and fold dispersion. Brier, log loss and calibration error are only
   allowed after independently adjudicated positive and negative outcomes exist.
6. Audit missingness by feature and country, and test missing indicators rather
   than silently assuming median imputation is harmless.
7. Use a fail-closed promotion gate with a material AP effect, uncertainty,
   top-k preservation and feature-coverage checks.

## Non-goals

- Do not call any output a probability of project viability, permit approval,
  profitability or land availability.
- Do not treat unlabeled cells as confirmed true negatives.
- Do not publish the WorldClim-derived full training table.
- Do not replace parcel-level, connection-capacity or environmental checks.
- Do not promote stacking or calibration merely because they look better
  in-sample.

## Constraints

- Full training data remains local because of redistribution restrictions.
- The honest test contains only 26 Spanish positive cells associated with 24
  operating plants.
- Italian positives are medium-confidence proxies and negative weights encode
  uncertainty rather than verified absence.
- Training must remain deterministic and feasible on a CPU workstation. The
  RTX 5090 is not required by scikit-learn models.

## Approach

### Spatial contract

- Build deterministic coordinate-only 100 km blocks from EPSG:3035 `X_LLC`
  and `Y_LLC`; administrative country prefixes must not split physical blocks.
- Use `is_spain` as the canonical Spanish-domain flag and keep every such land
  cell outside model selection, calibration and threshold selection.
- Use grouped folds over FR/IT for hyperparameter comparison and out-of-fold
  predictions.
- Split FR/IT spatial groups deterministically into calibration-fit and
  calibration-validation partitions.

### Candidate models

- Logistic Regression
- Random Forest
- Gradient Boosting
- Linear SVM

Stacking is explicitly deferred. With unstable base-model transfer and a
historically reused Spanish anchor, evaluating and retaining a stack would add
variance and consume the test as a selection set.

The grid is intentionally small. Selection prioritizes grouped-CV average
precision, then fold stability and top-k capture. Model complexity is not a
promotion criterion.

### Calibration and thresholding

- First run an eligibility gate that requires independently adjudicated
  positive and negative outcomes.
- The current dataset fails that gate because absence of a known plant is not
  a confirmed negative outcome. Therefore no public probability is fitted or
  promoted in this iteration.
- Produce capacity-based cut-offs (`top 10`, `25`, `50`, `100`, `250`) and
  weak-label confusion diagnostics only. They are reference summaries, not
  permit, investment or build/no-build thresholds.
- Keep sigmoid/isotonic helpers and tests ready for a future adjudicated
  calibration cohort, without invoking them on the current weak-label table.

### Promotion gates

A calibrated proxy output is reportable only if a future dataset satisfies all
of the following:

1. Spain remains untouched until final evaluation.
2. Every spatial validation fold contains both classes.
3. The calibration and evaluation cohorts contain independently adjudicated
   positives and negatives; weak unlabeled cells are not accepted as negatives.
4. Calibration improves Brier score on an adjudicated holdout and does not
   reduce AP by more than 2% relative.
5. Reliability tables and label caveats are published.

The model itself is eligible for app promotion only if all conditions hold:

1. Spain remains quarantined by `is_spain` throughout development.
2. The Spain AP gain is both at least 20% relative and 0.005 absolute over v4.
3. The stratified-bootstrap 95% lower bound of Spain AP is above the v4 point
   estimate, and top-250 capture is not worse.
4. No required feature is entirely missing in development or at least 95%
   missing in Spain.
5. A new independent temporal or adjudicated confirmation set is available;
   the historically reused Spain anchor alone can never auto-promote a model.

## Task slices

1. Add pure spatial split, metric, calibration and missingness helpers with
   synthetic tests.
2. Add the end-to-end local training/evaluation script and compact search grid.
3. Execute against the private curated table and generate metrics/report/model
   artifacts.
4. Update public methodology and app language only if promotion gates pass;
   stacking remains formally out of scope for this iteration.
5. Run focused and full tests, artifact checks and independent review.

## Validation plan

- Unit tests for deterministic group assignment and group-disjoint folds.
- Unit tests proving Spain is never used for selection/calibration/thresholds.
- Unit tests proving cross-border cells in one coordinate block share one
  group and that preprocessing is selected inside inner CV.
- Synthetic calibration tests plus a fail-closed eligibility test on weak
  labels.
- Capacity-threshold and confusion-matrix tests.
- Missingness-report schema and high-missingness flag tests.
- Determinism check with fixed seed.
- Full repository test suite.
- Independent read-only adversarial review of code, metrics and claims.

## Closeout

Status: complete — independently re-audited as PASS WITH CAVEATS after all P1
and P2 findings were corrected. Remaining caveats are intrinsic data limits:
weak negatives, 26 Spanish positive cells, historically reused Spain labels
and severe cross-country feature-coverage shift. The v5 model was not promoted.
