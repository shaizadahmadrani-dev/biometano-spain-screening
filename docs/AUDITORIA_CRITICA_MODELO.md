# Auditoría crítica del sistema v49

## Dictamen

La aplicación es defendible como **herramienta de cribado para decidir dónde adquirir evidencia primero**. No es defendible como probabilidad de éxito, veredicto de viabilidad, permiso ni recomendación automática de inversión.

## Qué se corrigió

- Se separa la **cobertura nacional de 5 km** (21.519 celdas) del **refinamiento de 1 km** (30.450 celdas del universo previamente priorizado).
- La intersección con zonas vulnerables a nitratos pasa a ser **riesgo de gestión del digestato**, no veto universal de emplazamiento.
- Se muestran por separado la prioridad, la evidencia de screening y la prefactibilidad.
- Ninguna celda se declara prefactible sin verificar contrato y calidad de sustratos, conexiones, parcela, urbanismo, digestato, agua, permisos, offtake y economía.
- La distancia a plantas operativas se recalculó para todas las celdas refinadas contra las 24 plantas etiquetadas.
- El Top provincial evita elegir varios hijos de 1 km del mismo padre de 5 km.

## Calidad cuantitativa disponible

- Plantas operativas etiquetadas: **24**.
- Negativos reales confirmados: **0**.
- ROC AUC del ranking previo: **0,804**.
- Average Precision: **0,0153**.
- Celdas refinadas con riesgo alto de digestato: **15.830**.
- Vetos cuyo único motivo sigue siendo nitratos: **0**.
- Exclusiones físicas explícitas en la capa 1 km: **1.115**.
- Celdas declaradas prefactibles sin dossier: **0**.

El ROC AUC indica capacidad de ordenación global, pero el Average Precision es bajo porque la clase positiva es extremadamente rara y las etiquetas son incompletas. Sin negativos reales no puede hablarse de precisión operativa de viabilidad.

## Riesgos que siguen abiertos

1. Las señales nacionales de materia prima son proxies macro; no acreditan toneladas contratables ni estacionalidad.
2. Las distancias a gas y electricidad no acreditan capacidad, presión, tensión, coste ni plazo de conexión.
3. La capa de 5 km no sustituye Catastro, planeamiento, servidumbres, inundabilidad ni estudio ambiental parcelario.
4. El suelo construido de WorldCover no equivale jurídicamente a clasificación urbanística.
5. Las celdas sin planta conocida son no etiquetadas, no negativos verdaderos.
6. La economía del proyecto y la aceptación social todavía requieren datos específicos.

## Uso correcto

Usar el mapa para generar una lista diversa de zonas, encargar comprobaciones oficiales y descartar progresivamente. No presentar un color verde ni una puntuación alta como prueba de que una planta puede construirse.
