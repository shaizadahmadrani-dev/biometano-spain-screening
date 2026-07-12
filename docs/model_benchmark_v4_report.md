# Benchmark classificadors v4

Data: 2026-07-03 16:16:51

## Models comparats

- Logistic Regression
- Random Forest
- Gradient Boosting
- Linear SVM

## Resultat resum

| model | calib_ap | calib_auc | transfer_ap | transfer_auc | transfer_top100 | transfer_top250 |
| --- | --- | --- | --- | --- | --- | --- |
| Random Forest | 1.0000 | 1.0000 | 0.0136 | 0.7418 | 2 | 3 |
| Linear SVM | 0.0237 | 0.8474 | 0.0089 | 0.7837 | 1 | 6 |
| Gradient Boosting | 0.1933 | 0.9709 | 0.0077 | 0.8071 | 1 | 3 |
| Logistic Regression | 0.0296 | 0.8366 | 0.0059 | 0.7450 | 1 | 3 |

## Lectura

- La columna important és `transfer_ap`: entrenar sense Espanya i avaluar contra Espanya.
- El calibratge amb Espanya dins del training **no és validació independent**.
- Random Forest fa `1.0000` en calibratge in-sample: això és senyal clar d'overfit/memorització, no una victòria real.
- Tot i que Random Forest lidera l'AP de transferència, no s'hauria d'usar com a model final sense validació espacial/country-blocked addicional.
- En aquest problema de screening, AP i top-k són més accionables que ROC AUC; un AUC alt no garanteix una bona shortlist territorial.
- Lectura recomanada: **No hi ha guanyador net. Random Forest té la millor AP de transferència, Linear SVM recupera més positius al top-250, i Gradient Boosting té millor ROC AUC. La recomanació defensable és auditar els top candidats i els filtres territorials, no triar un champion final.**.

## Caveat

Això continua sent un benchmark de screening amb labels forts ES/FR i proxy Itàlia. No és decisió final d'ubicació.
