# Seguridad — Quant Lab (STRIDE, antes de codificar)

| # | Categoría STRIDE | Amenaza | Mitigación |
|---|---|---|---|
| 1 | **Tampering** (manipulación) | El documento del reporte (10-K) es texto no confiable: podría contener instrucciones que intenten manipular al LLM para que invente cifras, ignore las reglas de cita o cambie su propio comportamiento. | El texto del documento y del usuario van en su propio rol, nunca concatenados al prompt del sistema. El LLM nunca calcula cifras (eso lo hace `calc/`); solo resume. El verificador (`verify/`) rechaza cualquier cita que no exista literalmente en el documento guardado, venga o no del LLM. |
| 2 | **Information Disclosure** (fuga de información) | Llaves de API, el contacto de `EDGAR_CONTACT`, o datos personales/de portafolio terminan en el repo, en commits, en README o en tests. | Llaves y contacto solo en `.env` (gitignorado, permisos 0600); `.env.example` sin valores reales. Ningún código, doc o test menciona portafolios, tickers propios ni datos personales — solo "empresa de ejemplo". Escaneo de secretos antes de cada PR (skill `auditoria-seguridad`). |
| 3 | **Denial of Service / abuso de la fuente externa** | El ingestor excede el límite de tasa de SEC EDGAR (riesgo de bloqueo de IP) o descarga documentos sin límite de tamaño/tiempo, agotando memoria, disco o la cuota del LLM. | `ingest/` usa 1 solicitud/segundo con backoff en 429/5xx, timeout en cada solicitud y tope de tamaño de archivo. Toda llamada al LLM tiene tope de tokens de entrada y de salida. |

## Actualización — Fase 5 (llm/)

La mitigación de Tampering de arriba se volvió más fuerte de lo planeado: `llm/summarizer.py`
**nunca envía el texto crudo del documento al modelo**. Solo recibe el JSON de hechos que
`extract/` calculó y `verify/` ya confirmó contra el documento guardado (ver SPEC.md sección 5 y
el docstring de `llm/summarizer.py`). Una instrucción escondida en el 10-K no tiene ninguna vía
para llegar al modelo porque el modelo nunca lee el 10-K.

Además, cada línea de la respuesta del LLM se descarta si no cita una clave real del JSON que se
le dio (`enforce_citations`): no se confía en que el modelo siguió la regla del prompt, se
comprueba después, de forma determinista — el mismo espíritu del verificador de citas, aplicado
a la salida del LLM.

Revisar y ampliar esta tabla en cada fase que añada una superficie nueva (ej. si se agrega una
interfaz web).
