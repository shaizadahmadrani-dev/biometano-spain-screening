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
