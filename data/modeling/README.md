# Local training feature table

`scripts/train_benchmark.py` expects this local file:

```text
data/modeling/biometano_grid5km_curated_v4_attributes.parquet
```

It is intentionally excluded from Git because it contains WorldClim-derived climate
values. WorldClim allows academic and other non-commercial use but does not permit
redistribution or commercial use without prior permission.

Prepare the table locally from the original providers and preserve their attribution,
licence notices and data vintages. The required model features, label and weight fields
are listed in `model_features.json`.

The benchmark also expects these control columns:

- `GRD_ID`
- `primary_country`
- `is_land_cell`
- `is_spain`
- `X_LLC`
- `Y_LLC`
- `label_tier_mediterranean_v4`
- `label_has_operating_biomethane_plant_spain_v3`

`X_LLC` and `Y_LLC` are the lower-left EPSG:3035 coordinates used to build
deterministic 100 km spatial groups. They prevent neighbouring cells from being
split casually between model-selection folds.

Do not interpret unlabeled cells as verified unsuitable sites. They are weak negatives
used for ranking experiments.
