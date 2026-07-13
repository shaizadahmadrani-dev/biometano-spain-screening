# Modelo y metodología v49

## Objetivo

v49 responde a una pregunta concreta: **¿en qué zonas merece la pena invertir primero en obtener evidencia de prefactibilidad para una planta de biometano?**

No intenta estimar la probabilidad de construir una planta. El número 0–100 es una prioridad relativa de investigación.

## Dos escalas complementarias

1. **Cobertura nacional 5 km — 21.519 celdas.** Compara todo el territorio español mediante señales homogéneas. Es la vista inicial de la aplicación.
2. **Refinamiento priorizado 1 km — 30.450 celdas.** Añade detalle dentro de 1.218 celdas padre que el sistema anterior había preseleccionado. No es una malla nacional exhaustiva.

No se expandió artificialmente cada celda nacional a 25 hijos de 1 km, porque eso habría repetido los mismos datos macro y creado falsa precisión.

## Señales de screening

- **Materia prima:** ganadería, cultivos, estiércoles y otros indicadores territoriales.
- **Residuos orgánicos:** depuradoras y proximidad a fuentes de residuo.
- **Conectividad:** distancia orientativa a corredores gasistas y carreteras.
- **Compatibilidad territorial:** suelo agrícola, suelo construido, Natura 2000 y otras restricciones disponibles.
- **Robustez del ranking:** acuerdo entre los clasificadores históricos.

Estas señales son proxies. La proximidad no demuestra capacidad y un índice alto no equivale a suministro contratado.

## Estados v49

- **Prioridad alta de investigación:** conviene adquirir evidencia aquí antes.
- **Prioridad media de investigación:** señales útiles con condicionantes o incertidumbre.
- **Prioridad baja de investigación:** otras zonas merecen investigarse primero.
- **Descartado por filtro físico:** existe una exclusión física explícita en el screening refinado.

## Nitratos y digestato

La zona vulnerable a nitratos no se usa como veto universal de ubicación. Activa `riesgo de digestato = alto` y obliga a estudiar balance de nitrógeno, superficie receptora, almacenamiento, transporte y normativa autonómica.

## Prefactibilidad separada

La aplicación no declara una celda prefactible hasta verificar todos estos gates:

1. contrato de suministro;
2. calidad de sustratos;
3. capacidad gasista;
4. capacidad eléctrica;
5. Catastro y disponibilidad de parcela;
6. compatibilidad urbanística;
7. plan de digestato;
8. agua e hidrología;
9. permisos ambientales;
10. offtake;
11. economía completa del proyecto.

## Validación

El ranking histórico obtuvo ROC AUC 0,804 y Average Precision 0,0153 con 24 plantas operativas etiquetadas y sin negativos reales confirmados. Por eso se conserva como señal de ordenación, no como clasificador calibrado de viabilidad.

### Validación espacial v5

Se añadió una validación cruzada espacial anidada sobre Francia e Italia:

- bloques deterministas de 100 km en EPSG:3035;
- 4 folds externos para estimar estabilidad y 3 internos para hiperparámetros;
- selección por Average Precision media, con dispersión y mínimo por fold;
- España completamente fuera de selección hasta la prueba de transferencia;
- análisis explícito de imputación mediana frente a indicadores de ausencia.

Random Forest obtuvo la mejor AP espacial FR/IT (0,0943) y alcanzó AP 0,0157 y
ROC AUC 0,6595 en España. Aunque la AP puntual supera v4 un 15,4% relativo, no
alcanza el efecto mínimo absoluto de 0,005, el límite inferior bootstrap del
95% queda por debajo de v4 y el top-250 cae de 6 a 2 positivos. Por eso **no se
incorporó a la aplicación**. Tampoco se elige retrospectivamente otro modelo
mirando España.

El análisis de calidad encontró 12 de 31 variables con diferencias de
missingness superiores a 20 puntos porcentuales. Las dos variables de estiércol
y las variables bovina y avícola faltan en el 99,03% del dominio español; unas
pocas celdas fronterizas no equivalen a cobertura nacional. Antes de volver a
entrenar conviene armonizar estas fuentes o definir un conjunto común de
cobertura.

### Calibración

No se publica una probabilidad calibrada. Las celdas sin planta conocida son
negativos débiles, no fracasos o emplazamientos inviables confirmados. Sin una
muestra adjudicada que contenga positivos y negativos, Brier, log loss,
isotónica o Platt sólo darían una apariencia de precisión. Los cortes top-k se
mantienen como diagnóstico de capacidad de revisión, nunca como umbral de
construir/no construir.
