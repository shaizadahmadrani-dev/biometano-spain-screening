# Data sources and attribution

This project combines public, open and source-specific datasets. The application
snapshots contain derived indicators and screening outputs, not the original raw files.

| Source | Use in the project | Terms / attribution |
| --- | --- | --- |
| Eurostat / GISCO | European 5 km grid, population and regional agricultural statistics | Reuse is generally authorised with source acknowledgement and notice of modifications. https://ec.europa.eu/eurostat/help/copyright-notice |
| IGN/CNIG Spain | Roads, combustible conductions and other official Spanish geographic layers | Free use, including commercial publication, with attribution to IGN/CNIG and compliance with dataset-specific terms. https://centrodedescargas.cnig.es/CentroDescargas/faqs |
| MITECO | Natura 2000, nitrate-vulnerable zones and environmental constraints | Reuse permitted under the Spanish public-sector reuse conditions; cite MITECO, preserve metadata and do not imply endorsement. https://www.datosabiertos.miteco.gob.es/es/aviso-legal.html |
| ESA WorldCover 2021 | Land-cover shares | CC BY 4.0. Credit: © ESA WorldCover project / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium. https://worldcover2021.esa.int/documentation |
| European Environment Agency / Copernicus | CORINE and related environmental context | EEA materials are generally CC BY unless a dataset states otherwise; retain dataset-specific attribution. https://www.eea.europa.eu/en/legal-notice |
| OpenStreetMap contributors | Proxy gas/biogas infrastructure and base-map content | ODbL 1.0; credit OpenStreetMap and contributors and keep adapted databases open. https://www.openstreetmap.org/copyright |
| ODRÉ France | Operating biomethane injection points | Licence Ouverte v2.0 (Etalab), with source attribution. https://odre.opendatasoft.com/explore/dataset/points-dinjection-de-biomethane-en-france/ |
| WorldClim | Bioclimatic variables used during model development | Academic/non-commercial use; redistribution or commercial use requires prior permission. Climate feature tables are therefore not included. https://worldclim.org/about.html |
| Sedigas / Gasnam | Spanish plant-label reconciliation and sector context | Publicly visible sector information used as a weak label source. Verify provider terms and current plant status before reuse or operational decisions. |

Other inputs and exact file hashes are recorded in
`sergio_biometano_app/data/provenance_manifest_v49.json`.

## Required interpretation

- Modified and aggregated data are the responsibility of this project, not the upstream providers.
- No provider endorses the rankings.
- Source vintages differ; consult the manifest before comparing with current conditions.
- Gas and electricity distance indicators do not confirm available connection capacity.

