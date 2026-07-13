# Benchmark espacial v5 del modelo de biometano

Fecha UTC: 2026-07-13T19:41:28.649932+00:00

## Qué se ha validado

Se comparan Logistic Regression, Random Forest, Gradient Boosting y Linear SVM
mediante validación cruzada espacial anidada en Francia e Italia. `is_spain` es
la frontera canónica: toda celda española permanece fuera de selección, ajuste
de hiperparámetros, preprocessing y calibración. Se evalúa al final como prueba
de transferencia, pero se reconoce que España ya fue utilizada históricamente
en v4 y no equivale a una nueva confirmación independiente.

## Resultados

| modelo | AP_CV | std_AP | AP_Espana | AUC_Espana | top100 | top250 | seleccionado |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Logistic Regression | 0.0763 | 0.0053 | 0.0070 | 0.7801 | 1 | 4 | no |
| Linear SVM | 0.0752 | 0.0065 | 0.0082 | 0.7984 | 0 | 4 | no |
| Random Forest | 0.0943 | 0.0110 | 0.0157 | 0.6595 | 1 | 2 | sí |
| Gradient Boosting | 0.0886 | 0.0082 | 0.0090 | 0.8032 | 3 | 4 | no |

El modelo preseleccionado exclusivamente por CV espacial es
**Random Forest**. Su AP en España es
`0.015725` frente a
`0.013624` del mejor benchmark v4.
El intervalo bootstrap estratificado del 95% para la AP es
`[0.001797,
0.091334]`.

## Calibración y umbral

Estado: **blocked_weak_labels**. No se publica una probabilidad
calibrada porque las celdas sin planta conocida son negativos débiles, no
casos negativos confirmados. Brier, log loss y curvas de fiabilidad sobre esas
etiquetas podrían parecer precisos y, aun así, ser conceptualmente falsos.

Los cortes top-k se conservan únicamente como
`weak_label_reference_only`: describen qué habría ocurrido al revisar una
capacidad fija de celdas, pero NO son un umbral de construir/no construir.

## Valores ausentes

Se auditaron 31 variables. Hay 12 con una
diferencia de ausencia superior a 20 puntos porcentuales entre FR/IT y España.
No se elimina ninguna automáticamente: cada desplazamiento queda marcado para
revisión y la imputación mediana se compara de forma explícita con indicadores
de ausencia. Esta opción forma parte de cada candidato y se selecciona dentro
del inner CV; no se activa después mirando los outer folds.

Variables totalmente ausentes en España:
`ninguna`.
Variables con al menos un 95% de valores ausentes en España:
`manure_tonnes_2020_mnr_exp_lq_sl, manure_tonnes_2020_mnr_exp_so, bovine_lsu_2023, poultry_lsu_2023`.
La ausencia casi total también bloquea la promoción: unas pocas celdas de
frontera no convierten una variable en nacionalmente disponible.

## Stacking

Estado: **deferred_out_of_scope**. El stacking queda formalmente fuera
del alcance de esta iteración porque los modelos base no transfieren de forma
estable y reutilizar España para decidir si conservarlo convertiría el test en
parte del ajuste.

## Decisión de promoción

Promoción a la app: **no**.
Motivos: la AP en España no alcanza el efecto mínimo (20% relativo y 0,005 absoluto), el límite inferior bootstrap del 95% para AP no supera la referencia v4, la recuperación top-250 en España empeora frente a v4, hay variables requeridas con al menos un 95% de valores ausentes en España, no existe un nuevo conjunto temporal o adjudicado de confirmación independiente.
Si no supera la puerta, la app conserva el ranking v49; el resultado v5 queda
como evidencia de validación, no se fuerza una mejora cosmética.

## Límites

- El target es presencia observada/proxy de plantas, no viabilidad de proyecto.
- No hay negativos confirmados ni validación parcelaria, de conexión o permiso.
- Italia aporta etiquetas proxy de confianza media.
- España contiene 26 celdas positivas; la incertidumbre de las métricas es alta.
