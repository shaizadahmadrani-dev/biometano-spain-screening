# Biomethane Spain Screening

Open academic project for exploring where to **prioritise further evidence gathering** for biomethane projects in Spain.

It combines a Mediterranean classification benchmark with a two-scale territorial explorer:

- **5 km:** national screening across 21,519 land cells.
- **1 km:** refined review across 30,450 cells inside the previously prioritised universe.
- **Interactive app:** map, filters, evidence, physical exclusions, scenario weights and point reports.
- **Model benchmark:** Logistic Regression, Random Forest, Gradient Boosting and Linear SVM.

> **Important:** the score is not a probability and the cells are not confirmed sites. The system ranks areas for investigation; it does not confirm land ownership, planning permission, substrate contracts, gas/electric capacity, environmental approval or project economics.

## Run the explorer

Python 3.11 or newer is recommended.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
streamlit run sergio_biometano_app/app.py
```

The repository includes the compact v49 snapshots and the simplified GeoJSON layers required by the app. Internet access is needed for the remote base maps and the official SNCZI flood service.

After selecting a cell, the **Exportaciones** section can download a comparison
CSV, a one-page summary or a four-section detailed PDF. The detailed report
records coordinates, screening evidence, technical proxies, unresolved
prefactibility gates, source vintages and limitations. It is a review checklist,
not a cadastral, engineering, permitting or investment dossier.

## Model benchmark

The supervised benchmark compares four classifiers under two readings:

1. **Calibration fit:** Spain, France and Italy are included in training. This is not independent validation.
2. **Transfer fit:** the model is trained on France and Italy and evaluated on Spain. This is the more honest stress test.

| Model | Transfer AP | Transfer ROC AUC | Positives in top 250 |
| --- | ---: | ---: | ---: |
| Logistic Regression | 0.0059 | 0.7450 | 3 |
| Random Forest | 0.0136 | 0.7418 | 3 |
| Gradient Boosting | 0.0077 | 0.8071 | 3 |
| Linear SVM | 0.0089 | 0.7837 | 6 |

There is **no defensible champion**. Random Forest leads transfer AP, Gradient Boosting leads transfer ROC AUC and Linear SVM retrieves more labelled positives in the top 250. Labels are sparse and unlabeled cells are weak negatives, not verified true negatives.

### Spatial validation v5

The follow-up benchmark uses 100 km EPSG:3035 groups, 4 outer folds and 3
inner folds on France/Italy. Spain is excluded from family selection,
hyperparameter selection and missing-indicator selection.

| Model | Nested spatial CV AP | Spain AP | Spain ROC AUC | Positives in top 250 |
| --- | ---: | ---: | ---: | ---: |
| Logistic Regression | 0.0763 | 0.0070 | 0.7801 | 4 |
| Linear SVM | 0.0752 | 0.0082 | 0.7984 | 4 |
| Random Forest | 0.0943 | 0.0157 | 0.6595 | 2 |
| Gradient Boosting | 0.0886 | 0.0090 | 0.8032 | 4 |

Random Forest was preselected only from FR/IT spatial CV, but it failed the
locked Spain transfer gate: its AP gain was not materially large, the 95%
bootstrap lower bound did not exceed v4 and top-250 capture fell from 6 to 2.
It was **not promoted to the app**. The audit also found 12/31 features with a
missingness shift above 20 percentage points and four livestock/manure
features missing in 99.03% of the Spanish-domain cells. Probability calibration
and a decisional threshold remain blocked because there are no confirmed
negatives. See [the v5 report](docs/model_benchmark_v5_report.md).

The fitted benchmark bundle is included at:

```text
models/benchmark_classifiers_mediterranean_proxy_v4.joblib
```

The spatially validated but **rejected-for-deployment** v5 bundle is retained
for reproducibility at
`models/benchmark_classifiers_mediterranean_proxy_v5.joblib`. Its metadata
marks the score as ranking-only, calibration as blocked and promotion as false.

Only load Joblib/Pickle artifacts from a trusted source. See [SECURITY.md](SECURITY.md).

## Retraining

The portable training entry point is:

```bash
pip install -r requirements-model.txt
python scripts/train_benchmark.py
```

The stricter spatial benchmark is run separately so the deployment environment
does not need scikit-learn:

```bash
python -m scripts.train_spatial_benchmark --input path/to/biometano_grid5km_curated_v4_attributes.parquet
```

The curated training feature table is intentionally **not redistributed** because one of its inputs, WorldClim, does not permit redistribution without prior permission. The expected schema and preparation note are in [data/modeling/README.md](data/modeling/README.md).

## Repository structure

```text
sergio_biometano_app/   Streamlit explorer and pure decision logic
models/                 Fitted classifier benchmark
scripts/                Portable benchmark training entry point
data/modeling/          Expected training schema, without restricted source data
docs/                   Methodology, audits, metrics and validation evidence
tests/                  Source-level and semantic tests
```

## What v49 means

v49 does not claim to be a new viability classifier. It separates:

- relative screening priority;
- available evidence and its completeness;
- physical exclusions;
- digestate risk in nitrate-vulnerable zones;
- critical prefactibility gates still missing.

Nitrate-vulnerable zones are treated as a digestate-management risk, not as a universal location veto. Distance to gas, electricity or roads is a proxy and does not prove connection capacity.

## Known limitations

- Few confirmed Spanish positives and no verified negative-site register.
- Italy is used as a medium-confidence proxy; Greece is context only because coverage was too sparse.
- National feedstock variables are partly macro/regional proxies.
- The 1 km layer is a refinement of a prioritised universe, not exhaustive national 1 km coverage.
- No cadastral, planning, ownership, commercial, social-acceptance or connection-capacity confirmation.
- Results must be validated at parcel and project level before any investment decision.

Read [docs/AUDITORIA_CRITICA_MODELO.md](docs/AUDITORIA_CRITICA_MODELO.md) and [docs/MODELO_Y_METODOLOGIA.md](docs/MODELO_Y_METODOLOGIA.md) before using the rankings.

## Licences and attribution

- Source code: [MIT](LICENSE).
- Project database/snapshots: [ODbL 1.0](DATA_LICENSE.md), subject to upstream rights and attribution requirements.
- Documentation: CC BY 4.0.

See [SOURCES.md](SOURCES.md) for source-specific credits and restrictions. In particular, the repository does not redistribute WorldClim climate data.

## Citation

If this project helps your work, cite the repository URL, version/date and the upstream datasets listed in [SOURCES.md](SOURCES.md).
