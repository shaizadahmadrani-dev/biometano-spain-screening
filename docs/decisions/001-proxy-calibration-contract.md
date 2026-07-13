# ADR 001: Calibrate only the observed proxy task

## Status

Accepted.

## Decision

Probability calibration is blocked for the current dataset. A future fitted
calibrator may estimate only the probability of an independently adjudicated
observed label under its calibration distribution. It must never be presented
as the probability that a biomethane plant is feasible, permitted, profitable
or buildable.

Spain remains an untouched geographic transfer test. Model selection,
calibrator selection and threshold selection use group-disjoint FR/IT data.

## Why

The dataset has 24 known operating Spanish plants, 26 positive Spanish cells,
medium-confidence Italian proxies and no confirmed negative sample. A numeric
probability cannot repair target or label uncertainty.

## Consequences

- Ranking remains the primary public decision surface.
- The current weak-label table must not emit calibrated probabilities, Brier
  claims or a promoted binary threshold.
- Capacity-based cut-offs and confusion tables may be shown only as
  `weak_label_reference_only` diagnostics.
- Brier score, log loss and reliability tables require an independently
  adjudicated positive-and-negative calibration cohort.
- Failed calibration is documented rather than hidden or forced into the app.
