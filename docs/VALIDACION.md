# Validación de la versión 1.3.0 / método v49

Fecha de corte: **10 de julio de 2026**.

## Resultado

- Suite automatizada: **69/69 tests superados**.
- Auditoría funcional adversarial: **32/32 checks superados**, 0 fallos críticos.
- Auditoría real en Chrome: **11/11 checks superados**, 0 fallos críticos.
- Render Streamlit: cobertura nacional 5 km y refinamiento 1 km sin excepciones.
- Lanzador Windows real: dry-run, arranque en el puerto dedicado 8529, health-check y cierre verificados.
- Tema oscuro, contraste del panel lateral, escritorio y móvil verificados.
- Fondos oscuro, satélite y topográfico activados en navegador real.
- Exportaciones CSV y PDF verificadas.

## Gates de datos

| Gate | Resultado |
|---|---:|
| Celdas nacionales 5 km únicas | 21.519 / 21.519 |
| Celdas refinadas 1 km únicas | 30.450 / 30.450 |
| Intersecciones con nitratos preservadas como riesgo de digestato | 15.830 |
| Vetos cuyo único motivo es nitratos | 0 |
| Exclusiones físicas explícitas 1 km | 1.115 |
| Distancia a planta operativa calculada | 100 % |
| Plantas representadas en el cálculo de proximidad | 24 |
| Celdas declaradas prefactibles sin dossier | 0 |
| Duplicados padre 5 km dentro del Top-25 provincial | 0 |
| Hashes de entradas y salidas | Coinciden |
| Snapshot v48 original | Inalterado |

## Validación cartográfica

- El límite de 250 marcadores nacionales usa muestreo espacial equilibrado: no elimina Canarias ni regiones periféricas.
- Los agregados nacionales se colorean por la prioridad dominante, no por el mejor hijo aislado.
- El mapa conserva las tres clases de prioridad y las exclusiones físicas.
- Las capas de nitratos, gas, carreteras, electricidad, plantas, Natura 2000, suelo construido, materia prima e inundación permanecen disponibles.

## Límites que la validación no elimina

La validación confirma consistencia técnica y semántica de la aplicación. No convierte los proxies en capacidad de red, contratos de sustrato, clasificación urbanística, permiso ambiental, aceptación social ni rentabilidad. La decisión de proyecto exige completar los gates de prefactibilidad que aparecen en cada ficha.

## Evidencia reproducible

- `docs/sergio_app_v49_functionality_adversarial_audit.json`
- `docs/sergio_app_v49_browser_adversarial_audit.json`
- `docs/biometano_v49_evidence_system_metrics.json`
- `sergio_biometano_app/data/provenance_manifest_v49.json`
