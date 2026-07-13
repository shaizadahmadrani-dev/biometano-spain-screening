# Biomethane Spain Screening

Open academic project for exploring where to **prioritise further evidence gathering** for biomethane projects in Spain.

It combines a Mediterranean classification benchmark with a two-scale territorial explorer:

- **5 km:** national screening across 21,519 land cells.
- **1 km:** refined review across 30,450 cells inside the previously prioritised universe.
- **Interactive app:** map, filters, evidence, physical exclusions, scenario weights and exports.
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

The fitted benchmark bundle is included at:

```text
models/benchmark_classifiers_mediterranean_proxy_v4.joblib
```

Only load Joblib/Pickle artifacts from a trusted source. See [SECURITY.md](SECURITY.md).

## Retraining

The portable training entry point is:

```bash
pip install -r requirements-model.txt
python scripts/train_benchmark.py
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
